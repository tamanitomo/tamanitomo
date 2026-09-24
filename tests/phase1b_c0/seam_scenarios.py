"""C0 HARNESS -- run with the pinned Hermes interpreter, never imported by the app.

    <hermes python> seam_scenarios.py <mode: rev2|commit> <scenario> <workdir>

Drives the REAL pinned SessionDB (hermes_state*.py at 0e9fc2cc15) in a synthetic
state.db and prints one JSON object: the receipt facts the recorder wrote and the
rows actually committed in state.db. Faults are injected by monkeypatching Hermes
methods in this process only (U6); nothing here ships.
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import receipt_probe  # noqa: E402

SID = 'c0-session'


def _msgs(*roles):
    out = []
    for i, role in enumerate(roles):
        if role == 'assistant_tool':
            out.append({'role': 'assistant', 'content': '',
                        'tool_calls': [{'id': f'call_{i}', 'type': 'function',
                                        'function': {'name': 'noop', 'arguments': '{}'}}]})
        else:
            out.append({'role': role, 'content': f'synthetic {role} {i}'})
    return out


def committed_rows(db_path):
    con = sqlite3.connect(str(db_path))
    try:
        return [{'row_id': r[0], 'session_id': r[1], 'role': r[2], 'active': r[3]}
                for r in con.execute('SELECT id, session_id, role, active FROM messages ORDER BY id')]
    finally:
        con.close()


def sessions(db_path):
    con = sqlite3.connect(str(db_path))
    try:
        return [r[0] for r in con.execute('SELECT id FROM sessions ORDER BY id')]
    finally:
        con.close()


def run(mode, scenario, work):
    from hermes_state import SessionDB
    ledger = receipt_probe.Ledger(work / 'receipts.sqlite3')
    db_path = work / 'state.db'
    db = SessionDB(db_path=db_path)
    db.create_session(SID, 'cli')                      # set-up, before the recorder is installed
    (receipt_probe.install_commit if mode == 'commit' else receipt_probe.install_rev2)(ledger)
    out = {'scenario': scenario, 'mode': mode, 'error': None, 'notes': {}}
    try:
        _scenario(scenario, db, ledger, db_path, out)
    except Exception as exc:                           # the scenario's own injected failure
        out['error'] = type(exc).__name__
    out['facts'] = receipt_probe.read_facts(work / 'receipts.sqlite3')
    out['state_rows'] = committed_rows(db_path)
    out['sessions'] = sessions(db_path)
    out['receipt_gap'] = getattr(ledger, 'receipt_gap', 0)
    db.close()
    return out


def _scenario(name, db, ledger, db_path, out):
    from hermes_state import SessionDB

    if name == 'append_ok':
        out['notes']['returned_id'] = db.append_message(SID, 'user', 'synthetic owner message')

    elif name == 'batch_rollback_after_inner_insert':
        # The outer operation fails after _insert_message_rows returned (the review's B2.1 trace).
        def boom(self, *a, **k):
            raise RuntimeError('injected failure after the inner insert helper returned')
        SessionDB._bump_session_counters = boom
        db.append_messages_batch(SID, _msgs('user', 'assistant'))

    elif name == 'batch_retry_after_locked':
        # SessionDB retries the WHOLE callback on a locked/busy error raised inside it
        # (hermes_state.py:840-842). The first attempt's row ids are rolled back and reused.
        original = SessionDB._bump_session_counters      # a staticmethod
        state = {'n': 0}
        def flaky(*a, **k):
            state['n'] += 1
            if state['n'] == 1:
                raise sqlite3.OperationalError('database is locked (injected, first attempt only)')
            return original(*a, **k)
        SessionDB._bump_session_counters = staticmethod(flaky)
        out['notes']['returned'] = db.append_messages_batch(SID, _msgs('user', 'assistant'))
        out['notes']['attempts'] = state['n']

    elif name == 'rolled_back_id_reused_by_foreign_writer':
        def boom(self, *a, **k):
            raise RuntimeError('injected')
        original = SessionDB._bump_session_counters
        SessionDB._bump_session_counters = boom
        try:
            db.append_messages_batch(SID, _msgs('user'))
        except RuntimeError:
            pass
        SessionDB._bump_session_counters = original
        # Another process (a terminal) now commits its own row. With AUTOINCREMENT the
        # rolled-back sqlite_sequence update is rolled back too, so the id is handed out again.
        foreign = sqlite3.connect(str(db_path))
        with foreign:
            cur = foreign.execute("INSERT INTO messages (session_id, role, content, timestamp) "
                                  "VALUES (?, 'user', 'a foreign terminal row', 1.0)", (SID,))
        out['notes']['foreign_row_id'] = cur.lastrowid
        foreign.close()

    elif name == 'chunked_batch':
        out['notes']['returned'] = db.append_messages_batch(
            SID, _msgs('user', 'assistant', 'user', 'assistant', 'user'), chunk_rows=2)

    elif name == 'replace_messages_copies':
        db.append_message(SID, 'user', 'synthetic first')
        db.append_message(SID, 'assistant', 'synthetic first reply')
        db.replace_messages(SID, _msgs('user', 'assistant'), archive_dropped=True)

    elif name == 'public_vs_internal_rows':
        db.append_messages_batch(SID, _msgs('user', 'assistant_tool', 'tool', 'assistant'))

    elif name == 'receipt_write_fails_after_source_commit':
        # The FIRST receipt for a committed row fails to reach the receipt ledger.
        original_fact = ledger.fact
        calls = {'n': 0}
        def fact(kind, **data):
            if kind == 'write_committed':
                calls['n'] += 1
                if calls['n'] == 1:
                    raise sqlite3.OperationalError('injected receipt-ledger failure after source commit')
            if kind == 'row_written':
                calls['n'] += 1
                if calls['n'] == 1:
                    raise sqlite3.OperationalError('injected receipt-ledger failure after source commit')
            return original_fact(kind, **data)
        ledger.fact = fact
        try:
            db.append_message(SID, 'user', 'synthetic owner message')
        except Exception as exc:
            out['notes']['caller_saw'] = type(exc).__name__
        try:
            db.append_message(SID, 'assistant', 'synthetic reply')
        except Exception as exc:
            out['notes']['later_write'] = type(exc).__name__

    elif name == 'commit_raises_after_callback':
        # Settlement unknown: the callback ran, then the commit step raised.
        # The pinned code propagates this (hermes_state.py:786-790, 858).
        real = db._conn
        class CommitFails:
            def __init__(self, c): self._c = c
            def __getattr__(self, n): return getattr(self._c, n)
            def commit(self):
                self._c.rollback()
                raise sqlite3.OperationalError('disk I/O error (injected at commit)')
        db._conn = CommitFails(real)
        try:
            db.append_message(SID, 'user', 'synthetic owner message')
        finally:
            db._conn = real

    elif name == 'sessions_create_vs_upsert':
        db.create_session('c0-fresh', 'cli')
        db.create_session(SID, 'cli')                  # already exists: an upsert, not a creation
        db.ensure_session(SID, 'cli')
        db.ensure_session('c0-ensured-fresh', 'cli')
        def boom(*a, **k):
            raise RuntimeError('injected session-row failure after the INSERT')
        SessionDB._inherit_parent_session_metadata = staticmethod(boom)
        try:
            db.create_session('c0-failed', 'cli', parent_session_id=SID)
        except Exception as exc:
            out['notes']['failed_create'] = type(exc).__name__

    elif name == 'compression_child_and_clone':
        for i in range(4):
            db.append_message(SID, 'user' if i % 2 == 0 else 'assistant', f'synthetic {i}')
        watermark = db.get_active_message_watermark(SID) - 1   # the last row "arrived during" compression
        db.publish_compression_child(
            parent_session_id=SID, child_session_id='c0-child', source='cli',
            messages=_msgs('user', 'assistant'), require_compression_lease=False, watermark=watermark)

    elif name == 'archive_and_compact_clone':
        for i in range(4):
            db.append_message(SID, 'user' if i % 2 == 0 else 'assistant', f'synthetic {i}')
        watermark = db.get_active_message_watermark(SID) - 1
        db.archive_and_compact(SID, _msgs('user', 'assistant'), watermark=watermark)

    elif name == 'rewind_replacement':
        first = db.append_message(SID, 'user', 'synthetic first')
        db.append_message(SID, 'assistant', 'synthetic reply')
        result = db.rewind_to_message(SID, first, expected_target_content='synthetic first',
                                      preserve_compaction_handoff=False)
        out['notes']['rewind'] = str(type(result).__name__)

    else:
        raise SystemExit(f'unknown scenario {name}')


if __name__ == '__main__':
    mode, scenario, work = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
    work.mkdir(parents=True, exist_ok=True)
    print(json.dumps(run(mode, scenario, work)))
