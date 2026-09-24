"""TEST-ONLY: make the executor's `row_provenance` fact write fail (tests only; never shipped).

Placed on one executor's PYTHONPATH by tests/test_phase1b_c1_pinned.py: the continuation
note is then committed without its provenance, and the receipt must stay conservative.
"""
import sqlite3

_connect = sqlite3.connect


class _Ledger:
    def __init__(self, con):
        self._con = con

    def __getattr__(self, name):
        return getattr(self._con, name)

    def execute(self, sql, params=()):
        if isinstance(sql, str) and sql.startswith('INSERT INTO send_facts') and params \
                and params[2] == 'row_provenance':
            raise sqlite3.OperationalError('injected provenance write failure')
        return self._con.execute(sql, params)


def connect(database, *args, **kwargs):
    con = _connect(database, *args, **kwargs)
    name = str(database)
    if 'ledger.sqlite3' in name and 'mode=ro' not in name:
        return _Ledger(con)
    return con


sqlite3.connect = connect
