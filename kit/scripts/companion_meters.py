#!/usr/bin/env python3
"""The meters' own daily record, and how far each may move in a day.

The owner's rules (2026-10-10):

- Each meter moves at most a set amount a day: closeness 6 points (gains scaled
  by the pace chosen at setup), warmth 0.20, trust 0.10, hurt and irritation
  0.30. The rest of a change is not lost; it arrives over the following days. So
  a fight still lands in full, over two to four days, and making up can stop it
  partway, while fishing for sweet moments cannot jump a meter ahead.
- Missing you is a live gauge of time apart and is not capped: it resets the
  moment you are back.
- There is no floor. Closeness can fall all the way.

The record also keeps each day's contact as it is first seen. Closeness and the
slow drift of warmth and trust are built from every day the two of you talked,
and Hermes deletes old conversations; a deleted chat must never lower a meter.
Rules that change how a past day counts apply from RULES_FROM, so a relationship
already under way does not jump when they arrive.

Reading is always read-only, so building her context writes nothing. The record
is kept by one writer, the no-model `meters` job every 15 minutes (`tick`).
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import pathlib
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from companion_platform import atomic_write, file_lock

RECORD = "meters.json"
VERSION = 1
DAILY_CAP = {
    "closeness": 6.0,
    "warmth": 0.20,
    "trust": 0.10,
    "hurt": 0.30,
    "irritation": 0.30,
}
# Closeness's gains scale with pace; its losses do not.
PACED = ("closeness",)
# Sweet moments are the companion's own notes, so on their own they add little
# trust a day: trust is what time and kept promises build.
MOMENT_TRUST_PER_DAY = 0.02
# The day these rules began. Moments before it keep what they already gave.
RULES_FROM = dt.date(2026, 10, 11)
RANGE = {"closeness": (0.0, 120.0)}
# Kept to a tenth of a percent (a hundredth of a point), so a meter drifting by
# the minute does not rewrite the record on every read.
PRECISION = {"closeness": 2}
# A clock this far past the real one is a what-if, not a day to record.
AHEAD = dt.timedelta(hours=1)


def _tz(c):
    try:
        return ZoneInfo(getattr(c, "timezone", "") or "UTC")
    except Exception:
        return dt.timezone.utc


def day_of(c, when):
    """The human's local date for a moment, which is what "a day" means here."""
    if isinstance(when, str):
        when = dt.datetime.fromisoformat(when)
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when.astimezone(_tz(c)).date()


def path(c):
    return c.life / RECORD


def _blank():
    return {"version": VERSION, "days": {}, "contact": {}}


def _load(c):
    """The record, or a blank one. Never writes."""
    try:
        data = json.loads(path(c).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _blank(), False
    except (OSError, ValueError):
        return _blank(), True
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return _blank(), True
    for key in ("days", "contact"):
        if not isinstance(data.get(key), dict):
            data[key] = {}
    return data, False


def _save(c, data, damaged):
    """Write the record. A failed write is not fatal: the values computed now are
    still right, and the next tick tries again."""
    target = path(c)
    try:
        if damaged and target.exists():
            # An unreadable record is set aside, never silently overwritten.
            target.replace(target.with_name(target.name + ".damaged"))
        atomic_write(target, json.dumps(data, indent=1, sort_keys=True) + "\n")
    except OSError:
        pass


@contextlib.contextmanager
def _locked(c, write):
    """Hold the record's lock for a write, or carry on read-only: reading takes no
    lock, and a busy or unwritable record never takes the feelings down."""
    stack = contextlib.ExitStack()
    locked = False
    if write:
        try:
            stack.enter_context(file_lock(c.life / ".meters.lock", timeout=5))
            locked = True
        except (TimeoutError, OSError):
            pass
    with stack:
        yield locked


def settle(c, now, raw, seed=None, pace=1.0, write=False):
    """Each meter's value now: its target, held within the daily cap of where it
    ended the last recorded day.

    `raw` maps a meter to what the history says it should read. `seed` is used
    instead when there is no earlier day to measure from, which is only ever the
    record's first day. Returns, per meter, the value, the target, whether the cap
    is holding it back today, and the value it is measured from.
    """
    today = day_of(c, now)
    key = today.isoformat()
    seed = seed or {}
    out = {}
    with _locked(c, write) as locked:
        data, damaged = _load(c)
        earlier = sorted((d for d in data["days"] if d < key), reverse=True)
        for name, target in raw.items():
            low, high = RANGE.get(name, (0.0, 1.0))
            target = min(max(float(target), low), high)
            start = None
            for day in earlier:
                value = data["days"][day].get(name)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    start = (dt.date.fromisoformat(day), float(value))
                    break
            digits = PRECISION.get(name, 3)
            if start is None:
                value = min(max(float(seed.get(name, target)), low), high)
                out[name] = {
                    "value": round(value, digits),
                    "target": round(target, digits),
                    "held": False,
                    "start": None,
                }
                continue
            elapsed = max(1, (today - start[0]).days)
            down = DAILY_CAP[name] * elapsed
            up = down * (pace if name in PACED else 1.0)
            value = min(max(target, start[1] - down), start[1] + up)
            value = round(min(max(value, low), high), digits)
            out[name] = {
                "value": value,
                "target": round(target, digits),
                "held": abs(value - round(target, digits)) >= 10**-digits,
                "start": round(start[1], digits),
                "room": {"up": round(up, digits), "down": round(down, digits)},
            }
        latest = max(data["days"], default="")
        if locked and key >= latest and now <= dt.datetime.now(dt.timezone.utc) + AHEAD:
            row = data["days"].setdefault(key, {})
            changed = damaged
            for name, info in out.items():
                if row.get(name) != info["value"]:
                    row[name] = info["value"]
                    changed = True
            if changed:
                _save(c, data, damaged)
    return out


def _kept(c, seen, merge, field, write):
    with _locked(c, write) as locked:
        data, damaged = _load(c)
        kept = data["contact"]
        changed = damaged
        merged = {}
        for day in set(seen) | {dt.date.fromisoformat(d) for d in kept}:
            row = kept.setdefault(day.isoformat(), {})
            value = merge(row.get(field), seen.get(day))
            if value != row.get(field):
                row[field] = value
                changed = True
            merged[day] = value
        if changed and locked:
            _save(c, data, damaged)
    return merged


def _bigger(recorded, seen):
    numbers = [
        v
        for v in (recorded, seen)
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    return round(max(numbers), 4) if numbers else 0.0


def _bigger_pair(recorded, seen):
    pairs = [
        tuple(int(x) for x in v)
        for v in (recorded, seen)
        if isinstance(v, (list, tuple)) and len(v) == 2
    ]
    if not pairs:
        return [0, 0]
    return [max(p[0] for p in pairs), max(p[1] for p in pairs)]


def kept_credits(c, credits, write=False):
    """Each day's closeness credit, the larger of what was recorded and what the
    conversation store shows now: a later message raises a day, a deleted chat
    never lowers one."""
    return _kept(c, credits, _bigger, "credit", write)


def kept_counts(c, counts, write=False):
    """Each day's (messages from the human, messages from her), kept the same way."""
    merged = _kept(
        c, {d: list(v) for d, v in counts.items()}, _bigger_pair, "counts", write
    )
    return {day: tuple(pair) for day, pair in merged.items() if any(pair)}


def history(c, now, days=14):
    """The recorded end-of-day values for the last `days` days, oldest first."""
    today = day_of(c, now)
    data, _ = _load(c)
    first = (today - dt.timedelta(days=days - 1)).isoformat()
    return [
        {"day": day, **values}
        for day, values in sorted(data["days"].items())
        if first <= day <= today.isoformat()
    ]


def tick(c, now=None):
    """Keep the record: work the meters out now and write today's values and
    every day's contact. The `meters` job runs this every 15 minutes."""
    import companion_intimacy

    return companion_intimacy.compute(c, now, record=True)


def main():
    import argparse

    import companion_config as cc

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=pathlib.Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("tick", help="keep the record (silent)")
    sub.add_parser("show", help="print the last two weeks of the record")
    args = parser.parse_args()
    c = cc.load(args.home)
    now = dt.datetime.now(dt.timezone.utc)
    if args.command == "tick":
        tick(c, now)
    else:
        print(json.dumps(history(c, now), indent=2))


if __name__ == "__main__":
    main()
