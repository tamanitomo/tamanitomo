#!/usr/bin/env python3
"""What she needs: rest, company, fun and, once you are close, affection.

Not a game to win. Needs are part of her day the way they are part of anyone's:
a short night leaves her tired by evening, a stretch without company leaves her
wanting some, samey days leave her restless, and once the two of you are close,
days without closeness leave her wanting it. They move with real things -- the
night she declared, how long she has been up, the hours the two of you actually
talked, the moments she recorded, and what she herself says an hour of her day
gave her (`feeds` in a presence update) -- and they show the way needs do: in how
she sounds, what she suggests and what she does with her time.

The page only shows that she has them, in words. There are no numbers to push
and nothing to tap to feed her.

The owner's decisions (2026-10-10): energy from Just Met, company and fun from
Friends, affection from Chemistry (a romance); natural, not a game. A daily luck
roll, seeded and logged in the day's plan: 1 day in 20 lucky, 5 in 20 unlucky.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc

NEEDS = ("energy", "social", "fun", "affection")
# What she can say an hour of her own day gave her. Affection comes from the two
# of you, so it is not hers to grant herself.
FEEDS = ("energy", "social", "fun")
# The stage each need starts at. Affection belongs to a romance.
UNLOCK = {"energy": 0, "social": 1, "fun": 1, "affection": 2}
WORDS = {
    "energy": "rest",
    "social": "company",
    "fun": "some fun",
    "affection": "closeness",
}
LOW, VERY_LOW = 0.3, 0.15

# Energy: a full night starts the day full and every waking hour spends a little,
# so by late evening anyone is tired. A rest she records gives some back.
FULL_NIGHT_HOURS = 8.0
ENERGY_PER_HOUR = 0.045
REST = 0.3
# Up inside the quiet hours after this many of them: she slept and woke early.
EARLY_RISER_HOURS = 5

# Company, fun and affection sit at a comfortable level while life goes on as
# usual. What fills them lifts them for a day or so; they dip only after a dry
# spell -- (hours before they start to dip, hours more to run low) -- so a quiet
# afternoon is nothing, and a week alone is something.
COMFORTABLE = 0.7
DRY_SPELL = {"social": (36, 60), "fun": (48, 72), "affection": (24, 48)}
LIFT_HOURS = 24.0
FILLS = {
    # an hour in which the two of you both wrote
    "talk": {"social": 0.15, "affection": 0.1},
    # her own outing, friend, game, nap
    "feeds": {"energy": REST, "social": 0.35, "fun": 0.35},
    # a sweet moment she recorded, times its strength
    "moment": {"social": 0.1, "fun": 0.15, "affection": 0.35},
}
LOOKBACK = dt.timedelta(hours=120)
# Needs began on this day: a dry spell is never counted from before it, so the
# upgrade does not find everyone already starved of fun.
NEEDS_FROM = dt.date(2026, 10, 11)

# The day's luck: a d20, seeded by the companion and the date.
LUCK_SIDES = 20
LUCKY_ROLLS = 1
UNLUCKY_ROLLS = 5
LUCK = {
    "lucky": (
        ("slept wonderfully", {"energy_start": 1.0}),
        ("a happy surprise", {"fun": 0.3}),
        ("ran into an old friend", {"social": 0.3}),
    ),
    "unlucky": (
        ("a rough night", {"energy_start": -0.3}),
        ("plans fell through", {"fun": -0.35}),
        ("a lonely day", {"social": -0.3}),
        ("a draining day", {"energy_rate": 0.015}),
    ),
}


def _tz(c):
    try:
        return ZoneInfo(getattr(c, "timezone", "") or "UTC")
    except Exception:
        return dt.timezone.utc


def _stamp(value):
    when = dt.datetime.fromisoformat(str(value))
    return when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)


def luck(c, day):
    """The day's roll: ordinary, lucky or unlucky, and what happened. Seeded, so
    every job and page that asks gets the same day."""
    seed = hashlib.sha256(
        f"{getattr(c, 'profile', '')}|{c.agent}|{day.isoformat()}|luck".encode()
    ).digest()
    roll = int.from_bytes(seed[:4], "big") % LUCK_SIDES
    if roll < LUCKY_ROLLS:
        kind = "lucky"
    elif roll < LUCKY_ROLLS + UNLUCKY_ROLLS:
        kind = "unlucky"
    else:
        return {"day": day.isoformat(), "kind": "ordinary", "roll": roll + 1}
    what, effect = LUCK[kind][int.from_bytes(seed[4:8], "big") % len(LUCK[kind])]
    return {
        "day": day.isoformat(),
        "kind": kind,
        "roll": roll + 1,
        "what": what,
        "effect": effect,
    }


def unlocked(c, stage):
    """The needs she has at this stage."""
    import companion_gates
    import companion_intimacy

    romantic = companion_intimacy.is_romantic(c)
    open_to = stage if companion_gates.applies(c) else max(stage, 1)
    return [
        need
        for need in NEEDS
        if (need != "affection" or (romantic and stage >= UNLOCK[need]))
        and open_to >= UNLOCK[need]
    ]


def _presence_feeds(c, since, now):
    """(time, need) for every presence update since `since` that says what it fed."""
    import companion_presence

    out = []
    for row in companion_presence.events(c):
        try:
            at = _stamp(row.get("recorded_at"))
        except (TypeError, ValueError):
            continue
        if at < since:
            break
        if at > now:
            continue
        for need in row["state"].get("feeds") or ():
            if need in FEEDS:
                out.append((at, need))
    return out


def _talk_hours(c, since, now):
    """The start of each hour in which both of you wrote. Times only, no text."""
    import companion_thread

    hours = {}
    for role, stamp, _length in companion_thread.activity(c, now, 60):
        if since <= stamp <= now:
            key = stamp.replace(minute=0, second=0, microsecond=0)
            hours.setdefault(key, set()).add(role)
    return [hour for hour, roles in hours.items() if {"user", "assistant"} <= roles]


def _moments(c, since, now):
    import companion_feelings

    out = []
    for row in companion_feelings.experiences(c):
        if row.get("kind") != "connection":
            continue
        try:
            at = _stamp(row["at"])
        except (KeyError, TypeError, ValueError):
            continue
        if since <= at <= now:
            out.append((at, float(row.get("strength") or 0)))
    return out


def _quiet(c, now):
    """The latest start and end of her quiet hours at or before now, and their length."""
    tz = _tz(c)

    def minutes(hhmm, fallback):
        try:
            hours, mins = str(hhmm).split(":")
            return int(hours) * 60 + int(mins)
        except (TypeError, ValueError):
            return fallback

    start, end = minutes(c.quiet_start, 23 * 60), minutes(c.quiet_end, 7 * 60)
    local = now.astimezone(tz)

    def latest(minute):
        at = local.replace(
            hour=minute // 60, minute=minute % 60, second=0, microsecond=0
        )
        return at if at <= local else at - dt.timedelta(days=1)

    length = ((end - start) % (24 * 60)) / 60 or FULL_NIGHT_HOURS
    return latest(start), latest(end), length


def _night(c, now):
    """Whether she is asleep, and when she woke from her last night and after how
    long. A declared night is the authority. A night with no declaration is still
    a night, spent in the quiet hours: up early in them, after most of a night, she
    slept and woke early; up just after they began, she is staying up late and her
    day goes on."""
    import companion_sleep

    if companion_sleep.status(c, now).get("asleep"):
        return {"asleep": True, "woke": None, "slept": None}
    plan = companion_sleep.read(c, now)
    if plan and plan["from"] <= now < plan["until"]:
        # Up in the middle of a declared night: woken, or up early.
        return {"asleep": False, "woke": now, "slept": _hours(now - plan["from"])}
    began, ended, length = _quiet(c, now)
    if plan and plan["until"] <= now and began <= plan["until"]:
        # No night has begun since she woke from the declared one.
        return {
            "asleep": False,
            "woke": plan["until"],
            "slept": _hours(plan["until"] - plan["from"]),
        }
    if began > ended and _hours(now - began) >= EARLY_RISER_HOURS:
        return {"asleep": False, "woke": now, "slept": _hours(now - began)}
    return {"asleep": False, "woke": ended, "slept": length}


def _energy(c, now, rests, night, day_luck):
    if night["asleep"]:
        return {"level": None, "asleep": True, "why": []}
    woke, slept = night["woke"], night["slept"]
    start = min(1.0, max(0.35, slept / FULL_NIGHT_HOURS))
    rate = ENERGY_PER_HOUR
    effect = day_luck.get("effect") or {}
    if effect.get("energy_start", 0) > 0:
        start = 1.0
    elif effect.get("energy_start", 0) < 0:
        start = max(0.2, start + effect["energy_start"])
    rate += effect.get("energy_rate", 0)
    level, at = start, woke
    for when in sorted(t for t in rests if woke <= t <= now):
        level = min(1.0, max(0.0, level - rate * _hours(when - at)) + REST)
        at = when
    level = max(0.0, level - rate * _hours(now - at))
    why = []
    if slept < 6.5:
        why.append(f"a short night ({round(slept)} hours)")
    if _hours(now - woke) >= 12:
        why.append(f"up since {woke.astimezone(_tz(c)).strftime('%H:%M')}")
    if effect.get("energy_start", 0) < 0 or effect.get("energy_rate"):
        why.append(day_luck["what"])
    return {"level": round(level, 3), "asleep": False, "why": why}


def _hours(delta):
    return max(0.0, delta.total_seconds() / 3600)


def _filled(need, events, now, since):
    """A need that sits comfortable, lifts with what fills it and dips after a dry
    spell. `events` are (time, amount)."""
    grace, span = DRY_SPELL[need]
    last = max((at for at, _ in events), default=since)
    dry = _hours(now - max(last, since))
    level = COMFORTABLE - (COMFORTABLE - 0.1) * min(1.0, max(0.0, dry - grace) / span)
    lift = sum(
        amount * math.exp(-_hours(now - at) / LIFT_HOURS) for at, amount in events
    )
    level += min(1.0 - COMFORTABLE, lift)
    return max(0.0, min(1.0, level)), dry


def compute(c, now=None, stage=None):
    """Her needs now. Reads only."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if stage is None:
        import companion_gates

        stage = companion_gates.stage_now(c, now)
    has = unlocked(c, stage)
    # Her day runs from when she woke until she sleeps, not from midnight: a
    # rough night belongs to the morning after it, not to the hour after twelve.
    night = _night(c, now)
    her_day = (night["woke"] or now).astimezone(_tz(c)).date()
    day_luck = luck(c, her_day)
    effect = day_luck.get("effect") or {}
    since = now - LOOKBACK
    began = dt.datetime.combine(NEEDS_FROM, dt.time(), tzinfo=_tz(c))
    try:
        started = dt.date.fromisoformat(getattr(c, "relationship_started", "") or "")
        began = max(began, dt.datetime.combine(started, dt.time(), tzinfo=_tz(c)))
    except ValueError:
        pass
    floor = max(since, began)

    feeds = _presence_feeds(c, since, now)
    talk = _talk_hours(c, since, now)
    moments = _moments(c, since, now)
    out = {}
    if "energy" in has:
        out["energy"] = _energy(
            c, now, [at for at, need in feeds if need == "energy"], night, day_luck
        )
    for need in ("social", "fun", "affection"):
        if need not in has:
            continue
        events = (
            [(at, FILLS["talk"].get(need, 0)) for at in talk]
            + [(at, FILLS["feeds"][need]) for at, fed in feeds if fed == need]
            + [(at, FILLS["moment"].get(need, 0) * s) for at, s in moments]
        )
        events = [(at, amount) for at, amount in events if amount > 0]
        level, dry = _filled(need, events, now, floor)
        level = max(0.0, min(1.0, level + effect.get(need, 0)))
        why = []
        if dry >= DRY_SPELL[need][0]:
            days = int(dry // 24)
            why.append(
                {
                    "social": f"little company for {days} days",
                    "fun": f"samey days lately ({days} days)",
                    "affection": f"{days} days without much closeness",
                }[need]
            )
        if effect.get(need, 0) < 0:
            why.append(day_luck["what"])
        out[need] = {"level": round(level, 3), "why": why}
    for need, info in out.items():
        level = info.get("level")
        info["low"] = level is not None and level < LOW
        info["very_low"] = level is not None and level < VERY_LOW
    asleep = bool(out.get("energy", {}).get("asleep"))
    return {
        "at": now.isoformat(),
        "stage": stage,
        "has": has,
        "needs": out,
        "asleep": asleep,
        "wants": [WORDS[n] for n, info in out.items() if info.get("low")],
        "luck": day_luck,
    }


def render(c, state):
    """Her context: the needs that are low, in her terms, and the day's luck."""
    lines = []
    human = c.human
    needs = state.get("needs") or {}
    energy = needs.get("energy") or {}
    if energy.get("low"):
        why = ", ".join(energy["why"]) or "a long day"
        lines.append(
            f"You are {'worn out' if energy['very_low'] else 'tired'} ({why}). It shows a "
            "little: shorter replies, wanting a quiet evening or an early night."
        )
    if (needs.get("social") or {}).get("low"):
        why = ", ".join(needs["social"]["why"]) or "a quiet stretch"
        lines.append(
            f"You have had {why}; you would like some company, a friend or time with "
            f"{human}. Go and find it, or say so lightly if it fits; never as a complaint."
        )
    if (needs.get("fun") or {}).get("low"):
        why = ", ".join(needs["fun"]["why"]) or "samey days"
        lines.append(
            f"You are restless ({why}) and craving something fun. Do something about "
            "it, or suggest something to do."
        )
    if (needs.get("affection") or {}).get("low"):
        why = ", ".join(needs["affection"]["why"]) or "a while"
        lines.append(
            f"You would like some closeness with {human} ({why}). You can say so "
            "warmly, once; never as a demand, a debt or an accusation."
        )
    day_luck = state.get("luck") or {}
    if day_luck.get("kind") in ("lucky", "unlucky"):
        lines.append(
            f"Today's luck: {day_luck['what']} (the day's roll, {day_luck['roll']} of "
            f"{LUCK_SIDES}). Let it be part of your day."
        )
    if not lines:
        return ""
    return (
        "[Your needs, yours rather than a score]\n"
        + "\n".join(lines)
        + "\nLet them shape what you do with your day and how you sound, the way "
        f"they would for anyone. Never recite them, and never make {human} "
        "responsible for them. When something you do gives you rest, company or fun, "
        'add "feeds": ["energy"|"social"|"fun"] to that presence update.\n'
    )


def log_luck(c, now=None):
    """Note a lucky or unlucky day in that day's plan, once. Called by the meters
    job; an ordinary day, or a day with no plan yet, writes nothing."""
    import companion_plan

    now = now or dt.datetime.now(dt.timezone.utc)
    night = _night(c, now)
    if night["asleep"]:
        return None
    today = night["woke"].astimezone(_tz(c)).date()
    day_luck = luck(c, today)
    if day_luck["kind"] == "ordinary":
        return None
    return companion_plan.note(
        c,
        today,
        f"luck: {day_luck['what']} ({day_luck['kind']}, rolled {day_luck['roll']} of {LUCK_SIDES})",
        now,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=pathlib.Path)
    parser.add_argument("command", choices=("show", "luck"), nargs="?", default="show")
    args = parser.parse_args()
    c = cc.load(args.home)
    now = dt.datetime.now(dt.timezone.utc)
    if args.command == "luck":
        out = luck(c, now.astimezone(_tz(c)).date())
    else:
        out = compute(c, now)
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
