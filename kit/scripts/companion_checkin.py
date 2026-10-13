#!/usr/bin/env python3
"""Reflect within minutes of a conversation, not at four in the morning.

The daily job is the right place for the shape of a day. It is the wrong place
for "he mentioned his sister is called Bee" — twelve hours later, that detail is
competing with everything else that happened, and the session it came from may
already have been compacted.

So: when a session ends, Hermes runs `session_end` and this writes a flag. A
cron job gated by `--monitor-script` on that flag then runs a small reflection
within a few minutes, and is suppressed entirely the rest of the time. Nothing
runs when nothing has been said.

Two modes, matching the two things Hermes needs:

  flag        called from the session_end hook; records that a session ended
  fingerprint printed for --monitor-script; changes only when a new session has
              ended since the last reflection, so the job runs once per
              conversation rather than every tick
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
from companion_platform import atomic_write, file_lock


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def path_for(c):
    return c.life / "session-flag.json"


def read(c):
    try:
        return json.loads(path_for(c).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"pending": 0, "last_end": "", "last_reflected": ""}


OWNER_PLATFORMS = frozenset({"cli", "desktop", "tui", "telegram"})


def flag(c, now=None, session_id="", platform="", trusted=False):
    """A session ended. Cheap, and safe to call from a hook.

    Only a session Hermes attributes to an owner-facing platform re-arms the
    job. Without this, the check-in's own reflection turn ends on platform
    'cron' and its session_end flags a new conversation, so the job re-arms
    itself and never goes quiet -- it was never told the difference between a
    real conversation ending and its own turn ending. An unset or unrecognised
    platform is treated as internal, not guessed as owner speech.

    `trusted=True` is for the rare internal caller (nightly rollover) that has
    already established real human activity by reading the session DB itself,
    rather than relaying an on_session_end payload; it is never set from hook
    input.
    """
    if not trusted and str(platform or "") not in OWNER_PLATFORMS:
        return read(c)
    now = now or dt.datetime.now(_tz(c))
    with file_lock(path_for(c).with_suffix(".json.lock")):
        state = read(c)
        state["pending"] = int(state.get("pending", 0)) + 1
        state["last_end"] = now.isoformat()
        if session_id:
            state["last_session"] = str(session_id)[:120]
        atomic_write(path_for(c), json.dumps(state, ensure_ascii=False, indent=2))
    return state


def clear(c, now=None):
    """A reflection happened. Called by the job itself once it has recorded.

    It clears the sessions the job was started for -- the count its monitor tick
    saw -- not whatever is pending by the time it finishes. Zeroing the counter
    erased a conversation that ended while the reflection was running, and nothing
    would ever look at it. What it covered is kept, so the next pre-read starts
    where this one ended.
    """
    now = now or dt.datetime.now(_tz(c))
    with file_lock(path_for(c).with_suffix(".json.lock")):
        state = read(c)
        pending = int(state.get("pending", 0) or 0)
        claimed = state.pop("claimed", None)
        state["pending"] = 0 if claimed is None else max(0, pending - int(claimed))
        state["last_reflected"] = now.isoformat()
        if state.get("through"):
            state["covered"] = state["through"]
        atomic_write(path_for(c), json.dumps(state, ensure_ascii=False, indent=2))
    return state


# A conversation is over when it has been quiet this long. Hermes ends a session
# after every reply on a chat platform, so the flag went up after each message and
# the reflection ran in the middle of the conversation -- thirty-one times in one
# day for one companion, each a full model run, mostly finding nothing new.
SETTLE_MINUTES = 20


def _stamp(c, value):
    try:
        when = dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=_tz(c))


def fingerprint(c, now=None):
    """Stable bytes for --monitor-script. Changes only when there is something to do.

    It names the end of the last conversation that has settled, and nothing
    else: so it moves once a conversation has been quiet for SETTLE_MINUTES, and
    not again when the reflection clears the flag. (Hermes wakes the job on any
    change of these bytes, so a fingerprint that went back to "nothing pending"
    after each clear paid for a second run with nothing to do.) It notes how many
    sessions it has seen, so the run it triggers clears exactly those.
    """
    now = now or dt.datetime.now(_tz(c))
    with file_lock(path_for(c).with_suffix(".json.lock")):
        state = read(c)
        pending = int(state.get("pending", 0) or 0)
        ended = state.get("last_end") or ""
        when = _stamp(c, ended)
        settled = when is None or now - when >= dt.timedelta(minutes=SETTLE_MINUTES)
        if pending and settled and state.get("through") != (ended or f"#{pending}"):
            state["through"] = ended or f"#{pending}"
            state["claimed"] = pending
            atomic_write(path_for(c), json.dumps(state, ensure_ascii=False, indent=2))
    return f"through {state.get('through', '')}\n"


# The conversation is handed to the run whole, newest kept when it is long.
TRANSCRIPT_CHARS = 16000
MESSAGE_CHARS = 1500


def preread(c, now=None):
    """What the check-in needs and nothing else: the conversation since the last
    check-in, and the threads already open so it updates one rather than adding
    a twin. Without this the run was handed the companion's whole day -- closet,
    laundry rules and every open loop, 80,000 characters -- and still had to go
    looking for the conversation, through files, the database and the kit's own
    source, before giving up."""
    import companion_loops
    import companion_thread

    now = now or dt.datetime.now(_tz(c))
    state = read(c)
    start = (
        _stamp(c, state.get("covered"))
        or _stamp(c, state.get("last_reflected"))
        or now - dt.timedelta(hours=24)
    )
    start = max(start, now - dt.timedelta(days=3))
    out = [
        "[Check-in pre-read: the conversation since your last check-in, already read from",
        " the conversation store. Do not search files or the database for it, and do not read",
        " Tamanitomo's source to work out the rules: run the commands below as written.]",
        "",
    ]
    rows = companion_thread.since(c, start, now)
    if rows is None:
        out.append(
            "[The conversation store could not be read this run. Do not guess at what was said:"
            " leave the check-in pending (do not clear) so the next run tries again.]"
        )
    elif not any(r["who"] == "them" for r in rows):
        out.append(
            f"[{c.human} has said nothing since {start.strftime('%a %H:%M')}. There is nothing to"
            " record: run the clear command and stop.]"
        )
    else:
        lines = []
        for r in rows:
            who = c.human if r["who"] == "them" else c.agent
            text = " ".join(r["text"].split())
            if len(text) > MESSAGE_CHARS:
                text = text[: MESSAGE_CHARS - 1] + "…"
            lines.append(f"**{who}** ({r['at'].strftime('%a %H:%M')}): {text}")
        kept, size = [], 0
        for line in reversed(lines):
            if size + len(line) > TRANSCRIPT_CHARS and kept:
                break
            kept.append(line)
            size += len(line) + 1
        kept.reverse()
        omitted = len(lines) - len(kept)
        heard = sum(1 for r in rows if r["who"] == "them")
        out.append(
            f"[Conversation since {start.strftime('%a %H:%M')}: {len(rows)} messages,"
            f" {heard} from {c.human}"
            + (f"; the {omitted} earliest are left out for length" if omitted else "")
            + ". Only what "
            + c.human
            + " wrote is evidence about "
            + c.human
            + ".]"
        )
        out.extend(kept)
    try:
        import companion_asks

        asked = companion_asks.render(c, now)
        if asked:
            out.append("")
            out.append(asked)
    except (OSError, ValueError):
        pass
    open_loops = companion_loops.loops(c, "open")
    if open_loops:
        out.append("")
        out.append(
            "[Threads already open between you -- update or close one of these (kind update,"
            " with its id) instead of adding a second copy:]"
        )
        for loop in open_loops[-25:]:
            out.append(f"- {loop['id']}: {loop['title'][:100]}")
        if len(open_loops) > 25:
            out.append(f"- …and {len(open_loops) - 25} older ones (`list` shows them).")
    out.append(f"[Local time: {now.isoformat(timespec='minutes')} ({c.timezone})]")
    return "\n".join(out) + "\n"


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    p.add_argument("--platform", default="")
    p.add_argument(
        "mode",
        choices=["flag", "fingerprint", "preread", "clear", "status"],
        nargs="?",
        default="fingerprint",
    )
    a = p.parse_args()
    c = cc.load(a.home)
    if a.mode == "fingerprint":
        sys.stdout.write(fingerprint(c))
    elif a.mode == "preread":
        sys.stdout.write(preread(c))
    elif a.mode == "flag":
        # Called from a Hermes hook: say nothing, ever. A hook that prints is a
        # hook that ends up in somebody's chat.
        try:
            flag(c, platform=a.platform)
        except (OSError, ValueError):
            pass
        print(json.dumps({}))
    elif a.mode == "clear":
        print(json.dumps(clear(c), ensure_ascii=False))
    else:
        print(json.dumps(read(c), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except (ValueError, OSError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
