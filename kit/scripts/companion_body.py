#!/usr/bin/env python3
"""Their sleep, from a watch or another wearable that knows (the "sleep" sense).

Any client may write `<soul>/ambient/body.json`: states and times, nothing medical, nothing more.

    {"checked_at": "2026-11-27T07:30:00-05:00",  # when the device last confirmed (fresh for 30 minutes)
     "asleep": false,                            # true while they sleep
     "since": "2026-11-27T07:12:00-05:00",       # when that state began: fell asleep at, or woke at
     "slept_minutes": 400,                       # optional: last night's sleep, all told
     "source": "watch"}                          # optional, a short word

With the sense on and the file fresh, three things follow (no model call is ever made here):

- Her messages wait while they sleep. Outside quiet hours too (a lie-in, a nap), the dispatcher holds anything
  that is not high priority, and the message's own expiry still decides whether it is worth sending later.
- Her good morning can go when they are really up. Inside quiet hours, being awake for ten minutes in the last
  three hours of the night lifts the window, as writing to her already does; a two o'clock wake never does.
- She knows, in her context: asleep (since when), or awake since a time this morning and how long they slept.

Stale or missing (a flat watch, a dropped connection), nothing changes: quiet hours stand as they always did.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

FRESH = dt.timedelta(minutes=30)
UP_FOR = dt.timedelta(minutes=10)
MORNING_LEAD = dt.timedelta(hours=3)
SAY_WOKE_FOR = dt.timedelta(hours=4)
SENSE = "sleep"


def path(c) -> Path:
    return c.soul_dir / "ambient" / "body.json"


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:  # noqa: BLE001 -- an unknown zone reads as UTC, as elsewhere
        return ZoneInfo("UTC")


def _when(c, value):
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return dt.datetime.fromtimestamp(float(value), _tz(c))
        when = dt.datetime.fromisoformat(str(value))
    except (ValueError, OverflowError, OSError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=_tz(c))


def read(c, now) -> dict:
    """What the wearable says, or {} when the sense is off, the file is missing, malformed or stale."""
    if SENSE not in (c.sensors or []):
        return {}
    try:
        data = json.loads(path(c).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or not isinstance(data.get("asleep"), bool):
        return {}
    checked = _when(c, data.get("checked_at"))
    if (
        checked is None
        or now - checked > FRESH
        or checked - now > dt.timedelta(minutes=5)
    ):
        return {}
    since = _when(c, data.get("since"))
    if since is not None and since > now + dt.timedelta(minutes=5):
        since = None
    slept = data.get("slept_minutes")
    slept = (
        int(slept) if isinstance(slept, (int, float)) and 0 < slept <= 24 * 60 else None
    )
    return {"asleep": data["asleep"], "since": since, "slept_minutes": slept,
            "source": str(data.get("source") or "")[:20]}  # fmt: skip


def asleep(c, now):
    """True or False when a fresh wearable says, None when nothing does."""
    body = read(c, now)
    return body["asleep"] if body else None


def _to_quiet_end(c, now):
    import companion_outreach as outreach

    if not outreach.in_quiet_hours(c, now):
        return dt.timedelta(0)
    hours, minutes = (int(x) for x in str(c.quiet_end or "08:00").split(":")[:2])
    end = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    if end <= now:
        end += dt.timedelta(days=1)
    return end - now


def up_for_the_day(c, now) -> bool:
    """Awake for ten minutes, and either past quiet hours or in their last three hours (a morning, not a 2 am wake)."""
    body = read(c, now)
    if (
        not body
        or body["asleep"]
        or body["since"] is None
        or now - body["since"] < UP_FOR
    ):
        return False
    try:
        return _to_quiet_end(c, now) <= MORNING_LEAD
    except (ValueError, TypeError):
        return False


def _clock(c, when):
    return when.astimezone(_tz(c)).strftime("%H:%M")


def _span(minutes):
    hours, rest = divmod(int(minutes), 60)
    if not hours:
        return f"{rest} minutes"
    return f"{hours} h {rest:02d} m" if rest else f"{hours} hours"


def render(c, now):
    """(line, data) for her context: asleep since when, or up since this morning after how long."""
    body = read(c, now)
    if not body:
        return "", {}
    who, by = c.human, (
        f"by {c.h_poss()} {body['source']}" if body["source"] else "by a wearable"
    )
    since = body["since"]
    if body["asleep"]:
        line = (
            f"{who} is asleep ({by}"
            + (f", since {_clock(c, since)}" if since else "")
            + "). "
        )
        line += f"Nothing needs to reach {c.h_obj()} now; it can wait until {c.h_subj()} wakes."
        return line, {"asleep": True, "since": since.isoformat() if since else None}
    if since and now - since <= SAY_WOKE_FOR:
        line = f"{who} is up, awake since {_clock(c, since)}"
        if body["slept_minutes"]:
            line += f" after {_span(body['slept_minutes'])} of sleep"
        return line + f" ({by}).", {
            "asleep": False,
            "woke": since.isoformat(),
            "slept": body["slept_minutes"],
        }
    return "", {"asleep": False}


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
        print("the sleep sense is off")
    elif not read(c, now):
        print("no fresh word from a wearable (nothing in the last half hour)")
    else:
        print(
            f"{c.human} is awake, by the wearable (since when is not known, or too long ago to mention)"
        )


if __name__ == "__main__":
    main()
