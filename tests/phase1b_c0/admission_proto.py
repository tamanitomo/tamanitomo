"""C0 HARNESS / PROTOTYPE of send-ledger admission and explicit reset -- not production.

Two admission rules over a real SQLite ledger file, so a test can compare them:

* `floor`      -- revision 2 (section 4.1/5.3): a key is admitted iff its client
                  timestamp is >= meta.admission_floor (creation or reset time) and
                  within the freshness window.
* `generation` -- the amended rule: bootstrap returns an opaque, server-made
                  `generation`; the client freezes it into the pending send with
                  the key and resubmits both unchanged. A request whose generation
                  is not the ledger's current one is never accepted as new
                  (`409 generation_changed`). Freshness (24 h / +5 min) is checked
                  separately and never acts as the reset fence.

Reset is serialised with acceptance and executor registration by one
ownership lock (`guard.lock`): acceptance and S2 registration hold it shared,
reset holds it exclusive, fences every open launch token in the old ledger,
checks quiescence (every executor lock acquirable), and only then moves the old
ledger aside and creates a new generation.
"""
from __future__ import annotations

import contextlib
import fcntl
import os
import pathlib
import secrets
import sqlite3

DAY = 24 * 3600
FUTURE = 300


class Refused(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class Ledger:
    def __init__(self, directory, rule, clock):
        self.dir = pathlib.Path(directory)
        self.rule = rule
        self.clock = clock                  # server time, a callable
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / 'executors').mkdir(exist_ok=True)

    @property
    def db(self):
        return self.dir / 'ledger.sqlite3'

    @contextlib.contextmanager
    def guard(self, exclusive, blocking=True):
        with (self.dir / 'guard.lock').open('a+b') as handle:
            flags = (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | (0 if blocking else fcntl.LOCK_NB)
            try:
                fcntl.flock(handle, flags)
            except BlockingIOError:
                raise Refused('ledger_busy')
            yield

    def _connect(self):
        con = sqlite3.connect(str(self.db), timeout=5, isolation_level=None)
        con.execute('PRAGMA journal_mode=DELETE')
        return con

    def _create(self):
        con = self._connect()
        con.executescript('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);'
                          'CREATE TABLE IF NOT EXISTS sends(client_key TEXT PRIMARY KEY, digest TEXT, '
                          'state TEXT, launch_token TEXT, claim INTEGER DEFAULT 1);')
        con.execute('BEGIN IMMEDIATE')
        con.execute("INSERT OR IGNORE INTO meta VALUES ('generation', ?)", (secrets.token_hex(16),))
        con.execute("INSERT OR IGNORE INTO meta VALUES ('admission_floor', ?)", (repr(self.clock()),))
        con.execute('COMMIT')
        con.close()

    def meta(self, key):
        con = self._connect()
        try:
            return con.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()[0]
        finally:
            con.close()

    def bootstrap(self):
        """Amended: first-use initialisation happens here, BEFORE the client mints
        and freezes its pending send. Returns the current generation."""
        with self.guard(exclusive=False):
            if not self.db.exists():
                self._create()
            return self.meta('generation')

    def accept(self, key, key_time, digest, generation=None):
        with self.guard(exclusive=False):
            if not self.db.exists():
                if self.rule == 'generation':
                    raise Refused('not_bootstrapped')
                self._create()                  # revision 2: first POST initialises
            con = self._connect()
            try:
                con.execute('BEGIN IMMEDIATE')
                row = con.execute('SELECT digest, state FROM sends WHERE client_key=?', (key,)).fetchone()
                if row:
                    con.execute('COMMIT')
                    if row[0] != digest:
                        raise Refused('key_conflict')
                    return 'replay'
                now = self.clock()
                if self.rule == 'generation':
                    current = con.execute("SELECT value FROM meta WHERE key='generation'").fetchone()[0]
                    if generation != current:
                        con.execute('ROLLBACK')
                        raise Refused('generation_changed')
                else:
                    floor = float(con.execute("SELECT value FROM meta WHERE key='admission_floor'").fetchone()[0])
                    if key_time < floor:
                        con.execute('ROLLBACK')
                        raise Refused('key_predates_ledger')
                if key_time < now - DAY:
                    con.execute('ROLLBACK')
                    raise Refused('key_expired')
                if key_time > now + FUTURE:
                    con.execute('ROLLBACK')
                    raise Refused('key_in_future')
                token = secrets.token_hex(8)
                con.execute("INSERT INTO sends VALUES (?, ?, 'launching', ?, 1)", (key, digest, token))
                con.execute('COMMIT')
                return 'accepted'
            finally:
                con.close()

    def register_executor(self, key, token, hold=None):
        """S2: the executor proves its authorisation under the shared guard.
        `hold` is a test hook called while the guard and transaction are held."""
        with self.guard(exclusive=False):
            con = self._connect()
            try:
                con.execute('BEGIN IMMEDIATE')
                row = con.execute('SELECT launch_token FROM sends WHERE client_key=?', (key,)).fetchone()
                if not row or row[0] != token:
                    con.execute('ROLLBACK')
                    return False
                if hold:
                    hold()
                con.execute("UPDATE sends SET state='generating' WHERE client_key=?", (key,))
                con.execute('COMMIT')
                return True
            finally:
                con.close()

    def token(self, key):
        con = self._connect()
        try:
            return con.execute('SELECT launch_token FROM sends WHERE client_key=?', (key,)).fetchone()[0]
        finally:
            con.close()

    def reset(self, blocking=False):
        """Explicit owner reset. Exclusive guard -> fence -> quiescence -> replace."""
        with self.guard(exclusive=True, blocking=blocking):
            if self.db.exists():
                con = self._connect()
                con.execute('BEGIN IMMEDIATE')
                con.execute('UPDATE sends SET launch_token=NULL, claim=claim+1 WHERE launch_token IS NOT NULL')
                con.execute('COMMIT')
                con.close()
            for lock in (self.dir / 'executors').glob('*.lock'):
                with lock.open('a+b') as handle:
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        raise Refused('executor_live')
            if self.db.exists():
                os.replace(self.db, self.dir / f'ledger.lost-{int(self.clock())}.sqlite3')
            self._create()
            return self.meta('generation')
