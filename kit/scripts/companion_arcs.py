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
            found.setdefault(ident, {**row, "beats": [], "ended": None})
        elif row.get("kind") == "arc_beat" and ident in found:
            found[ident]["beats"].append({"on": row["on"], "text": row["text"]})
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


def start(c, title, premise, kind="other", weeks=4, day=None, now=None):
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
        "started_on": day.isoformat(),
        "recorded_at": now.isoformat(),
    }

    def guard():
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


def beat(c, ident, text, day=None, now=None):
    """The storyline moved: one step, at most one a day."""
    now = now or dt.datetime.now(_tz(c))
    day = _day(day or now.astimezone(_tz(c)))
    arc = _find(c, ident)
    if arc["ended"]:
        raise ValueError(f'"{arc["title"]}" has ended; start a new storyline instead')
    row = {
        "id": arc["id"],
        "kind": "arc_beat",
        "on": day.isoformat(),
        "text": _text(text, 300, "beat"),
        "recorded_at": now.isoformat(),
    }

    def guard():
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
        f'most) and end one with `{cmd} end --arc <id> --outcome resolved|dropped --text "..."`]'
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
