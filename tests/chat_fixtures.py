"""Synthetic message-source fixtures for the chat projection (Phase 1A).

BOUNDARY: this is the *source store* boundary -- a Hermes state.db file, built
here with the sessions/messages columns of the installed Hermes schema, so the
read-only adapter (kit/app/chat_sources.py) can be exercised without a live
store. It is not a provider or transport fixture; see tests/mock_provider.py.

The DDL is copied from Hermes hermes_state_common.SCHEMA_SQL (schema_version 30,
hermes-agent 0e9fc2cc15, 2026-09-24). Every row written here is invented: the
companion is Nova, the owner is Robin, the stranger is Kit.
"""
from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

SESSIONS_DDL = """CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, source TEXT NOT NULL, user_id TEXT, session_key TEXT, chat_id TEXT, chat_type TEXT,
    thread_id TEXT, display_name TEXT, origin_json TEXT, expiry_finalized INTEGER DEFAULT 0, model TEXT,
    model_config TEXT, system_prompt TEXT, system_prompt_hash TEXT, parent_session_id TEXT, started_at REAL NOT NULL,
    ended_at REAL, end_reason TEXT, message_count INTEGER DEFAULT 0, tool_call_count INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0, reasoning_tokens INTEGER DEFAULT 0, cwd TEXT, git_branch TEXT,
    git_repo_root TEXT, git_metadata_generation INTEGER NOT NULL DEFAULT 0, billing_provider TEXT,
    billing_base_url TEXT, billing_mode TEXT, estimated_cost_usd REAL, actual_cost_usd REAL, cost_status TEXT,
    cost_source TEXT, pricing_version TEXT, title TEXT, title_source TEXT, last_activity_at REAL,
    last_activity_description TEXT, last_activity_provenance TEXT, api_call_count INTEGER DEFAULT 0,
    handoff_state TEXT, handoff_platform TEXT, handoff_error TEXT, compression_failure_cooldown_until REAL,
    compression_failure_error TEXT, compression_fallback_streak INTEGER NOT NULL DEFAULT 0,
    compression_ineffective_count INTEGER NOT NULL DEFAULT 0, compression_recovery_deadline REAL,
    profile_name TEXT, rewind_count INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0,
    pinned INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0, last_read_at REAL, tool_names TEXT);"""

MESSAGES_DDL = """CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id), role TEXT NOT NULL,
    content TEXT, tool_call_id TEXT, tool_calls TEXT, tool_name TEXT, effect_disposition TEXT,
    timestamp REAL NOT NULL, token_count INTEGER, finish_reason TEXT, reasoning TEXT, reasoning_content TEXT,
    reasoning_details TEXT, codex_reasoning_items TEXT, codex_message_items TEXT, platform_message_id TEXT,
    observed INTEGER DEFAULT 0, _compressed_summary INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
    compacted INTEGER NOT NULL DEFAULT 0, api_content TEXT, display_kind TEXT, display_metadata TEXT);"""

OWNER_TELEGRAM = '4242'
STRANGER_TELEGRAM = '9999'


class HermesStore:
    """A Hermes-shaped state.db the tests write to, standing in for Hermes."""

    def __init__(self, home: Path):
        self.path = Path(home) / 'state.db'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript(SESSIONS_DDL + MESSAGES_DDL)

    @contextlib.contextmanager
    def db(self):
        con = sqlite3.connect(self.path)
        try:
            with con:
                yield con
        finally:
            con.close()

    def session(self, ident, source, *, profile='nova', user_id=None, chat_id=None, chat_type=None, started=1.0):
        with self.db() as db:
            db.execute('INSERT INTO sessions(id,source,user_id,chat_id,chat_type,started_at,profile_name) VALUES (?,?,?,?,?,?,?)',
                       (ident, source, user_id, chat_id, chat_type, started, profile))
        return ident

    def _platform_id(self, db, session, role):
        """Hermes records the platform's message id on every gateway user turn
        (gateway/run_turn.py); a Telegram user row gets one unless a test
        passes platform_message_id=None to write a row that has none."""
        source = db.execute('SELECT source FROM sessions WHERE id=?', (session,)).fetchone()
        if role != 'user' or not source or source[0] != 'telegram':
            return None
        self._next_platform_id = getattr(self, '_next_platform_id', 1000) + 1
        return str(self._next_platform_id)

    def say(self, session, role, content, ts, **cols):
        with self.db() as db:
            if 'platform_message_id' not in cols and (pid := self._platform_id(db, session, role)):
                cols['platform_message_id'] = pid
        names = ['session_id', 'role', 'content', 'timestamp', *cols]
        with self.db() as db:
            cur = db.execute(f"INSERT INTO messages({','.join(names)}) VALUES ({','.join('?' * len(names))})",
                             (session, role, content, ts, *cols.values()))
            return cur.lastrowid

    def update(self, ident, **cols):
        with self.db() as db:
            db.execute(f"UPDATE messages SET {','.join(k + '=?' for k in cols)} WHERE id=?", (*cols.values(), ident))

    def delete(self, ident):
        with self.db() as db:
            db.execute('DELETE FROM messages WHERE id=?', (ident,))

    def many(self, session, rows):
        with self.db() as db:
            db.executemany('INSERT INTO messages(session_id,role,content,timestamp,platform_message_id) VALUES (?,?,?,?,?)',
                           [(session, role, content, ts, self._platform_id(db, session, role)) for role, content, ts in rows])


def standard_sessions(store):
    """The sessions most tests need: every kind of source the adapter must
    include or exclude, for profile nova, plus one belonging to rowan."""
    store.session('web', 'cli', started=1)                       # started from the workspace
    store.session('term', 'cli', started=2)                      # typed at a local terminal
    store.session('tg', 'telegram', user_id=OWNER_TELEGRAM, chat_id=OWNER_TELEGRAM, chat_type='dm', started=3)
    store.session('tg-old', 'telegram', user_id=OWNER_TELEGRAM, chat_id=OWNER_TELEGRAM, started=4)  # pre-chat_type row
    store.session('stranger', 'telegram', user_id=STRANGER_TELEGRAM, chat_id=STRANGER_TELEGRAM, chat_type='dm', started=5)
    store.session('group', 'telegram', user_id=OWNER_TELEGRAM, chat_id='-100777', chat_type='group', started=6)
    store.session('dc', 'discord', user_id='d-1', chat_id='d-1', chat_type='dm', started=7)
    store.session('job', 'cron', started=8)
    store.session('sub', 'subagent', started=9)
    store.session('gw-cli', 'cli', chat_id='x-1', started=10)    # a cli-labelled row with a gateway chat
    store.session('rowan-tg', 'telegram', profile='rowan', user_id=OWNER_TELEGRAM, chat_id=OWNER_TELEGRAM,
                  chat_type='dm', started=11)
