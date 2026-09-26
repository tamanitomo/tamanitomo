#!/usr/bin/env python3
"""A fresh conversation every morning, without losing a thing.

Hermes compresses a long chat to keep it inside the model's window, and each
pass loses a little: by the fourth, it warns that accuracy may degrade and
suggests /new. This Hermes never starts a new session on a clock -- its
`session_reset` setting is inert -- and a person should not have to know to
type /new. So once a night, while the companion is asleep:

  1. nothing happens if the human wrote in the last two hours;
  2. the check-in reflection is flagged, so the conversation's details are
     recorded before anything ends;
  3. the chat's current session -- the newest link of its compression chain --
     is ended through Hermes's own SessionDB.end_session. The gateway already
     treats a routed session that is ended in state.db as over, and starts a
     fresh one on the next message (its #54878 self-heal), loading SOUL.md anew.

Nothing is deleted: the old session stays searchable for the morning journal
and for recall, and continuity carries over through the ledgers, the journal,
the present state and the per-turn hook, whose first turn picks the thread up.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import pathlib
import sqlite3
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc

QUIET_MINUTES = 120
CHAT_PLATFORMS = (
    "telegram",
    "discord",
    "slack",
    "signal",
    "whatsapp",
    "matrix",
    "weixin",
    "feishu",
    "dingtalk",
    "sms",
    "email",
)
END_REASON = "session_reset"


def _tz(c):
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(c.timezone)
    except Exception:
        return dt.timezone.utc


def routes(c):
    """The gateway's chat routes for this profile: {session_key: session_id}."""
    try:
        data = json.loads(
            (c.home / "sessions/sessions.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}
    entries = data.get("entries", data) if isinstance(data, dict) else {}
    # Direct messages with the human only. A group channel or thread is somebody
    # else's conversation too, and is never reset from here.
    return {
        k: v["session_id"]
        for k, v in entries.items()
        if isinstance(v, dict)
        and v.get("session_id")
        and ":dm:" in k
        and str(v.get("platform", "")).lower() in CHAT_PLATFORMS
    }


def _db(c):
    return sqlite3.connect(
        pathlib.Path(c.home / "state.db").resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=2,
    )


def chain_tip(con, session_id):
    """The newest session a compression chain has moved to, and every open link."""
    open_links = []
    current = session_id
    seen = set()
    while current and current not in seen:
        seen.add(current)
        row = con.execute(
            "select end_reason from sessions where id=?", (current,)
        ).fetchone()
        if row and row[0] is None:
            open_links.append(current)
        child = con.execute(
            "select id from sessions where parent_session_id=? order by started_at desc limit 1",
            (current,),
        ).fetchone()
        current = child[0] if child else None
    return open_links


def last_human(con, platforms=CHAT_PLATFORMS):
    marks = ",".join("?" * len(platforms))
    row = con.execute(
        f"""select max(m.timestamp) from messages m join sessions s on s.id=m.session_id
        where m.role='user' and lower(coalesce(s.source,'')) in ({marks})""",
        platforms,
    ).fetchone()
    return float(row[0]) if row and row[0] else None


def hermes_python():
    """The interpreter Hermes itself runs, so its own SessionDB does the ending."""
    from companion_platform import hermes_command
    import shutil

    found = shutil.which(hermes_command()[0])
    if not found:
        return None
    exe = pathlib.Path(found)
    try:
        text = (
            exe.read_text(encoding="utf-8", errors="replace")
            if exe.stat().st_size < 20000
            else ""
        )
    except OSError:
        text = ""
    import re

    m = re.search(r'exec\s+"?([^"\s]+/bin/)hermes"?', text)
    directories = ([pathlib.Path(m.group(1))] if m else []) + [exe.resolve().parent]
    names = (
        ("python.exe", "python")
        if sys.platform == "win32"
        else ("python", "python.exe")
    )
    for directory in directories:
        for name in names:
            candidate = directory / name
            if candidate.is_file():
                return str(candidate)
    return None


def end_sessions(c, ids, python=None):
    python = python or hermes_python()
    if not python:
        raise ValueError("cannot find the Python that Hermes runs")
    script = (
        "import sys,pathlib\nfrom hermes_state import SessionDB\n"
        "db=SessionDB(pathlib.Path(sys.argv[1]))\n"
        "for sid in sys.argv[3:]:db.end_session(sid,sys.argv[2])\n"
    )
    r = subprocess.run(
        [
            python,
            "-c",
            script,
            str(pathlib.Path(c.home / "state.db").resolve()),
            END_REASON,
            *ids,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "HERMES_HOME": str(c.home)},
    )
    if r.returncode:
        raise ValueError(
            "Hermes could not end the session: " + (r.stderr or "").strip()[-200:]
        )


def run(c, now=None, apply=True, ender=None):
    now = (now or dt.datetime.now(_tz(c))).astimezone(_tz(c))
    if c.agent_type == "worker":
        return {"rolled": False, "reason": "workers keep their sessions"}
    mapped = routes(c)
    if not mapped:
        return {"rolled": False, "reason": "no chat session to roll over"}
    try:
        con = _db(c)
        try:
            last = last_human(con)
            targets = {key: chain_tip(con, sid) for key, sid in mapped.items()}
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"rolled": False, "reason": f"state.db unreadable: {exc}"}
    if last and now.timestamp() - last < QUIET_MINUTES * 60:
        return {
            "rolled": False,
            "reason": f"{c.human} wrote {int((now.timestamp()-last)//60)} minutes ago",
        }
    ids = [sid for links in targets.values() for sid in links]
    if not ids:
        return {"rolled": False, "reason": "the chat is already fresh"}
    if not apply:
        return {"rolled": False, "would_end": ids}
    try:
        import companion_checkin

        # The rollover reader has already established the human conversation;
        # this direct DB close has no live on_session_end hook to carry a platform.
        companion_checkin.flag(c, now, "nightly-rollover", trusted=True)
    except (OSError, ValueError):
        pass
    (ender or end_sessions)(c, ids)
    row = {
        "at": now.isoformat(timespec="seconds"),
        "ended": ids,
        "routes": list(targets),
    }
    log = c.life / "rollover.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return {"rolled": True, **row}


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    c = cc.load(a.home)
    out = run(c, apply=not a.dry_run)
    if a.json or a.dry_run:
        print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except (ValueError, OSError) as e:
        print(f"rollover: {e}", file=sys.stderr)
        sys.exit(1)
