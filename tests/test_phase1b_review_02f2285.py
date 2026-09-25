"""Focused reviewer checks against reconstructed 02f2285 (C1 code == 3d78c57).
All inputs synthetic. No provider, platform, or live profile is used.
Run from the repository root with pythonpath pointing to . and kit/scripts.
"""
import json
import threading
import unittest
from unittest.mock import patch

from kit.app.chat_send_routes import PublicFilter, public_text
from tests import test_phase1b_c1_review_r1 as fixtures
from tests.test_phase1b_c1_integration import LINUX, POSIX_ONLY, wait_for
from tests import test_dispatch_claim as c2fixtures
DAY = c2fixtures.DAY
import companion_dispatch as dispatch
import companion_outbox as outbox

HIDDEN = 'SYNTHETIC_UNICODE_PRIVATE_028'
PREFIX = '\u0130' * 96
TAIL = 'Visible public tail.'


class UnicodeFilter(unittest.TestCase):
    def test_lowercase_expansion_preserves_public_characters(self):
        self.assertEqual(public_text('\u0130stanbul <think>hidden</think>Public answer.'),
                         '\u0130stanbul Public answer.')

    def test_fragmentation_does_not_change_hidden_block_exclusion(self):
        raw = PREFIX + '<think>' + HIDDEN + '</think>' + TAIL
        expected = PREFIX + TAIL
        f = PublicFilter()
        one = f.feed(raw) + f.finish()
        f = PublicFilter()
        fragmented = ''.join(f.feed(c) for c in raw) + f.finish()
        self.assertEqual(fragmented, expected)
        self.assertNotIn(HIDDEN, one)
        self.assertEqual(one, expected)


@unittest.skipUnless(LINUX, POSIX_ONLY)
class UnicodeHttp(fixtures.StreamPrivacyReview):
    test_running_hidden_block_stays_hidden_after_raw_buffer_rollover = None
    test_completed_operation_does_not_reintroduce_hidden_delta_text = None
    test_failed_operation_does_not_reintroduce_hidden_delta_text = None
    test_ordinary_public_output_is_still_delivered = None

    def test_interruption_does_not_publish_hidden_unicode_prefixed_delta(self):
        # The pause is before an assistant source row is created. Therefore the terminal
        # response must use the transient public partial; no stored hidden row is involved.
        self.steps(PREFIX + '<think>' + HIDDEN + '</think>' + TAIL,
                   'not emitted', gates=(1,), reply='A deliberately clean durable reply.')
        self.a.bootstrap()
        svc = next(iter(self.a.app.state.chat_sends._services.values()))
        original = svc.launch
        processed = threading.Event()
        def observed_launch(send_id, message, on_delta=None):
            def observed_delta(text):
                if on_delta is not None:
                    on_delta(text)
                processed.set()
            return original(send_id, message, observed_delta)
        with patch.object(svc, 'launch', side_effect=observed_launch):
            ident, send_id = self.start()
            try:
                self.assertTrue(processed.wait(30), 'fixture delta never reached the route')
                self.assertTrue(wait_for(lambda: (self.pause / 'at1').exists(), 30))
                running = self.op(ident).json()
                self.assertEqual(running['status'], 'running')
                self.assertNotIn(HIDDEN, json.dumps(running))
                self.assertEqual(self.a.post(f'/chat/sends/{send_id}/stop').status_code, 200)
                self.a.settle(send_id)
                terminal = self.op(ident).json()
            finally:
                (self.pause / 'go1').write_text('')
        self.assertEqual(terminal['status'], 'interrupted')
        self.assertEqual(self.a.launches(send_id), 1)
        self.assertFalse(any(row[2] == 'assistant' for row in self.a.rows()),
                         'fixture must not store an assistant row')
        self.assertNotIn(HIDDEN, self.op_file(ident))
        self.assertNotIn(HIDDEN, json.dumps(terminal),
                         'hidden transient text reappeared only at the terminal HTTP read')
        self.assertEqual(terminal['result']['response'], PREFIX + TAIL)


class PrecheckCancellation(c2fixtures.Base):
    def test_drop_between_precheck_and_claim_prevents_charge_and_delivery(self):
        entry = self.queue()
        old = dispatch.verdict
        def cancel_after_check(c, snapshot, now):
            decision = old(c, snapshot, now)
            self.assertEqual(decision['action'], 'send')
            outbox.mark(c, entry['id'], 'withheld', 'owner withdrew it', now)
            return decision
        with patch.object(dispatch, 'verdict', side_effect=cancel_after_check), self.invoke():
            result = dispatch.run(self.c, DAY)
        self.assertEqual((self.status(entry['id']), self.calls(), self.slots()), ('withheld', 0, 0))
        self.assertEqual(result['handled'][0]['action'], 'skipped')
