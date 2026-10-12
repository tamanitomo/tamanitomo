#!/usr/bin/env python3
"""What the human watches, from their own Plex or Jellyfin server, and what you watch together.

Someone who shares a life knows what the other has been watching: that a series was
finished last night, that a film is half over right now, that the two of them are three
episodes into something together. This reads the human's own media server, and nothing
else:

- `sense` (the "viewing" sensor) says what is on now, what was finished lately and where
  each series is up to;
- `viewing.jsonl` keeps every episode or film the server reported finished, so the memory
  outlasts the server's own history and every later read agrees with it;
- `together` records an agreement to watch something together. While it holds, what the
  human plays of that title is kept as watched together, and she is told what the
  episode is about, so she can watch along without inventing scenes.
- Manual sessions need no server: their progress comes only from explicit human
  reports. Pause/resume/end track participation, not remote playback. Personal
  moments keep conversation evidence and link to the relationship memory.

No model is called; manual sessions make no network requests. Only an explicitly
configured media server is contacted by the sensor. Its address, kind and the human's
account are in companion.json; the token is read from media_token_file, so no secret sits
there. The titles reach her model provider like everything else in her context, which
the setting says.
"""

from __future__ import annotations
import argparse
import contextlib
import contextvars
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
import companion_self as slf
from companion_platform import file_lock

TIMEOUT = 8
# A read made during a chat turn must not hold the reply up for long.
QUICK_TIMEOUT = 3
# The first read goes back two weeks; later reads overlap the last kept row by a day,
# because a server can report a viewing a little after the fact.
HISTORY_DAYS = 14
LATELY_DAYS = 10
LATELY_SHOWN = 4
TOGETHER_HOURS = (1, 8)
# A server marks an episode watched near its end, which can fall just past the window.
TOGETHER_GRACE = dt.timedelta(minutes=30)
SUMMARY_LIMIT = 280
# Jellyfin lists every session it has seen recently; only these count as on now.
ACTIVE_SECONDS = 960
TICKS_PER_MINUTE = 600_000_000
GENERIC_EPISODE = re.compile(r"^(episode|ep\.?)\s*\d+$", re.I)


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def path_for(c):
    return c.life / "viewing.jsonl"


def _invalidate_context(c, result):
    """A participation change makes the last sensor picture stale immediately."""
    if result.get("written"):
        for path in (
            c.soul_dir / "ambient/viewing.md",
            c.home / "state/viewing-refreshed",
        ):
            path.unlink(missing_ok=True)
    return result


def token_path(c):
    """Where the app keeps a token typed into Settings. A `secrets` folder stays out of backups."""
    return c.home / "secrets" / "media-server.token"


def _token(c):
    if not c.media_token_file:
        return None
    try:
        token = (
            pathlib.Path(c.media_token_file)
            .expanduser()
            .read_text(encoding="utf-8")
            .strip()
        )
    except OSError:
        return None
    return token or None


def configured(c):
    return bool(c.media_server and _token(c))


def source_name(c):
    return "Plex" if c.media_kind == "plex" else "Jellyfin"


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _time(value):
    if isinstance(value, dt.datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    # Jellyfin writes seven fractional digits and a Z, which fromisoformat refuses
    # before Python 3.11 and misreads in none of the versions we run.
    text = re.sub(r"(\.\d{6})\d+", r"\1", text).replace("Z", "+00:00")
    try:
        when = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)


_timeout = contextvars.ContextVar("companion_viewing_timeout", default=TIMEOUT)


@contextlib.contextmanager
def quick():
    """Shorter waits for reads made while a reply is being prepared."""
    token = _timeout.set(QUICK_TIMEOUT)
    try:
        yield
    finally:
        _timeout.reset(token)


def _get(c, path, params=()):
    """One GET against the server. The token travels in a header, never in the URL."""
    token = _token(c)
    if not token:
        raise ValueError("the media server token is missing or unreadable")
    # Plex filters history with `viewedAt>=N`, which must reach it unescaped.
    query = "&".join(
        (
            f"{key}={value}"
            if key.endswith(">")
            else f"{key}={urllib.parse.quote(str(value), safe=',:')}"
        )
        for key, value in params
    )
    if c.media_kind == "plex":
        headers = {
            "X-Plex-Token": token,
            "X-Plex-Product": "Tamanitomo",
            "X-Plex-Client-Identifier": "tamanitomo",
        }
    else:
        headers = {
            "Authorization": f'MediaBrowser Token="{token}"',
            "X-Emby-Token": token,
        }
    url = c.media_server.rstrip("/") + path + (f"?{query}" if query else "")
    request = urllib.request.Request(
        url,
        headers={**headers, "Accept": "application/json", "User-Agent": "tamanitomo"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_timeout.get()) as response:
            body = response.read(4_000_000)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError(f"{source_name(c)} refused the token") from None
        raise ValueError(f"{source_name(c)} answered {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise ValueError(f"could not reach {source_name(c)}: {reason}") from None
    try:
        return json.loads(body or b"null")
    except ValueError:
        raise ValueError(f"{source_name(c)} did not answer with JSON") from None


# ---- Plex ------------------------------------------------------------------
def _plex_account(c):
    """The human's account on the server: its owner (always 1) unless media_user names another."""
    if not c.media_user:
        return "1"
    container = (_get(c, "/accounts") or {}).get("MediaContainer") or {}
    for row in container.get("Account") or []:
        if str(row.get("name") or "").casefold() == c.media_user.casefold():
            return str(row.get("id"))
    raise ValueError(f"{source_name(c)} has no account called {c.media_user!r}")


def _plex_item(row):
    what = row.get("type")
    if what not in ("episode", "movie"):
        return None
    episode = what == "episode"
    year = _int(row.get("year"))
    if not year and row.get("originallyAvailableAt"):
        year = _int(str(row["originallyAvailableAt"])[:4])
    return {
        "key": str(
            row.get("ratingKey") or row.get("key") or row.get("historyKey") or ""
        ),
        "what": what,
        "show": (
            str(row.get("grandparentTitle") or "").strip() or None if episode else None
        ),
        "season": _int(row.get("parentIndex")) if episode else None,
        "episode": _int(row.get("index")) if episode else None,
        "title": str(row.get("title") or "").strip(),
        "year": None if episode else year,
    }


def _plex_history(c, since):
    account = _plex_account(c)
    params = [
        ("sort", "viewedAt:desc"),
        ("accountID", account),
        ("viewedAt>", int(since.timestamp())),
        ("X-Plex-Container-Start", 0),
        ("X-Plex-Container-Size", 200),
    ]
    container = (_get(c, "/status/sessions/history/all", params) or {}).get(
        "MediaContainer"
    ) or {}
    found = []
    for row in container.get("Metadata") or []:
        # Some servers ignore the filters; the rows still say whose and when.
        if str(row.get("accountID")) != account or not row.get("viewedAt"):
            continue
        item = _plex_item(row)
        at = dt.datetime.fromtimestamp(int(row["viewedAt"]), dt.timezone.utc)
        if item and at >= since:
            found.append({**item, "at": at})
    return found


def _plex_now(c):
    account = _plex_account(c)
    container = (_get(c, "/status/sessions") or {}).get("MediaContainer") or {}
    found = []
    for row in container.get("Metadata") or []:
        user = row.get("User") or {}
        mine = str(user.get("id")) == account or (
            c.media_user
            and str(user.get("title") or "").casefold() == c.media_user.casefold()
        )
        item = _plex_item(row) if mine else None
        if not item:
            continue
        found.append(
            {
                **item,
                "position_min": round(int(row.get("viewOffset") or 0) / 60000),
                "length_min": round(int(row.get("duration") or 0) / 60000) or None,
                "paused": (row.get("Player") or {}).get("state") == "paused",
                "summary": str(row.get("summary") or "").strip(),
            }
        )
    return found


def _plex_summary(c, key):
    container = (_get(c, f"/library/metadata/{urllib.parse.quote(key)}") or {}).get(
        "MediaContainer"
    ) or {}
    rows = container.get("Metadata") or [{}]
    return str(rows[0].get("summary") or "").strip()


# ---- Jellyfin --------------------------------------------------------------
def _jellyfin_user(c):
    """(id, name) of the human's account: the one media_user names, else the administrator."""
    users = _get(c, "/Users") or []
    for row in users:
        if (
            c.media_user
            and str(row.get("Name") or "").casefold() == c.media_user.casefold()
        ):
            return str(row["Id"]), row["Name"]
    if not c.media_user:
        for row in users:
            if (row.get("Policy") or {}).get("IsAdministrator"):
                return str(row["Id"]), row["Name"]
    raise ValueError(
        f"{source_name(c)} has no account called {c.media_user!r}"
        if c.media_user
        else f"{source_name(c)} has no administrator account to read"
    )


def _jellyfin_item(row):
    what = {"Episode": "episode", "Movie": "movie"}.get((row or {}).get("Type"))
    if not what:
        return None
    episode = what == "episode"
    return {
        "key": str(row.get("Id") or ""),
        "what": what,
        "show": str(row.get("SeriesName") or "").strip() or None if episode else None,
        "season": _int(row.get("ParentIndexNumber")) if episode else None,
        "episode": _int(row.get("IndexNumber")) if episode else None,
        "title": str(row.get("Name") or "").strip(),
        "year": None if episode else _int(row.get("ProductionYear")),
    }


def _jellyfin_history(c, since):
    user, _ = _jellyfin_user(c)
    params = [
        ("SortBy", "DatePlayed"),
        ("SortOrder", "Descending"),
        ("Filters", "IsPlayed"),
        ("IncludeItemTypes", "Episode,Movie"),
        ("Recursive", "true"),
        ("Limit", 200),
    ]
    data = _get(c, f"/Users/{user}/Items", params) or {}
    found = []
    for row in data.get("Items") or []:
        at = _time((row.get("UserData") or {}).get("LastPlayedDate"))
        if not at or at < since:
            continue
        item = _jellyfin_item(row)
        if item:
            found.append({**item, "at": at})
    return found


def _jellyfin_now(c):
    user, _ = _jellyfin_user(c)
    found = []
    for session in (
        _get(c, "/Sessions", [("ActiveWithinSeconds", ACTIVE_SECONDS)]) or []
    ):
        row = session.get("NowPlayingItem")
        if str(session.get("UserId")) != user or not row:
            continue
        item = _jellyfin_item(row)
        if not item:
            continue
        play = session.get("PlayState") or {}
        found.append(
            {
                **item,
                "position_min": round(
                    int(play.get("PositionTicks") or 0) / TICKS_PER_MINUTE
                ),
                "length_min": round(
                    int(row.get("RunTimeTicks") or 0) / TICKS_PER_MINUTE
                )
                or None,
                "paused": bool(play.get("IsPaused")),
                "summary": str(row.get("Overview") or "").strip(),
            }
        )
    return found


def _jellyfin_summary(c, key):
    user, _ = _jellyfin_user(c)
    row = _get(c, f"/Users/{user}/Items/{urllib.parse.quote(key)}") or {}
    return str(row.get("Overview") or "").strip()


def history(c, since):
    """Episodes and films the human finished since `since`, newest first, as the server says."""
    return (_plex_history if c.media_kind == "plex" else _jellyfin_history)(c, since)


def now_playing(c):
    """What the human has on right now (playing or paused). Music is left to the music sensor."""
    return (_plex_now if c.media_kind == "plex" else _jellyfin_now)(c)


def _summary(c, item):
    text = item.get("summary") or ""
    if not text and item.get("key"):
        try:
            text = (_plex_summary if c.media_kind == "plex" else _jellyfin_summary)(
                c, item["key"]
            )
        except ValueError:
            text = ""
    text = " ".join(text.split())
    if len(text) <= SUMMARY_LIMIT:
        return text
    cut = text[:SUMMARY_LIMIT].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


# ---- what is kept ----------------------------------------------------------
def label(item):
    if item.get("what") == "episode":
        name = item.get("show") or item.get("title") or "an episode"
        if item.get("season") is not None and item.get("episode") is not None:
            name += f" S{item['season']}E{item['episode']}"
        title = item.get("title") or ""
        if title and title != item.get("show") and not GENERIC_EPISODE.match(title):
            name += f" “{title}”"
        return name
    title = item.get("title") or "a film"
    return f"{title} ({item['year']})" if item.get("year") else title


def _norm(text):
    text = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return " ".join(re.findall(r"[^\W_]+", text, re.UNICODE))


def matches(title, item):
    """Whether something played is the title agreed on: the series, or the film."""
    want, have = _norm(title), _norm(item.get("show") or item.get("title"))
    if not want or not have:
        return False
    # Prefixes confuse sequels and remakes. A year may disambiguate a film, but
    # an otherwise different title needs a separate agreement.
    return have == want or bool(
        item.get("year") and want == _norm(f"{item.get('title')} {item['year']}")
    )


def seen(c):
    """Everything kept as finished, oldest first."""
    rows = [r for r in slf._read(path_for(c)) if r.get("kind") == "seen"]
    return sorted(rows, key=lambda r: _time(r["at"]))


def agreements(c, at=None):
    """Fold the append-only session log, including agreements from older releases."""
    found = {}
    for row in slf._read(path_for(c)):
        if row.get("kind") == "together":
            begun = _time(row["from"])
            if at and begun > at:
                continue
            found[row["id"]] = {
                **row,
                "from": begun,
                "until": _time(row["until"]),
                "state": "active",
                "mode": row.get("mode", "server"),
                "comments": row.get("comments", "occasional"),
                "intervals": [[begun, None]],
                "report": None,
            }
            continue
        session = found.get(row.get("session_id") or row.get("id"))
        when = _time(row.get("at"))
        if not session or not when or (at and when > at):
            continue
        kind = row.get("kind")
        if kind in ("together_pause", "together_end"):
            if session["intervals"][-1][1] is None:
                session["intervals"][-1][1] = when
            session["state"] = "paused" if kind == "together_pause" else "ended"
            if kind == "together_end":
                session["ended_at"] = when
                session["until"] = min(session["until"], when)
        elif kind == "together_resume" and session["state"] == "paused":
            session["state"] = "active"
            session["intervals"].append([when, None])
        elif kind == "together_report":
            session["report"] = row
    return sorted(found.values(), key=lambda a: a["from"])


def active(c, now=None):
    """Live sessions, including paused sessions that can still be resumed."""
    now = now or dt.datetime.now(_tz(c))
    return [
        a
        for a in agreements(c, now)
        if a["from"] <= now < a["until"] and a["state"] != "ended"
    ]


def _covered(item, at, agreed):
    for agreement in agreed:
        if agreement.get("mode") == "manual" or not matches(agreement["title"], item):
            continue
        for begun, ended in agreement.get("intervals", [[agreement["from"], None]]):
            # Only natural expiry has a grace period. Explicit pauses/ends are
            # boundaries, even when the media server reports a finish later.
            end = min(ended, agreement["until"]) if ended else agreement["until"]
            if ended is None and not agreement.get("ended_at"):
                end += TOGETHER_GRACE
            if begun <= at < end:
                return True
    return False


def sync(c, now=None):
    """Keep what the server reports as finished since the last read. Returns the new rows."""
    now = now or dt.datetime.now(_tz(c))
    path = path_for(c)
    kept = seen(c)
    since = now - dt.timedelta(days=HISTORY_DAYS)
    if kept:
        since = max(since, _time(kept[-1]["at"]) - dt.timedelta(days=1))
    reported = sorted(history(c, since), key=lambda i: i["at"])
    agreed = agreements(c)
    added = []
    with file_lock(path.parent / ("." + path.name + ".lock")):
        known = {r.get("id") for r in slf._read(path)}
        for item in reported:
            at = item["at"].astimezone(_tz(c))
            ident = slf._mkid(
                "seen", c.media_kind, item["key"], str(int(at.timestamp()))
            )
            if ident in known:
                continue
            row = {
                "id": ident,
                "kind": "seen",
                "at": at.isoformat(),
                **{
                    k: item[k]
                    for k in (
                        "what",
                        "show",
                        "season",
                        "episode",
                        "title",
                        "year",
                        "key",
                    )
                },
                "together": _covered(item, at, agreed),
                "source": c.media_kind,
                "recorded_at": now.isoformat(),
            }
            known.add(ident)
            added.append(row)
        if added:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                for row in added:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return added


def together(
    c, title, hours=3, now=None, *, mode="auto", comments="occasional", evidence=""
):
    """Start an agreed session; manual sessions need no media server or model call."""
    now = slf._now(_tz(c), now)
    for name, value in (
        ("title", title),
        ("mode", mode),
        ("comments", comments),
        ("evidence", evidence),
    ):
        if not isinstance(value, str):
            raise ValueError(f"{name} must be text")
    title = slf._text(title, 120, "title")
    if not _norm(title):
        raise ValueError("title must contain letters or numbers")
    if mode not in ("auto", "manual", "server"):
        raise ValueError("mode must be auto, manual or server")
    if comments not in ("quiet", "occasional"):
        raise ValueError("comments must be quiet or occasional")
    if mode == "auto":
        mode = "server" if configured(c) else "manual"
    if mode == "server" and not configured(c):
        raise ValueError("no media server is set up; use a manual session")
    evidence = slf._text(evidence, 600, "evidence") if evidence else ""
    if type(hours) is not int or not TOGETHER_HOURS[0] <= hours <= TOGETHER_HOURS[1]:
        raise ValueError(
            f"hours must be a whole number from {TOGETHER_HOURS[0]} to {TOGETHER_HOURS[1]}"
        )
    row = {
        "id": slf._mkid("together", title.casefold(), now.isoformat()),
        "kind": "together",
        "title": title,
        "mode": mode,
        "comments": comments,
        "evidence": evidence,
        "from": now.isoformat(),
        "until": (now + dt.timedelta(hours=hours)).isoformat(),
        "recorded_at": now.isoformat(),
    }

    def guard():
        live = active(c, now)
        if live:
            agreement = live[-1]
            return {
                "written": False,
                "session_id": agreement["id"],
                "reason": f"already watching {agreement['title']} together until "
                f"{agreement['until'].astimezone(_tz(c)):%H:%M}; end that session first",
            }
        return None

    return _invalidate_context(
        c,
        {
            "session_id": row["id"],
            **slf._append(path_for(c), row, dedupe_id=False, guard=guard),
        },
    )


def _session(c, session_id, now, live=True):
    rows = active(c, now) if live else agreements(c, now)
    rows = [s for s in rows if not session_id or s["id"] == session_id]
    if not rows:
        raise ValueError(
            "no live shared session" if live else "shared session not found"
        )
    if len(rows) > 1 and not session_id:
        raise ValueError("choose a session_id")
    return rows[-1]


def _transition(c, action, now=None, session_id=None):
    now = slf._now(_tz(c), now)
    session = _session(c, session_id, now)
    target = "paused" if action == "pause" else "active"

    def guard():
        current = _session(c, session["id"], now)
        if current["state"] == target:
            return {"written": False, "session_id": session["id"], "state": target}
        return None

    row = {
        "id": slf._mkid("viewing-" + action, session["id"], now.isoformat()),
        "session_id": session["id"],
        "kind": "together_" + action,
        "at": now.isoformat(),
    }
    return _invalidate_context(
        c,
        {
            "session_id": session["id"],
            "state": target,
            **slf._append(path_for(c), row, guard=guard),
        },
    )


def pause(c, now=None, session_id=None):
    """Pause shared participation, not playback on the human's device."""
    return _transition(c, "pause", now, session_id)


def resume(c, now=None, session_id=None):
    """Resume participation inside the original expiry window."""
    return _transition(c, "resume", now, session_id)


def stop(c, now=None, session_id=None):
    """End every agreement that is still running."""
    now = slf._now(_tz(c), now)
    ended = []
    for agreement in active(c, now):
        if session_id and agreement["id"] != session_id:
            continue
        result = slf._append(
            path_for(c),
            {
                "id": slf._mkid("viewing-end", agreement["id"]),
                "session_id": agreement["id"],
                "kind": "together_end",
                "at": now.isoformat(),
            },
            dedupe_id=False,
            guard=lambda: (
                None
                if any(s["id"] == agreement["id"] for s in active(c, now))
                else {"written": False}
            ),
        )
        _invalidate_context(c, result)
        ended.append(agreement["title"])
    return {"stopped": ended}


def report(c, text, evidence, now=None, session_id=None, position_min=None):
    """Keep a human-reported checkpoint without turning it into media-server evidence."""
    now = slf._now(_tz(c), now)
    session = _session(c, session_id, now)
    text = slf._text(text, 400, "text")
    evidence = slf._text(evidence, 600, "evidence")
    if position_min is not None and (
        type(position_min) is not int or not 0 <= position_min <= 1440
    ):
        raise ValueError("position_min must be a whole number from 0 to 1440")
    row = {
        "id": slf._mkid(
            "viewing-report", session["id"], text, evidence, now.isoformat()
        ),
        "session_id": session["id"],
        "kind": "together_report",
        "at": now.isoformat(),
        "text": text,
        "evidence": evidence,
        "position_min": position_min,
        "source": "user_report",
    }

    def guard():
        _session(c, session["id"], now)

    return _invalidate_context(c, slf._append(path_for(c), row, guard=guard))


def moments(c, session_id=None):
    """Personal moments with their conversation evidence and session identity."""
    return [
        row
        for row in slf._read(path_for(c))
        if row.get("kind") == "together_moment"
        and (not session_id or row.get("session_id") == session_id)
    ]


def moment(c, text, evidence, now=None, session_id=None, kind="note"):
    """Record a particular shared memory in both the session and relationship ledgers.

    Evidence is supplied from the conversation, never inferred from a synopsis.
    Stable IDs let a retry repair either ledger without creating another memory.
    """
    import companion_notes as notes

    now = slf._now(_tz(c), now)
    session = _session(c, session_id, now, live=not bool(session_id))
    if kind not in notes.MOMENT_KINDS:
        raise ValueError(f"kind must be one of {notes.MOMENT_KINDS}")
    text = slf._text(text, 350, "text")
    evidence = slf._text(evidence, 600, "evidence")
    ident = slf._mkid("viewing-moment", session["id"], kind, text, evidence)
    row = {
        "id": ident,
        "kind": "together_moment",
        "session_id": session["id"],
        "title": session["title"],
        "moment": kind,
        "text": text,
        "evidence": evidence,
        "source": "conversation",
        "happened_on": session["from"].astimezone(_tz(c)).date().isoformat(),
        "recorded_at": now.isoformat(),
        "relationship_id": ident,
    }
    result = slf._append(path_for(c), row)
    kept = result["entry"]
    memory = notes.add_moment(
        c,
        {
            "id": ident,
            "moment": kind,
            "text": f"Watching {session['title']}: {text}",
            "evidence": f"Shared session {session['id']}: {evidence}"[:300],
            "happened_on": kept["happened_on"],
        },
        _time(kept["recorded_at"]),
    )
    return {**result, "relationship": memory}


def _json_session(session, now):
    return {
        key: value.isoformat() if isinstance(value, dt.datetime) else value
        for key, value in {
            **{k: v for k, v in session.items() if k != "intervals"},
            "state": (
                "expired"
                if session["until"] <= now and session["state"] != "ended"
                else session["state"]
            ),
        }.items()
    }


def snapshot(c, now=None):
    """JSON-safe local session state; this function never contacts a media server."""
    now = now or dt.datetime.now(_tz(c))
    return {
        "sessions": [_json_session(s, now) for s in active(c, now)],
        "recent_sessions": [_json_session(s, now) for s in agreements(c, now)[-10:]],
        "moments": moments(c)[-10:],
    }


def fingerprint(c, now=None):
    """Wake on session changes or expiry, never on the passage of each minute."""
    return slf._mkid(
        "viewing", json.dumps(snapshot(c, now), sort_keys=True, ensure_ascii=False)
    )


def session_context(c, now=None, limit=1000):
    """Local shared-session context, also usable when viewing sensing is disabled."""
    now = now or dt.datetime.now(_tz(c))
    running = active(c, now)
    session = running[-1] if running else None
    if not session:
        recent = [
            s
            for s in agreements(c, now)
            if dt.timedelta(0) <= now - s["until"] <= dt.timedelta(hours=24)
        ]
        if not recent:
            return ""
        session = dict(max(recent, key=lambda s: s["until"]))
        if session["state"] != "ended":
            session["state"] = "expired"
    lines = [
        f"Shared session: {session['title']} ({session['state']}; {session['mode']}; id {session['id']}).",
        "Evidence boundary: no live audio/video or scene perception. Do not invent reactions or reveal events beyond what the human reported or the observed playhead.",
        (
            "Quiet company: no unsolicited commentary; reply when addressed."
            if session["comments"] == "quiet"
            else "Occasional comments are welcome when relevant; silence is fine. This preference does not authorize delivery or bypass outreach/quiet hours."
        ),
    ]
    if not running:
        lines.append(
            f"Session {session['state']} at {session['until'].isoformat()}; this does not mean the film finished. "
            "A natural follow-up about the shared experience may fit; it is optional, never a required message."
        )
    if session["state"] == "paused":
        lines.append(
            "Shared participation is paused; do not narrate continuing to watch."
        )
    if session["mode"] == "manual":
        lines.append(
            "Manual agreement, not observed playback. Only the human can report progress; do not advance the playhead by elapsed time."
        )
    if report := session.get("report"):
        position = (
            f" ({report['position_min']} minutes)"
            if report.get("position_min") is not None
            else ""
        )
        lines.append(
            f"Last human-reported checkpoint at {report['at']}{position} (not live observation): {report['text']}"
        )
        lines.append(f"Conversation evidence: {report['evidence']}")
    import companion_notes as notes

    retired = {row["id"] for row in notes.moments(c, "retired")}
    kept_moments = [
        row
        for row in moments(c, session["id"])
        if row["relationship_id"] not in retired
    ]
    for row in kept_moments[-2:]:
        lines.append(
            f"Remembered from this session: {row['text']} (evidence: {row['evidence']})"
        )
    text = "\n".join(lines)
    return text if len(text) <= limit else text[:limit].rsplit("\n", 1)[0]


def _when(at, now):
    """A viewing day runs to 4 am, so a film finished at 1 am belongs to the night before."""
    at = at.astimezone(now.tzinfo)
    day = (at - dt.timedelta(hours=4)).date()
    days = ((now - dt.timedelta(hours=4)).date() - day).days
    evening = at.hour >= 18 or at.hour < 4
    if days <= 0:
        return "tonight" if evening else "today"
    if days == 1:
        return "last night" if evening else "yesterday"
    if days < 7:
        return f"on {day:%A}"
    return f"on {day.day} {day:%b}"


def lately(c, now, rows=None):
    """The latest of each series or film finished lately, newest first."""
    rows = seen(c) if rows is None else rows
    cutoff = now - dt.timedelta(days=LATELY_DAYS)
    groups = {}
    for row in rows:
        at = _time(row["at"])
        if at < cutoff:
            continue
        name = _norm(row.get("show") or row.get("title"))
        group = groups.setdefault(name, {"rows": []})
        group["rows"].append(row)
    found = []
    for group in groups.values():
        last = max(group["rows"], key=lambda r: _time(r["at"]))
        together_count = sum(1 for r in group["rows"] if r.get("together"))
        found.append((_time(last["at"]), last, together_count, len(group["rows"])))
    found.sort(key=lambda f: f[0], reverse=True)
    phrases = []
    for at, last, together_count, count in found[:LATELY_SHOWN]:
        if last.get("what") == "episode" and last.get("season") is not None:
            text = f"{last.get('show') or last.get('title')} up to S{last['season']}E{last['episode']}"
        else:
            text = label(last)
        text += f", {_when(at, now)}"
        if together_count:
            text += (
                " (watched together)"
                if together_count == count == 1
                else f" ({together_count} of them together)"
            )
        phrases.append(text)
    return phrases


def render(c, now, playing=(), limit=800):
    now = now.astimezone(_tz(c))
    running = active(c, now)
    lines = []
    shared = None
    for item in list(playing)[:1]:
        length = f" of {item['length_min']}" if item.get("length_min") else ""
        paused = ", paused" if item.get("paused") else ""
        lines.append(
            f"- At {now:%H:%M} {c.human} was watching {label(item)} on {source_name(c)}, "
            f"{item.get('position_min', 0)}{length} minutes in{paused}."
        )
        shared = next(
            (a for a in running if a["mode"] == "server" and matches(a["title"], item)),
            None,
        )
        if shared:
            if shared["state"] == "paused":
                lines.append(
                    "- Shared participation is paused; playback is not evidence that you resumed together."
                )
                continue
            about = _summary(c, item)
            lines.append(
                f"- You are watching this together (agreed at "
                f"{shared['from'].astimezone(now.tzinfo):%H:%M})."
            )
            lines.append(
                "Synopsis only, not scene perception. Avoid spoilers beyond the observed playhead or human reports; never invent scene-specific reactions."
            )
            if shared["comments"] == "quiet":
                lines.append(
                    "Quiet company: no unsolicited commentary; reply when addressed."
                )
            if about:
                lines.append(
                    f"Whole-episode synopsis (may include later events): {about}"
                )
    if running and not shared:
        agreement = running[-1]
        if agreement["mode"] == "manual":
            lines.append(
                f"- Manual shared session: {agreement['title']}; playback and progress depend on human reports."
            )
        elif agreement["state"] == "paused":
            lines.append(f"- Your shared session of {agreement['title']} is paused.")
        else:
            lines.append(
                f"- You agreed at {agreement['from'].astimezone(now.tzinfo):%H:%M} to watch "
                f"{agreement['title']} together; it is not on yet."
            )
    phrases = lately(c, now)
    if phrases:
        lines.append("- Lately: " + "; ".join(phrases) + ".")
    if not lines:
        return ""
    lines.append(
        "From their own media server: something to share or ask about when it fits, never a list to recite."
    )
    text = "\n".join(lines)
    return text if len(text) <= limit else text[:limit].rsplit("\n", 1)[0]


def sense(c, now=None):
    """(text, facts) for the viewing sensor, or (None, why) when there is nothing true to say."""
    now = now or dt.datetime.now(_tz(c))
    running = active(c, now)
    if running and all(s["mode"] == "manual" for s in running):
        return session_context(c, now), {
            "source": "manual",
            "playing": [],
            "together": [s["title"] for s in running],
            "lately": 0,
        }
    if not c.media_server:
        return None, "no media server is set"
    if not _token(c):
        return None, "the media server token is missing or unreadable"
    try:
        sync(c, now)
        playing = now_playing(c)
    except ValueError as exc:
        # Unreadable is not "nothing on": say nothing rather than a half-true picture.
        return None, str(exc)
    text = render(c, now, playing)
    if not text:
        return None, f"nothing watched on {source_name(c)} lately"
    return text, {
        "source": c.media_kind,
        "playing": [label(i) for i in playing],
        "together": [a["title"] for a in active(c, now)],
        "lately": len(lately(c, now)),
    }


def check(c, now=None):
    """What Settings shows after saving: whether the server answers and whose viewing it reads."""
    now = now or dt.datetime.now(_tz(c))
    if not c.media_server:
        raise ValueError("set the server address first")
    if not _token(c):
        raise ValueError("add the server's token")
    if c.media_kind == "plex":
        account = c.media_user or "the server's owner"
        _plex_account(c)
    else:
        account = _jellyfin_user(c)[1]
    recent = history(c, now - dt.timedelta(days=HISTORY_DAYS))
    playing = now_playing(c)
    latest = max(recent, key=lambda i: i["at"]) if recent else None
    return {
        "ok": True,
        "server": source_name(c),
        "account": account,
        "playing": label(playing[0]) if playing else None,
        "latest": label(latest) if latest else None,
        "latest_when": _when(latest["at"], now.astimezone(_tz(c))) if latest else None,
    }


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser(
        "together",
        aliases=["start"],
        help="start an agreed shared session (manual without a server)",
    )
    t.add_argument("--title", required=True, help="the series or film")
    t.add_argument("--hours", type=int, default=3)
    t.add_argument("--mode", choices=("auto", "manual", "server"), default="auto")
    t.add_argument("--comments", choices=("quiet", "occasional"), default="occasional")
    t.add_argument("--evidence", default="", help="the words agreeing to the session")
    for command in ("pause", "resume", "stop"):
        parser = sub.add_parser(command, aliases=["end"] if command == "stop" else [])
        parser.add_argument("--session-id")
    r = sub.add_parser("report", help="keep a human-reported progress checkpoint")
    r.add_argument("--session-id")
    r.add_argument("--text", required=True)
    r.add_argument("--evidence", required=True)
    r.add_argument("--position-min", type=int)
    m = sub.add_parser(
        "moment", help="remember a particular shared moment with conversation evidence"
    )
    m.add_argument("--session-id")
    m.add_argument("--text", required=True)
    m.add_argument("--evidence", required=True)
    m.add_argument(
        "--kind",
        choices=("note", "joke", "nickname", "ritual", "first", "milestone"),
        default="note",
    )
    sub.add_parser(
        "show", help="what is on, what was finished lately, what you watch together"
    )
    sub.add_parser("check", help="whether the server answers")
    args = p.parse_args()
    c = cc.load(args.home)
    if args.cmd in ("together", "start"):
        out = together(
            c,
            args.title,
            args.hours,
            mode=args.mode,
            comments=args.comments,
            evidence=args.evidence,
        )
    elif args.cmd in ("stop", "end", "pause", "resume"):
        action = {"stop": stop, "end": stop, "pause": pause, "resume": resume}[args.cmd]
        out = action(c, session_id=args.session_id)
    elif args.cmd == "report":
        out = report(
            c,
            args.text,
            args.evidence,
            session_id=args.session_id,
            position_min=args.position_min,
        )
    elif args.cmd == "moment":
        out = moment(
            c, args.text, args.evidence, session_id=args.session_id, kind=args.kind
        )
    elif args.cmd == "check":
        out = check(c)
    else:
        now = dt.datetime.now(_tz(c))
        state = snapshot(c, now)
        out = {
            **state,
            "together": state["sessions"],
            "lately": lately(c, now),
            "kept": len(seen(c)),
        }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
