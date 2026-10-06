#!/usr/bin/env python3
"""When the human is usually quiet, learned from when they actually write.

A night's sleep must not read as distance, and nobody should have to type in a
sleep schedule for that to be true. This looks at the hours of the day at which
messages have really arrived, finds the longest stretch that is almost always
silent, and offers it to `companion_feelings` as an expected absence.

It is evidence, not a guess about what the human is doing. It uses timestamps
only, calls no model, says nothing until there is enough history to mean
something, and never claims the human is asleep: the window is "usually quiet".
Windows the human entered themselves are kept alongside it, and the whole thing
switches off with the `learn_rhythm` feelings setting.
"""

from __future__ import annotations
import datetime as dt
import sys
import pathlib
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

HISTORY_DAYS = 28
# Below these there is no pattern to find, only a few evenings.
MIN_ACTIVE_DAYS = 10
MIN_MESSAGES = 40
# An hour counts as quiet if messages land in it on no more than this share of the
# days the human wrote at all, so one 2 a.m. message does not erase a night.
QUIET_SHARE = 0.1
MIN_QUIET_HOURS = 5
MAX_QUIET_HOURS = 12
LABEL = "Usually quiet (learned from your messages)"


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def quiet_window(stamps, tz):
    """(start_hour, end_hour, active_days, messages) for the longest quiet stretch, or None."""
    local = [s.astimezone(tz) for s in stamps]
    days = {s.date() for s in local}
    if len(days) < MIN_ACTIVE_DAYS or len(local) < MIN_MESSAGES:
        return None
    busy_days = [set() for _ in range(24)]
    for stamp in local:
        busy_days[stamp.hour].add(stamp.date())
    quiet = [len(busy_days[h]) <= QUIET_SHARE * len(days) for h in range(24)]
    best_len, best_start = 0, None
    for start in range(24):
        # Only measure a run from its first hour, so a stretch is counted once.
        if not quiet[start] or quiet[(start - 1) % 24]:
            continue
        length = 0
        while length < 24 and quiet[(start + length) % 24]:
            length += 1
        if length > best_len:
            best_len, best_start = length, start
    if best_start is None or best_len >= 24 or best_len < MIN_QUIET_HOURS:
        return None
    length = min(best_len, MAX_QUIET_HOURS)
    return best_start, (best_start + length) % 24, len(days), len(local)


def learned(c, now=None):
    """The learned window as feelings settings would write it, plus its evidence.

    `{"windows": [...], "evidence": {...} | None}`; `windows` is empty when there is
    nothing to say.
    """
    import companion_thread

    now = now or dt.datetime.now(_tz(c))
    found = quiet_window(
        companion_thread.human_times(c, now, HISTORY_DAYS),
        _tz(c),
    )
    if not found:
        return {"windows": [], "evidence": None}
    start, end, days, messages = found
    return {
        "windows": [
            {
                "label": LABEL,
                "days": [0, 1, 2, 3, 4, 5, 6],
                "start": f"{start:02d}:00",
                "end": f"{end:02d}:00",
                "learned": True,
            }
        ],
        "evidence": {
            "start": f"{start:02d}:00",
            "end": f"{end:02d}:00",
            "active_days": days,
            "messages": messages,
            "window_days": HISTORY_DAYS,
        },
    }
