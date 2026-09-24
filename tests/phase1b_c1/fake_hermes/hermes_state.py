"""TEST DOUBLE of Hermes's SessionDB commit point -- never shipped, never a model.

Reproduces only what the C1 executor depends on: `_execute_write(self, fn,
patience_s=None)` runs `fn(conn)` inside BEGIN IMMEDIATE, commits, and re-runs the
WHOLE callback on a locked/busy error (hermes_state.py:773-858 at 0e9fc2cc15).
It is a local double: it is NOT evidence for Hermes behaviour (O-2..O-6); the
pinned-Hermes lane is. It exists so crash tests can stop at exact boundaries.
"""
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, source TEXT NOT NULL, started_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id), role TEXT NOT NULL,
  content TEXT, tool_calls TEXT, timestamp REAL NOT NULL, finish_reason TEXT, observed INTEGER DEFAULT 0,
  _compressed_summary INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
  compacted INTEGER NOT NULL DEFAULT 0, display_kind TEXT);
"""


class SessionDB:
    def __init__(self, db_path):
        self._conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False, timeout=1)
        self._conn.executescript(SCHEMA)
        self._lock = threading.RLock()

    def _execute_write(self, fn, patience_s=None):
        deadline = time.monotonic() + (patience_s or 5)
        while True:
            try:
                with self._lock:
                    self._conn.execute('BEGIN IMMEDIATE')
                    try:
                        result = fn(self._conn)
                        self._conn.execute('COMMIT')
                    except BaseException:
                        try:
                            self._conn.execute('ROLLBACK')
                        except sqlite3.Error:
                            pass
                        raise
                return result
            except sqlite3.OperationalError as exc:
                if ('locked' in str(exc) or 'busy' in str(exc)) and time.monotonic() < deadline:
                    time.sleep(0.01)
                    continue
                raise

    def create_session(self, session_id, source='cli'):
        def write(conn):
            conn.execute('INSERT INTO sessions (id, source, started_at) VALUES (?, ?, ?) '
                         'ON CONFLICT(id) DO NOTHING', (session_id, source, time.time()))
            return session_id
        return self._execute_write(write)

    def append_message(self, session_id, role, content, finish_reason=None, tool_calls=None,
                       display_kind=None, summary=0, observed=0):
        def write(conn):
            cur = conn.execute(
                'INSERT INTO messages (session_id, role, content, tool_calls, timestamp, finish_reason, '
                'display_kind, _compressed_summary, observed) VALUES (?,?,?,?,?,?,?,?,?)',
                (session_id, role, content, tool_calls, time.time(), finish_reason, display_kind, summary,
                 observed))
            return cur.lastrowid
        return self._execute_write(write)

    def clone_tail(self, source_session, target_session):
        def write(conn):
            conn.execute('INSERT INTO sessions (id, source, started_at) VALUES (?, ?, ?)',
                         (target_session, 'cli', time.time()))
            conn.execute('INSERT INTO messages (session_id, role, content, timestamp) '
                         'SELECT ?, role, content, timestamp FROM messages WHERE session_id=?',
                         (target_session, source_session))
        return self._execute_write(write)
