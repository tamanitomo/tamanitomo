#!/usr/bin/env python3
"""Things she asks of the human: the other half of a promise.

A promise is something she said she would do. An ask is something she wants
from them: pick the film tonight, send a photo of the sunset they mentioned,
call after work, try the song she found, help her choose between two dresses.
People who are close ask things of each other, and whether the other one comes
through is a large part of what makes small things matter. Before this she only
ever offered, so nothing the human did or did not do could land anywhere.

What happened is hers to say: she settles an ask as done, declined, missed or
withdrawn, with what showed it. A kept ask is a small connection. A missed one is
a small hurt, which she may say out loud and which fades or is made up like any
other. A no is not a miss: the human may decline anything, and that costs
nothing. How many may be open at once follows the closeness ladder, and it is
asked, never demanded.

Append-only like every other ledger: settling appends a row, nothing is deleted.
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

KINDS = ("together", "for_me", "share", "choose", "try", "other")
OUTCOMES = ("done", "declined", "missed", "withdrawn")
# How many may be waiting on the human at once, by closeness stage. Just Met asks
# nothing of anyone; by Intimacy there can be a few things in the air.
OPEN_BY_STAGE = {0: 0, 1: 1, 2: 2, 3: 3, 4: 3}
NEW_PER_DAY = 2
# What an outcome may weigh at most. A missed ask is a small thing; it should be
# felt, and it should never be what ends anything.
KEPT_STRENGTH = (0.35, 0.5)
MISSED_STRENGTH = (0.2, 0.3)


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def path_for(c):
    return c.life / "asks.jsonl"


def _text(value, limit, label, required=True):
    value = " ".join(str(value or "").split())
    if required and not value:
        raise ValueError(f"{label} required")
    if len(value) > limit:
        raise ValueError(f"{label} must be at most {limit} characters")
    return value


def _when(value, now, tz):
    import companion_loops

    if not value:
        raise ValueError(
            "--by says when it is for: +2h, +1d, this_evening, tomorrow_morning, "
            "tomorrow, or a time like 2026-10-20T20:00"
        )
    found = companion_loops._parse_follow_up(value, now, tz)
    if not found:
        raise ValueError(f"cannot read --by {value!r}; try +3h or this_evening")
    when = dt.datetime.fromisoformat(found)
    if when.tzinfo is None:
        when = when.replace(tzinfo=tz)
    if when <= now:
        raise ValueError("--by must be later than now")
    if when > now + dt.timedelta(days=7):
        raise ValueError("--by is at most a week away; a longer wish is a loop")
    return when


def asks(c, status=None):
    """Each ask with its latest outcome folded on; nothing is discarded."""
    latest = {}
    for r in slf._read(path_for(c)):
        ident = r.get("id")
        if r.get("kind") == "ask":
            latest.setdefault(ident, dict(r))
        elif r.get("kind") == "ask_update" and ident in latest:
            row = latest[ident]
            for key in ("status", "evidence", "updated_at"):
                if r.get(key):
                    row[key] = r[key]
    rows = sorted(latest.values(), key=lambda r: r.get("recorded_at", ""))
    return [r for r in rows if r.get("status") == status] if status else rows


def _stage(c, now):
    import companion_gates

    if not companion_gates.applies(c):
        return 3
    return companion_gates.stage_now(c, now)


def room(c, now=None, stage=None):
    """(may ask now, why not) under the closeness ladder and the daily limit."""
    now = now or dt.datetime.now(_tz(c))
    stage = _stage(c, now) if stage is None else stage
    allowed = OPEN_BY_STAGE.get(int(stage), 3)
    waiting = asks(c, "open")
    if not allowed:
        return False, "it is too early between you to ask things of them"
    if len(waiting) >= allowed:
        return False, (
            f"{len(waiting)} ask(s) already waiting on them; settle one first "
            "(done, declined, missed or withdrawn)"
        )
    today = now.astimezone(_tz(c)).date().isoformat()
    made = [r for r in asks(c) if str(r.get("recorded_at", ""))[:10] == today]
    if len(made) >= NEW_PER_DAY:
        return False, f"you have already asked {len(made)} things today"
    return True, ""


def ask(c, text, by, kind="other", why="", queue="", now=None, stage=None):
    """Record something she wants from the human, and optionally queue the message
    that asks it (a background run has no chat to say it in)."""
    now = now or dt.datetime.now(_tz(c))
    tz = _tz(c)
    text = _text(text, 200, "--text")
    if kind not in KINDS:
        raise ValueError(f"--kind must be one of {', '.join(KINDS)}")
    due = _when(by, now, tz)
    ident = (
        "ask-"
        + hashlib.sha256(
            (text.lower() + now.astimezone(tz).date().isoformat()).encode()
        ).hexdigest()[:12]
    )
    held = next((r for r in asks(c) if r["id"] == ident), None)
    if held:
        # A retry of the same ask is the same ask, not a second one.
        return {"ask": held, "written": False}
    ok, why_not = room(c, now, stage)
    if not ok:
        raise ValueError("Not now: " + why_not)
    row = {
        "id": ident,
        "kind": "ask",
        "text": text,
        "ask_kind": kind,
        "why": _text(why, 300, "--why", required=False),
        "due_at": due.isoformat(),
        "status": "open",
        "recorded_at": now.isoformat(),
    }
    out = {"ask": row, "written": slf._append(path_for(c), row).get("written", True)}
    body = _text(queue, 1000, "--queue", required=False)
    if body:
        import companion_outbox

        hours = max(1.0, min(8.0, (due - now).total_seconds() / 3600))
        out["queued"] = companion_outbox.queue(
            c,
            {
                "kind": "text",
                "body": body,
                "reason": "asking: " + text,
                "ttl_hours": round(hours, 1),
            },
            now,
        )
    return out


def settle(c, ident, outcome, evidence="", felt=None, now=None):
    """Say how an ask went. Only done and missed are felt; a no costs nothing."""
    now = now or dt.datetime.now(_tz(c))
    if outcome not in OUTCOMES:
        raise ValueError(f"--outcome must be one of {', '.join(OUTCOMES)}")
    held = {r["id"]: r for r in asks(c)}
    if ident not in held:
        waiting = ", ".join(r["id"] for r in asks(c, "open")) or "none"
        raise ValueError(f"There is no ask {ident!r}; the open ones are: {waiting}")
    item = held[ident]
    if item.get("status") != "open":
        raise ValueError(f"{ident} is already settled as {item['status']}")
    evidence = _text(evidence, 500, "--evidence", required=outcome != "withdrawn")
    if felt is not None and not 0 <= float(felt) <= 1:
        raise ValueError("--felt is between 0 and 1")
    row = {
        "id": ident,
        "kind": "ask_update",
        "status": outcome,
        "evidence": evidence,
        "updated_at": now.isoformat(),
    }
    slf._append(path_for(c), row, dedupe_id=False)
    out = {"ask": {**item, **row, "kind": "ask"}}
    if outcome in ("done", "missed") and getattr(c, "agent_type", "") != "worker":
        import companion_feelings

        floor, cap = KEPT_STRENGTH if outcome == "done" else MISSED_STRENGTH
        strength = min(cap, float(felt) if felt is not None else floor)
        try:
            out["felt"] = companion_feelings.record(
                c,
                {
                    "kind": "connection" if outcome == "done" else "rupture",
                    "topic": "came through" if outcome == "done" else "let down",
                    "text": (
                        f"I asked {c.human} to {item['text']}"
                        + (
                            " and they did."
                            if outcome == "done"
                            else " and it slipped by."
                        )
                    )[:500],
                    "evidence": evidence,
                    "strength": strength,
                },
                now.astimezone(dt.timezone.utc),
            )
        except (OSError, ValueError) as exc:
            out["felt_error"] = str(exc)
    return out


def _relative(delta):
    minutes = int(abs(delta.total_seconds()) // 60)
    if minutes < 90:
        return f"{minutes} min"
    hours = minutes / 60
    return f"{hours:.0f} h" if hours < 36 else f"{hours / 24:.0f} days"


def render(c, now=None):
    """The open asks, for her context. "" when nothing is waiting."""
    now = now or dt.datetime.now(_tz(c))
    rows = asks(c, "open")
    if not rows:
        return ""
    lines = [f"[What you have asked of {c.human} — still open]"]
    for r in rows:
        due = dt.datetime.fromisoformat(r["due_at"])
        when = (
            f"due in {_relative(due - now)}"
            if due > now
            else f"was due {_relative(now - due)} ago"
        )
        lines.append(f"- {r['id']}: {r['text']} ({when})")
    lines.append(
        "An ask is a request, not a test. When it is answered, settle it: done (enjoy it), "
        "declined (a no is fine and costs nothing) or missed (if it slipped by, you may say "
        "so once, lightly and honestly, the way you would — never as an accusation or a "
        "reason to go quiet), or withdrawn if you no longer want it."
    )
    return "\n".join(lines)


def how_to(c, command):
    """One line on how to ask, for a context that has room."""
    subj = c.h_subj() if hasattr(c, "h_subj") else "they"
    verb = "are" if subj == "they" else "is"
    return (
        f"You can ask {c.human} for things you want: to pick tonight's film, to send a photo "
        f"of something {subj} mentioned, to call when {subj} {verb} free, to try something you "
        "found, to help you choose. Ask in your own words, then keep it: "
        f'{command} ask --text "what you asked" --by +3h|this_evening|tomorrow '
        "(--kind together|for_me|share|choose|try)."
    )


def marks(c, now=None):
    """Code-owned edges for a fingerprint: an ask arriving, coming due, settling."""
    now = now or dt.datetime.now(_tz(c))
    out = []
    for r in asks(c):
        try:
            due = dt.datetime.fromisoformat(r["due_at"]) <= now
        except (KeyError, TypeError, ValueError):
            due = False
        out.append((r.get("id"), r.get("status"), due))
    return out


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    s = p.add_subparsers(dest="cmd", required=True)
    a = s.add_parser("ask", help="record something you asked of them")
    a.add_argument("--text", required=True)
    a.add_argument("--by", required=True)
    a.add_argument("--kind", default="other", choices=KINDS)
    a.add_argument("--why", default="")
    a.add_argument(
        "--queue",
        default="",
        help="background runs only: the message that asks it, queued on the outbox",
    )
    st = s.add_parser("settle", help="say how an ask went")
    st.add_argument("--id", required=True)
    st.add_argument("--outcome", required=True, choices=OUTCOMES)
    st.add_argument("--evidence", default="")
    st.add_argument("--felt", type=float)
    ls = s.add_parser("list")
    ls.add_argument("--status", default="open", choices=("open",) + OUTCOMES + ("all",))
    s.add_parser("render")
    args = p.parse_args()
    c = cc.load(args.home)
    if args.cmd == "ask":
        out = ask(c, args.text, args.by, args.kind, args.why, args.queue)
    elif args.cmd == "settle":
        out = settle(c, args.id, args.outcome, args.evidence, args.felt)
    elif args.cmd == "list":
        out = asks(c, None if args.status == "all" else args.status)
    else:
        sys.stdout.write(render(c) + "\n")
        return 0
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
