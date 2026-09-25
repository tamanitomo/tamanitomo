"""Phase 1B C3: the keyed client is off unless explicitly enabled (no browser needed).

The page gets the keyed client (the signal meta + /static/chat-sends.js) and the feed gets
row ids only for an app built with chat_sends=Options(client=True). The default build, and
a build with the keyed routes but without the client opt-in, serve the ordinary page and
feed byte-for-byte as before. release-files.json ships none of it, and a shipped copy's page
references no unshipped asset. Synthetic homes only.
"""
import json
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from fastapi.testclient import TestClient      # noqa: E402
import companion_config as cc                  # noqa: E402

from kit.app import chat_send_routes as csr    # noqa: E402
from kit.app.server import build               # noqa: E402
from tests.phase1b_c1 import harness as h      # noqa: E402

SIGNAL = '<meta name="tamanitomo-chat-sends" content="keyed">'


class Builds(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='c3d-')
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.root = self.tmp / 'hermes'
        (self.tmp / 'vault').mkdir()
        self.root.mkdir()
        self.c = cc.Companion(agent='Nova', profile='nova', hermes_root=self.root, vault=self.tmp / 'vault',
                              soul_in_vault=False, context_mode='fixed')
        self.c.home.mkdir(parents=True)
        self.c.save()
        self.n = 0

    def app(self, options):
        self.n += 1
        app = build(self.root, token='t', state_dir=self.tmp / f'state{self.n}', chat_sends=options)
        if options is not None:
            self.addCleanup(app.state.chat_sends.close)
        return TestClient(app)

    def keyed(self, client):
        return csr.Options(executor=lambda rt, home: h.fake_executor(home), client=client)

    def page(self, client):
        return client.get('/').text

    def feed(self, client):
        r = client.get('/api/feed', params={'profile': 'nova'}, headers={'x-companion-token': 't'})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def seed_rows(self):
        # One synthetic exchange through the keyed path, so the feed has rows to compare.
        client = self.app(self.keyed(False))
        boot = client.get('/api/chat/sends/bootstrap', params={'profile': 'nova'},
                          headers={'x-companion-token': 't'}).json()
        from kit.app import chat_sends as cs
        r = client.post('/api/chat/sends', params={'profile': 'nova'}, headers={'x-companion-token': 't'},
                        json={'client_key': cs.new_ulid(), 'generation': boot['generation'],
                              'conversation_id': boot['conversation_id'], 'message': 'Synthetic seed',
                              'session': None})
        self.assertEqual(r.status_code, 202, r.text)
        from tests.test_phase1b_c1_integration import wait_for
        send_id = r.json()['send']['send_id']
        self.assertTrue(wait_for(lambda: client.get(f'/api/chat/sends/{send_id}', params={'profile': 'nova'},
                                                    headers={'x-companion-token': 't'}).json()['settled'], 60))

    def test_default_and_routes_only_builds_serve_the_ordinary_page(self):
        pristine = (ROOT / 'kit/app/static/index.html').read_text(encoding='utf-8')
        for options in (None, self.keyed(False)):
            html = self.page(self.app(options))
            self.assertNotIn(SIGNAL, html)
            self.assertNotIn('chat-sends.js', html)
            # the served page is index.html with only the asset-version stamps added
            self.assertEqual(re.sub(r'\?v=[0-9a-f]{16}', '', html), pristine)

    def test_the_explicit_client_build_adds_only_the_signal_and_the_script(self):
        html = self.page(self.app(self.keyed(True)))
        self.assertIn(SIGNAL, html)
        self.assertRegex(html, r'<script src="/static/chat-sends\.js\?v=[0-9a-f]{16}"></script>\n</html>')
        pristine = (ROOT / 'kit/app/static/index.html').read_text(encoding='utf-8')
        stripped = re.sub(r'\?v=[0-9a-f]{16}', '', html).replace(SIGNAL + '\n', '', 1)
        stripped = stripped.replace('<script src="/static/chat-sends.js"></script>\n', '', 1)
        self.assertEqual(stripped, pristine)

    @unittest.skipUnless(h.LINUX, 'the seed turn uses the C1 supervision (Linux)')
    def test_feed_rows_carry_ids_only_for_the_client_build(self):
        self.seed_rows()
        default = self.feed(self.app(None))['messages']
        routes_only = self.feed(self.app(self.keyed(False)))['messages']
        client = self.feed(self.app(self.keyed(True)))['messages']
        self.assertTrue(default)
        self.assertEqual(default, routes_only)
        self.assertFalse(any('source_message' in m for m in default))
        self.assertEqual([{k: v for k, v in m.items() if k != 'source_message'} for m in client], default)
        self.assertTrue(all(isinstance(m['source_message'], str) for m in client))

    def test_nothing_new_is_shipped_and_no_entry_point_enables_the_client(self):
        shipped = json.loads((ROOT / 'release-files.json').read_text())
        self.assertNotIn('kit/app/static/chat-sends.js', shipped)
        self.assertIn('kit/app/static/index.html', shipped)
        self.assertNotIn('chat-sends.js', (ROOT / 'kit/app/static/index.html').read_text(encoding='utf-8'))
        callers = [p for p in list(ROOT.glob('*.py')) + list((ROOT / 'kit').rglob('*.py'))
                   if 'client=True' in p.read_text(encoding='utf-8')]
        self.assertEqual(callers, [])

    def test_the_client_file_is_inert_without_the_signal(self):
        src = (ROOT / 'kit/app/static/chat-sends.js').read_text(encoding='utf-8')
        head = src[:src.index("const CROCKFORD")]
        self.assertIn("if(!signal||signal.content!=='keyed')return;", head)
        self.assertNotIn("'/chat'", src.replace("'/chat/", ''), 'the keyed client has no path to POST /api/chat')


if __name__ == '__main__':
    unittest.main()
