"""Phase 1C check 3 at the real request boundary: the pinned Hermes CLI resumes a terminal
session, runs companion_context.py as its registered pre_llm_call shell hook, and sends
the model request to the local mock provider (tests/mock_provider.py), whose recorded
request body is what is inspected.

Pinned Hermes 0e9fc2cc15 only (tests/phase1b_c1/pinned_lane.py verifies the exported
tree); skipped without it, a failure when TAMANITOMO_C1_REQUIRE_PINNED=1. Synthetic
root-profile home, fresh HOME/HERMES_HOME, local mock provider, fallbacks disabled.

What this shows: the outgoing request of a resumed turn carries the bounded, labelled
handoff inside the continuity fence of the current user message, the owner's own text
is intact, the session's native history is not repeated, and the hook adds no model
request. It does NOT show that a model uses, recalls or reports that context correctly.
"""
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts'), str(ROOT / 'tests')]

import companion_config as cc                              # noqa: E402
import companion_context as ctx                            # noqa: E402
import companion_self as slf                               # noqa: E402
from chat_fixtures import OWNER_TELEGRAM                   # noqa: E402
from kit.app import chat_sources as csrc                   # noqa: E402
from mock_provider import MockProvider                     # noqa: E402
from tests.phase1b_c1 import pinned_lane as pl             # noqa: E402

BEGIN, END = '<!-- tamanitomo:continuity:begin -->', '<!-- tamanitomo:continuity:end -->'
HEAD = '[Recent messages from your other conversations with Robin'


class PinnedHandoff(unittest.TestCase):

    def setUp(self):
        self.src, self.python = pl.pinned_or_skip(self)
        tmp = tempfile.TemporaryDirectory(prefix='p1c-pinned-')
        self.addCleanup(tmp.cleanup)
        self.home = pathlib.Path(tmp.name) / 'home'
        self.home.mkdir()
        self.provider = MockProvider().__enter__()
        self.addCleanup(self.provider.__exit__, None, None, None)
        pl.synthetic_home(self.home, self.provider, 'deltas')
        hook = f'{sys.executable} {ROOT / "kit/scripts/companion_context.py"} --home {self.home}'
        with open(self.home / 'config.yaml', 'a') as f:
            f.write('hooks_auto_accept: true\n'
                    'hooks:\n'
                    '  pre_llm_call:\n'
                    f'    - command: "{hook}"\n'
                    '  output_spill:\n'
                    '    max_chars: 60000\n')
        c = cc.Companion(agent='Nova', human='Robin', hermes_root=self.home, vault=pathlib.Path(tmp.name) / 'vault',
                         soul_in_vault=False, context_mode='fixed', timezone='UTC')
        c.soul_dir.mkdir(parents=True, exist_ok=True)
        c.soul.write_text('A companion.\n' + slf.BEGIN + '\nI like books.\n' + slf.END + '\n')
        c.save()
        (self.home / csrc.BINDING_FILE).write_text(json.dumps({'telegram': [OWNER_TELEGRAM]}))

    def turn(self, message, session=None, handoff=True):
        env = pl.executor_env(self.src, self.home)
        env['COMPANION_MEMORY_READ_ONLY'] = '1'
        if handoff:
            env[ctx.HANDOFF_ENV] = '1'
        code = 'import sys\nfrom hermes_cli.main import main\nsys.argv = ["hermes", *sys.argv[1:]]\nmain()'
        argv = [self.python, '-c', code, 'chat', '--quiet', '--oneshot', '-q', message, '-m', 'deltas']
        if session:
            argv += ['--resume', session]
        first = len(self.provider.bodies)
        proc = subprocess.run(argv, env=env, cwd=str(self.home), capture_output=True, text=True, timeout=180)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        return self.provider.bodies[first:]

    def db(self):
        return sqlite3.connect(self.home / 'state.db')

    def seed_telegram(self):
        """Owner Telegram DM rows, written into the store the pinned Hermes created (its
        full schema, triggers included), as its gateway would have recorded them."""
        now = time.time()
        with self.db() as con:
            con.execute("INSERT INTO sessions(id,source,user_id,chat_id,chat_type,started_at) VALUES "
                        "('tg','telegram',?,?,'dm',?)", (OWNER_TELEGRAM, OWNER_TELEGRAM, now - 600))
            con.execute("INSERT INTO messages(session_id,role,content,timestamp,platform_message_id) VALUES "
                        "('tg','user','My sister Bee is visiting on Friday.',?, '101')", (now - 500,))
            con.execute("INSERT INTO messages(session_id,role,content,timestamp) VALUES "
                        "('tg','assistant','Oh lovely, say hi to Bee!',?)", (now - 490,))
            con.execute("INSERT INTO sessions(id,source,user_id,chat_id,chat_type,started_at) VALUES "
                        "('stranger','telegram','9999','9999','dm',?)", (now - 400,))
            con.execute("INSERT INTO messages(session_id,role,content,timestamp,platform_message_id) VALUES "
                        "('stranger','user','a stranger writes (must not appear)',?, '7')", (now - 300,))

    @staticmethod
    def user_texts(body):
        return [m['content'] if isinstance(m['content'], str) else json.dumps(m['content'])
                for m in body['messages'] if m.get('role') == 'user']

    def test_a_resumed_turn_request_carries_the_handoff_once(self):
        first = self.turn('First terminal message 5151', handoff=False)
        self.assertTrue(first, 'the pinned CLI reached the mock provider')
        with self.db() as con:
            session = con.execute("SELECT session_id FROM messages WHERE content='First terminal message 5151'").fetchone()[0]
        self.seed_telegram()
        before = self.db().execute('SELECT count(*) FROM messages').fetchone()[0]

        control = self.turn('Hello again 6262', session=session, handoff=False)
        enabled = self.turn('Hello again 7373', session=session)
        self.assertEqual(len(enabled), len(control), 'the handoff adds no model request')

        body = next(b for b in enabled if any('Hello again 7373' in t for t in self.user_texts(b)))
        texts = self.user_texts(body)
        current = texts[-1]
        self.assertTrue(current.startswith('Hello again 7373'), 'the owner\'s raw message leads, intact')
        fenced = current.split(BEGIN, 1)[1].split(END, 1)[0]
        self.assertIn(HEAD, fenced)
        self.assertIn('· Telegram · Robin: "My sister Bee is visiting on Friday."', fenced)
        self.assertIn('· Telegram · Nova (you): "Oh lovely, say hi to Bee!"', fenced)
        self.assertNotIn('must not appear', json.dumps(body))
        self.assertNotIn('First terminal message 5151', fenced, 'native history is not repeated in the handoff')
        self.assertEqual(sum(t.startswith('First terminal message 5151') for t in texts), 1,
                         'the resumed session\'s own row appears once, as native history')
        self.assertEqual(sum(HEAD in t for t in texts), 1, 'one handoff in the request')

        control_body = next(b for b in control if any('Hello again 6262' in t for t in self.user_texts(b)))
        self.assertNotIn(HEAD, json.dumps(control_body), 'off unless the development option is set')

        with self.db() as con:
            rows = con.execute('SELECT role,content FROM messages WHERE session_id=? ORDER BY id', (session,)).fetchall()
            after = con.execute('SELECT count(*) FROM messages').fetchone()[0]
        self.assertEqual([r for r in rows if r[0] == 'user' and 'Recent messages' in (r[1] or '')], [],
                         'the handoff is not stored as an authored user message')
        self.assertEqual(after - before, 4, 'two turns, a user and an assistant row each; nothing else written')
        pl.evidence('phase1c_pinned_handoff', {
            'requests_control': len(control), 'requests_enabled': len(enabled),
            'handoff_section': fenced[fenced.index(HEAD):].split('\n\n')[0]})


if __name__ == '__main__':
    unittest.main()
