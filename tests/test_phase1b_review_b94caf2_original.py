"""Reviewer regressions for the supplied b94caf2 snapshot.

Synthetic HTTP/protocol-double evidence only, NOT a pinned-Hermes or browser run.
Run from the repository root with its existing pytest pythonpath configuration.
These tests add no production code and use only temporary fixture homes.
"""
import json
import threading
from unittest.mock import patch
import unittest

from kit.app import chat_send_routes as csr
from tests.test_phase1b_c1_closure import Base, LINUX, POSIX_ONLY

PUBLIC = 'Public answer 6254.'
HIDDEN_TAIL = 'SYNTHETIC_PRIVATE_TAIL_9531'
HIDDEN_FINAL = 'SYNTHETIC_PRIVATE_FINAL_8276'


@unittest.skipUnless(LINUX, POSIX_ONLY)
class StreamPrivacyReview(Base):
    def test_running_hidden_block_stays_hidden_after_raw_buffer_rollover(self):
        # Runtime currently keeps the last 1,000,000 raw characters. The opening
        # tag is deliberately earlier than that boundary; no real private text.
        self.steps('<think>' + 'x' * 1_000_020 + HIDDEN_TAIL,
                   '</think>' + PUBLIC, reply=PUBLIC)
        self.a.bootstrap()
        svc = next(iter(self.a.app.state.chat_sends._services.values()))
        original_launch = svc.launch
        processed = threading.Event()

        def observed_launch(send_id, message, on_delta=None):
            def observed_delta(text):
                if on_delta is not None:
                    on_delta(text)
                # Test-only observation after the real route callback returns.
                processed.set()
            return original_launch(send_id, message, observed_delta)

        with patch.object(svc, 'launch', side_effect=observed_launch):
            ident, send_id = self.start()
            try:
                self.assertTrue(processed.wait(20), 'Fixture delta was not processed')
                response = self.op(ident)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body['status'], 'running')
                leaked = HIDDEN_TAIL in json.dumps(body)
                length = len(body.get('stream_text', ''))
            finally:
                self.go(1)
                self.a.settle(send_id)
        self.assertEqual(self.a.launches(send_id), 1)
        self.assertFalse(leaked, f'Hidden tail reached the HTTP response after rollover; snapshot length={length}')

    def _completed_view(self, exit_code):
        # The durable assistant row is intentionally already clean. Only the
        # transient delta history contains the synthetic hidden block.
        self.steps('<think>' + HIDDEN_FINAL + '</think>', PUBLIC,
                   reply=PUBLIC, exit=exit_code)
        ident, send_id = self.start()
        self.go(1)
        self.a.settle(send_id)
        response = self.op(ident)
        self.assertEqual(response.status_code, 200)
        view = response.json()
        self.assertEqual(view['status'], 'complete' if exit_code == 0 else 'failed')
        source_reply = [r for r in self.a.rows() if r[2] == 'assistant'][-1][3]
        self.assertEqual(source_reply, PUBLIC)
        self.assertEqual(self.a.launches(send_id), 1)
        self.assertNotIn(HIDDEN_FINAL, self.op_file(ident).read_text())
        leaked = HIDDEN_FINAL in json.dumps(view)
        self.assertFalse(leaked, 'Terminal operation exposes the unfiltered transient delta history despite a clean stored reply')

    def test_completed_operation_does_not_reintroduce_hidden_delta_text(self):
        self._completed_view(0)

    def test_failed_operation_does_not_reintroduce_hidden_delta_text(self):
        self._completed_view(1)


class PublicOutputControl(unittest.TestCase):
    def test_plain_public_text_remains_available_and_bounded(self):
        source = 'ordinary public text ' * 10000 + 'END'
        text, truncated = csr.public_stream(source)
        self.assertEqual(text, source[-csr.STREAM_LIMIT:])
        self.assertTrue(truncated)
