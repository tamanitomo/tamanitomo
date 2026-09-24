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


def sp_live_members(pgid):
    """Live processes in a process group, from /proc (the same question quiescence asks)."""
    out = []
    for entry in pathlib.Path('/proc').iterdir():
        if entry.name.isdigit():
            facts = proc_facts(entry.name)
            if facts['alive'] and facts['pgid'] == pgid:
                out.append(int(entry.name))
    return out


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
class PinnedHttp(unittest.TestCase):
    """The C1 integration through the app (review R5 section 5) with the PINNED Hermes and the mock
    provider: keyed HTTP acceptance, execution, receipt/operation, the Phase 1A reads with the
    send join, and the O-12 read-side exclusion of the real continuation note."""

    STUB = ('[System: The previous response was cut off by a network error mid-stream. Continue exactly '
            'where you left off. Do not restart or repeat prior text. Finish the answer directly.]')

    def setUp(self):
        self.src, self.python = pl.pinned_or_skip(self)
        self.provider = MockProvider().__enter__()
        self.addCleanup(self.provider.__exit__, None, None, None)

    def app(self, scenario, inject=False):
        from tests.test_phase1b_c1_integration import App

        def executor(rt, home):
            env = pl.executor_env(self.src, home)
            if inject:
                env['PYTHONPATH'] = os.pathsep.join([str(INJECT_PROVENANCE), env['PYTHONPATH']])
            return cs.ExecutorSpec(python=self.python, env=env, cwd=str(home))
        a = App(self, executor=executor)
        pl.synthetic_home(a.home(), self.provider, scenario)
        return a

    def reads(self, a):
        snap = a.snapshot()
        first = a.get('/chat/snapshot', limit=1).json()
        older = a.get('/chat/history', before=first['history']['before'], limit=200).json() \
            if first['history']['before'] else {'messages': []}
        return snap, older

    def test_http_fresh_turn_links_reads_and_replays(self):
        a = self.app('deltas')
        before = a.snapshot()
        body, accepted, receipt = a.send()
        send_id = accepted['send']['send_id']
        rows = state_rows(a.home())
        pl.evidence('http_fresh_turn', {'receipt': {k: receipt[k] for k in ('state', 'owner_turn', 'reply', 'links')},
                                        'state_rows': rows, 'provider_requests': list(self.provider.requests)})
        self.assertEqual((receipt['state'], receipt['owner_turn'], receipt['reply'], receipt['links']),
                         ('complete', 'recorded', 'final', 'linked'))
        snap = a.snapshot()
        parts = {m['message_id']: m['correlation']['send_part'] for m in snap['messages'] if m['correlation']}
        self.assertEqual(parts[receipt['owner_message_id']], 'owner')
        self.assertEqual({m['source']['kind'] for m in snap['messages']}, {'workspace'})
        changes = a.get('/chat/changes', after=before['changes']['after']).json()
        self.assertEqual(len(changes['changes']), len(rows))
        requests = len(self.provider.requests)
        again = a.post('/chat/sends', body)
        self.assertEqual((again.status_code, again.json()['send']['send_id']), (200, send_id))
        self.assertEqual((a.launches(send_id), len(self.provider.requests)), (1, requests))
        op = a.get('/operations/' + accepted['operation']['id']).json()
        self.assertEqual((op['status'], op['result']['content_retained']), ('complete', True))

    def test_http_dropped_stream_note_is_excluded_from_reads(self):
        """O-12 read side on the real note: snapshot, history and changes never carry it; the
        owner row is the real owner row; the send completes."""
        a = self.app('recover_stream')
        before = a.snapshot()
        body, accepted, receipt = a.send()
        rows = state_rows(a.home())
        self.assertEqual([(r['role'], r['finish_reason']) for r in rows],
                         [('user', None), ('assistant', 'length'), ('user', None), ('assistant', 'stop')])
        note = rows[2]
        snap, older = self.reads(a)
        changes = a.get('/chat/changes', after=before['changes']['after']).json()
        pl.evidence('http_dropped_stream_reads', {
            'receipt': {k: receipt[k] for k in ('state', 'owner_turn', 'reply', 'links')},
            'snapshot_sources': [m['source']['message'] for m in snap['messages']],
            'excluded': snap['excluded'], 'note_row': note['row_id']})
        self.assertEqual((receipt['state'], receipt['owner_turn'], receipt['reply']), ('complete', 'recorded', 'final'))
        for page in (snap['messages'], older['messages'], [c['message'] for c in changes['changes']]):
            self.assertNotIn(str(note['row_id']), {m['source']['message'] for m in page})
        owners = [m for m in snap['messages'] if m['speaker'] == 'owner']
        self.assertEqual([(m['content'], m['source']['message']) for m in owners],
                         [(body['message'], str(rows[0]['row_id']))])
        self.assertEqual(snap['excluded'].get('internal_turn_machinery'), 1)

    def test_http_owner_text_equal_to_the_note_stays_owner_speech(self):
        a = self.app('deltas')
        _, _, receipt = a.send(self.STUB)
        snap = a.snapshot()
        owners = [m for m in snap['messages'] if m['speaker'] == 'owner']
        self.assertEqual([m['content'] for m in owners], [self.STUB])
        self.assertEqual(owners[0]['correlation']['send_part'], 'owner')
        self.assertEqual(snap['excluded'].get('internal_turn_machinery'), None)

    def test_http_note_without_provenance_reads_as_recorded(self):
        """Failed provenance write: nothing is hidden by guesswork. Both user rows read as the
        session recorded them, and the receipt is not complete (ambiguous owner turn)."""
        a = self.app('recover_stream', inject=True)
        _, _, receipt = a.send()
        self.assertEqual((receipt['state'], receipt['owner_turn']), ('unknown', 'ambiguous'))
        self.assertNotIn('owner_message_id', {k for k, v in receipt.items() if v})
        owners = [m for m in a.snapshot()['messages'] if m['speaker'] == 'owner']
        self.assertEqual(len(owners), 2)
        self.assertTrue(all(m['correlation'] is None for m in owners))


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


def proc_facts(pid):
    """{'alive', 'pgid', 'sid'} for a pid from /proc (zombies are not alive)."""
    try:
        stat = pathlib.Path(f'/proc/{int(pid)}/stat').read_text()
    except (OSError, ValueError):
        return {'alive': False, 'pgid': None, 'sid': None}
    fields = stat.rsplit(')', 1)[1].split()
    return {'alive': fields[0] != 'Z', 'pgid': int(fields[2]), 'sid': int(fields[3])}


def reap(*pids):
    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGKILL)
        except (OSError, ValueError, TypeError):
            pass


def wait_until(pred, timeout=60.0, interval=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = pred()
        if value:
            return value
        time.sleep(interval)
    return None


@unittest.skipUnless(h.LINUX, 'the C1 supervision is established on Linux only (O-8, O-9, O-11)')
class PinnedActivation(unittest.TestCase):
    """Linux activation evidence (continuation handoff 2026-09-24 section 5), pinned Hermes +
    mock provider, synthetic homes. The pinned `terminal` tool runs harmless commands in the
    synthetic home. These tests ASSERT WHAT WAS OBSERVED, including limitations: a passing test
    here that documents an escape is evidence of an OPEN gate, not a closed one."""

    setUp = PinnedTurns.setUp
    service = PinnedTurns.service
    run_send = PinnedTurns.run_send
    facts = PinnedTurns.facts
    record = PinnedTurns.record

    def started(self, svc, send_id):
        return [d for k, d in self.facts(svc, send_id) if k == 'executor_started']

    def lease(self, svc, send_id):
        return h.ledger_rows(svc, 'SELECT count(*) FROM lease WHERE send_id=?', send_id)[0][0]

    def pid_file(self, name, timeout=60):
        path = self.env.home / name
        found = wait_until(lambda: path.exists() and path.read_text().strip(), timeout)
        self.assertTrue(found, f'{name} never appeared')
        pid = int(path.read_text().strip())
        self.addCleanup(reap, pid)
        return pid

    def launch_async(self, svc, scenario, message='A synthetic owner message'):
        body, (status, payload) = h.send(svc, self.scope, message=message)
        self.assertEqual(status, 202)
        send_id, result = payload['send']['send_id'], {}
        t = threading.Thread(target=lambda: result.update(row=svc.launch(send_id, message, lambda d: None)))
        t.start()
        self.addCleanup(t.join, 120)
        return body, send_id, t, result

    # --- a tool-using turn ------------------------------------------------------------------------

    def test_tool_turn_completes_with_tool_rows_excluded(self):
        """The real quiet CLI: tool call -> the pinned terminal tool -> tool result -> final reply.
        Owner/reply correlation, tool rows not owner or reply evidence, completion facts."""
        svc = self.service('tool_echo')
        body, row, deltas = self.run_send(svc)
        rows = state_rows(self.env.home)
        receipt = svc.receipt(self.scope, row['send_id'], authorized_kinds={'workspace'})
        committed = [r for k, d in self.facts(svc, row['send_id']) if k == 'write_committed' for r in d['rows']]
        self.record('tool_turn', svc, row, deltas=len(deltas), committed_classes=[
            (r['role'], r['class']) for r in committed], source_links=receipt['source_links'])
        self.assertEqual([(r['role'], r['finish_reason']) for r in rows],
                         [('user', None), ('assistant', 'tool_calls'), ('tool', None), ('assistant', 'stop')])
        self.assertEqual((self.env.home / 'c1_tool_output.txt').read_text().strip(), 'c1-tool-ok')
        self.assertEqual((row['state'], row['owner_turn'], row['reply'], row['coverage'], row['liveness']),
                         ('complete', 'recorded', 'final', 'complete', 'quiescent'))
        self.assertEqual(receipt['source_links']['owner'], [[rows[0]['session_id'], rows[0]['row_id']]])
        replies = {tuple(r) for r in receipt['source_links']['reply']}
        self.assertIn((rows[3]['session_id'], rows[3]['row_id']), replies)
        self.assertNotIn((rows[2]['session_id'], rows[2]['row_id']), replies)       # the tool row
        self.assertEqual(len(self.started(svc, row['send_id'])), 1)
        self.assertEqual([r[1] for r in self.provider.requests if r[0] == 'tool_echo'].count(True), 2)
        self.assertEqual(svc.accept(self.scope, body, h.workspace_only)[0], 200)
        self.assertEqual(len(self.started(svc, row['send_id'])), 1)

    # --- interruption while the tool process is active --------------------------------------------

    def interrupted_during_tool(self, how):
        kw = {'turn_timeout': 6.0, 'stop_grace': 10.0} if how == 'deadline' else {}
        svc = self.service('tool_sleep', **kw)
        body, send_id, t, result = self.launch_async(svc, 'tool_sleep')
        tool = self.pid_file('c1_tool.pid')
        executor = wait_until(lambda: self.started(svc, send_id), 30)[0]
        during = {'tool': proc_facts(tool), 'executor_pgid': executor['pgid']}
        requests_before = len(self.provider.requests)
        if how == 'stop':
            svc.stop(self.scope, send_id)
            after_request = {'lease': self.lease(svc, send_id),
                             'settled': h.ledger_rows(svc, 'SELECT settled_at FROM sends WHERE send_id=?',
                                                      send_id)[0][0] is not None}
        else:
            after_request = None
        t.join(120)
        row = result['row']
        after = {'tool': proc_facts(tool), 'lease': self.lease(svc, send_id)}
        status, again = svc.accept(self.scope, body, h.workspace_only)
        self.record(f'tool_{how}_turn', svc, row, during=during, after_stop_request=after_request, after=after,
                    launches=len(self.started(svc, send_id)),
                    provider_requests_after_interrupt=len(self.provider.requests) - requests_before,
                    retry_status=status)
        return svc, send_id, row, tool, during, after_request, after, status

    def test_stop_during_a_tool(self):
        svc, send_id, row, tool, during, after_request, after, retry = self.interrupted_during_tool('stop')
        # The tool runs in its own session (pinned local backend: start_new_session=True):
        # outside the executor's managed process group.
        self.assertTrue(during['tool']['alive'])
        self.assertNotEqual(during['tool']['pgid'], during['executor_pgid'])
        # A stop request alone releases nothing.
        self.assertEqual(after_request, {'lease': 1, 'settled': False})
        self.assertEqual((row['state'], row['error_code'], row['liveness']), ('interrupted', 'stopped', 'quiescent'))
        self.assertEqual(after['lease'], 0)
        # Observed: Hermes's own interrupt handling kills the tool's group before the executor
        # exits, so the tool is gone by settlement. (Hermes cleanup, not Tamanitomo containment.)
        self.assertFalse(after['tool']['alive'])
        self.assertEqual((retry, len(self.started(svc, send_id))), (200, 1))

    def test_deadline_during_a_tool(self):
        svc, send_id, row, tool, during, _, after, retry = self.interrupted_during_tool('deadline')
        self.assertNotEqual(during['tool']['pgid'], during['executor_pgid'])
        self.assertEqual((row['state'], row['error_code'], row['liveness']), ('interrupted', 'timeout', 'quiescent'))
        self.assertFalse(after['tool']['alive'])
        self.assertEqual((retry, len(self.started(svc, send_id))), (200, 1))

    def test_executor_killed_during_a_tool_leaves_the_tool_running(self):
        """The case Hermes cannot clean up: the executor process group is SIGKILLed (what the
        supervisor does after the stop grace). The tool, in its own session, survives; the
        managed group is empty, so the send settles while the tool still runs. OPEN GATE."""
        svc = self.service('tool_sleep', stop_grace=0.5)
        body, send_id, t, result = self.launch_async(svc, 'tool_sleep')
        tool = self.pid_file('c1_tool.pid')
        executor = wait_until(lambda: self.started(svc, send_id), 30)[0]
        os.killpg(executor['pgid'], signal.SIGKILL)
        t.join(120)
        row = result['row']
        after = proc_facts(tool)
        self.record('tool_executor_killed_turn', svc, row, tool_after=after, executor_pgid=executor['pgid'],
                    lease=self.lease(svc, send_id))
        self.assertIsNotNone(row['settled_at'])
        self.assertEqual(row['liveness'], 'quiescent')
        self.assertEqual(self.lease(svc, send_id), 0)
        self.assertTrue(after['alive'], 'the tool died with the executor group; update the gate table')
        self.assertEqual(len(self.started(svc, send_id)), 1)

    def test_controller_death_during_a_tool(self):
        """M-8 with a tool active: the controller is SIGKILLed while the tool runs; the executor
        continues; a new controller supervises it to completion; one launch."""
        pl.synthetic_home(self.env.home, self.provider, 'tool_sleep')
        ex = cs.ExecutorSpec(python=self.python, env=pl.executor_env(self.src, self.env.home), cwd=str(self.env.home))
        out, cfg = self.env.root / 'ctl.json', self.env.root / 'cfg.json'
        cfg.write_text(json.dumps({'home': str(self.env.home), 'state': str(self.env.state), 'kill_at': None,
                                   'key': cs.new_ulid(), 'message': 'A synthetic owner message', 'out': str(out),
                                   'turn_timeout': 120, 'poll': 0.2,
                                   'executor': {'python': ex.python, 'env': ex.env, 'cwd': ex.cwd}}))
        ctl = subprocess.Popen([sys.executable, str(HERE / 'phase1b_c1' / 'controller_proc.py'), str(cfg)],
                               cwd=str(HERE.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (ctl.poll() is None and ctl.kill(), ctl.wait()))
        tool = self.pid_file('c1_tool.pid')
        ctl.kill()
        ctl.wait(30)
        send_id = json.loads(out.read_text())['send_id']
        svc = self.env.service(ex)
        mid = {'tool': proc_facts(tool), 'state': h.ledger_rows(svc, 'SELECT state FROM sends WHERE send_id=?',
                                                                  send_id)[0][0],
               'lease': self.lease(svc, send_id)}
        row = svc.watch(send_id, timeout=110)
        self.record('tool_controller_death_turn', svc, row, mid=mid, tool_after=proc_facts(tool))
        self.assertTrue(mid['tool']['alive'])
        self.assertEqual((mid['state'], mid['lease']), ('generating', 1))
        self.assertEqual((row['state'], row['owner_turn'], row['reply'], row['liveness']),
                         ('complete', 'recorded', 'final', 'quiescent'))
        self.assertEqual(len(self.started(svc, send_id)), 1)

    # --- real CLI compression -------------------------------------------------------------------

    def test_real_cli_compression_continuation(self):
        """The actual CLI compression path, not a SessionDB seam: a resumed session with a long
        synthetic history (seeded through the pinned SessionDB), the provider refusing the first
        main request as a context overflow (structured code), Hermes compressing and retrying,
        then replying. Observed on the pinned code: compression rewrites IN PLACE (same session,
        no child), appending copies of history, a summary row and a copy of the owner message.
        Checked: which path ran, receipted rows and classes, owner/reply correlation, and what
        snapshot/history/changes and a projection rebuild show. The receipt side holds; the
        READ side fails (see the assertions): an OPEN GATE, pinned as observed."""
        from tests.test_phase1b_c1_integration import App

        def executor(rt, home):
            return cs.ExecutorSpec(python=self.python, env=pl.executor_env(self.src, home), cwd=str(home))
        a = App(self, executor=executor)
        home = a.home()
        pl.synthetic_home(home, self.provider, 'overflow_once')
        cfg = home / 'config.yaml'
        cfg.write_text(cfg.read_text().replace('model:\n', 'model:\n  context_length: 64000\n'))
        seeded = subprocess.run([self.python, str(HERE / 'phase1b_c1' / 'seed_history.py'), str(home / 'state.db'),
                                 'c1-history', '40', '8000'], env=pl.executor_env(self.src, home), cwd=str(home),
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(seeded.returncode, 0, seeded.stderr[-2000:])
        history = json.loads(seeded.stdout.strip().splitlines()[-1])['rows']
        before = a.snapshot()
        body, accepted, receipt = a.send('A synthetic owner message 6061', session='c1-history')
        send_id = accepted['send']['send_id']
        rows = [r for r in state_rows(home) if r['row_id'] > max(history)]
        con = sqlite3.connect(str(home / 'state.db'))
        try:
            sessions = [list(r) for r in con.execute('SELECT id, source, parent_session_id FROM sessions')]
            texts = {r[0]: r[1] for r in con.execute('SELECT id, content FROM messages WHERE id > ?', (max(history),))}
        finally:
            con.close()
        svc = a.app.state.chat_sends._services[os.path.realpath(home)]
        committed = [r for k, d in h.facts(svc, send_id) if k == 'write_committed' for r in d['rows']]
        classes = {r['row_id']: r['class'] for r in committed}
        requests = [(n, st) for n, st, _ in self.provider.requests]
        snap, older = PinnedHttp.reads(self, a)
        changes = a.get('/chat/changes', after=before['changes']['after']).json()
        new_public = [m for m in snap['messages'] + older['messages'] if int(m['source']['message']) > max(history)]
        pages = {'snapshot': snap['messages'], 'history': older['messages'],
                 'changes': [c['message'] for c in changes['changes']]}
        seen_rows = {name: sorted({int(m['source']['message']) for m in page if int(m['source']['message']) > max(history)})
                     for name, page in pages.items()}
        for path in (a.state / 'chat').rglob('*.sqlite3'):
            path.unlink()
        rebuilt = a.snapshot()
        rebuilt_rows = sorted({int(m['source']['message']) for m in rebuilt['messages']
                               if int(m['source']['message']) > max(history)})
        owner_copies = [r['row_id'] for r in rows if r['role'] == 'user' and texts[r['row_id']] == body['message']]
        pl.evidence('real_compression_turn', {
            'receipt': {k: receipt.get(k) for k in ('state', 'owner_turn', 'reply', 'links', 'session')},
            'sessions': sessions, 'provider_requests': requests,
            'new_rows': [(r['row_id'], r['role'], classes.get(r['row_id'])) for r in rows],
            'owner_text_rows': owner_copies, 'read_rows': seen_rows, 'rebuilt_rows': rebuilt_rows,
            'excluded': snap.get('excluded')})
        # Which path ran: the reactive compression in the real CLI (overflow, then a compressed retry).
        self.assertEqual([st for n, st in requests if n == 'overflow_once'].count(True), 3)
        self.assertEqual(len(sessions), 1)                          # in place: no child session
        owner_row, reply_row = rows[0], rows[-1]
        # Receipt side (holds): one launch; the owner turn is the real owner row; the copies,
        # including a verbatim copy of the owner text, are classified rewrite_copy, never owner
        # or reply evidence; the reply is the final public output.
        self.assertEqual((receipt['state'], receipt['owner_turn'], receipt['reply']), ('complete', 'recorded', 'final'))
        self.assertEqual(owner_copies[0], owner_row['row_id'])
        self.assertGreaterEqual(len(owner_copies), 2)               # the rewrite copied the owner text
        self.assertEqual(classes[owner_row['row_id']], 'user_turn')
        self.assertEqual(classes[reply_row['row_id']], 'public_output')
        for r in rows[1:-1]:
            self.assertEqual(classes.get(r['row_id']), 'rewrite_copy', r)
        self.assertEqual(a.launches(send_id), 1)
        # Read side (OPEN GATE, observed): Hermes deactivates the original rows and appends active
        # copies; the Phase 1A reads follow `active`, so the real owner row reads as deleted (the
        # send's links are `lost`) and the copies read as NEW public messages -- including the
        # copy of the owner text as uncorrelated owner speech. The summary row stays excluded.
        # These assertions pin the observed failure so a fix flips them; they are not a pass.
        copies = [r['row_id'] for r in rows[1:-1] if r['row_id'] not in seen_rows['snapshot'] + seen_rows['history']]
        self.assertEqual(receipt['links'], 'lost')
        self.assertNotIn(owner_row['row_id'], seen_rows['snapshot'] + seen_rows['history'] + seen_rows['changes'])
        self.assertIn(owner_copies[-1], seen_rows['snapshot'])
        self.assertEqual(len(copies), 1)                            # only the summary row is hidden
        self.assertEqual(rebuilt_rows, seen_rows['snapshot'])
        owners = [m for m in new_public if m['speaker'] == 'owner']
        self.assertIn(str(owner_copies[-1]), {m['source']['message'] for m in owners})
        self.assertTrue(all(m['correlation'] is None for m in owners))

    # --- foreign writers -------------------------------------------------------------------------

    def foreign_turn(self, message, session=None, scenario='deltas'):
        """The pinned CLI run directly (NOT through Tamanitomo): an upstream writer that knows
        nothing about the send ledger, its lease or the installation guard."""
        code = 'import sys\nfrom hermes_cli.main import main\nsys.argv = ["hermes", *sys.argv[1:]]\nmain()'
        argv = [self.python, '-c', code, 'chat', '--quiet', '--oneshot', '-q', message, '-m', scenario]
        if session:
            argv += ['--resume', session]
        started = time.monotonic()
        proc = subprocess.run(argv, env=pl.executor_env(self.src, self.env.home), cwd=str(self.env.home),
                              capture_output=True, text=True, timeout=120)
        return {'exit': proc.returncode, 'seconds': round(time.monotonic() - started, 2),
                'stderr_tail': proc.stderr.strip().splitlines()[-3:]}

    def test_foreign_writers_are_never_attributed(self):
        """While a keyed send runs (its provider stream stalled): a second pinned CLI process
        resuming THE SAME session is refused by Hermes's OWN session-owner lease
        (SESSION_NOT_OWNED) -- upstream coordination, not Tamanitomo's lease; an unrelated
        fresh-session turn in the same profile runs freely (control). After settlement, a
        foreign turn in the same session with the SAME owner text is accepted by Hermes. No
        foreign row is ever receipted, linked or counted for the send."""
        svc = self.service('hang')
        message = 'A synthetic owner message 7373'
        body, send_id, t, result = self.launch_async(svc, 'hang', message)
        owner = wait_until(lambda: [r for r in state_rows(self.env.home) if r['role'] == 'user'], 60)
        self.assertTrue(owner, 'the keyed owner row never appeared')
        session = owner[0]['session_id']
        lease_during = self.lease(svc, send_id)
        same_during = self.foreign_turn(message, session=session)
        unrelated = self.foreign_turn('An unrelated synthetic message')
        still_running = t.is_alive()
        t.join(120)
        row = result['row']
        before = svc.receipt(self.scope, send_id, authorized_kinds={'workspace'})
        same_after = self.foreign_turn(message, session=session)
        rows = state_rows(self.env.home)
        receipt = svc.receipt(self.scope, send_id, authorized_kinds={'workspace'})
        receipted = {(r['session_id'], r['row_id']) for k, d in self.facts(svc, send_id) if k == 'write_committed'
                     for r in d['rows']}
        linked = {tuple(x) for part in receipt['source_links'].values() for x in part}
        foreign = [r for r in rows if (r['session_id'], r['row_id']) not in receipted]
        self.record('foreign_writers_turn', svc, row, lease_during=lease_during, same_session_during=same_during,
                    unrelated=unrelated, same_session_after=same_after, keyed_still_running_after_foreign=still_running,
                    foreign_rows=[(r['session_id'] == session, r['row_id'], r['role']) for r in foreign],
                    linked=sorted(linked))
        self.assertEqual(lease_during, 1)
        self.assertEqual(same_during['exit'], 1)
        self.assertIn('hermes-refusal-reason: SESSION_NOT_OWNED', same_during['stderr_tail'])
        self.assertEqual((unrelated['exit'], same_after['exit']), (0, 0))
        self.assertTrue(still_running)          # neither foreign turn waited for the send's lease
        same_session_foreign = [r for r in foreign if r['session_id'] == session]
        self.assertEqual([r['role'] for r in same_session_foreign], ['user', 'assistant'])
        self.assertTrue([r for r in foreign if r['session_id'] != session])         # the unrelated control
        self.assertFalse({(r['session_id'], r['row_id']) for r in foreign} & linked)
        self.assertEqual(receipt['source_links'], before['source_links'])
        self.assertEqual(receipt['source_links']['owner'], [[session, owner[0]['row_id']]])
        self.assertTrue(linked <= receipted)
        self.assertEqual((row['state'], row['owner_turn']), ('complete', 'recorded'))
        self.assertEqual(len(self.started(svc, send_id)), 1)

    # --- descendants of a real tool ---------------------------------------------------------------

    def test_tool_descendants_escape_the_managed_group(self):
        """Two descendants started through the real terminal tool: a Hermes-managed background
        process (`background: true`) and a child a fixture script detaches with os.setsid().
        Both are outside the executor's group (the pinned local backend starts every command
        in a new session), neither is detected, and the send settles while they run. The
        executor's own group is empty: quiescence holds for what it can see. OPEN GATE (O-10).
        (Ordinary in-group children are covered at fixture level: test_phase1b_c1_core M-7e.)"""
        from mock_provider import DETACH_SCRIPT
        svc = self.service('tool_children')
        (self.env.home / 'c1_detach.py').write_text(DETACH_SCRIPT)
        _, row, _ = self.run_send(svc)
        tool_rows = [r for r in state_rows(self.env.home) if r['role'] == 'tool']
        self.assertEqual(len(tool_rows), 2)
        child, escaped = self.pid_file('c1_child.pid'), self.pid_file('c1_escaped.pid')
        executor = self.started(svc, row['send_id'])[0]
        facts_ = {'child': proc_facts(child), 'escaped': proc_facts(escaped), 'executor_pgid': executor['pgid']}
        self.record('tool_descendants_turn', svc, row, **facts_)
        self.assertEqual((row['state'], row['liveness']), ('complete', 'quiescent'))
        self.assertIsNotNone(row['settled_at'])
        for name in ('child', 'escaped'):
            self.assertTrue(facts_[name]['alive'], name)
            self.assertNotEqual(facts_[name]['pgid'], executor['pgid'], name)
        self.assertEqual(sp_live_members(executor['pgid']), [])



if __name__ == '__main__':
    unittest.main()
