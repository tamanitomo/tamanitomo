"""Durable workspace sends: the Phase 1B C1 core.

NOT ACTIVATED for ordinary or live profiles. The keyed routes that use this module
(kit/app/chat_send_routes.py) are registered only when the app is built with an explicit
`chat_sends=` option, which no shipped entry point passes; no UI or release file uses it.
The current workspace chat path (POST /api/chat -> Runtime.chat -> hermes_stream.py) is
unchanged. See Phase1B_C1_Results.md for what is and is not shown.

Design: PHASE1B_DESIGN.md revision 3 with the R3 review corrections.

  ledger       <profile home>/.tamanitomo-sends/ledger.sqlite3 (+ ledger.id, guard.lock,
               controllers/, executors/). Safety state, never a cache.
  bootstrap    creates the ledger; returns {conversation_id, generation}. A POST never creates it.
  accept       idempotent by (conversation_id, client_key); generation fence; 24 h / +5 min
               freshness; one lease per physical home.
  launch       T1 token -> spawn in a new session/process group -> `go` -> the executor
               registers itself (S2) before Hermes runs. See send_executor.py.
  settle       outcome from executor facts only; lease released only on proof of quiescence
               (send_quiescence.observe: identity-checked lock AND a demonstrably empty group).
  recover      fence by claim compare-and-set, then read facts, probe, transition.
  reset        exclusive guard -> fence tokens -> the SAME quiescence contract -> move aside.

The ledger stores no message, reply, stream or stderr text. The message crosses
into the executor's argv exactly as today (U9).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import send_protocol as sp
from . import send_quiescence as sq

EXECUTOR = Path(__file__).resolve().parent / 'send_executor.py'
DAY = 24 * 3600
FUTURE = 300
RETENTION = 30 * DAY
PRUNE_BATCH = 500
MAX_MESSAGE = 30000
FINAL = ('complete', 'failed', 'interrupted', 'not_started', 'unknown')
OPEN = ('accepted', 'launching', 'generating', 'stopping')
# Local file systems on which flock and SQLite rollback-journal locking are established.
# tmpfs is local and supports both; it is listed so a synthetic home under /tmp is supported.
SUPPORTED_FS = frozenset({'ext4', 'ext3', 'btrfs', 'xfs', 'f2fs', 'tmpfs', 'apfs', 'hfs'})
_CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
_ULID = re.compile(r'[0-9A-HJKMNP-TV-Z]{26}')

ERRORS = {  # fixed vocabulary; no free text is ever stored
    'timeout': 'The reply took too long and was stopped.',
    'reply_incomplete': 'The reply did not finish.',
    'no_reply_recorded': 'No reply was recorded.',
    'sources_unverified': 'Hermes finished the turn; the app could not verify what it recorded.',
    'receipts_incomplete': 'The app could not confirm everything Hermes recorded for this turn.',
    'owner_turn_not_established': 'The app could not establish that your message was recorded exactly once.',
    'hermes_failed': 'Hermes reported that the turn failed.',
    'stopped': 'Stopped.',
    'spawn_failed': 'The reply process could not be started.',
    'launch_failed': 'The reply process was not started.',
    'executor_lost': 'The reply process ended without reporting how the turn went.',
}


class Refused(Exception):
    """A request that was not accepted; nothing was written for it."""

    def __init__(self, code, status=409, **extra):
        super().__init__(code)
        self.code, self.status, self.extra = code, status, extra


class NotFound(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class ExecutorSpec:
    """How to start the executor: Hermes's interpreter, environment and working directory."""
    python: str
    env: dict
    cwd: str


# --- Identities --------------------------------------------------------------------------

def new_ulid(at=None):
    ms = int((time.time() if at is None else at) * 1000)
    value = (ms << 80) | secrets.randbits(80)
    return ''.join(_CROCKFORD[(value >> (5 * i)) & 31] for i in reversed(range(26)))


def key_time(client_key):
    if not isinstance(client_key, str) or not _ULID.fullmatch(client_key):
        raise Refused('invalid_client_key', 400)
    value = 0
    for ch in client_key:
        value = value * 32 + _CROCKFORD.index(ch)
    return (value >> 80) / 1000.0


def request_digest(conversation_id, session, message):
    body = json.dumps({'v': 1, 'conversation_id': conversation_id, 'destination': 'workspace',
                       'session': session, 'message': message}, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'))
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def home_key(home):
    st = os.stat(home)
    real = os.path.realpath(home)
    return hashlib.sha256(f'{st.st_dev}|{st.st_ino}|{real}'.encode()).hexdigest()


def _send_id():
    return 'snd_' + ''.join(secrets.choice('abcdefghijklmnopqrstuvwxyz234567') for _ in range(26))


def filesystem_type(path):
    """The mount type holding `path` (Linux mountinfo), or None when it cannot be read."""
    try:
        text = Path(sq.PROC, 'self', 'mountinfo').read_text()
    except OSError:
        return None
    real = os.path.realpath(path)
    best, kind = -1, None
    for line in text.splitlines():
        left, sep, right = line.partition(' - ')
        if not sep:
            continue
        point = left.split()[4].replace('\\040', ' ')
        if (real == point or real.startswith(point.rstrip('/') + '/')) and len(point) > best:
            best, kind = len(point), right.split()[0]
    return kind


# --- Receipt derivation (4.3.2, amended by review R3 5.2) ----------------------------------

@dataclasses.dataclass
class Derived:
    started: dict | None = None
    finished: dict | None = None
    coverage: str = 'none'           # complete | bounded | incomplete | unavailable | none
    owner_turn: str = 'absent'
    reply: str = 'none'
    correlation: str = 'pending'
    outcome: str | None = None
    error_code: str | None = None
    sessions: list = dataclasses.field(default_factory=list)
    owner_rows: list = dataclasses.field(default_factory=list)
    reply_rows: list = dataclasses.field(default_factory=list)
    stop_seen: str | None = None
    internal_rows: list = dataclasses.field(default_factory=list)
    # (R6) The same rows with their receipted identity, for the read-side join and provenance:
    # [{role: owner|reply, part, session_id, row_id, fingerprint}] and
    # [{session_id, row_id, fingerprint}]. Present only where owner_rows/reply_rows are.
    link_rows: list = dataclasses.field(default_factory=list)
    internal_detail: list = dataclasses.field(default_factory=list)


def derive(send, facts):
    """Everything a receipt says, from the send row and its facts. Pure.

    Coverage is decided first and restricts every field, whether or not
    `executor_finished` exists: unidentified rows, a receipt gap, a session insert
    with no identifiable id, turn rows outside the send's session set, or a finish
    fact that does not claim complete receipts make coverage INCOMPLETE, and
    incomplete coverage never establishes an absence (review R3 5.2)."""
    out = Derived()
    started = sp.started_for(facts, send.get('attempt_id'))
    if not started:
        return out
    token = started[-1]['launch_token']
    own = [f for f in facts if f['launch_token'] == token]
    out.started = started[-1]['data']
    finished = [f for f in own if f['kind'] == 'executor_finished']
    out.finished = finished[-1]['data'] if finished else None
    stops = [f for f in own if f['kind'] == 'stop_seen']
    out.stop_seen = stops[0]['data'].get('reason') if stops else None
    downgraded = send.get('capability') == 'unverified_sources' or any(
        f['kind'] == 'capability_downgrade' for f in own)
    intents = {f['data']['wid'] for f in own if f['kind'] == 'write_intent'}
    outcomes = {f['data']['wid']: f['kind'] for f in own
                if f['kind'] in ('write_committed', 'write_rolled_back', 'write_unsettled', 'receipt_gap')}
    committed = [f['data'] for f in own if f['kind'] == 'write_committed']
    gap = any(f['kind'] == 'receipt_gap' for f in own)
    unsettled = any(k == 'write_unsettled' for k in outcomes.values())
    unresolved = bool(intents - set(outcomes))
    sessions, session_set = [], set()
    if send.get('requested_session'):
        sessions.append({'session_id': send['requested_session'], 'created_here': False})
        session_set.add(send['requested_session'])
    unidentified = 0
    for c in committed:
        unidentified += int(c.get('unidentified') or 0)
        for s in c.get('sessions') or []:
            if s.get('fresh') is None or (s.get('fresh') and s.get('session_id') is None):
                unidentified += 1           # a session insert whose effect could not be observed
            elif s.get('fresh') and s['session_id'] not in session_set:
                sessions.append({'session_id': s['session_id'], 'created_here': True})
                session_set.add(s['session_id'])
    rows = [r for c in committed for r in c.get('rows') or []]
    # O-12: a committed row this executor's own provenance names as Hermes's continuation note
    # is internal machinery, not owner speech. Bound to a receipted row of THIS attempt; a
    # provenance entry naming any other row changes nothing.
    notes = {(n.get('session_id'), n.get('row_id')) for f in own if f['kind'] == 'row_provenance'
             for n in f['data'].get('rows') or [] if n.get('kind') == 'length_continuation_nudge'}
    internal = [r for r in rows if r.get('role') == 'user' and (r.get('session_id'), r.get('row_id')) in notes]
    out.internal_rows = [[r['session_id'], r['row_id']] for r in internal]
    out.internal_detail = [{'session_id': r['session_id'], 'row_id': r['row_id'], 'fingerprint': _fp(r)}
                           for r in internal]
    user_rows = [r for r in rows if r.get('class') == 'user_turn' and r not in internal]
    public_rows = [r for r in rows if r.get('class') == 'public_output']
    outside = [r for r in user_rows + public_rows if r.get('session_id') not in session_set]
    finish_incomplete = out.finished is not None and not out.finished.get('receipts_complete')
    hard = gap or unidentified or outside or finish_incomplete
    out.sessions = sessions
    if downgraded:
        out.coverage = 'unavailable'
    elif hard or unresolved or unsettled:
        out.coverage = 'incomplete'
    else:
        out.coverage = 'complete' if out.finished else 'bounded'
    # owner_turn
    if out.coverage == 'unavailable' or hard:
        out.owner_turn = 'unknown'
    elif len(user_rows) > 1:
        out.owner_turn = 'ambiguous'
    elif len(user_rows) == 1:
        out.owner_turn = 'recorded'
    elif unresolved or unsettled:
        out.owner_turn = 'possible'
    else:
        out.owner_turn = 'absent'
    # reply (`final` is exactly the `complete` rule; decided after the outcome below)
    final_reply = bool(public_rows) and public_rows[-1].get('finish_reason') == 'stop'
    if out.coverage == 'unavailable' or hard:
        out.reply = 'unknown'
    elif public_rows:
        out.reply = 'partial'
    elif unresolved or unsettled:
        out.reply = 'unknown'
    else:
        out.reply = 'none'
    if out.coverage in ('complete', 'bounded') and out.owner_turn != 'ambiguous':
        out.owner_rows = [[r['session_id'], r['row_id']] for r in user_rows]
        out.reply_rows = [[r['session_id'], r['row_id']] for r in public_rows]
        out.link_rows = [{'role': role, 'part': i, 'session_id': r['session_id'], 'row_id': r['row_id'],
                          'fingerprint': _fp(r)}
                         for role, group in (('owner', user_rows), ('reply', public_rows))
                         for i, r in enumerate(group)]
    out.correlation = ('unverified' if out.coverage == 'unavailable' else
                       'ambiguous' if out.coverage == 'incomplete' or out.owner_turn == 'ambiguous' else
                       'linked' if (user_rows or public_rows) else 'pending')
    # outcome: only from executor_finished (4.3.2)
    fin = out.finished
    if fin is not None:
        code = fin.get('exit')
        if code == 130 or fin.get('interrupted'):
            out.outcome = 'interrupted'
            out.error_code = 'timeout' if fin.get('timed_out') else 'stopped'
        elif code == 0:
            if out.coverage == 'unavailable':
                out.outcome, out.error_code = 'unknown', 'sources_unverified'
            elif out.coverage != 'complete':
                out.outcome, out.error_code = 'unknown', 'receipts_incomplete'
            elif out.owner_turn != 'recorded':
                out.outcome, out.error_code = 'unknown', 'owner_turn_not_established'
            elif not public_rows:
                out.outcome, out.error_code = 'failed', 'no_reply_recorded'
            elif not final_reply:
                out.outcome, out.error_code = 'failed', 'reply_incomplete'
            else:
                out.outcome = 'complete'
        elif fin.get('timed_out'):
            out.outcome, out.error_code = 'failed', 'timeout'
        else:
            out.outcome, out.error_code = 'failed', 'hermes_failed'
    if out.outcome == 'complete':
        out.reply = 'final'
    return out


def _fp(row):
    return sp.fingerprint(row['row_id'], row['session_id'], row.get('role'), row.get('timestamp'))


# --- The service ---------------------------------------------------------------------------

class SendService:
    """One app process's view of one profile home's send ledger.

    `platform_check` and `hooks` exist for tests: the first lets a test present an
    unsupported platform; `_hook(name)` is a no-op a test-only subclass overrides to
    crash the controller at a named boundary (U6: no environment variable)."""

    def __init__(self, home, app_state, executor=None, *, installation_root=None, clock=time.time,
                 turn_timeout=600.0, stop_grace=15.0, watchdog_interval=1.0, platform_check=None,
                 stderr=None):
        self.home = Path(home)
        self.dir = sp.ledger_dir(self.home)
        self.db = self.dir / sp.LEDGER_FILE
        self.app_state = Path(app_state)
        self.executor = executor
        self.installation_root = Path(installation_root) if installation_root else None
        self.clock = clock
        self.turn_timeout, self.stop_grace, self.watchdog_interval = turn_timeout, stop_grace, watchdog_interval
        self.platform_check = platform_check or sq.platform_supported
        self.stderr = stderr
        self.controller = 'ctl_' + secrets.token_hex(8)
        self._controller_fd = None
        self._active = set()
        self._lock = threading.Lock()
        self._opened = False

    # ----- controller identity -----

    def _ensure_controller(self):
        with self._lock:
            if self._controller_fd is not None:
                return
            (self.dir / 'controllers').mkdir(mode=0o700, exist_ok=True)
            fd = sp.open_lock_file(self.dir / 'controllers' / f'{self.controller}.lock', create=True)
            sp.fcntl.flock(fd, sp.fcntl.LOCK_EX | sp.fcntl.LOCK_NB)
            self._controller_fd = fd

    def close(self):
        with self._lock:
            if self._controller_fd is not None:
                os.close(self._controller_fd)
                self._controller_fd = None

    def _controller_alive(self, controller):
        if controller == self.controller:
            return True
        path = self.dir / 'controllers' / f'{controller}.lock'
        state, _ = sq.probe_lock(path, None)
        # 'live' = held. Anything else (acquirable, missing) means the owner cannot be shown
        # alive; the claim compare-and-set keeps a stale owner from changing anything.
        return state == 'live'

    def _hook(self, name):
        """Test seam (no-op in production)."""

    # ----- storage, markers, open -----

    def supervision(self):
        """(True, '') or (False, code, detail). Checked before any acceptance."""
        ok, why = self.platform_check()
        if not ok:
            return False, 'send_supervision_unavailable', why
        if self.executor is None or not Path(self.executor.python).is_file():
            return False, 'send_supervision_unavailable', 'the executor interpreter is not available'
        kind = filesystem_type(self.home)
        if kind not in SUPPORTED_FS:
            return False, 'send_storage_unsupported', f'unsupported file system: {kind}'
        return True, '', ''

    def _require_supervision(self):
        ok, code, detail = self.supervision()
        if not ok:
            raise Refused(code, 503, detail=detail)

    def _markers_path(self):
        return self.app_state / 'send-ledgers.json'

    def _read_marker(self, key):
        try:
            return json.loads(self._markers_path().read_text()).get(key)
        except (OSError, ValueError, AttributeError):
            return None

    def _write_marker(self, key, ledger_id):
        self.app_state.mkdir(parents=True, exist_ok=True)
        with sp.held_lock(self.app_state / '.send-ledgers.lock', timeout=5):
            try:
                data = json.loads(self._markers_path().read_text())
                if not isinstance(data, dict):
                    data = {}
            except (OSError, ValueError):
                data = {}
            data[key] = ledger_id
            tmp = self._markers_path().with_suffix('.tmp')
            tmp.write_text(json.dumps(data, sort_keys=True))
            os.replace(tmp, self._markers_path())

    def _refuse_symlinks(self):
        for path in (self.dir, self.db, self.dir / sp.LEDGER_ID_FILE, self.dir / sp.GUARD_FILE,
                     self.dir / 'executors', self.dir / 'controllers'):
            if path.is_symlink():
                raise Refused('send_storage_unsupported', 503, detail='a send-ledger path is a symlink')

    def status(self):
        """'absent' | 'ok' | 'lost'. Never creates anything."""
        self._refuse_symlinks()
        hkey = home_key(self.home)
        id_file = self.dir / sp.LEDGER_ID_FILE
        marker = self._read_marker(hkey)
        if not self.db.exists():
            pending = self.dir / (sp.LEDGER_FILE + '.new')
            if pending.exists() and id_file.exists():
                return 'lost'          # an interrupted creation is not repaired silently
            return 'absent' if not id_file.exists() and marker is None else 'lost'
        try:
            con = sp.connect(self.db, readonly=True)
            try:
                if not self._opened:
                    if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        return 'lost'
                meta = dict(con.execute('SELECT key, value FROM meta'))
            finally:
                con.close()
        except sqlite3.Error:
            return 'lost'
        ledger_id = meta.get('ledger_id')
        try:
            on_disk = id_file.read_text().strip()
        except OSError:
            return 'lost'
        if not ledger_id or on_disk != ledger_id or meta.get('home_key') != hkey:
            return 'lost'
        if marker is None:
            self._write_marker(hkey, ledger_id)     # another app state reaching the same home
        elif marker != ledger_id:
            try:
                previous = json.loads(meta.get('previous_ledger_ids') or '[]')
            except ValueError:
                previous = []
            if marker not in previous:
                return 'lost'
            self._write_marker(hkey, ledger_id)     # an explicit reset made by another app state
        self._opened = True
        return 'ok'

    def _create(self, reset_at=None, previous=(), carry=()):
        """`carry` (reset only): provenance rows to keep, or None when the old ledger could
        not be read -- then the loss is recorded in meta and disclosed by reads (R6)."""
        self.dir.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self.dir, 0o700)
        for sub in ('executors', 'controllers'):
            (self.dir / sub).mkdir(mode=0o700, exist_ok=True)
        ledger_id, generation = secrets.token_hex(16), secrets.token_hex(16)
        pending = self.dir / (sp.LEDGER_FILE + '.new')
        if pending.exists():
            pending.unlink()
        con = sp.connect(pending, create=True)
        try:
            con.executescript(sp.SCHEMA)
            now = self.clock()
            rows = {'schema_version': sp.SCHEMA_VERSION, 'ledger_id': ledger_id, 'home_key': home_key(self.home),
                    'generation': generation, 'created_at': repr(now)}
            if reset_at is not None:
                rows['reset_at'] = repr(reset_at)
                # Other app states reaching this home still hold the old id in their marker;
                # an explicit reset is recognised by them through this list (never a lost file).
                rows['previous_ledger_ids'] = json.dumps(list(previous))
                if carry is None:
                    rows['provenance_lost_at'] = repr(reset_at)
            with sp.immediate(con):
                con.executemany('INSERT INTO meta VALUES (?,?)', rows.items())
                con.executemany('INSERT OR IGNORE INTO provenance VALUES (?,?,?,?,?,?,?)', carry or ())
        finally:
            con.close()
        os.chmod(pending, 0o600)
        id_tmp = self.dir / (sp.LEDGER_ID_FILE + '.tmp')
        id_tmp.write_text(ledger_id)
        os.chmod(id_tmp, 0o600)
        os.replace(pending, self.db)
        os.replace(id_tmp, self.dir / sp.LEDGER_ID_FILE)
        self._write_marker(home_key(self.home), ledger_id)
        self._opened = True
        return generation

    def _connect(self):
        return sp.connect(self.db)

    def _generation(self, con):
        return con.execute("SELECT value FROM meta WHERE key='generation'").fetchone()[0]

    def _open_or_refuse(self):
        state = self.status()
        if state == 'absent':
            raise Refused('not_bootstrapped', 409)
        if state == 'lost':
            raise Refused('send_ledger_lost', 503)

    # ----- bootstrap -----

    def bootstrap(self, scope):
        self._require_supervision()
        self._refuse_symlinks()
        self._make_dir()
        try:
            with sp.guard(self.dir, exclusive=False, timeout=2):
                generation = None
                state = self.status()
                if state == 'absent':
                    # Two first bootstraps both hold the guard shared: creation itself is exclusive.
                    with sp.held_lock(self.dir / 'create.lock', timeout=10):
                        state = self.status()
                        if state == 'absent':
                            generation = self._create()
                            state = 'ok'
                if state == 'lost':
                    raise Refused('send_ledger_lost', 503)
                if generation is None:
                    con = self._connect()
                    try:
                        generation = self._generation(con)
                    finally:
                        con.close()
        except sp.Busy:
            raise Refused('ledger_busy', 409) from None
        self._ensure_controller()
        return {'conversation_id': scope.conversation_id, 'generation': generation}

    def _make_dir(self):
        self.dir.mkdir(mode=0o700, exist_ok=True)
        return self.dir

    # ----- acceptance (5.2, 5.3) -----

    def accept(self, scope, body, authorize_session, admit=True):
        """(status, payload). `authorize_session(scope, session)` returns
        (source_kind, source_namespace) for a session the current binding would
        project, or None. A new session is the workspace's.

        `admit=False` (R6): this process cannot start a turn right now (its in-process
        installation slot is taken). An existing receipt still replays -- identical retries
        must never see a misleading busy answer (M-1a) -- but nothing new is accepted or
        re-armed: `409 installation_busy`."""
        if not isinstance(body, dict):
            raise Refused('invalid_request', 400)
        key, generation = body.get('client_key'), body.get('generation')
        message, session = body.get('message'), body.get('session')
        ktime = key_time(key)
        if body.get('conversation_id') != scope.conversation_id:
            raise Refused('wrong_conversation', 400)
        if not isinstance(message, str) or not 1 <= len(message) <= MAX_MESSAGE:
            raise Refused('invalid_message', 400)
        if session is not None and (not isinstance(session, str) or not session):
            raise Refused('invalid_session', 400)
        if not isinstance(generation, str):
            raise Refused('invalid_generation', 400)
        if session is None:
            kind, namespace = 'workspace', None
        else:
            allowed = authorize_session(scope, session)
            if not allowed:
                raise Refused('unauthorised_session', 400)
            kind, namespace = allowed
        digest = request_digest(scope.conversation_id, session, message)
        self._open_or_refuse()
        self._ensure_controller()
        self.recover_open()                         # lazy recovery (4.6), bounded
        existing = self._lookup(scope.conversation_id, key)
        if existing is not None:
            return self._replay_or_rearm(scope, existing, digest, ktime, admit)
        if not admit:
            raise Refused('turn_in_progress' if self._lease_held() else 'installation_busy', 409)
        now = self.clock()
        con = self._connect()
        try:
            if generation != self._generation(con):
                raise Refused('generation_changed', 409)
        finally:
            con.close()
        self._fresh(ktime, now)
        self._require_supervision()
        concurrent = None
        with self._admission_locks():
            con = self._connect()
            try:
                with sp.immediate(con):
                    concurrent = self._row(con, conversation_id=scope.conversation_id, client_key=key)
                    if concurrent is not None:
                        send_id = None      # an identical request committed first: replay it below
                    elif generation != self._generation(con):
                        raise Refused('generation_changed', 409)
                    else:
                        send_id = self._insert(con, scope, key, ktime, digest, session, kind, namespace,
                                               generation)
            finally:
                con.close()
        if concurrent is not None:
            return self._replay_or_rearm(scope, concurrent, digest, ktime, admit)
        self._hook('after_accept')
        self.prune()
        return 202, {'send': self.receipt(scope, send_id), 'replay': False}

    def _insert(self, con, scope, key, ktime, digest, session, kind, namespace, generation):
        """The acceptance insert, inside the caller's BEGIN IMMEDIATE."""
        self._fresh(ktime, self.clock())
        if con.execute('SELECT 1 FROM lease').fetchone():
            raise Refused('turn_in_progress', 409)
        send_id, now = _send_id(), self.clock()
        con.execute(
            'INSERT INTO sends(send_id, conversation_id, client_key, key_time, request_digest, '
            'destination, requested_session, source_kind, source_namespace, generation, legacy, '
            'operation_id, state, claim, claim_owner, capability, created_at, updated_at) '
            "VALUES (?,?,?,?,?,'workspace',?,?,?,?,0,?,'accepted',1,?,'full',?,?)",
            (send_id, scope.conversation_id, key, ktime, digest, session, kind, namespace,
             generation, secrets.token_hex(16), self.controller, now, now))
        con.execute('INSERT INTO lease VALUES (?,?,?)', (home_key(self.home), send_id, now))
        self._event(con, send_id, None, 'accepted', 1, 'accepted')
        return send_id

    def _lease_held(self):
        con = self._connect()
        try:
            return con.execute('SELECT 1 FROM lease').fetchone() is not None
        finally:
            con.close()

    def _fresh(self, ktime, now):
        if ktime < now - DAY:
            raise Refused('key_expired', 422)
        if ktime > now + FUTURE:
            raise Refused('key_in_future', 400)

    def _admission_locks(self):
        """Installation lock (briefly) -> ownership guard shared. Fixed order (4.7)."""
        service = self
        class _Locks:
            def __enter__(self_inner):
                self_inner.stack = []
                if service.installation_root is not None:
                    cm = sp.held_lock(service.installation_root / '.tamanitomo-installation.lock', timeout=2)
                    try:
                        cm.__enter__()
                    except sp.Busy:
                        raise Refused('installation_busy', 409) from None
                    self_inner.stack.append(cm)
                cm = sp.guard(service.dir, exclusive=False, timeout=2)
                try:
                    cm.__enter__()
                except sp.Busy:
                    for held in reversed(self_inner.stack):
                        held.__exit__(None, None, None)
                    raise Refused('ledger_busy', 409) from None
                self_inner.stack.append(cm)
                return self_inner
            def __exit__(self_inner, *exc):
                for held in reversed(self_inner.stack):
                    held.__exit__(*exc)
                return False
        return _Locks()

    def _replay_or_rearm(self, scope, row, digest, ktime, admit=True):
        if row['request_digest'] != digest:
            raise Refused('key_conflict', 409, send_id=row['send_id'])
        if row['state'] != 'not_started':
            return 200, {'send': self.receipt(scope, row['send_id'], recover=False), 'replay': True}
        if ktime < self.clock() - DAY:
            return 200, {'send': self.receipt(scope, row['send_id'], recover=False), 'replay': True,
                         'rearm': 'expired'}
        if not admit:
            raise Refused('turn_in_progress' if self._lease_held() else 'installation_busy', 409)
        return self._rearm(scope, row)

    def _rearm(self, scope, row):
        self._require_supervision()
        with self._admission_locks():
            con = self._connect()
            try:
                with sp.immediate(con):
                    current = self._row(con, send_id=row['send_id'])
                    if current['state'] != 'not_started':
                        rearmed = False       # a concurrent identical re-arm won
                    else:
                        if con.execute('SELECT 1 FROM lease').fetchone():
                            raise Refused('turn_in_progress', 409)
                        now = self.clock()
                        con.execute(
                            "UPDATE sends SET state='accepted', claim=claim+1, claim_owner=?, launch_token=NULL, "
                            "attempt_id=NULL, "
                            "owner_turn='absent', reply='none', correlation='pending', coverage='none', "
                            "liveness='none', error_code=NULL, settled_at=NULL, stop_requested_at=NULL, "
                            'deadline_at=NULL, updated_at=? WHERE send_id=? AND claim=?',
                            (self.controller, now, row['send_id'], current['claim']))
                        con.execute('INSERT INTO lease VALUES (?,?,?)', (home_key(self.home), row['send_id'], now))
                        self._event(con, row['send_id'], 'not_started', 'accepted', current['claim'] + 1, 'rearm')
                        rearmed = True
            finally:
                con.close()
        receipt = self.receipt(scope, row['send_id'], recover=False)
        return (202, {'send': receipt, 'replay': True, 'rearmed': True}) if rearmed else \
               (200, {'send': receipt, 'replay': True})

    # ----- rows, events, facts -----

    def _row(self, con, **where):
        clause = ' AND '.join(f'{k}=?' for k in where)
        cur = con.execute(f'SELECT * FROM sends WHERE {clause}', tuple(where.values()))
        row = cur.fetchone()
        return None if row is None else dict(zip([d[0] for d in cur.description], row))

    def _lookup(self, conversation_id, key):
        con = self._connect()
        try:
            return self._row(con, conversation_id=conversation_id, client_key=key)
        finally:
            con.close()

    def _facts(self, con, send_id):
        return [{'seq': s, 'launch_token': t, 'kind': k, 'data': json.loads(d), 'at': at}
                for s, t, k, d, at in con.execute(
                    'SELECT seq, launch_token, kind, data, at FROM send_facts WHERE send_id=? ORDER BY seq',
                    (send_id,))]

    def _event(self, con, send_id, from_state, to_state, claim, reason):
        con.execute('INSERT INTO send_events(send_id, from_state, to_state, claim, actor, at, reason) '
                    'VALUES (?,?,?,?,?,?,?)', (send_id, from_state, to_state, claim, self.controller,
                                               self.clock(), reason))

    def _cas(self, con, send_id, from_state, claim, reason, **values):
        """Compare-and-set on (state, claim) by the current claim owner. False = lost the race."""
        values['updated_at'] = self.clock()
        sets = ', '.join(f'{k}=?' for k in values)
        cur = con.execute(f'UPDATE sends SET {sets} WHERE send_id=? AND state=? AND claim=? AND claim_owner=?',
                          (*values.values(), send_id, from_state, claim, self.controller))
        if cur.rowcount != 1:
            return False
        if 'state' in values and values['state'] != from_state:
            self._event(con, send_id, from_state, values['state'], claim, reason)
        return True

    # ----- launch (4.4) -----

    def _argv(self, message, session):
        argv = ['chat', '--quiet', '--oneshot', '-q', message]
        return argv + (['--resume', session] if session else [])

    def launch(self, send_id, message, on_delta=None):
        """Run the accepted send to settlement in this thread. Returns the final row."""
        con = self._connect()
        try:
            row = self._row(con, send_id=send_id)
        finally:
            con.close()
        if row is None or row['state'] != 'accepted' or row['claim_owner'] != self.controller:
            raise Refused('not_launchable', 409)
        if request_digest(row['conversation_id'], row['requested_session'], message) != row['request_digest']:
            raise Refused('digest_mismatch', 409)
        claim, token, attempt = row['claim'], secrets.token_hex(16), secrets.token_hex(16)
        with self._lock:
            self._active.add(send_id)
        try:
            self._hook('before_T1')
            con = self._connect()
            try:
                with sp.immediate(con):
                    ok = self._cas(con, send_id, 'accepted', claim, 'launch', state='launching',
                                   launch_token=token, attempt_id=attempt,
                                   deadline_at=time.time() + self.turn_timeout)
            except sqlite3.Error:
                ok = None
            finally:
                con.close()
            if ok is False:
                return self._read(send_id)     # lost the claim: this launch authorised nothing
            if ok is None:
                # Not committed (rolled back). Settle only if the row is still exactly as we left it.
                return self._settle_without_executor(send_id, 'launch_failed', claim=claim)
            self._hook('after_T1')
            try:
                proc = subprocess.Popen(
                    [self.executor.python, str(EXECUTOR), '--', *self._argv(message, row['requested_session'])],
                    env=self.executor.env, cwd=self.executor.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=self.stderr if self.stderr is not None else subprocess.DEVNULL,
                    start_new_session=True, close_fds=True, text=True, encoding='utf-8', errors='replace')
            except OSError:
                con = self._connect()
                try:
                    with sp.immediate(con):
                        sp.insert_fact(con, send_id, None, 'spawn_failed', {'code': 'spawn_failed'})
                finally:
                    con.close()
                return self._settle_without_executor(send_id, 'spawn_failed', attempt=attempt)
            self._hook('after_popen')
            try:
                proc.stdin.write(json.dumps({'go': token, 'send_id': send_id, 'attempt': attempt,
                                             'ledger': str(self.dir), 'poll': self.watchdog_interval}) + '\n')
                proc.stdin.flush()
                proc.stdin.close()
            except OSError:
                pass
            self._hook('after_go')
            self._supervise(send_id, proc, on_delta, attempt)
            self._hook('before_finalize')
            return self._finalize(send_id, attempt)
        finally:
            with self._lock:
                self._active.discard(send_id)

    def _settle_without_executor(self, send_id, code, attempt=None, claim=None):
        """Fence, then not_started if no executor of THIS attempt registered (4.4.3). Bound to
        its own attempt (or, before T1, its own claim): stale cleanup never touches a newer one."""
        self._resolve(send_id, fence=True, error_code=code, attempt=attempt, claim=claim)
        return self._read(send_id)

    def _supervise(self, send_id, proc, on_delta, attempt):
        """Read the executor's stream; enforce the kill fallback after stop/deadline grace."""
        events = []
        def read():
            try:
                for line in proc.stdout:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get('event') == 'started':
                        events.append('started')
                        self._hook('started_event')
                        self._mark_generating(send_id, attempt)
                    elif event.get('event') == 'delta' and on_delta:
                        try:
                            on_delta(event.get('text', ''))
                        except Exception:
                            pass
            except (OSError, ValueError):
                pass
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        killed = False
        while proc.poll() is None:
            time.sleep(0.05)
            row = self._read(send_id)
            if row is None or row['claim_owner'] != self.controller or row['attempt_id'] != attempt:
                break              # lost the claim or the attempt: stop reading, never kill (4.6)
            if row['stop_requested_at'] and row['state'] == 'generating':
                con = self._connect()
                try:
                    with sp.immediate(con):
                        self._cas(con, send_id, 'generating', row['claim'], 'stop', state='stopping')
                finally:
                    con.close()
            if not killed and self._grace_expired(row):
                self._kill(send_id, row)
                killed = True
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        reader.join(timeout=5)
        if not reader.is_alive():
            # Closing while the reader is blocked would wait on it: a process that still holds
            # the pipe (a fork-without-exec descendant) keeps it open until it is killed.
            try:
                proc.stdout.close()
            except OSError:
                pass

    def _grace_expired(self, row):
        now = time.time()
        if row['stop_requested_at'] and now > row['stop_requested_at'] + self.stop_grace:
            return True
        return bool(row['deadline_at']) and now > row['deadline_at'] + self.stop_grace

    def _kill(self, send_id, row):
        con = self._connect()
        try:
            started = sp.started_for(self._facts(con, send_id), row['attempt_id'])
        finally:
            con.close()
        if not started:
            return 'kill_refused_no_group'
        ident = started[-1]['data']
        result = sq.kill_group(ident.get('pgid'), ident.get('pid'), ident.get('start'))
        con = self._connect()
        try:
            with sp.immediate(con):
                sp.insert_fact(con, send_id, None, 'kill_sent', {'result': result})
        finally:
            con.close()
        return result

    def _mark_generating(self, send_id, attempt):
        con = self._connect()
        try:
            with sp.immediate(con):
                row = self._row(con, send_id=send_id)
                # Start evidence by the immutable attempt, not the token: a refused reset may have
                # revoked the token after S2 committed (C1-R4-1).
                if row and row['state'] == 'launching' and row['attempt_id'] == attempt \
                        and sp.started_for(self._facts(con, send_id), attempt):
                    self._cas(con, send_id, 'launching', row['claim'], 'executor_started', state='generating')
        finally:
            con.close()
        self._hook('generating')

    def _finalize(self, send_id, attempt, tries=20):
        """After the executor process ended: ingest, prove quiescence (killing managed
        descendants still in the group), release. Unproven stays held. Bound to `attempt`."""
        for _ in range(tries):
            # The executor process has ended, so a send still `launching` is fenced now:
            # without start evidence for THIS attempt it is definitely not started.
            row = self._resolve(send_id, fence=True, attempt=attempt)
            if row is None or row['settled_at'] is not None or row['claim_owner'] != self.controller \
                    or row['attempt_id'] != attempt:
                return row
            if row['liveness'] == 'live':
                self._kill(send_id, row)
                time.sleep(0.1)
                continue
            return row
        return self._read(send_id)

    # ----- resolve / recover (4.5, 4.6) -----

    def _read(self, send_id):
        con = self._connect()
        try:
            return self._row(con, send_id=send_id)
        finally:
            con.close()

    def _lock_path(self, send_id, started):
        return self.dir / 'executors' / sp.lock_name(send_id, started.get('attempt_id') or 'missing')

    def _executor_observation(self, send_id, started):
        # A record without a nonce can never match one (an executor always writes it).
        return sq.observe(self._lock_path(send_id, started), started.get('lock_identity'),
                          started.get('pgid'), started.get('lock_nonce') or '')

    def _resolve(self, send_id, fence=False, error_code=None, attempt=None, claim=None):
        """Ingest facts and transition, as the current claim owner. Returns the row.
        `attempt`/`claim` bind a caller to its own launch: a row now belonging to another
        attempt (or, before T1, another claim) is returned untouched."""
        con = self._connect()
        try:
            row = self._row(con, send_id=send_id)
            if row is None or row['claim_owner'] != self.controller:
                return row
            if (attempt is not None and row['attempt_id'] != attempt) or (claim is not None and row['claim'] != claim):
                return row
            if row['state'] in ('accepted', 'launching') and fence:
                with sp.immediate(con):
                    row = self._row(con, send_id=send_id)
                    if (attempt is not None and row['attempt_id'] != attempt) or \
                            (claim is not None and row['claim'] != claim):
                        return row
                    current = row['claim']
                    cur = con.execute('UPDATE sends SET claim=claim+1, launch_token=NULL, updated_at=? '
                                      'WHERE send_id=? AND claim=? AND claim_owner=?',
                                      (self.clock(), send_id, current, self.controller))
                    if cur.rowcount != 1:
                        return self._row(con, send_id=send_id)
                    claim = current + 1
                    # Revoking the token stops FUTURE starts; whether this attempt already started
                    # is read from its immutable start evidence (C1-R4-1).
                    started = bool(sp.started_for(self._facts(con, send_id), row['attempt_id']))
                    if started:
                        self._cas(con, send_id, row['state'], claim, 'executor_started', state='generating')
                    else:
                        spawn = any(f['kind'] == 'spawn_failed' for f in self._facts(con, send_id))
                        self._cas(con, send_id, row['state'], claim, 'fenced', state='not_started',
                                  liveness='none', owner_turn='absent', reply='none', coverage='none',
                                  error_code='spawn_failed' if spawn else (error_code or 'launch_failed'),
                                  settled_at=self.clock())
                        con.execute('DELETE FROM lease WHERE send_id=?', (send_id,))
                row = self._row(con, send_id=send_id)
            if row['state'] in ('accepted', 'launching'):
                return row      # awaiting launch by its owner, or fenced by recover()
            if row['state'] not in ('generating', 'stopping', 'unknown') and not (
                    row['state'] in FINAL and row['settled_at'] is None):
                return row
            facts = self._facts(con, send_id)
        finally:
            con.close()
        derived = derive(row, facts)
        if derived.started is None:
            return row
        observation = self._executor_observation(send_id, derived.started)   # outside any transaction
        con = self._connect()
        try:
            with sp.immediate(con):
                current = self._row(con, send_id=send_id)
                if current['claim'] != row['claim'] or current['claim_owner'] != self.controller:
                    return current           # superseded: a stale observer changes nothing
                values = dict(owner_turn=derived.owner_turn, reply=derived.reply, coverage=derived.coverage,
                              correlation=derived.correlation, liveness=observation.state)
                if any(f['kind'] == 'capability_downgrade' for f in facts):
                    values['capability'] = 'unverified_sources'
                outcome = derived.outcome
                if outcome is None and observation.quiescent:
                    outcome = 'unknown'
                    values['error_code'] = 'executor_lost'
                if outcome is not None:
                    values['state'] = outcome
                    values.setdefault('error_code', derived.error_code)
                if observation.quiescent and (outcome or current['state']) in FINAL:
                    values['settled_at'] = self.clock()
                    con.execute('DELETE FROM lease WHERE send_id=?', (send_id,))
                from_state = current['state']
                if values.get('state') == from_state:
                    values.pop('state')
                if self._cas(con, send_id, from_state, current['claim'],
                             'quiescent' if observation.quiescent else observation.reason, **values):
                    self._record_links(con, current, derived, values.get('capability', current['capability']))
                return self._row(con, send_id=send_id)
        finally:
            con.close()

    def _record_links(self, con, row, derived, capability):
        """(R6) Inside the resolving transaction, as the claim owner: replace the send's
        verified links, and add the provenance that must outlive the send (5.5). Only from
        this attempt's committed receipts (derive); nothing is inferred from text."""
        send_id, now = row['send_id'], self.clock()
        con.execute('DELETE FROM send_links WHERE send_id=?', (send_id,))
        if capability != 'full':
            return          # unverified sources: no link, no session, no provenance (4.10.6)
        con.executemany('INSERT INTO send_links VALUES (?,?,?,?,?,?)',
                        [(send_id, l['role'], l['part'], l['session_id'], l['row_id'], l['fingerprint'])
                         for l in derived.link_rows])
        con.executemany("INSERT OR IGNORE INTO provenance VALUES ('internal_row',?,?,?,?,?,?)",
                        [(n['session_id'], n['row_id'], n['fingerprint'], 'length_continuation_nudge', send_id, now)
                         for n in derived.internal_detail])
        if row['source_kind'] == 'workspace':
            # A session the executor's committed receipts show it CREATED (fresh insert). A resumed
            # terminal session, or a continuation of one, is never relabelled (4.10.2, M-18a).
            con.executemany("INSERT OR IGNORE INTO provenance VALUES ('workspace_session',?,0,NULL,NULL,?,?)",
                            [(s['session_id'], send_id, now) for s in derived.sessions if s['created_here']])

    def recover(self, send_id):
        """Take ownership of an open send whose owner is gone, then resolve it (4.6)."""
        self._ensure_controller()
        con = self._connect()
        try:
            row = self._row(con, send_id=send_id)
            if row is None or row['settled_at'] is not None:
                return row
            if row['claim_owner'] == self.controller:
                if send_id in self._active:
                    return row             # being supervised by this process right now
            elif self._controller_alive(row['claim_owner']):
                return row                 # the owner is alive
            else:
                with sp.immediate(con):
                    cur = con.execute(
                        'UPDATE sends SET claim=claim+1, claim_owner=?, updated_at=?, '
                        "launch_token=CASE WHEN state='launching' THEN NULL ELSE launch_token END "
                        'WHERE send_id=? AND claim=? AND claim_owner=?',
                        (self.controller, self.clock(), send_id, row['claim'], row['claim_owner']))
                    if cur.rowcount != 1:
                        return self._row(con, send_id=send_id)   # another recoverer won
                    sp.insert_fact(con, send_id, None, 'recovery',
                                   {'from_claim': row['claim'], 'state': row['state']})
                    if row['state'] == 'accepted':
                        # Accepted, never authorised: no executor can exist (4.8 row 2).
                        self._cas(con, send_id, 'accepted', row['claim'] + 1, 'recovered_unlaunched',
                                  state='not_started', liveness='none', error_code='launch_failed',
                                  settled_at=self.clock())
                        con.execute('DELETE FROM lease WHERE send_id=?', (send_id,))
                    if row['state'] == 'launching':
                        # The fence above revoked the token (a refused reset may already have). Start
                        # evidence is the attempt's, independent of the token (C1-R4-1).
                        started = bool(sp.started_for(self._facts(con, send_id), row['attempt_id']))
                        claim = row['claim'] + 1
                        if started:
                            self._cas(con, send_id, 'launching', claim, 'executor_started', state='generating')
                        else:
                            self._cas(con, send_id, 'launching', claim, 'fenced', state='not_started',
                                      liveness='none', error_code='launch_failed', settled_at=self.clock())
                            con.execute('DELETE FROM lease WHERE send_id=?', (send_id,))
        finally:
            con.close()
        row = self._resolve(send_id)
        if row is not None and row['settled_at'] is None and row['claim_owner'] == self.controller \
                and row['liveness'] == 'live' and self._grace_expired(row):
            self._kill(send_id, row)       # the new owner holds kill authority (4.6)
            row = self._resolve(send_id)
        return row

    def recover_open(self, limit=20):
        con = self._connect()
        try:
            ids = [r[0] for r in con.execute(
                'SELECT send_id FROM sends WHERE settled_at IS NULL ORDER BY created_at LIMIT ?', (limit,))]
        finally:
            con.close()
        for send_id in ids:
            self.recover(send_id)

    def watch(self, send_id, timeout=60.0, interval=0.1):
        """Supervise a recovered send (no stream) until it settles or `timeout` passes."""
        deadline = time.monotonic() + timeout
        row = self.recover(send_id)
        while row is not None and row['settled_at'] is None and time.monotonic() < deadline:
            time.sleep(interval)
            row = self.recover(send_id)
        return row

    # ----- stop (4.9) -----

    def stop(self, scope, send_id):
        self._open_or_refuse()
        self._ensure_controller()
        con = self._connect()
        try:
            with sp.immediate(con):
                row = self._row(con, send_id=send_id)
                if row is None or row['conversation_id'] != scope.conversation_id:
                    raise NotFound(send_id)
                if row['state'] in ('launching', 'generating', 'stopping') and row['stop_requested_at'] is None:
                    con.execute('UPDATE sends SET stop_requested_at=?, updated_at=? WHERE send_id=?',
                                (time.time(), self.clock(), send_id))
                    if row['state'] == 'generating' and row['claim_owner'] == self.controller:
                        self._cas(con, send_id, 'generating', row['claim'], 'stop', state='stopping')
        finally:
            con.close()
        return self.receipt(scope, send_id)

    # ----- receipts -----

    def receipt(self, scope, send_id, authorized_kinds=None, recover=True):
        """The receipt within the captured scope. Source links are included only when the
        send's source kind is still authorised by the CURRENT binding (4.10.3)."""
        self._open_or_refuse()
        if recover:
            self.recover(send_id)
        con = self._connect()
        try:
            row = self._row(con, send_id=send_id)
            if row is None or row['conversation_id'] != scope.conversation_id:
                raise NotFound(send_id)
            facts = self._facts(con, send_id)
        finally:
            con.close()
        derived = derive(row, facts)
        out = {k: row[k] for k in ('send_id', 'client_key', 'conversation_id', 'state', 'owner_turn', 'reply',
                                   'correlation', 'capability', 'liveness', 'coverage', 'created_at',
                                   'updated_at', 'source_kind')}
        out['operation_id'] = row['operation_id']
        out['settled'] = row['settled_at'] is not None
        out['error'] = {'code': row['error_code'], 'message': ERRORS.get(row['error_code'], '')} \
            if row['error_code'] else None
        out['hermes_sessions'] = derived.sessions
        out['internal_rows'] = derived.internal_rows      # source ids only, e.g. continuation notes
        if authorized_kinds is not None and row['source_kind'] in authorized_kinds \
                and row['capability'] == 'full':
            out['source_links'] = {'owner': derived.owner_rows, 'reply': derived.reply_rows}
        return out

    def by_operation(self, scope, operation_id):
        """The send_id whose reserved operation id this is, within the captured scope, or None.
        Never creates a ledger (a missing or lost one is simply no send)."""
        if self.status() != 'ok':
            return None
        con = self._connect()
        try:
            row = con.execute('SELECT send_id FROM sends WHERE operation_id=? AND conversation_id=?',
                              (operation_id, scope.conversation_id)).fetchone()
        finally:
            con.close()
        return row[0] if row else None

    def row(self, scope, send_id):
        """The raw row within the captured scope (NotFound otherwise). For the route layer."""
        con = self._connect()
        try:
            row = self._row(con, send_id=send_id)
        finally:
            con.close()
        if row is None or row['conversation_id'] != scope.conversation_id:
            raise NotFound(send_id)
        return row

    def links(self, send_id):
        """[{role, part, session_id, row_id, fingerprint}] recorded for the send."""
        con = self._connect()
        try:
            return [dict(zip(('role', 'part', 'session_id', 'row_id', 'fingerprint'), r)) for r in con.execute(
                'SELECT role, part, session_id, row_id, fingerprint FROM send_links WHERE send_id=? '
                "ORDER BY role='reply', part", (send_id,))]
        finally:
            con.close()

    def lookup(self, scope, client_key, authorized_kinds=None):
        """The receipt for a client key; source links under the same rule as receipt()."""
        self._open_or_refuse()
        row = self._lookup(scope.conversation_id, client_key)
        if row is None:
            raise NotFound(client_key)
        return self.receipt(scope, row['send_id'], authorized_kinds=authorized_kinds)

    def open_receipts(self, scope, authorized_kinds=None):
        self._open_or_refuse()
        self.recover_open()
        self.prune()
        con = self._connect()
        try:
            ids = [r[0] for r in con.execute(
                'SELECT send_id FROM sends WHERE conversation_id=? AND settled_at IS NULL '
                'ORDER BY created_at DESC LIMIT 20', (scope.conversation_id,))]
        finally:
            con.close()
        return [self.receipt(scope, i, authorized_kinds=authorized_kinds, recover=False) for i in ids]

    # ----- retention (5.5) -----

    def prune(self, now=None):
        now = self.clock() if now is None else now
        con = self._connect()
        try:
            doomed = con.execute('SELECT send_id FROM sends WHERE settled_at IS NOT NULL AND settled_at < ? '
                                 'ORDER BY settled_at LIMIT ?', (now - RETENTION, PRUNE_BATCH)).fetchall()
            locks = {}
            for (send_id,) in doomed:
                locks[send_id] = {sp.lock_name(send_id, f['data'].get('attempt_id')): f['data']
                                  for f in self._facts(con, send_id) if f['kind'] == 'executor_started'}
            with sp.immediate(con):
                for (send_id,) in doomed:
                    con.execute('DELETE FROM sends WHERE send_id=? AND settled_at IS NOT NULL AND settled_at < ?',
                                (send_id, now - RETENTION))
        finally:
            con.close()
        removed = 0
        for send_id, recorded in locks.items():
            for path in (self.dir / 'executors').glob(f'{send_id}.*.lock'):
                started = recorded.get(path.name)
                if started is not None:
                    safe = self._executor_observation(send_id, started).quiescent
                else:                   # an attempt that never registered: only "not busy" matters
                    safe = sq.probe_lock(path, None)[0] != 'live'
                if safe:
                    path.unlink()
                    removed += 1
        return len(doomed), removed

    # ----- explicit reset (4.1) -----

    def reset(self):
        """Owner action. Exclusive guard -> fence -> quiescence (the same contract) -> replace."""
        self._refuse_symlinks()
        if not self.dir.exists():
            raise Refused('not_bootstrapped', 409)
        try:
            with sp.guard(self.dir, exclusive=True, timeout=0):
                readable = True
                try:
                    con = self._connect()
                    try:
                        if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                            raise sqlite3.DatabaseError('integrity')
                        with sp.immediate(con):
                            con.execute('UPDATE sends SET launch_token=NULL, claim=claim+1 '
                                        'WHERE launch_token IS NOT NULL')
                        unsettled = [r[0] for r in con.execute(
                            'SELECT send_id FROM sends WHERE settled_at IS NULL')]
                        carried = self._provenance_to_carry(con)
                        recorded = {}           # lock file name -> (send_id, start record), per attempt
                        for send_id in unsettled:
                            for f in self._facts(con, send_id):
                                if f['kind'] == 'executor_started':
                                    name = sp.lock_name(send_id, f['data'].get('attempt_id'))
                                    recorded[name] = (send_id, f['data'])
                    finally:
                        con.close()
                except sqlite3.Error:
                    readable = False
                    recorded = {}
                    carried = None
                blocked = []
                for send_id, started in recorded.values():
                    obs = self._executor_observation(send_id, started)
                    if not obs.quiescent:
                        blocked.append((send_id, obs.state, obs.reason))
                for path in sorted((self.dir / 'executors').glob('*.lock')):
                    send_id = path.name.split('.')[0]
                    if path.name in recorded:
                        continue
                    obs = self._orphan_lock_observation(path, use_content=not readable)
                    if obs is not None and not obs.quiescent:
                        blocked.append((send_id, obs.state, obs.reason))
                if blocked:
                    raise Refused('executor_live', 409, executors=[
                        {'send_id': s, 'liveness': st, 'reason': r} for s, st, r in blocked])
                previous = []
                try:
                    con = sp.connect(self.db, readonly=True)
                    try:
                        meta = dict(con.execute('SELECT key, value FROM meta'))
                        previous = json.loads(meta.get('previous_ledger_ids') or '[]') + [meta['ledger_id']]
                    finally:
                        con.close()
                except (sqlite3.Error, KeyError, ValueError):
                    pass
                try:
                    old_id = (self.dir / sp.LEDGER_ID_FILE).read_text().strip()
                    if old_id and old_id not in previous:
                        previous.append(old_id)
                except OSError:
                    pass
                stamp = time.strftime('%Y%m%dT%H%M%S', time.gmtime(self.clock()))
                if self.db.exists():
                    os.replace(self.db, self.dir / f'ledger.lost-{stamp}-{secrets.token_hex(3)}.sqlite3')
                self._opened = False
                generation = self._create(reset_at=self.clock(), previous=previous[-20:], carry=carried)
        except sp.Busy:
            raise Refused('ledger_busy', 409) from None
        return {'generation': generation}

    def _provenance_to_carry(self, con):
        """Provenance that must survive the reset: the persisted table, plus what unsettled
        sends' own receipts establish (settled sends wrote theirs when they settled). A ledger
        without the table cannot vouch for what it held: None (recorded as lost)."""
        try:
            rows = [tuple(r) for r in con.execute('SELECT * FROM provenance')]
            earlier = con.execute("SELECT value FROM meta WHERE key='provenance_lost_at'").fetchone()
        except sqlite3.Error:
            return None
        if earlier is not None:
            return None         # a loss already recorded is not repaired by resetting again
        now = self.clock()
        for send_id in [r[0] for r in con.execute('SELECT send_id FROM sends WHERE settled_at IS NULL')]:
            send = self._row(con, send_id=send_id)
            derived = derive(send, self._facts(con, send_id))
            if send['capability'] != 'full' or derived.started is None:
                continue
            rows += [('internal_row', n['session_id'], n['row_id'], n['fingerprint'], 'length_continuation_nudge',
                      send_id, now) for n in derived.internal_detail]
            if send['source_kind'] == 'workspace':
                rows += [('workspace_session', s['session_id'], 0, None, None, send_id, now)
                         for s in derived.sessions if s['created_here']]
        return rows

    def _orphan_lock_observation(self, path, use_content):
        """A lock file with no executor_started in a readable ledger: its executor never
        entered Hermes, so only a busy lock matters. With an unreadable ledger, the identity
        the executor wrote into the file is the record, checked by the same contract."""
        if not use_content:
            state, why = sq.probe_lock(path, None)
            return sq.Observation('live', why) if state == 'live' else None
        try:
            ident = json.loads(path.read_text() or 'null')
        except (OSError, ValueError):
            ident = None
        if not isinstance(ident, dict):
            # No readable identity. An executor that died between creating its lock and writing
            # it never ran Hermes, but a lock path REPLACED while its executor still holds the
            # unlinked original looks the same. With no ledger to tell them apart: unproven.
            state, why = sq.probe_lock(path, None)
            return sq.Observation('live', why) if state == 'live' else sq.Observation('unproven', 'lock_identity_unreadable')
        return sq.observe(path, ident.get('lock_identity'), ident.get('pgid'), ident.get('lock_nonce') or '')


# --- Installation mutations (4.7): the same quiescence contract -----------------------------

def installation_quiescence(root):
    """[(profile_home, send_id, liveness, reason)] for every managed execution that is not
    proven quiescent in any profile ledger under a Hermes installation root. Empty = safe."""
    root = Path(root)
    homes = [root] + sorted(p for p in (root / 'profiles').glob('*') if p.is_dir()) \
        if (root / 'profiles').is_dir() else [root]
    blocked = []
    for home in homes:
        directory = sp.ledger_dir(home)
        db = directory / sp.LEDGER_FILE
        if not directory.exists():
            continue
        try:
            con = sp.connect(db, readonly=True)
            try:
                open_sends = [r[0] for r in con.execute(
                    'SELECT send_id FROM sends WHERE settled_at IS NULL OR send_id IN (SELECT send_id FROM lease)')]
                facts = {}
                for send_id in open_sends:
                    rows = con.execute("SELECT data FROM send_facts WHERE send_id=? AND kind='executor_started' "
                                       'ORDER BY seq DESC LIMIT 1', (send_id,)).fetchone()
                    facts[send_id] = json.loads(rows[0]) if rows else None
            finally:
                con.close()
        except sqlite3.Error:
            blocked.append((str(home), None, 'unproven', 'ledger_unreadable'))
            continue
        for send_id, started in facts.items():
            if started is None:
                blocked.append((str(home), send_id, 'unproven', 'send_open_without_executor_record'))
                continue
            obs = sq.observe(directory / 'executors' / sp.lock_name(send_id, started.get('attempt_id') or 'missing'),
                             started.get('lock_identity'), started.get('pgid'), started.get('lock_nonce') or '')
            if not obs.quiescent:
                blocked.append((str(home), send_id, obs.state, obs.reason))
    return blocked


def hold_installation(root):
    """(R6) The cross-process installation guard for an exclusive mutation (4.7). Takes
    `<root>/.tamanitomo-installation.lock` EXCLUSIVELY, non-blocking, then checks every profile
    ledger under the root with the one quiescence contract. Returns a hold whose `release()`
    ends the mutation; the caller keeps it for the mutation's whole duration.

    Refused('installation_busy') -- another mutation, or a send's acceptance, holds the lock.
    Refused('chat_reply_running') -- a send is open or its execution is not proven quiescent.

    An OS lock, so it excludes other app processes; the in-process `Operations.busy` rule is
    separate and unchanged. Where advisory locks do not exist (Windows), sends are refused
    outright (O-8), so no chat can be running and the hold is a no-op."""
    root = Path(root)
    if sp.fcntl is None:
        return _Hold(None)
    try:
        fd = sp.open_lock_file(root / '.tamanitomo-installation.lock', create=True)
    except OSError:
        raise Refused('installation_busy', 409, detail='the installation lock cannot be opened') from None
    try:
        sp.fcntl.flock(fd, sp.fcntl.LOCK_EX | sp.fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise Refused('installation_busy', 409) from None
    try:
        blocked = installation_quiescence(root)
    except BaseException:
        os.close(fd)
        raise
    if blocked:
        os.close(fd)
        raise Refused('chat_reply_running', 409, executors=[
            {'send_id': s, 'liveness': st, 'reason': r} for _, s, st, r in blocked])
    return _Hold(fd)


class _Hold:
    def __init__(self, fd):
        self._fd, self._lock = fd, threading.Lock()

    def release(self):
        with self._lock:
            if self._fd is not None:
                os.close(self._fd)      # closing the only descriptor releases the flock
                self._fd = None


# --- Read-side provenance (R6): what the Phase 1A read boundary may use ---------------------

@dataclasses.dataclass(frozen=True)
class ReadModel:
    """Read-only view of one profile home's ledger for the Phase 1A read boundary.

    state  'none'         no ledger: no keyed send was ever made here (nothing to apply)
           'ok'           provenance read
           'incomplete'   an explicit reset could not carry the old ledger's provenance
           'unavailable'  a ledger exists but cannot be read now
    `workspace_sessions` -- sessions an executor's committed receipts show it created for a
    workspace send. `internal` -- {(session_id, row_id): fingerprint} of committed rows an
    executor proved to be Hermes's own machinery (O-12). Both are bound to receipts; neither
    is ever inferred from text, and rows written outside a C1 executor have neither."""
    state: str
    reason: str | None = None
    home: str | None = None
    workspace_sessions: frozenset = frozenset()
    internal: tuple = ()

    @property
    def internal_map(self):
        return dict(self.internal)

    def disclosure(self):
        notes = {
            'none': None,
            'ok': None,
            'incomplete': 'An explicit send-ledger reset could not carry which earlier rows were Hermes’s '
                          'own continuation notes; such rows may show as your messages.',
            'unavailable': 'The send ledger cannot be read right now, so rows known to be Hermes’s own '
                           'continuation notes may show as your messages.',
        }
        out = {'state': self.state, 'limitation': 'Continuation notes written outside a keyed workspace '
               'send (terminal, Telegram, earlier app versions) carry no provenance and show as that '
               'session recorded them.'}
        if notes.get(self.state):
            out['notice'] = notes[self.state]
        if self.reason:
            out['reason'] = self.reason
        return out

    def links(self, keys):
        """{(session_id, row_id): [{send_id, role, part, fingerprint, conversation_id, source_kind,
        source_namespace, capability}]} for source rows in `keys` (<= 500)."""
        keys = [(str(s), int(r)) for s, r in keys][:500]
        if self.state not in ('ok', 'incomplete') or not keys:
            return {}
        db = sp.ledger_dir(self.home) / sp.LEDGER_FILE
        out = {}
        try:
            con = sp.connect(db, readonly=True)
            try:
                for i in range(0, len(keys), 200):
                    chunk = keys[i:i + 200]
                    where = ' OR '.join('(l.session_id=? AND l.row_id=?)' for _ in chunk)
                    for r in con.execute(
                            'SELECT l.session_id, l.row_id, l.send_id, l.role, l.part, l.fingerprint, '
                            's.conversation_id, s.source_kind, s.source_namespace, s.capability '
                            f'FROM send_links l JOIN sends s ON s.send_id=l.send_id WHERE {where}',
                            [v for k in chunk for v in k]):
                        out.setdefault((r[0], r[1]), []).append(dict(zip(
                            ('send_id', 'role', 'part', 'fingerprint', 'conversation_id', 'source_kind',
                             'source_namespace', 'capability'), r[2:])))
            finally:
                con.close()
        except sqlite3.Error:
            return {}
        return out


def read_model(home):
    """The ReadModel for a profile home. Read-only: never creates, repairs or marks anything."""
    home = str(Path(home))
    directory = sp.ledger_dir(home)
    db = directory / sp.LEDGER_FILE
    if not directory.exists() and not directory.is_symlink():
        return ReadModel('none', home=home)
    if directory.is_symlink() or db.is_symlink():
        return ReadModel('unavailable', 'symlinked_ledger', home)
    if not db.exists():
        return ReadModel('unavailable', 'ledger_missing', home)
    try:
        con = sp.connect(db, readonly=True)
        try:
            meta = dict(con.execute('SELECT key, value FROM meta'))
            rows = con.execute('SELECT kind, session_id, row_id, fingerprint FROM provenance').fetchall()
            sessions = {r[1] for r in rows if r[0] == 'workspace_session'}
            internal = {(r[1], r[2]): r[3] for r in rows if r[0] == 'internal_row'}
            # Unsettled sends have not written theirs yet (it is written when they settle): read
            # their own receipts, so a note is withheld while its turn is still running.
            for (send_id,) in con.execute('SELECT send_id FROM sends WHERE settled_at IS NULL').fetchall():
                cur = con.execute('SELECT * FROM sends WHERE send_id=?', (send_id,))
                send = dict(zip([d[0] for d in cur.description], cur.fetchone()))
                facts = [{'seq': s, 'launch_token': t, 'kind': k, 'data': json.loads(d), 'at': at}
                         for s, t, k, d, at in con.execute(
                             'SELECT seq, launch_token, kind, data, at FROM send_facts WHERE send_id=? ORDER BY seq',
                             (send_id,))]
                derived = derive(send, facts)
                if send['capability'] != 'full' or derived.started is None or any(
                        f['kind'] == 'capability_downgrade' for f in facts):
                    continue
                internal.update({(n['session_id'], n['row_id']): n['fingerprint'] for n in derived.internal_detail})
                if send['source_kind'] == 'workspace':
                    sessions |= {s['session_id'] for s in derived.sessions if s['created_here']}
        finally:
            con.close()
    except (sqlite3.Error, ValueError, TypeError):
        return ReadModel('unavailable', 'ledger_unreadable', home)
    state = 'incomplete' if meta.get('provenance_lost_at') else 'ok'
    return ReadModel(state, 'ledger_reset_without_readable_provenance' if state == 'incomplete' else None,
                     home, frozenset(sessions), tuple(sorted(internal.items())))
