#!/usr/bin/env python3
"""Contextual relationship indicators derived from recorded experiences and routines.

Presence remains the authority for authored mood and private stance. These game-like
indicators supply context, never evidence that an unrecorded event occurred.
"""

from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write, file_lock

UTC = dt.timezone.utc
PROFILES = {
    "steady": {"sensitivity": 0.7, "recovery_days": 7, "trust": 0.7},
    "expressive": {"sensitivity": 1.3, "recovery_days": 14, "trust": 0.65},
    "guarded": {"sensitivity": 1.0, "recovery_days": 30, "trust": 0.5},
}
DEFAULTS = {
    "personality": "steady",
    "connection_hours": 48,
    "absence_windows": [],
    "learn_rhythm": True,
}


def _text(value, label, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} must contain 1–{limit} characters")
    return value.strip()


def _stamp(value):
    try:
        result = dt.datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError("Use an ISO timestamp with a timezone")
    if result.tzinfo is None:
        raise ValueError("Timestamp needs a timezone")
    return result.astimezone(UTC)


def _number(value, label, low, high):
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError(f"{label} must be between {low} and {high}")
    return value


def validate_settings(data):
    if not isinstance(data, dict):
        raise ValueError("Feelings settings must be an object")
    personality = data.get("personality", "steady")
    if personality not in PROFILES:
        raise ValueError("Choose steady, expressive or guarded")
    hours = _number(data.get("connection_hours", 48), "connection_hours", 6, 168)
    windows = data.get("absence_windows", [])
    if not isinstance(windows, list) or len(windows) > 20:
        raise ValueError("Supply at most 20 expected absence windows")
    cleaned = []
    for row in windows:
        if not isinstance(row, dict):
            raise ValueError("Each absence window must be an object")
        days = row.get("days")
        if (
            not isinstance(days, list)
            or not days
            or any(type(x) != int or not 0 <= x <= 6 for x in days)
        ):
            raise ValueError("days must contain weekdays 0 (Monday) through 6 (Sunday)")
        for key in ("start", "end"):
            if not isinstance(row.get(key), str) or not re.fullmatch(
                r"(?:[01]\d|2[0-3]):[0-5]\d", row[key]
            ):
                raise ValueError("Use HH:MM for absence start and end")
        if row["start"] == row["end"]:
            raise ValueError(
                "An absence window must have different start and end times"
            )
        cleaned.append(
            {
                "label": _text(row.get("label"), "absence label", 80),
                "days": sorted(set(days)),
                "start": row["start"],
                "end": row["end"],
            }
        )
    learn = data.get("learn_rhythm", True)
    if not isinstance(learn, bool):
        raise ValueError("learn_rhythm must be true or false")
    return {
        "personality": personality,
        "connection_hours": hours,
        "absence_windows": cleaned,
        "learn_rhythm": learn,
    }


def settings(c):
    path = c.life / "feelings-settings.json"
    raw = path.read_text(encoding="utf-8") if path.exists() else ""
    return {
        "settings": validate_settings(json.loads(raw) if raw else DEFAULTS),
        "revision": hashlib.sha256(raw.encode()).hexdigest(),
    }


def save_settings(c, data, revision):
    clean = validate_settings(data)
    with file_lock(c.life / ".feelings.lock"):
        if revision != settings(c)["revision"]:
            raise FileExistsError("Feelings settings changed. Reload before saving.")
        atomic_write(
            c.life / "feelings-settings.json",
            json.dumps(clean, ensure_ascii=False, indent=2) + "\n",
        )
    return settings(c)


def experiences(c):
    path = c.life / "relationship-feelings.jsonl"
    if not path.exists():
        return []
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Invalid relationship experience ledger")
    return rows


def record(c, data, now=None):
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    now = now.astimezone(UTC)
    if not isinstance(data, dict):
        raise ValueError("Experience must be an object")
    kind = data.get("kind")
    if kind not in ("connection", "rupture", "repair", "correction"):
        raise ValueError("kind must be connection, rupture, repair or correction")
    evidence = _text(data.get("evidence"), "evidence", 1000)
    topic = _text(data.get("topic"), "topic", 80).lower()
    description = _text(data.get("text"), "experience", 500)
    at = _stamp(data.get("at", now.isoformat()))
    if at > now + dt.timedelta(minutes=1):
        raise ValueError("An experience cannot be in the future")
    severity = _number(data.get("strength", 0.5), "strength", 0, 1)
    related = data.get("related")
    ident = (
        data.get("id")
        or hashlib.sha256(
            (kind + topic + evidence + at.date().isoformat()).encode()
        ).hexdigest()[:24]
    )
    if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", ident):
        raise ValueError("Use a short alphanumeric experience id")
    row = {
        "id": ident,
        "kind": kind,
        "topic": topic,
        "text": description,
        "evidence": evidence,
        "strength": severity,
        "at": at.isoformat(),
        "related": related,
    }
    with file_lock(c.life / ".feelings.lock"):
        rows = experiences(c)
        if kind in ("repair", "correction"):
            target = next(
                (
                    r
                    for r in rows
                    if r["id"] == related
                    and (
                        r["kind"] == "rupture"
                        if kind == "repair"
                        else r["kind"] != "correction"
                    )
                ),
                None,
            )
            if not target:
                raise ValueError(
                    "Choose a recorded rupture for repair, or an existing experience for correction"
                )
            if _stamp(target["at"]) > at:
                raise ValueError(
                    "Repair or correction cannot precede the original experience"
                )
            row["topic"] = target["topic"]
        elif related is not None:
            raise ValueError("Only repair and correction experiences use related")
        existing = next((r for r in rows if r["id"] == ident), None)
        if existing:
            # Retry is idempotent; an ID must not silently identify different evidence.
            if any(
                existing[k] != row[k]
                for k in ("kind", "topic", "text", "evidence", "strength", "related")
            ):
                raise FileExistsError("Experience id already has different content")
            return {"written": False, "experience": existing}
        with (c.life / "relationship-feelings.jsonl").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"written": True, "experience": row}


def _absence_time(value, timezone=None):
    """Resolve wall time explicitly; never guess during a DST gap or fold."""
    try:
        stamp = dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("Use an ISO date and time for the expected absence")
    if stamp.tzinfo is not None:
        return stamp.astimezone(UTC)
    if not timezone:
        raise ValueError("Expected absence times need a timezone or an explicit offset")
    try:
        zone = ZoneInfo(timezone)
    except (ValueError, KeyError, TypeError):
        raise ValueError("Choose a valid timezone")
    choices = {
        candidate.astimezone(UTC)
        for fold in (0, 1)
        if (candidate := stamp.replace(tzinfo=zone, fold=fold))
        .astimezone(UTC)
        .astimezone(zone)
        .replace(tzinfo=None)
        == stamp
    }
    if len(choices) != 1:
        raise ValueError(
            "That local time is ambiguous or does not exist because the clocks change. "
            "Use an ISO timestamp with an explicit UTC offset."
        )
    return choices.pop()


def expected_absences(c, now=None):
    """Current dated expectations plus their unchanged, append-only evidence."""
    now = now or dt.datetime.now(UTC)
    path = c.life / "expected-absences.jsonl"
    raw = path.read_text(encoding="utf-8") if path.exists() else ""
    history = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in history):
        raise ValueError("Invalid expected absence ledger")
    latest = {}
    for row in history:
        if _stamp(row["recorded_at"]) <= now:
            latest[row["id"]] = row
    rows = []
    for row in latest.values():
        status = (
            "cancelled"
            if row["action"] == "cancel"
            else (
                "ended"
                if _stamp(row["end"]) <= now
                else "upcoming" if _stamp(row["start"]) > now else "current"
            )
        )
        rows.append({**row, "status": status})
    return {
        "absences": sorted(rows, key=lambda row: (row["start"], row["id"])),
        "history": history,
        "revision": hashlib.sha256(raw.encode()).hexdigest(),
        "timezone": c.timezone or "UTC",
    }


def record_absence(c, data, now=None):
    """Save a human-supported plan. Changes preserve time already explained."""
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    now = now.astimezone(UTC)
    if not isinstance(data, dict):
        raise ValueError("Expected absence must be an object")
    action = data.get("action", "create")
    if action not in ("create", "edit", "cancel"):
        raise ValueError("action must be create, edit or cancel")
    clean = {
        "action": action,
        "evidence": _text(data.get("evidence"), "the human's explanation", 1000),
        "source": _text(data.get("source"), "evidence source", 300),
    }
    if action != "cancel":
        start = _absence_time(data.get("start"), data.get("timezone"))
        end = _absence_time(data.get("end"), data.get("timezone"))
        if end <= start:
            raise ValueError("Expected absence end must be after its start")
        clean.update(
            label=_text(data.get("label"), "absence label", 80),
            start=start.isoformat(),
            end=end.isoformat(),
        )
    ident = data.get("id")
    if not ident and action == "create":
        ident = hashlib.sha256(json.dumps(clean, sort_keys=True).encode()).hexdigest()[
            :24
        ]
    if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", ident):
        raise ValueError("Use a short alphanumeric absence id")
    clean["id"] = ident
    event_id = (
        data.get("event_id")
        or hashlib.sha256(
            json.dumps(
                {**clean, "revision": data.get("revision")}, sort_keys=True
            ).encode()
        ).hexdigest()[:24]
    )
    if not isinstance(event_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,80}", event_id
    ):
        raise ValueError("Use a short alphanumeric event_id for retries")
    with file_lock(c.life / ".feelings.lock"):
        state = expected_absences(c, now)
        previous = next((row for row in state["absences"] if row["id"] == ident), None)
        existing = next(
            (row for row in state["history"] if row["event_id"] == event_id), None
        )
        if existing:
            if any(existing.get(key) != value for key, value in clean.items()):
                raise FileExistsError("Expected absence event id has different content")
            return {"written": False, "event": existing, **state}
        if data.get("revision") != state["revision"]:
            raise FileExistsError("Expected absences changed. Reload before saving.")
        if any(_stamp(row["recorded_at"]) > now for row in state["history"]):
            raise ValueError("The clock precedes an existing expected absence record")
        if action == "create" and previous:
            raise FileExistsError("Expected absence id already exists; edit it instead")
        if action != "create" and (not previous or previous["status"] == "cancelled"):
            raise ValueError("Choose an existing, uncancelled expected absence")
        if previous and _stamp(previous["recorded_at"]) > now:
            raise ValueError("The clock precedes the previous expected absence record")
        if action == "cancel":
            clean.update({key: previous[key] for key in ("label", "start", "end")})
        row = {**clean, "event_id": event_id, "recorded_at": now.isoformat()}
        with (c.life / "expected-absences.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return {"written": True, "event": row, **expected_absences(c, now)}


def expected_absence_intervals(c, now):
    """Each revision supersedes only the remaining future of its predecessor."""
    pending = {}
    intervals = []
    for row in expected_absences(c, now)["history"]:
        at = _stamp(row["recorded_at"])
        if at > now:
            continue
        previous = pending.pop(row["id"], None)
        if previous:
            start, end, label = previous
            if min(end, at) > start:
                intervals.append((start, min(end, at), label))
        if row["action"] != "cancel":
            start = _stamp(row["start"])
            # Creation can explain a past interval supplied by the human. Later
            # edits cannot remove the explanation that already governed that time.
            if row["action"] == "edit":
                start = max(start, at)
            pending[row["id"]] = (start, _stamp(row["end"]), row["label"])
    intervals.extend(pending.values())
    return intervals


def absence(c, since, now, config, known_at=None):
    """Union expected windows in UTC; overlapping routines never count twice."""
    if not since:
        return {
            "hours": None,
            "unexplained_hours": None,
            "expected_hours": None,
            "current": [],
        }
    start = _stamp(since)
    end = now.astimezone(UTC)
    if start > end:
        return {
            "hours": None,
            "unexplained_hours": None,
            "expected_hours": None,
            "current": [],
            "warning": "Last message is in the future; check the clock.",
        }
    # Longing saturates; bound routine evaluation to the most recent year.
    measured = max(start, end - dt.timedelta(days=366))
    tz = ZoneInfo(c.timezone or "UTC")
    intervals = []
    labels = []
    for a, b, label in expected_absence_intervals(c, known_at or end):
        if a <= end < b:
            labels.append(label)
        a, b = max(a, measured), min(b, end)
        if b > a:
            intervals.append((a, b))
    day = measured.astimezone(tz).date() - dt.timedelta(days=1)
    last = end.astimezone(tz).date()
    while day <= last:
        for window in config["absence_windows"]:
            if day.weekday() not in window["days"]:
                continue
            a = dt.datetime.combine(day, dt.time.fromisoformat(window["start"]), tz)
            b = dt.datetime.combine(
                day + dt.timedelta(days=window["end"] < window["start"]),
                dt.time.fromisoformat(window["end"]),
                tz,
            )
            a = a.astimezone(UTC)
            b = b.astimezone(UTC)
            if a <= end < b:
                labels.append(window["label"])
            a = max(a, measured)
            b = min(b, end)
            if b > a:
                intervals.append((a, b))
        day += dt.timedelta(days=1)
    merged = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    expected = sum((b - a).total_seconds() / 3600 for a, b in merged)
    hours = (end - start).total_seconds() / 3600
    return {
        "hours": round(hours, 2),
        "unexplained_hours": round(
            max(0, (end - measured).total_seconds() / 3600 - expected), 2
        ),
        "expected_hours": round(expected, 2),
        "current": list(dict.fromkeys(labels)),
        "measured_since": measured.isoformat(),
    }


# Warmth and trust move on their own, slowly, from how the two of you actually are:
# ordinary days of talking, and things she was asked to do and did. No model reads the
# conversation for this; it counts days. Both are small and capped, so they colour the
# recorded experiences and never replace them.
CONTACT_HUMAN_MESSAGES = 3
WARMTH_PER_DAY = 0.02
WARMTH_CAP = 0.2
TRUST_PER_DAY = 0.004
TRUST_CAP = 0.12
TRUST_PER_KEPT_ASK = 0.01
TRUST_KEPT_CAP = 0.06


def passive(c, now, profile, unresolved):
    """Slow drift from days of real two-way conversation and kept requests.

    A day counts when the human wrote at least three times and she answered. Warmth
    is recent (it fades on the temperament's own recovery time); trust is the whole
    history and does not fade. While a rupture sits unrepaired trust does not build
    and warmth builds at half rate: time alone does not mend what was hurt.
    """
    import companion_thread

    days = companion_thread.contact_days(c, now)
    counted = {
        day: counts
        for day, counts in days.items()
        if counts[0] >= CONTACT_HUMAN_MESSAGES and counts[1] >= 1
    }
    try:
        today = now.astimezone(ZoneInfo(c.timezone or "UTC")).date()
    except Exception:
        today = now.astimezone(UTC).date()
    warmth = sum(
        WARMTH_PER_DAY
        * math.exp(-max(0, (today - day).days) / profile["recovery_days"])
        for day in counted
    )
    trust = TRUST_PER_DAY * len(counted)
    try:
        import companion_missions

        kept = len(companion_missions.missions(c, "done", now))
    except (OSError, ValueError, ImportError):
        kept = 0
    trust += min(TRUST_KEPT_CAP, TRUST_PER_KEPT_ASK * kept)
    warmth = min(WARMTH_CAP, warmth) * (0.5 if unresolved else 1)
    trust = 0.0 if unresolved else min(TRUST_CAP + TRUST_KEPT_CAP, trust)
    return {
        "warmth": round(warmth, 4),
        "trust": round(trust, 4),
        "contact_days": len(counted),
        "kept_requests": kept,
        "paused_by_unrepaired_rupture": bool(unresolved),
    }


def compute(c, now=None):
    import companion_thread
    import companion_presence

    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    config = settings(c)["settings"]
    profile = PROFILES[config["personality"]]
    thread = companion_thread.read(c, now)
    # Entered windows always count. When there is enough history, the hours the human
    # is almost never writing count too, so sleep is not mistaken for distance.
    rhythm = {"windows": [], "evidence": None}
    if config["learn_rhythm"]:
        import companion_rhythm

        rhythm = companion_rhythm.learned(c, now)
    config = {
        **config,
        "absence_windows": config["absence_windows"] + rhythm["windows"],
    }
    away = absence(c, thread.get("last_from_human"), now, config)
    arrival = None
    last = thread.get("last_from_human")
    previous = thread.get("previous_from_human")
    if (
        last
        and previous
        and 0 <= (now.astimezone(UTC) - _stamp(last)).total_seconds() < 300
    ):
        arrival = absence(c, previous, _stamp(last), config, known_at=now)
    relevant = arrival or away
    gap = relevant["unexplained_hours"]
    longing = (
        None
        if gap is None
        else gap / config["connection_hours"] * profile["sensitivity"]
    )
    trust = profile["trust"]
    warmth = 0.65
    hurt = 0.0
    irritation = 0.0
    counts = {}
    reasons = []
    rows = sorted(
        (r for r in experiences(c) if _stamp(r["at"]) <= now.astimezone(UTC)),
        key=lambda r: r["at"],
    )
    history = rows
    corrected = {r["related"] for r in history if r["kind"] == "correction"}
    rows = [
        r for r in history if r["id"] not in corrected and r["kind"] != "correction"
    ]
    repair = {}
    for row in rows:
        if row["kind"] == "repair":
            repair[row["related"]] = max(repair.get(row["related"], 0), row["strength"])
    for row in rows:
        age = max(0, (now.astimezone(UTC) - _stamp(row["at"])).total_seconds() / 86400)
        decay = math.exp(-age / profile["recovery_days"])
        strength = row["strength"]
        if row["kind"] == "connection":
            warmth += 0.12 * strength * decay
            trust += 0.04 * strength
        if row["kind"] == "rupture":
            counts[row["topic"]] = counts.get(row["topic"], 0) + 1
            repetition = 1 + min(2, counts[row["topic"]] - 1) * 0.4
            impact = strength * profile["sensitivity"] * repetition
            repaired = repair.get(row["id"], 0)
            trust -= 0.25 * impact * (1 - 0.8 * repaired)
            hurt += 0.65 * impact * decay * (1 - 0.7 * repaired)
            irritation += 0.45 * impact * decay * (1 - 0.6 * repaired)
            warmth -= 0.2 * impact * decay * (1 - 0.7 * repaired)
            reasons.append(
                {
                    "id": row["id"],
                    "text": row["text"],
                    "topic": row["topic"],
                    "occurrence": counts[row["topic"]],
                    "repair": repaired,
                }
            )
        trust = max(0, min(1, trust))
        warmth = max(0, min(1, warmth))
    try:
        slow = passive(c, now, profile, any(row["repair"] < 0.5 for row in reasons))
    except (OSError, ValueError, TypeError):
        slow = None
    if slow:
        warmth = max(0, min(1, warmth + slow["warmth"]))
        trust = max(0, min(1, trust + slow["trust"]))
    if gap is not None:
        irritation += (
            max(0, gap - config["connection_hours"]) * 0.003 * profile["sensitivity"]
        )
    clamp = lambda value: max(0.0, min(1.0, value))
    scene = companion_presence.current(c)
    return {
        "at": now.isoformat(),
        "enabled": c.bars,
        "personality": config["personality"],
        "mood": scene["state"].get("mood") if scene else None,
        "mood_at": scene.get("recorded_at") if scene else None,
        "private_stance": scene["state"].get("private_stance") if scene else None,
        "meters": {
            "warmth": clamp(warmth),
            "trust": clamp(trust),
            "hurt": clamp(hurt),
            "irritation": clamp(irritation),
            "longing": None if longing is None else clamp(longing),
        },
        "absence": away,
        "expected_absences": expected_absences(c, now)["absences"],
        "slow_change": slow,
        "learned_rhythm": rhythm["evidence"],
        "recent_return": arrival,
        "reasons": reasons[-5:],
        "experiences": history[-30:],
        "history_count": len(history),
        "basis": "Character defaults adjusted by recorded experiences; game-like interpretation, not measured emotions.",
    }


def render(c, state):
    if not c.bars:
        return ""
    meters = ", ".join(
        f"{name} {round(value*100)}%"
        for name, value in state["meters"].items()
        if value is not None
    )
    lines = [
        f'[Contextual feelings — {state["personality"]} temperament; current derived state]',
        meters,
        "Let this affect warmth, reserve, teasing and willingness to discuss a hurt, in the voice of SOUL.md. "
        "Preserve your recorded mood and private stance; these indicators add context rather than replacing them. Use this live interpretation over older elapsed-gap sensor guidance. "
        "Acknowledge an unresolved repeated hurt differently from a first occurrence. Repair softens it without erasing history. "
        "Do not recite meters. Do not infer betrayal or invent an event from silence. Continue practical help dependably even when irritated.",
    ]
    gap = state["recent_return"] or state["absence"]
    if gap["hours"] is not None:
        lines.append(
            (
                "They just returned after "
                if state["recent_return"]
                else "Since their last message: "
            )
            + f'{gap["hours"]:g}h; {gap["expected_hours"]:g}h explained by expected time apart; {gap["unexplained_hours"]:g}h outside it.'
        )
    if state["absence"]["current"]:
        lines.append(
            "Expected time apart now (not live observation): "
            + ", ".join(state["absence"]["current"])
            + ". Do not treat this as unexplained withdrawal."
        )
    for row in state.get("expected_absences", []):
        if row["status"] in ("current", "upcoming"):
            lines.append(
                f'Human-explained plan {row["id"]}: {row["label"]}, '
                f'{row["start"]} to {row["end"]}; {row["status"]}. '
                f'Evidence: {row["evidence"]} (source: {row["source"]}). '
                "This is an expectation, not an observation of what they are doing. "
                "No longing, irritation or relationship penalty for the explained interval."
            )
    for row in state["reasons"]:
        lines.append(
            f'Recorded experience {row["id"]}: {row["text"]} (topic {row["topic"]}, occurrence {row["occurrence"]}, repair {round(row["repair"]*100)}%).'
        )
    from companion_platform import terminal_python_command

    command = terminal_python_command(
        pathlib.Path(__file__), "--home", c.home, "record"
    )
    lines.append(
        "Record meaningful relationship experiences only when supported by this conversation, not every message: "
        + command
        + " --json JSON. Fields: kind connection|rupture|repair|correction, topic (reuse for repeated experiences), text, evidence (actual words/context), strength 0..1; repair needs related rupture id; correction excludes a mistaken related experience without deleting it. Do not claim a record was saved until the command succeeds."
    )
    read_command = terminal_python_command(
        pathlib.Path(__file__), "--home", c.home, "absences"
    )
    write_command = terminal_python_command(
        pathlib.Path(__file__), "--home", c.home, "absence"
    )
    lines.append(
        "When the human explicitly explains dated time away, save it with their actual words and source; "
        "do not infer dates from silence or quiet hours. Read "
        + read_command
        + " for the current revision and IDs, then "
        + write_command
        + " --json JSON. Fields: action create|edit|cancel, revision, id (required for edit/cancel), "
        "event_id (stable retry ID), label, start, end (ISO timestamps with offsets, or local ISO times plus timezone), "
        "evidence (human's words), source (conversation/message reference). Cancel needs only action, revision, id, evidence and source. "
        "Ask for unclear dates rather than inventing them. Future plans are expectations, not observed activity. "
        "Edits and cancellation preserve elapsed explained time. Claim saved only after successful execution. "
        "The human can review and change dated plans in Us → Expected time apart."
    )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=pathlib.Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show")
    sub.add_parser("absences")
    p = sub.add_parser("record")
    p.add_argument("--json", required=True)
    p = sub.add_parser("absence")
    p.add_argument("--json", required=True)
    args = parser.parse_args()
    c = cc.load(args.home)
    print(
        json.dumps(
            (
                record(c, json.loads(args.json))
                if args.command == "record"
                else (
                    record_absence(c, json.loads(args.json))
                    if args.command == "absence"
                    else (
                        expected_absences(c)
                        if args.command == "absences"
                        else compute(c)
                    )
                )
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
