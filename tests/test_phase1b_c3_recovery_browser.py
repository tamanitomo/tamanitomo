"""Phase 1B C3 recovery closure (review of a8b4e52): browser journeys beyond the reviewer's.

Same boundary as tests/test_phase1b_c3_browser.py (headless Chromium -> the actual page ->
real uvicorn -> SendService -> fake Hermes; synthetic data only). Playwright routing models
transport only; a synthetic ledger is moved only after settlement and an idle worker.
TAMANITOMO_C3_REQUIRE_BROWSER=1 makes a missing browser a failure, never a skip.
"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from tests.phase1b_c1.harness import LINUX                                   # noqa: E402
from tests.test_phase1b_c3_browser import Browser, pause, until               # noqa: E402
from kit.app import send_protocol as sp                                       # noqa: E402


@unittest.skipUnless(LINUX, 'the C1 supervision is established on Linux only')
class RecoveryClosure(Browser):

    def test_reload_with_an_equal_text_earlier_message_hides_nothing(self):
        # Control for the request status: no history row is matched or hidden by text.
        self.s.scenario(reply='First answer.')
        self.open()
        self.type_and_send('Same words')
        self.wait_reply('First answer.')
        until(lambda: self.pending() is None, what='first send settled')
        self.s.gated(['Second ', 'answer.'])
        self.type_and_send('Same words')
        until(lambda: self.s.reached(1), what='second owner recorded, reply paused')
        self.page.reload()
        self.page.wait_for_selector('#chat-message')
        self.page.wait_for_function("!document.querySelector('.chat-loading')")
        until(lambda: self.page.query_selector('#chat-log .keyed-request'), what='the request status')
        for _ in range(4):
            self.assertEqual(self.bubbles('Same words'), 2, 'both recorded rows, no provisional third')
            pause(0.25)
        self.s.release(1)
        self.wait_reply('Second answer.')
        until(lambda: self.pending() is None, what='second send settled')
        until(lambda: not self.page.query_selector('#chat-log .keyed-request'), what='request status reconciled')
        self.assertEqual(self.bubbles('Same words'), 2)
        self.assertEqual(self.bubbles('Second answer.', owner=False), 1)
        self.assert_never_legacy()

    def test_navigation_during_bootstrap_without_typing_does_not_bring_the_sent_text_back(self):
        self.s.scenario(reply='Answered once.')
        self.open()
        held = []
        self.page.route('**/api/chat/sends/bootstrap?*', lambda r: held.append(r))
        self.type_and_send('Sent before navigating')
        until(lambda: held, what='bootstrap held')
        self.page.evaluate("()=>showTab('now')")
        self.page.evaluate("()=>showTab('chat')")
        self.page.wait_for_selector('#chat-message')
        self.page.wait_for_function("!document.querySelector('.chat-loading')")
        held.pop(0).continue_()
        self.wait_reply('Answered once.')
        self.assertEqual(self.page.input_value('#chat-message'), '', 'the unedited submitted draft is cleared')
        self.assertEqual(self.storage('chat-draft-existing-nova'), '')
        self.assertEqual(len(self.keyed_posts()), 1)
        self.assert_never_legacy()

    def test_typing_during_bootstrap_in_the_same_view_is_kept(self):
        self.s.scenario(reply='Answered while drafting.')
        self.open()
        held = []
        self.page.route('**/api/chat/sends/bootstrap?*', lambda r: held.append(r))
        self.type_and_send('The submitted text')
        until(lambda: held, what='bootstrap held')
        self.page.fill('#chat-message', 'The submitted text')     # an edit, even back to the same text
        held.pop(0).continue_()
        self.wait_reply('Answered while drafting.')
        self.assertEqual(self.page.input_value('#chat-message'), 'The submitted text')
        self.assertEqual(self.storage('chat-draft-existing-nova'), 'The submitted text')
        self.assert_never_legacy()

    def test_unresolved_intent_is_recovered_by_check_now_with_the_same_key(self):
        self.s.scenario(reply='Found again.')
        self.open()
        ledger = sp.ledger_dir(self.s.home()) / sp.LEDGER_FILE
        kept = ledger.with_name(ledger.name + '.closure-kept')
        lost = {}

        def lose_after_acceptance(route):
            if route.request.method != 'POST' or lost:
                route.continue_()
                return
            accepted = route.fetch().json()
            lost.update(accepted)
            self.s.settled(accepted['send']['send_id'])
            until(lambda: not self.s.app.state.operations.busy, what='worker idle before synthetic ledger loss')
            ledger.rename(kept)
            route.abort()

        self.page.route('**/api/chat/sends?*', lose_after_acceptance)
        try:
            self.type_and_send('Recover me')
            until(lambda: self.page.query_selector('#chat-log button:has-text("Check now")'), timeout=20,
                  what='the manual same-request check')
            self.assertIn('not confirmed', self.status_of('Recover me'))
            self.assertNotIn('will check again', self.status_of('Recover me'))
            key = self.pending()['client_key']
        finally:
            if kept.exists():
                kept.rename(ledger)
        self.page.click('#chat-log button:has-text("Check now")')
        self.wait_reply('Found again.')
        self.one_send('Recover me', 'Found again.')
        self.assertEqual({p['client_key'] for p in self.keyed_posts()}, {key})
        until(lambda: self.pending() is None, what='settled by its receipt')
        self.assert_never_legacy()


if __name__ == '__main__':
    unittest.main()
