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
import json
import math
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write

TIMEOUT = 8
USER_AGENT = "tamanitomo"


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
        return None, f"weather service unreachable: {exc}"
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
        extra = {
            "sunrise": today["astronomy"][0]["sunrise"],
            "sunset": today["astronomy"][0]["sunset"],
            "temp_c": current["temp_C"],
            "description": desc,
        }
        return text, extra
    except (KeyError, IndexError, TypeError) as exc:
        return None, f"weather service returned a shape we do not understand: {exc}"


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
    season = SEASONS_NORTH[now.month - 1]
    lines = [
        f"It is {now.strftime('%A %-d %B')}, in {season}.",
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
        return None, data.get("reason", "no conversation history yet")
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


def _ambient_listening_mood(now):
    hour = now.hour
    if 23 <= hour or hour < 7:
        return "Late night quiet: soft ambient, low-fi drift, deep rest."
    elif 7 <= hour < 12:
        return "Morning air: quiet acoustic, warm instrumental coffee vibes."
    elif 12 <= hour < 17:
        return "Afternoon flow: focused downtempo, atmospheric synth."
    elif 17 <= hour < 21:
        return "Evening unwind: mellow jazz, vinyl warmth, melodic indie."
    else:
        return "Nightfall: contemplative ambient, gentle piano."


def music(c, now):
    """What the human is listening to on Spotify, or shared ambient room music."""
    st = _spotify_state(c)
    if st:
        token = _spotify_token(c, st)
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
    mood = _ambient_listening_mood(now)
    text = f"- Ambient listening vibe: {mood}"
    return text, {"source": "ambient_mood", "mood": mood}


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
        "blurb": "The season, the moon, and the length of the day. "
        "Computed, no network, always available.",
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
    "thread": {
        "fn": "thread",
        "needs": None,
        "blurb": "How long since either of you wrote, and what that stretch "
        "of quiet tends to mean. The most useful thing on this list.",
    },
    "music": {
        "fn": "music",
        "needs": "Spotify auth or ambient mood",
        "blurb": "What the human is playing on Spotify, or the ambient listening mood for the room.",
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
        text, extra = None, f"sensor failed: {exc}"
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
