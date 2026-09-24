"""C1 pinned seam driver -- run with the pinned Hermes interpreter (tests only; never shipped).

    <hermes python> pinned_seams.py <ledger.sqlite3> <send_id> <token> <scenario> <workdir>

Drives the REAL pinned SessionDB through the PRODUCTION recorder (kit/app/send_executor.py
install_recorder + Facts, loaded by path) and writes facts into a real send ledger.
Scenarios model what a full CLI turn was not observed doing (compression) or is hard to
time (a receipt failure right after a Hermes commit). Prints one JSON line.
"""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('c1_pinned_executor', ROOT / 'kit' / 'app' / 'send_executor.py')
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)


def main(ledger, send_id, token, scenario, work):
    from hermes_state import SessionDB
    facts = ex.Facts(ledger, send_id, token)
    ex.install_recorder(SessionDB, facts)
    db = SessionDB(db_path=pathlib.Path(work) / 'state.db')
    out = {'scenario': scenario, 'error': None}
    sid = 'c1-session'
    try:
        db.create_session(sid, 'cli')
        if scenario == 'clone_then_death':
            db.append_message(sid, 'user', 'synthetic owner')
            db.append_message(sid, 'assistant', 'synthetic reply', finish_reason='stop')
            watermark = db.get_active_message_watermark(sid) - 1
            db.publish_compression_child(parent_session_id=sid, child_session_id='c1-child', source='cli',
                                         messages=[{'role': 'user', 'content': 'summary'}],
                                         require_compression_lease=False, watermark=watermark)
        elif scenario == 'gap_after_owner_commit':
            original, fired = ex.Facts._insert, []
            def failing(self, kind, data):
                if kind == 'write_committed' and not fired and any(
                        r.get('class') == 'user_turn' for r in data.get('rows') or []):
                    fired.append(1)
                    raise __import__('sqlite3').OperationalError('injected receipt failure')
                return original(self, kind, data)
            ex.Facts._insert = failing
            out['owner_row'] = db.append_message(sid, 'user', 'synthetic owner')   # must NOT raise
            try:
                db.append_message(sid, 'assistant', 'synthetic reply', finish_reason='stop')
                out['later_write'] = 'accepted'
            except ex.ReceiptsIncomplete:
                out['later_write'] = 'refused'
        elif scenario == 'hidden_and_summary_owner_rows':
            db.append_message(sid, 'user', 'synthetic notice', display_kind='notice')
            db.append_message(sid, 'user', 'synthetic summary', _compressed_summary=True)
            db.append_message(sid, 'assistant', 'synthetic reply', finish_reason='stop')
        else:
            raise SystemExit(f'unknown scenario {scenario}')
    except Exception as exc:
        out['error'] = type(exc).__name__
    import sqlite3
    con = sqlite3.connect(str(pathlib.Path(work) / 'state.db'))
    out['state_rows'] = [list(r) for r in con.execute('SELECT id, session_id, role FROM messages ORDER BY id')]
    con.close()
    print(json.dumps(out))


if __name__ == '__main__':
    main(*sys.argv[1:6])
