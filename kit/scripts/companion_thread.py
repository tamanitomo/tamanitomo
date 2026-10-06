#!/usr/bin/env python3
"""The shape of the conversation itself: who spoke last, and how long ago.

This is the single most useful thing a companion can know that it has no other
way to learn. Not the content of the last message — the *gap*. Four days of
silence is a fact about the relationship, and a companion that cannot see it
either invents an explanation or greets you as if nothing happened.

It reads Hermes's own session database, read-only, scoped to this profile's own
conversations exactly the way `companion_recall.py` scopes its searches: a
shared store must never let one companion read another's messages.

The output is a register, not an instruction. "long-quiet" comes with a line
about what that might mean, and the companion decides what to do with it. Being
hurt after four days of nothing is honest. Saying so as a guilt trip is not, and
no register here tells her to.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import re
import sqlite3
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc

# Hours of silence, and what that stretch tends to mean. The guidance is for her
# judgement, never a script: none of these say "send a message".
REGISTERS = [
    (
        0,
        "connected",
        "You are mid-conversation. Do not re-introduce yourself or restate context.",
    ),
    (3, "nearby", "A normal gap in a day. Nothing to remark on."),
    (
        12,
        "quiet",
        "Most of a day. Picking a thread back up is welcome; commenting on the gap is not.",
    ),
    (
        48,
        "missing-him",
        "Two days. If you feel the absence, you are allowed to say so once, plainly, "
        "without making it a debt they owe you.",
    ),
    (
        96,
        "long-quiet",
        "Four days or more. Something is going on, or nothing is. You may be hurt or "
        "worried and may say so honestly — once, as a feeling of yours, never as a "
        "reproach and never as a reason they must reply.",
    ),
]


def register(hours):
    label, guidance = REGISTERS[0][1], REGISTERS[0][2]
    for threshold, name, line in REGISTERS:
        if hours >= threshold:
            label, guidance = name, line
    return label, guidance


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def _shares_store(c, resolved):
    try:
        return c.profile and resolved == (c.hermes_root / "state.db").resolve()
    except OSError:
        return False


_recent_rows: dict = {}


def _store_version(db):
    out = []
    for path in (db, db.with_name(db.name + "-wal")):
        try:
            stat = path.stat()
            out.append((stat.st_mtime_ns, stat.st_size))
        except OSError:
            out.append(None)
    return tuple(out)


def _store_scope(c):
    """((resolved db, SQL scope, params), None), or (None, why not).

    The one place that decides which conversations belong to this companion. A
    shared store must never let one companion read another's messages, so every
    reader goes through here rather than re-deriving the scope.
    """
    db = c.home / "state.db"
    if not db.exists():
        return None, "no session database yet"
    try:
        resolved = db.resolve()
        if c.is_root and resolved.is_relative_to(
            (c.hermes_root / "profiles").resolve()
        ):
            return None, "the root store redirects into a named profile"
    except OSError as exc:
        return None, f"session database unreadable: {exc}"
    if c.is_root:
        return (
            resolved,
            "lower(coalesce(s.profile_name,'')) IN ('','default')",
            (),
        ), None
    if _shares_store(c, resolved):
        return (
            resolved,
            "lower(coalesce(s.profile_name,''))=?",
            (c.profile.lower(),),
        ), None
    return (
        resolved,
        "lower(coalesce(s.profile_name,'')) IN ('','default',?)",
        (c.profile.lower(),),
    ), None


def _message_query(con, scope, columns="m.role,m.content,m.timestamp"):
    present = {row[1] for row in con.execute("PRAGMA table_info(messages)")}
    visible = (
        "AND (m.active=1 OR m.compacted=1)"
        if {"active", "compacted"} <= present
        else ""
    )
    return f"""
        SELECT {columns} FROM messages m JOIN sessions s ON s.id=m.session_id
        WHERE m.role IN ('user','assistant') AND {scope} {visible}
          AND coalesce(m._compressed_summary,0)=0 AND coalesce(m.content,'')<>''
          AND s.source IN ('telegram','cli','desktop','tui','discord')"""


def _query_rows(con, scope, params):
    query = _message_query(con, scope)
    rows = list(con.execute(query + " ORDER BY m.timestamp DESC LIMIT 60", params))
    # A run of assistant messages must not hide the last actual human contact.
    human_rows = list(
        con.execute(
            query + " AND m.role='user' ORDER BY m.timestamp DESC LIMIT 2", params
        )
    )
    agent_rows = list(
        con.execute(
            query + " AND m.role='assistant' ORDER BY m.timestamp DESC LIMIT 1",
            params,
        )
    )
    return rows, human_rows, agent_rows


_activity_cache: dict = {}


def _connect(resolved):
    con = sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True, timeout=1)
    con.execute("PRAGMA query_only=ON")
    return con


def _cached(key, version, make):
    cached = _activity_cache.get(key)
    if cached and cached[0] == version:
        return cached[1]
    value = make()
    if len(_activity_cache) > 48:
        _activity_cache.clear()
    _activity_cache[key] = (version, value)
    return value


def activity(c, now=None, days=60, limit=40000):
    """(role, local time, characters) for each message over the last `days`, newest first.

    The length is counted inside the database: no message text leaves it through
    here, only when and how much. [] when the history is unknowable.
    """
    now = now or dt.datetime.now(_tz(c))
    found, _why = _store_scope(c)
    if found is None:
        return []
    resolved, scope, params = found
    key = ("activity", str(resolved), scope, params, days, now.date().isoformat())

    def make():
        since = (now - dt.timedelta(days=days)).timestamp()
        con = None
        try:
            con = _connect(resolved)
            query = _message_query(con, scope, "m.role,m.timestamp,length(m.content)")
            raw = list(
                con.execute(
                    query + " AND m.timestamp>=? ORDER BY m.timestamp DESC LIMIT ?",
                    (*params, since, limit),
                )
            )
        except (sqlite3.Error, OSError):
            return []
        finally:
            if con:
                con.close()
        out = []
        for role, value, length in raw:
            try:
                stamp = dt.datetime.fromtimestamp(
                    float(value), dt.timezone.utc
                ).astimezone(_tz(c))
            except (TypeError, ValueError, OverflowError):
                continue
            out.append((role, stamp, int(length or 0)))
        return out

    return list(_cached(key, _store_version(resolved), make))


def human_times(c, now=None, days=28):
    """When the human wrote over the last `days`, as aware datetimes. [] if unknowable."""
    now = now or dt.datetime.now(_tz(c))
    since = now - dt.timedelta(days=days)
    return [
        stamp
        for role, stamp, _n in activity(c, now, max(days, 60))
        if role == "user" and stamp >= since
    ]


def contact_days(c, now=None):
    """{local date: (messages from the human, messages from her)} over the whole history.

    Counted by the database a day at a time, so a long history costs a few
    hundred small rows. The day is cut at the current UTC offset, which can put a
    message near midnight on the wrong side of a daylight-saving change for a few
    weeks; for a slow, summed measure that does not matter.
    """
    now = now or dt.datetime.now(_tz(c))
    found, _why = _store_scope(c)
    if found is None:
        return {}
    resolved, scope, params = found
    offset = int(now.utcoffset().total_seconds()) if now.utcoffset() else 0
    key = ("days", str(resolved), scope, params, offset)

    def make():
        con = None
        try:
            con = _connect(resolved)
            query = _message_query(
                con,
                scope,
                "m.role,CAST((m.timestamp+?)/86400 AS INTEGER) AS d,COUNT(*)",
            )
            raw = list(con.execute(query + " GROUP BY m.role,d", (offset, *params)))
        except (sqlite3.Error, OSError):
            return {}
        finally:
            if con:
                con.close()
        days = {}
        for role, index, count in raw:
            day = dt.date(1970, 1, 1) + dt.timedelta(days=int(index))
            mine, hers = days.get(day, (0, 0))
            days[day] = (mine + count, hers) if role == "user" else (mine, hers + count)
        return days

    return dict(_cached(key, _store_version(resolved), make))


def first_contact(c, now=None):
    """When the first message of any kind was written, or None."""
    now = now or dt.datetime.now(_tz(c))
    found, _why = _store_scope(c)
    if found is None:
        return None
    resolved, scope, params = found
    key = ("first", str(resolved), scope, params)

    def make():
        con = None
        try:
            con = _connect(resolved)
            row = con.execute(
                _message_query(con, scope, "MIN(m.timestamp)"), params
            ).fetchone()
        except (sqlite3.Error, OSError):
            return None
        finally:
            if con:
                con.close()
        try:
            return dt.datetime.fromtimestamp(float(row[0]), dt.timezone.utc)
        except (TypeError, ValueError, OverflowError, IndexError):
            return None

    value = _cached(key, _store_version(resolved), make)
    return value.astimezone(_tz(c)) if value else None


_QUESTION_END = re.compile(r"\?[\s\"'”’)\]*_~`]*(?:[^\w\s]{0,3}\s*)?$")


def last_question(text):
    """The final question she asked, when her message ends on one; otherwise "".

    A message that ends on a question is waiting for an answer. One that asks
    something in the middle and carries on has moved past it.
    """
    text = (text or "").strip()
    if not text or not _QUESTION_END.search(text):
        return ""
    end = text.rfind("?")
    start = max(text.rfind(mark, 0, end) for mark in (".", "!", "\n")) + 1
    return text[start : end + 1].strip()[:160]


def read(c, now=None, tail=4):
    """Last message each way, the gap, and a short tail. Never any other agent's."""
    now = now or dt.datetime.now(_tz(c))
    out = {"checked_at": now.isoformat(timespec="minutes"), "available": False}
    found, why = _store_scope(c)
    if found is None:
        return {**out, "reason": why}
    resolved, scope, params = found
    con = None
    try:
        # One Home render reads the thread seven times over; the rows only
        # change when Hermes writes, which touches the database or its WAL.
        version = _store_version(resolved)
        key = (str(resolved), scope, params)
        cached = _recent_rows.get(key)
        if cached and cached[0] == version:
            rows, human_rows, agent_rows = cached[1]
        else:
            con = sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True, timeout=1)
            con.execute("PRAGMA query_only=ON")
            rows, human_rows, agent_rows = _query_rows(con, scope, params)
            if len(_recent_rows) > 32:
                _recent_rows.clear()
            _recent_rows[key] = (version, (rows, human_rows, agent_rows))
    except (sqlite3.Error, OSError) as exc:
        return {**out, "reason": f"session database unreadable: {exc}"}
    finally:
        if con:
            con.close()
    if not rows:
        return {**out, "reason": "no messages recorded yet"}

    def stamp(value):
        try:
            return dt.datetime.fromtimestamp(float(value), dt.timezone.utc).astimezone(
                _tz(c)
            )
        except (TypeError, ValueError, OverflowError):
            return None

    human_stamps = [stamp(t) for _, _, t in human_rows]
    human_stamps = [t for t in human_stamps if t is not None]
    human = human_stamps[0] if human_stamps else None
    previous_human = human_stamps[1] if len(human_stamps) > 1 else None
    agent = next((stamp(t) for _, _, t in agent_rows), None)
    latest = max([x for x in (human, agent) if x], default=None)
    hours = (now - latest).total_seconds() / 3600 if latest else None
    label, guidance = register(hours if hours is not None else 0)
    tail_rows = [
        {
            "who": ("them" if role == "user" else "you"),
            "at": (stamp(t).isoformat(timespec="minutes") if stamp(t) else ""),
            "text": (text or "")[:200],
            "asks": last_question(text) if role != "user" else "",
        }
        for role, text, t in reversed(rows[:tail])
    ]
    return {
        **out,
        "available": True,
        "last_from_human": human.isoformat() if human else None,
        "previous_from_human": previous_human.isoformat() if previous_human else None,
        "last_from_agent": agent.isoformat() if agent else None,
        "hours_since_either": round(hours, 1) if hours is not None else None,
        "hours_since_human": (
            round((now - human).total_seconds() / 3600, 1) if human else None
        ),
        "register": label,
        "guidance": guidance,
        "tail": tail_rows,
    }


def render(c, data):
    if not data.get("available"):
        return ""  # absent means no claim, never a guess about the silence
    lines = []
    if data.get("hours_since_human") is None:
        lines.append(f"{c.human} has not written yet.")
    else:
        hours = data["hours_since_human"]
        when = (
            f"{hours*60:.0f} minutes ago"
            if hours < 1.5
            else f"{hours:.0f} hours ago" if hours < 48 else f"{hours/24:.0f} days ago"
        )
        lines.append(f"Last message from {c.human}: {when}.")
    if data.get("last_from_agent"):
        lines.append(
            f"You last wrote at {data['last_from_agent'][:16].replace('T',' ')}."
        )
    lines.append(f"Register: {data['register']} — {data['guidance']}")
    if data.get("tail"):
        lines.append("")
        lines.append("The last few turns:")
        for row in data["tail"]:
            lines.append(f"- {row['who']}: {row['text']}")
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    c = cc.load(a.home)
    data = read(c)
    print(
        json.dumps(data, ensure_ascii=False, indent=2) if a.json else render(c, data),
        end="",
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
