"""Trusted Chat integration over HTTP: the enabled client's reads and continuation choice.

BOUNDARY: HTTP routes (TestClient) -> the Phase 1A read routes and the keyed-send routes
(chat_send_routes, incl. the read-only GET /api/chat/continuation) -> SendService -> the fake
Hermes protocol double -> a synthetic Hermes-schema state.db. The app is built with an
explicit chat_sends=Options(...); no shipped entry point does. Synthetic data only.

The mixed fixture is the one the persistent Chat preview seeds: the owner on the workspace,
a terminal and Telegram; a stranger, a group, a cron run and a `cli`-labelled gateway chat
(`gw-cli`, the newest session) that must never be read as conversation or continued.
"""
import hashlib
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts'), str(ROOT / 'tests')]

from chat_fixtures import OWNER_TELEGRAM, HermesStore, standard_sessions   # noqa: E402
from kit.app import chat_sources as csrc                                   # noqa: E402
from kit.app import runtime as hr                                          # noqa: E402
from kit.app import send_protocol as sp                                    # noqa: E402
from tests.phase1b_c1.harness import LINUX                                 # noqa: E402
from tests.test_phase1b_c1_integration import App                          # noqa: E402

MARKERS = ('must not appear',)
T = 1_757_000_000.0


def seed_mixed(c):
    """tools/preview_fixture.seed_conversation, without its date: every trusted source, every
    excluded kind, three equal-text owner messages, and gw-cli as the newest session."""
    store = HermesStore(c.home)
    standard_sessions(store)
    hr.note_workspace_session(c, 'web')
    (c.home / csrc.BINDING_FILE).write_text(json.dumps({'telegram': [OWNER_TELEGRAM]}))
    store.say('tg', 'user', 'Morning! On the train again.', T + 60, platform_message_id='101')
    store.say('tg', 'assistant', 'Safe travels. Did you bring the book?', T + 90)
    store.say('web', 'user', 'Back at my desk now.', T + 3600)
    store.say('web', 'assistant', 'Welcome back. Tea first?', T + 3620)
    store.say('term', 'user', 'quick question from the terminal', T + 7200)
    store.say('stranger', 'user', 'a stranger writes (must not appear)', T + 7300)
    store.say('group', 'user', 'group chatter (must not appear)', T + 7400)
    store.say('job', 'assistant', 'nightly cron output (must not appear)', T + 7500)
    for _ in range(3):
        store.say('tg', 'user', 'hi', T + 8000)
    return store


def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


class Mixed(unittest.TestCase):

    def setUp(self):
        self.a = App(self)
        self.c = self.a.companions['nova']
        self.store = seed_mixed(self.c)

    def continuation(self, session=None, profile='nova'):
        r = self.a.get('/chat/continuation', profile, **({'session': session} if session else {}))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    # ----- the boundary as found (unchanged legacy compatibility) -----

    def test_legacy_feed_still_chooses_gw_cli_and_keyed_acceptance_refuses_it(self):
        feed = self.a.get('/feed').json()
        self.assertEqual(feed['session'], 'gw-cli')
        self.assertTrue(any('must not appear' in m['content'] for m in feed['messages']),
                        'the legacy feed is unchanged: it still reads groups and strangers')
        refused = self.a.post('/chat/sends', self.a.body(session='gw-cli'))
        self.assertEqual((refused.status_code, refused.json()['error']), (400, 'unauthorised_session'))

    # ----- 1. mixed-history reads -----

    def test_trusted_reads_newest_and_older_pages_exclude_untrusted_rows_and_write_nothing(self):
        before = digest(self.c.home / 'state.db')
        page = self.a.snapshot(limit=3)
        seen = list(page['messages'])
        cursor = page['history']['before']
        pages = 1
        while cursor:
            r = self.a.get('/chat/history', before=cursor, limit=3)
            self.assertEqual(r.status_code, 200, r.text)
            seen = r.json()['messages'] + seen
            cursor = r.json()['history']['before']
            pages += 1
        self.assertGreaterEqual(pages, 3, 'several bounded pages')
        texts = [m['content'] for m in seen]
        self.assertFalse([t for t in texts if 'must not appear' in t], 'stranger, group and cron rows stay out')
        self.assertEqual({m['source']['kind'] for m in seen}, {'workspace', 'terminal', 'telegram'})
        self.assertNotIn('gw-cli', {m['source']['session'] for m in seen})
        his = [m for m in seen if m['content'] == 'hi']
        self.assertEqual(len(his), 3)
        self.assertEqual(len({m['message_id'] for m in his}), 3, 'equal text, three distinct messages')
        self.assertEqual(len({m['message_id'] for m in seen}), len(seen))
        self.assertEqual(digest(self.c.home / 'state.db'), before, 'reading never writes the source')
        self.assertEqual(self.a.snapshot(limit=3)['messages'], page['messages'], 'stable ids across reads')

    def test_an_invalidated_cursor_answers_resync_not_an_empty_page(self):
        cursor = self.a.snapshot(limit=2)['history']['before']
        (self.c.home / csrc.BINDING_FILE).write_text(json.dumps({'telegram': []}))   # binding change
        self.a.snapshot(limit=2)                                                     # the rebuild
        r = self.a.get('/chat/history', before=cursor, limit=2)
        self.assertEqual((r.status_code, r.json()['error']), (409, 'resync_required'))

    # ----- 2. continuation without the favourable seed -----

    def test_continuation_refuses_the_gateway_cli_session_and_suggests_the_most_recent_eligible(self):
        out = self.continuation('gw-cli')
        self.assertEqual(out['current'], {'session': 'gw-cli', 'eligible': False})
        self.assertEqual(out['suggestion']['session'], 'term')        # newest activity among eligible
        self.assertEqual(out['suggestion']['kind'], 'terminal')
        self.assertEqual(out['policy'], 'saved_then_most_recent_local')
        self.assertEqual(out['conversation_id'], self.a.snapshot()['conversation_id'])

    def test_the_suggested_session_sends_once_through_keyed_acceptance(self):
        session = self.continuation()['suggestion']['session']
        _, accepted, final = self.a.send('Continue from here', session=session)
        self.assertEqual((final['state'], final['session']), ('complete', session))
        self.assertEqual(self.a.launches(accepted['send']['send_id']), 1)
        now = self.continuation(session)
        self.assertEqual(now['current'], {'session': session, 'eligible': True, 'kind': 'terminal'})

    def test_excluded_sessions_are_never_eligible_even_when_newest(self):
        # Give every excluded kind a later activity than any eligible session.
        for i, sid in enumerate(('gw-cli', 'job', 'sub', 'stranger', 'group', 'dc')):
            self.store.say(sid, 'user', 'later', T + 20000 + i)
        excluded = ('gw-cli', 'job', 'sub', 'stranger', 'group', 'dc', 'tg', 'tg-old', 'rowan-tg', 'no-such')
        for sid in excluded:
            out = self.continuation(sid)
            self.assertEqual(out['current'], {'session': sid, 'eligible': False}, sid)
            self.assertEqual(out['suggestion']['session'], 'term', sid)

    def test_continuation_is_read_only(self):
        before = digest(self.c.home / 'state.db')
        self.continuation('gw-cli')
        self.continuation()
        self.assertFalse(sp.ledger_dir(self.c.home).exists(), 'no ledger is created')
        self.assertEqual(digest(self.c.home / 'state.db'), before, 'no source write')
        self.assertFalse(self.a.app.state.operations.busy, 'no turn is launched')

    def test_workspace_trust_withdrawn_makes_the_saved_workspace_session_ineligible(self):
        self.assertEqual(self.continuation('web')['current'], {'session': 'web', 'eligible': True, 'kind': 'workspace'})
        (self.c.home / csrc.BINDING_FILE).write_text(json.dumps({'workspace': False, 'telegram': [OWNER_TELEGRAM]}))
        self.assertEqual(self.continuation('web')['current'], {'session': 'web', 'eligible': False})

    def test_authorisation_changing_after_the_suggestion_is_refused_at_acceptance(self):
        session = self.continuation()['suggestion']['session']
        body = self.a.body('Raced', session=session)
        (self.c.home / csrc.BINDING_FILE).write_text(json.dumps({'terminal': False, 'telegram': [OWNER_TELEGRAM]}))
        refused = self.a.post('/chat/sends', body)
        self.assertEqual((refused.status_code, refused.json()['error']), (400, 'unauthorised_session'))
        con = sp.connect(self.a.ledger(), readonly=True)
        try:
            self.assertEqual(con.execute('SELECT count(*) FROM sends').fetchone()[0], 0)
        finally:
            con.close()
        self.assertEqual(self.continuation(session)['current'], {'session': session, 'eligible': False})

    def test_an_unreadable_store_is_unavailable_not_empty(self):
        (self.c.home / 'state.db').write_bytes(b'not a database')
        r = self.a.get('/chat/continuation', session='term')
        self.assertEqual((r.status_code, r.json()['error']), (503, 'source_unavailable'))

    def test_another_profiles_sessions_are_not_suggested(self):
        out = self.continuation(profile='rowan')
        self.assertIsNone(out['suggestion'])       # rowan's only session is a Telegram DM
        self.assertEqual(self.continuation('term', profile='rowan')['current'], {'session': 'term', 'eligible': False})


@unittest.skipUnless(LINUX, 'the C1 supervision is established on Linux only')
class NewProfile(unittest.TestCase):

    def setUp(self):
        self.a = App(self)

    def test_a_new_profile_starts_a_session_and_then_continues_it(self):
        r = self.a.get('/chat/continuation', 'rowan')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()['current'], r.json()['suggestion']), (None, None))
        _, accepted, final = self.a.send('Hello, first time', profile='rowan', session=None)
        self.assertEqual(final['state'], 'complete')
        self.assertEqual(self.a.launches(accepted['send']['send_id'], 'rowan'), 1)
        created = final['session']
        out = self.a.get('/chat/continuation', 'rowan', session=created).json()
        self.assertEqual(out['current'], {'session': created, 'eligible': True, 'kind': 'workspace'})
        self.assertEqual(out['suggestion']['session'], created)


class Disabled(unittest.TestCase):

    def test_the_continuation_route_exists_only_with_keyed_sends(self):
        a = App(self, enable=False)
        self.assertEqual(a.get('/chat/continuation').status_code, 404)


if __name__ == '__main__':
    unittest.main()
