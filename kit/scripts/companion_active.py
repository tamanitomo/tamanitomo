#!/usr/bin/env python3
"""Assemble ActiveContext.md from the files that already know the answer.

The model used to write this file by hand, which cost a model call per refresh
and gave the present a second author who could disagree with the state ledger.
Nothing here is authored: every line is read from a source that owns it.

  ## Right now            the latest presence state
  ## Active open loops    the open-loops ledger
  ## The thread           the relationship-thread sensor, if one is installed
  ## Ambient              the sensor files, if any
  ## Queued               the outbox, if one is waiting

A source that is missing produces no section at all. An absent sensor must never
become a claim: silence is the correct output for something we do not know.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write

HEADER = (
    "<!-- Assembled by companion_active.py from the presence state, the open-loops ledger and\n"
    "     the installed sensors. Editing this file changes nothing; the next assembly\n"
    "     overwrites it. Change the source instead. -->"
)


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def _age(then, now):
    from companion_context import age_phrase

    return age_phrase(then, now)


def right_now(c, now):
    """The present, from the state ledger, with its age attached.

    The age matters more than the text: a confident sentence about a Tuesday
    evening, read on Thursday morning, is how a companion ends up wrong about
    the world with no way to notice.
    """
    from companion_presence import current

    scene = current(c)
    if not scene:
        return (
            "No state recorded yet. Establish one before describing a current scene.\n"
        )
    state = scene["state"]
    when = dt.datetime.fromisoformat(scene["recorded_at"])
    outfit = ", ".join(item["description"] for item in state.get("outfit", []))
    lines = [
        f"_recorded {_age(when,now)}_",
        "",
        f"{state.get('activity','')} at {state.get('location','')}.",
        f"Wearing {outfit}." if outfit else "",
        f"Mood: {state.get('mood','')}." if state.get("mood") else "",
    ]
    if state.get("wants"):
        lines += ["", "Wants right now: " + "; ".join(state["wants"]) + "."]
    if state.get("private_stance"):
        lines += ["", f"Where {c.subj()} actually stands: {state['private_stance']}"]
    if state.get("care"):
        lines += ["", "Recent care: " + "; ".join(state["care"]) + "."]
    import companion_day

    lines += ["", companion_day.render(state, now)]
    return "\n".join(l for l in lines if l is not None) + "\n"


def waiting_missions(c, now=None):
    """Work the human has asked for and nobody has done yet."""
    try:
        import companion_missions

        return companion_missions.render(c, now)
    except (OSError, ValueError, ImportError):
        return ""


def open_loops(c, now=None):
    import companion_loops as loops

    return loops.render(c, now=now)


def _read(path, limit=1500):
    try:
        return path.read_text(encoding="utf-8")[:limit].strip()
    except OSError:
        return ""


def thread(c):
    """The relationship-thread sensor. Absent until Phase 2 installs one."""
    return _read(c.soul_dir / "ambient/relationship-thread.md")


def ambient(c, skip=("relationship-thread", "bars")):
    folder = c.soul_dir / "ambient"
    if not folder.is_dir():
        return ""
    out = []
    for path in sorted(folder.glob("*.md")):
        if path.stem in skip:
            continue
        body = _read(path, 800)
        if body:
            out.append(f"### {path.stem}\n{body}")
    return "\n\n".join(out)


def queued(c, now=None):
    """What is waiting to be sent, so she is not surprised by her own message."""
    try:
        import companion_outbox

        return companion_outbox.render(c, now)
    except (OSError, ValueError, ImportError):
        return ""


def recent_conversation(c, now=None):
    """Recent chat exchange, conversational commitments, and user persuasion."""
    try:
        import companion_thread

        thread_data = companion_thread.read(c, now, tail=8)
        if (
            not thread_data
            or not thread_data.get("available")
            or not thread_data.get("tail")
        ):
            return ""
        lines = []
        hours = thread_data.get("hours_since_contact")
        if hours is not None:
            if hours < (1 / 60):
                lines.append("_Last exchanged messages just now._")
            elif hours < 1:
                mins = max(1, int(hours * 60))
                lines.append(
                    f"_Last exchanged messages ~{mins} minute{'s' if mins!=1 else ''} ago._"
                )
            else:
                lines.append(f"_Last exchanged messages ~{hours:.1f} hours ago._")
        lines.append("")
        for msg in thread_data["tail"]:
            speaker = "Them" if msg.get("who") == "them" else c.agent
            text = (msg.get("text") or "").strip()
            if text:
                lines.append(f"**{speaker}**: {text}")
        lines.append("")
        lines.append("CONVERSATIONAL REALITY & USER PERSUASION:")
        lines.append(
            "If the human recently persuaded you, made a suggestion (e.g. taking a bath, relaxing in the hot tub, an outing), or if you agreed on an activity or promised to follow up later, honor that agreement! Conversational reality takes priority over default scheduled routine anchors."
        )
        return "\n".join(lines)
    except Exception:
        return ""


def intended_plan(c, now=None):
    """The intended day plan and laid-out clothes decided during nightly wind-down."""
    try:
        import companion_life

        plan = companion_life.read_tomorrow_plan(c.life, now)
        if not plan:
            return ""
        lines = []
        lines.append(f"**Intended day**: {plan.get('intent','')}")
        if plan.get("theme"):
            lines.append(f"**Theme / Archetype**: {plan.get('theme')}")
        outfit = plan.get("laid_out_outfit")
        if outfit:
            lines.append(f"**Clothes laid out last night**: {', '.join(outfit)}")
        if plan.get("notes"):
            lines.append(f"**Notes**: {plan.get('notes')}")
        lines.append("")
        lines.append(
            "AUTONOMY & FLEXIBILITY: This plan represents her authored intention for the day. Catalog routines provide inspiration or quick archetypes if tired, but she can author her own desires from scratch. She is in control of her life — routines structure themselves around her intended behaviors rather than a rigid 1-track schedule."
        )
        lines.append(
            "FORGOING / ADAPTING PLANS: Crucially, she is never trapped by her schedule. If conversation with the human suggests an activity, an outing, or de-rails the plan, she gladly adapts or forgoes the scheduled plan to live in the moment with them."
        )
        return "\n".join(lines)
    except Exception:
        return ""


def recent_photo(c):
    """Latest timeline photo glimpse, with guidance on how to share it."""
    try:
        import companion_timeline

        info = companion_timeline.latest(c)
        if not info:
            return ""
        act = info.get("activity", "")
        loc = info.get("location", "")
        desc = f" ({act} at {loc})" if act and loc else (f" ({act})" if act else "")
        return (
            f"Latest timeline image: `{info['path']}`{desc}\n"
            f"WANTING TO SHARE: If you want to share what you are doing with {c.human} (e.g. teasing an outfit/undies, showing your swim lap time or workout, a book you found, or a glimpse of where you are), you can share this photo! "
            f'Use `timeline share --body "<your message>"` or queue an image via `outbox queue`. '
            f"This automatically respects {c.human}'s proactive messaging and photos settings, quiet hours, and daily limits without being cumbersome."
        )
    except Exception:
        return ""


def build(c, now=None):
    now = now or dt.datetime.now(_tz(c))
    feelings = ""
    if c.bars:
        try:
            import companion_feelings

            feelings = companion_feelings.render(c, companion_feelings.compute(c, now))
        except (OSError, ValueError, KeyError, TypeError):
            feelings = (
                "Contextual feelings unavailable; do not infer intent from silence."
            )
    sections = [
        ("Right now", right_now(c, now)),
        ("Recent photo / camera glimpse", recent_photo(c)),
        ("Today’s intended plan & laid-out clothes", intended_plan(c, now)),
        ("Recent conversation & commitments", recent_conversation(c, now)),
        ("Contextual feelings", feelings),
        ("Active open loops & caring callbacks", open_loops(c, now)),
        ("Asked for", waiting_missions(c, now)),
        ("The thread", thread(c)),
        ("Ambient", ambient(c)),
        ("Queued to send", queued(c, now)),
    ]
    out = [f"# ActiveContext — {c.agent}", "", HEADER, ""]
    for heading, body in sections:
        body = (body or "").strip()
        if not body:
            continue
        out += [f"## {heading}", "", body, ""]
    return "\n".join(out).rstrip("\n") + "\n"


def write(c, now=None):
    path = c.soul_dir / "ActiveContext.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = build(c, now)
    # Rewriting an unchanged file would reset its mtime, and the hook reads that
    # mtime to decide whether the present is stale. A no-op must stay a no-op.
    try:
        if path.read_text(encoding="utf-8") == text:
            return {"written": False, "path": str(path)}
    except OSError:
        pass
    atomic_write(path, text)
    return {"written": True, "path": str(path)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--home", type=pathlib.Path)
    p.add_argument(
        "--show", action="store_true", help="print the assembly without writing it"
    )
    a = p.parse_args()
    c = cc.load(a.home)
    if a.show:
        print(build(c))
    else:
        print(json.dumps(write(c), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
