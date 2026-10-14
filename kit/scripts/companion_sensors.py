#!/usr/bin/env python3
"""Real-world texture, gathered by scripts, written into `ambient/`.

A companion with no senses has to invent weather, invent the season, and invent
what kind of day it is — and inventing those is how a companion starts being
wrong about the world in ways nobody can correct. These are cheap, they call no
model, and each one is optional.

One rule governs all of them, and it is the reason this file is careful: **an
absent sensor produces no file, and an absent file must never become a claim.**
Not knowing the weather is fine. Saying it is raining because a fetch failed is
not. Every sensor here either writes something true or writes nothing.

Sensors are chosen at setup and in the app. Adding one means adding a function
and a row in REGISTRY; nothing else in the kit needs to know it exists.
"""

from __future__ import annotations
import argparse
import datetime as dt
import functools
import json
import math
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zoneinfo
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write

TIMEOUT = 8
USER_AGENT = "tamanitomo"


class Broken(str):
    """A reason for silence that is a failure, not an empty moment.

    Every sense says nothing when it has nothing true to say, and that silence
    is right. But "Spotify signed out" and "nothing played lately" looked the
    same from outside, so a sense could be broken for days with nobody told. A
    sense returns its reason as Broken when the thing it reads has stopped
    working; `run_one` keeps the time it started, and the health watch reports
    one that stays broken (companion_watch.check_senses).
    """


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def _get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(200_000).decode("utf-8", errors="replace")


# ---- weather -------------------------------------------------------------
def weather(c, now):
    """wttr.in, which needs no key and understands a plain place name."""
    if not c.location:
        return None, "no location is set for this companion"
    url = "https://wttr.in/" + urllib.parse.quote(c.location) + "?format=j1"
    try:
        data = json.loads(_get(url))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        return None, Broken(f"the weather service is unreachable: {exc}")
    try:
        current = data["current_condition"][0]
        today = data["weather"][0]
        desc = current["weatherDesc"][0]["value"]
        text = (
            f"{c.location}: {desc.lower()}, {current['temp_C']}°C "
            f"(feels like {current['FeelsLikeC']}°C), humidity {current['humidity']}%.\n"
            f"Today {today['mintempC']}–{today['maxtempC']}°C. "
            f"Sunrise {today['astronomy'][0]['sunrise']}, sunset {today['astronomy'][0]['sunset']}."
        )
        # Tomorrow, for the plan she makes at wind-down: a rainy Tuesday is an indoor
        # swim, not the park. Absent when the service does not send a second day.
        try:
            nxt = data["weather"][1]
            hours = nxt.get("hourly") or []
            rain = max((int(h.get("chanceofrain", 0)) for h in hours), default=0)
            midday = (
                hours[4]["weatherDesc"][0]["value"].lower() if len(hours) > 4 else ""
            )
            text += (
                f"\nTomorrow {nxt['mintempC']}–{nxt['maxtempC']}°C"
                + (f", {midday}" if midday else "")
                + f", chance of rain up to {rain}%."
            )
        except (KeyError, IndexError, TypeError, ValueError):
            pass
        try:
            latitude = float(data["nearest_area"][0]["latitude"])
        except (KeyError, IndexError, TypeError, ValueError):
            latitude = None
        extra = {
            "latitude": latitude,
            "sunrise": today["astronomy"][0]["sunrise"],
            "sunset": today["astronomy"][0]["sunset"],
            "temp_c": current["temp_C"],
            "description": desc,
        }
        return text, extra
    except (KeyError, IndexError, TypeError) as exc:
        return None, Broken(
            f"the weather service returned a shape we do not understand: {exc}"
        )


# ---- daylight, season, moon ---------------------------------------------
SEASONS_NORTH = (
    "winter",
    "winter",
    "spring",
    "spring",
    "spring",
    "summer",
    "summer",
    "summer",
    "autumn",
    "autumn",
    "autumn",
    "winter",
)
SEASONS_SOUTH = SEASONS_NORTH[6:] + SEASONS_NORTH[:6]
# Close enough to the equator that "winter" and "summer" are not the honest words.
TROPICS = 15.0
_ZONE_ROW = re.compile(r"([+-])(\d{2})(\d{2})(\d{2})?[+-]\d")


@functools.lru_cache(maxsize=64)
def zone_row(zone):
    """(ISO country code, latitude) of an IANA zone's reference city, from zone.tab.

    (None, None) when it cannot say. Every zone carries its coordinates, so nothing
    here is a hand-kept list of which countries are in the south.
    """
    tables = []
    try:
        import importlib.resources as resources

        tables.append(
            (resources.files("tzdata.zoneinfo") / "zone.tab").read_text("utf-8")
        )
    except (ImportError, OSError, ModuleNotFoundError):
        pass
    for root in zoneinfo.TZPATH:
        try:
            tables.append((pathlib.Path(root) / "zone.tab").read_text("utf-8"))
        except OSError:
            pass
    for text in tables:
        for line in text.splitlines():
            columns = line.split("\t")
            if line.startswith("#") or len(columns) < 3 or columns[2] != zone:
                continue
            found = _ZONE_ROW.match(columns[1])
            if found:
                sign, deg, minutes, seconds = found.groups()
                value = int(deg) + int(minutes) / 60 + int(seconds or 0) / 3600
                return columns[0], (-value if sign == "-" else value)
    return None, None


def zone_latitude(zone):
    return zone_row(zone)[1]


def hemisphere(c):
    """ "north", "south", or None when we cannot say. Weather's latitude first, her zone second."""
    lat = None
    try:
        data = json.loads((c.soul_dir / "ambient/weather.json").read_text("utf-8"))
        lat = float(data["latitude"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if lat is None:
        lat = zone_latitude(getattr(c, "timezone", "") or "")
    if lat is None or abs(lat) < TROPICS:
        return None
    return "south" if lat < 0 else "north"


def season_for(c, when):
    """The season where she lives, or None. An unknown hemisphere is not a claim."""
    side = hemisphere(c)
    if side is None:
        return None
    return (SEASONS_SOUTH if side == "south" else SEASONS_NORTH)[when.month - 1]


def moon_phase(when):
    """Rough phase from a known new moon. Good enough to look out of a window."""
    known = dt.datetime(2000, 1, 6, 18, 14, tzinfo=dt.timezone.utc)
    days = (when.astimezone(dt.timezone.utc) - known).total_seconds() / 86400
    fraction = (days % 29.530588853) / 29.530588853
    names = [
        "new",
        "waxing crescent",
        "first quarter",
        "waxing gibbous",
        "full",
        "waning gibbous",
        "last quarter",
        "waning crescent",
    ]
    return names[int(fraction * 8 + 0.5) % 8]


def daylight(c, now):
    """No network at all: the season, the moon, and how long the day is."""
    season = season_for(c, now)
    lines = [
        f"It is {now.strftime('%A')} {now.day} {now.strftime('%B')}"
        + (f", in {season}." if season else "."),
        f"The moon is {moon_phase(now)}.",
    ]
    sun = c.soul_dir / "ambient/weather.json"
    try:
        data = json.loads(sun.read_text(encoding="utf-8"))
        if data.get("sunrise") and data.get("sunset"):
            lines.append(
                f"Sunrise was {data['sunrise'].lower()}, sunset is {data['sunset'].lower()}."
            )
    except (OSError, ValueError, KeyError):
        pass
    return "\n".join(lines), {"season": season, "moon": moon_phase(now)}


# ---- dates the human cares about ----------------------------------------
def dates(c, now):
    """A file the human writes: `MM-DD | what it is`. Seven days of lookahead."""
    path = c.data / "dates.md"
    if not path.exists():
        return None, (
            f'no dates file yet — write one at {path}, one per line as "MM-DD | what it is"'
        )
    upcoming = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|", 1)]
        if len(parts) != 2:
            continue
        try:
            month, day = (int(x) for x in parts[0].split("-")[-2:])
        except ValueError:
            continue
        for year in (now.year, now.year + 1):
            try:
                when = dt.date(year, month, day)
            except ValueError:
                break
            delta = (when - now.date()).days
            if 0 <= delta <= 7:
                when_text = (
                    "today"
                    if not delta
                    else "tomorrow" if delta == 1 else f"in {delta} days"
                )
                upcoming.append(
                    (delta, f"{parts[1]} — {when_text} ({when.isoformat()})")
                )
                break
    if not upcoming:
        return None, "nothing in the next seven days"
    upcoming.sort()
    return "Coming up:\n" + "\n".join(f"- {text}" for _, text in upcoming), {
        "count": len(upcoming)
    }


# ---- things to circle back on -------------------------------------------
def care(c, now):
    """What is due to be circled back on.

    This used to read one hand-written file and nothing else, so it was switched
    on, wired up and completely inert for anyone who had never been told to
    create it -- which is everyone. Circling back on the thing you said you would
    check on is not an optional extra, so it now reads the store the companion
    already writes to by herself: an open loop with a `follow_up_at` that has
    arrived is exactly this, and she records those without being asked.

    `care.md` stays as an optional place for a person to add their own, in
    `YYYY-MM-DD | topic | what to do about it` lines.
    """
    due = []
    try:
        import companion_loops

        for row in companion_loops.loops(c):
            if row.get("status") == "closed":
                continue
            # Stored resolved, as an ISO timestamp; the parser above is for the
            # loose forms ("+2d", "this_evening") accepted when one is recorded.
            raw = str(row.get("follow_up_at") or "").strip()
            if not raw:
                continue
            try:
                when = dt.datetime.fromisoformat(raw)
            except ValueError:
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=now.tzinfo)
            if when > now:
                continue
            title = (row.get("title") or "").strip()
            if not title:
                continue
            gentle = (row.get("gentle_use") or "").strip()
            due.append(
                f'{title}{" — "+gentle if gentle else ""} (since {when.date().isoformat()})'
            )
    except Exception:
        pass  # A loop store that will not read is not a reason to lose care.md.
    path = c.data / "care.md"
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            try:
                when = dt.date.fromisoformat(parts[0])
            except ValueError:
                continue
            if when <= now.date():
                due.append(f"{parts[1]} — {parts[2]} (due {parts[0]})")
    if not due:
        return None, "nothing due"
    return (
        "Worth circling back to. These are yours to raise naturally, when it fits, "
        "not a list to read out:\n" + "\n".join(f"- {item}" for item in due),
        {"count": len(due)},
    )


# ---- the conversation itself --------------------------------------------
def thread(c, now):
    import companion_thread

    data = companion_thread.read(c, now)
    if not data.get("available"):
        reason = data.get("reason", "no conversation history yet")
        return None, (Broken(reason) if "unreadable" in reason else reason)
    return companion_thread.render(c, data), data


# The registry is data: a name, what it needs, and what it is for. The function
# is looked up by name at run time rather than captured here, so the app can read
# this table without importing the sensors and a test can stand one in.
# ---- durations, counted rather than remembered ---------------------------
def durations(c, now):
    """ "Married 13 years" — computed from the date, never stored as a number.

    A number written down once is a number that is quietly wrong a year later,
    and being wrong about how long someone has been married is a particular kind
    of wrong. The same `dates.md` the lookahead reads can carry full dates; any
    line with a year gets counted here.
    """
    path = c.data / "dates.md"
    if not path.exists():
        return None, "no dates file"
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|", 1)]
        if len(parts) != 2:
            continue
        try:
            when = dt.date.fromisoformat(parts[0])
        except ValueError:
            continue  # MM-DD lines belong to the lookahead only
        years = now.year - when.year - ((now.month, now.day) < (when.month, when.day))
        if years < 1:
            continue
        out.append(
            f'{parts[1]}: {years} year{"s" if years!=1 else ""} as of today ({parts[0]})'
        )
    if not out:
        return None, "no dated anniversaries to count"
    return (
        "Counted from the dates themselves, so these are right today and will be right next "
        "year:\n" + "\n".join(f"- {line}" for line in out),
        {"count": len(out)},
    )


# ---- ambient music & listening awareness --------------------------------
def _spotify_state(c):
    for candidate in (getattr(c, "hermes_root", None), getattr(c, "home", None)):
        if not candidate:
            continue
        auth_file = candidate / "auth.json"
        if auth_file.is_file():
            try:
                data = json.loads(auth_file.read_text(encoding="utf-8"))
                st = data.get("providers", {}).get("spotify")
                if st:
                    return st
            except Exception:
                pass
    return None


def _spotify_token(c, st: dict) -> str | None:
    import time

    cache_path = c.home / "state" / "spotify-music-cache.json"
    cache = {}
    if cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if cache.get("access_token") and cache.get("expires_at", 0) - 60 > time.time():
        return cache["access_token"]
    client_id = st.get("client_id")
    refresh_token = cache.get("refresh_token") or st.get("refresh_token")
    accounts = st.get("accounts_base_url", "https://accounts.spotify.com").rstrip("/")
    if not (client_id and refresh_token):
        return None
    data = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }
    ).encode()
    try:
        req = urllib.request.Request(
            f"{accounts}/api/token",
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            tok = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    at = tok.get("access_token")
    if not at:
        return None
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "access_token": at,
                    "expires_at": time.time() + int(tok.get("expires_in", 3600)),
                    "refresh_token": tok.get("refresh_token", refresh_token),
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
    return at


def _spotify_get(url: str, token: str):
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            if resp.status == 204:
                return None
            body = resp.read(200_000).decode("utf-8", errors="replace")
            return json.loads(body) if body else None
    except Exception:
        return None


def music(c, now):
    """What the human is listening to on Spotify. Nothing, if Spotify cannot say."""
    st = _spotify_state(c)
    if st:
        token = _spotify_token(c, st)
        if not token:
            # Connected, but the sign-in no longer works: not the same as quiet.
            (c.soul_dir / "context-music.md").unlink(missing_ok=True)
            return None, Broken(
                "Spotify is connected but its sign-in has stopped working; sign in again"
            )
        if token:
            api = st.get("api_base_url", "https://api.spotify.com/v1").rstrip("/")
            try:
                cur = _spotify_get(f"{api}/me/player/currently-playing", token)
                if cur and cur.get("item"):
                    it = cur["item"]
                    artists = ", ".join(a["name"] for a in it.get("artists", []))
                    playing = cur.get("is_playing")
                    verb = "is playing" if playing else "has paused"
                    text = f'- {c.human} {verb} “{it.get("name")}” by {artists} on Spotify right now.'
                    try:
                        legacy = c.soul_dir / "context-music.md"
                        atomic_write(legacy, text + "\n")
                    except OSError:
                        pass
                    return text, {
                        "source": "spotify",
                        "state": "playing" if playing else "paused",
                        "track": it.get("name"),
                        "artists": artists,
                    }
                rec = _spotify_get(f"{api}/me/player/recently-played?limit=1", token)
                items = (rec or {}).get("items", [])
                if items:
                    it = items[0].get("track", {})
                    artists = ", ".join(a["name"] for a in it.get("artists", []))
                    text = f'- {c.human} was recently listening to “{it.get("name")}” by {artists} on Spotify.'
                    try:
                        legacy = c.soul_dir / "context-music.md"
                        atomic_write(legacy, text + "\n")
                    except OSError:
                        pass
                    return text, {
                        "source": "spotify",
                        "state": "recent",
                        "track": it.get("name"),
                        "artists": artists,
                    }
            except Exception:
                pass
    # Not connected, signed out, or nothing played: say nothing, and take back the
    # legacy copy so a stale "is playing" line cannot outlive the connection.
    (c.soul_dir / "context-music.md").unlink(missing_ok=True)
    return None, "Spotify is not connected, or has nothing to report"


# ---- what the human watches ------------------------------------------------
def viewing(c, now):
    """What the human watches on their own Plex or Jellyfin server. Nothing, if it cannot say."""
    import companion_viewing

    return companion_viewing.sense(c, now)


# ---- the dates two people keep -------------------------------------------
def together(c, now):
    """First conversation, anniversaries, day counts, birthday, traditions: all counted."""
    import companion_together

    text, facts = companion_together.render(c, now)
    if not text:
        return None, facts
    return text, facts


# ---- public holidays -----------------------------------------------------
HOLIDAY_API = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"
HOLIDAY_LOOKAHEAD_DAYS = 7


def _holidays_for(c, country, year):
    """A year of a country's public holidays, kept on disk so one fetch lasts the year."""
    cache = c.home / "state" / f"holidays-{country}-{year}.json"
    try:
        return json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        rows = json.loads(_get(HOLIDAY_API.format(year=year, country=country)))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    kept = [
        {"date": r["date"], "name": r.get("localName") or r.get("name")}
        for r in rows
        if isinstance(r, dict) and r.get("global", True) and r.get("date")
    ]
    if not kept:
        return None
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(cache, json.dumps(kept, ensure_ascii=False))
    except OSError:
        pass
    return kept


def holidays(c, now):
    """Public holidays in the next week where she lives. Only the country and year leave."""
    country, _lat = zone_row(getattr(c, "timezone", "") or "")
    if not country:
        return None, "her timezone does not say which country she is in"
    today = now.date()
    end = today + dt.timedelta(days=HOLIDAY_LOOKAHEAD_DAYS)
    rows = []
    for year in sorted({today.year, end.year}):
        found = _holidays_for(c, country, year)
        if found is None:
            return (
                None,
                f"no holiday list for {country} {year} (offline, or not published)",
            )
        rows += found
    coming = []
    for row in rows:
        try:
            when = dt.date.fromisoformat(row["date"])
        except (ValueError, KeyError):
            continue
        if today <= when <= end:
            delta = (when - today).days
            word = (
                "today"
                if not delta
                else "tomorrow" if delta == 1 else f"in {delta} days"
            )
            coming.append((when, f"- {row['name']} — {word} ({when.isoformat()})"))
    if not coming:
        return None, "no public holiday in the next seven days"
    coming.sort()
    return "Public holidays:\n" + "\n".join(t for _, t in coming), {
        "country": country,
        "count": len(coming),
    }


REGISTRY = {
    "weather": {
        "fn": "weather",
        "needs": "a location",
        "blurb": "Temperature and conditions where you live, hourly. "
        'No account needed. Grounds "it is grim out" in something true.',
    },
    "daylight": {
        "fn": "daylight",
        "needs": None,
        "blurb": "The season where she lives, the moon, and the length of the day. "
        "Computed, no network. Says nothing about the season near the equator or when "
        "it cannot tell which hemisphere she is in.",
    },
    "dates": {
        "fn": "dates",
        "needs": "a dates.md file",
        "blurb": "Birthdays and anniversaries you write down, "
        "surfaced a week ahead so they can be remembered rather than announced.",
    },
    "care": {
        "fn": "care",
        "needs": "a care.md file",
        "blurb": "Things worth asking about again — an interview, "
        "a hospital appointment, a hard week. This is how a companion circles back.",
    },
    "durations": {
        "fn": "durations",
        "needs": "dated lines in dates.md",
        "blurb": 'How long things have been true — "married 13 years" — counted from the date rather than '
        "remembered as a number that goes quietly wrong.",
    },
    "together": {
        "fn": "together",
        "needs": None,
        "blurb": "How long you have known each other, counted from the first conversation: "
        "monthly anniversaries, 100 days, a year, your birthday once you have told her, and "
        "traditions as they come round. Computed; nothing to write down.",
    },
    "holidays": {
        "fn": "holidays",
        "needs": "a country (from your timezone)",
        "blurb": "Public holidays where she lives, a week ahead. Looks up the country and "
        "year only, once, and keeps the answer.",
    },
    "thread": {
        "fn": "thread",
        "needs": None,
        "blurb": "How long since either of you wrote, and what that stretch "
        "of quiet tends to mean. The most useful thing on this list.",
    },
    "music": {
        "fn": "music",
        "needs": "Spotify auth",
        "blurb": "What the human is playing on Spotify, and their artists and albums when she "
        "picks one for them. Off, Spotify is never read. Silent when Spotify is not connected.",
    },
    "viewing": {
        "fn": "viewing",
        "needs": "a Plex or Jellyfin server",
        "blurb": "What you watch on your own Plex or Jellyfin server: what is on, what you "
        "finished lately and where each series is up to, and what the two of you watch "
        "together. Only your server is contacted; the titles reach her model provider "
        "like the rest of her context.",
    },
}


def run_one(c, name, now):
    spec = REGISTRY.get(name)
    if not spec:
        raise ValueError(f"unknown sensor {name!r}; known: {sorted(REGISTRY)}")
    folder = c.soul_dir / "ambient"
    folder.mkdir(parents=True, exist_ok=True)
    md = folder / f"{name}.md"
    data_path = folder / f"{name}.json"
    try:
        text, extra = globals()[spec["fn"]](c, now)
    except Exception as exc:
        text, extra = None, Broken(f"it crashed: {exc}")
    _note_health(
        c, name, extra if isinstance(extra, Broken) and not text else None, now
    )
    if not text:
        # Absent means silent. Removing the stale file is the point: yesterday's
        # weather presented as today's is worse than no weather at all.
        for path in (md, data_path):
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
        return {
            "sensor": name,
            "wrote": False,
            "reason": extra if isinstance(extra, str) else "nothing to report",
        }
    atomic_write(md, text.rstrip("\n") + "\n")
    if isinstance(extra, dict):
        atomic_write(
            data_path,
            json.dumps(
                {**extra, "checked_at": now.isoformat()}, ensure_ascii=False, indent=2
            ),
        )
    return {"sensor": name, "wrote": True, "chars": len(text)}


def health_path(c):
    return c.home / "state" / "sensor-health.json"


def _note_health(c, name, broken, now):
    """Keep when each sense started failing; a sense that works again is forgotten."""
    path = health_path(c)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    if broken is None:
        if name not in data:
            return
        data.pop(name)
    else:
        since = (data.get(name) or {}).get("since") or now.isoformat()
        data[name] = {"since": since, "at": now.isoformat(), "reason": str(broken)}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))
    except OSError:
        pass


def broken_senses(c):
    """{name: {"since", "at", "reason"}} for the senses failing right now."""
    try:
        data = json.loads(health_path(c).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def run(c, now=None, names=None):
    now = now or dt.datetime.now(_tz(c))
    # The bars ride along with the senses: same schedule, same "absent means no
    # claim" rule, and they need the thread the thread sensor just refreshed.
    try:
        import companion_bars

        companion_bars.write(c, now)
    except (OSError, ValueError, ImportError):
        pass
    chosen = names if names is not None else (c.sensors or [])
    # weather before daylight: daylight reads the sunrise weather just wrote.
    order = [n for n in REGISTRY if n in chosen]
    return [run_one(c, name, now) for name in order]


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    p.add_argument("--only", action="append", help="run just this sensor, repeatable")
    p.add_argument(
        "--list", action="store_true", help="what is available and what each needs"
    )
    a = p.parse_args()
    if a.list:
        print(
            json.dumps(
                {
                    k: {"needs": v["needs"], "blurb": v["blurb"]}
                    for k, v in REGISTRY.items()
                },
                indent=2,
            )
        )
        return 0
    c = cc.load(a.home)
    results = run(c, names=a.only)
    # As a no-agent job: silent unless a sensor that was switched on could not
    # report. Sensors going quiet is normal; nobody needs a heartbeat.
    problems = [r for r in results if not r["wrote"]]
    if problems and a.only:
        print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except (ValueError, OSError) as e:
        print(f"{e}", file=sys.stderr)
        sys.exit(1)
