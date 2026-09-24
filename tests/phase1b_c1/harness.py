"""Phase 1B C1 test harness (tests only; never shipped).

Builds synthetic profile homes and SendService instances whose executor runs either
the local fake Hermes double (protocol/crash tests) or the pinned Hermes (the
integration lane, see pinned_lane.py). No live profile, credential or message is used.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kit.app import chat_sends as cs            # noqa: E402
from kit.app.chat_projection import ChatScope   # noqa: E402

FAKE = pathlib.Path(__file__).resolve().parent / 'fake_hermes'
LINUX = sys.platform.startswith('linux')


def scope_for(home, installation='synthetic'):
    return ChatScope(installation=installation, profile='default', home=str(pathlib.Path(home).resolve()),
                     binding_digest='test')


def fake_executor(home, extra_path=()):
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': str(home), 'HERMES_HOME': str(home),
           'PYTHONPATH': os.pathsep.join([*map(str, extra_path), str(FAKE)]), 'PYTHONDONTWRITEBYTECODE': '1'}
    return cs.ExecutorSpec(python=sys.executable, env=env, cwd=str(home))


def scenario(home, **values):
    (pathlib.Path(home) / 'fake_scenario.json').write_text(json.dumps(values))


def workspace_only(scope, session):
    return None


def resume_any(kind='workspace'):
    return lambda scope, session: (kind, None)


class Env:
    """A synthetic profile home + app state in a temp directory."""

    def __init__(self, test, name='home'):
        tmp = tempfile.TemporaryDirectory(prefix='c1-')
        test.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.home = self.root / name
        self.home.mkdir()
        self.state = self.root / 'app-state'
        self.test = test

    def service(self, executor=None, **kw):
        svc = cs.SendService(self.home, self.state, executor or fake_executor(self.home), **kw)
        self.test.addCleanup(svc.close)
        return svc


def send(svc, scope, message='A synthetic owner message', session=None, key=None, generation=None,
         authorize=workspace_only):
    if generation is None:
        generation = svc.bootstrap(scope)['generation']
    body = {'client_key': key or cs.new_ulid(), 'generation': generation, 'conversation_id': scope.conversation_id,
            'message': message, 'session': session}
    return body, svc.accept(scope, body, authorize)


def ledger_rows(svc, sql, *params):
    con = cs.sp.connect(svc.db, readonly=True)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def facts(svc, send_id):
    return [(k, json.loads(d)) for k, d in ledger_rows(
        svc, 'SELECT kind, data FROM send_facts WHERE send_id=? ORDER BY seq', send_id)]
