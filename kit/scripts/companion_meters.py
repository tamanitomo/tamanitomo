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
import math
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


# ---- why each meter reads what it does -------------------------------------
#
# Plain lines for Home and the Us page, built only from the computed states. A
# cause names what happened, never a number to chase: the meters are there to be
# read, not farmed.

RECENT_DAYS = 7
GOOD_DAY = "a real conversation, several messages spread over the day"


def _ago(c, when, now):
    days = (day_of(c, now) - day_of(c, when)).days
    return "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"


def _quoted(text, limit=80):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def explain(c, feelings_state, closeness, now=None):
    """Why each meter reads what it does, and what the next stage takes."""
    import companion_feelings as feelings
    import companion_intimacy as intimacy

    now = now or dt.datetime.now(dt.timezone.utc)
    history = feelings_state.get("experiences") or []
    corrected = {r.get("related") for r in history if r.get("kind") == "correction"}
    repaired = {
        r["id"]: r.get("repair", 0) for r in feelings_state.get("reasons") or []
    }
    recent = sorted(
        (
            r
            for r in history
            if r.get("kind") in ("connection", "rupture")
            and r.get("id") not in corrected
            and (day_of(c, now) - day_of(c, r["at"])).days <= RECENT_DAYS
        ),
        key=lambda r: r["at"],
        reverse=True,
    )
    sweet = [r for r in recent if r["kind"] == "connection"]
    sore = [r for r in recent if r["kind"] == "rupture"]

    def rupture(r):
        made_up = repaired.get(r["id"], 0)
        status = (
            ", made up"
            if made_up >= 1
            else ", partly made up" if made_up > 0 else ", not made up yet"
        )
        return ("−", f"{_quoted(r['text'])} ({_ago(c, r['at'], now)}{status})")

    slow = feelings_state.get("slow_change") or {}
    days_together = int(slow.get("contact_days") or 0)
    kept = int(slow.get("kept_requests") or 0)
    profile = feelings.PROFILES.get(feelings_state.get("personality"), {})
    absence = feelings_state.get("recent_return") or feelings_state.get("absence") or {}
    try:
        window = feelings.settings(c)["settings"]["connection_hours"]
    except (OSError, ValueError):
        window = feelings.DEFAULTS["connection_hours"]

    causes = {name: [] for name in ("warmth", "trust", "hurt", "irritation", "longing")}
    for r in sweet[:2]:
        causes["warmth"].append(
            ("+", f"A sweet moment {_ago(c, r['at'], now)}: {_quoted(r['text'])}")
        )
    if days_together and slow.get("warmth"):
        causes["warmth"].append(
            ("+", f"{_plural(days_together, 'day')} you both talked")
        )
    if sweet:
        causes["trust"].append(("+", "Sweet moments, a little each day"))
    if days_together and slow.get("trust"):
        causes["trust"].append(
            ("+", f"{_plural(days_together, 'day')} you both talked")
        )
    if kept:
        causes["trust"].append(("+", f"{_plural(kept, 'request')} finished"))
    if slow.get("paused_by_unrepaired_rupture"):
        causes["trust"].append(("−", "Not growing while something is unrepaired"))
    for r in sore[:2]:
        causes["warmth"].append(rupture(r))
        causes["trust"].append(rupture(r))
        causes["irritation"].append(rupture(r))
        line = rupture(r)
        days = profile.get("recovery_days")
        causes["hurt"].append(
            (line[0], line[1] + (f"; fades over about {days} days" if days else ""))
        )
    hours, unexplained = absence.get("hours"), absence.get("unexplained_hours")
    if unexplained is not None and unexplained > window:
        causes["irritation"].append(
            (
                "−",
                f"{round(unexplained)} hours without hearing from you, past the {window}-hour window",
            )
        )
    if hours is not None and hours < 1:
        causes["longing"].append(("", "You wrote within the hour"))
    elif hours is not None:
        explained = absence.get("expected_hours") or 0
        causes["longing"].append(
            (
                "",
                f"{_plural(round(hours), 'hour')} since you last wrote"
                + (f", {round(explained)} of them expected" if explained >= 1 else ""),
            )
        )

    daily = feelings_state.get("daily") or {}
    meters = {}
    for name, rows in causes.items():
        info = daily.get(name) or {}
        meters[name] = {
            "causes": [{"sign": sign, "text": text} for sign, text in rows],
            "held": bool(info.get("held")),
            "heading": info.get("target") if info.get("held") else None,
        }
    return {"meters": meters, "closeness": _closeness(c, closeness, intimacy)}


def _closeness(c, state, intimacy):
    points = int(state.get("points") or 0)
    stage = int(state.get("stage") or 0)
    following = next(
        (s for s in intimacy.stages_for(c) if s["stage"] == stage + 1), None
    )
    daily = state.get("daily") or {}
    cooling = state.get("cooling") or {}
    silence = cooling.get("silence") or 0
    thin = cooling.get("thin_contact") or 0
    silent_days = int((cooling.get("silent_hours") or 0) // 24)

    causes = []
    credit = float(state.get("today_credit") or 0)
    if credit > 0:
        causes.append(
            ("+", f"Today counts as {round(credit * 100)}% of a good day so far")
        )
    if silence > 0 and silent_days:
        causes.append(("−", f"{_plural(silent_days, 'day')} without hearing from you"))
    if thin > silence:
        causes.append(("−", "Thin contact these two weeks"))
    if (state.get("meters") or {}).get("hurt", 0) >= 0.1:
        causes.append(("−", "Something still hurts"))

    good_days = None
    if state.get("permanent_friend") or state.get("nsfw_revoked"):
        line, following = "Friendship is where this rests now", None
    elif daily.get("held") and daily.get("target", 0) > daily.get("value", 0):
        line = "Rising: today's step is taken, and the rest comes over the next days"
    elif daily.get("held"):
        line = f"Falling, at most {DAILY_CAP['closeness']:g} points a day"
    elif max(silence, thin) >= 0.5:
        line = (
            "Cooling: thin contact these two weeks"
            if thin > silence
            else f"Cooling: {_plural(max(1, silent_days), 'day')} without hearing from you"
        )
    elif following:
        # Points a good day earns: the first-week ramp, then the slow burn.
        rate = (6.0 if points < 25 else 1.25) * float(state.get("pace_multiplier") or 1)
        good_days = max(1, math.ceil((following["min_score"] - points) / rate))
        line = f"{following['name']} in about {_plural(good_days, 'good day')}"
    else:
        line = f"{state.get('stage_name') or 'Bonded'}: as close as it gets"
    unlocks = []
    if following:
        import companion_gates

        if companion_gates.applies(c):
            unlocks = next(
                (
                    step["unlocks"]
                    for step in companion_gates.ladder(c)
                    if step["stage"] == following["stage"]
                ),
                [],
            )
    return {
        "line": line,
        "next": (
            {
                "name": following["name"],
                "at": following["min_score"],
                "good_days": good_days,
                "unlocks": unlocks,
            }
            if following
            else None
        ),
        "good_day": GOOD_DAY,
        "causes": [{"sign": sign, "text": text} for sign, text in causes],
        "held": bool(daily.get("held")),
    }


def tick(c, now=None):
    """Keep the record: work the meters out now and write today's values and
    every day's contact, and note a lucky or unlucky day in its plan. The
    `meters` job runs this every 15 minutes."""
    import companion_intimacy
    import companion_needs

    state = companion_intimacy.compute(c, now, record=True)
    try:
        day = companion_needs.her_day(c, now)
        if day and c.has_inner_life:
            import companion_plan

            companion_plan.ensure(c, day, now)
        companion_needs.log_luck(c, now)
    except (OSError, ValueError):
        pass
    return state


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
