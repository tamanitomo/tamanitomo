"""Phase 1B C1 core against the PINNED Hermes (0e9fc2cc15) and tests/mock_provider.py.

These are the cases C1 acceptance relies on. They run in the designated lane,
tools/pinned_hermes_lane.py, which exports and blob-verifies the pinned tree, records
the interpreter and import origins, and sets TAMANITOMO_C1_REQUIRE_PINNED=1 so that a
missing prerequisite FAILS here instead of skipping. In an ordinary run without that
configuration they skip with the reason printed.

Every Hermes process runs in a fresh synthetic HOME/HERMES_HOME with PATH=/usr/bin:/bin,
a local mock provider (random token, fallbacks disabled). No live profile, credential,
model or platform message is touched. Nothing here is reachable from an app route.
"""
import json
import os
import pathlib
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from tests.phase1b_c1 import harness as h, pinned_lane as pl    # noqa: E402
from kit.app import chat_sends as cs                            # noqa: E402
from kit.app import send_protocol as sp                         # noqa: E402
from mock_provider import MockProvider                          # noqa: E402

INJECT = HERE / 'phase1b_c1' / 'inject'
INJECT_PROVENANCE = HERE / 'phase1b_c1' / 'inject_provenance'


def state_rows(home):
    path = pathlib.Path(home) / 'state.db'
    if not path.exists():
        return []
    con = sqlite3.connect(str(path))
    try:
        return [{'row_id': r[0], 'session_id': r[1], 'role': r[2], 'finish_reason': r[3]}
                for r in con.execute('SELECT id, session_id, role, finish_reason FROM messages ORDER BY id')]
    finally:
        con.close()


@unittest.skipUnless(h.LINUX, 'the C1 supervision is established on Linux only (O-8, O-9, O-11)')
class PinnedTurns(unittest.TestCase):

    def setUp(self):
        self.src, self.python = pl.pinned_or_skip(self)
        self.env = h.Env(self)
        self.scope = h.scope_for(self.env.home)
        self.provider = MockProvider().__enter__()
        self.addCleanup(self.provider.__exit__, None, None, None)

    def service(self, scenario='deltas', inject=False, **kw):
        pl.synthetic_home(self.env.home, self.provider, scenario)
        env = pl.executor_env(self.src, self.env.home)
        if inject:
            path = INJECT_PROVENANCE if inject == 'provenance' else INJECT
            env['PYTHONPATH'] = os.pathsep.join([str(path), env['PYTHONPATH']])
        ex = cs.ExecutorSpec(python=self.python, env=env, cwd=str(self.env.home))
        kw.setdefault('turn_timeout', 120)
        kw.setdefault('watchdog_interval', 0.2)
        return self.env.service(ex, **kw)

    def run_send(self, svc, message='A synthetic owner message', session=None, authorize=h.workspace_only):
        body, (status, payload) = h.send(svc, self.scope, message=message, session=session, authorize=authorize)
        self.assertEqual(status, 202)
        deltas = []
        row = svc.launch(payload['send']['send_id'], message, deltas.append)
        return body, row, deltas

    def facts(self, svc, send_id):
        return h.facts(svc, send_id)

    def record(self, name, svc, row, **extra):
        pl.evidence(name, {'row': {k: row[k] for k in ('state', 'owner_turn', 'reply', 'coverage', 'correlation',
                                                       'liveness', 'error_code', 'capability')},
                           'settled': row['settled_at'] is not None,
                           'fact_kinds': [k for k, _ in self.facts(svc, row['send_id'])],
                           'provider_requests': list(self.provider.requests),
                           'state_rows': state_rows(self.env.home), **extra})

    def assert_exact_cover(self, svc, row, before=()):
        """Receipted rows == the rows committed in the send's sessions during this send
        (`before` = rows that existed when it was accepted), no row twice."""
        receipted = [(r['session_id'], r['row_id']) for k, d in self.facts(svc, row['send_id'])
                     if k == 'write_committed' for r in d['rows']]
        self.assertEqual(len(receipted), len(set(receipted)))
        sessions = {s for s, _ in receipted}
        committed = {(r['session_id'], r['row_id']) for r in state_rows(self.env.home)
                     if r['session_id'] in sessions} - set(before)
        self.assertEqual(set(receipted), committed)

    # --- the connected path -------------------------------------------------------------------

    def test_fresh_turn_completes_and_the_same_key_replays(self):
        """bootstrap -> accept -> go/S2 -> pinned turn -> commit receipts -> finish -> quiescence ->
        settlement -> same-key replay. M-1, M-11 (launch and provider counters kept apart)."""
        svc = self.service('deltas')
        body, row, deltas = self.run_send(svc)
        self.record('fresh_turn', svc, row, deltas=len(deltas))
        self.assertEqual((row['state'], row['owner_turn'], row['reply'], row['coverage'], row['liveness']),
                         ('complete', 'recorded', 'final', 'complete', 'quiescent'))
        self.assertIsNotNone(row['settled_at'])
        self.assertTrue(deltas)
        self.assert_exact_cover(svc, row)
        receipt = svc.receipt(self.scope, row['send_id'], authorized_kinds={'workspace'})
        self.assertEqual([s['created_here'] for s in receipt['hermes_sessions']], [True])
        rows = state_rows(self.env.home)
        self.assertEqual(receipt['source_links']['owner'], [[rows[0]['session_id'], rows[0]['row_id']]])
        requests = len(self.provider.requests)
        status, again = svc.accept(self.scope, body, h.workspace_only)
        self.assertEqual((status, again['send']['state']), (200, 'complete'))
        self.assertEqual([k for k, _ in self.facts(svc, row['send_id'])].count('executor_started'), 1)
        self.assertEqual(len(self.provider.requests), requests)            # nothing re-sent to the provider
        # M-23 privacy leg on a real turn: no owner or reply text anywhere in the send-ledger directory.
        from mock_provider import PUBLIC_TEXT
        for path in svc.dir.rglob('*'):
            if path.is_file():
                data = path.read_bytes()
                self.assertNotIn(body['message'].encode(), data, path)
                self.assertNotIn(PUBLIC_TEXT.encode(), data, path)
                self.assertNotIn(b'kettle', data, path)

    def test_resumed_session_is_not_created_here(self):
        """M-18a (workspace leg): the resumed session keeps created_here=false."""
        svc = self.service('deltas')
        _, first, _ = self.run_send(svc)
        session = svc.receipt(self.scope, first['send_id'])['hermes_sessions'][0]['session_id']
        before = {(r['session_id'], r['row_id']) for r in state_rows(self.env.home)}
        _, row, _ = self.run_send(svc, message='A second synthetic message', session=session,
                                  authorize=h.resume_any('workspace'))
        self.record('resume_turn', svc, row)
        self.assertEqual((row['state'], row['owner_turn'], row['reply']), ('complete', 'recorded', 'final'))
        receipt = svc.receipt(self.scope, row['send_id'], authorized_kinds={'workspace'})
        self.assertEqual(receipt['hermes_sessions'], [{'session_id': session, 'created_here': False}])
        self.assertEqual({s for s, _ in receipt['source_links']['owner']}, {session})
        self.assert_exact_cover(svc, row, before)

    def test_a_provider_retry_inside_one_turn_is_one_launch(self):
        """M-11: the `recover` scenario drops the first provider request; Hermes retries inside
        the same executor. Launch counter 1, provider counter >= 2.

        Two paths were observed on the pinned code, depending on which request the single drop
        hits. (a) An auxiliary non-stream request is dropped: one owner row, one final reply,
        `complete`. (b) The main stream is dropped mid-reply: Hermes stores the partial reply
        (`length`), then a role=user continuation note with NO structural marker, then the final
        reply. The executor's provenance (O-12) names that exact committed row as internal, so the
        owner turn is the one real owner row and the turn completes."""
        svc = self.service('recover')
        _, row, _ = self.run_send(svc)
        users = [r for r in state_rows(self.env.home) if r['role'] == 'user']
        path = 'single_owner_row' if len(users) == 1 else 'continuation_note_row'
        self.record('provider_retry_turn', svc, row, path=path)
        self.assertEqual([k for k, _ in self.facts(svc, row['send_id'])].count('executor_started'), 1)
        self.assertGreaterEqual(len([r for r in self.provider.requests if r[0] == 'recover']), 2)
        if path == 'single_owner_row':
            self.assertEqual((row['state'], row['owner_turn'], row['reply']), ('complete', 'recorded', 'final'))
        else:
            self.assertEqual(len(users), 2)
            self.assertEqual((row['state'], row['owner_turn'], row['reply']), ('complete', 'recorded', 'final'))
            receipt = svc.receipt(self.scope, row['send_id'])
            self.assertEqual(receipt['internal_rows'], [[users[1]['session_id'], users[1]['row_id']]])
        self.assertIsNotNone(row['settled_at'])

    def test_a_dropped_main_stream_adds_an_unmarked_user_row(self):
        """O-12: the main reply stream dropped mid-reply. The pinned Hermes stores the partial reply,
        then a role=user continuation note with no display_kind, observed or summary marker, then
        the retried reply. The executor records provenance for exactly that committed row (the
        dict Hermes created with `_length_continuation_nudge`, matched by identity, not text), so
        it is internal, the owner turn is the real owner row, and a same-key retry replays."""
        svc = self.service('recover_stream')
        body, row, _ = self.run_send(svc)
        rows = state_rows(self.env.home)
        self.record('dropped_main_stream_turn', svc, row)
        self.assertEqual([(r['role'], r['finish_reason']) for r in rows],
                         [('user', None), ('assistant', 'length'), ('user', None), ('assistant', 'stop')])
        committed = [r for k, d in self.facts(svc, row['send_id']) if k == 'write_committed' for r in d['rows']]
        self.assertEqual([r['class'] for r in committed if r['role'] == 'user'], ['user_turn', 'user_turn'])
        provenance = [d for k, d in self.facts(svc, row['send_id']) if k == 'row_provenance']
        self.assertEqual([n['row_id'] for d in provenance for n in d['rows']], [rows[2]['row_id']])
        self.assertEqual((row['state'], row['owner_turn'], row['reply'], row['correlation']),
                         ('complete', 'recorded', 'final', 'linked'))
        receipt = svc.receipt(self.scope, row['send_id'], authorized_kinds={'workspace'})
        self.assertEqual(receipt['internal_rows'], [[rows[2]['session_id'], rows[2]['row_id']]])
        self.assertEqual(receipt['source_links']['owner'], [[rows[0]['session_id'], rows[0]['row_id']]])
        self.assertEqual([k for k, _ in self.facts(svc, row['send_id'])].count('executor_started'), 1)
        status, again = svc.accept(self.scope, body, h.workspace_only)
        self.assertEqual((status, again['send']['state'], again['send']['internal_rows']),
                         (200, 'complete', receipt['internal_rows']))

    def test_an_owner_message_equal_to_the_note_text_is_still_owner_speech(self):
        """O-12 control: the owner may type the note's exact words. With no provenance for that
        row it stays owner evidence; nothing is excluded by text."""
        stub = ('[System: The previous response was cut off by a network error mid-stream. Continue exactly '
                'where you left off. Do not restart or repeat prior text. Finish the answer directly.]')
        svc = self.service('deltas')
        _, row, _ = self.run_send(svc, message=stub)
        self.record('equal_text_owner_turn', svc, row)
        self.assertEqual((row['state'], row['owner_turn'], row['reply']), ('complete', 'recorded', 'final'))
        self.assertEqual(svc.receipt(self.scope, row['send_id'])['internal_rows'], [])

    def test_a_note_without_its_provenance_stays_conservative(self):
        """O-12 interrupted delivery: the provenance fact cannot be written. The note is then a
        possible owner row: owner_turn=ambiguous, never complete."""
        svc = self.service('recover_stream', inject='provenance')
        _, row, _ = self.run_send(svc)
        self.record('note_without_provenance_turn', svc, row)
        self.assertNotIn('row_provenance', [k for k, _ in self.facts(svc, row['send_id'])])
        self.assertEqual((row['state'], row['owner_turn'], row['reply'], row['error_code']),
                         ('unknown', 'ambiguous', 'partial', 'owner_turn_not_established'))

    def test_truncated_and_disconnected_replies_fail_as_incomplete(self):
        """M-9: the pinned CLI exits 0 with a finish_reason='length' row."""
        for scenario in ('truncated', 'disconnect_before_done'):
            with self.subTest(scenario=scenario):
                env = h.Env(self)
                self.env, self.scope = env, h.scope_for(env.home)
                svc = self.service(scenario)
                _, row, _ = self.run_send(svc)
                self.record(f'{scenario}_turn', svc, row)
                self.assertEqual((row['state'], row['error_code'], row['reply'], row['owner_turn']),
                                 ('failed', 'reply_incomplete', 'partial', 'recorded'))
                finished = [d for k, d in self.facts(svc, row['send_id']) if k == 'executor_finished'][0]
                self.assertEqual(finished['exit'], 0)

    def test_provider_error_before_the_first_byte(self):
        svc = self.service('error_before_first_byte')
        _, row, _ = self.run_send(svc)
        self.record('provider_error_turn', svc, row)
        self.assertEqual((row['state'], row['error_code'], row['owner_turn'], row['reply']),
                         ('failed', 'hermes_failed', 'recorded', 'none'))
        self.assertIsNotNone(row['settled_at'])

    def test_stop_during_a_stream_is_interrupted(self):
        """M-12: stop flag -> executor watchdog -> interrupt_main -> exit 130; no partial row claimed."""
        svc = self.service('hang')
        body, (_, payload) = h.send(svc, self.scope)
        send_id, result = payload['send']['send_id'], {}
        deltas = []
        t = threading.Thread(target=lambda: result.update(row=svc.launch(send_id, body['message'], deltas.append)))
        t.start()
        end = time.monotonic() + 60
        while not deltas and time.monotonic() < end:
            time.sleep(0.05)
        self.assertTrue(deltas, 'the hang scenario never streamed')
        svc.stop(self.scope, send_id)
        t.join(90)
        row = result['row']
        self.record('stop_turn', svc, row)
        self.assertEqual((row['state'], row['error_code'], row['owner_turn'], row['liveness']),
                         ('interrupted', 'stopped', 'recorded', 'quiescent'))
        self.assertIn(row['reply'], ('none', 'partial'))
        self.assertIn('stop_seen', [k for k, _ in self.facts(svc, send_id)])

    def test_deadline_interrupts_a_hung_turn(self):
        """M-13 (timeout shortened by the test)."""
        svc = self.service('hang', turn_timeout=6.0, stop_grace=10.0)
        _, row, _ = self.run_send(svc)
        self.record('deadline_turn', svc, row)
        self.assertEqual((row['state'], row['error_code'], row['liveness']), ('interrupted', 'timeout', 'quiescent'))

    def test_controller_death_mid_turn_then_recovery(self):
        """M-8: the executor keeps running on POSIX; a new controller supervises it through the
        lock and facts; one launch."""
        pl.synthetic_home(self.env.home, self.provider, 'delayed_first_delta')
        ex = cs.ExecutorSpec(python=self.python, env=pl.executor_env(self.src, self.env.home), cwd=str(self.env.home))
        key = cs.new_ulid()
        out, cfg = self.env.root / 'ctl.json', self.env.root / 'cfg.json'
        cfg.write_text(json.dumps({'home': str(self.env.home), 'state': str(self.env.state), 'kill_at': 'generating',
                                   'key': key, 'message': 'A synthetic owner message', 'out': str(out),
                                   'turn_timeout': 120, 'poll': 0.2,
                                   'executor': {'python': ex.python, 'env': ex.env, 'cwd': ex.cwd}}))
        proc = subprocess.run([sys.executable, str(HERE / 'phase1b_c1' / 'controller_proc.py'), str(cfg)],
                              cwd=str(HERE.parent), capture_output=True, timeout=120)
        self.assertEqual(proc.returncode, -signal.SIGKILL, proc.stderr.decode()[-2000:])
        svc = self.env.service(ex)
        send_id = json.loads(out.read_text())['send_id']
        row = svc.watch(send_id, timeout=90)
        self.record('controller_death_turn', svc, row)
        self.assertEqual((row['state'], row['owner_turn'], row['reply'], row['liveness']),
                         ('complete', 'recorded', 'final', 'quiescent'))
        self.assertIn('recovery', [k for k, _ in self.facts(svc, send_id)])
        self.assertEqual([k for k, _ in self.facts(svc, send_id)].count('executor_started'), 1)

    def test_receipt_gap_in_a_real_turn(self):
        """O-F with the real exception path: the owner-row receipt fails after Hermes committed
        it. The committed write is not failed back into Hermes; later writes are refused before
        they start; the send is never complete; quiescence recovery still settles it."""
        svc = self.service('deltas', inject=True)
        _, row, _ = self.run_send(svc)
        kinds = [k for k, _ in self.facts(svc, row['send_id'])]
        self.record('receipt_gap_turn', svc, row)
        self.assertIn('receipt_gap', kinds)
        self.assertNotEqual(row['state'], 'complete')
        # Observed: the pinned CLI still exits 0 after its reply write was refused, so exit 0
        # is again not evidence of a persisted reply; the receipt stays `unknown`.
        self.assertEqual((row['state'], row['error_code']), ('unknown', 'receipts_incomplete'))
        self.assertEqual((row['owner_turn'], row['reply'], row['coverage']), ('unknown', 'unknown', 'incomplete'))
        self.assertIsNotNone(row['settled_at'])
        roles = [r['role'] for r in state_rows(self.env.home)]
        self.assertEqual(roles.count('user'), 1)                        # committed, not failed back
        self.assertNotIn('assistant', roles)                             # refused after the gap
        finished = [d for k, d in self.facts(svc, row['send_id']) if k == 'executor_finished']
        self.assertEqual([f['receipts_complete'] for f in finished], [False])


@unittest.skipUnless(h.LINUX, 'the C1 supervision is established on Linux only (O-8, O-9, O-11)')
class PinnedSeams(unittest.TestCase):
    """The production recorder on the real pinned SessionDB, for paths a CLI turn in this lane
    does not reach. SessionDB-level evidence; it does not certify a full compressed CLI turn."""

    def setUp(self):
        self.src, self.python = pl.pinned_or_skip(self)
        self.env = h.Env(self)
        self.scope = h.scope_for(self.env.home)
        self.svc = self.env.service(h.fake_executor(self.env.home))

    def seam(self, scenario):
        _, (_, payload) = h.send(self.svc, self.scope)
        send_id = payload['send']['send_id']
        con = sp.connect(self.svc.db)
        with sp.immediate(con):
            self.svc._cas(con, send_id, 'accepted', 1, 'test', state='launching', launch_token='T',
                          attempt_id='a' * 32)
            sp.insert_fact(con, send_id, 'T', 'executor_started',
                           {'pid': 1, 'pgid': 1, 'lock_identity': [0, 0], 'attempt_id': 'a' * 32})
            self.svc._cas(con, send_id, 'launching', 1, 'test', state='generating')
        con.close()
        work = self.env.root / 'seam'
        work.mkdir()
        proc = subprocess.run([self.python, str(HERE / 'phase1b_c1' / 'pinned_seams.py'), str(self.svc.db), send_id,
                               'T', scenario, str(work)], env=pl.executor_env(self.src, work), cwd=str(work),
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
        out = json.loads(proc.stdout.strip().splitlines()[-1])
        con = sp.connect(self.svc.db, readonly=True)
        try:
            row = self.svc._row(con, send_id=send_id)
            facts = self.svc._facts(con, send_id)
        finally:
            con.close()
        derived = cs.derive(row, facts)
        pl.evidence(f'seam_{scenario}', {'driver': out, 'fact_kinds': [f['kind'] for f in facts],
                                         'derived': {k: getattr(derived, k) for k in
                                                     ('coverage', 'owner_turn', 'reply', 'outcome', 'sessions')}})
        return out, facts, derived

    def test_compression_clone_then_death_is_unknown_not_absent(self):
        """Review R3 5.2: real publish_compression_child (a direct session insert plus an
        INSERT ... SELECT clone) followed by executor death."""
        out, facts, derived = self.seam('clone_then_death')
        self.assertIsNone(out['error'])
        committed = [f['data'] for f in facts if f['kind'] == 'write_committed']
        self.assertTrue(any(c['unidentified'] for c in committed))
        self.assertIn({'session_id': 'c1-child', 'created_here': True}, derived.sessions)
        self.assertEqual((derived.coverage, derived.owner_turn, derived.reply), ('incomplete', 'unknown', 'unknown'))

    def test_receipt_gap_after_a_real_commit(self):
        out, facts, derived = self.seam('gap_after_owner_commit')
        self.assertIsNone(out['error'])
        self.assertEqual(out['later_write'], 'refused')
        self.assertEqual([r[2] for r in out['state_rows']], ['user'])
        self.assertIn('receipt_gap', [f['kind'] for f in facts])
        self.assertEqual(derived.owner_turn, 'unknown')

    def test_hidden_and_summary_owner_rows_are_not_owner_evidence(self):
        """Review R3 5.2 negative controls on the real SessionDB."""
        out, facts, derived = self.seam('hidden_and_summary_owner_rows')
        self.assertIsNone(out['error'])
        classes = [r['class'] for f in facts if f['kind'] == 'write_committed' for r in f['data']['rows']]
        self.assertEqual(classes, ['user_internal', 'user_internal', 'public_output'])
        self.assertEqual(derived.owner_turn, 'absent')


if __name__ == '__main__':
    unittest.main()
