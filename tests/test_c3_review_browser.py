"""Reviewer-authored C3 browser acceptance tests. NOT EXECUTED successfully here:
Chromium refused page navigation with ERR_BLOCKED_BY_ADMINISTRATOR.

Copy under tests/ or run with PYTHONPATH=<repo>:<repo>/kit/scripts and
--import-mode=importlib. Reuses the actual server/fake-Hermes fixture and actual
Browser helper. Routing changes model transport/status visibility, not execution.
These are additional to the supplied tests, not replacements for them.
"""
import json
import pathlib
import sys

# When copied into tests/, this is the repository. For an external copy set PYTHONPATH.
ROOT = pathlib.Path(__file__).resolve().parents[1]
if (ROOT / 'kit/scripts').is_dir():
    sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from tests.test_phase1b_c3_browser import Browser, WORDS, until, pause
from kit.app import send_protocol as sp


class ClientRecoveryReview(Browser):
    def test_sign_in_expiry_before_acceptance_can_resume_the_same_key(self):
        self.s.scenario(reply='Recovered after signing in.')
        expired = {'on': True}
        self.open()

        def gate(route):
            if route.request.method == 'POST' and expired['on']:
                route.fulfill(status=401, content_type='application/json', body='{"error":"unauthorized"}')
            else:
                route.continue_()

        self.page.route('**/api/chat/sends?*', gate)
        self.type_and_send('A request before acceptance')
        self.wait_status('A request before acceptance', WORDS['signed_out'])
        original = self.pending()['client_key']
        expired['on'] = False
        self.page.click('#chat-log button:has-text("Check now")')
        self.wait_reply('Recovered after signing in.', timeout=15)
        self.one_send('A request before acceptance', 'Recovered after signing in.')
        self.assertEqual({p['client_key'] for p in self.keyed_posts()}, {original})
        self.assert_never_legacy()

    def test_lost_accepted_response_then_missing_ledger_stays_pending(self):
        self.s.scenario(reply='The server completed this request.')
        self.open()
        saved = {}
        ledger = sp.ledger_dir(self.s.home()) / sp.LEDGER_FILE
        kept = ledger.with_name(ledger.name + '.review-kept')

        def lose_after_acceptance(route):
            if route.request.method != 'POST' or saved:
                route.continue_()
                return
            reply = route.fetch()
            self.assertEqual(reply.status, 202)
            accepted = reply.json()
            saved.update(accepted)
            receipt = self.s.settled(accepted['send']['send_id'])
            self.assertEqual(receipt['owner_turn'], 'recorded')
            until(lambda: not self.s.app.state.operations.busy, what='worker idle before synthetic ledger loss')
            ledger.rename(kept)
            route.abort()

        self.page.route('**/api/chat/sends?*', lose_after_acceptance)
        try:
            self.type_and_send('An accepted request with a lost response')
            until(lambda: len(self.keyed_posts()) >= 2, timeout=20, what='the original-key recovery POST')
            pause(0.2)
            self.assertNotEqual(self.status_of('An accepted request with a lost response'), 'Not sent')
            self.assertIsNotNone(self.pending(), 'Ledger loss must not erase the original pending intent')
            self.assertEqual(len({p['client_key'] for p in self.keyed_posts()}), 1)
            self.assertFalse(ledger.exists(), 'No implicit ledger reset')
            self.assertEqual(self.s.owner_rows().count('An accepted request with a lost response'), 1)
            self.assert_never_legacy()
        finally:
            if kept.exists():
                kept.rename(ledger)

    def test_receipt_outage_does_not_forget_an_accepted_intent(self):
        self.s.gated(['The reply is running. ', 'Now complete.'])
        self.open()
        self.page.route('**/api/operations/*', lambda r: r.fulfill(
            status=404, content_type='application/json', body='{"error":"not_found"}'))
        # This URL pattern targets direct send-id reads, not bootstrap or POST /sends.
        def receipt_unavailable(route):
            if '/bootstrap' in route.request.url:
                route.continue_()
            else:
                route.fulfill(status=503, content_type='application/json', body='{"error":"source_unavailable"}')
        self.page.route('**/api/chat/sends/*', receipt_unavailable)
        try:
            self.type_and_send('Keep my accepted request')
            until(lambda: self.s.reached(1), what='executor paused')
            until(lambda: any('/api/chat/sends/snd_' in u for _, u, _ in self.requests),
                  what='receipt fallback request')
            pause(0.2)
            self.assertIsNotNone(self.pending())
            self.assertEqual(self.pending()['message'], 'Keep my accepted request')
            self.assertEqual(len(self.s.sends()), 1)
            self.assert_never_legacy()
        finally:
            self.s.release(1)

    def test_delayed_bootstrap_cannot_clear_a_newer_draft_after_navigation(self):
        self.s.scenario(reply='The older request completed.')
        self.open()
        held = []
        self.page.route('**/api/chat/sends/bootstrap?*', lambda r: held.append(r))
        self.page.eval_on_selector('#chat-message', "el=>el.dataset.reviewOld='1'")
        self.type_and_send('Older submitted text')
        until(lambda: held, what='bootstrap held before pending acceptance')
        self.page.evaluate("()=>showTab('now')")
        self.page.evaluate("()=>showTab('chat')")
        self.page.wait_for_selector('#chat-message')
        self.page.wait_for_function("!document.querySelector('.chat-loading')")
        self.page.wait_for_function("document.getElementById('chat-message') && !document.getElementById('chat-message').dataset.reviewOld")
        self.page.fill('#chat-message', 'New draft after navigation')
        held.pop(0).continue_()
        self.wait_reply('The older request completed.')
        self.assertEqual(self.page.input_value('#chat-message'), 'New draft after navigation')
        self.assertEqual(self.storage('chat-draft-existing-nova'), 'New draft after navigation')
        self.assert_never_legacy()


class PreviouslyDisclosedGates(Browser):
    def test_reload_during_turn_does_not_add_a_second_transcript_owner_bubble(self):
        # Known submitted limitation, NOT a newly executed reviewer failure.
        # A separate pending-request status is permitted; a second transcript message is not.
        self.s.gated(['Working. ', 'Finished.'])
        self.open()
        self.type_and_send('One owner message after reload')
        until(lambda: self.s.reached(1), what='owner committed, reply paused')
        try:
            self.page.reload()
            self.page.wait_for_selector('#chat-message')
            self.page.wait_for_function("!document.querySelector('.chat-loading')")
            until(lambda: self.pending() and self.pending().get('send_id'), what='pending restored')
            pause(0.5)
            self.assertEqual(self.bubbles('One owner message after reload'), 1)
        finally:
            self.s.release(1)

    def test_send_again_recheck_refuses_live_or_unproven_receipt(self):
        # UI guard test only: the execution is a real fake-Hermes unknown outcome,
        # and only its status response at confirmation is replaced. Not OS liveness evidence.
        self.s.scenario(kill_at='after_owner_row')
        self.open()
        self.type_and_send('Check quiescence at confirmation')
        self.wait_status('Check quiescence at confirmation', WORDS['unknown'], timeout=60)
        before_posts = len(self.keyed_posts())
        send = self.s.sends()[0]
        for liveness in ('live', 'unproven'):
            # Adapted (C3 closure): Playwright passes (route, request) to a two-parameter
            # handler, which overwrote a `value=liveness` default with the Request object.
            def refusing(value):
                def refuse(route):
                    response = route.fetch()
                    receipt = response.json()
                    receipt.update(state='unknown', liveness=value, settled=False)
                    route.fulfill(status=200, content_type='application/json', body=json.dumps(receipt))
                return refuse
            refuse = refusing(liveness)
            pattern = '**/api/chat/sends/' + send['send_id'] + '?*'
            self.page.route(pattern, refuse)
            # Adapted (C3 closure): clear the hint and count receipt reads, so the second
            # iteration cannot pass on the first iteration's leftover text.
            self.page.evaluate("()=>{document.getElementById('chat-status').textContent=''}")
            reads = len(self.calls('GET', '/api/chat/sends/' + send['send_id']))
            self.page.click('#chat-log button:has-text("Send again")')
            self.page.click('#chat-log button:has-text("Send anyway")')
            until(lambda: 'not yet proven finished' in self.page.inner_text('#chat-status'),
                  what='the live/unproven recheck to refuse')
            self.assertGreater(len(self.calls('GET', '/api/chat/sends/' + send['send_id'])), reads)
            pause(0.3)
            self.assertEqual(len(self.keyed_posts()), before_posts)
            self.assertEqual(len(self.s.sends()), 1)
            self.page.unroute(pattern, refuse)
        self.assert_never_legacy()
