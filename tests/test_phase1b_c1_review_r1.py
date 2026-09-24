"""Reviewer regressions R1/R2 (TAMANITOMO_C1_REVIEW_AND_HANDOFF_b94caf2.md sections 3-4).

RECONSTRUCTED: the reviewer's own `test_phase1b_c1_review_r1.py` (companion review ZIP) was not
available on this host. These tests implement the review's described reproductions with its
class and test names; their bytes are not the reviewer's.

BOUNDARY: HTTP (TestClient) -> chat_send_routes -> SendService -> executor -> the fake Hermes
PROTOCOL DOUBLE (stream_steps) -> a synthetic state.db. Synthetic text only. The durable
assistant row is deliberately CLEAN (`reply`), so a hidden marker in any response can only
come from the transient delta path.
"""
import json
import pathlib
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from tests.test_phase1b_c1_integration import App, LINUX, POSIX_ONLY, wait_for     # noqa: E402

HIDDEN = 'Synthetic hidden marker 7e1f'
PUBLIC = 'Synthetic public answer 51c2.'


@unittest.skipUnless(LINUX, POSIX_ONLY)
class StreamPrivacyReview(unittest.TestCase):

    def setUp(self):
        self.a = App(self)
        self.pause = self.a.tmp / 'pause'
        self.pause.mkdir()

    def steps(self, *pieces, gates=(), **extra):
        """stream_steps with every go<i> pre-released except those listed in `gates`."""
        for i in range(1, len(pieces)):
            if i not in gates:
                (self.pause / f'go{i}').write_text('')
        self.a.scenario(stream_steps=list(pieces), stream_pause_dir=str(self.pause), **extra)

    def start(self):
        r = self.a.post('/chat/sends', self.a.body('A synthetic owner message'))
        self.assertEqual(r.status_code, 202, r.text)
        return r.json()['operation']['id'], r.json()['send']['send_id']

    def op(self, ident):
        r = self.a.get('/operations/' + ident)
        self.assertEqual(r.status_code, 200, r.text)
        return r

    def op_file(self, ident):
        return (self.a.state / 'operations' / (ident + '.json')).read_text()

    def test_running_hidden_block_stays_hidden_after_raw_buffer_rollover(self):
        """R1: `<think>`, then more than the 1,000,000-character raw buffer, then a marker, then a
        pause before `</think>`. No poll may show the marker, before or after the pause."""
        filler = 'h' * 1_000_050
        self.steps('<think>', filler, HIDDEN, '</think>' + PUBLIC, ' Done.', gates=(3, 4), reply=PUBLIC + ' Done.')
        ident, send_id = self.start()
        self.assertTrue(wait_for(lambda: (self.pause / 'at3').exists(), 60), 'the fixture never reached the pause')
        seen = []
        end = time.monotonic() + 1.5
        while time.monotonic() < end:                       # the marker was emitted before the pause
            seen.append(self.op(ident).text)
            time.sleep(0.05)
        for payload in seen:                                # R1 itself: the marker during the pause
            self.assertNotIn(HIDDEN, payload)
        (self.pause / 'go3').write_text('')
        view = wait_for(lambda: (lambda v: v if (v.get('stream') or {}).get('text') == PUBLIC else None)(
            self.op(ident).json()), 60)
        self.assertIsNotNone(view, f'the public tail never arrived: {str(self.op(ident).json())[:300]}')
        seen.append(json.dumps(view))                       # ordered pipe: the marker delta came first
        (self.pause / 'go4').write_text('')
        self.a.settle(send_id)
        seen.append(self.op(ident).text)
        for payload in seen:
            self.assertNotIn(HIDDEN, payload)
            self.assertNotIn('h' * 64, payload)
        self.assertEqual(self.a.launches(send_id), 1)

    def terminal(self, **extra):
        self.steps(f'<think>{HIDDEN}</think>', PUBLIC, reply=PUBLIC, **extra)
        ident, send_id = self.start()
        receipt = self.a.settle(send_id)
        return ident, send_id, receipt, self.op(ident)

    def test_completed_operation_does_not_reintroduce_hidden_delta_text(self):
        """R2 on completion: the remembered delta transcript must not beat the clean final row."""
        ident, send_id, receipt, r = self.terminal()
        self.assertEqual(r.json()['status'], 'complete')
        self.assertNotIn(HIDDEN, r.text)
        self.assertEqual(r.json()['result']['response'], PUBLIC)
        self.assertNotIn(HIDDEN, self.op_file(ident))
        self.assertEqual(self.a.launches(send_id), 1)

    def test_failed_operation_does_not_reintroduce_hidden_delta_text(self):
        """R2 on failure (the executor exits non-zero after streaming)."""
        ident, send_id, receipt, r = self.terminal(exit=1)
        self.assertEqual(r.json()['status'], 'failed')
        self.assertNotIn(HIDDEN, r.text)
        self.assertNotIn(HIDDEN, self.op_file(ident))
        self.assertEqual(self.a.launches(send_id), 1)

    def test_ordinary_public_output_is_still_delivered(self):
        """Control: plain public text streams while running and is the terminal response."""
        self.steps('Synthetic public ', 'answer 51c2.', gates=(1,), reply=PUBLIC)
        ident, send_id = self.start()
        view = wait_for(lambda: (lambda v: v if (v.get('stream') or {}).get('text') == 'Synthetic public ' else None)(
            self.op(ident).json()), 60)
        self.assertIsNotNone(view)
        (self.pause / 'go1').write_text('')
        self.a.settle(send_id)
        r = self.op(ident)
        self.assertEqual((r.json()['status'], r.json()['result']['response']), ('complete', PUBLIC))
        self.assertEqual(self.a.launches(send_id), 1)


@unittest.skipUnless(LINUX, POSIX_ONLY)
class StreamPrivacyCoverage(StreamPrivacyReview):
    """Beyond the reviewer's regressions (handoff section 4, "Extend tests"): the same hidden
    delta across interruption, restart reconstruction, revocation, ledger loss and source
    unavailability, asserting the WHOLE payload. Written for this task, not by the reviewer."""

    test_running_hidden_block_stays_hidden_after_raw_buffer_rollover = None
    test_completed_operation_does_not_reintroduce_hidden_delta_text = None
    test_failed_operation_does_not_reintroduce_hidden_delta_text = None
    test_ordinary_public_output_is_still_delivered = None

    def clean(self, r, ident):
        self.assertNotIn(HIDDEN, r.text)
        self.assertNotIn(HIDDEN, self.op_file(ident))
        return r.json()

    def test_interrupted_keeps_only_public_partial_text(self):
        self.steps(f'<think>{HIDDEN}</think>', 'Partial public ', 'never sent', gates=(2,), reply=PUBLIC)
        ident, send_id = self.start()
        self.assertTrue(wait_for(lambda: (self.pause / 'at2').exists(), 60))
        wait_for(lambda: (self.op(ident).json().get('stream') or {}).get('text') == 'Partial public ', 30)
        self.assertEqual(self.a.post(f'/chat/sends/{send_id}/stop').status_code, 200)
        self.a.settle(send_id)
        view = self.clean(self.op(ident), ident)
        self.assertEqual(view['status'], 'interrupted')
        self.assertNotIn('stream', view)
        self.assertEqual(view['result']['response'], 'Partial public ')     # remembered, filtered
        self.assertEqual(self.a.launches(send_id), 1)

    def test_restart_reconstruction_uses_the_clean_row(self):
        ident, send_id, _, _ = self.terminal()
        self.a.restart()
        view = self.clean(self.op(ident), ident)
        self.assertEqual((view['status'], view['result']['response']), ('complete', PUBLIC))
        self.assertEqual([m['content'] for m in view['result']['messages']], ['A synthetic owner message', PUBLIC])
        self.assertEqual(self.a.launches(send_id), 1)

    def test_revocation_withholds_everything(self):
        from kit.app import chat_sources as csrc
        ident, send_id, _, _ = self.terminal()
        (self.a.home() / csrc.BINDING_FILE).write_text(json.dumps({'workspace': False}))
        view = self.clean(self.op(ident), ident)
        self.assertEqual((view['result']['response'], view['result']['messages'], view['result']['content_retained']),
                         (None, [], False))

    def test_ledger_loss_is_the_restricted_view(self):
        from kit.app import send_protocol as sp
        ident, send_id, _, _ = self.terminal()
        id_file = sp.ledger_dir(self.a.home()) / sp.LEDGER_ID_FILE
        id_file.rename(id_file.with_suffix('.away'))
        view = self.clean(self.op(ident), ident)
        self.assertEqual((view['status'], view['error_code'], view['result']), ('unknown', 'send_ledger_unavailable', None))

    def test_source_unavailable_withholds_content(self):
        ident, send_id, _, _ = self.terminal()
        moved = []
        for name in ('state.db', 'state.db-wal', 'state.db-shm'):
            path = self.a.home() / name
            if path.exists():
                path.rename(path.with_name(name + '.away'))
                moved.append(path)
        try:
            view = self.clean(self.op(ident), ident)
            self.assertEqual(view['send']['links'], 'unavailable')
            self.assertEqual((view['result']['response'], view['result']['messages']), (None, []))
        finally:
            for path in moved:
                path.with_name(path.name + '.away').rename(path)
        self.assertEqual(self.a.launches(send_id), 1)


class PublicFilterUnit(unittest.TestCase):
    """The incremental boundary itself (no processes)."""

    def run_all(self, pieces):
        from kit.app.chat_send_routes import PublicFilter
        f = PublicFilter()
        out = ''.join(f.feed(p) for p in pieces)
        self.assertLessEqual(len(f.pending), 11)
        return out + f.finish(), f

    def test_every_split_of_a_block(self):
        text = 'Before <think>hidden body</think> after <REASONING>more</reasoning>end'
        for cut in range(len(text) + 1):
            with self.subTest(cut=cut):
                self.assertEqual(self.run_all([text[:cut], text[cut:]])[0], 'Before  after end')
        self.assertEqual(self.run_all(list(text))[0], 'Before  after end')      # one character at a time

    def test_bounded_state_inside_a_huge_block(self):
        from kit.app.chat_send_routes import PublicFilter
        f = PublicFilter()
        self.assertEqual(f.feed('<think>'), '')
        for _ in range(30):
            self.assertEqual(f.feed('x' * 100_000), '')
            self.assertLessEqual(len(f.pending), 8)
        self.assertEqual(f.feed('marker</think>tail'), 'tail')

    def test_ordinary_text_and_edges(self):
        self.assertEqual(self.run_all(['a < b and <b>bold</b>'])[0], 'a < b and <b>bold</b>')
        self.assertEqual(self.run_all(['ends with <thi'])[0], 'ends with <thi')   # never became a tag
        out, f = self.run_all(['<thinking>never closed'])
        self.assertEqual((out, f.withheld), ('', True))
        self.assertEqual(self.run_all(['x</think>y'])[0], 'x</think>y')          # no opening: not withheld


if __name__ == '__main__':
    unittest.main()
