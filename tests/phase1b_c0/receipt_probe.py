"""C0 HARNESS / PROTOTYPE -- not production code, not shipped, not wired into the app.

Source-receipt recorders that run INSIDE a Hermes interpreter (the pinned
revision) and write metadata-only facts to a separate SQLite "receipt ledger",
standing in for the proposed send ledger's `send_facts` table.

Two recorders, so a test can show the defect and the correction side by side:

* `rev2`   -- what PHASE1B_DESIGN.md revision 2 (7907066) specified in section 4.10.1:
              wrap append_message, append_messages_batch, _insert_message_rows,
              replace_messages and create_session; write `row_intent` before and
              `row_written` after each call returns.
* `commit` -- the amended rule: the only commit boundary in the pinned SessionDB
              is `_execute_write` returning (it runs the callback inside
              BEGIN IMMEDIATE and commits; hermes_state.py:773-833). Inserts seen
              inside a callback attempt are CANDIDATES. A retried attempt discards
              the previous attempt's candidates. Candidates become a
              `write_committed` fact only after the outermost `_execute_write`
              returns. A callback that returned but whose commit raised is
              `write_unsettled` (settlement unknown); one that raised is
              `write_rolled_back`. Nested calls publish nothing of their own.

Neither recorder stores message text. Row facts hold ids, role and a
classification computed inside the write transaction from the row itself.
"""
from __future__ import annotations

import functools
import json
import re
import sqlite3
import sys
import threading
import time

_INSERT_MESSAGES = re.compile(r'^\s*INSERT\s+INTO\s+messages\s*\(', re.I)
_INSERT_SESSIONS = re.compile(r'^\s*INSERT\s+(?:OR\s+\w+\s+)?INTO\s+sessions\s*\(([^)]*)\)', re.I)
_TURN_METHODS = {'append_message', 'append_messages_batch'}


class Ledger:
    """The stand-in receipt ledger. `fail_next` injects one failed fact write."""

    def __init__(self, path):
        self.path = str(path)
        self.fail_next = 0
        con = sqlite3.connect(self.path)
        con.execute('PRAGMA journal_mode=DELETE')
        con.execute('CREATE TABLE IF NOT EXISTS facts(seq INTEGER PRIMARY KEY AUTOINCREMENT, '
                    'kind TEXT NOT NULL, data TEXT NOT NULL, at REAL NOT NULL)')
        con.commit();con.close()

    def fact(self, kind, **data):
        if self.fail_next:
            self.fail_next -= 1
            raise sqlite3.OperationalError('injected receipt-ledger write failure')
        con = sqlite3.connect(self.path, timeout=5)
        try:
            with con:
                con.execute('INSERT INTO facts(kind,data,at) VALUES (?,?,?)',
                            (kind, json.dumps(data, sort_keys=True), time.time()))
        finally:
            con.close()


def _row_facts(conn, row_id):
    """Classification of one row, read back inside the write transaction."""
    row = conn.execute(
        'SELECT session_id, role, tool_calls, content IS NOT NULL AND length(content) > 0, '
        'display_kind, _compressed_summary, observed FROM messages WHERE id = ?', (row_id,)).fetchone()
    if row is None:
        return None
    session_id, role, tool_calls, has_text, display_kind, summary, observed = row
    has_tools = bool(tool_calls) and tool_calls not in ('[]', 'null')
    return {'session_id': session_id, 'row_id': int(row_id), 'role': role, 'has_text': bool(has_text),
            'has_tool_calls': has_tools, 'display_kind': display_kind, 'summary': bool(summary),
            'observed': bool(observed)}


class _Scope:
    def __init__(self, method):
        self.method = method
        self.reset()

    def reset(self):
        self.attempts = getattr(self, 'attempts', 0) + 1
        self.rows = []
        self.sessions = []
        self.unidentified = 0
        self.callback_returned = False


class _ConnProxy:
    """Passes everything to the real connection; observes INSERTs into messages/sessions."""

    def __init__(self, conn, scope):
        object.__setattr__(self, '_conn', conn)
        object.__setattr__(self, '_scope', scope)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        setattr(self._conn, name, value)

    def execute(self, sql, params=()):
        scope = self._scope
        if isinstance(sql, str) and _INSERT_MESSAGES.match(sql):
            cur = self._conn.execute(sql, params)
            if re.search(r'\bSELECT\b', sql, re.I):
                # INSERT ... SELECT (the pure-SQL clone, hermes_state_messages.py:498-506):
                # several rows, one statement, no per-row id. Counted (changes() excludes
                # the FTS trigger rows), not identified.
                scope.unidentified += self._conn.execute('SELECT changes()').fetchone()[0]
            elif cur.lastrowid is not None:
                facts = _row_facts(self._conn, cur.lastrowid)
                if facts:
                    scope.rows.append(facts)
                else:
                    scope.unidentified += 1
            return cur
        match = _INSERT_SESSIONS.match(sql) if isinstance(sql, str) else None
        if match:
            columns = [c.strip().lower() for c in match.group(1).split(',')]
            sid = params[columns.index('id')] if 'id' in columns and isinstance(params, (list, tuple)) else None
            existed = None
            if sid is not None:
                existed = self._conn.execute('SELECT 1 FROM sessions WHERE id = ?', (sid,)).fetchone() is not None
            cur = self._conn.execute(sql, params)
            exists = sid is not None and self._conn.execute(
                'SELECT 1 FROM sessions WHERE id = ?', (sid,)).fetchone() is not None
            scope.sessions.append({'session_id': sid, 'fresh': bool(sid is not None and existed is False and exists),
                                   'existed_before': existed})
            return cur
        return self._conn.execute(sql, params)


def _classify(row, method):
    """What a committed row can be evidence of. Only a turn-path, text-bearing, tool-free,
    ordinary assistant row is public turn output; copies made by rewrites never are."""
    if method not in _TURN_METHODS:
        return 'rewrite_copy'
    if row['role'] == 'user':
        return 'user_turn'
    if row['role'] == 'assistant':
        if row['has_tool_calls'] or not row['has_text']:
            return 'assistant_internal'
        if row['display_kind'] or row['summary'] or row['observed']:
            return 'assistant_internal'
        return 'public_output'
    return 'internal'


def install_commit(ledger):
    """Commit-aware recorder (the amended section 4.10.1)."""
    from hermes_state import SessionDB
    original = SessionDB._execute_write
    local = threading.local()
    counter = iter(range(1, 1 << 30))

    @functools.wraps(original)
    def _execute_write(self, fn, patience_s=None):
        depth = getattr(local, 'depth', 0)
        if depth:
            # Nested: the enclosing scope owns the observations; nothing is published here.
            outer = local.scope
            def nested(conn):
                return fn(conn if isinstance(conn, _ConnProxy) else _ConnProxy(conn, outer))
            return original(self, nested, patience_s)
        method = sys._getframe(1).f_code.co_name
        wid = next(counter)
        scope = _Scope(method)
        first = [True]

        def attempt(conn):
            if not first[0]:
                scope.reset()          # a retried callback: the previous attempt's candidates are void
            first[0] = False
            result = fn(_ConnProxy(conn, scope))
            scope.callback_returned = True
            return result

        if getattr(ledger, 'receipt_gap', 0):
            # Fail closed: once a committed write could not be receipted, no later write may
            # land (it could be an owner row in a session the ledger never attributed).
            raise sqlite3.OperationalError('send receipts incomplete; refusing further writes')
        ledger.fact('write_intent', wid=wid, method=method)   # fails closed BEFORE Hermes writes
        local.depth, local.scope = 1, scope
        try:
            result = original(self, attempt, patience_s)
        except BaseException:
            local.depth = 0
            if scope.callback_returned:
                _safe_fact(ledger, 'write_unsettled', wid=wid, method=method, attempts=scope.attempts)
            else:
                _safe_fact(ledger, 'write_rolled_back', wid=wid, method=method, attempts=scope.attempts,
                           candidates=len(scope.rows))
            raise
        local.depth = 0
        rows = [{**r, 'class': _classify(r, method)} for r in scope.rows]
        try:
            ledger.fact('write_committed', wid=wid, method=method, attempts=scope.attempts, rows=rows,
                        sessions=scope.sessions, unidentified=scope.unidentified)
        except Exception:
            # Hermes has committed; the receipt could not be. Never raise into Hermes for THIS
            # write (it succeeded) and never guess the receipt later: the gap is recorded if
            # possible, later writes are refused, and executor_finished cannot claim complete receipts.
            ledger.receipt_gap = getattr(ledger, 'receipt_gap', 0) + 1
            _safe_fact(ledger, 'receipt_gap', wid=wid, method=method)
        return result

    SessionDB._execute_write = _execute_write
    return ledger


def _safe_fact(ledger, kind, **data):
    try:
        ledger.fact(kind, **data)
    except Exception:
        ledger.receipt_gap = getattr(ledger, 'receipt_gap', 0) + 1


def install_rev2(ledger):
    """Revision 2's recorder, reproduced from its text, to demonstrate the defect."""
    from hermes_state import SessionDB

    def wrap(name, kind):
        original = getattr(SessionDB, name)

        @functools.wraps(original)
        def wrapper(self, *args, **kwargs):
            session_id = args[0] if args and isinstance(args[0], str) else kwargs.get('session_id')
            if name == '_insert_message_rows':
                session_id = args[1] if len(args) > 1 else kwargs.get('session_id')
            ledger.fact('row_intent', method=name, session_id=session_id)
            result = original(self, *args, **kwargs)
            if name == 'append_message':
                ledger.fact('row_written', method=name, session_id=session_id, row_id=int(result))
            elif name == '_insert_message_rows':
                messages = args[2] if len(args) > 2 else kwargs.get('messages')
                for msg in messages:
                    if '_row_id' in msg:
                        ledger.fact('row_written', method=name, session_id=session_id,
                                    row_id=int(msg['_row_id']), role=msg.get('role'))
            elif name == 'create_session':
                ledger.fact('session_created', session_id=result)
            return result
        setattr(SessionDB, name, wrapper)

    for name in ('append_message', 'append_messages_batch', '_insert_message_rows',
                 'replace_messages', 'create_session'):
        wrap(name, None)
    return ledger


def read_facts(path):
    con = sqlite3.connect(str(path))
    try:
        return [{'seq': s, 'kind': k, 'at': at, **json.loads(d)} for s, k, d, at in
                con.execute('SELECT seq, kind, data, at FROM facts ORDER BY seq')]
    finally:
        con.close()
