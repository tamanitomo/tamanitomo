"""Phase 1B C2 dispatcher safety (PHASE1B_DESIGN.md section 7; matrix M-20, M-20a-d, M-21).

BOUNDARY: the PRODUCTION kit/scripts/companion_dispatch.py, companion_outbox.py and
companion_outreach.py on synthetic life directories. The only doubles are the delivery call
(`companion_dispatch._invoke`, which is what would reach a platform) and, in the crash cases,
the `_hook` seam that SIGKILLs a subprocess at a named boundary. No Hermes, platform, network
or real message is involved. Every case asserts the outbox status, the number of delivery
calls and the daily-slot effect (outreach.sent_today).
"""
import datetime as dt
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'kit/scripts'))
import companion_config as cc          # noqa: E402
import companion_dispatch as dispatch  # noqa: E402
import companion_outbox as outbox      # noqa: E402
import companion_outreach as outreach  # noqa: E402
import companion_self as slf            # noqa: E402
from companion_platform import file_lock  # noqa: E402

TZ = dt.timezone.utc
DAY = dt.datetime(2026, 9, 10, 14, 0, tzinfo=TZ)
PROC = ROOT / 'tests' / 'phase1b_c2' / 'dispatch_proc.py'
POSIX = os.name != 'nt'
SENT = {'returncode': 0, 'stdout': json.dumps({'success': True, 'message_id': 'm-1'})}


class Base(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.kw = dict(agent='Nova', human='Alex', hermes_root=str(self.root / 'home'), vault=str(self.root / 'vault'),
                       timezone='UTC', quiet_start='23:00', quiet_end='08:00', outreach_per_day=3)
        self.c = self.companion()
        self.c.life.mkdir(parents=True, exist_ok=True)
        self.deliveries = self.root / 'deliveries.jsonl'

    def companion(self):
        kw = dict(self.kw)
        kw['hermes_root'], kw['vault'] = pathlib.Path(kw['hermes_root']), pathlib.Path(kw['vault'])
        return cc.Companion(**kw)

    def queue(self, body='thinking about you', **extra):
        return outbox.queue(self.c, {'kind': 'text', 'body': body, 'reason': 'test', **extra}, DAY)['entry']

    def status(self, ident):
        return outbox.current(self.c, ident)['status']

    def calls(self):
        return len(self.deliveries.read_text().splitlines()) if self.deliveries.exists() else 0

    def slots(self):
        return outreach.sent_today(self.c, DAY)

    def invoke(self, reply=SENT):
        """An in-process delivery double for companion_dispatch._invoke."""
        def call(c, body, target):
            with self.deliveries.open('a') as f:
                f.write(json.dumps({'target': target}) + '\n')
            return subprocess.CompletedProcess([], reply['returncode'], reply.get('stdout', ''), reply.get('stderr', ''))
        return mock.patch.object(dispatch, '_invoke', call)

    def run_proc(self, kill_at=None, reply=SENT, hold_file=None):
        cfg = self.root / f'cfg-{time.monotonic_ns()}.json'
        cfg.write_text(json.dumps({'companion': self.kw, 'now': DAY.isoformat(), 'deliveries': str(self.deliveries),
                                   'kill_at': kill_at, 'reply': reply, 'hold_file': hold_file}))
        return subprocess.Popen([sys.executable, str(PROC), str(cfg)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)

    def finish(self, proc, timeout=60):
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err


# --- 1. one active run, one claim (M-20a) --------------------------------------------------------

@unittest.skipUnless(POSIX, 'crash and concurrency cases use POSIX process signals')
class OneRunOneClaim(Base):

    def test_a_second_dispatcher_is_refused_by_the_run_lock(self):
        entry = self.queue()
        hold = self.root / 'release'
        first = self.run_proc(hold_file=str(hold))           # holds the run lock inside its "network call"
        self.assertTrue(_wait(lambda: self.calls() == 1, 30))
        with self.invoke():
            second = dispatch.run(self.c, DAY)
        self.assertEqual((second.get('busy'), second['handled']), (True, []))
        hold.write_text('')
        code, out, err = self.finish(first)
        self.assertEqual(code, 0, err)
        self.assertEqual((self.status(entry['id']), self.calls(), self.slots()), ('sent', 1, 1))

    def test_with_the_run_lock_bypassed_the_claim_guard_admits_one(self):
        """Two runs load the same queued entry before either claims (a double removes the run
        lock). Both reach the claim; exactly one appends `dispatching`; one send, one slot."""
        entry = self.queue()
        barrier = threading.Barrier(2, timeout=30)
        real_verdict = dispatch.verdict

        def both_have_the_snapshot(c, e, now):
            barrier.wait()
            return real_verdict(c, e, now)
        results = []
        with self.invoke(), mock.patch.object(dispatch, 'verdict', both_have_the_snapshot), \
                mock.patch.object(dispatch, 'file_lock', side_effect=lambda *a, **k: _null()):
            threads = [threading.Thread(target=lambda: results.append(dispatch.run(self.c, DAY))) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(60)
        actions = sorted(h['action'] for r in results for h in r['handled'])
        self.assertEqual(actions, ['sent', 'skipped'])
        self.assertEqual((self.status(entry['id']), self.calls(), self.slots()), ('sent', 1, 1))

    def test_concurrent_processes_never_deliver_one_entry_twice(self):
        """Eight real dispatcher processes at once, repeatedly, over three entries: each entry
        is delivered at most once and the daily cap is never exceeded."""
        ids = [self.queue(f'thought {i}')['id'] for i in range(3)]
        for _ in range(3):
            procs = [self.run_proc() for _ in range(8)]
            for p in procs:
                self.assertEqual(self.finish(p)[0], 0)
        rows = [r for r in slf._read(outbox.path_for(self.c)) if r.get('kind') == 'outbox_update']
        claims = [r['id'] for r in rows if r['status'] == 'dispatching']
        self.assertEqual(sorted(claims), sorted(ids))                  # one claim per entry, ever
        self.assertEqual([self.status(i) for i in ids], ['sent'] * 3)
        self.assertEqual((self.calls(), self.slots()), (3, 3))


# --- 2/3. crash boundaries and an unreadable charge ledger (M-20, M-20b) -------------------------

@unittest.skipUnless(POSIX, 'crash cases SIGKILL a subprocess')
class CrashBoundaries(Base):
    EXPECTED = {
        # boundary: (status after the next run, delivery calls, slots used) -- PHASE1B_DESIGN 7.3
        'after_claim': ('sent', 1, 1),               # no intent: provably uncharged, requeued, then sent
        'after_reservation_intent': ('sent', 1, 1),  # intent, no charge row for the attempt: requeued
        'after_charge': ('failed', 0, 1),            # charge row found: consumed, never dispatched
        'after_slot_marker': ('failed', 0, 1),
        'after_sending_marker': ('unknown', 0, 1),   # hermes send may have run: never resent
        'after_delivery': ('unknown', 1, 1),         # it did run; the outcome row was lost: never resent
    }

    def crash(self, boundary):
        code, _, err = self.finish(self.run_proc(kill_at=boundary))
        self.assertEqual(code, -9, f'{boundary}: {err[-500:]}')

    def test_every_boundary(self):
        for boundary, expected in self.EXPECTED.items():
            with self.subTest(boundary=boundary):
                self.setUp()
                entry = self.queue()
                self.crash(boundary)
                code, out, err = self.finish(self.run_proc())            # the next run: recovery, maybe a send
                self.assertEqual(code, 0, err)
                self.assertEqual((self.status(entry['id']), self.calls(), self.slots()), expected)
                after = outbox.current(self.c, entry['id'])
                if expected[0] == 'failed':
                    self.assertTrue(after.get('not_dispatched'))
                code, _, err = self.finish(self.run_proc())               # and a further run changes nothing
                self.assertEqual(code, 0, err)
                self.assertEqual((self.status(entry['id']), self.calls(), self.slots()), expected)

    def test_an_unreadable_charge_ledger_leaves_the_reservation_unresolved(self):
        """A torn outreach line: the charge cannot be established, so it is NOT taken as proof
        that no charge happened. Not requeued, not refunded, not sent; the owner sees it."""
        entry = self.queue()
        self.crash('after_reservation_intent')
        outreach.path(self.c).parent.mkdir(parents=True, exist_ok=True)
        with outreach.path(self.c).open('a', encoding='utf-8') as f:
            f.write('{"kind": "outreach", "day": "2026-09-10", "rea')
        for _ in range(2):
            code, out, err = self.finish(self.run_proc())
            self.assertEqual(code, 0, err)
        after = outbox.current(self.c, entry['id'])
        self.assertEqual((after['status'], self.calls()), ('reservation_unresolved', 0))
        self.assertIn('whether a daily slot was used is unknown', after['detail'])
        self.assertEqual(outbox.waiting(self.c, DAY), [])

    def test_a_charge_lookup_error_is_never_read_as_no_charge(self):
        entry = self.queue()
        self.crash('after_charge')
        with mock.patch.object(outreach, 'charges_for', side_effect=OSError('permission denied')), self.invoke():
            dispatch.run(self.c, DAY)
        self.assertEqual((self.status(entry['id']), self.calls(), self.slots()), ('reservation_unresolved', 0, 1))

    def test_a_crash_while_the_run_lock_is_held_does_not_block_the_next_run(self):
        entry = self.queue()
        self.crash('after_sending_marker')
        with self.invoke():
            result = dispatch.run(self.c, DAY)
        self.assertFalse(result.get('busy'))
        self.assertEqual(result['recovered'], [(entry['id'], 'unknown')])


# --- 4. attempt ownership (M-20c) ---------------------------------------------------------------

class AttemptOwnership(Base):

    def at(self, status, attempt='r1:0'):
        entry = self.queue()
        path = ['dispatching', 'reserving_slot', 'slot_reserved', 'sending', 'unknown']
        expect = 'queued'
        for step in path[:path.index(status) + 1]:
            self.assertTrue(outbox.transition(self.c, entry['id'], step, attempt, 'r1', expect, DAY)['written'])
            expect = step
        return entry['id']

    def test_a_different_attempt_cannot_move_the_entry(self):
        ident = self.at('sending')
        for status in ('sent', 'failed', 'unknown', 'queued'):
            r = outbox.transition(self.c, ident, status, 'r2:0', 'r2', 'sending', DAY)
            self.assertEqual(r, {'written': False, 'refused': 'the message belongs to a different attempt'})
        self.assertEqual(self.status(ident), 'sending')

    def test_a_stale_expected_phase_is_refused(self):
        ident = self.at('slot_reserved')
        r = outbox.transition(self.c, ident, 'slot_reserved', 'r1:0', 'r1', 'reserving_slot', DAY)
        self.assertFalse(r['written'])
        self.assertEqual(self.status(ident), 'slot_reserved')

    def test_a_late_outcome_after_recovery_is_refused(self):
        """The old run wakes after the next run resolved its `sending` entry as unknown: its
        `sent` (expecting `sending`) is refused; the recorded outcome stays unknown."""
        ident = self.at('sending')
        with self.invoke():
            dispatch.run(self.c, DAY)
        self.assertEqual(self.status(ident), 'unknown')
        r = outbox.transition(self.c, ident, 'sent', 'r1:0', 'r1', 'sending', DAY)
        self.assertFalse(r['written'])
        self.assertEqual((self.status(ident), self.calls()), ('unknown', 0))

    def test_unknown_is_replaced_only_by_the_same_attempt_with_evidence(self):
        ident = self.at('unknown')
        refused = outbox.resolve_unknown(self.c, ident, 'r1:0', 'sent', {})
        self.assertIn('needs evidence', refused['refused'])
        other = outbox.resolve_unknown(self.c, ident, 'r9:0', 'sent', {'message_id': 'm-9'})
        self.assertEqual(other['refused'], 'the message belongs to a different attempt')
        self.assertEqual(self.status(ident), 'unknown')
        same = outbox.resolve_unknown(self.c, ident, 'r1:0', 'sent', {'message_id': 'm-1'})
        self.assertTrue(same['written'])
        after = outbox.current(self.c, ident)
        self.assertEqual((after['status'], after['delivery']['message_id']), ('sent', 'm-1'))
        again = outbox.resolve_unknown(self.c, ident, 'r1:0', 'failed', {'platform_result': 'x'})
        self.assertFalse(again['written'])                        # no contradictory second result
        self.assertEqual(self.calls(), 0)                         # nothing is ever resent

    def test_a_requeued_entry_belongs_to_its_new_attempt(self):
        ident = self.at('dispatching')
        with self.invoke():
            dispatch.run(self.c, DAY)                                   # recovers r1:0 -> queued, then sends it
        self.assertEqual((self.status(ident), self.calls()), ('sent', 1))
        self.assertFalse(outbox.transition(self.c, ident, 'unknown', 'r1:0', 'r1', 'sent', DAY)['written'])

    def test_mark_cannot_overwrite_an_attempt_or_an_outcome(self):
        for status in ('dispatching', 'sending', 'unknown'):
            with self.subTest(status=status):
                self.setUp()
                ident = self.at(status)
                r = outbox.mark(self.c, ident, 'withheld', 'withdrawn by hand', DAY)
                self.assertFalse(r['written'])
                self.assertEqual(self.status(ident), status)
        entry = self.queue('another')
        self.assertTrue(outbox.mark(self.c, entry['id'], 'withheld', 'withdrawn by hand', DAY)['written'])


# --- outcome classification and the delivery record (M-21) ---------------------------------------

class Classification(unittest.TestCase):

    def case(self, returncode=0, stdout='', stderr='', error=None):
        return dispatch.classify('telegram', returncode, stdout, stderr, error)

    def test_the_table(self):
        partial = json.dumps({'error': 'Adapter media send failed after 1/3 files'})
        rows = [
            ('id', self.case(stdout=json.dumps({'success': True, 'message_id': 42})), 'sent'),
            ('no id', self.case(stdout=json.dumps({'success': True})), 'sent'),
            ('skipped', self.case(stdout=json.dumps({'success': True, 'skipped': True, 'reason': 'dup'})), 'withheld'),
            ('partial media error', self.case(returncode=1, stdout=partial), 'unknown'),
            ('other error', self.case(returncode=1, stdout=json.dumps({'error': 'Unknown platform: x'})), 'unknown'),
            ('error with exit 0', self.case(stdout=json.dumps({'success': False, 'error': 'x'})), 'unknown'),
            ('timeout', self.case(error=subprocess.TimeoutExpired('hermes', 120)), 'unknown'),
            ('os error', self.case(error=OSError('no hermes')), 'unknown'),
            ('non-JSON', self.case(stdout='Sent!'), 'unknown'),
            ('non-zero exit, no JSON', self.case(returncode=137, stderr='Killed'), 'unknown'),
            ('success but non-zero exit', self.case(returncode=1, stdout=json.dumps({'success': True})), 'unknown'),
        ]
        for name, result, outcome in rows:
            with self.subTest(name):
                self.assertEqual(result['outcome'], outcome)
                record = result['delivery']
                self.assertEqual((record['id_scope'], record['recipient_resolved'], record['mirrored']),
                                 ('last_chunk', None, None))
                self.assertEqual(record['requested_target'], 'telegram')
        self.assertEqual(rows[0][1]['delivery']['message_id'], 42)
        self.assertEqual((rows[1][1]['delivery']['message_id'], rows[1][1]['delivery']['id_missing']), (None, True))
        self.assertIn('Adapter media send failed', rows[3][1]['detail'])

    def test_reported_values_are_kept_and_nothing_is_invented(self):
        r = self.case(stdout=json.dumps({'success': True, 'message_id': 'a', 'chat_id': 99, 'mirrored': True}))
        self.assertEqual((r['delivery']['recipient_resolved'], r['delivery']['mirrored']), (99, True))

    def test_the_pre_platform_list_starts_empty(self):
        self.assertEqual(dispatch.PRE_PLATFORM_ERRORS, ())

    def test_the_watch_notifier_keeps_its_shape(self):
        c = mock.Mock(home='h', profile=None)
        with mock.patch.object(dispatch, '_invoke', return_value=subprocess.CompletedProcess(
                [], 0, json.dumps({'success': True, 'message_id': 1}), '')):
            self.assertEqual(dispatch.hermes_send(c, 'hi'), (True, 'sent'))


class OutcomesThroughTheDispatcher(Base):

    def test_the_record_lands_in_the_outbox(self):
        entry = self.queue()
        with self.invoke({'returncode': 0, 'stdout': json.dumps({'success': True, 'message_id': 'm-7'})}):
            result = dispatch.run(self.c, DAY)
        self.assertEqual(result['handled'][0]['action'], 'sent')
        after = outbox.current(self.c, entry['id'])
        self.assertEqual((after['status'], after['delivery']['message_id'], after['delivery']['id_scope']),
                         ('sent', 'm-7', 'last_chunk'))
        self.assertEqual(after['attempt'].split(':')[0], result['run_id'])

    def test_an_error_is_unknown_and_never_resent(self):
        entry = self.queue()
        with self.invoke({'returncode': 1, 'stdout': json.dumps({'error': 'Adapter media send failed after 1/2 files'})}):
            for _ in range(3):
                dispatch.run(self.c, DAY)
        self.assertEqual((self.status(entry['id']), self.calls(), self.slots()), ('unknown', 1, 1))

    def test_skipped_is_withheld(self):
        entry = self.queue()
        with self.invoke({'returncode': 0, 'stdout': json.dumps({'success': True, 'skipped': True, 'reason': 'dup'})}):
            dispatch.run(self.c, DAY)
        self.assertEqual(self.status(entry['id']), 'withheld')

    def test_a_cap_refusal_appends_no_charge_and_requeues(self):
        """verdict() allowed it, then the slot was gone by the time claim() ran (the race 7.2
        step 3b covers): the refusal appends no charge and releases the entry to `queued`."""
        self.c.outreach_per_day = 1
        first, second = self.queue('one'), self.queue('two')
        with self.invoke():
            dispatch.run(self.c, DAY)
            with mock.patch.object(dispatch, 'verdict', return_value={'action': 'send', 'reason': 'x', 'urgent': False}):
                result = dispatch.run(self.c, DAY)
        self.assertEqual(result['handled'][0]['action'], 'hold')
        after = outbox.current(self.c, second['id'])
        self.assertEqual((after['status'], after['release_reason']), ('queued', 'cap'))
        self.assertEqual((self.calls(), self.slots()), (1, 1))

    def test_a_raising_delivery_step_is_unknown(self):
        entry = self.queue()
        with mock.patch.object(dispatch, 'deliver', side_effect=RuntimeError('bug')):
            dispatch.run(self.c, DAY)
        self.assertEqual((self.status(entry['id']), self.slots()), ('unknown', 1))


class ChargeLedger(Base):

    def test_the_charge_row_carries_the_attempt(self):
        outreach.claim(self.c, 'outbox', now=DAY, attempt='r1:0')
        row = json.loads(outreach.path(self.c).read_text().splitlines()[-1])
        self.assertEqual(row['attempt'], 'r1:0')
        self.assertEqual(outreach.charges_for(self.c, 'r1:0'), 1)
        self.assertEqual(outreach.charges_for(self.c, 'r2:0'), 0)

    def test_a_missing_ledger_is_empty_and_a_torn_one_is_unreadable(self):
        self.assertEqual(outreach.charges_for(self.c, 'r1:0'), 0)
        outreach.path(self.c).parent.mkdir(parents=True, exist_ok=True)
        outreach.path(self.c).write_text('{"kind": "outreach", "day": "2026-09-10", "rea')
        with self.assertRaises(ValueError):
            outreach.charges_for(self.c, 'r1:0')

    def test_a_refused_claim_appends_nothing(self):
        self.c.outreach = 'never'
        before = outreach.path(self.c).exists()
        self.assertFalse(outreach.claim(self.c, 'x', now=DAY, attempt='r1:0')['allowed'])
        self.assertEqual(outreach.path(self.c).exists(), before)


# --- 5. existing entries and mixed versions (M-20d, 7.8) -----------------------------------------

PRE_1B = '3d78c57594df100ff7ae170d7aa501a8ad59a6df'     # the C2 base: these modules unchanged since before 1B


def _pre_1b(module, **deps):
    """The production module as it was before C2, loaded from git. `deps` are modules it
    should import instead of today's (so an old dispatcher uses the old outbox)."""
    source = subprocess.run(['git', '-C', str(ROOT), 'show', f'{PRE_1B}:kit/scripts/{module}.py'],
                            capture_output=True, text=True, check=True).stdout
    spec = importlib.util.spec_from_loader(f'pre1b_{module}', loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = str(ROOT / 'kit' / 'scripts' / f'{module}.py')
    saved = {name: sys.modules.get(name) for name in deps}
    sys.modules.update(deps)
    try:
        exec(compile(source, f'pre1b_{module}.py', 'exec'), mod.__dict__)
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
    return mod


class Compatibility(Base):

    def test_an_existing_outbox_stays_readable_and_its_queued_entry_is_dispatched(self):
        path = outbox.path_for(self.c)
        rows = [{'id': 'old-1', 'kind': 'outbox', 'content': 'text', 'body': 'sent long ago', 'media_path': '',
                 'priority': 'normal', 'reason': '', 'not_before': '', 'target': 'telegram', 'status': 'queued',
                 'expires_at': (DAY + dt.timedelta(hours=4)).isoformat(), 'queued_at': (DAY - dt.timedelta(hours=1)).isoformat()},
                {'id': 'old-1', 'kind': 'outbox_update', 'status': 'sent', 'detail': 'sent', 'at': DAY.isoformat()},
                {'id': 'old-2', 'kind': 'outbox', 'content': 'text', 'body': 'still waiting', 'media_path': '',
                 'priority': 'normal', 'reason': '', 'not_before': '', 'target': 'telegram', 'status': 'queued',
                 'expires_at': (DAY + dt.timedelta(hours=4)).isoformat(), 'queued_at': DAY.isoformat()}]
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        self.assertEqual([(e['id'], e['status'], e.get('attempt')) for e in outbox.fold(self.c)],
                         [('old-1', 'sent', None), ('old-2', 'queued', None)])
        with self.invoke():
            dispatch.run(self.c, DAY)
        self.assertEqual([self.status('old-1'), self.status('old-2')], ['sent', 'sent'])
        self.assertEqual(self.calls(), 1)

    def test_the_pre_1b_fold_does_not_requeue_new_phases(self):
        old = _pre_1b('companion_outbox')
        for status in ('dispatching', 'reserving_slot', 'slot_reserved', 'sending', 'unknown', 'reservation_unresolved'):
            with self.subTest(status=status):
                self.setUp()
                entry = self.queue()
                path = ['dispatching', 'reserving_slot', 'slot_reserved', 'sending']
                expect = 'queued'
                for step in path[:path.index(status) + 1] if status in path else path:
                    outbox.transition(self.c, entry['id'], step, 'r1:0', 'r1', expect, DAY)
                    expect = step
                if status not in path:
                    outbox.transition(self.c, entry['id'], status, 'r1:0', 'r1', expect, DAY)
                self.assertEqual(old.waiting(self.c, DAY), [])

    def test_a_running_pre_1b_dispatcher_is_not_excluded(self):
        """STATED LIMITATION (7.8), pinned: a pre-1B dispatcher that took its snapshot before a
        1B run claimed the entry takes neither the run lock nor the claim guard, so it sends
        the entry again. Running old and new dispatchers together is unsupported."""
        old_outbox = _pre_1b('companion_outbox')
        old = _pre_1b('companion_dispatch', companion_outbox=old_outbox)
        entry = self.queue()
        stale = outbox.waiting(self.c, DAY)
        with self.invoke():
            dispatch.run(self.c, DAY)
        with mock.patch.object(old, 'deliver', return_value=(True, 'sent')) as old_deliver, \
                mock.patch.object(old.outbox, 'waiting', return_value=stale):
            old.run(self.c, DAY)
        self.assertIs(old.outbox, old_outbox)
        self.assertEqual((self.calls(), old_deliver.call_count), (1, 1))      # the duplicate this cannot prevent
        self.assertEqual(self.slots(), 2)
        self.assertEqual(self.status(entry['id']), 'sent')


def _wait(pred, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


if __name__ == '__main__':
    unittest.main()
