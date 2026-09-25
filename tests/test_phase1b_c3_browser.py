"""Phase 1B C3: the keyed-send client in a real browser (PHASE1B_DESIGN.md section 6, M-22).

BOUNDARY: headless Chromium (Playwright) -> the actual page (index.html + workspace.js +
chat-sends.js) -> a real uvicorn server built with chat_sends=Options(client=True) ->
chat_send_routes -> SendService -> executor -> the fake Hermes protocol double -> a
synthetic state.db. Execution and idempotency are asserted on the ledger the server wrote,
not on a frontend mock. Transport failures are injected with Playwright routing only.
Synthetic data only; no model, platform, credential or live profile.

Skipped (as an explicitly incomplete browser gate) when Playwright or its Chromium is not
installed, unless TAMANITOMO_C3_REQUIRE_BROWSER=1, which makes that a failure.
"""
import json
import os
import pathlib
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from tests.phase1b_c1.harness import LINUX                  # noqa: E402

REQUIRE = os.environ.get('TAMANITOMO_C3_REQUIRE_BROWSER') == '1'
try:
    from playwright.sync_api import sync_playwright         # noqa: E402
    import uvicorn                                           # noqa: E402,F401
    MISSING = None
except ImportError as exc:                                   # pragma: no cover - environment
    MISSING = f'browser gate not run: {exc}'

WORDS = {
    'not_sent': 'Not sent',
    'failed_recorded': 'Your message was recorded; the reply failed',
    'unknown': 'The app accepted your request. Whether Hermes recorded it or finished a reply is unknown.',
    'reset': 'The app’s send records were reset. Whether this message was sent before the reset is unknown.',
    'signed_out': 'Your sign-in ended. Sign in again, and the app will check this message with the same request.',
    'duplicate': 'This may send your message twice.',
    'storage': 'Not sent: this browser could not keep a safe record of the message. Your draft is kept.',
}


PAGE = []      # the current test's page: waiting must pump Playwright (routes, events)


def pause(seconds):
    PAGE[0].wait_for_timeout(seconds * 1000) if PAGE else time.sleep(seconds)


def until(pred, timeout=30.0, interval=0.05, what='condition'):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = pred()
        if value:
            return value
        pause(interval)
    raise AssertionError(f'timed out waiting for {what}')


class Browser(unittest.TestCase):
    """One Chromium per class; a fresh server, context (fresh sessionStorage) and page per test."""

    @classmethod
    def setUpClass(cls):
        if MISSING:
            if REQUIRE:
                raise AssertionError(MISSING)
            raise unittest.SkipTest(MISSING)
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except Exception as exc:                             # pragma: no cover - environment
            cls.pw.stop()
            if REQUIRE:
                raise
            raise unittest.SkipTest(f'browser gate not run: Chromium unavailable ({exc})')
        cls.version = cls.browser.version

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    client = True
    keyed = True

    def setUp(self):
        from tests.phase1b_c3.fixture import Server
        self.s = Server(client=self.client, keyed=self.keyed)
        self.addCleanup(self.s.close)
        self.ctx = self.browser.new_context()
        self.addCleanup(self.ctx.close)
        self.page = self.ctx.new_page()
        PAGE[:] = [self.page]
        self.addCleanup(PAGE.clear)
        self.errors, self.requests = [], []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.page.on('request', lambda r: self.requests.append((r.method, r.url, r.post_data)))

    def tearDown(self):
        self.assertEqual([e for e in self.errors if 'Failed to fetch' not in e], [])

    # ----- helpers -----

    def open(self, profile='nova', tab='chat'):
        self.page.goto(self.s.url(profile, tab))
        if tab == 'chat':
            self.page.wait_for_selector('#chat-message', timeout=20000)
            self.page.wait_for_function("!document.querySelector('.chat-loading')", timeout=20000)

    def type_and_send(self, text):
        self.page.fill('#chat-message', text)
        self.page.press('#chat-message', 'Enter')

    def bubbles(self, text, owner=True):
        # a reply is a presented reply row, not the live stream snapshot (id "<send>:stream")
        sel = '#chat-log .bubble.user' if owner else '#chat-log .bubble:not(.user):not(.typing):not([id$=":stream"])'
        return self.page.evaluate('([sel,text])=>[...document.querySelectorAll(sel)].filter(b=>'
                                  "(b.querySelector('.message-body')?.innerText||'').trim()===text).length",
                                  [sel, text])

    def status_of(self, text):
        return self.page.evaluate("text=>{const b=[...document.querySelectorAll('#chat-log .bubble.user')]"
                                  ".find(b=>(b.querySelector('.message-body')?.innerText||'').trim()===text);"
                                  "return b?(b.querySelector('.bubble-status')?.innerText||''):null}", text)

    def wait_status(self, text, expected, timeout=30):
        return until(lambda: (self.status_of(text) or '').strip() == expected, timeout,
                     what=f'status {expected!r} (now {self.status_of(text)!r})')

    def wait_reply(self, text, timeout=30):
        until(lambda: self.bubbles(text, owner=False) >= 1, timeout, what=f'reply {text!r}')

    def storage(self, key):
        return self.page.evaluate('k=>sessionStorage.getItem(k)', key)

    def pending(self, profile='nova'):
        raw = self.storage(f'chat-pending-existing-{profile}')
        return json.loads(raw) if raw else None

    def calls(self, method, path):
        return [r for r in self.requests if r[0] == method and r[1].split('?')[0].endswith(path)]

    def keyed_posts(self):
        return [json.loads(r[2]) for r in self.calls('POST', '/api/chat/sends')]

    def assert_never_legacy(self):
        self.assertEqual(self.calls('POST', '/api/chat'), [], 'the keyed client must never use POST /api/chat')

    def one_send(self, text, reply):
        """The ledger holds one send for this text, launched once, one owner row in Hermes,
        and the page presents one owner and one reply bubble."""
        sends = self.s.sends()
        self.assertEqual(len(sends), 1, sends)
        self.assertEqual(self.s.launches(sends[0]['send_id']), 1)
        self.assertEqual(self.s.owner_rows().count(text), 1)
        until(lambda: self.bubbles(text) == 1 and self.bubbles(reply, owner=False) == 1, 10,
              what='one owner and one reply bubble')
        self.assertEqual(len({p['client_key'] for p in self.keyed_posts()}), 1, 'every POST used the same key')
        return sends[0]


@unittest.skipUnless(LINUX, 'the C1 supervision is established on Linux only')
class KeyedSends(Browser):

    def test_submit_and_double_submit_launch_once(self):
        self.s.scenario(reply='Hello <b>there</b>, one reply.')
        self.open()
        self.page.fill('#chat-message', 'A synthetic owner message')
        self.page.evaluate("()=>{const f=document.getElementById('chat-form');f.requestSubmit();f.requestSubmit();}")
        self.page.press('#chat-message', 'Enter')
        self.page.click('#send-message', force=True)
        self.wait_reply('Hello <b>there</b>, one reply.')
        send = self.one_send('A synthetic owner message', 'Hello <b>there</b>, one reply.')
        self.assertEqual(len(self.keyed_posts()), 1)
        self.assertEqual(self.page.eval_on_selector_all('#chat-log b', 'els=>els.length'), 0, 'reply HTML escaped')
        self.assertIsNotNone(self.page.query_selector(f'[id="{send["send_id"]}:owner"]'))
        self.assertIsNotNone(self.page.query_selector(f'[id="{send["send_id"]}:reply:0"]'))
        until(lambda: self.pending() is None, 5, what='pending cleared')
        self.assertEqual(self.page.input_value('#chat-message'), '')
        self.assert_never_legacy()

    def test_lost_response_is_recovered_by_the_same_key(self):
        self.s.scenario(reply='Recovered reply.')
        self.open()
        seen = []

        def lose_response(route):
            seen.append(route.request.post_data)
            if len(seen) == 1:
                route.fetch()           # the server accepts it ...
                route.abort()           # ... and the browser never sees the answer
            else:
                route.continue_()
        self.page.route('**/api/chat/sends?*', lambda r: lose_response(r) if r.request.method == 'POST'
                        else r.continue_())
        self.type_and_send('Lost response message')
        self.wait_reply('Recovered reply.')
        self.one_send('Lost response message', 'Recovered reply.')
        self.assertTrue(self.calls('GET', '/api/chat/sends'), 'looked up by key')
        self.assertEqual(len(set(seen)), 1, 'any retry was the identical request')
        self.assert_never_legacy()

    def test_lookup_404_while_the_post_is_in_flight_never_mints_a_new_key(self):
        self.s.scenario(reply='In flight reply.')
        self.open()
        held, lookups = [], []

        def handle(route):
            req = route.request
            if req.method == 'GET':
                resp = route.fetch()
                lookups.append(resp.status)
                route.fulfill(response=resp)
                return
            if not held:
                held.append(req.post_data)
                route.abort('timedout')  # the first POST has not reached the server yet
                return
            # The original request arrives late, before the retry: the retry must replay it.
            path = req.url.replace(self.s.base, '').split('?')[0]
            self.assertEqual(self.s.raw_post(path, held[0].encode()), 202)
            route.continue_()
        self.page.route('**/api/chat/sends?*', handle)
        self.type_and_send('In flight message')
        self.wait_reply('In flight reply.')
        self.one_send('In flight message', 'In flight reply.')
        self.assertIn(404, lookups, 'a lookup saw no receipt while the POST was in flight')
        self.assertEqual({json.loads(held[0])['client_key']}, {p['client_key'] for p in self.keyed_posts()})
        self.assert_never_legacy()

    def test_reload_mid_turn_recovers_the_same_intent_and_presents_it_once(self):
        self.s.gated(['First part. ', 'Second part.'])
        self.open()
        self.type_and_send('Reload me mid turn')
        until(lambda: self.s.reached(1), what='the turn to pause mid-stream')
        until(lambda: 'First part.' in self.page.inner_text('#chat-log'), what='the first streamed part')
        key = self.pending()['client_key']
        self.page.reload()
        self.page.wait_for_selector('#chat-message')
        until(lambda: self.pending() and self.pending().get('send_id'), what='pending kept across reload')
        self.assertEqual(self.pending()['client_key'], key)
        # Mid-turn the recorded owner row may already be in history as well as the provisional
        # bubble: C1 records the send's links only when it settles (stated limitation).
        until(lambda: 1 <= self.bubbles('Reload me mid turn') <= 2, what='the owner after reload')
        self.assertTrue(self.page.is_disabled('#send-message'), 'one pending intent at a time')
        self.s.release(1)
        self.wait_reply('First part. Second part.')
        self.one_send('Reload me mid turn', 'First part. Second part.')
        self.assert_never_legacy()

    def test_draft_edited_during_a_turn_survives_completion_and_navigation(self):
        self.s.gated(['Working on it. ', 'Done.'])
        self.open()
        self.type_and_send('Sent while drafting')
        until(lambda: self.s.reached(1), what='the turn to pause')
        self.page.fill('#chat-message', 'A newer draft')
        self.assertEqual(self.pending()['message'], 'Sent while drafting', 'the pending intent is immutable')
        # a non-chat action is excluded while the send is pending (the existing rule)
        refused = self.page.evaluate("()=>action('/maintenance/doctor').then(()=>'ran',e=>e.message)")
        self.assertEqual(refused, 'Wait for the current action to finish.')
        self.page.evaluate("()=>showTab('now')")
        self.page.evaluate("()=>showTab('chat')")
        self.page.wait_for_selector('#chat-message')
        until(lambda: self.page.input_value('#chat-message') == 'A newer draft', 10, what='draft back after navigation')
        self.s.release(1)
        self.wait_reply('Working on it. Done.')
        self.one_send('Sent while drafting', 'Working on it. Done.')
        self.assertEqual(self.page.input_value('#chat-message'), 'A newer draft')
        # history may present the stored reply row a poll before the send settles here
        until(lambda: self.pending() is None, 10, what='the pending intent cleared at settlement')
        self.assertEqual(self.page.input_value('#chat-message'), 'A newer draft')
        self.assertEqual(self.storage('chat-draft-existing-nova'), 'A newer draft')

    def test_storage_failure_never_sends_and_keeps_the_draft(self):
        self.open()
        self.page.evaluate("""()=>{const set=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){
            if(String(k).startsWith('chat-pending-'))throw new DOMException('full','QuotaExceededError');
            return set.call(this,k,v);};}""")
        self.type_and_send('Cannot be recorded')
        until(lambda: WORDS['storage'] in self.page.inner_text('#chat-status'), what='storage wording')
        self.assertEqual(self.keyed_posts(), [])
        self.assertEqual(self.s.sends(), [])
        self.assertEqual(self.page.input_value('#chat-message'), 'Cannot be recorded')
        self.assertFalse(self.page.is_disabled('#send-message'))
        self.assert_never_legacy()

    def test_profile_switch_and_late_results_stay_in_their_profile(self):
        self.s.gated(['Nova is thinking. ', 'Nova answered.'])
        self.page.goto(self.s.url('rowan'))
        self.page.wait_for_selector('#chat-message')
        self.page.fill('#chat-message', 'Rowan draft')
        self.open('nova')
        self.type_and_send('For Nova only')
        until(lambda: self.s.reached(1), what='nova turn paused')
        self.open('rowan')
        self.assertEqual(self.page.input_value('#chat-message'), 'Rowan draft')
        self.assertEqual(self.bubbles('For Nova only'), 0)
        self.assertIsNone(self.pending('rowan'))
        self.assertEqual(self.pending('nova')['message'], 'For Nova only')
        self.assertFalse(self.page.is_disabled('#send-message'), 'rowan is not blocked by nova')
        mark = len(self.requests)
        self.s.release(1)
        pause(1.0)
        later = [r[1] for r in self.requests[mark:] if '/api/' in r[1]]
        self.assertFalse([u for u in later if 'profile=nova' in u], 'the rowan page never polls nova')
        self.assertEqual(self.bubbles('Nova answered.', owner=False), 0)
        self.assertEqual(self.bubbles('Nova is thinking. Nova answered.', owner=False), 0)
        self.open('nova')
        self.wait_reply('Nova is thinking. Nova answered.')
        self.one_send('For Nova only', 'Nova is thinking. Nova answered.')
        self.assertEqual(self.s.sends('rowan'), [])

    def test_failed_generation_with_a_recorded_message_offers_ask_again(self):
        self.s.scenario(reply='partial', exit=1)
        self.open()
        self.type_and_send('This reply fails')
        self.wait_status('This reply fails', WORDS['failed_recorded'])
        self.assertTrue(self.page.query_selector('#chat-log button:has-text("Ask again")'))
        self.assertEqual(self.page.input_value('#chat-message'), '', 'not restored to the box')
        first = self.s.sends()
        self.assertEqual([s['state'] for s in first], ['failed'])
        self.s.scenario(reply='Asked again, answered.')
        self.page.click('#chat-log .bubble.user button:has-text("Ask again")')
        self.wait_reply('Asked again, answered.')
        sends = self.s.sends()
        self.assertEqual([s['state'] for s in sends], ['failed', 'complete'])
        self.assertNotEqual(sends[0]['client_key'], sends[1]['client_key'], 'Ask again is a new intent')
        self.assert_never_legacy()

    def test_stopped_turn_shows_its_partial_reply_as_partial(self):
        self.s.scenario(stream_steps=['Only this much.'], stream_pause_dir=str(self.s.pause), exit=130)
        self.open()
        self.type_and_send('This turn is stopped')
        self.wait_status('This turn is stopped', 'Stopped')
        until(lambda: self.page.query_selector('#chat-log .bubble.partial'), what='a partial reply bubble')
        self.assertIn('Partial reply', self.page.inner_text('#chat-log .bubble.partial'))
        self.assertEqual([s['state'] for s in self.s.sends()], ['interrupted'])

    def test_unknown_outcome_needs_confirmation_and_quiescence_for_a_new_key(self):
        self.s.scenario(kill_at='after_owner_row')
        self.open()
        self.type_and_send('Outcome unknown')
        self.wait_status('Outcome unknown', WORDS['unknown'], timeout=60)
        self.assertEqual(self.page.input_value('#chat-message'), '')
        self.page.click('#chat-log button:has-text("Send again")')
        self.assertIn(WORDS['duplicate'], self.page.inner_text('#chat-log'))
        self.page.click('#chat-log button:has-text("Cancel")')
        pause(0.5)
        self.assertEqual(len(self.s.sends()), 1, 'nothing sent without confirmation')
        self.s.scenario(reply='Second attempt answered.')
        self.page.click('#chat-log button:has-text("Send again")')
        self.page.click('#chat-log button:has-text("Send anyway")')
        self.wait_reply('Second attempt answered.')
        sends = self.s.sends()
        self.assertEqual([s['state'] for s in sends], ['unknown', 'complete'])
        self.assertNotEqual(sends[0]['client_key'], sends[1]['client_key'])
        receipt_checks = [r for r in self.calls('GET', f'/api/chat/sends/{sends[0]["send_id"]}')]
        self.assertTrue(receipt_checks, 'quiescence was re-checked on the receipt before the new key')
        self.assert_never_legacy()

    def test_ledger_reset_before_acceptance_is_reported_not_resent(self):
        self.open()
        blocked = {'on': True}
        self.page.route('**/api/chat/sends?*', lambda r: r.abort() if (r.request.method == 'POST' and blocked['on'])
                        else r.continue_())
        self.type_and_send('Sent across a reset')
        until(lambda: len(self.calls('GET', '/api/chat/sends')) >= 1, what='a lookup while unconfirmed')
        status, _ = self.s.api('POST', '/chat/sends/ledger/reset', {'confirm': 'reset send ledger'})
        self.assertEqual(status, 200)
        blocked['on'] = False
        self.wait_status('Sent across a reset', WORDS['reset'], timeout=40)
        self.assertTrue(self.page.query_selector('#chat-log button:has-text("Send again")'))
        self.assertEqual(self.s.sends(), [], 'the stale-generation request was never accepted')
        self.assertIsNone(self.pending())
        self.assertEqual(len({p['client_key'] for p in self.keyed_posts()}), 1)
        self.assert_never_legacy()

    def test_authentication_expiry_stops_polling_and_never_falls_back(self):
        self.s.gated(['Waiting for sign-in. ', 'Signed in again.'])
        self.open()
        expired = {'on': False}
        self.page.route('**/api/operations/*', lambda r: r.fulfill(status=401, content_type='application/json',
                        body='{"error":"bad or missing token"}') if expired['on'] else r.continue_())
        self.type_and_send('Sent before expiry')
        until(lambda: self.s.reached(1), what='turn paused')
        expired['on'] = True
        self.wait_status('Sent before expiry', WORDS['signed_out'])
        count = len(self.calls('GET', '/api/operations/'))
        pause(1.5)
        self.assertEqual(len(self.calls('GET', '/api/operations/')), count, 'protected polling stopped')
        self.assertEqual(self.pending()['message'], 'Sent before expiry')
        expired['on'] = False
        self.page.click('#chat-log button:has-text("Check now")')
        self.s.release(1)
        self.wait_reply('Waiting for sign-in. Signed in again.')
        self.one_send('Sent before expiry', 'Waiting for sign-in. Signed in again.')
        self.assert_never_legacy()

    def test_refused_while_another_turn_runs_is_not_sent_and_offered_back(self):
        self.s.gated(['Busy. ', 'Free.'])
        _, boot = self.s.api('GET', '/chat/sends/bootstrap')
        from kit.app import chat_sends as cs
        status, other = self.s.api('POST', '/chat/sends', {'client_key': cs.new_ulid(), 'generation': boot['generation'],
                                                           'conversation_id': boot['conversation_id'],
                                                           'message': 'Another client', 'session': None})
        self.assertEqual(status, 202)
        until(lambda: self.s.reached(1), what='the other turn running')
        self.open()
        self.type_and_send('Refused while busy')
        self.wait_status('Refused while busy', WORDS['not_sent'])
        self.assertEqual(self.page.input_value('#chat-message'), 'Refused while busy', 'offered back as a draft')
        self.assertIsNone(self.pending())
        self.assertEqual(len(self.s.sends()), 1)
        self.s.release(1)
        self.s.settled(other['send']['send_id'])
        self.assert_never_legacy()

    def test_withheld_reasoning_never_reaches_the_page(self):
        # The stored reply is the public text, as Hermes records it; a stored row WITH inline
        # markup is shown as recorded (the stated Phase 1A read boundary, not changed here).
        self.s.gated(['<think>SYNTHETIC_HIDDEN_C3', '</think>Visible answer.'], reply='Visible answer.')
        self.open()
        self.type_and_send('Show only public text')
        until(lambda: self.s.reached(1), what='paused inside the hidden block')
        pause(0.8)
        self.assertNotIn('SYNTHETIC_HIDDEN_C3', self.page.content())
        self.s.release(1)
        self.wait_reply('Visible answer.')
        self.assertNotIn('SYNTHETIC_HIDDEN_C3', self.page.content())


class DisabledClient(Browser):
    """The default: keyed routes absent, or present without the client opt-in. The page is
    the ordinary one and sends through POST /api/chat, exactly as before."""
    keyed = False

    def test_default_page_carries_no_keyed_client_and_uses_the_legacy_route(self):
        self.open()
        self.assertFalse(self.page.evaluate("!!document.querySelector('meta[name=\"tamanitomo-chat-sends\"]')"))
        self.assertFalse(self.page.evaluate('!!window.KeyedChat'))
        self.assertNotIn('chat-sends.js', self.page.content())
        self.page.route('**/api/chat?*', lambda r: r.fulfill(status=503, content_type='application/json',
                                                             body='{"detail":"synthetic refusal"}'))
        self.type_and_send('Default path message')
        until(lambda: self.calls('POST', '/api/chat'), what='the legacy POST')
        self.wait_status('Default path message', 'Failed to send')
        self.assertEqual(self.calls('POST', '/api/chat/sends'), [])
        self.assertEqual(self.calls('GET', '/api/chat/sends/bootstrap'), [])
        self.errors.clear()             # the legacy handler rethrows; that is its existing behaviour


class RoutesWithoutClient(DisabledClient):
    keyed = True
    client = False


if __name__ == '__main__':
    unittest.main()
