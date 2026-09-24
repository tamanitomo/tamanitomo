"""TEST-ONLY fault injector for the C1 pinned lane. Placed on the executor's PYTHONPATH by
tests/test_phase1b_c1_pinned.py only (U6: no shipped code reads a crash variable).

Wraps sqlite3.connect for the send ledger so that the first `write_committed` fact whose
receipt holds the owner row (class user_turn) fails AFTER Hermes has committed that row:
a real receipt gap inside a real CLI turn.
"""
import sqlite3

_connect = sqlite3.connect


class _Ledger:
    fired = False

    def __init__(self, con):
        self._con = con

    def __getattr__(self, name):
        return getattr(self._con, name)

    def execute(self, sql, params=()):
        if (not _Ledger.fired and isinstance(sql, str) and sql.startswith('INSERT INTO send_facts')
                and params and params[2] == 'write_committed' and '"user_turn"' in params[3]):
            _Ledger.fired = True
            raise sqlite3.OperationalError('injected receipt failure after the source commit')
        return self._con.execute(sql, params)


def connect(database, *args, **kwargs):
    con = _connect(database, *args, **kwargs)
    if str(database).endswith('ledger.sqlite3'):
        return _Ledger(con)
    return con


sqlite3.connect = connect
