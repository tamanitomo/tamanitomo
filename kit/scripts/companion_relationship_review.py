#!/usr/bin/env python3
"""Explain relationship restrictions and audit corrections without erasing history.

A review only retires a machine restriction whose identified source records have
already been corrected. It neither interprets an incident nor changes a stance,
configuration choice, provider policy or the original restriction record.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json

from companion_platform import atomic_write, file_lock

LOCK_FILE = ".permanent-friend.json"
REVIEWS_FILE = "relationship-restriction-reviews.jsonl"
RESTRICTIONS_FILE = "relationship-restrictions.jsonl"
TOPICS = frozenset(
    ("intimacy_boundary_violation", "sexual_boundary_violation", "boundary_violation")
)
UTC = dt.timezone.utc


class StaleReviewError(ValueError):
    """The evidence changed after the report was opened."""


def _now(value):
    value = value or dt.datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("Timezone required")
    return value.astimezone(UTC)


def _stamp(value):
    result = dt.datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Timezone required")
    return result.astimezone(UTC)


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _read(path, warnings):
    try:
        return path.read_text(encoding="utf-8") if path.exists() else None
    except (OSError, UnicodeError):
        warnings.append(f"Could not read {path.name}; inspection is required.")
        return "<unreadable>"


def _rows(raw, label, warnings):
    try:
        rows = [json.loads(line) for line in (raw or "").splitlines() if line.strip()]
        if any(not isinstance(row, dict) for row in rows):
            raise ValueError("Expected objects")
        return rows
    except (ValueError, TypeError):
        warnings.append(f"Malformed {label}; inspection is required.")
        return []


def _generation(c, now, lock_raw, ledger_raw, review_raw, revoked_raw, warnings):
    warnings = list(warnings)
    rows = _rows(ledger_raw, "relationship experiences", warnings)
    reviews = _rows(review_raw, "restriction reviews", warnings)
    lock = None
    if lock_raw is not None:
        try:
            lock = json.loads(lock_raw)
            if not isinstance(lock, dict):
                raise ValueError("Expected object")
        except (ValueError, TypeError):
            lock = None
            warnings.append("Malformed restriction record; inspection is required.")
    by_id = {}
    relevant = []
    for row in rows:
        try:
            ident = row["id"]
            if not isinstance(ident, str) or not ident or ident in by_id:
                raise ValueError("Missing or ambiguous experience ID")
            _stamp(row["at"])
            if row.get("kind") not in ("connection", "rupture", "repair", "correction"):
                raise ValueError("Unknown experience kind")
            by_id[ident] = row
        except (KeyError, ValueError, TypeError):
            warnings.append(
                "Invalid or duplicate experience IDs/dates; inspection is required."
            )
    source_ids = (lock or {}).get("violation_ids", [])
    valid_ids = (
        isinstance(source_ids, list)
        and len(source_ids) >= 2
        and all(isinstance(i, str) and i for i in source_ids)
        and len(set(source_ids)) == len(source_ids)
    )
    source_ids = source_ids if valid_ids else []
    boundary_ids = {
        r.get("id")
        for r in rows
        if isinstance(r.get("id"), str)
        and r.get("kind") == "rupture"
        and isinstance(r.get("topic"), str)
        and r.get("topic") in TOPICS
    }
    for row in rows:
        try:
            if _stamp(row["at"]) > now:
                continue
            if row.get("id") in boundary_ids or (
                row.get("kind") == "correction"
                and row.get("related") in boundary_ids | set(source_ids)
            ):
                relevant.append(row)
        except (KeyError, ValueError, TypeError):
            continue
    incident_revision = _digest(relevant)
    # A reviewed mistake stays corrected when an independent incident happens.
    # Only changes to this lock's original sources or their corrections invalidate
    # its retirement. The full ledger still binds the optimistic report revision,
    # and two current violations independently enforce a restriction in intimacy.
    source_revision = _digest(
        [
            row
            for row in relevant
            if row.get("id") in source_ids
            or (row.get("kind") == "correction" and row.get("related") in source_ids)
        ]
    )
    incidents = []
    for ident in dict.fromkeys(
        source_ids
        + [
            r.get("id")
            for r in rows
            if isinstance(r.get("id"), str) and r.get("id") in boundary_ids
        ]
    ):
        row = by_id.get(ident)
        incident = {"id": ident, "status": "missing", "corrections": [], "repairs": []}
        if row:
            incident.update(
                {k: row.get(k) for k in ("topic", "text", "evidence", "at")}
            )
            valid = (
                row.get("kind") == "rupture"
                and isinstance(row.get("topic"), str)
                and row.get("topic") in TOPICS
                and all(
                    isinstance(row.get(k), str) and row[k].strip()
                    for k in ("text", "evidence")
                )
            )
            try:
                valid = valid and _stamp(row["at"]) <= now
            except (ValueError, TypeError, KeyError):
                valid = False
            incident["status"] = "active" if valid else "invalid"
            for update in rows:
                if update.get("related") != ident or update.get("kind") not in (
                    "correction",
                    "repair",
                ):
                    continue
                try:
                    at = _stamp(update["at"])
                    if at > now:
                        continue
                    if at < _stamp(row["at"]) or not all(
                        isinstance(update.get(k), str) and update[k].strip()
                        for k in ("id", "text", "evidence")
                    ):
                        raise ValueError("Invalid correction or repair")
                    key = "corrections" if update["kind"] == "correction" else "repairs"
                    incident[key].append(
                        {k: update[k] for k in ("id", "text", "evidence", "at")}
                    )
                except (KeyError, TypeError, ValueError):
                    warnings.append(
                        f"Invalid correction or repair for {ident}; inspection is required."
                    )
            if valid and incident["corrections"]:
                incident["status"] = "corrected"
        incidents.append(incident)
    if any(r["status"] == "invalid" for r in incidents):
        warnings.append(
            "A boundary incident has invalid or future evidence; inspection is required."
        )
    sources = [r for r in incidents if r["id"] in source_ids]
    active = [r for r in incidents if r["status"] == "active"]
    present = lock_raw is not None
    lock_revision = _digest(lock_raw) if present else None
    provenance = "missing" if not present else "identified"
    if present:
        if lock is None:
            provenance = "malformed"
        elif "violation_ids" not in lock:
            provenance = "legacy"
        elif (
            not valid_ids
            or lock.get("permanent_friend") is not True
            or (
                type(lock.get("violations")) is not int
                or lock["violations"] != len(source_ids)
            )
        ):
            provenance = "malformed"
        else:
            try:
                created = _stamp(lock["at"])
                if created > now or any(
                    r["status"] in ("missing", "invalid") or _stamp(r["at"]) > created
                    for r in sources
                ):
                    provenance = "missing"
            except (KeyError, ValueError, TypeError):
                provenance = "malformed"
    corrected_sources = bool(
        present
        and provenance == "identified"
        and not warnings
        and any(r["status"] == "corrected" for r in sources)
        and sum(r["status"] == "active" for r in sources) < 2
    )
    eligible = corrected_sources and len(active) < 2
    retirement = None
    if corrected_sources:
        for row in reviews:
            try:
                matches = (
                    row.get("kind") == "retire_corrected_restriction"
                    and row.get("lock_revision") == lock_revision
                    and row.get("source_revision") == source_revision
                    and row.get("source_ids") == source_ids
                    and isinstance(row.get("reason"), str)
                    and bool(row["reason"].strip())
                    and _stamp(row["at"]) <= now
                )
                if matches:
                    retirement = row
            except (KeyError, ValueError, TypeError):
                continue
    effective = present and retirement is None
    if retirement:
        status, reason = (
            "retired",
            "This exact restriction was reviewed after its source incidents were corrected. The original record is preserved.",
        )
    elif not present:
        status, reason = "absent", "There is no persisted relationship restriction."
    elif warnings or provenance != "identified":
        status, reason = (
            "inspection_required",
            "The restriction's complete source history cannot be verified; no automatic retirement is available.",
        )
    elif eligible:
        status, reason = (
            "active",
            "Explicit corrections leave fewer than two active boundary incidents. A reasoned review can retire this recorded restriction.",
        )
    else:
        status, reason = (
            "active",
            "The current source records do not establish that this restriction was based on corrected incidents.",
        )
    inspection_required = bool(warnings) or (present and provenance != "identified")
    evidence_groups = {}
    for incident in incidents:
        evidence = incident.get("evidence")
        if isinstance(evidence, str):
            evidence_groups.setdefault(evidence.strip(), []).append(incident["id"])
    duplicates = [ids for text, ids in evidence_groups.items() if text and len(ids) > 1]
    if duplicates:
        warnings.append(
            "Some boundary records repeat the same evidence. They remain separate records; no incident has been automatically corrected."
        )
    configuration = {
        "boundary": c.boundary,
        "agent_type": c.agent_type,
        "explicit": bool(c.explicit),
        "adult_images": bool(getattr(c, "adult_images", False)),
        "nsfw_revoked": revoked_raw is not None,
    }
    return {
        "revision": _digest(
            [
                str(c.home.resolve()),
                lock_raw,
                ledger_raw,
                review_raw,
                revoked_raw,
                configuration,
                incident_revision,
            ]
        ),
        "configuration": configuration,
        "restriction": {
            "present": present,
            "effective": effective,
            "status": status,
            "lock_revision": lock_revision,
            "provenance": provenance,
            "source_ids": source_ids,
            "incidents": sources,
            "eligible": eligible and retirement is None,
            "reason": reason,
        },
        "incidents": incidents,
        "active_violation_count": len(active),
        "incident_revision": incident_revision,
        "source_revision": source_revision,
        "duplicate_evidence_groups": duplicates,
        "reviews": reviews,
        "inspection_required": inspection_required,
        "warnings": list(dict.fromkeys(warnings)),
    }


def _snapshot(c, now):
    warnings = []
    original = _read(c.home / LOCK_FILE, warnings)
    saved_raw = _read(c.life / RESTRICTIONS_FILE, warnings)
    ledger_raw = _read(c.life / "relationship-feelings.jsonl", warnings)
    review_raw = _read(c.life / REVIEWS_FILE, warnings)
    revoked_raw = _read(c.home / ".nsfw-revoked.json", warnings)
    saved = _rows(saved_raw, "restriction generations", warnings)
    records = [original] if original is not None else []
    seen = set()
    malformed = False
    for row in saved:
        try:
            ident = row["id"]
            if (
                row.get("kind") != "persisted_relationship_restriction"
                or not isinstance(ident, str)
                or not ident
                or ident in seen
            ):
                raise ValueError("Invalid restriction generation")
            seen.add(ident)
            if _stamp(row["at"]) <= now:
                records.append(json.dumps(row, sort_keys=True))
        except (KeyError, ValueError, TypeError):
            malformed = True
    if saved and original is None:
        warnings.append(
            "The original restriction record is missing; inspection is required."
        )
    if malformed or (saved_raw and not saved):
        warnings.append("Malformed restriction generations; inspection is required.")
        records.append("<malformed restriction generations>")
    generations = [
        _generation(c, now, raw, ledger_raw, review_raw, revoked_raw, warnings)
        for raw in records or [None]
    ]
    # A later retirement cannot hide an earlier source whose correction changed.
    current = next(
        (r for r in reversed(generations) if r["restriction"]["effective"]),
        generations[-1],
    )
    current["restriction_history"] = [
        {**r["restriction"], "source_revision": r["source_revision"]}
        for r in generations
        if r["restriction"]["present"]
    ]
    current["inspection_required"] = any(r["inspection_required"] for r in generations)
    current["revision"] = _digest(
        [
            str(c.home.resolve()),
            original,
            saved_raw,
            ledger_raw,
            review_raw,
            revoked_raw,
            current["configuration"],
            current["incident_revision"],
            [r["lock_revision"] for r in current["restriction_history"]],
        ]
    )
    return current


def persist_restriction(c, now=None):
    """Persist a new supported generation; never overwrite any earlier record."""
    now = _now(now)
    with file_lock(c.life / ".feelings.lock"):
        with file_lock(c.home / ".relationship-review.lock"):
            current = _snapshot(c, now)
            active = [r["id"] for r in current["incidents"] if r["status"] == "active"]
            if len(active) < 2 or current["inspection_required"]:
                return {"written": False}
            covered = any(
                saved["effective"]
                and sum(r["status"] == "active" for r in saved["incidents"]) >= 2
                for saved in current["restriction_history"]
            )
            if covered:
                return {"written": False}
            record = {
                "permanent_friend": True,
                "violations": len(active),
                "violation_ids": active,
                "at": now.isoformat(),
            }
            path = c.home / LOCK_FILE
            if not path.exists() and not (c.life / RESTRICTIONS_FILE).exists():
                atomic_write(path, json.dumps(record) + "\n")
            else:
                record.update(
                    kind="persisted_relationship_restriction",
                    id=_digest([current["revision"], record])[:24],
                )
                with (c.life / RESTRICTIONS_FILE).open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            return {"written": True, "restriction": record}


def restriction_state(c, now=None):
    """Read-only decision used by intimacy; current violations are also enforced there."""
    if not (c.home / LOCK_FILE).exists() and not (c.life / RESTRICTIONS_FILE).exists():
        return {"present": False, "effective": False, "status": "absent"}
    return _snapshot(c, _now(now))["restriction"]


def report(c, now=None):
    """Explain recorded inputs; never infer consent, personality or provider behavior."""
    import companion_intimacy as intimacy

    now = _now(now)
    result = _snapshot(c, now)
    result["version"] = 1
    result["configuration"]["romantic_progression"] = intimacy.is_romantic(c)
    try:
        state = intimacy.compute(c, now)
        result["derived"] = {
            "stage": state["stage"],
            "stage_name": state["stage_name"],
            "score": state["score"],
            "trust": state["meters"].get("trust"),
            "hurt": state["meters"].get("hurt"),
            "intimacy_ready": state["intimacy_ready"],
            "blockers": state["intimacy_blockers"],
            "active_violation_count": state["violations_count"],
        }
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result["derived"] = {
            "stage": None,
            "stage_name": None,
            "score": None,
            "trust": None,
            "hurt": None,
            "intimacy_ready": False,
            "blockers": ["Relationship state could not be computed: " + str(exc)[:200]],
            "active_violation_count": result["active_violation_count"],
        }
        result["restriction"]["eligible"] = False
        result["warnings"].append("Derived relationship state needs inspection.")
    result["stance"] = {
        "assessed": False,
        "note": "These diagnostics explain configuration and recorded gates only. Authored identity, standing instructions, memories and model/provider rules can separately affect a reply; none is interpreted here. An open gate does not establish willingness. Reviewing a mistaken restriction does not change her stance, adult settings or provider limits.",
    }
    return result


def review(c, *, revision, reason, now=None):
    """Retire only a demonstrably corrected restriction, preserving every original."""
    now = _now(now)
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 1000:
        raise ValueError("Give a review reason of 1 to 1000 characters")
    if not isinstance(revision, str) or not revision:
        raise ValueError("A report revision is required")
    with file_lock(c.life / ".feelings.lock"):
        with file_lock(c.home / ".relationship-review.lock"):
            current = report(c, now)
            if revision != current["revision"]:
                raise StaleReviewError(
                    "Relationship evidence changed; open a fresh report before reviewing"
                )
            restriction = current["restriction"]
            if not restriction["eligible"]:
                raise ValueError(restriction["reason"])
            row = {
                "id": _digest([revision, reason.strip(), now.isoformat()])[:24],
                "kind": "retire_corrected_restriction",
                "at": now.isoformat(),
                "reason": reason.strip(),
                "report_revision": revision,
                "lock_revision": restriction["lock_revision"],
                "incident_revision": current["incident_revision"],
                "source_revision": current["source_revision"],
                "source_ids": restriction["source_ids"],
                "incidents": restriction["incidents"],
                "active_incident_ids": [
                    r["id"] for r in current["incidents"] if r["status"] == "active"
                ],
            }
            with (c.life / REVIEWS_FILE).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"written": True, "review": row, "report": report(c, now)}
