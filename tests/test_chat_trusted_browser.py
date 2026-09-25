"""Trusted Chat integration in a real browser: trusted reads and an eligible continuation.

BOUNDARY: headless Chromium (Playwright) -> the actual page with the keyed client and the
persistent Chat store/view/controller -> a real uvicorn server built with
chat_sends=Options(client=True) (tests/phase1b_c3/fixture.py) -> the Phase 1A read routes,
GET /api/chat/continuation and keyed acceptance -> SendService -> the fake Hermes protocol
double -> a synthetic state.db. Launch counts are read from the ledger the server wrote.

The mixed fixture is the unmodified one whose legacy latest_session is the gateway `gw-cli`
(tests/test_chat_trusted_integration.seed_mixed); there is no favourable newest workspace
session. Synthetic data only; no model, platform, credential, live profile or dispatcher.

TAMANITOMO_C3_REQUIRE_BROWSER=1 makes a missing browser a failure, never a skip.
"""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts'), str(ROOT / 'tests')]

from chat_fixtures import OWNER_TELEGRAM                                     # noqa: E402
from kit.app import chat_sources as csrc                                     # noqa: E402
from tests.phase1b_c1.harness import LINUX                                   # noqa: E402
from tests.test_chat_trusted_integration import T, digest, seed_mixed        # noqa: E402
import tests.test_persistent_chat_browser as accepted                         # noqa: E402
from tests.test_phase1b_c3_browser import WORDS, pause, until                # noqa: E402

TRUSTED = ('Morning! On the train again.', 'Back at my desk now.', 'Welcome back. Tea first?',
           'quick question from the terminal', 'Safe travels. Did you bring the book?')
CHOICE = 'The conversation this tab was continuing can no longer be continued from here.'
INELIGIBLE = ('Not sent. The conversation this tab was continuing can no longer be continued from here. '
              'Choose how to continue; your draft is kept.')
NEW_SESSION = 'Your first message starts a new session.'


class Trusted(accepted.Persistent):

    def seed(self, older=0):
        store = seed_mixed(self.s.companions['nova'])
        for i in range(older):                    # older trusted terminal history, for paging
            store.say('term', 'user' if i % 2 == 0 else 'assistant', f'Earlier line {i:03d}', T - 100000 + i * 60)
        return store

    def log(self):
        return self.page.inner_text('#chat-log')

    def hint(self):
        return self.page.inner_text('#chat-status')

    def draft(self, profile='nova'):
        return self.storage(f'chat-draft-existing-{profile}')

    def selection(self, profile='nova'):
        raw = self.storage(f'chat-continuation-existing-{profile}')
        return json.loads(raw) if raw else None

    def one_send_ledger(self, text):       # as accepted.Journeys
        sends = self.s.sends()
        self.assertEqual(len(sends), 1, sends)
        self.assertEqual(self.s.owner_rows().count(text), 1)
        self.assertEqual(len({p['client_key'] for p in self.keyed_posts()}), 1)
        return sends[0]

    def assert_no_feed(self):
        self.assertEqual(self.calls('GET', '/api/feed'), [], 'the enabled client reads the trusted contract only')


@unittest.skipUnless(LINUX, 'the C1 supervision is established on Linux only')
class MixedHistory(Trusted):

    # 1. mixed-history reads -----------------------------------------------------------

    def test_1_trusted_rows_on_page_and_dock_through_newest_and_older_pages(self):
        self.page.set_viewport_size({'width': 1280, 'height': 800})
        self.seed(older=70)
        db = self.s.home() / 'state.db'
        before = digest(db)
        self.open()
        text = self.log()
        for t in TRUSTED:
            self.assertIn(t, text)
        self.assertNotIn('must not appear', text)
        self.assertEqual(self.bubbles('hi'), 3, 'three equal-text messages stay three')
        keys = self.page.evaluate("[...document.querySelectorAll('#chat-log .bubble[data-item]')].map(b=>b.dataset.item)")
        self.assertTrue(keys and all(k.startswith('m:msg_') for k in keys), keys[:3])
        self.assertEqual(len(keys), len(set(keys)))
        self.assertNotIn('Earlier line 000', text, 'only the newest page first')
        # Older pages, through the trusted history route.
        self.page.evaluate("()=>{document.getElementById('chat-log').scrollTop=0}")
        until(lambda: 'Earlier line 000' in self.log(), what='the oldest page')
        until(lambda: 'The beginning of the conversation.' in self.log(), what='start reached')
        self.assertNotIn('must not appear', self.log())
        self.assertTrue(self.calls('GET', '/api/chat/history'), 'older pages came from /api/chat/history')
        # The dock renders the same store.
        self.open_note()
        until(self.dock_visible, what='launcher')
        self.page.click('#chat-dock-launcher')
        until(lambda: 'quick question from the terminal' in self.dock_text(), what='dock history')
        self.assertNotIn('must not appear', self.dock_text())
        self.assertEqual(self.dock_bubbles('hi'), 3)
        self.assert_no_feed()
        self.assertEqual(digest(db), before, 'reading wrote nothing to the source')
        self.assertEqual(self.s.sends(), [], 'reading sent nothing')

    # 2. continuation without the favourable seed --------------------------------------

    def test_2_the_gw_cli_fixture_sends_through_the_eligible_session(self):
        self.seed()
        self.s.scenario(reply='Continuing from the terminal.')
        self.open()
        until(lambda: (self.selection() or {}).get('session') == 'term', what='the eligible suggestion saved')
        self.type_and_send('Continue please')
        self.wait_reply('Continuing from the terminal.')
        send = self.one_send_ledger('Continue please')
        self.assertEqual(self.s.launches(send['send_id']), 1)
        self.assertEqual([p['session'] for p in self.keyed_posts()], ['term'])
        self.assertEqual(self.bubbles('Continue please'), 1)
        self.assertNotIn(WORDS['not_sent'], self.log())
        self.assert_never_legacy()
        self.assert_no_feed()

    def test_2_an_ineligible_saved_session_keeps_the_draft_and_offers_a_new_session(self):
        self.seed()
        self.s.scenario(reply='A fresh start.')
        self.open()
        self.page.evaluate("()=>sessionStorage.setItem('chat-continuation-existing-nova',"
                           "JSON.stringify({session:'gw-cli',fresh:false}))")
        self.page.reload()
        self.page.wait_for_selector('.chat-session-choice')
        self.assertIn(CHOICE, self.log())
        self.type_and_send('Keep this draft')
        until(lambda: self.hint() == INELIGIBLE, what='the truthful refusal')
        self.assertEqual(self.page.input_value('#chat-message'), 'Keep this draft')
        self.assertEqual(self.draft(), 'Keep this draft')
        self.assertEqual(self.keyed_posts(), [], 'nothing is posted for an ineligible session')
        self.assertIsNone(self.pending(), 'no intent was created')
        self.assertEqual(self.selection()['session'], 'gw-cli', 'no silent switch')
        # The owner's explicit choice: a new session.
        self.page.click('[data-session-action="new"]')
        until(lambda: self.hint() == 'Your next message starts a new session.', what='the choice acknowledged')
        self.assertFalse(self.page.query_selector('.chat-session-choice'))
        self.page.press('#chat-message', 'Enter')
        self.wait_reply('A fresh start.')
        send = self.one_send_ledger('Keep this draft')
        self.assertEqual(self.s.launches(send['send_id']), 1)
        self.assertEqual([p['session'] for p in self.keyed_posts()], [None])
        created = self.s.settled(send['send_id'])['session']
        self.assertNotIn(created, ('gw-cli', 'term', 'web'))
        until(lambda: self.selection() == {'session': created, 'fresh': False}, what='the new session is current')

    def test_2_the_owner_may_choose_the_most_recent_eligible_session_instead(self):
        self.seed()
        self.s.scenario(reply='Back in the terminal thread.')
        self.page.goto(self.s.url('nova', 'vault'))
        self.page.evaluate("()=>sessionStorage.setItem('chat-continuation-existing-nova',"
                           "JSON.stringify({session:'gw-cli',fresh:false}))")
        self.open()
        self.page.wait_for_selector('[data-session-action="suggested"]')
        self.page.click('[data-session-action="suggested"]')
        self.type_and_send('Pick up the terminal thread')
        self.wait_reply('Back in the terminal thread.')
        self.assertEqual([p['session'] for p in self.keyed_posts()], ['term'])
        self.one_send_ledger('Pick up the terminal thread')

    def test_2_authorisation_withdrawn_between_check_and_post_is_an_honest_refusal(self):
        self.seed()
        self.open()
        until(lambda: (self.selection() or {}).get('session') == 'term', what='suggestion saved')
        home = self.s.home()

        def race(route):
            response = route.fetch()                   # the real, still-eligible answer...
            (home / csrc.BINDING_FILE).write_text(json.dumps({'terminal': False, 'telegram': [OWNER_TELEGRAM]}))
            route.fulfill(response=response)           # ...then trust is withdrawn before the POST
        self.page.route('**/api/chat/continuation*', race)
        self.type_and_send('Raced message')
        until(lambda: WORDS['not_sent'] in self.hint(), what='Not sent')
        self.assertIn('can no longer be continued from here', self.hint())
        self.assertEqual(self.page.input_value('#chat-message'), 'Raced message', 'the message is back in the box')
        self.assertEqual([p['session'] for p in self.keyed_posts()], ['term'], 'one POST, never retried elsewhere')
        self.assertEqual(self.s.sends(), [], 'nothing accepted')
        self.assertIsNone(self.pending())
        self.page.wait_for_selector('.chat-session-choice')
        self.assertEqual(self.selection()['session'], 'term', 'no silent switch')
        self.assert_never_legacy()

    def test_2_a_new_profile_says_so_and_begins_then_continues_its_session(self):
        self.s.scenario('rowan', reply='Nice to meet you.')
        self.open('rowan')
        until(lambda: self.hint() == NEW_SESSION, what='the new-session state is stated')
        self.type_and_send('Hello Rowan')
        until(lambda: self.bubbles('Nice to meet you.', owner=False) == 1, what='first reply')
        sends = self.s.sends('rowan')
        created = self.s.settled(sends[0]['send_id'], 'rowan')['session']
        until(lambda: (self.selection('rowan') or {}).get('session') == created, what='created session current')
        self.s.scenario('rowan', reply='Still here.')
        self.type_and_send('Second message')
        until(lambda: self.bubbles('Still here.', owner=False) == 1, what='second reply')
        self.assertEqual([p['session'] for p in self.keyed_posts()], [None, created])
        self.assertEqual([self.s.launches(s['send_id'], 'rowan') for s in self.s.sends('rowan')], [1, 1])

    # 4. recovery and isolation --------------------------------------------------------

    def test_4_one_profiles_selection_is_never_used_for_another(self):
        self.seed()
        self.open()
        until(lambda: (self.selection() or {}).get('session') == 'term', what='nova selection')
        self.s.scenario('rowan', reply='Rowan here.')
        self.page.goto(self.s.url('rowan', 'chat'))
        self.page.wait_for_selector('#chat-message')
        self.type_and_send('For rowan only')
        until(lambda: self.bubbles('Rowan here.', owner=False) == 1, what='rowan reply')
        self.assertEqual([p['session'] for p in self.keyed_posts()], [None])
        self.assertEqual(self.s.sends('nova'), [])
        self.assertNotIn('quick question from the terminal', self.log(), 'nova rows are not on rowan')

    def test_4_a_read_failure_keeps_rows_draft_and_the_pending_send(self):
        self.seed()
        self.s.gated(['Still ', 'answering.'])
        self.open()
        self.type_and_send('Mid-turn')
        until(lambda: self.s.reached(1), what='reply paused')
        key = self.pending()['client_key']
        self.page.fill('#chat-message', 'A newer draft')
        self.page.route('**/api/chat/snapshot*', lambda r: r.fulfill(
            status=503, content_type='application/json', body='{"error":"source_unavailable","retryable":true}'))
        self.page.evaluate('PersistentChat.loadNewest(ChatStore.now())')
        until(lambda: 'What is shown was read earlier.' in self.log(), what='the read is stated unavailable')
        self.assertIn('quick question from the terminal', self.log(), 'rows stay; never an empty conversation')
        self.assertNotIn('The beginning', self.page.inner_text('#chat-log .chat-welcome') if
                         self.page.query_selector('#chat-log .chat-welcome') else '')
        self.assertEqual(self.pending()['client_key'], key)
        self.assertEqual(self.page.input_value('#chat-message'), 'A newer draft')
        self.page.unroute('**/api/chat/snapshot*')
        self.s.release(1)
        self.wait_reply('Still answering.')
        self.assertEqual(self.draft(), 'A newer draft')
        send = self.one_send_ledger('Mid-turn')
        self.assertEqual(self.s.launches(send['send_id']), 1)

    def test_4_an_invalidated_cursor_resyncs_with_one_fresh_snapshot_and_keeps_state(self):
        self.page.set_viewport_size({'width': 1280, 'height': 800})
        self.seed(older=70)
        self.s.gated(['Resync ', 'done.'])
        self.open()
        self.type_and_send('During a resync')
        until(lambda: self.s.reached(1), what='reply paused')
        key = self.pending()['client_key']
        self.page.fill('#chat-message', 'Draft during resync')
        snapshots = len(self.calls('GET', '/api/chat/snapshot'))
        self.page.route('**/api/chat/history*', lambda r: r.fulfill(
            status=409, content_type='application/json', body='{"error":"resync_required","reason":"projection_rebuilt"}'))
        self.page.evaluate('PersistentChat.loadOlder(ChatStore.now())')
        until(lambda: len(self.calls('GET', '/api/chat/snapshot')) == snapshots + 1, what='one fresh snapshot')
        pause(0.5)
        self.assertEqual(len(self.calls('GET', '/api/chat/snapshot')), snapshots + 1, 'bounded: exactly one')
        self.assertEqual(len(self.calls('GET', '/api/chat/history')), 1)
        self.assertNotIn('must not appear', self.log())
        self.assertIn('quick question from the terminal', self.log())
        self.assertEqual(self.pending()['client_key'], key)
        self.assertEqual(self.page.input_value('#chat-message'), 'Draft during resync')
        self.page.unroute('**/api/chat/history*')
        self.s.release(1)
        self.wait_reply('Resync done.')
        self.assertEqual(self.bubbles('During a resync'), 1, 'one presentation')
        send = self.one_send_ledger('During a resync')
        self.assertEqual(self.s.launches(send['send_id']), 1)


@unittest.skipUnless(LINUX, 'the C1 supervision is established on Linux only')
class MixedJourneys(accepted.Journeys):
    """3. The accepted journeys (page, Vault, dock, reply, maximise; views, reload, profile
    switch, recovery) rerun unchanged on the mixed gw-cli fixture instead of an empty profile."""

    def setUp(self):
        super().setUp()
        seed_mixed(self.s.companions['nova'])


if __name__ == '__main__':
    unittest.main()
