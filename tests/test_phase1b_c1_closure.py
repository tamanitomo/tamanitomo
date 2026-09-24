"""Phase 1B C1 integration closure (continuation handoff 2026-09-24, findings F1-F3).

BOUNDARY: as tests/test_phase1b_c1_integration.py -- HTTP routes (TestClient) ->
chat_send_routes -> SendService -> executor -> the fake Hermes PROTOCOL DOUBLE -> a
synthetic state.db. Nothing here is evidence about Hermes itself, a browser, or a device.

F1  a keyed operation whose ledger cannot resolve it never falls back to the raw legacy row
F2  the keyed operation view carries a bounded, authorised public stream snapshot
F3  key lookup and open receipts carry the same authorised links as the direct receipt

Each test was first run against the unchanged reviewed code (dd7d614); the outcomes are
recorded in Phase1B_C1_ActivationReadiness.md.
"""
import json
import os
import pathlib
import sqlite3
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from fastapi.testclient import TestClient      # noqa: E402

from kit.app import chat_send_routes as csr    # noqa: E402
from kit.app import chat_sends as cs           # noqa: E402
from kit.app import chat_sources as csrc       # noqa: E402
from kit.app import send_protocol as sp        # noqa: E402
from kit.app.server import build               # noqa: E402
from tests.test_phase1b_c1_integration import App, LINUX, POSIX_ONLY, wait_for     # noqa: E402

OWNER, REPLY_A, REPLY_B, REPLY_C = ('Unmistakable owner 3141', 'Unmistakable alpha 2718 ',
                                    'Unmistakable bravo 1618 ', 'Unmistakable charlie 1414')
LINK_FIELDS = ('session', 'links', 'owner_message_id', 'reply_message_ids')


class Base(unittest.TestCase):

    def setUp(self):
        self.a = App(self)
        self.pause = self.a.tmp / 'pause'
        self.pause.mkdir()

    # ----- helpers -----

    def op(self, ident, profile='nova'):
        return self.a.get('/operations/' + ident, profile)

    def op_file(self, ident):
        return self.a.state / 'operations' / (ident + '.json')

    def revoke(self, profile='nova'):
        (self.a.home(profile) / csrc.BINDING_FILE).write_text(json.dumps({'workspace': False}))

    def steps(self, *pieces, profile='nova', **extra):
        self.a.scenario(profile, stream_steps=list(pieces), stream_pause_dir=str(self.pause), **extra)

    def go(self, i):
        (self.pause / f'go{i}').write_text('')

    def start(self, message=OWNER, profile='nova'):
        r = self.a.post('/chat/sends', self.a.body(message, profile), profile)
        self.assertEqual(r.status_code, 202, r.text)
        return r.json()['operation']['id'], r.json()['send']['send_id']

    def id_file(self, profile='nova'):
        return sp.ledger_dir(self.a.home(profile)) / sp.LEDGER_ID_FILE

    def ledger_files(self, profile='nova'):
        return sorted(p.name for p in sp.ledger_dir(self.a.home(profile)).iterdir())

    def executors(self, profile='nova'):
        d = sp.ledger_dir(self.a.home(profile)) / 'executors'
        return sorted(p.name for p in d.iterdir()) if d.is_dir() else []

    def assert_no_text(self, payload, *texts):
        blob = payload if isinstance(payload, str) else json.dumps(payload)
        for text in texts:
            self.assertNotIn(text.strip(), blob)

    def assert_restricted(self, r, code):
        """F1: an explicit unknown outcome for a known keyed send, never a legacy row."""
        self.assertEqual(r.status_code, 200, r.text)
        view = r.json()
        self.assertEqual((view['kind'], view['format'], view['status'], view['error_code']),
                         ('chat', 2, 'unknown', code))
        self.assertEqual(view['send']['state'], 'unknown')
        for key in ('stream_text', 'stream'):
            self.assertNotIn(key, view)
        self.assertIn(view.get('result'), (None,))
        return view


@unittest.skipUnless(LINUX, POSIX_ONLY)
class F1LegacyFallback(Base):
    """A keyed operation is never returned as an unrestricted legacy row because the ledger
    cannot establish its receipt; no read launches, resets or recreates anything."""

    def completed(self):
        self.a.scenario(reply=REPLY_A)
        body, accepted, _ = self.a.send(OWNER)
        ident, send_id = accepted['operation']['id'], accepted['send']['send_id']
        mem = self.a.app.state.operations.rows[ident]
        self.assertIn(REPLY_A.strip(), json.dumps(mem))        # the in-memory copy holds the reply
        return body, ident, send_id

    def test_unreadable_ledger_authorised_and_revoked(self):
        for revoked in (False, True):
            with self.subTest(revoked=revoked):
                if revoked:
                    self.a = App(self)
                _, ident, _ = self.completed()
                if revoked:
                    self.revoke()
                rows, execs = self.a.rows(), self.executors()
                self.id_file().rename(self.id_file().with_suffix('.away'))       # unreadable: 'lost'
                files = self.ledger_files()
                r = self.op(ident)
                self.assert_no_text(r.text, OWNER, REPLY_A)
                self.assert_restricted(r, 'send_ledger_unavailable')
                self.assertEqual((self.a.rows(), self.executors(), self.ledger_files()), (rows, execs, files))

    def test_corrupt_ledger(self):
        _, ident, _ = self.completed()
        self.revoke()
        db = self.a.ledger()
        for extra in ('-wal', '-shm'):
            pathlib.Path(str(db) + extra).unlink(missing_ok=True)
        db.write_bytes(b'not a database' * 100)
        r = self.op(ident)
        self.assert_no_text(r.text, OWNER, REPLY_A)
        self.assert_restricted(r, 'send_ledger_unavailable')
        self.assertEqual(db.read_bytes(), b'not a database' * 100)            # never reset by a read
        self.assertEqual([n for n in self.ledger_files() if n.startswith('ledger.lost-')], [])

    def test_persisted_format_two_after_restart(self):
        _, ident, send_id = self.completed()
        session = self.a.rows()[0][1]
        self.revoke()
        self.a.restart()
        self.id_file().rename(self.id_file().with_suffix('.away'))
        r = self.op(ident)
        self.assert_no_text(r.text, OWNER, REPLY_A, session)       # not even the session id
        view = self.assert_restricted(r, 'send_ledger_unavailable')
        self.assertEqual(view['send_id'], send_id)

    def test_readable_reset(self):
        _, ident, _ = self.completed()
        self.revoke()
        reset = self.a.post('/chat/sends/ledger/reset', {'confirm': csr.RESET_CONFIRMATION})
        self.assertEqual(reset.status_code, 200, reset.text)
        generation = self.a.bootstrap()['generation']
        r = self.op(ident)
        self.assert_no_text(r.text, OWNER, REPLY_A)
        self.assert_restricted(r, 'send_record_unavailable')
        self.assertEqual(self.a.bootstrap()['generation'], generation)       # the read reset nothing

    def test_readable_reset_authorised_is_restricted_too(self):
        """Even with the binding unchanged, a send the ledger no longer holds cannot be
        re-authorised: its links are gone, so content is not shown from memory."""
        _, ident, _ = self.completed()
        self.a.post('/chat/sends/ledger/reset', {'confirm': csr.RESET_CONFIRMATION})
        r = self.op(ident)
        self.assert_no_text(r.text, OWNER, REPLY_A)
        self.assert_restricted(r, 'send_record_unavailable')

    def test_receipt_pruning(self):
        _, ident, send_id = self.completed()
        self.revoke()
        svc = next(iter(self.a.app.state.chat_sends._services.values()))
        pruned, _ = svc.prune(now=time.time() + cs.RETENTION + 60)
        self.assertEqual(pruned, 1)
        r = self.op(ident)
        self.assert_no_text(r.text, OWNER, REPLY_A)
        self.assert_restricted(r, 'send_record_unavailable')

    def test_other_profile_is_404_even_with_the_ledger_lost(self):
        _, ident, _ = self.completed()
        self.id_file().rename(self.id_file().with_suffix('.away'))
        self.a.bootstrap('rowan')
        self.assertEqual(self.op(ident, 'rowan').status_code, 404)

    def test_genuine_legacy_operation_and_unknown_id(self):
        """Controls: a legacy chat operation keeps its full row; an unknown id is 404, not
        'unavailable' (nothing claims a send exists or never existed without a record). The
        legacy path answers an unknown id with 400 'Unknown operation'; that is kept."""
        self.a.bootstrap()
        ops = self.a.app.state.operations
        ident = ops.submit(str(self.a.root), 'Chat with Nova', lambda report: {'response': 'Legacy reply 4242'},
                           profile='nova', kind='chat')['id']
        wait_for(lambda: ops.rows[ident]['status'] == 'complete')
        row = self.op(ident).json()
        self.assertEqual((row['status'], row['result']['response']), ('complete', 'Legacy reply 4242'))
        unknown = self.op('0' * 32)                  # the existing legacy answer, unchanged
        self.assertEqual((unknown.status_code, unknown.json().get('detail')), (400, 'Unknown operation'))


@unittest.skipUnless(LINUX, POSIX_ONLY)
class F2PublicStream(Base):
    """The keyed operation view carries an authorised, bounded snapshot of the public stream
    while the turn runs; no text reaches the operation file."""

    def running_view(self, ident, want):
        def seen():
            v = self.op(ident).json()
            return v if (v.get('stream') or {}).get('text') == want else None
        view = wait_for(seen, 30)
        self.assertIsNotNone(view, f'stream never reached {want!r}: {self.op(ident).json()}')
        return view

    def test_snapshot_grows_and_is_not_append_only(self):
        self.steps(REPLY_A, REPLY_B, REPLY_C)
        ident, send_id = self.start()
        first = self.running_view(ident, REPLY_A)
        self.assertEqual((first['status'], first['stream_text'], first['stream']['truncated']),
                         ('running', REPLY_A, False))
        again = self.op(ident).json()
        self.assertEqual(again['stream']['text'], REPLY_A)                   # a snapshot, not a replay
        self.assert_no_text(self.op_file(ident).read_text(), OWNER, REPLY_A)  # mid-turn file
        self.go(1)
        second = self.running_view(ident, REPLY_A + REPLY_B)
        self.assertTrue(second['stream']['text'].startswith(first['stream']['text']))
        self.go(2)
        self.a.settle(send_id)
        done = self.op(ident).json()
        self.assertEqual(done['status'], 'complete')
        self.assertNotIn('stream', done)
        self.assertEqual(done['result']['response'], REPLY_A + REPLY_B + REPLY_C)
        self.assert_no_text(self.op_file(ident).read_text(), OWNER, REPLY_A, REPLY_B, REPLY_C)

    def test_failure_file_holds_no_text(self):
        self.steps(REPLY_A, REPLY_B, exit=1)
        ident, send_id = self.start()
        self.running_view(ident, REPLY_A)
        self.go(1)
        self.a.settle(send_id)
        self.assert_no_text(self.op_file(ident).read_text(), OWNER, REPLY_A, REPLY_B)

    def test_revocation_withholds_the_next_read(self):
        self.steps(REPLY_A, REPLY_B)
        ident, send_id = self.start()
        self.running_view(ident, REPLY_A)
        self.revoke()
        r = self.op(ident)
        self.assert_no_text(r.text, REPLY_A)
        self.assertEqual(r.json()['stream'], {'available': False, 'reason': 'not_authorised'})
        self.go(1)
        self.a.settle(send_id)

    def test_other_profile_and_lost_ledger(self):
        self.steps(REPLY_A, REPLY_B)
        ident, send_id = self.start()
        self.running_view(ident, REPLY_A)
        self.a.bootstrap('rowan')
        other = self.op(ident, 'rowan')
        self.assertEqual(other.status_code, 404)
        self.assert_no_text(other.text, REPLY_A)
        away = self.id_file().with_suffix('.away')
        self.id_file().rename(away)
        lost = self.op(ident)
        self.assert_no_text(lost.text, REPLY_A)
        self.assert_restricted(lost, 'send_ledger_unavailable')
        away.rename(self.id_file())
        self.go(1)
        self.a.settle(send_id)

    def test_reasoning_markup_never_leaves_the_server(self):
        self.steps('<think>Private plan 9090</think>', REPLY_A, '<reasoning>Half 8080', REPLY_B)
        ident, send_id = self.start()
        self.go(1)
        view = self.running_view(ident, REPLY_A)
        self.assert_no_text(view, 'Private plan 9090')
        self.go(2)
        wait_for(lambda: '8080' in json.dumps(self.a.app.state.operations.rows[ident]), 10)
        partial = self.op(ident).json()
        self.assertEqual(partial['stream']['text'], REPLY_A)                 # an unclosed block is withheld
        self.go(3)
        self.a.settle(send_id)

    def test_after_restart_a_partial_stream_is_not_fabricated(self):
        """A second app over the same state (the first still running the turn): the ledger
        says running, the stream is honestly unavailable, nothing is relaunched."""
        self.steps(REPLY_A, REPLY_B)
        ident, send_id = self.start()
        self.running_view(ident, REPLY_A)
        other = build(self.a.root, token='t', state_dir=self.a.state,
                      chat_sends=csr.Options(executor=self.a.executor, turn_timeout=120, stop_grace=1.0,
                                             watchdog_interval=0.1))
        self.addCleanup(other.state.chat_sends.close)
        client = TestClient(other)
        r = client.get('/api/operations/' + ident, params={'profile': 'nova'}, headers={'x-companion-token': 't'})
        self.assertEqual((r.status_code, r.json()['status']), (200, 'running'))
        self.assertEqual(r.json()['stream'], {'available': False, 'reason': 'not_retained'})
        self.assert_no_text(r.text, REPLY_A)
        self.go(1)
        self.a.settle(send_id)
        self.assertEqual(self.a.launches(send_id), 1)


@unittest.skipUnless(LINUX, POSIX_ONLY)
class F3ReceiptPaths(Base):
    """Direct receipt, key lookup, replay response, open receipts and the operation view's
    embedded receipt agree under the same current binding."""

    def fields(self, receipt):
        return {k: receipt.get(k, '<absent>') for k in (*LINK_FIELDS, 'send_id', 'state')}

    def test_completed_turn_all_paths_agree_then_all_withhold(self):
        body, accepted, _ = self.a.send(OWNER)
        send_id, ident = accepted['send']['send_id'], accepted['operation']['id']
        direct = self.a.get(f'/chat/sends/{send_id}').json()
        self.assertEqual(direct['links'], 'linked')
        self.assertIsNotNone(direct['owner_message_id'])
        self.assertEqual(len(direct['reply_message_ids']), 1)
        paths = lambda: {
            'direct': self.a.get(f'/chat/sends/{send_id}').json(),
            'lookup': self.a.get('/chat/sends', key=body['client_key']).json(),
            'replay': self.a.post('/chat/sends', body).json()['send'],
            'operation': self.op(ident).json()['send'],
        }
        for name, receipt in paths().items():
            with self.subTest(path=name, binding='current'):
                self.assertEqual(self.fields(receipt), self.fields(direct))
        self.revoke()
        for name, receipt in paths().items():
            with self.subTest(path=name, binding='revoked'):
                for key in LINK_FIELDS:
                    self.assertNotIn(key, receipt)
        self.assertEqual(self.a.launches(send_id), 1)

    def test_open_receipts_for_a_paused_unsettled_turn(self):
        """Links are recorded when the controller resolves an outcome, not mid-generation, so a
        paused `generating` turn has none (by design). The deterministic unsettled turn WITH
        links is a finished turn whose process group still has a live member: the outcome
        and links are recorded, settlement waits for quiescence."""
        pid_file = self.a.tmp / 'child.pid'
        self.a.scenario(child='group', child_pid_file=str(pid_file))
        ident, send_id = self.start()
        direct = wait_for(lambda: (lambda d: d if d.get('owner_message_id') and not d['settled'] else None)(
            self.a.get(f'/chat/sends/{send_id}').json()), 30)
        self.assertIsNotNone(direct, 'no unsettled receipt with links appeared')
        try:
            listed = self.a.get('/chat/sends', open=1).json()['sends']
            self.assertEqual([s['send_id'] for s in listed], [send_id])
            self.assertEqual(self.fields(listed[0]), self.fields(direct))
            self.assertEqual(listed[0]['links'], 'linked')
            self.revoke()
            for key in LINK_FIELDS:
                self.assertNotIn(key, self.a.get('/chat/sends', open=1).json()['sends'][0])
        finally:
            try:
                os.kill(int(pid_file.read_text()), 9)
            except (OSError, ValueError):
                pass
        self.a.settle(send_id)

    def test_two_profiles_same_key_and_lost_response_retry(self):
        key = cs.new_ulid()
        nova_body = self.a.body(OWNER, key=key)
        self.a.post('/chat/sends', nova_body)                      # response "lost"
        found = self.a.get('/chat/sends', key=key).json()
        n = found['send_id']
        self.assertEqual(self.a.post('/chat/sends', nova_body).status_code, 200)
        self.a.settle(n)
        _, rowan, _ = self.a.send(OWNER, profile='rowan', key=key)
        r = rowan['send']['send_id']
        for profile, send_id in (('nova', n), ('rowan', r)):
            with self.subTest(profile=profile):
                direct = self.a.get(f'/chat/sends/{send_id}', profile).json()
                looked = self.a.get('/chat/sends', profile, key=key).json()
                self.assertEqual(self.fields(looked), self.fields(direct))
                self.assertEqual(looked['links'], 'linked')
        nova_ids = {self.a.get('/chat/sends', key=key).json()['owner_message_id']}
        rowan_ids = {m['message_id'] for m in self.a.snapshot('rowan')['messages']}
        self.assertFalse(nova_ids & rowan_ids)
        self.assertEqual((self.a.launches(n), self.a.launches(r, 'rowan')), (1, 1))


class PublicStreamUnit(unittest.TestCase):
    """The server-side boundary for the snapshot text (no processes)."""

    def test_bounded_tail_and_markup(self):
        text, truncated = csr.public_stream('x' * (csr.STREAM_LIMIT + 10) + 'END')
        self.assertEqual((len(text), text[-3:], truncated), (csr.STREAM_LIMIT, 'END', True))
        self.assertEqual(csr.public_stream('Hi <think>plan</think>there'), ('Hi there', False))
        self.assertEqual(csr.public_stream('Hi <THINKING>open plan'), ('Hi ', False))
        self.assertEqual(csr.public_stream('Hi <thi'), ('Hi ', False))           # a tag being streamed
        self.assertEqual(csr.public_stream('a < b'), ('a < b', False))           # ordinary text kept
        self.assertEqual(csr.public_stream('x <b>y</b>'), ('x <b>y</b>', False))


if __name__ == '__main__':
    unittest.main()
