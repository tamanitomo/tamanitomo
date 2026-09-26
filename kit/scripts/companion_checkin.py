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


def flag(c, now=None, session_id=""):
    """A session ended. Cheap, and safe to call from a hook."""
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
    would ever look at it.
    """
    now = now or dt.datetime.now(_tz(c))
    with file_lock(path_for(c).with_suffix(".json.lock")):
        state = read(c)
        pending = int(state.get("pending", 0) or 0)
        claimed = state.pop("claimed", None)
        state["pending"] = 0 if claimed is None else max(0, pending - int(claimed))
        state["last_reflected"] = now.isoformat()
        atomic_write(path_for(c), json.dumps(state, ensure_ascii=False, indent=2))
    return state


def fingerprint(c):
    """Stable bytes for --monitor-script. Changes only when there is something to do.

    No clock in here at all: this is the one gate that should stay silent
    indefinitely when nobody is talking. It notes how many sessions it has seen,
    so the run it triggers clears exactly those.
    """
    with file_lock(path_for(c).with_suffix(".json.lock")):
        state = read(c)
        pending = int(state.get("pending", 0) or 0)
        if pending and state.get("claimed") != pending:
            state["claimed"] = pending
            atomic_write(path_for(c), json.dumps(state, ensure_ascii=False, indent=2))
    return (
        f"pending {pending}\nlast_end {state.get('last_end','') if pending else ''}\n"
    )


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    p.add_argument(
        "mode",
        choices=["flag", "fingerprint", "clear", "status"],
        nargs="?",
        default="fingerprint",
    )
    a = p.parse_args()
    c = cc.load(a.home)
    if a.mode == "fingerprint":
        sys.stdout.write(fingerprint(c))
    elif a.mode == "flag":
        # Called from a Hermes hook: say nothing, ever. A hook that prints is a
        # hook that ends up in somebody's chat.
        try:
            flag(c)
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
