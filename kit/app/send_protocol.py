"""Shared, standard-library-only pieces of the Phase 1B send protocol (C1 core).

Imported by the app (kit/app/chat_sends.py) AND by the executor, which runs
under Hermes's own interpreter (kit/app/send_executor.py). So: no third-party
imports, no app imports, nothing newer than Python 3.11.

NOT ACTIVATED: used only by the keyed-send routes, which exist only in an app built
with `chat_sends=` (no shipped entry point); see Phase1B_C1_Results.md.

What lives here:
  * the ledger location, schema and connection settings (PHASE1B_DESIGN.md 4.1, 4.2);
  * the ownership guard (`guard.lock`): acceptance, bootstrap and executor
    registration hold it shared, an explicit reset holds it exclusive;
  * how a committed Hermes row is classified from its structural markers,
    including the public/trusted-source eligibility of OWNER rows (review R3 5.2).

The ledger never stores message text, reply text, stream text or stderr.
"""
from __future__ import annotations

import contextlib
import errno
import json
import os
import sqlite3
import time
from pathlib import Path

try:  # POSIX advisory locks. Absent on Windows, where sends are refused (O-8).
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows CI only
    fcntl = None

LEDGER_DIRNAME = '.tamanitomo-sends'
LEDGER_FILE = 'ledger.sqlite3'
LEDGER_ID_FILE = 'ledger.id'
GUARD_FILE = 'guard.lock'
SCHEMA_VERSION = '3'   # 3: send_links + provenance (C1 integration, review R5)

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE sends(
  send_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  client_key TEXT NOT NULL,
  key_time REAL NOT NULL,
  request_digest TEXT NOT NULL,
  destination TEXT NOT NULL CHECK(destination='workspace'),
  requested_session TEXT,
  source_kind TEXT NOT NULL,
  source_namespace TEXT,
  generation TEXT NOT NULL,
  legacy INTEGER NOT NULL DEFAULT 0,
  operation_id TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL,
  claim INTEGER NOT NULL DEFAULT 1,
  claim_owner TEXT NOT NULL,
  launch_token TEXT,                    -- REVOCABLE authorisation to start (fencing nulls it)
  attempt_id TEXT,                      -- IMMUTABLE identity of the current launch attempt (R4)
  capability TEXT NOT NULL,
  owner_turn TEXT NOT NULL DEFAULT 'absent',
  reply TEXT NOT NULL DEFAULT 'none',
  correlation TEXT NOT NULL DEFAULT 'pending',
  coverage TEXT NOT NULL DEFAULT 'none',
  liveness TEXT NOT NULL DEFAULT 'none',
  stop_requested_at REAL,
  deadline_at REAL,
  error_code TEXT,
  created_at REAL NOT NULL, updated_at REAL NOT NULL,
  settled_at REAL,
  UNIQUE(conversation_id, client_key));
CREATE INDEX sends_settled ON sends(settled_at) WHERE settled_at IS NOT NULL;
CREATE INDEX sends_open ON sends(state) WHERE settled_at IS NULL;
CREATE TABLE send_facts(
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  send_id TEXT NOT NULL REFERENCES sends ON DELETE CASCADE,
  launch_token TEXT,
  kind TEXT NOT NULL,
  data TEXT NOT NULL,
  at REAL NOT NULL);
CREATE INDEX send_facts_send ON send_facts(send_id, seq);
CREATE TABLE send_events(
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  send_id TEXT NOT NULL REFERENCES sends ON DELETE CASCADE,
  from_state TEXT, to_state TEXT NOT NULL, claim INTEGER NOT NULL,
  actor TEXT NOT NULL, at REAL NOT NULL, reason TEXT NOT NULL);
CREATE TABLE lease(
  home_key TEXT PRIMARY KEY,
  send_id TEXT NOT NULL REFERENCES sends,
  acquired_at REAL NOT NULL);
-- (R6) Verified source links of a send, rewritten by the claim owner at each resolution from the
-- committed receipts: ids and an identity fingerprint only, never text. Pruned with the send.
CREATE TABLE send_links(
  send_id TEXT NOT NULL REFERENCES sends ON DELETE CASCADE,
  role TEXT NOT NULL CHECK(role IN ('owner','reply')),
  part INTEGER NOT NULL,
  session_id TEXT NOT NULL,
  row_id INTEGER NOT NULL,
  fingerprint TEXT NOT NULL,
  PRIMARY KEY(send_id, role, part));
CREATE INDEX send_links_row ON send_links(session_id, row_id);
-- (R6) Attribution and visibility provenance that must OUTLIVE send retention: a workspace
-- session this app's executor created, and a committed row an executor proved to be Hermes's
-- own machinery (O-12). Not cascaded, not pruned; carried across an explicit reset when the
-- old ledger is readable, otherwise its loss is recorded (meta provenance_lost_at).
CREATE TABLE provenance(
  kind TEXT NOT NULL CHECK(kind IN ('workspace_session','internal_row')),
  session_id TEXT NOT NULL,
  row_id INTEGER NOT NULL DEFAULT 0,
  fingerprint TEXT,
  detail TEXT,
  send_id TEXT NOT NULL,
  recorded_at REAL NOT NULL,
  PRIMARY KEY(kind, session_id, row_id));
"""

# Fact kinds. Executor facts carry the launch token that authorised them.
EXECUTOR_FACTS = ('executor_started', 'capability_downgrade', 'write_intent', 'write_committed',
                  'write_rolled_back', 'write_unsettled', 'receipt_gap', 'stop_seen', 'executor_finished')
CONTROLLER_FACTS = ('spawn_failed', 'kill_sent', 'recovery')


class Busy(Exception):
    """A non-blocking lock was held by someone else."""


def fingerprint(ident, session, role, timestamp):
    """What must not change for a source row to still be the same message: its id, session,
    role and authored time (Phase 1A, chat_sources.fingerprint, which re-exports this). A send
    receipt records these four for every committed row, so a link or a provenance entry is
    bound to the row's identity, not to a row key another message could later hold."""
    import hashlib
    return hashlib.sha256(json.dumps([ident, session, role, timestamp]).encode()).hexdigest()[:24]


def ledger_dir(home):
    return Path(home) / LEDGER_DIRNAME


def lock_name(send_id, attempt_id):
    """One lock file per launch ATTEMPT, never per send: a re-armed send reuses its send_id,
    and a stale executor of an earlier attempt must not be able to open (and rewrite) the
    lock of a newer one (review R4, C1-R4-2)."""
    return f'{send_id}.{attempt_id}.lock'


def started_for(facts, attempt_id):
    """The executor_started facts of one attempt. Start evidence is looked up by the immutable
    attempt id, never by the revocable launch token (review R4, C1-R4-1)."""
    return [f for f in facts if f['kind'] == 'executor_started' and attempt_id
            and (f.get('data') or {}).get('attempt_id') == attempt_id]


def connect(path, readonly=False, create=False):
    """The ledger connection: rollback journal (not WAL), full sync, explicit transactions.
    Only ledger creation may create the file; every other open fails if it is missing, so a
    lost ledger is never silently replaced by an empty one."""
    mode = 'ro' if readonly else ('rwc' if create else 'rw')
    con = sqlite3.connect(Path(path).absolute().as_uri() + f'?mode={mode}', uri=True, timeout=5,
                          isolation_level=None, check_same_thread=False)
    try:
        if not readonly:
            con.execute('PRAGMA journal_mode=DELETE')
            con.execute('PRAGMA synchronous=FULL')
            con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA busy_timeout=5000')
    except BaseException:
        con.close()             # e.g. a file that is not a database
        raise
    return con


@contextlib.contextmanager
def immediate(con):
    """One BEGIN IMMEDIATE transaction. Never held across a process wait."""
    con.execute('BEGIN IMMEDIATE')
    try:
        yield con
    except BaseException:
        con.execute('ROLLBACK')
        raise
    con.execute('COMMIT')


def open_lock_file(path, create):
    """An fd for a lock file. Symlinks are refused; a missing file is only created on request."""
    flags = os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
    if create:
        flags |= os.O_CREAT
    return os.open(str(path), flags, 0o600)


@contextlib.contextmanager
def held_lock(path, exclusive=True, blocking=False, timeout=None, create=True):
    """Hold an advisory lock on `path` for the block. Raises Busy when not acquired."""
    if fcntl is None:
        raise Busy('advisory locks are not available on this platform')
    fd = open_lock_file(path, create)
    try:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, mode | (0 if blocking and deadline is None else fcntl.LOCK_NB))
                break
            except OSError as exc:
                if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    raise
                if deadline is None or time.monotonic() >= deadline:
                    raise Busy(str(path)) from None
                time.sleep(0.02)
        yield fd
    finally:
        os.close(fd)


def guard(directory, exclusive, timeout=None):
    """The ownership guard (4.1). Shared: acceptance, bootstrap, S2 registration.
    Exclusive: explicit reset. Busy -> `ledger_busy` for the caller."""
    return held_lock(Path(directory) / GUARD_FILE, exclusive=exclusive, timeout=timeout)


def insert_fact(con, send_id, token, kind, data, at=None):
    con.execute('INSERT INTO send_facts(send_id, launch_token, kind, data, at) VALUES (?,?,?,?,?)',
                (send_id, token, kind, json.dumps(data, sort_keys=True), time.time() if at is None else at))


# --- Row classification (4.10.1, amended by review R3 5.2) -----------------------------

TURN_METHODS = frozenset({'append_message', 'append_messages_batch'})
ROW_COLUMNS = ('session_id', 'role', 'tool_calls', 'has_text', 'display_kind', '_compressed_summary',
               'observed', 'active', 'compacted', 'finish_reason', 'timestamp')


def row_facts(conn, row_id):
    """The class inputs of one row, read back inside the write transaction. Never content."""
    cols = {r[1] for r in conn.execute('PRAGMA table_info(messages)')}
    def pick(name, default='NULL'):
        return name if name in cols else default
    row = conn.execute(
        f"SELECT session_id, role, {pick('tool_calls')}, "
        f"content IS NOT NULL AND length(trim(content)) > 0, {pick('display_kind')}, "
        f"{pick('_compressed_summary', '0')}, {pick('observed', '0')}, {pick('active', '1')}, "
        f"{pick('compacted', '0')}, {pick('finish_reason')}, {pick('timestamp')} "
        'FROM messages WHERE id = ?', (row_id,)).fetchone()
    if row is None:
        return None
    (session_id, role, tool_calls, has_text, display_kind, summary, observed, active, compacted,
     finish, stamp) = row
    return {'session_id': session_id, 'row_id': int(row_id), 'role': role,
            'has_text': bool(has_text), 'has_tool_calls': bool(tool_calls) and tool_calls not in ('[]', 'null'),
            'display_kind': display_kind or None, 'summary': bool(summary), 'observed': bool(observed),
            'active': None if active is None else int(active), 'compacted': int(compacted or 0),
            'finish_reason': finish, 'timestamp': stamp}


def publicly_visible(row):
    """Phase 1A's structural visibility rule (chat_sources.classify), applied to receipt rows:
    no display kind, not a compression summary, active (or a compacted original), with text."""
    return (not row.get('display_kind') and not row.get('summary')
            and (row.get('active') in (None, 1) or row.get('compacted') == 1)
            and bool(row.get('has_text')))


def classify(row, method):
    """What a committed row can be evidence of.

    `user_turn` (owner evidence) now needs the same public/trusted eligibility as
    reply evidence: a hidden, display-only, summary, observed or empty user row written
    through a turn method does NOT establish that the owner's message was recorded
    (review R3 5.2). Thread/call provenance alone is not message eligibility."""
    if method not in TURN_METHODS:
        return 'rewrite_copy'
    role = row.get('role')
    if role == 'user':
        if publicly_visible(row) and not row.get('observed') and not row.get('has_tool_calls'):
            return 'user_turn'
        return 'user_internal'
    if role == 'assistant':
        if row.get('has_tool_calls') or not publicly_visible(row) or row.get('observed'):
            return 'assistant_internal'
        return 'public_output'
    return 'internal'


# --- Identity helpers ------------------------------------------------------------------

def boot_id():
    try:
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    except OSError:
        return None


def start_time(pid, proc='/proc'):
    """Linux process start time (clock ticks since boot, /proc/<pid>/stat field 22), or None."""
    try:
        stat = Path(proc, str(pid), 'stat').read_text()
        return int(stat[stat.rindex(')') + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return None
