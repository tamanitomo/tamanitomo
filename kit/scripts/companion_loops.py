#!/usr/bin/env python3
"""Open loops: the threads between two people that are not finished yet.

An open loop is a thing left hanging — an interview on Thursday, a dentist
appointment, a book lent out, a fight half-resolved. Each carries a `gentle_use`
line saying how and when to raise it, because the difference between a companion
and a reminder app is that a companion knows a question can be unwelcome.

Append-only, like every other ledger here. Closing a loop appends a closing
entry; it never removes the original, so what mattered last month is still
readable next year.
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
from companion_platform import file_lock
import companion_self as slf

STATUSES = ("open", "closed", "paused")


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def path_for(c):
    return c.life / "open-loops.jsonl"


def _text(value, limit, label, required=True):
    value = (value or "").strip()
    if required and not value:
        raise ValueError(f"{label} required")
    if len(value) > limit:
        raise ValueError(f"{label} must be at most {limit} characters")
    return value


def _parse_follow_up(value, now, tz):
    if not value:
        return ""
    val = str(value).strip().lower()
    if val.startswith("+"):
        body = val[1:].strip()
        try:
            if body.endswith("h"):
                return (now + dt.timedelta(hours=float(body[:-1]))).isoformat()
            if body.endswith("m"):
                return (now + dt.timedelta(minutes=float(body[:-1]))).isoformat()
            if body.endswith("d"):
                return (now + dt.timedelta(days=float(body[:-1]))).isoformat()
        except ValueError:
            pass
    if val in ("this_evening", "evening"):
        target = now.replace(hour=19, minute=0, second=0, microsecond=0)
        if target <= now:
            target = now + dt.timedelta(hours=2)
        return target.isoformat()
    if val in ("tomorrow_morning", "morning"):
        target = (now + dt.timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        return target.isoformat()
    if val in ("tomorrow_evening", "tomorrow"):
        target = (now + dt.timedelta(days=1)).replace(
            hour=19, minute=0, second=0, microsecond=0
        )
        return target.isoformat()
    try:
        when = dt.datetime.fromisoformat(val)
        if when.tzinfo is None:
            when = when.replace(tzinfo=tz)
        return when.isoformat()
    except ValueError:
        return ""


def add(c, entry, now):
    title = _text(entry.get("title"), 160, "title")
    follow_up = _parse_follow_up(
        entry.get("follow_up_at") or entry.get("follow_up_after"), now, _tz(c)
    )
    row = {
        "id": entry.get("id")
        or "loop-" + hashlib.sha256(title.lower().encode()).hexdigest()[:16],
        "kind": "loop",
        "title": title,
        "detail": _text(entry.get("detail"), 600, "detail", required=False),
        "gentle_use": _text(entry.get("gentle_use"), 300, "gentle_use"),
        "category": _text(
            entry.get("category", "care"), 50, "category", required=False
        ),
        "follow_up_at": follow_up,
        "status": "open",
        "recorded_at": now.isoformat(),
    }
    return slf._append(path_for(c), row)


def update(c, entry, now):
    ident = _text(entry.get("id"), 120, "id")
    status = entry.get("status", "open")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if not any(r.get("id") == ident for r in slf._read(path_for(c), kind="loop")):
        raise ValueError("unknown loop id")
    follow_up = _parse_follow_up(
        entry.get("follow_up_at") or entry.get("follow_up_after"), now, _tz(c)
    )
    row = {
        "id": ident,
        "kind": "loop_update",
        "status": status,
        "detail": _text(entry.get("detail"), 600, "detail", required=False),
        "gentle_use": _text(entry.get("gentle_use"), 300, "gentle_use", required=False),
        "category": _text(entry.get("category"), 50, "category", required=False),
        "follow_up_at": follow_up,
        "note": _text(entry.get("note"), 300, "note", required=False),
        "updated_at": now.isoformat(),
    }
    return slf._append(path_for(c), row, dedupe_id=False)


def loops(c, status="open"):
    """Fold updates onto originals; newest change wins, nothing is discarded."""
    latest = {}
    for r in slf._read(path_for(c)):
        ident = r.get("id")
        if r.get("kind") == "loop":
            latest.setdefault(ident, dict(r))
        elif r.get("kind") == "loop_update" and ident in latest:
            loop = latest[ident]
            loop["status"] = r.get("status", loop["status"])
            for key in ("detail", "gentle_use", "category", "follow_up_at"):
                if r.get(key):
                    loop[key] = r[key]
            loop["updated_at"] = r.get("updated_at", "")
            if r.get("note"):
                loop["note"] = r["note"]
    rows = sorted(
        latest.values(), key=lambda l: l.get("updated_at") or l["recorded_at"]
    )
    return [l for l in rows if l["status"] == status] if status else rows


def batch(c, path, now):
    """One JSON file, the same shape the reflection ledgers take."""
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("entries")
    if not isinstance(data, list) or not data:
        raise ValueError("batch file must hold a list of entries")
    if len(data) > 50:
        raise ValueError("batch file holds more than 50 entries")
    results = []
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError("each entry must be a JSON object")
        try:
            out = (
                update(c, entry, now)
                if entry.get("id") and entry.get("kind") == "update"
                else add(c, entry, now)
            )
        except (ValueError, OSError, TypeError) as exc:
            results.append({"index": i, "ok": False, "error": str(exc)})
            return {
                "applied": sum(1 for r in results if r.get("ok")),
                "failed_at": i,
                "results": results,
            }
        results.append(
            {
                "index": i,
                "ok": True,
                "id": out["entry"]["id"],
                "written": out["written"],
            }
        )
    return {"applied": len(results), "failed_at": None, "results": results}


def render(c, limit=None, now=None):
    """The markdown the ActiveContext assembler and the app both show."""
    now = now or dt.datetime.now(_tz(c))
    rows = loops(c, "open")
    if limit:
        rows = rows[-limit:]
    if not rows:
        return "Nothing is hanging between you right now.\n"
    due = []
    for l in rows:
        fu = l.get("follow_up_at")
        if fu:
            try:
                when = dt.datetime.fromisoformat(fu)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=_tz(c))
                if when <= now:
                    due.append(l)
            except ValueError:
                pass
    out = []
    if due:
        out.append("## [CARING CALLBACKS READY TO RAISE]")
        out.append(
            "The following open thread(s) have reached their follow-up horizon. Check in warmly and gently:\n"
        )
        for loop in due:
            out.append(f"**{loop['title']}** (follow up: {loop['follow_up_at'][:16]})")
            if loop.get("detail"):
                out.append(f"- Detail: {loop['detail']}")
            out.append(f"- How to raise gently: {loop['gentle_use']}")
            out.append("")
    for loop in rows:
        out.append(f"### {loop['title']}")
        if loop.get("detail"):
            out.append(loop["detail"])
        out.append(
            f"- status: open since {loop['recorded_at'][:10]}"
            + (
                f", last touched {loop['updated_at'][:10]}"
                if loop.get("updated_at")
                else ""
            )
        )
        out.append(f"- gentle use: {loop['gentle_use']}")
        if loop.get("follow_up_at"):
            out.append(f"- follow up: {loop['follow_up_at'][:16]}")
        if loop.get("note"):
            out.append(f"- note: {loop['note']}")
        out.append("")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--home", type=pathlib.Path)
    s = p.add_subparsers(dest="cmd", required=True)
    b = s.add_parser("add", help="add or update loops from one JSON file")
    b.add_argument("--file", type=pathlib.Path, required=True)
    l = s.add_parser("list")
    l.add_argument("--status", choices=list(STATUSES) + ["all"], default="open")
    cl = s.add_parser("close")
    cl.add_argument("--id", required=True)
    s.add_parser("render")
    a = p.parse_args()
    c = cc.load(a.home)
    now = dt.datetime.now(_tz(c))
    if a.cmd == "add":
        out = batch(c, a.file, now)
    elif a.cmd == "list":
        out = {"loops": loops(c, None if a.status == "all" else a.status)}
    elif a.cmd == "close":
        out = update(c, {"id": a.id, "status": "closed"}, now)
    else:
        out = {"markdown": render(c)}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
