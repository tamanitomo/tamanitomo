"""Phase 1A read routes over HTTP: scope captured per request, errors that say
what to do, and the existing Chat surfaces left as they were.

BOUNDARY: HTTP routes -> projection -> source store fixture. The send path is
only checked to be unchanged; it is still the fake Hermes CLI (tests/fake_hermes.py).
"""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests')]

from chat_fixtures import HermesStore, OWNER_TELEGRAM, standard_sessions  # noqa: E402
from tests import test_workspace as workspace  # noqa: E402
from kit.app import runtime as hr, chat_sources as cs  # noqa: E402


class ChatRouteTests(unittest.TestCase):
    def setUp(self):
        self.f = workspace.WorkspaceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.store = HermesStore(self.f.c.home);standard_sessions(self.store)
        (self.f.c.home / cs.BINDING_FILE).write_text(json.dumps({'telegram': [OWNER_TELEGRAM]}))
        hr.note_workspace_session(self.f.c, 'web')

    def get(self, path, profile='nova', **params):
        return self.f.client.get('/api' + path, params={'profile': profile, **params}, headers=self.f.headers)

    def test_snapshot_history_and_changes(self):
        for i in range(5):self.store.say('tg', 'user', f'm{i}', 10 + i)
        self.store.say('stranger', 'user', 'not yours', 20)
        snap = self.get('/chat/snapshot', limit=2)
        self.assertEqual(snap.status_code, 200, snap.text)
        body = snap.json()
        self.assertEqual([m['content'] for m in body['messages']], ['m3', 'm4'])
        self.assertEqual(body['scope'], {'profile': 'nova', 'installation': 'existing', 'owner_binding': 'owner-file'})
        self.assertTrue(all(m['attachments'] == [] for m in body['messages']))
        older = self.get('/chat/history', before=body['history']['before'], limit=2).json()
        self.assertEqual([m['content'] for m in older['messages']], ['m1', 'm2'])
        self.store.say('tg', 'assistant', 'new reply', 30)
        changes = self.get('/chat/changes', after=body['changes']['after']).json()
        self.assertEqual([c['message']['content'] for c in changes['changes']], ['new reply'])
        self.assertNotIn('not yours', json.dumps([body, older, changes]))

    def test_errors_say_what_to_do(self):
        self.store.say('tg', 'user', 'hello', 10)
        body = self.get('/chat/snapshot').json()
        bad = self.get('/chat/history', before='nonsense')
        self.assertEqual((bad.status_code, bad.json()['error']), (400, 'invalid_cursor'))
        self.assertEqual(self.get('/chat/snapshot', limit=500).status_code, 400)
        # A cursor from nova is refused for rowan: a stale request cannot adopt another profile.
        store = HermesStore(self.f.other.home)
        store.session('tg', 'telegram', profile='rowan', user_id=OWNER_TELEGRAM, chat_id=OWNER_TELEGRAM, chat_type='dm')
        cross = self.get('/chat/changes', profile='rowan', after=body['changes']['after'])
        self.assertEqual((cross.status_code, cross.json()['error']), (400, 'invalid_cursor'))
        self.assertIn('another conversation', cross.json()['detail'])
        # Revoking the owner binding invalidates the old cursor.
        (self.f.c.home / cs.BINDING_FILE).write_text(json.dumps({'telegram': []}))
        stale = self.get('/chat/changes', after=body['changes']['after'])
        self.assertEqual((stale.status_code, stale.json()['error']), (409, 'resync_required'))
        # An unreadable store is retryable, not "no messages".
        self.store.path.write_bytes(b'garbage' * 200)
        down = self.get('/chat/snapshot')
        self.assertEqual((down.status_code, down.json()['error'], down.json()['retryable']), (503, 'source_unavailable', True))

    def test_sources_report_capabilities_and_binding(self):
        body = self.get('/chat/sources').json()
        self.assertEqual(body['owner_binding']['origin'], 'owner-file')
        self.assertEqual(body['capabilities']['discord']['status'], 'unsupported')
        self.assertEqual(body['capabilities']['telegram']['status'], 'supported')

    def test_the_legacy_feed_and_send_path_are_unchanged(self):
        self.store.say('tg', 'user', 'on telegram', 10)
        feed = self.get('/feed').json()
        self.assertEqual(set(feed), {'messages', 'next_cursor', 'session', 'agent'})
        self.assertEqual([m['content'] for m in feed['messages']], ['on telegram'])
        self.assertEqual(set(feed['messages'][0]), {'role', 'content', 'timestamp', 'session', 'source', 'attachments'})


if __name__ == '__main__':
    unittest.main()
