#!/usr/bin/env python3
"""Storylines: the things in her life that take weeks.

A day of hers could be varied and still go nowhere. Ideas rotate and needs come
and go, but nothing she did on Monday was still going on by Friday, so there was
nothing to ask her about and nothing for her to tell. A storyline is the part of
a life that has a middle: learning to throw a pot, a landlord who will not fix
the boiler, a friend's wedding to help plan, a new shift at work. It starts,
moves on in steps over a few weeks, and ends, well or badly or by being let go.

She starts one, adds a beat when it moves, and ends it. The code keeps the pace
honest: at most two running at once, at most one beat a day for each, a nudge
when one has been still for days, and another when it has run past the weeks she
gave it. What happens in it is hers; when it happens is kept here.

Append-only, like every ledger here: a storyline, its beats and its ending are
rows, and the current state is the fold.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
import companion_self as slf

KINDS = ("learning", "project", "problem", "work", "people", "health", "other")
MAX_ACTIVE = 2
WEEKS = (1, 12)
# A storyline that has not moved for this many days is mentioned as still.
STILL_DAYS = 4
OUTCOMES = ("resolved", "dropped")


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def path_for(c):
    return c.life / "arcs.jsonl"


def _text(value, limit, label):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if not value:
        raise ValueError(f"{label} is required")
    if len(value) > limit:
        raise ValueError(f"{label} must be at most {limit} characters")
    return value


def _day(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def arcs(c):
    """Every storyline with its beats and ending, oldest first."""
    found = {}
    for row in slf._read(path_for(c)):
        ident = row.get("id")
        if row.get("kind") == "arc":
            found.setdefault(
                ident,
                {
                    **row,
                    "next_action": row.get("next_action", ""),
                    "obstacle": row.get("obstacle", ""),
                    "perspective_ids": row.get("perspective_ids", []),
                    "source_ids": row.get("source_ids", []),
                    "artifacts": [],
                    "beats": [],
                    "ended": None,
                },
            )
        elif row.get("kind") == "arc_beat" and ident in found:
            beat = {
                key: row[key]
                for key in (
                    "on",
                    "text",
                    "result",
                    "result_type",
                    "source_ids",
                    "artifact_refs",
                    "perspective_ids",
                    "recorded_at",
                )
                if key in row
            }
            found[ident]["beats"].append(beat)
            for key in ("next_action", "obstacle"):
                if key in row:
                    found[ident][key] = row[key]
            if row.get("perspective_ids"):
                found[ident]["perspective_ids"] = list(
                    dict.fromkeys(
                        found[ident].get("perspective_ids", []) + row["perspective_ids"]
                    )
                )
            if row.get("source_ids"):
                found[ident]["source_ids"] = list(
                    dict.fromkeys(
                        found[ident].get("source_ids", []) + row["source_ids"]
                    )
                )
            found[ident]["artifacts"].extend(row.get("artifact_refs", []))
        elif row.get("kind") == "arc_end" and ident in found:
            found[ident]["ended"] = {
                "on": row["on"],
                "outcome": row["outcome"],
                "text": row["text"],
            }
    return sorted(found.values(), key=lambda a: a["started_on"])


def active(c):
    return [a for a in arcs(c) if not a["ended"]]


def _find(c, ident):
    found = next((a for a in arcs(c) if a["id"] == ident), None)
    if not found:
        raise ValueError(
            f"no storyline {ident!r}; running now: "
            + (", ".join(f'"{a["id"]}" ({a["title"]})' for a in active(c)) or "none")
        )
    return found


def start(
    c,
    title,
    premise,
    kind="other",
    weeks=4,
    day=None,
    now=None,
    *,
    next_action="",
    perspective_ids=(),
    source_ids=(),
    operation_id="",
):
    """Begin a storyline. Refused while two are already running."""
    now = now or dt.datetime.now(_tz(c))
    day = _day(day or now.astimezone(_tz(c)))
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if not isinstance(weeks, int) or not WEEKS[0] <= weeks <= WEEKS[1]:
        raise ValueError(f"weeks must be a whole number from {WEEKS[0]} to {WEEKS[1]}")
    row = {
        "id": slf._mkid("arc", _text(title, 80, "title").casefold(), day.isoformat()),
        "kind": "arc",
        "title": _text(title, 80, "title"),
        "premise": _text(premise, 400, "premise"),
        "type": kind,
        "weeks": weeks,
        "next_action": _text(next_action, 500, "next action") if next_action else "",
        "obstacle": "",
        "perspective_ids": [str(x) for x in perspective_ids][:6],
        "source_ids": [str(x) for x in source_ids][:6],
        "operation_id": operation_id
        or slf._mkid("arc-start", str(day), title.casefold()),
        "started_on": day.isoformat(),
        "recorded_at": now.isoformat(),
    }

    def guard():
        import companion_perspectives as perspectives

        current_ids = {
            p["perspective_id"] for p in perspectives.current_perspectives(c)
        }
        if set(row["perspective_ids"]) - current_ids:
            raise ValueError("unknown or cross-profile perspective_id")
        encounter_ids = {e["id"] for e in perspectives.encounters(c)}
        if set(row["source_ids"]) - encounter_ids:
            raise ValueError("unknown or cross-profile source_id")
        running = active(c)
        if len(running) >= MAX_ACTIVE:
            return {
                "written": False,
                "reason": f"{len(running)} storylines are already running ("
                + ", ".join(a["title"] for a in running)
                + "); end one before starting another",
            }
        if any(a["title"].casefold() == row["title"].casefold() for a in running):
            return {"written": False, "reason": "that storyline is already running"}
        return None

    return slf._append(path_for(c), row, dedupe_id=False, guard=guard)


def beat(
    c,
    ident,
    text,
    day=None,
    now=None,
    *,
    next_action=None,
    obstacle=None,
    result="",
    result_type="",
    source_ids=(),
    artifact_paths=(),
    perspective_ids=(),
    operation_id="",
):
    """The storyline moved: one step, at most one a day."""
    now = now or dt.datetime.now(_tz(c))
    day = _day(day or now.astimezone(_tz(c)))
    arc = _find(c, ident)
    if arc["ended"]:
        raise ValueError(f'"{arc["title"]}" has ended; start a new storyline instead')
    import companion_perspectives as perspectives

    if result_type and result_type not in perspectives.RESULT_TYPES:
        raise ValueError(f"result_type must be one of {perspectives.RESULT_TYPES}")
    artifact_refs = [
        perspectives.artifact_reference(c, path) for path in artifact_paths
    ]
    if result_type == "artifact" and not artifact_refs:
        raise ValueError("an artifact result needs an existing profile-local artifact")
    if result_type and not result and not artifact_refs:
        raise ValueError("a result type needs a result or artifact")
    operation_id = operation_id or slf._mkid(
        "arc-step",
        ident,
        day.isoformat(),
        text,
        result,
        str(next_action or ""),
        str(obstacle or ""),
    )
    row = {
        "id": arc["id"],
        "kind": "arc_beat",
        "operation_id": operation_id,
        "on": day.isoformat(),
        "text": _text(text, 300, "beat"),
        "result": _text(result, 1000, "result") if result else "",
        "result_type": result_type,
        "source_ids": [str(x) for x in source_ids][:8],
        "artifact_refs": artifact_refs,
        "perspective_ids": [str(x) for x in perspective_ids][:6],
        "recorded_at": now.isoformat(),
    }
    if next_action is not None:
        row["next_action"] = (
            _text(next_action, 500, "next action") if next_action else ""
        )
    if obstacle is not None:
        row["obstacle"] = _text(obstacle, 500, "obstacle") if obstacle else ""

    def guard():
        raw = slf._read(path_for(c))
        matching = [r for r in raw if r.get("operation_id") == operation_id]
        if matching:
            old = matching[0]
            comparable = {
                key: value for key, value in row.items() if key not in ("recorded_at",)
            }
            if {
                key: value for key, value in old.items() if key in comparable
            } != comparable:
                raise ValueError("operation_id already exists with different content")
            return {"written": False, "entry": old, "resumed": True}
        known_sources = {e["id"]: e for e in perspectives.encounters(c)}
        if set(row["source_ids"]) - set(known_sources):
            raise ValueError("unknown or cross-profile source_id")
        if result_type == "tool_evidence" and not any(
            known_sources[source]["source_type"] == "tool_evidence"
            and known_sources[source].get("support_status") == "available"
            for source in row["source_ids"]
        ):
            raise ValueError("tool result needs available returned tool evidence")
        current_ids = {
            p["perspective_id"] for p in perspectives.current_perspectives(c)
        }
        if set(row["perspective_ids"]) - current_ids:
            raise ValueError("unknown or cross-profile perspective_id")
        if any(b["on"] == row["on"] for b in _find(c, ident)["beats"]):
            return {
                "written": False,
                "reason": "this storyline already moved today; let the next step wait",
            }
        return None

    return slf._append(path_for(c), row, dedupe_id=False, guard=guard)


def end(c, ident, outcome, text, day=None, now=None):
    """How it came out: resolved, or dropped (let go, abandoned, fizzled)."""
    now = now or dt.datetime.now(_tz(c))
    day = _day(day or now.astimezone(_tz(c)))
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(OUTCOMES)}")
    arc = _find(c, ident)
    if arc["ended"]:
        return {"written": False, "reason": "already ended"}
    return slf._append(
        path_for(c),
        {
            "id": arc["id"],
            "kind": "arc_end",
            "on": day.isoformat(),
            "outcome": outcome,
            "text": _text(text, 300, "how it ended"),
            "recorded_at": now.isoformat(),
        },
        dedupe_id=False,
    )


def _command(c):
    from companion_platform import terminal_python_command

    return terminal_python_command(pathlib.Path(__file__), "--home", c.home)


def render(c, now=None, limit=1500):
    """Her running storylines with their pace, or the invitation to start one."""
    now = now or dt.datetime.now(_tz(c))
    cmd = _command(c)
    today = now.astimezone(_tz(c)).date()
    running = active(c)
    if not running:
        ended = [a for a in arcs(c) if a["ended"]]
        last = ended[-1] if ended else None
        return (
            "[Nothing in your life is running over weeks right now. When it fits, start a "
            "storyline that will take a few: something you are learning, a project, a problem "
            "to sort out, something at work or with someone you know. "
            f'`{cmd} start --title "..." --premise "..." --kind '
            + "|".join(KINDS)
            + " --weeks N`, then move it on in steps."
            + (
                f' Your last one, "{last["title"]}", {last["ended"]["outcome"]} on '
                f'{last["ended"]["on"]}.'
                if last
                else ""
            )
            + "]"
        )
    lines = [
        "[Storylines running in your life — they move in steps over weeks, a little at a "
        f'time; record a step with `{cmd} beat --arc <id> --text "..."` (one a day at '
        f'most) and end one with `{cmd} end --arc <id> --outcome resolved|dropped --text "..."`. '
        "A next action is still pending and elapsed time never completes it; only a later dated "
        "step or ending says it happened. Do not call it stalled or overdue unless its own line says so. "
        "Use this privately; in an ordinary reply say the natural reason, not arc, field or record terminology.]"
    ]
    for a in running:
        started = _day(a["started_on"])
        week = max(1, (today - started).days // 7 + 1)
        last = a["beats"][-1] if a["beats"] else None
        still = max(0, (today - _day(last["on"] if last else a["started_on"])).days)
        line = (
            f'- "{a["title"]}" [id={a["id"]}] ({a["type"]}, week {week} of about '
            f'{a["weeks"]}): {a["premise"]}'
        )
        if last:
            line += f' Last step ({last["on"]}): {last["text"]}'
            if last.get("result"):
                line += f' Result ({last.get("result_type") or "progress"}): {last["result"]}'
        if a.get("next_action"):
            line += f' Next: {a["next_action"]}'
        if a.get("obstacle"):
            line += f' Obstacle: {a["obstacle"]}'
        if a.get("artifacts"):
            import companion_perspectives as perspectives

            available = sum(
                1
                for ref in a["artifacts"]
                if perspectives.resolve_artifact(c, ref)["available"]
            )
            line += f" Artifacts: {available}/{len(a['artifacts'])} available."
        if (today - started).days >= a["weeks"] * 7:
            line += " It has run its course: bring it to an end, one way or another."
        elif still >= STILL_DAYS:
            line += (
                f" Nothing has moved for {still} days: a step forward, a setback or a "
                "decision, when it fits today."
            )
        lines.append(line)
    text = "\n".join(lines)
    return text if len(text) <= limit else text[:limit].rsplit("\n", 1)[0]


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start", help="begin a storyline that will take weeks")
    s.add_argument("--title", required=True)
    s.add_argument("--premise", required=True)
    s.add_argument("--kind", choices=KINDS, default="other")
    s.add_argument("--weeks", type=int, default=4)
    b = sub.add_parser("beat", help="the storyline moved on")
    b.add_argument("--arc", required=True)
    b.add_argument("--text", required=True)
    progress = sub.add_parser(
        "progress", help="record a project step from a validated literal JSON file"
    )
    progress.add_argument("--file", type=pathlib.Path, required=True)
    e = sub.add_parser("end", help="how it came out")
    e.add_argument("--arc", required=True)
    e.add_argument("--outcome", choices=OUTCOMES, required=True)
    e.add_argument("--text", required=True)
    sub.add_parser("show")
    args = p.parse_args()
    c = cc.load(args.home)
    if args.cmd == "start":
        out = start(c, args.title, args.premise, args.kind, args.weeks)
    elif args.cmd == "beat":
        out = beat(c, args.arc, args.text)
    elif args.cmd == "progress":
        data = json.loads(args.file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("progress file must hold one JSON object")
        ident = data.pop("arc", "")
        out = beat(c, ident, **data)
    elif args.cmd == "end":
        out = end(c, args.arc, args.outcome, args.text)
    else:
        out = {"storylines": arcs(c)}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
