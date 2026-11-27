#!/usr/bin/env python3
"""Their day in motion, from a watch or another wearable that counts steps (the "activity" sense).

Any client may write `<soul>/ambient/steps.json` (not activity.json: the senses job writes its own
activity.md and activity.json beside it): counts and times, nothing medical, nothing more.

    {"checked_at": "2026-11-27T15:10:00-05:00",  # when the device last counted (fresh for 45 minutes)
     "steps": 9800,                              # steps so far today
     "usual_by_now": 5200,                       # optional: their usual count by this time of day
     "source": "watch"}                          # optional, a short word

With the sense on and a fresh count from today, she knows, in her context, how much they have been on their feet
today and, when the device knows their usual, whether that is a busy day or a quiet one. It is for noticing the way
a partner would ("you've been on your feet all day"), never a goal, a score or a lecture, and never a reason to
message them: it only rides along when she is already talking or writing. No model call is ever made here.

Stale, from another day, malformed or missing (a flat watch, a dropped connection): she knows nothing of it.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

FRESH = dt.timedelta(minutes=45)
SENSE = "activity"
BUSY = 1.5  # this many times their usual by now reads as a busy day on their feet
QUIET = 0.5  # and this little as a quiet one
QUIET_MIN_USUAL = (
    1500  # below this usual count, "quiet" means nothing (an early hour, a slow usual)
)


def path(c) -> Path:
    return c.soul_dir / "ambient" / "steps.json"


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:  # noqa: BLE001 -- an unknown zone reads as UTC, as elsewhere
        return ZoneInfo("UTC")


def _count(value, ceiling=200_000):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if 0 <= value <= ceiling else None


def read(c, now) -> dict:
    """What the device counted, or {} when the sense is off, the file is missing, malformed, stale or from another day."""
    if SENSE not in (c.sensors or []):
        return {}
    try:
        data = json.loads(path(c).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    steps = _count(data.get("steps"))
    try:
        checked = dt.datetime.fromisoformat(str(data.get("checked_at")))
    except ValueError:
        return {}
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=_tz(c))
    if (
        steps is None
        or now - checked > FRESH
        or checked - now > dt.timedelta(minutes=5)
        or checked.astimezone(_tz(c)).date() != now.astimezone(_tz(c)).date()
    ):
        return {}
    return {"steps": steps, "usual": _count(data.get("usual_by_now")) or None, "checked": checked,
            "source": str(data.get("source") or "")[:20]}  # fmt: skip


def _about(n):
    """9,800 for 9,764; 640 for 640: the way a person would say it."""
    return f"{round(n, -2):,}" if n >= 1000 else str(n)


def render(c, now):
    """(line, data) for her context: steps so far today, against their usual by this hour when known."""
    act = read(c, now)
    if not act:
        return "", {}
    who, poss = c.human, c.h_poss()
    by = f"by {poss} {act['source']}" if act["source"] else "by a wearable"
    clock = act["checked"].astimezone(_tz(c)).strftime("%H:%M")
    steps, usual = act["steps"], act["usual"]
    line = f"{who} has walked about {_about(steps)} steps today by {clock} ({by})"
    data = {"steps": steps, "usual_by_now": usual}
    if usual:
        ratio = steps / usual
        if ratio >= BUSY:
            line += f", well over {poss} usual of about {_about(usual)} by this hour: a busy day on {poss} feet"
            data["day"] = "busy"
        elif ratio <= QUIET and usual >= QUIET_MIN_USUAL:
            line += f", well under {poss} usual of about {_about(usual)} by this hour: a quiet day so far"
            data["day"] = "quiet"
        else:
            line += f", about {poss} usual for this time of day"
            data["day"] = "usual"
    line += ". Yours to notice if it fits; never a goal, a score or a lecture."
    return line, data


def main():
    import argparse

    import companion_config as cc

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--home", default=None)
    ap.add_argument("cmd", choices=["status"])
    args = ap.parse_args()
    c = cc.load(Path(args.home).expanduser()) if args.home else cc.load()
    now = dt.datetime.now(_tz(c))
    line, _data = render(c, now)
    if line:
        print(line)
    elif SENSE not in (c.sensors or []):
        print('The "activity" sense is off.')
    else:
        print(f"No fresh count from today in {path(c)}.")


if __name__ == "__main__":
    main()
