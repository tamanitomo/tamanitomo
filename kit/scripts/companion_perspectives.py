#!/usr/bin/env python3
"""Traceable encounters, interpretations, perspectives and investigations.

This module is deliberately a ledger adapter, not a second transcript or artifact
archive.  Encounter rows point at profile-local sources that already exist.  An
interpretation says what the companion made of one or more encounters.  A
perspective is an append-only revision chain whose current state is derived here.

``self-development.jsonl`` schema version 1

* ``encounter``: stable source type/id, occurrence time, locator, evidential
  boundary, lineage id and availability.
* ``encounter_support``: a correction or availability change; the origin stays.
* ``interpretation``: authored reaction/inference/question linked to encounters.
* ``perspective_revision``: stable perspective/revision ids, subject, position,
  reasons, qualitative uncertainty, source/interpretation refs, prior revision
  and explicit change reason.
* ``investigation`` / ``investigation_update``: a human question, independent
  inquiry, or exploration through making, with a next step and honest result or
  obstacle.

All writes use operation ids and validate against the current fold while holding
the ledger lock.  Retrying a partially applied batch is therefore safe.  A bad
line is reported as malformed rather than treated as an empty personality.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import file_lock

SCHEMA_VERSION = 1
LEDGER = "self-development.jsonl"
SOURCE_TYPES = (
    "human_words",
    "human_report",
    "shared_activity",
    "supplied_checkpoint",
    "tool_evidence",
    "artifact",
    "fictional_episode",
    "fictional_scene",
    "fictional_person",
    "fictional_project",
    "media_metadata",
)
OBSERVATION_KINDS = (
    "actual_words",
    "reported_claim",
    "recorded_participation",
    "returned_tool_result",
    "created_artifact",
    "authored_fiction",
    "catalog_only",
)
SUPPORT_STATES = ("available", "corrected", "unavailable")
UNCERTAINTIES = ("provisional", "uncertain", "mixed", "settled", "unknown")
CHANGES = ("new", "nuance", "supersede", "withdraw", "tension", "unchanged")
INVESTIGATION_MODES = ("human", "independent", "making")
INVESTIGATION_STATUSES = ("open", "paused", "blocked", "resolved", "dropped")
RESULT_TYPES = ("thought", "tool_evidence", "artifact", "fictional")
MAX_ACTIVE_INVESTIGATIONS = 3


class LedgerError(ValueError):
    """The ledger exists but cannot safely be folded."""


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def _now(c, value=None):
    value = value or dt.datetime.now(_tz(c))
    if value.tzinfo is None:
        raise ValueError("timezone required")
    return value.astimezone(_tz(c))


def _profile(c):
    return c.profile or "root"


def path_for(c):
    return pathlib.Path(c.life) / LEDGER


def _text(value, limit, label, required=True):
    value = str(value or "").strip()
    if required and not value:
        raise ValueError(f"{label} is required")
    if len(value) > limit:
        raise ValueError(f"{label} must be at most {limit} characters")
    return value


def _list(value, limit, item_limit, label):
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) or len(value) > limit:
        raise ValueError(f"{label} must be a list of at most {limit} items")
    return [_text(item, item_limit, label) for item in value]


def _stamp(value, label="time"):
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        try:
            parsed = dt.datetime.fromisoformat(str(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.isoformat()


def _id(prefix, *parts):
    return (
        prefix
        + "-"
        + hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16]
    )


def _semantic_hash(row):
    body = {k: v for k, v in row.items() if k not in ("recorded_at", "id")}
    return hashlib.sha256(
        json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def read_ledger(c):
    """Return rows and explicit health; never turn damage into an empty ledger."""
    path = path_for(c)
    if not path.exists():
        return {"status": "empty", "rows": [], "errors": [], "path": str(path)}
    rows, errors = [], []
    try:
        with path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("row is not an object")
                    if row.get("schema") != SCHEMA_VERSION:
                        raise ValueError("unsupported or missing schema version")
                    if not row.get("kind") or not row.get("operation_id"):
                        raise ValueError("missing kind or operation_id")
                    rows.append(row)
                except (ValueError, TypeError) as exc:
                    errors.append({"line": number, "error": str(exc)})
    except OSError as exc:
        return {
            "status": "unreadable",
            "rows": [],
            "errors": [{"error": str(exc)}],
            "path": str(path),
        }
    if not errors:
        errors.extend(_semantic_errors(rows, _profile(c)))
    return {
        "status": "malformed" if errors else "ok",
        "rows": rows,
        "errors": errors,
        "path": str(path),
    }


def _semantic_errors(rows, profile):
    """Validate references and revision chains during every authoritative read."""
    errors = []
    encounters_seen = set()
    interpretations_seen = set()
    perspectives_seen = {}
    investigations_seen = set()
    operations = set()
    for index, row in enumerate(rows, 1):
        kind = row.get("kind")
        operation = row.get("operation_id")
        if row.get("profile") != profile:
            errors.append({"line": index, "error": "cross-profile row"})
            continue
        if operation in operations:
            errors.append({"line": index, "error": "duplicate operation_id"})
        operations.add(operation)
        if kind == "encounter":
            encounters_seen.add(row.get("id"))
        elif kind == "encounter_support":
            if row.get("encounter_id") not in encounters_seen:
                errors.append(
                    {"line": index, "error": "unknown encounter support target"}
                )
        elif kind == "interpretation":
            if (
                not row.get("encounter_ids")
                or set(row["encounter_ids"]) - encounters_seen
            ):
                errors.append(
                    {"line": index, "error": "unknown interpretation encounter"}
                )
            interpretations_seen.add(row.get("id"))
        elif kind == "perspective_revision":
            ident = row.get("perspective_id")
            prior = row.get("prior_revision", "")
            current = perspectives_seen.get(ident)
            if row.get("change") == "new":
                if current or prior:
                    errors.append(
                        {"line": index, "error": "invalid new perspective chain"}
                    )
            elif not current or prior != current:
                errors.append(
                    {"line": index, "error": "invalid perspective revision chain"}
                )
            if set(row.get("interpretation_ids", [])) - interpretations_seen:
                errors.append(
                    {"line": index, "error": "unknown perspective interpretation"}
                )
            if set(row.get("source_ids", [])) - encounters_seen:
                errors.append({"line": index, "error": "unknown perspective source"})
            perspectives_seen[ident] = row.get("revision_id")
        elif kind == "investigation":
            if set(row.get("perspective_ids", [])) - set(perspectives_seen):
                errors.append(
                    {"line": index, "error": "unknown investigation perspective"}
                )
            if set(row.get("source_ids", [])) - encounters_seen:
                errors.append({"line": index, "error": "unknown investigation source"})
            investigations_seen.add(row.get("investigation_id"))
        elif kind == "investigation_update":
            if row.get("investigation_id") not in investigations_seen:
                errors.append(
                    {"line": index, "error": "unknown investigation update target"}
                )
            if set(row.get("source_ids", [])) - encounters_seen:
                errors.append(
                    {"line": index, "error": "unknown investigation result source"}
                )
        else:
            errors.append({"line": index, "error": f"unknown row kind {kind!r}"})
    return errors


def _healthy(c):
    state = read_ledger(c)
    if state["status"] in ("malformed", "unreadable"):
        detail = "; ".join(
            f"line {e.get('line', '?')}: {e['error']}" for e in state["errors"][:3]
        )
        raise LedgerError(f"self-development ledger is {state['status']}: {detail}")
    return state["rows"]


def _append_locked(c, row, validate):
    """Validate and append under one lock, with operation-level retry safety."""
    path = path_for(c)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"schema": SCHEMA_VERSION, "profile": _profile(c), **row}
    row["operation_hash"] = _semantic_hash(row)
    with file_lock(path.parent / ("." + path.name + ".lock")):
        rows = _healthy(c)
        for old in rows:
            if old.get("operation_id") != row["operation_id"]:
                continue
            if old.get("operation_hash") != row["operation_hash"]:
                raise ValueError(
                    "operation_id already exists with different content; original retained"
                )
            return {"written": False, "entry": old, "resumed": True}
        refused = validate(rows)
        if refused:
            return refused
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return {"written": True, "entry": row, "resumed": False}


def _operation(value, prefix, *parts):
    return _text(value, 160, "operation_id", required=False) or _id(prefix, *parts)


def _encounters_from(rows):
    found = {}
    for row in rows:
        if row.get("kind") == "encounter":
            found.setdefault(row["id"], dict(row))
        elif (
            row.get("kind") == "encounter_support" and row.get("encounter_id") in found
        ):
            item = found[row["encounter_id"]]
            item["support_status"] = row["support_status"]
            item["support_reason"] = row["reason"]
            item["support_updated_at"] = row["recorded_at"]
    return found


def encounters(c):
    rows = _healthy(c)
    return list(_encounters_from(rows).values())


def record_encounter(
    c,
    source_type,
    source_id,
    occurred_at,
    locator,
    summary,
    observed_as,
    *,
    lineage_id="",
    support_status="available",
    operation_id="",
    now=None,
):
    """Point at an encounter without copying its transcript/artifact archive."""
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {SOURCE_TYPES}")
    if observed_as not in OBSERVATION_KINDS:
        raise ValueError(f"observed_as must be one of {OBSERVATION_KINDS}")
    if support_status not in SUPPORT_STATES:
        raise ValueError(f"support_status must be one of {SUPPORT_STATES}")
    source_id = _text(source_id, 240, "source_id")
    occurred_at = _stamp(occurred_at, "occurred_at")
    locator = _text(locator, 600, "locator")
    summary = _text(summary, 800, "summary")
    lineage_id = _text(lineage_id, 240, "lineage_id", required=False) or _id(
        "origin", _profile(c), source_type, source_id
    )
    ident = _id("enc", _profile(c), source_type, source_id)
    operation_id = _operation(operation_id, "op-enc", ident)
    row = {
        "id": ident,
        "kind": "encounter",
        "operation_id": operation_id,
        "source_type": source_type,
        "source_id": source_id,
        "occurred_at": occurred_at,
        "locator": locator,
        "summary": summary,
        "observed_as": observed_as,
        "lineage_id": lineage_id,
        "support_status": support_status,
        "recorded_at": _now(c, now).isoformat(),
    }

    def validate(rows):
        existing = _encounters_from(rows).get(ident)
        if existing:
            # A second synopsis or retry remains one evidential origin.  Metadata is
            # not silently rewritten; support corrections have their own operation.
            return {
                "written": False,
                "entry": existing,
                "resumed": False,
                "reason": "encounter source already has one evidential origin",
            }

    out = _append_locked(c, row, validate)
    if out["written"]:
        return out
    return out


def update_support(c, encounter_id, support_status, reason, operation_id="", now=None):
    if support_status not in SUPPORT_STATES:
        raise ValueError(f"support_status must be one of {SUPPORT_STATES}")
    encounter_id = _text(encounter_id, 80, "encounter_id")
    reason = _text(reason, 500, "reason")
    operation_id = _operation(
        operation_id, "op-support", encounter_id, support_status, reason
    )
    row = {
        "id": _id("support", operation_id),
        "kind": "encounter_support",
        "operation_id": operation_id,
        "encounter_id": encounter_id,
        "support_status": support_status,
        "reason": reason,
        "recorded_at": _now(c, now).isoformat(),
    }

    def validate(rows):
        if encounter_id not in _encounters_from(rows):
            raise ValueError("unknown or cross-profile encounter_id")

    return _append_locked(c, row, validate)


def interpretations(c):
    return [r for r in _healthy(c) if r.get("kind") == "interpretation"]


def record_interpretation(
    c,
    encounter_ids,
    text,
    *,
    interested="",
    inference="",
    unresolved_question="",
    feeling="",
    implication="",
    operation_id="",
    now=None,
):
    encounter_ids = _list(encounter_ids, 8, 80, "encounter_ids")
    if not encounter_ids:
        raise ValueError("at least one encounter_id is required")
    fields = {
        "text": _text(text, 1000, "interpretation"),
        "interested": _text(interested, 500, "interested", required=False),
        "inference": _text(inference, 500, "inference", required=False),
        "unresolved_question": _text(
            unresolved_question, 500, "unresolved_question", required=False
        ),
        "feeling": _text(feeling, 500, "feeling", required=False),
        "implication": _text(implication, 500, "implication", required=False),
    }
    operation_id = _operation(
        operation_id,
        "op-int",
        *sorted(encounter_ids),
        *fields.values(),
    )
    known_before = {item["id"]: item for item in encounters(c)}
    missing_before = [ident for ident in encounter_ids if ident not in known_before]
    if missing_before:
        raise ValueError(
            "unknown or cross-profile encounter_id: " + ", ".join(missing_before)
        )
    row = {
        "id": _id("int", operation_id),
        "kind": "interpretation",
        "operation_id": operation_id,
        "encounter_ids": encounter_ids,
        "lineage_ids": sorted(
            {known_before[ident]["lineage_id"] for ident in encounter_ids}
        ),
        **fields,
        "recorded_at": _now(c, now).isoformat(),
    }

    def validate(rows):
        known = _encounters_from(rows)
        missing = [ident for ident in encounter_ids if ident not in known]
        if missing:
            raise ValueError(
                "unknown or cross-profile encounter_id: " + ", ".join(missing)
            )

    out = _append_locked(c, row, validate)
    # validate mutates the written row with lineage ids.  A resumed row already
    # carries the original lineage and is returned unchanged.
    return out


def _perspective_history_from(rows):
    histories = {}
    for row in rows:
        if row.get("kind") != "perspective_revision":
            continue
        histories.setdefault(row["perspective_id"], []).append(dict(row))
    return histories


def perspective_history(c, perspective_id=""):
    histories = _perspective_history_from(_healthy(c))
    if perspective_id:
        return histories.get(perspective_id, [])
    return histories


def _current_from(rows):
    histories = _perspective_history_from(rows)
    current = []
    for ident, revisions in histories.items():
        latest = revisions[-1]
        if latest["change"] != "withdraw":
            current.append(latest)
    return current


def current_perspectives(c):
    return _current_from(_healthy(c))


def record_perspective(
    c,
    subject,
    position,
    reasons,
    uncertainty,
    *,
    interpretation_ids=(),
    source_ids=(),
    perspective_id="",
    prior_revision="",
    change="new",
    revision_reason="",
    operation_id="",
    now=None,
):
    subject = _text(subject, 160, "subject")
    position = _text(position, 1000, "position")
    reasons = _list(reasons, 6, 500, "reasons")
    if not reasons:
        raise ValueError("at least one authored reason is required")
    if uncertainty not in UNCERTAINTIES:
        raise ValueError(f"uncertainty must be one of {UNCERTAINTIES}")
    if change not in CHANGES:
        raise ValueError(f"change must be one of {CHANGES}")
    interpretation_ids = _list(interpretation_ids, 8, 80, "interpretation_ids")
    source_ids = _list(source_ids, 8, 80, "source_ids")
    perspective_id = _text(perspective_id, 80, "perspective_id", required=False) or _id(
        "view", _profile(c), subject.casefold()
    )
    prior_revision = _text(prior_revision, 80, "prior_revision", required=False)
    revision_reason = _text(revision_reason, 600, "revision_reason", required=False)
    if change == "new" and (prior_revision or revision_reason):
        raise ValueError("a new perspective cannot name a prior revision")
    if change != "new" and (not prior_revision or not revision_reason):
        raise ValueError("a revision requires prior_revision and revision_reason")
    operation_id = _operation(
        operation_id,
        "op-view",
        perspective_id,
        prior_revision,
        change,
        position,
    )
    row = {
        "id": _id("rev", operation_id),
        "kind": "perspective_revision",
        "operation_id": operation_id,
        "perspective_id": perspective_id,
        "revision_id": _id("rev", operation_id),
        "subject": subject,
        "position": position,
        "reasons": reasons,
        "uncertainty": uncertainty,
        "interpretation_ids": interpretation_ids,
        "source_ids": source_ids,
        "prior_revision": prior_revision,
        "change": change,
        "revision_reason": revision_reason,
        "recorded_at": _now(c, now).isoformat(),
    }

    def validate(rows):
        histories = _perspective_history_from(rows)
        history = histories.get(perspective_id, [])
        if change == "new":
            if history:
                raise ValueError(
                    "perspective already exists; revise its current revision explicitly"
                )
        else:
            if not history:
                raise ValueError("unknown or cross-profile perspective_id")
            if history[-1]["revision_id"] != prior_revision:
                raise ValueError(
                    "stale prior_revision; current perspective was not changed"
                )
        known_interpretations = {
            r["id"] for r in rows if r.get("kind") == "interpretation"
        }
        if set(interpretation_ids) - known_interpretations:
            raise ValueError("unknown or cross-profile interpretation_id")
        known_sources = set(_encounters_from(rows))
        if set(source_ids) - known_sources:
            raise ValueError("unknown or cross-profile source_id")

    return _append_locked(c, row, validate)


def _legacy_preferences(c):
    """Old authored rows as views with unknown source links, without rewriting."""
    path = pathlib.Path(c.life) / "preferences.jsonl"
    if not path.exists():
        return {"status": "empty", "rows": [], "errors": []}
    rows, errors = [], []
    try:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                if raw.get("kind") != "companion_preference":
                    continue
                rows.append(
                    {
                        "perspective_id": raw.get("id") or _id("legacy", number),
                        "revision_id": raw.get("id") or _id("legacy", number),
                        "subject": str(
                            raw.get("subject") or raw.get("text") or ""
                        ).strip(),
                        "position": str(raw.get("text") or "").strip(),
                        "reasons": [],
                        "uncertainty": "unknown",
                        "source_ids": [],
                        "interpretation_ids": [],
                        "recorded_at": raw.get("recorded_at", ""),
                        "change": "legacy",
                        "revision_reason": "",
                        "legacy": True,
                        "valence": raw.get("valence", "mixed"),
                    }
                )
            except (ValueError, TypeError, AttributeError) as exc:
                errors.append({"line": number, "error": str(exc)})
    except OSError as exc:
        return {"status": "unreadable", "rows": [], "errors": [{"error": str(exc)}]}
    return {"status": "malformed" if errors else "ok", "rows": rows, "errors": errors}


def _words(text):
    return set(re.findall(r"[\w'-]{3,}", (text or "").casefold()))


def investigations(c, status=None):
    rows = _healthy(c)
    found = {}
    for row in rows:
        ident = row.get("investigation_id")
        if row.get("kind") == "investigation":
            found.setdefault(ident, dict(row))
        elif row.get("kind") == "investigation_update" and ident in found:
            item = found[ident]
            for key in (
                "status",
                "next_step",
                "obstacle",
                "result",
                "result_type",
                "source_ids",
                "artifact_refs",
                "due_at",
            ):
                if key in row:
                    item[key] = row[key]
            item["updated_at"] = row["recorded_at"]
    result = sorted(
        found.values(), key=lambda item: item.get("updated_at") or item["recorded_at"]
    )
    return [item for item in result if item["status"] == status] if status else result


def start_investigation(
    c,
    question,
    mode,
    reason,
    next_step,
    *,
    perspective_ids=(),
    source_ids=(),
    due_at="",
    operation_id="",
    now=None,
):
    if mode not in INVESTIGATION_MODES:
        raise ValueError(f"mode must be one of {INVESTIGATION_MODES}")
    question = _text(question, 500, "question")
    reason = _text(reason, 600, "reason")
    next_step = _text(next_step, 600, "next_step")
    perspective_ids = _list(perspective_ids, 6, 80, "perspective_ids")
    source_ids = _list(source_ids, 6, 80, "source_ids")
    due_at = _stamp(due_at, "due_at") if due_at else ""
    operation_id = _operation(operation_id, "op-inv", mode, question.casefold())
    ident = _id("investigation", _profile(c), mode, question.casefold())
    row = {
        "id": _id("invrow", operation_id),
        "kind": "investigation",
        "operation_id": operation_id,
        "investigation_id": ident,
        "question": question,
        "mode": mode,
        "reason": reason,
        "next_step": next_step,
        "perspective_ids": perspective_ids,
        "source_ids": source_ids,
        "due_at": due_at,
        "status": "open",
        "obstacle": "",
        "result": "",
        "result_type": "",
        "artifact_refs": [],
        "recorded_at": _now(c, now).isoformat(),
    }

    def validate(rows):
        open_rows = [
            item
            for item in _investigations_from(rows)
            if item["status"] in ("open", "paused", "blocked")
        ]
        if len(open_rows) >= MAX_ACTIVE_INVESTIGATIONS:
            raise ValueError(
                "too many active investigations; resolve, pause or drop one"
            )
        if any(item["investigation_id"] == ident for item in open_rows):
            raise ValueError("that investigation is already active")
        current_ids = {item["perspective_id"] for item in _current_from(rows)}
        if set(perspective_ids) - current_ids:
            raise ValueError("unknown or cross-profile perspective_id")
        if set(source_ids) - set(_encounters_from(rows)):
            raise ValueError("unknown or cross-profile source_id")

    return _append_locked(c, row, validate)


def _investigations_from(rows):
    # Same fold as investigations(), but usable while the ledger lock is held.
    found = {}
    for row in rows:
        ident = row.get("investigation_id")
        if row.get("kind") == "investigation":
            found.setdefault(ident, dict(row))
        elif row.get("kind") == "investigation_update" and ident in found:
            for key in (
                "status",
                "next_step",
                "obstacle",
                "result",
                "result_type",
                "source_ids",
                "artifact_refs",
                "due_at",
            ):
                if key in row:
                    found[ident][key] = row[key]
            found[ident]["updated_at"] = row["recorded_at"]
    return list(found.values())


def _workspace_roots(c):
    roots = []
    for label, value in (("home", c.home), ("data", c.data)):
        root = pathlib.Path(value).resolve()
        if not any(root == existing[1] for existing in roots):
            roots.append((label, root))
    return roots


def artifact_reference(c, value, require_exists=True):
    """Return a profile-local artifact reference; reject traversal/symlink escape."""
    path = pathlib.Path(value)
    if not path.is_absolute():
        raise ValueError("artifact path must be absolute")
    try:
        resolved = path.resolve(strict=require_exists)
    except OSError as exc:
        raise ValueError("artifact does not exist") from exc
    for label, root in _workspace_roots(c):
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            continue
        if require_exists and not resolved.is_file():
            raise ValueError("artifact must be an existing file")
        return {
            "workspace": label,
            "path": relative.as_posix(),
            "available": resolved.is_file(),
        }
    raise ValueError("artifact path escapes this profile's workspace")


def resolve_artifact(c, reference):
    roots = dict(_workspace_roots(c))
    root = roots.get(reference.get("workspace"))
    if not root:
        return {**reference, "available": False, "reason": "unknown workspace"}
    candidate = (root / str(reference.get("path", ""))).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError:
        return {**reference, "available": False, "reason": "path escaped workspace"}
    return {
        **reference,
        "available": candidate.is_file(),
        "absolute_path": str(candidate),
        **({"reason": "artifact is missing"} if not candidate.is_file() else {}),
    }


def update_investigation(
    c,
    investigation_id,
    status,
    *,
    next_step="",
    obstacle="",
    result="",
    result_type="",
    source_ids=(),
    artifact_paths=(),
    due_at="",
    operation_id="",
    now=None,
):
    if status not in INVESTIGATION_STATUSES:
        raise ValueError(f"status must be one of {INVESTIGATION_STATUSES}")
    investigation_id = _text(investigation_id, 80, "investigation_id")
    next_step = _text(next_step, 600, "next_step", required=False)
    obstacle = _text(obstacle, 600, "obstacle", required=False)
    result = _text(result, 1000, "result", required=False)
    source_ids = _list(source_ids, 8, 80, "source_ids")
    artifact_refs = [artifact_reference(c, path) for path in artifact_paths]
    due_at = _stamp(due_at, "due_at") if due_at else ""
    if result_type and result_type not in RESULT_TYPES:
        raise ValueError(f"result_type must be one of {RESULT_TYPES}")
    if status == "blocked" and not obstacle:
        raise ValueError("a blocked investigation needs an obstacle")
    if status == "resolved" and not (result or artifact_refs):
        raise ValueError("a resolved investigation needs a durable result")
    if result_type == "artifact" and not artifact_refs:
        raise ValueError("an artifact result needs an existing profile-local artifact")
    operation_id = _operation(
        operation_id, "op-inv-update", investigation_id, status, result, obstacle
    )
    row = {
        "id": _id("invupdate", operation_id),
        "kind": "investigation_update",
        "operation_id": operation_id,
        "investigation_id": investigation_id,
        "status": status,
        "next_step": next_step,
        "obstacle": obstacle,
        "result": result,
        "result_type": result_type,
        "source_ids": source_ids,
        "artifact_refs": artifact_refs,
        "due_at": due_at,
        "recorded_at": _now(c, now).isoformat(),
    }

    def validate(rows):
        current = next(
            (
                i
                for i in _investigations_from(rows)
                if i["investigation_id"] == investigation_id
            ),
            None,
        )
        if not current:
            raise ValueError("unknown or cross-profile investigation_id")
        known = _encounters_from(rows)
        if set(source_ids) - set(known):
            raise ValueError("unknown or cross-profile source_id")
        if result_type == "tool_evidence" and not any(
            known[s]["source_type"] == "tool_evidence"
            and known[s].get("support_status") == "available"
            for s in source_ids
        ):
            raise ValueError(
                "tool_evidence result needs available returned tool evidence"
            )

    return _append_locked(c, row, validate)


def snapshot(c, query="", budget=2400, now=None, limit=8):
    """The one deterministic current-view selector used by every consumer."""
    state = read_ledger(c)
    legacy = _legacy_preferences(c)
    if state["status"] in ("malformed", "unreadable") or legacy["status"] in (
        "malformed",
        "unreadable",
    ):
        return {
            "status": "unavailable",
            "current": [],
            "omitted": 0,
            "errors": state["errors"] + legacy["errors"],
        }
    rows = state["rows"]
    current = _current_from(rows) + legacy["rows"]
    now = _now(c, now)
    query_words = _words(query)
    open_work = [
        item
        for item in _investigations_from(rows)
        if item["status"] in ("open", "paused", "blocked")
    ]
    linked = {pid for item in open_work for pid in item.get("perspective_ids", [])}
    # Project relevance is optional and imported lazily to avoid a module cycle.
    try:
        import companion_arcs

        projects = companion_arcs.active(c)
        linked.update(
            pid for project in projects for pid in project.get("perspective_ids", [])
        )
        project_words = _words(
            " ".join(
                p.get("title", "") + " " + p.get("next_action", "") for p in projects
            )
        )
    except (ImportError, OSError, ValueError, LedgerError):
        project_words = set()
    terms = query_words | project_words

    def score(item):
        words = _words(
            " ".join(
                [item.get("subject", ""), item.get("position", "")]
                + list(item.get("reasons", []))
            )
        )
        relevant = len(words & terms)
        linked_score = 1 if item["perspective_id"] in linked else 0
        return (
            relevant,
            linked_score,
            item.get("recorded_at", ""),
            item["perspective_id"],
        )

    ordered = sorted(current, key=score, reverse=True)
    selected, used = [], 0
    if budget <= 0 or limit <= 0:
        return {
            "status": "ok" if (rows or legacy["rows"]) else "empty",
            "current": [],
            "omitted": len(current),
            "total": len(current),
            "errors": [],
        }
    for item in ordered:
        size = len(item.get("position", "")) + len(item.get("subject", "")) + 180
        if selected and (len(selected) >= limit or used + size > budget):
            continue
        selected.append(item)
        used += size
    return {
        "status": "ok" if (rows or legacy["rows"]) else "empty",
        "current": selected,
        "omitted": len(current) - len(selected),
        "total": len(current),
        "errors": [],
    }


def render_current(c, query="", budget=2400, now=None, limit=8):
    selected = snapshot(c, query, budget, now, limit)
    if selected["status"] == "unavailable":
        return "[Current perspectives unavailable; the ledger is not empty and needs repair.]"
    lines = []
    encounter_index = {e["id"]: e for e in encounters(c)} if selected["current"] else {}
    for item in selected["current"]:
        reasons = (
            "; ".join(item.get("reasons", [])[:2])
            or "legacy authored preference; source links unknown"
        )
        support = sorted(
            {
                encounter_index[s].get("support_status", "available")
                for s in item.get("source_ids", [])
                if s in encounter_index
            }
        )
        marker = "legacy" if item.get("legacy") else item.get("uncertainty", "unknown")
        if support and support != ["available"]:
            marker += "; support " + "/".join(support)
        lines.append(
            f"- {item['subject']} [perspective={item['perspective_id']} revision={item['revision_id']}; {marker}]: "
            f"{item['position']} — {reasons}"
        )
    if selected.get("omitted"):
        lines.append(
            f"[+{selected['omitted']} current views omitted here; inspect with companion_perspectives.py show]"
        )
    return "\n".join(lines)


def render_investigations(c, now=None, limit=3):
    now = _now(c, now)
    rows = [
        item
        for item in investigations(c)
        if item["status"] in ("open", "paused", "blocked")
    ][-limit:]
    lines = []
    for item in rows:
        due = ""
        if item.get("due_at"):
            try:
                due = " due" if dt.datetime.fromisoformat(item["due_at"]) <= now else ""
            except ValueError:
                due = ""
        line = (
            f"- {item['question']} [investigation={item['investigation_id']}; {item['mode']}; "
            f"{item['status']}{due}] Why: {item['reason']} Next: {item.get('next_step') or 'leave open'}"
        )
        if item.get("obstacle"):
            line += " Obstacle: " + item["obstacle"]
        lines.append(line)
    return "\n".join(lines)


def fingerprint(c, now=None):
    """Stable meaningful state plus due edges; no continuously moving clock."""
    now = _now(c, now)
    state = read_ledger(c)
    if state["status"] in ("malformed", "unreadable"):
        return "unavailable:" + state["status"]
    current = _current_from(state["rows"])
    inv = _investigations_from(state["rows"])
    marks = [
        (p["perspective_id"], p["revision_id"], p["change"])
        for p in sorted(current, key=lambda p: p["perspective_id"])
    ]
    for item in sorted(inv, key=lambda i: i["investigation_id"]):
        due = False
        if item.get("due_at"):
            try:
                due = dt.datetime.fromisoformat(item["due_at"]) <= now
            except ValueError:
                pass
        marks.append(
            (
                item["investigation_id"],
                item["status"],
                item.get("next_step", ""),
                item.get("obstacle", ""),
                item.get("result", ""),
                due,
            )
        )
    return hashlib.sha256(repr(marks).encode()).hexdigest()[:16]


def inspection(c):
    state = read_ledger(c)
    legacy = _legacy_preferences(c)
    if state["status"] in ("malformed", "unreadable"):
        return {
            "status": state["status"],
            "errors": state["errors"],
            "current": [],
            "history": {},
            "encounters": [],
            "interpretations": [],
            "investigations": [],
        }
    rows = state["rows"]
    history = _perspective_history_from(rows)
    current = _current_from(rows) + legacy["rows"]
    return {
        "status": "malformed" if legacy["status"] == "malformed" else state["status"],
        "errors": state["errors"] + legacy["errors"],
        "current": current,
        "history": history,
        "encounters": list(_encounters_from(rows).values()),
        "interpretations": [r for r in rows if r.get("kind") == "interpretation"],
        "investigations": _investigations_from(rows),
    }


def _json_file(path):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("input file must hold one JSON object")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=pathlib.Path)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, help_text in (
        ("encounter", "record a stable reference to an encounter"),
        ("interpret", "record an interpretation of encounters"),
        ("perspective", "record or explicitly revise a perspective"),
        ("investigate", "start an independent, making, or human inquiry"),
        ("investigation-update", "record progress, an obstacle, or a result"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--file", type=pathlib.Path, required=True)
    support = sub.add_parser(
        "support", help="mark encounter support corrected/unavailable"
    )
    support.add_argument("--id", required=True)
    support.add_argument("--status", required=True, choices=SUPPORT_STATES)
    support.add_argument("--reason", required=True)
    show = sub.add_parser("show", help="inspect current views separately from history")
    show.add_argument("--perspective", default="")
    args = parser.parse_args()
    c = cc.load(args.home)
    now = _now(c)
    if args.cmd == "encounter":
        data = _json_file(args.file)
        out = record_encounter(c, now=now, **data)
    elif args.cmd == "interpret":
        data = _json_file(args.file)
        out = record_interpretation(c, now=now, **data)
    elif args.cmd == "perspective":
        data = _json_file(args.file)
        out = record_perspective(c, now=now, **data)
    elif args.cmd == "investigate":
        data = _json_file(args.file)
        out = start_investigation(c, now=now, **data)
    elif args.cmd == "investigation-update":
        data = _json_file(args.file)
        out = update_investigation(c, now=now, **data)
    elif args.cmd == "support":
        out = update_support(c, args.id, args.status, args.reason, now=now)
    else:
        out = inspection(c)
        if args.perspective:
            out = {
                "status": out["status"],
                "current": [
                    p for p in out["current"] if p["perspective_id"] == args.perspective
                ],
                "history": out["history"].get(args.perspective, []),
            }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
