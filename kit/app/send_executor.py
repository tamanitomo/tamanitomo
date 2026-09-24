"""The Phase 1B supervised executor (C1 core). Runs ONLY under Hermes's own interpreter.

NOT ACTIVATED: the current workspace chat still uses kit/app/hermes_stream.py.
This file is launched only by kit/app/chat_sends.py, which no route calls yet.

    <hermes python> send_executor.py -- <hermes argv ...>

Protocol (PHASE1B_DESIGN.md 4.4.1), in this order:
  G   block reading ONE line from stdin: {"go": <launch token>, "send_id", "ledger", ...}.
      EOF or anything else -> exit without importing Hermes.
  S1  open/create executors/<send_id>.lock (no symlinks), lock it non-blocking, record
      its (st_dev, st_ino). The lock is held until this process ends; the OS releases it.
  S2  under the SHARED ownership guard, one BEGIN IMMEDIATE: require
      sends.launch_token = token and state = 'launching', insert `executor_started`
      {pid, start, boot, pgid, lock_identity}. Token mismatch -> exit without running.
  S3  install the stop/deadline watchdog and the commit-boundary recorder, then
      import cli and run Hermes's quiet one-shot turn.
  S4  insert `executor_finished` {exit, interrupted, timed_out, receipts_complete}.

The recorder wraps SessionDB._execute_write, the pinned SessionDB's only commit point:
`write_intent` is committed before Hermes's callback runs (fails closed), inserts seen
inside a callback attempt are candidates (discarded when Hermes retries the callback),
and only when the outermost call RETURNS is `write_committed` published. A callback that
returned but whose commit raised is `write_unsettled`; one that raised is
`write_rolled_back`. If Hermes committed but the receipt could not be written, the gap
is latched (`receipt_gap`), that write is NOT failed back into Hermes, and every later
write is refused before it starts.

Every fact write is exactly-once under the single KeyboardInterrupt the watchdog may
deliver: each carries a per-executor `fid`, and an interrupted write is checked and
completed before the interrupt is re-raised.

The message stays in argv as today (U9). Nothing here writes message, reply or stream
text to the ledger; stdout carries only delta events for the live controller.
"""
from __future__ import annotations

import _thread
import contextlib
import functools
import importlib.util
import inspect
import io
import itertools
import json
import os
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_protocol():
    # Loaded by path under a private name: putting kit/app on sys.path inside Hermes's
    # process could shadow Hermes modules with the app's own (runtime, content, ...).
    spec = importlib.util.spec_from_file_location('tamanitomo_send_protocol', HERE / 'send_protocol.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sp = _load_protocol()

EXIT_NO_GO = 0          # the controller died before `go`: nothing ran
EXIT_LOCK_BUSY = 75     # S1 could not take the executor lock: nothing ran
EXIT_NOT_AUTHORISED = 76  # S2 token check failed (fenced): nothing ran
EXIT_REGISTRATION = 77  # S2 could not be committed: nothing ran

_INSERT_MESSAGES = re.compile(r'^\s*INSERT\s+(?:OR\s+\w+\s+)?INTO\s+messages\s*\(', re.I)
_INSERT_SESSIONS = re.compile(r'^\s*INSERT\s+(?:OR\s+\w+\s+)?INTO\s+sessions\s*\(([^)]*)\)', re.I)


class ReceiptsIncomplete(sqlite3.OperationalError):
    """Raised BEFORE a Hermes write once a committed write could not be receipted."""


class Facts:
    """The executor's writer into send_facts. One connection, serialised; every
    write is exactly-once under one KeyboardInterrupt (see the module docstring)."""

    def __init__(self, ledger_path, send_id, token):
        self.send_id, self.token = send_id, token
        self.con = sp.connect(ledger_path)
        self.lock = threading.RLock()
        self.fids = itertools.count(1)
        self.gap = False            # latched: a committed Hermes write has no receipt
        self.fail_next = 0          # test seam for an injected ledger failure (tests only)

    def write(self, kind, **data):
        fid = next(self.fids)
        data['fid'] = fid
        with self.lock:
            try:
                self._insert(kind, data)
            except KeyboardInterrupt:
                self._settle(kind, data)
                raise

    def _insert(self, kind, data):
        if self.fail_next:
            self.fail_next -= 1
            raise sqlite3.OperationalError('injected send-ledger write failure')
        with sp.immediate(self.con):
            sp.insert_fact(self.con, self.send_id, self.token, kind, data)

    def _settle(self, kind, data):
        # An interrupt landed around the write. Finish it exactly once, then let it propagate.
        if self.con.in_transaction:
            self.con.execute('ROLLBACK')
        present = self.con.execute(
            "SELECT 1 FROM send_facts WHERE send_id=? AND kind=? AND json_extract(data,'$.fid')=?",
            (self.send_id, kind, data['fid'])).fetchone()
        if not present:
            self._insert(kind, data)

    def safe(self, kind, **data):
        """For outcome facts whose failure must not raise into Hermes: latch a gap instead."""
        try:
            self.write(kind, **data)
            return True
        except KeyboardInterrupt:
            raise
        except Exception:
            self.gap = True
            return False


class _Scope:
    def __init__(self):
        self.attempts = 0
        self.new_attempt()

    def new_attempt(self):
        self.attempts += 1
        self.rows, self.sessions, self.unidentified = [], [], 0
        self.callback_returned = False


class _ConnProxy:
    """Passes everything to Hermes's connection; observes INSERTs into messages/sessions
    inside the transaction. Reads back class inputs only, never content."""

    def __init__(self, conn, scope):
        object.__setattr__(self, '_conn', conn)
        object.__setattr__(self, '_scope', scope)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        setattr(self._conn, name, value)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *exc):
        return self._conn.__exit__(*exc)

    def executemany(self, sql, seq):
        if isinstance(sql, str) and (_INSERT_MESSAGES.match(sql) or _INSERT_SESSIONS.match(sql)):
            # Row ids are not observable per row: count what it changed as unidentified.
            before = self._conn.total_changes
            cur = self._conn.executemany(sql, seq)
            if _INSERT_MESSAGES.match(sql):
                self._scope.unidentified += max(0, cur.rowcount if cur.rowcount >= 0 else
                                                self._conn.total_changes - before)
            else:
                self._scope.sessions.append({'session_id': None, 'fresh': None, 'existed_before': None})
            return cur
        return self._conn.executemany(sql, seq)

    def execute(self, sql, params=()):
        scope = self._scope
        if isinstance(sql, str) and _INSERT_MESSAGES.match(sql):
            cur = self._conn.execute(sql, params)
            # changes() counts this statement's rows and excludes FTS trigger rows.
            changed = self._conn.execute('SELECT changes()').fetchone()[0]
            if re.search(r'\bSELECT\b', sql, re.I):
                scope.unidentified += changed       # INSERT ... SELECT (the tail clone): no per-row id
            elif changed == 1 and cur.lastrowid:
                facts = sp.row_facts(self._conn, cur.lastrowid)
                if facts:
                    scope.rows.append(facts)
                else:
                    scope.unidentified += 1
            elif changed:
                scope.unidentified += changed
            return cur
        if isinstance(sql, str) and _INSERT_SESSIONS.match(sql):
            # Fresh = a row that did not exist before this statement and does after. Sessions is a
            # rowid table and a new row always gets a rowid above the previous maximum, so the
            # new ids are read back by rowid; this does not depend on the statement's shape (the
            # pinned upsert has a literal NULL among its VALUES). An upsert of an existing id
            # adds no row and is `fresh: False`.
            try:
                high = self._conn.execute('SELECT coalesce(max(rowid), 0) FROM sessions').fetchone()[0]
            except sqlite3.Error:
                high = None
            cur = self._conn.execute(sql, params)
            if high is None:
                scope.sessions.append({'session_id': None, 'fresh': None})
                return cur
            new = [r[0] for r in self._conn.execute('SELECT id FROM sessions WHERE rowid > ?', (high,))]
            if new:
                scope.sessions.extend({'session_id': sid, 'fresh': True} for sid in new)
            else:
                scope.sessions.append({'session_id': None, 'fresh': False})
            return cur
        return self._conn.execute(sql, params)


def seam_available(session_db_class):
    """The commit-boundary seam with the pinned calling convention, or a reason it is not."""
    method = getattr(session_db_class, '_execute_write', None)
    if method is None:
        return False, 'SessionDB._execute_write missing'
    try:
        params = list(inspect.signature(method).parameters)
    except (TypeError, ValueError):
        return False, 'SessionDB._execute_write signature unreadable'
    if params[:3] != ['self', 'fn', 'patience_s']:
        return False, 'SessionDB._execute_write calling convention changed'
    return True, ''


def install_recorder(session_db_class, facts):
    """Wrap `_execute_write` on `session_db_class` (Hermes's SessionDB, or a test double)."""
    original = session_db_class._execute_write
    local = threading.local()
    counter = itertools.count(1)
    counter_lock = threading.Lock()

    @functools.wraps(original)
    def _execute_write(self, fn, patience_s=None):
        if getattr(local, 'depth', 0):
            # Nested: the enclosing scope owns the observations; nothing is published here.
            outer = local.scope
            def nested(conn):
                return fn(conn if isinstance(conn, _ConnProxy) else _ConnProxy(conn, outer))
            return original(self, nested, patience_s)
        method = sys._getframe(1).f_code.co_name
        with counter_lock:
            wid = next(counter)
        if facts.gap:
            # Fail closed: once a committed write could not be receipted, no later write may
            # land (it could be an owner row in a session the ledger never attributed).
            raise ReceiptsIncomplete('send receipts incomplete; refusing further writes')
        scope = _Scope()
        first = [True]

        def attempt(conn):
            if not first[0]:
                scope.new_attempt()     # a retried callback: the previous attempt's candidates are void
            first[0] = False
            result = fn(_ConnProxy(conn, scope))
            scope.callback_returned = True
            return result

        try:
            facts.write('write_intent', wid=wid, method=method)   # BEFORE Hermes writes
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            raise ReceiptsIncomplete('send receipts unavailable; refusing the write') from exc
        local.depth, local.scope = 1, scope
        try:
            result = original(self, attempt, patience_s)
        except BaseException:
            local.depth = 0
            if scope.callback_returned:
                facts.safe('write_unsettled', wid=wid, method=method, attempts=scope.attempts)
            else:
                facts.safe('write_rolled_back', wid=wid, method=method, attempts=scope.attempts,
                           candidates=len(scope.rows))
            raise
        local.depth = 0
        rows = [{**r, 'class': sp.classify(r, method)} for r in scope.rows]
        if not facts.safe('write_committed', wid=wid, method=method, attempts=scope.attempts, rows=rows,
                          sessions=scope.sessions, unidentified=scope.unidentified):
            # Hermes has committed; the receipt could not be. Never raise into Hermes for THIS
            # write (it succeeded) and never guess the receipt later.
            facts.safe('receipt_gap', wid=wid, method=method)
            facts.gap = True
        return result

    session_db_class._execute_write = _execute_write
    return _execute_write


class Watchdog(threading.Thread):
    """Reads the ledger's stop flag and deadline; delivers ONE interrupt to Hermes's
    main thread (the Ctrl-C path). Works without the controller."""

    def __init__(self, ledger_path, send_id, facts, interval):
        super().__init__(name='tamanitomo-send-watchdog', daemon=True)
        self.ledger_path, self.send_id, self.facts, self.interval = ledger_path, send_id, facts, interval
        self.lock = threading.Lock()
        self.done = False
        self.fired = None

    def run(self):
        try:
            con = sp.connect(self.ledger_path, readonly=True)
        except sqlite3.Error:
            return
        try:
            while True:
                with self.lock:
                    if self.done:
                        return
                try:
                    row = con.execute('SELECT stop_requested_at, deadline_at FROM sends WHERE send_id=?',
                                      (self.send_id,)).fetchone()
                except sqlite3.Error:
                    row = None
                reason = None
                if row and row[0] is not None:
                    reason = 'stop'
                elif row and row[1] is not None and time.time() >= row[1]:
                    reason = 'deadline'
                if reason:
                    self.facts.safe('stop_seen', reason=reason)
                    with self.lock:
                        if self.done:
                            return
                        self.fired = reason
                        _thread.interrupt_main()
                    return
                time.sleep(self.interval)
        finally:
            con.close()

    def finish(self):
        with self.lock:
            self.done = True


def read_go(stream):
    line = stream.readline()
    if not line:
        return None
    try:
        go = json.loads(line)
    except ValueError:
        return None
    if not (isinstance(go, dict) and isinstance(go.get('go'), str) and isinstance(go.get('send_id'), str)
            and isinstance(go.get('ledger'), str) and re.fullmatch(r'snd_[a-z2-7]{26}', go['send_id'])):
        return None
    return go


def take_lock(directory, send_id):
    """S1. Returns (fd, (dev, ino)) or None. The fd is never inherited by children."""
    path = Path(directory) / 'executors' / f'{send_id}.lock'
    try:
        fd = sp.open_lock_file(path, create=True)
    except OSError:
        return None
    try:
        sp.fcntl.flock(fd, sp.fcntl.LOCK_EX | sp.fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    st = os.fstat(fd)
    return fd, (st.st_dev, st.st_ino)


def register(directory, send_id, token, identity):
    """S2. True when this executor is now the send's tracked executor."""
    ledger = Path(directory) / sp.LEDGER_FILE
    try:
        with sp.guard(directory, exclusive=False, timeout=10):
            con = sp.connect(ledger)
            try:
                with sp.immediate(con):
                    row = con.execute('SELECT launch_token, state FROM sends WHERE send_id=?',
                                      (send_id,)).fetchone()
                    if not row or row[0] != token or row[1] != 'launching':
                        return False
                    sp.insert_fact(con, send_id, token, 'executor_started', identity)
                return True
            finally:
                con.close()
    except (sp.Busy, OSError, sqlite3.Error):
        return None


def private_wire():
    """Move the controller's pipes off fds 0 and 1. The wire keeps a private, non-inheritable
    duplicate of stdout; fds 0 and 1 become /dev/null, so no process Hermes starts inherits the
    controller's pipe (it would hold the stream open after this executor exits)."""
    wire = os.fdopen(os.dup(1), 'w', encoding='utf-8', errors='replace', buffering=1)
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.close(devnull)
    return wire


def main(argv=None, stdin=None, wire=None):
    argv = sys.argv[1:] if argv is None else argv
    stdin = sys.stdin if stdin is None else stdin
    hermes_argv = argv[argv.index('--') + 1:] if '--' in argv else argv

    def emit(kind, **values):
        try:
            wire.write(json.dumps({'event': kind, **values}, ensure_ascii=False) + '\n')
            wire.flush()
        except (OSError, ValueError):
            pass                        # the controller went away; the ledger is the record

    go = read_go(stdin)
    if go is None:
        return EXIT_NO_GO
    if wire is None:
        wire = private_wire()
    directory, send_id, token = go['ledger'], go['send_id'], go['go']
    held = take_lock(directory, send_id)
    if held is None:
        return EXIT_LOCK_BUSY
    fd, lock_identity = held
    pid = os.getpid()
    identity = {'pid': pid, 'pgid': os.getpgid(0), 'start': sp.start_time(pid), 'boot': sp.boot_id(),
                'lock_identity': list(lock_identity)}
    try:                                # the identity is also left in the lock file itself, for a
        os.ftruncate(fd, 0)             # reset that cannot read the ledger (4.1 step 3)
        os.pwrite(fd, json.dumps(identity).encode(), 0)
    except OSError:
        pass
    registered = register(directory, send_id, token, identity)
    if registered is None:
        return EXIT_REGISTRATION
    if not registered:
        return EXIT_NOT_AUTHORISED
    emit('started', send_id=send_id)

    ledger = str(Path(directory) / sp.LEDGER_FILE)
    facts = Facts(ledger, send_id, token)
    watchdog = Watchdog(ledger, send_id, facts, float(go.get('poll') or 1.0))
    code, interrupted, capability = 1, False, 'full'
    output = io.StringIO()
    try:
        watchdog.start()
        with contextlib.redirect_stdout(output):
            try:
                import hermes_state
                ok, why = seam_available(hermes_state.SessionDB)
            except Exception as exc:   # the seam is part of Hermes; its absence is a downgrade
                ok, why = False, f'hermes_state unavailable: {type(exc).__name__}'
            if ok:
                install_recorder(hermes_state.SessionDB, facts)
            else:
                capability = 'unverified_sources'
                facts.safe('capability_downgrade', missing=[why])
            import cli
            configure = getattr(cli, '_configure_quiet_agent', None)
            if configure:
                def configured(agent, *args, **kwargs):
                    configure(agent, *args, **kwargs)
                    agent.stream_delta_callback = (lambda delta: emit('delta', text=delta)
                                                   if isinstance(delta, str) else None)
                cli._configure_quiet_agent = configured
            from hermes_cli.main import main as hermes_main
            sys.argv = ['hermes', *hermes_argv]
            try:
                hermes_main()
                code = 0
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except KeyboardInterrupt:
        code, interrupted = 130, True
    except BaseException:
        code = 1
    # Close the interrupt window: after this no interrupt can be delivered, and one that was
    # already delivered is absorbed here (it arrived after Hermes returned; the outcome stands).
    for _ in range(3):
        try:
            watchdog.finish()
            for _ in range(200):
                pass
            break
        except KeyboardInterrupt:
            continue
    interrupted = interrupted or code == 130
    complete = not facts.gap and capability == 'full'
    try:
        facts.write('executor_finished', exit=code, interrupted=interrupted,
                    timed_out=watchdog.fired == 'deadline', receipts_complete=complete,
                    capability=capability)
    except BaseException:
        pass        # the controller then sees no finish fact: `unknown`, never `complete`
    return code


if __name__ == '__main__':
    sys.exit(main())
