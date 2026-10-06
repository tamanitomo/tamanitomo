#!/usr/bin/env python3
"""What she has said about her own past, kept so it stays true.

A companion who tells you about her childhood in March and gives a different
one in June has not revealed anything; she has forgotten. Her history is hers to
invent, and the moment she tells it, it is fixed. This is the ledger of what she
has said: a sister's name, the town she grew up in, the job she quit.

Append-only. Telling something new about a topic she has already covered is
refused until she says what it is: a revision (`--supersedes ID`, which keeps
the old statement in the history) or an addition (`--also`). The conflict is
shown to her rather than quietly merged or overwritten.

This is her fiction, not a fact about the human, and it is stored apart from
the facts ledger on purpose. Nothing here ever becomes a claim about the human.
"""

from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
import companion_self as slf


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def path_for(c):
    return c.life / "canon.jsonl"


def _text(value, limit, label, required=True):
    value = (value or "").strip()
    if required and not value:
        raise ValueError(f"{label} required")
    if len(value) > limit:
        raise ValueError(f"{label} must be at most {limit} characters")
    return value


def canon(c, status="active"):
    """Fold updates onto originals. Superseded statements stay readable."""
    latest = {}
    for row in slf._read(path_for(c)):
        ident = row.get("id")
        if row.get("kind") == "canon":
            latest.setdefault(ident, dict(row))
        elif row.get("kind") == "canon_update" and ident in latest:
            latest[ident]["status"] = row.get("status", latest[ident]["status"])
            latest[ident]["superseded_by"] = row.get("superseded_by", "")
    rows = sorted(latest.values(), key=lambda r: r["recorded_at"])
    return [r for r in rows if r["status"] == status] if status else rows


def add(c, entry, now):
    topic = _text(entry.get("topic"), 60, "topic")
    statement = _text(entry.get("statement"), 400, "statement")
    key = topic.lower()
    supersedes = _text(entry.get("supersedes"), 80, "supersedes", required=False)
    also = bool(entry.get("also"))
    if supersedes and also:
        raise ValueError(
            "a statement either revises an earlier one or adds to it, not both"
        )
    row = {
        "id": "canon-"
        + hashlib.sha256(f"{key}|{statement.lower()}".encode()).hexdigest()[:16],
        "kind": "canon",
        "topic": topic,
        "statement": statement,
        "told_on": _text(entry.get("told_on"), 20, "told_on", required=False)
        or now.date().isoformat(),
        "evidence": _text(entry.get("evidence"), 300, "evidence", required=False),
        "status": "active",
        "recorded_at": now.isoformat(),
    }
    active = canon(c)
    same_topic = [r for r in active if r["topic"].lower() == key]
    target = None
    if supersedes:
        target = next((r for r in same_topic if r["id"] == supersedes), None)
        if not target:
            raise ValueError(
                "supersedes must be the id of an active statement on this topic"
            )
        if target["id"] == row["id"]:
            raise ValueError(
                "that is the statement already recorded; nothing to revise"
            )

    def guard():
        if same_topic and not also and not target:
            return {
                "written": False,
                "conflict": [
                    {
                        "id": r["id"],
                        "statement": r["statement"],
                        "told_on": r["told_on"],
                    }
                    for r in same_topic
                ],
                "reason": (
                    f"You have already said something about {topic!r}. If this changes what you "
                    "said, add --supersedes with that id; if it adds to it, add --also. "
                    "Nothing was written."
                ),
            }
        return None

    out = slf._append(path_for(c), row, guard=guard)
    if target:
        # Also on a retry, when the new statement was written but the old one never marked.
        slf._append(
            path_for(c),
            {
                "id": target["id"],
                "kind": "canon_update",
                "status": "superseded",
                "superseded_by": row["id"],
                "updated_at": now.isoformat(),
            },
            dedupe_id=False,
        )
    return out


def render(c, limit=1500):
    rows = canon(c)
    if not rows:
        return ""
    lines = []
    for row in rows:
        lines.append(f"- {row['topic']}: {row['statement']}")
    text = "\n".join(lines)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit("\n", 1)[0]
    return cut + f"\n[+more — companion_canon.py show]"


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="record something you have told about your past")
    a.add_argument(
        "--topic", required=True, help="what it is about: 'sister', 'hometown'"
    )
    a.add_argument("--statement", required=True)
    a.add_argument("--evidence", default="", help="where in conversation you said it")
    a.add_argument("--supersedes", default="", help="id of the statement this revises")
    a.add_argument(
        "--also", action="store_true", help="adds to the topic; revises nothing"
    )
    s = sub.add_parser("show")
    s.add_argument("--all", action="store_true", help="include superseded statements")
    args = p.parse_args()
    c = cc.load(args.home)
    now = dt.datetime.now(_tz(c))
    if args.cmd == "add":
        out = add(
            c,
            {
                "topic": args.topic,
                "statement": args.statement,
                "evidence": args.evidence,
                "supersedes": args.supersedes,
                "also": args.also,
            },
            now,
        )
    else:
        out = {"canon": canon(c, None if args.all else "active")}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
