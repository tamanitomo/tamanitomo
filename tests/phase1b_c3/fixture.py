"""A real HTTP server for the Phase 1B C3 browser checks. Synthetic only.

A temporary Hermes root with two profiles (nova, rowan), the app built with keyed sends
AND the keyed client explicitly enabled (`chat_sends=Options(client=True)`), the executor
pointed at the fake Hermes protocol double (tests/phase1b_c1/fake_hermes). Nothing reaches
a model, a platform or a live profile. `uvicorn` serves it on 127.0.0.1 in a thread so a
real browser can load the actual page; test code reads the same ledger the server writes.
"""
from __future__ import annotations

import json
import pathlib
import socket
import sqlite3
import tempfile
import threading
import time
import urllib.request

import companion_config as cc

from kit.app import chat_send_routes as csr
from kit.app import send_protocol as sp
from kit.app.server import build
from tests.phase1b_c1 import harness as h

TOKEN = 'c3-synthetic-token'


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, client=True, keyed=True):
        self._tmp = tempfile.TemporaryDirectory(prefix='c3b-')
        self.tmp = pathlib.Path(self._tmp.name)
        self.root = self.tmp / 'hermes'
        vault = self.tmp / 'vault'
        self.root.mkdir()
        vault.mkdir()
        self.companions = {}
        for name, agent in (('nova', 'Nova'), ('rowan', 'Rowan')):
            c = cc.Companion(agent=agent, profile=name, hermes_root=self.root, vault=vault, soul_in_vault=False,
                             context_mode='fixed')
            c.home.mkdir(parents=True)
            c.save()
            self.companions[name] = c
        self.pause = self.tmp / 'pause'
        self.pause.mkdir()
        options = csr.Options(executor=lambda rt, home: h.fake_executor(home), turn_timeout=120, stop_grace=1.0,
                              watchdog_interval=0.1, client=client) if keyed else None
        self.app = build(self.root, token=TOKEN, state_dir=self.tmp / 'state', chat_sends=options)
        import uvicorn
        self.port = free_port()
        self.server = uvicorn.Server(uvicorn.Config(self.app, host='127.0.0.1', port=self.port, log_level='warning',
                                                    lifespan='off'))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        end = time.monotonic() + 20
        while not self.server.started:
            if time.monotonic() > end:
                raise RuntimeError('fixture server did not start')
            time.sleep(0.02)

    @property
    def base(self):
        return f'http://127.0.0.1:{self.port}'

    def url(self, profile='nova', tab='chat'):
        return f'{self.base}/?installation=existing&profile={profile}&token={TOKEN}#{tab}'

    def close(self):
        self.server.should_exit = True
        self.thread.join(10)
        if getattr(self.app.state, 'chat_sends', None) is not None:
            self.app.state.chat_sends.close()
        self._tmp.cleanup()

    # ----- the synthetic Hermes and the ledger the server writes -----

    def home(self, profile='nova'):
        return self.companions[profile].home

    def scenario(self, profile='nova', **values):
        h.scenario(self.home(profile), **values)

    def gated(self, steps, profile='nova', **values):
        """A reply streamed in `steps`; step i (i >= 1) waits for release(i)."""
        for f in self.pause.glob('*'):
            f.unlink()
        self.scenario(profile, stream_steps=steps, stream_pause_dir=str(self.pause), **values)

    def reached(self, step):
        return (self.pause / f'at{step}').exists()

    def release(self, step):
        (self.pause / f'go{step}').write_text('')

    def sends(self, profile='nova'):
        path = sp.ledger_dir(self.home(profile)) / sp.LEDGER_FILE
        if not path.exists():
            return []
        con = sp.connect(path, readonly=True)
        try:
            return [dict(zip(('send_id', 'client_key', 'state', 'owner_turn'), r)) for r in
                    con.execute('SELECT send_id, client_key, state, owner_turn FROM sends ORDER BY created_at')]
        finally:
            con.close()

    def launches(self, send_id, profile='nova'):
        con = sp.connect(sp.ledger_dir(self.home(profile)) / sp.LEDGER_FILE, readonly=True)
        try:
            return con.execute("SELECT count(*) FROM send_facts WHERE send_id=? AND kind='executor_started'",
                               (send_id,)).fetchone()[0]
        finally:
            con.close()

    def owner_rows(self, profile='nova'):
        db = self.home(profile) / 'state.db'
        if not db.exists():
            return []
        con = sqlite3.connect(db)
        try:
            return [r[0] for r in con.execute("SELECT content FROM messages WHERE role='user' ORDER BY id")]
        finally:
            con.close()

    def api(self, method, path, body=None, profile='nova'):
        """Direct HTTP to the fixture (the test acting as another client)."""
        sep = '&' if '?' in path else '?'
        req = urllib.request.Request(f'{self.base}/api{path}{sep}installation=existing&profile={profile}',
                                     method=method, headers={'x-tamanitomo-token': TOKEN,
                                                             'content-type': 'application/json'},
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read() or b'null')
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'null')

    def raw_post(self, path, data, profile='nova'):
        """Deliver an intercepted browser POST body to the server unchanged (a late arrival)."""
        sep = '&' if '?' in path else '?'
        req = urllib.request.Request(f'{self.base}{path}{sep}installation=existing&profile={profile}',
                                     method='POST', data=data,
                                     headers={'x-tamanitomo-token': TOKEN, 'content-type': 'application/json',
                                              'origin': self.base})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def settled(self, send_id, profile='nova', timeout=60):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            status, receipt = self.api('GET', f'/chat/sends/{send_id}', profile=profile)
            if status == 200 and receipt.get('settled'):
                return receipt
            time.sleep(0.05)
        raise AssertionError(f'{send_id} did not settle')
