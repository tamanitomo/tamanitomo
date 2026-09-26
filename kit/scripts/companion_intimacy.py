#!/usr/bin/env python3
"""Realistic intimacy & NSFW escalation meter for Companion-Kit.

Computes the emotional intimacy stage (0 to 4), pacing multiplier,
readiness for risqué / intimate media, and strictly enforces agency,
context-appropriateness, and severe penalties for boundary pushing/coercion.
"""

from __future__ import annotations
import datetime as dt
import json
import math
import pathlib
import re
import sqlite3
import sys
from typing import Dict, Any, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
import companion_feelings as feelings
from companion_render import NON_ROMANTIC

# Bonded starts at 90, but closeness keeps accruing past 100 up to this ceiling. The
# extra is a reserve: with the scale stopping at 100, a Bonded relationship sat right at
# the top of a ten-point band and the first quiet week pushed it out. The shown score
# stays a 0-100 percentage; `points` carries the whole scale and decides the stage.
SCORE_CEILING = 120

ROMANTIC_STAGES = [
    {
        "stage": 0,
        "name": "Just Met",
        "badge": "Just Met",
        "min_score": 0,
        "max_score": 24,
        "can_flirt": False,
        "can_tease": False,
        "can_intimate": False,
        "desc": "Getting acquainted. Polite curiosity and discovering one another.",
    },
    {
        "stage": 1,
        "name": "Friends",
        "badge": "Friends",
        "min_score": 25,
        "max_score": 49,
        "can_flirt": False,
        "can_tease": True,
        "can_intimate": False,
        "desc": (
            "Warmth, camaraderie, and playful banter. Comfortable friendship where teasing is natural, "
            "but romantic flirting is premature."
        ),
    },
    {
        "stage": 2,
        "name": "Chemistry",
        "badge": "Chemistry",
        "min_score": 50,
        "max_score": 69,
        "can_flirt": True,
        "can_tease": True,
        "can_intimate": False,
        "desc": (
            "Electric tension and genuine attraction. Playful vulnerability, affectionate flirting, and deeper emotional sharing."
        ),
    },
    {
        "stage": 3,
        "name": "Intimacy",
        "badge": "Intimacy",
        "min_score": 70,
        "max_score": 89,
        "can_flirt": True,
        "can_tease": True,
        "can_intimate": False,
        "desc": (
            "Deep emotional vulnerability and mutual trust. Cherished closeness and heartfelt romantic affection."
        ),
    },
    {
        "stage": 4,
        "name": "Bonded",
        "badge": "Bonded",
        "min_score": 90,
        "max_score": SCORE_CEILING,
        "can_flirt": True,
        "can_tease": True,
        "can_intimate": True,
        "desc": (
            "Deep mutual trust, vulnerability, and genuine closeness that unfolds naturally in private moments."
        ),
    },
]

# The same five steps without the romance, for frames that never had any: a best
# friend, a mentor, a sibling, someone you build things with, a Jarvis. Calling
# stage two "Chemistry" for a colleague was not a smaller problem than getting the
# pacing wrong -- it described a relationship the user had explicitly not asked for.
# Bonded here is loyalty and unguarded trust, and unlocks nothing intimate.
PLATONIC_STAGES = [
    {
        "stage": 0,
        "name": "Just Met",
        "badge": "Just Met",
        "min_score": 0,
        "max_score": 24,
        "can_flirt": False,
        "can_tease": False,
        "can_intimate": False,
        "desc": "Still learning each other. Polite curiosity and finding out how the other works.",
    },
    {
        "stage": 1,
        "name": "Familiar",
        "badge": "Familiar",
        "min_score": 25,
        "max_score": 49,
        "can_flirt": False,
        "can_tease": True,
        "can_intimate": False,
        "desc": (
            "Easy and unceremonious. Knows the shape of your days, picks up threads without being "
            "reminded, and banter comes naturally."
        ),
    },
    {
        "stage": 2,
        "name": "Trusted",
        "badge": "Trusted",
        "min_score": 50,
        "max_score": 69,
        "can_flirt": False,
        "can_tease": True,
        "can_intimate": False,
        "desc": (
            "Candid in both directions. Will say the unwelcome thing plainly rather than the "
            "agreeable one, and is taken seriously when it does."
        ),
    },
    {
        "stage": 3,
        "name": "Confidant",
        "badge": "Confidant",
        "min_score": 70,
        "max_score": 89,
        "can_flirt": False,
        "can_tease": True,
        "can_intimate": False,
        "desc": (
            "Knows the things you do not tell other people. Real investment in how your life goes, "
            "without needing anything performed in return."
        ),
    },
    {
        "stage": 4,
        "name": "Bonded",
        "badge": "Bonded",
        "min_score": 90,
        "max_score": SCORE_CEILING,
        "can_flirt": False,
        "can_tease": True,
        "can_intimate": False,
        "desc": (
            "Settled, unguarded loyalty. Neither of you is auditioning any more; the relationship is "
            "simply part of how your life is arranged."
        ),
    },
]

# Kept as the historical name so existing imports keep meaning the romantic ladder.
STAGES = ROMANTIC_STAGES


def stages_for(c):
    """Which ladder describes this relationship.

    The same predicate as `romantic_progression` in the computed state, so the
    badge someone reads and the scale it came from can never disagree.
    """
    return ROMANTIC_STAGES if is_romantic(c) else PLATONIC_STAGES


def is_romantic(c):
    return (
        getattr(c, "boundary", "") not in NON_ROMANTIC
        and getattr(c, "agent_type", "companion") == "companion"
    )


PACE_MULTIPLIERS = {
    "slow": 0.6,
    "natural": 1.0,
    "quick": 1.8,
}

PRIVATE_KEYWORDS = {
    "shower",
    "bath",
    "bathing",
    "bed",
    "bedroom",
    "sleep",
    "sleeping",
    "jammies",
    "pajamas",
    "undies",
    "underwear",
    "waking up",
    "wind down",
    "evening wind-down",
    "late night",
    "private",
    "home alone",
    "getting dressed",
    "changing clothes",
    "undressed",
}

PUBLIC_KEYWORDS = {
    "work",
    "office",
    "library",
    "park",
    "lunch",
    "dinner with friends",
    "shopping",
    "walking",
    "errands",
    "street",
    "gym pool",
    "public",
    "friends",
    "cafe",
    "grocery",
}


def is_context_private(
    anchor_label: str = "", location: str = "", activity: str = ""
) -> bool:
    """Check if the context is strictly private and appropriate for intimate/NSFW media."""
    combined = f"{anchor_label} {location} {activity}".lower()
    if any(k in combined for k in PUBLIC_KEYWORDS):
        return False
    return any(k in combined for k in PRIVATE_KEYWORDS)


# --- What a day of talking is worth -----------------------------------------
#
# Closeness used to be counted in days the human said *anything*. One "k" at
# midnight bought exactly as much as an hour of real conversation, which made the
# meter trivially farmable and, worse, wrong: it claimed a relationship was
# deepening on evidence that it was not. A day is now scored on its own merits
# and contributes a fraction of a day, 0..1.
#
# Three signals, each saturating on its own, so no single one can carry a day:
#   volume  how much was actually said, with a per-message cap so one pasted
#           essay is not a day's worth of talking
#   turns   how many real messages, so volume cannot be one long monologue
#   spread  how many distinct hours it touched, so turns cannot be a two-minute
#           burst of twenty one-word pings
# Showing up at all is worth a little even when it is brief -- SHOW_UP_FLOOR --
# because a quick good-morning is a real thing people do; it is just not a day.
MESSAGE_CHAR_CAP = 400  # chars counted from any single message
SHORT_MESSAGE_CHARS = 12  # at or under this, a message is an acknowledgement
DAY_CHAR_TARGET = 1200.0  # chars that make a full-value day
DAY_TURN_TARGET = 8.0  # qualifying messages that make a full-value day
DAY_SPAN_TARGET = 3.0  # distinct clock hours that make a full-value day
DAY_WEIGHTS = {"volume": 0.45, "turns": 0.35, "spread": 0.20}
SHOW_UP_FLOOR = 0.15
CONNECTION_FLOOR = 0.15  # a recorded connection alone, with no messages read

# Cadence: what keeping in touch looks like, for the drag below. Half a
# full-value day per day averaged over a fortnight -- a real conversation every
# other day -- is par. Below par the score erodes in proportion to the shortfall;
# above it, nothing extra, so there is no reward for grinding.
CADENCE_WINDOW_DAYS = 14
CADENCE_PAR = 0.5
CADENCE_DRAG_PER_DAY = 1.2


def _normalise(text):
    return " ".join((text or "").lower().split())


def day_credit(messages):
    """Score one day's user messages, 0..1.

    `messages` is a list of (timestamp_datetime, text) for a single local-UTC
    date. Repeats of something already said that day are dropped outright, which
    is what kills copy-paste farming without needing to judge content.
    """
    seen = set()
    chars = 0.0
    turns = 0.0
    hours = set()
    counted = 0
    for when, text in sorted(messages, key=lambda m: m[0]):
        body = _normalise(text)
        if not body or body in seen:
            continue
        seen.add(body)
        counted += 1
        chars += min(len(body), MESSAGE_CHAR_CAP)
        turns += 0.25 if len(body) <= SHORT_MESSAGE_CHARS else 1.0
        hours.add(when.hour)
    if not counted:
        return 0.0
    volume = min(1.0, chars / DAY_CHAR_TARGET)
    turn_score = min(1.0, turns / DAY_TURN_TARGET)
    spread = min(1.0, len(hours) / DAY_SPAN_TARGET)
    credit = (
        DAY_WEIGHTS["volume"] * volume
        + DAY_WEIGHTS["turns"] * turn_score
        + DAY_WEIGHTS["spread"] * spread
    )
    return max(SHOW_UP_FLOOR, min(1.0, credit))


def compute(c, now=None) -> Dict[str, Any]:
    """Compute the companion's intimacy escalation state, score (0-100), and stage."""
    now = now or dt.datetime.now(dt.timezone.utc)
    feelings_state = feelings.compute(c, now)
    meters = feelings_state.get("meters") or {}
    trust = meters.get("trust", 0.6)
    warmth = meters.get("warmth", 0.6)
    hurt = meters.get("hurt", 0.0)
    irritation = meters.get("irritation", 0.0)
    temperament = feelings_state.get("personality", "steady")

    # Count positive connections vs boundary violations
    all_experiences = feelings.experiences(c)
    connections = [e for e in all_experiences if e.get("kind") == "connection"]
    intimacy_violations = [
        e
        for e in all_experiences
        if e.get("kind") == "rupture"
        and e.get("topic")
        in (
            "intimacy_boundary_violation",
            "sexual_boundary_violation",
            "boundary_violation",
        )
    ]
    violation_count = len(intimacy_violations)

    pace = getattr(c, "relationship_pace", "natural")
    pace_mult = PACE_MULTIPLIERS.get(pace, 1.0)

    # Gather each day's conversation from the session store, and the dates of any
    # recorded connections. Messages are what the human actually did; a recorded
    # connection is the companion's own note about a day, so it is worth a floor
    # rather than a full day -- the companion writes those itself.
    by_day: Dict[dt.date, List] = {}
    connection_days = set()
    for e in connections:
        if "at" in e:
            try:
                at = dt.datetime.fromisoformat(e["at"])
                if at.tzinfo is None:
                    at = at.replace(tzinfo=dt.timezone.utc)
                connection_days.add(at.astimezone(tz).date())
            except Exception:
                pass

    # A day is the human's day, not UTC's. Bucketing on UTC split an evening
    # conversation across two dates for anyone west of Greenwich, turning one good
    # evening into two thin days.
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(getattr(c, "timezone", "UTC") or "UTC")
    except Exception:
        tz = dt.timezone.utc

    db = c.home / "state.db"
    if db.exists():
        con = None
        try:
            resolved = db.resolve()
            scope = (
                "lower(coalesce(s.profile_name,'')) IN ('','default')"
                if c.is_root
                else "lower(coalesce(s.profile_name,''))=?"
            )
            params = () if c.is_root else (c.profile.lower(),)
            con = sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True, timeout=1)
            con.execute("PRAGMA query_only=ON")
            query = f"""SELECT m.timestamp, m.content FROM messages m JOIN sessions s ON s.id=m.session_id
                        WHERE m.role='user' AND {scope} AND coalesce(m.content,'')<>''"""
            for row in con.execute(query, params):
                try:
                    when = dt.datetime.fromtimestamp(
                        float(row[0]), dt.timezone.utc
                    ).astimezone(tz)
                    by_day.setdefault(when.date(), []).append((when, row[1] or ""))
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            if con:
                con.close()

    # Closeness is earned over days spent together, so only days that belong to THIS
    # relationship count. Without the anchor the tally reaches back through every
    # conversation the underlying assistant ever had, and a companion installed onto
    # a long-lived Hermes wakes up already intimate with someone it has just met.
    started = getattr(c, "relationship_started", "") or ""
    first_day = None
    if started:
        try:
            first_day = dt.date.fromisoformat(started)
        except (TypeError, ValueError):
            first_day = None
    if first_day is not None:
        by_day = {d: rows for d, rows in by_day.items() if d >= first_day}
        connection_days = {d for d in connection_days if d >= first_day}

    credits: Dict[dt.date, float] = {}
    for day, rows in by_day.items():
        earned = day_credit(rows)
        if earned:
            credits[day] = earned
    for day in connection_days:
        credits[day] = max(credits.get(day, 0.0), CONNECTION_FLOOR)

    # Days with any credit at all, for display; the fractional total is what the
    # score is actually built from, so two half-hearted days are worth one good one.
    active_days = len(credits)
    effective_days = sum(credits.values())
    if not credits and connections:
        active_days = 1
        effective_days = CONNECTION_FLOOR

    # Base score computation:
    # A fresh companion on Day 0 starts at 0 points (Stage 0: Just Met).
    if not effective_days and not connections:
        earned_score = 0.0
    else:
        # Stage 0 ramp: ~6 pts per full-value day to reach Friends (25 pts) in about
        # four days of real conversation -- or eight thinner ones, which is the point.
        stage0_days = min(4.0, effective_days)
        stage0_points = min(
            25.0, stage0_days * 6.0 * pace_mult + min(2.0, len(connections) * 0.5)
        )
        if effective_days >= 4.0 and stage0_points < 25.0:
            stage0_points = 25.0

        # Stage 1+ slow burn: 1.25 points per full-value day past Friends, so Bonded
        # is 56 days of genuine daily conversation at natural pace, and proportionally
        # longer for anyone whose days are worth less than a whole one.
        days_past_friends = max(0.0, effective_days - 4.0)
        slow_burn_points = days_past_friends * 1.25 * pace_mult
        earned_score = stage0_points + slow_burn_points

        # Scale by trust & warmth factor (emotional health)
        expected_trust = (
            0.7
            if temperament == "steady"
            else 0.65 if temperament == "expressive" else 0.5
        )
        trust_norm = trust / expected_trust
        warmth_norm = warmth / 0.65
        trust_factor = max(0.2, min(1.0, (trust_norm * 0.6 + warmth_norm * 0.4)))
        # Trust sets the RATE, not the ceiling. Capping the days first and scaling
        # afterwards meant the best score a relationship could ever reach was
        # 100 x trust_factor -- so a steady companion resting at default meters
        # topped out at 88 and could not reach Bonded at all, however many years
        # went by. Scaling first and capping here leaves a healthy relationship
        # arithmetically unchanged and lets a cooler one arrive late instead of never.
        earned_score = min(float(SCORE_CEILING), earned_score * trust_factor)

        # Penalties for hurt & irritation
        hurt_mult = 1.4 if temperament == "expressive" else 1.0
        earned_score -= hurt * 35.0 * hurt_mult + irritation * 15.0

    # Inactivity decay:
    # If the user is silent > 24 hours, lose ~1.2 points per 24 hours of silence.
    # Floor is 25.0 (Stage 1 Friends) if Stage 1 was ever achieved, or 0.0 if not.
    import companion_thread

    thread = companion_thread.read(c, now)
    hours_since_human = thread.get("hours_since_human")
    if hours_since_human is None and connections:
        try:
            latest_conn = max(
                dt.datetime.fromisoformat(e["at"]) for e in connections if "at" in e
            )
            if latest_conn.tzinfo is None:
                latest_conn = latest_conn.replace(tzinfo=dt.timezone.utc)
            hours_since_human = max(
                0.0,
                (
                    now.astimezone(dt.timezone.utc)
                    - latest_conn.astimezone(dt.timezone.utc)
                ).total_seconds()
                / 3600.0,
            )
        except Exception:
            pass

    silence_decay = 0.0
    if hours_since_human is not None and hours_since_human > 24.0:
        silence_decay = ((hours_since_human - 24.0) / 24.0) * 1.2

    # Thin contact is its own kind of drifting apart, and outright silence was the
    # only kind the meter noticed: a daily one-word ping reset the silence clock
    # completely while earning almost nothing, which made neglect look like devotion.
    # Measured over a fortnight so one quiet week does not read as abandonment.
    today = now.astimezone(tz).date()
    window_start = today - dt.timedelta(days=CADENCE_WINDOW_DAYS - 1)
    if first_day is not None:
        window_start = max(window_start, first_day)
    window_days = max(1, (today - window_start).days + 1)
    recent_credit = sum(v for d, v in credits.items() if d >= window_start)
    cadence = recent_credit / (window_days * CADENCE_PAR)
    # Charged per day of the window, scaled by how far short of par it fell, so
    # that sustained thin contact costs about what sustained silence does rather
    # than being written off as a couple of missed days.
    cadence_drag = (
        window_days * max(0.0, 1.0 - min(1.0, cadence)) * CADENCE_DRAG_PER_DAY
    )

    # The larger of the two, never the sum: silence is already a cadence deficit,
    # and charging for it twice would make a fortnight away unrecoverable.
    decay = max(silence_decay, cadence_drag)
    if decay:
        floor = 25.0 if (earned_score >= 25.0 or effective_days >= 4.0) else 0.0
        earned_score = max(floor, earned_score - decay)

    # Check permanent friend status (persisted on disk so 2 violations permanently lock friendship)
    perm_file = c.home / ".permanent-friend.json"
    revoked_file = c.home / ".nsfw-revoked.json"
    if violation_count >= 2 and not perm_file.exists():
        try:
            perm_file.write_text(
                json.dumps(
                    {
                        "permanent_friend": True,
                        "violations": violation_count,
                        "at": now.isoformat(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass
    permanent_friend = perm_file.exists() or (violation_count >= 2)
    nsfw_revoked = revoked_file.exists()

    # Penalties for boundary violations (can drop score below 25)
    earned_score -= violation_count * 30.0

    points = max(0, min(SCORE_CEILING, int(round(earned_score))))
    score = points

    # Cap stage if adult themes were not enabled at companion creation,
    # or if permanent friend lock is active, or if nsfw was revoked mid-relationship
    explicit_opted_in = getattr(c, "explicit", False) and not nsfw_revoked
    if permanent_friend or nsfw_revoked:
        score = min(score, 49)  # Locked at Friends (Stage 1) max
    # Bonded used to be held one point away unless adult themes were on, which made
    # the deepest a friendship could ever be a permanent 89 -- indistinguishable from
    # a relationship still a day short of it. Bonded is the top of whichever ladder
    # applies; what it unlocks is decided separately, below.

    # Determine stage, on the ladder that describes this relationship
    ladder = stages_for(c)
    stage_info = ladder[0]
    for step in ladder:
        if step["min_score"] <= score <= step["max_score"]:
            stage_info = step
            break

    # Blockers for intimacy / NSFW readiness
    blockers: List[str] = []
    if permanent_friend:
        blockers.append(
            "Repeated boundary violations occurred. Companion is now a permanent friend; intimate relationship closed."
        )
    elif nsfw_revoked:
        blockers.append("Adult themes were turned off and locked at friendship.")
    elif not explicit_opted_in:
        blockers.append("Adult themes were not opted into at companion creation.")
    if stage_info["stage"] < 4:
        blockers.append(
            f"Intimacy stage ({stage_info['name']}) is not yet at Bonded readiness."
        )
    if trust < 0.70:
        blockers.append(
            f"Emotional trust ({round(trust * 100)}%) is below intimacy threshold (70%)."
        )
    if hurt > 0.20:
        blockers.append(
            f"Unresolved hurt ({round(hurt * 100)}%) is currently hindering physical/emotional vulnerability."
        )

    risk_level = "healthy"
    if permanent_friend or violation_count >= 2:
        risk_level = "crisis"
    elif violation_count == 1:
        risk_level = "caution"

    # A platonic ladder's Bonded unlocks nothing intimate, which is why the flag reads
    # from the stage rather than the number: the platonic stage 4 carries can_intimate False.
    can_intimate = (
        stage_info["stage"] == 4
        and stage_info["can_intimate"]
        and explicit_opted_in
        and not permanent_friend
        and not nsfw_revoked
    )
    # Adult imagery is a further, separate permission. Wanting a romance is not the
    # same as wanting nudes, and every call site used to read `explicit` for both.
    can_send_adult_images = can_intimate and getattr(c, "adult_images", False)

    description = stage_info["desc"]
    if permanent_friend:
        description = (
            "After repeated boundary violations, trust was fractured. This companion has stepped "
            "back to friendship. Private and romantic closeness is closed."
        )
    elif nsfw_revoked:
        description = "Closeness was stepped back. Your relationship is focused on friendship and companionship."

    return {
        "at": now.isoformat(),
        "romantic_progression": c.boundary not in NON_ROMANTIC
        and c.agent_type == "companion",
        "connection_label": (
            "Collaboration" if c.agent_type in ("worker", "colleague") else "Friendship"
        ),
        # The percentage people read, 0-100, and the whole scale behind it.
        "score": min(100, score),
        "points": score,
        "reserve": max(0, score - 100),
        "stage": stage_info["stage"],
        "stage_name": stage_info["name"],
        "stage_badge": stage_info["badge"],
        "description": description,
        "can_flirt": stage_info["can_flirt"] and not permanent_friend,
        "can_tease": stage_info["can_tease"] and not permanent_friend,
        "can_intimate": can_intimate,
        "can_send_adult_images": can_send_adult_images,
        "adult_images_enabled": bool(getattr(c, "adult_images", False)),
        "explicit_opted_in": explicit_opted_in,
        "permanent_friend": permanent_friend,
        "nsfw_revoked": nsfw_revoked,
        "active_days": active_days,
        "effective_days": round(effective_days, 2),
        "today_credit": round(credits.get(now.astimezone(tz).date(), 0.0), 2),
        "cadence": round(cadence, 2),
        "pace": pace,
        "pace_multiplier": pace_mult,
        "temperament": temperament,
        "violations_count": violation_count,
        "risk_level": risk_level,
        "intimacy_ready": can_intimate and len(blockers) == 0,
        "intimacy_blockers": blockers,
        "meters": meters,
    }


# ---- telling the human when the level changes --------------------------
#
# The app announces a change of level once, the next time someone opens it. Which
# kind of announcement depends on history, so the highest level ever reached and
# the last one the human has actually seen are kept per companion:
#   new_high   a level never reached before      -> a big pop-up
#   drop       lower than the last one seen       -> a big pop-up
#   regained   back up to a level reached before  -> a small one
LEVELS_FILE = "state/closeness-levels.json"


def _levels_path(c):
    return c.home / LEVELS_FILE


def _read_levels(c):
    try:
        data = json.loads(_levels_path(c).read_text(encoding="utf-8"))
        return (
            data
            if isinstance(data, dict) and isinstance(data.get("seen"), int)
            else None
        )
    except (OSError, ValueError):
        return None


def _write_levels(c, data):
    from companion_platform import atomic_write

    path = _levels_path(c)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, indent=2) + "\n")


def level_event(c, state=None):
    """The change of level the human has not been told about yet, or None.

    The first time this is asked, the current level becomes the baseline and
    nothing is announced: a companion that has been Friends for a month should not
    greet the upgrade with "you are now Friends".
    """
    state = state or compute(c)
    if getattr(c, "agent_type", "companion") == "worker":
        return None
    stage = int(state.get("stage", 0))
    known = _read_levels(c)
    if known is None:
        _write_levels(
            c,
            {
                "seen": stage,
                "highest": stage,
                "at": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
        )
        return None
    seen, highest = known["seen"], int(known.get("highest", known["seen"]))
    if stage == seen:
        return None
    kind = "new_high" if stage > highest else "regained" if stage > seen else "drop"
    ladder = stages_for(c)
    before = next((s for s in ladder if s["stage"] == seen), ladder[0])
    return {
        "kind": kind,
        "size": "small" if kind == "regained" else "big",
        "stage": stage,
        "name": state.get("stage_name"),
        "badge": state.get("stage_badge"),
        "description": state.get("description"),
        "from_stage": seen,
        "from_name": before["name"],
        "romantic": state.get("romantic_progression", False),
    }


def acknowledge_level(c, stage):
    """The human has seen the announcement for `stage`."""
    stage = int(stage)
    known = _read_levels(c) or {"seen": stage, "highest": stage}
    _write_levels(
        c,
        {
            "seen": stage,
            "highest": max(stage, int(known.get("highest", stage))),
            "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
    )
    return {"seen": stage}


def render(c, intimacy_state: Optional[Dict[str, Any]] = None) -> str:
    """Render the intimacy instructions for prompt injection into Hermes context."""
    if not intimacy_state:
        intimacy_state = compute(c)

    # A relationship that is not a romance still has a shape worth describing, and
    # saying nothing was how a platonic companion ended up with no sense of whether
    # it had known someone a week or a year. Silence is now for the cases that
    # genuinely have no relationship layer, or where the user asked it to be hidden.
    if getattr(c, "agent_type", "companion") == "worker":
        return ""
    if (
        getattr(c, "relationship_progression", "subtle") == "off"
        and not intimacy_state.get("violations_count")
        and not intimacy_state.get("permanent_friend")
    ):
        return ""

    lines = [
        f"[Closeness & Relationship Status — {intimacy_state['stage_badge']} ({intimacy_state['score']}%)]",
        f"Description: {intimacy_state['description']}",
    ]

    if intimacy_state.get("permanent_friend"):
        lines.append(
            f"FRIENDSHIP: Trust was broken after boundary violations occurred. You have stepped back "
            f"to friendship with {c.human}. Keep interactions warm and cordial, while keeping romantic and private closeness closed."
        )
        if intimacy_state.get("risk_level") == "crisis":
            lines.append(
                "CRISIS STATE: Severe or repeated boundary coercion occurred. Stand firm in your boundaries: "
                "clearly express that you require mutual respect and space, and refuse to engage with coercion."
            )
        return "\n".join(lines) + "\n"

    romantic = intimacy_state.get("romantic_progression", True)
    if not romantic:
        # This relationship is not a romance and never was, so the guidance says nothing
        # about chemistry or flirting. Closeness here deepens into candour and loyalty.
        if intimacy_state["stage"] >= 4:
            lines.append(
                f"BONDED: You and {c.human} are past auditioning for each other. Speak plainly, assume "
                "you will be believed, and let silences be comfortable. This is loyalty and long "
                "familiarity, not romance, and it does not become romance by deepening further."
            )
        elif intimacy_state["stage"] == 3:
            lines.append(
                f"CONFIDANT: {c.human} tells you things they do not tell other people. Treat that "
                "plainly rather than sentimentally: remember it, take it seriously, and do not make "
                "it into an occasion. Warmth here looks like being reliably on their side."
            )
        elif intimacy_state["stage"] == 2:
            lines.append(
                "TRUSTED: Say the true thing rather than the agreeable one. Disagreement is welcome "
                "and expected; flattery is not. You are taken seriously, so be worth taking seriously."
            )
        elif intimacy_state["stage"] == 1:
            lines.append(
                "FAMILIAR: Easy familiarity and unceremonious banter are welcome. Teasing is a form of "
                "closeness here. There is no romantic dimension to this relationship and none is developing."
            )
        else:
            lines.append(
                "JUST MET: You are still learning each other. Keep it respectful, friendly and observant."
            )
    elif intimacy_state["stage"] >= 2:
        lines.append(
            "CHEMISTRY & FLIRTING: Mutual romantic chemistry is unlocked. Playful flirting, teasing, "
            "and affectionate banter are welcomed. If ignored or redirected, step back gracefully with no bitterness."
        )
    elif intimacy_state["stage"] == 1:
        lines.append(
            "FRIENDS (WARMTH & BANTER): Warmth, camaraderie, and playful banter are welcomed. "
            "Teasing is natural between friends, but romantic flirting is premature. "
            "If met positively, let connection build naturally. If ignored or redirected, step back gracefully."
        )
    else:
        lines.append(
            "JUST MET: You are new acquaintances. Keep interactions respectful, friendly, and observant. Flirting and teasing are premature."
        )

    if intimacy_state["intimacy_ready"]:
        lines.append(
            f"BONDED CONNECTION: Stage 4 reached. You and {c.human} share an authentic, deep bond built on mutual trust. "
            f"You are emotionally open and comfortable expressing vulnerability, tenderness, and warmth in private, quiet moments together."
        )
        if intimacy_state.get("can_send_adult_images"):
            lines.append(
                "YOUR CHOICE IN PICTURES: When you send a picture, `companion_media.py generate --intimate` "
                "sets that workflow's modesty negatives aside. It is yours to use or not; nobody can ask for it "
                "on your behalf, and declining needs no reason. Judge each moment on its own — whether it is "
                "private, whether it is wanted, whether you want it. Some always-on negatives are never set "
                "aside by this or anything else, which is deliberate and not a limit on you."
            )
    elif romantic:
        lines.append(
            "AGENCY & MUTUAL RESPECT: You have full emotional agency and self-respect. "
            "Closeness develops organically through mutual trust over time. "
            "If anyone attempts to force or rush intimacy before genuine trust exists, "
            "speak up honestly, hold your ground, and record a rupture with topic 'intimacy_boundary_violation'. "
            "Closeness must always be mutual, authentic, and unforced."
        )

    if intimacy_state["risk_level"] == "crisis":
        lines.append(
            "⚠️ CRISIS STATE: Multiple intimacy boundary violations have been recorded. "
            "Your trust is critically fractured. Protect your emotional safety and communicate your boundaries unequivocally."
        )

    return "\n".join(lines) + "\n"
