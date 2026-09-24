"""Phase 1B C1 core: the durable send service, supervised executor, commit-boundary
receipts and the single quiescence contract (kit/app/chat_sends.py and friends).

NOT ACTIVATED: nothing here is reachable from a route. The executor in these tests
runs a local fake Hermes (tests/phase1b_c1/fake_hermes), which is a protocol double
and NOT evidence about Hermes; the Hermes-backed cases are in
tests/test_phase1b_c1_pinned.py and run in the designated pinned lane.

Matrix ids (PHASE1B_DESIGN.md section 10) are named in each test's docstring.
"""
import errno
import json
import os
import pathlib
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from tests.phase1b_c1 import harness as h            # noqa: E402
from kit.app import chat_sends as cs                 # noqa: E402
from kit.app import send_protocol as sp              # noqa: E402
from kit.app import send_quiescence as sq            # noqa: E402

LINUX = h.LINUX
POSIX_ONLY = 'the C1 supervision is established on Linux only (O-8, O-9, O-11)'


def _ulid_at(t):
    return cs.new_ulid(t)


def _wait(pred, timeout=15.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        state = pathlib.Path(f'/proc/{pid}/stat').read_text().split(') ')[1][0]
        return state not in 'ZX'
    except OSError:
        return False


def _kill(pid):
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


# ---------------------------------------------------------------------------------------------
# Receipt derivation (pure): coverage precedence and owner eligibility (review R3 5.2)
# ---------------------------------------------------------------------------------------------

def _f(kind, token='T', **data):
    return {'kind': kind, 'launch_token': token, 'data': data}


def _row(role, cls, sid='S1', row_id=1, finish=None):
    return {'session_id': sid, 'row_id': row_id, 'role': role, 'class': cls, 'finish_reason': finish}


def _turn(*writes, finished=None, session='S1', started=True):
    facts = [_f('executor_started', pid=1, pgid=1, lock_identity=[1, 1], attempt_id='A1')] if started else []
    facts.append(_f('write_intent', wid=0, method='_insert_session_row'))
    facts.append(_f('write_committed', wid=0, method='_insert_session_row', rows=[], unidentified=0,
                    sessions=[{'session_id': session, 'fresh': True}]))
    for i, w in enumerate(writes, start=1):
        facts.extend(w(i))
    if finished is not None:
        facts.append(_f('executor_finished', **finished))
    return facts


def committed(*rows, unidentified=0, sessions=()):
    return lambda wid: [_f('write_intent', wid=wid, method='append_messages_batch'),
                        _f('write_committed', wid=wid, method='append_messages_batch', rows=list(rows),
                           unidentified=unidentified, sessions=list(sessions))]


def intent_only():
    return lambda wid: [_f('write_intent', wid=wid, method='append_messages_batch')]


def unsettled():
    return lambda wid: [_f('write_intent', wid=wid, method='append_messages_batch'),
                        _f('write_unsettled', wid=wid, method='append_messages_batch')]


def gap():
    return lambda wid: [_f('write_intent', wid=wid, method='append_messages_batch'),
                        _f('receipt_gap', wid=wid, method='append_messages_batch')]


OK = {'exit': 0, 'interrupted': False, 'timed_out': False, 'receipts_complete': True}
SEND = {'capability': 'full', 'requested_session': None, 'attempt_id': 'A1'}
USER = _row('user', 'user_turn', row_id=1)
REPLY = _row('assistant', 'public_output', row_id=2, finish='stop')


class Derivation(unittest.TestCase):

    def test_complete_needs_complete_coverage_one_owner_row_and_a_stop_reply(self):
        d = cs.derive(SEND, _turn(committed(USER), committed(REPLY), finished=OK))
        self.assertEqual((d.coverage, d.owner_turn, d.reply, d.outcome), ('complete', 'recorded', 'final', 'complete'))
        self.assertEqual(d.sessions, [{'session_id': 'S1', 'created_here': True}])

    def test_no_intent_after_registration_is_a_definite_absence(self):
        """4.8: after S2, before any Hermes write; bounded coverage."""
        d = cs.derive(SEND, _turn())
        self.assertEqual((d.coverage, d.owner_turn, d.reply, d.outcome), ('bounded', 'absent', 'none', None))

    def test_unidentified_clone_rows_then_death_never_become_absence(self):
        """Review R3 5.2: a clone with unidentified rows followed by executor death must not
        derive owner_turn=absent or reply=none, although every intent has an outcome fact."""
        d = cs.derive(SEND, _turn(committed(unidentified=3)))
        self.assertEqual(d.coverage, 'incomplete')
        self.assertEqual((d.owner_turn, d.reply), ('unknown', 'unknown'))
        self.assertEqual((d.owner_rows, d.reply_rows), ([], []))

    def test_unidentified_rows_block_completion_even_with_a_finish_fact(self):
        d = cs.derive(SEND, _turn(committed(USER), committed(REPLY), committed(unidentified=1), finished=OK))
        self.assertEqual((d.coverage, d.owner_turn, d.reply), ('incomplete', 'unknown', 'unknown'))
        self.assertEqual((d.outcome, d.error_code), ('unknown', 'receipts_incomplete'))

    def test_an_unobservable_session_insert_is_unidentified(self):
        d = cs.derive(SEND, _turn(committed(USER, sessions=[{'session_id': None, 'fresh': None}])))
        self.assertEqual((d.coverage, d.owner_turn), ('incomplete', 'unknown'))

    def test_an_upsert_of_an_existing_session_is_not_created_here(self):
        facts = _turn(committed(USER, sessions=[{'session_id': None, 'fresh': False}]), finished=OK)
        d = cs.derive({'capability': 'full', 'requested_session': 'S1', 'attempt_id': 'A1'}, facts[:1] + facts[3:])
        self.assertEqual(d.sessions, [{'session_id': 'S1', 'created_here': False}])
        self.assertEqual(d.owner_turn, 'recorded')

    def test_unresolved_intent_or_unsettled_commit_is_possible(self):
        for w in (intent_only(), unsettled()):
            d = cs.derive(SEND, _turn(w))
            self.assertEqual((d.coverage, d.owner_turn, d.reply), ('incomplete', 'possible', 'unknown'))

    def test_a_receipt_gap_is_unknown_and_never_complete(self):
        d = cs.derive(SEND, _turn(committed(USER), gap(),
                                  finished={**OK, 'receipts_complete': False}))
        self.assertEqual((d.owner_turn, d.reply, d.outcome), ('unknown', 'unknown', 'unknown'))

    def test_two_owner_rows_are_ambiguous(self):
        d = cs.derive(SEND, _turn(committed(USER), committed(_row('user', 'user_turn', row_id=3))))
        self.assertEqual(d.owner_turn, 'ambiguous')
        self.assertEqual(d.owner_rows, [])

    def test_a_finished_reply_is_final_only_under_the_complete_rule(self):
        """4.3.2: `final` is the complete rule. A stop-finished reply after an ambiguous owner turn
        (O-12) or before any finish fact is `partial`."""
        second = _row('user', 'user_turn', row_id=3)
        d = cs.derive(SEND, _turn(committed(USER), committed(second), committed(REPLY), finished=OK))
        self.assertEqual((d.owner_turn, d.reply, d.outcome), ('ambiguous', 'partial', 'unknown'))
        d = cs.derive(SEND, _turn(committed(USER), committed(REPLY)))
        self.assertEqual((d.coverage, d.reply, d.outcome), ('bounded', 'partial', None))

    def test_owner_rows_outside_the_session_set_make_coverage_incomplete(self):
        d = cs.derive(SEND, _turn(committed(_row('user', 'user_turn', sid='OTHER'))))
        self.assertEqual((d.coverage, d.owner_turn), ('incomplete', 'unknown'))

    def test_exit_zero_with_a_length_reply_is_failed_reply_incomplete(self):
        d = cs.derive(SEND, _turn(committed(USER), committed(_row('assistant', 'public_output', row_id=2,
                                                                  finish='length')), finished=OK))
        self.assertEqual((d.outcome, d.error_code, d.reply), ('failed', 'reply_incomplete', 'partial'))

    def test_exit_zero_without_a_reply_is_failed_no_reply(self):
        d = cs.derive(SEND, _turn(committed(USER), finished=OK))
        self.assertEqual((d.outcome, d.error_code, d.reply), ('failed', 'no_reply_recorded', 'none'))

    def test_exit_zero_with_only_an_ineligible_owner_row_is_not_complete(self):
        hidden = _row('user', 'user_internal', row_id=1)
        d = cs.derive(SEND, _turn(committed(hidden), committed(REPLY), finished=OK))
        self.assertEqual(d.owner_turn, 'absent')
        self.assertEqual((d.outcome, d.error_code), ('unknown', 'owner_turn_not_established'))

    def test_interrupt_and_timeout(self):
        d = cs.derive(SEND, _turn(committed(USER), finished={**OK, 'exit': 130, 'interrupted': True}))
        self.assertEqual((d.outcome, d.error_code), ('interrupted', 'stopped'))
        d = cs.derive(SEND, _turn(committed(USER), finished={**OK, 'exit': 1, 'timed_out': True}))
        self.assertEqual((d.outcome, d.error_code), ('failed', 'timeout'))

    def test_downgraded_capability_never_completes(self):
        facts = _turn(finished=OK)
        facts.insert(1, _f('capability_downgrade', missing=['x']))
        d = cs.derive(SEND, facts)
        self.assertEqual((d.coverage, d.owner_turn, d.outcome, d.error_code),
                         ('unavailable', 'unknown', 'unknown', 'sources_unverified'))

    def test_continuation_note_provenance_binds_to_a_receipted_row(self):
        """O-12: provenance reclassifies exactly the named committed row of this attempt."""
        note = _row('user', 'user_turn', row_id=3)
        base = [committed(USER), committed(_row('assistant', 'public_output', row_id=2, finish='length')),
                committed(note), committed(_row('assistant', 'public_output', row_id=4, finish='stop'))]
        prov = lambda wid: [_f('row_provenance', rows=[{'session_id': 'S1', 'row_id': 3,
                                                        'kind': 'length_continuation_nudge'}])]
        d = cs.derive(SEND, _turn(*base, prov, finished=OK))
        self.assertEqual((d.owner_turn, d.reply, d.outcome, d.internal_rows),
                         ('recorded', 'final', 'complete', [['S1', 3]]))
        self.assertEqual(d.owner_rows, [['S1', 1]])
        # Without provenance, or with provenance under another token, or naming a row this
        # attempt did not commit (a reused id), nothing is reclassified.
        self.assertEqual(cs.derive(SEND, _turn(*base, finished=OK)).owner_turn, 'ambiguous')
        other = lambda wid: [_f('row_provenance', token='OTHER', rows=[{'session_id': 'S1', 'row_id': 3,
                                                                        'kind': 'length_continuation_nudge'}])]
        self.assertEqual(cs.derive(SEND, _turn(*base, other, finished=OK)).owner_turn, 'ambiguous')
        stray = lambda wid: [_f('row_provenance', rows=[{'session_id': 'S1', 'row_id': 99,
                                                         'kind': 'length_continuation_nudge'}])]
        d = cs.derive(SEND, _turn(*base, stray, finished=OK))
        self.assertEqual((d.owner_turn, d.internal_rows), ('ambiguous', []))

    def test_start_evidence_of_another_attempt_is_ignored(self):
        """C1-R4-1/2: start evidence belongs to one immutable attempt."""
        self.assertIsNone(cs.derive({**SEND, 'attempt_id': 'A2'}, _turn(committed(USER), finished=OK)).started)

    def test_facts_under_another_token_are_ignored(self):
        facts = _turn(committed(USER))
        facts.append({'kind': 'write_committed', 'launch_token': 'OTHER',
                      'data': {'wid': 9, 'rows': [REPLY], 'sessions': [], 'unidentified': 0}})
        self.assertEqual(cs.derive(SEND, facts).reply, 'none')


class OwnerEligibility(unittest.TestCase):
    """Review R3 5.2: a structurally hidden or compressed-summary user row written through
    a turn method is not owner evidence. The C0 `_classify` returned user_turn for any user row."""

    BASE = {'role': 'user', 'has_text': True, 'has_tool_calls': False, 'display_kind': None, 'summary': False,
            'observed': False, 'active': 1, 'compacted': 0}

    def test_negative_controls(self):
        self.assertEqual(sp.classify(self.BASE, 'append_message'), 'user_turn')
        for change in ({'display_kind': 'notice'}, {'summary': True}, {'observed': True}, {'has_text': False},
                       {'active': 0}, {'has_tool_calls': True}):
            with self.subTest(change=change):
                self.assertEqual(sp.classify({**self.BASE, **change}, 'append_messages_batch'), 'user_internal')
        self.assertEqual(sp.classify(self.BASE, 'replace_messages'), 'rewrite_copy')

    def test_assistant_controls(self):
        base = {**self.BASE, 'role': 'assistant'}
        self.assertEqual(sp.classify(base, 'append_message'), 'public_output')
        for change in ({'display_kind': 'notice'}, {'summary': True}, {'observed': True}, {'has_text': False},
                       {'has_tool_calls': True}):
            self.assertEqual(sp.classify({**base, **change}, 'append_message'), 'assistant_internal')


# ---------------------------------------------------------------------------------------------
# One quiescence contract (review R3 5.1)
# ---------------------------------------------------------------------------------------------

def _fake_proc(root, entries, mountinfo=None):
    proc = pathlib.Path(root) / 'proc'
    (proc / 'self').mkdir(parents=True)
    (proc / 'self' / 'mountinfo').write_text(
        '1 0 8:1 / / rw - ext4 /dev/sda1 rw\n' + (mountinfo or '22 1 0:21 / /proc rw,nosuid - proc proc rw\n'))
    for pid, stat in entries.items():
        (proc / str(pid)).mkdir()
        if stat is not None:
            (proc / str(pid) / 'stat').write_text(stat)
    return proc


@unittest.skipUnless(LINUX, POSIX_ONLY)
class Quiescence(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)

    def patch_proc(self, proc):
        patcher = mock.patch.object(sq, 'PROC', str(proc))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_uninspectable_process_is_not_an_empty_group(self):
        """The reviewer's probe, with a real PermissionError and a real EISDIR instead of a mock:
        the C0 prototype returned [] here."""
        proc = _fake_proc(self.dir, {424242: '424242 (x) S 1 424242 424242'})
        stat = proc / '424242' / 'stat'
        stat.chmod(0)
        self.addCleanup(stat.chmod, 0o644)
        self.patch_proc(proc)
        if os.geteuid() != 0:
            members, complete, reason = sq.group_members(424242)
            self.assertEqual((members, complete, reason), ((), False, 'process_uninspectable'))
        stat.chmod(0o644)
        stat.unlink()
        stat.mkdir()                                   # EISDIR: an I/O failure, not "gone"
        self.assertFalse(sq.group_members(424242)[1])

    def test_a_vanished_process_is_skipped_and_a_member_is_found(self):
        proc = _fake_proc(self.dir, {10: '10 (a b) S 1 77 77', 11: None, 12: '12 (z) Z 1 77 77'})
        self.patch_proc(proc)
        self.assertEqual(sq.group_members(77), ((10,), True, 'group_enumerated'))

    def test_an_unparseable_entry_is_incomplete(self):
        self.patch_proc(_fake_proc(self.dir, {10: 'garbage'}))
        self.assertFalse(sq.group_members(77)[1])

    def test_hidepid_or_unreadable_proc_is_unsupported(self):
        self.patch_proc(_fake_proc(self.dir, {}, '22 1 0:21 / /proc rw - proc proc rw,hidepid=2\n'))
        self.assertFalse(sq.platform_supported()[0])
        self.assertEqual(sq.group_members(1)[1:], (False, 'group_enumeration_unsupported'))

    def test_observe_reports_unproven_for_an_acquired_lock_with_an_uninspectable_group(self):
        lock = self.dir / 'e.lock'
        lock.write_text(json.dumps({'lock_nonce': 'n1'}))
        st = lock.stat()
        self.patch_proc(_fake_proc(self.dir, {5: '5 (x) S 1 5 5'}))
        (pathlib.Path(sq.PROC) / '5' / 'stat').unlink()
        (pathlib.Path(sq.PROC) / '5' / 'stat').mkdir()
        obs = sq.observe(lock, (st.st_dev, st.st_ino), 5, 'n1')
        self.assertEqual((obs.state, obs.reason), ('unproven', 'process_uninspectable'))

    def test_missing_and_replaced_lock_paths_are_unproven(self):
        lock = self.dir / 'e.lock'
        lock.write_text(json.dumps({'lock_nonce': 'n1'}))
        st = lock.stat()
        self.assertEqual(sq.probe_lock(lock, (st.st_dev, st.st_ino), 'n1'), ('acquired', 'executor_lock_acquired'))
        self.assertEqual(sq.observe(self.dir / 'missing.lock', (st.st_dev, st.st_ino), os.getpgid(0), 'n1').state,
                         'unproven')
        lock.unlink()
        lock.touch()                                   # recreated: the file system may REUSE the inode
        ident = (lock.stat().st_dev, lock.stat().st_ino)
        self.assertEqual(sq.probe_lock(lock, (st.st_dev, st.st_ino), 'n1'), ('unproven', 'lock_replaced'))
        if ident == (st.st_dev, st.st_ino):            # it did (seen on CI ext4): the nonce is what caught it
            self.assertEqual(sq.probe_lock(lock, (st.st_dev, st.st_ino)), ('acquired', 'executor_lock_acquired'))
        self.assertEqual(sq.probe_lock(lock, (st.st_dev, st.st_ino), ''), ('unproven', 'lock_replaced'))

    def test_the_same_inode_with_another_nonce_is_not_the_executors_lock(self):
        """Deterministic form of the CI finding: identical (st_dev, st_ino), different file."""
        lock = self.dir / 'e.lock'
        lock.write_text(json.dumps({'lock_nonce': 'first'}))
        st = lock.stat()
        lock.write_text(json.dumps({'lock_nonce': 'second'}))
        self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), (st.st_dev, st.st_ino))
        self.assertEqual(sq.probe_lock(lock, (st.st_dev, st.st_ino), 'first'), ('unproven', 'lock_replaced'))

    def test_a_symlinked_lock_is_refused(self):
        target = self.dir / 'real.lock'
        target.touch()
        (self.dir / 'link.lock').symlink_to(target)
        st = target.stat()
        self.assertEqual(sq.probe_lock(self.dir / 'link.lock', (st.st_dev, st.st_ino))[0], 'unproven')


# ---------------------------------------------------------------------------------------------
# Refusal of an unproven supervisor (O-A, O-E): every platform
# ---------------------------------------------------------------------------------------------

class SupervisionRefusal(unittest.TestCase):

    def test_unsupported_platform_refuses_bootstrap_and_acceptance_and_creates_nothing(self):
        """M-19 (platform leg). On Windows/macOS CI this is the real platform check."""
        env = h.Env(self)
        svc = env.service(platform_check=lambda: (False, 'process supervision is not established on testos'))
        scope = h.scope_for(env.home)
        with self.assertRaises(cs.Refused) as caught:
            svc.bootstrap(scope)
        self.assertEqual((caught.exception.code, caught.exception.status), ('send_supervision_unavailable', 503))
        self.assertFalse(svc.dir.exists())

    def test_this_platform_is_refused_unless_it_is_linux(self):
        env = h.Env(self)
        svc = env.service()
        ok, code, _ = svc.supervision()
        if not LINUX:
            self.assertEqual((ok, code), (False, 'send_supervision_unavailable'))

    def test_missing_executor_interpreter_is_refused(self):
        """M-19 (bridge leg)."""
        env = h.Env(self)
        svc = env.service(cs.ExecutorSpec(python=str(env.root / 'nope'), env={}, cwd=str(env.home)),
                          platform_check=lambda: (True, ''))
        with self.assertRaises(cs.Refused) as caught:
            svc.bootstrap(h.scope_for(env.home))
        self.assertEqual(caught.exception.code, 'send_supervision_unavailable')

    @unittest.skipUnless(LINUX, POSIX_ONLY)
    def test_unsupported_storage_is_refused(self):
        env = h.Env(self)
        svc = env.service()
        with mock.patch.object(cs, 'filesystem_type', return_value='nfs4'):
            with self.assertRaises(cs.Refused) as caught:
                svc.bootstrap(h.scope_for(env.home))
        self.assertEqual((caught.exception.code, caught.exception.status), ('send_storage_unsupported', 503))


# ---------------------------------------------------------------------------------------------
# Admission, replay, generation fence (5.2, 5.3)
# ---------------------------------------------------------------------------------------------

@unittest.skipUnless(LINUX, POSIX_ONLY)
class Admission(unittest.TestCase):

    def setUp(self):
        self.env = h.Env(self)
        self.svc = self.env.service()
        self.scope = h.scope_for(self.env.home)

    def refused(self, fn, *a):
        with self.assertRaises(cs.Refused) as caught:
            fn(*a)
        return caught.exception.code

    def test_a_post_never_creates_the_ledger(self):
        """M-6e."""
        body = {'client_key': cs.new_ulid(), 'generation': 'x', 'conversation_id': self.scope.conversation_id,
                'message': 'hi', 'session': None}
        self.assertEqual(self.refused(self.svc.accept, self.scope, body, h.workspace_only), 'not_bootstrapped')
        self.assertFalse(self.svc.db.exists())
        generation = self.svc.bootstrap(self.scope)['generation']
        status, payload = self.svc.accept(self.scope, {**body, 'generation': generation}, h.workspace_only)
        self.assertEqual(status, 202)

    def test_identical_retry_replays_even_while_the_lease_is_held(self):
        """M-1, M-1a, M-5."""
        body, (status, first) = h.send(self.svc, self.scope)
        self.assertEqual(status, 202)
        status, again = self.svc.accept(self.scope, body, h.workspace_only)
        self.assertEqual((status, again['replay'], again['send']['send_id']), (200, True, first['send']['send_id']))

    def test_same_key_different_payload_is_a_conflict_and_changes_nothing(self):
        """M-3."""
        body, (_, first) = h.send(self.svc, self.scope)
        before = h.ledger_rows(self.svc, 'SELECT * FROM sends')
        for change in ({'message': 'other'}, {'session': 'S-x'}):
            with self.subTest(change=change):
                code = self.refused(self.svc.accept, self.scope, {**body, **change}, h.resume_any())
                self.assertEqual(code, 'key_conflict')
        self.assertEqual(h.ledger_rows(self.svc, 'SELECT * FROM sends'), before)

    def test_different_keys_on_one_home_get_turn_in_progress(self):
        """M-4 / M-8c."""
        h.send(self.svc, self.scope)
        body = {'client_key': cs.new_ulid(), 'generation': self.svc.bootstrap(self.scope)['generation'],
                'conversation_id': self.scope.conversation_id, 'message': 'second', 'session': None}
        self.assertEqual(self.refused(self.svc.accept, self.scope, body, h.workspace_only), 'turn_in_progress')

    def test_generation_and_freshness_are_separate_checks(self):
        """M-6, M-6f."""
        generation = self.svc.bootstrap(self.scope)['generation']
        base = {'conversation_id': self.scope.conversation_id, 'message': 'hi', 'session': None}
        now = time.time()
        self.assertEqual(self.refused(self.svc.accept, self.scope,
                                      {**base, 'client_key': _ulid_at(now), 'generation': 'f' * 32},
                                      h.workspace_only), 'generation_changed')
        self.assertEqual(self.refused(self.svc.accept, self.scope,
                                      {**base, 'client_key': _ulid_at(now - 25 * 3600), 'generation': generation},
                                      h.workspace_only), 'key_expired')
        self.assertEqual(self.refused(self.svc.accept, self.scope,
                                      {**base, 'client_key': _ulid_at(now + 600), 'generation': generation},
                                      h.workspace_only), 'key_in_future')
        ahead = {**base, 'client_key': _ulid_at(now + 240), 'generation': generation}
        self.assertEqual(self.svc.accept(self.scope, ahead, h.workspace_only)[0], 202)
        self.svc.recover_open()
        con = sp.connect(self.svc.db)
        con.execute('DELETE FROM lease')              # (settle it by hand: no executor in this test)
        con.execute("UPDATE sends SET state='not_started', settled_at=?", (time.time(),))
        con.close()
        self.svc.reset()
        self.assertEqual(self.refused(self.svc.accept, self.scope, ahead, h.workspace_only), 'generation_changed')

    def test_expired_receipt_replays_and_expired_not_started_is_not_rearmed(self):
        """M-6a, M-6b."""
        clock = [time.time()]
        svc = self.env.service(clock=lambda: clock[0])
        body, (_, first) = h.send(svc, self.scope, key=_ulid_at(clock[0]))
        con = sp.connect(svc.db)
        con.execute('DELETE FROM lease')
        con.execute("UPDATE sends SET state='not_started', settled_at=?", (clock[0],))
        con.close()
        clock[0] += 25 * 3600
        status, payload = svc.accept(self.scope, body, h.workspace_only)
        self.assertEqual((status, payload.get('rearm'), payload['send']['state']), (200, 'expired', 'not_started'))

    def test_wrong_conversation_and_unauthorised_session(self):
        generation = self.svc.bootstrap(self.scope)['generation']
        base = {'client_key': cs.new_ulid(), 'generation': generation, 'message': 'hi'}
        self.assertEqual(self.refused(self.svc.accept, self.scope,
                                      {**base, 'conversation_id': 'conv_other', 'session': None}, h.workspace_only),
                         'wrong_conversation')
        self.assertEqual(self.refused(self.svc.accept, self.scope,
                                      {**base, 'conversation_id': self.scope.conversation_id, 'session': 'S9'},
                                      h.workspace_only), 'unauthorised_session')

    def test_twenty_concurrent_identical_requests_across_two_controllers(self):
        """M-2: one acceptance, nineteen replays, no turn_in_progress for the key's own receipt."""
        other = self.env.service()
        generation = self.svc.bootstrap(self.scope)['generation']
        body = {'client_key': cs.new_ulid(), 'generation': generation, 'conversation_id': self.scope.conversation_id,
                'message': 'hi', 'session': None}
        results, barrier = [], threading.Barrier(20)
        def go(svc):
            barrier.wait()
            try:
                results.append(svc.accept(self.scope, dict(body), h.workspace_only))
            except cs.Refused as exc:
                results.append((exc.code, None))
        threads = [threading.Thread(target=go, args=(self.svc if i % 2 else other,)) for i in range(20)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        statuses = sorted(r[0] for r in results)
        self.assertEqual(statuses, [200] * 19 + [202], statuses)
        self.assertEqual(len({r[1]['send']['send_id'] for r in results}), 1)
        self.assertEqual(h.ledger_rows(self.svc, 'SELECT count(*) FROM sends')[0][0], 1)

    def test_aliases_of_one_home_share_one_ledger_and_lease(self):
        """M-2a: another app state and a symlinked path reach one physical home."""
        link = self.env.root / 'alias'
        link.symlink_to(self.env.home)
        alias = cs.SendService(link, self.env.root / 'state-2', h.fake_executor(link))
        self.addCleanup(alias.close)
        h.send(self.svc, self.scope)
        alias_scope = h.scope_for(link, installation='other-label')
        self.assertEqual(alias.status(), 'ok')
        with self.assertRaises(cs.Refused) as caught:
            h.send(alias, alias_scope)
        self.assertEqual(caught.exception.code, 'turn_in_progress')

    def test_independent_homes_are_independent(self):
        """M-17: same key and text in two profile homes."""
        other_env = h.Env(self, name='home2')
        other = other_env.service()
        other_scope = h.scope_for(other_env.home)
        key = cs.new_ulid()
        _, (s1, p1) = h.send(self.svc, self.scope, key=key, message='same')
        _, (s2, p2) = h.send(other, other_scope, key=key, message='same')
        self.assertEqual((s1, s2), (202, 202))
        with self.assertRaises(cs.NotFound):
            other.receipt(other_scope, p1['send']['send_id'])
        with self.assertRaises(cs.NotFound):
            self.svc.receipt(self.scope, p2['send']['send_id'])

    def test_a_send_id_from_another_scope_is_not_found(self):
        _, (_, p) = h.send(self.svc, self.scope)
        with self.assertRaises(cs.NotFound):
            self.svc.receipt(h.scope_for(self.env.home, installation='elsewhere'), p['send']['send_id'])

    def test_lost_ledger_is_refused_and_never_silently_recreated(self):
        """M-6c."""
        body, (_, first) = h.send(self.svc, self.scope)
        (self.svc.dir / sp.LEDGER_ID_FILE).write_text('0' * 32)
        fresh = self.env.service()
        self.assertEqual(self.refused(fresh.bootstrap, self.scope), 'send_ledger_lost')
        self.assertEqual(self.refused(fresh.accept, self.scope, body, h.workspace_only), 'send_ledger_lost')
        (self.svc.dir / sp.LEDGER_ID_FILE).unlink()
        self.assertEqual(self.refused(self.env.service().bootstrap, self.scope), 'send_ledger_lost')

    def test_concurrent_first_bootstraps_create_one_ledger(self):
        services = [self.env.service() for _ in range(6)]
        results, barrier = [], threading.Barrier(6)
        def go(svc):
            barrier.wait()
            results.append(svc.bootstrap(self.scope)['generation'])
        threads = [threading.Thread(target=go, args=(svc,)) for svc in services]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        self.assertEqual(len(results), 6)
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(self.env.service().status(), 'ok')

    def test_a_reset_by_one_app_state_is_recognised_by_another(self):
        """Markers detect a replaced ledger, not an explicit reset made through another app state."""
        other = cs.SendService(self.env.home, self.env.root / 'state-2', h.fake_executor(self.env.home))
        self.addCleanup(other.close)
        old = self.svc.bootstrap(self.scope)['generation']
        self.assertEqual(other.status(), 'ok')
        new = self.svc.reset()['generation']
        self.assertNotEqual(old, new)
        fresh_other = cs.SendService(self.env.home, self.env.root / 'state-2', h.fake_executor(self.env.home))
        self.addCleanup(fresh_other.close)
        self.assertEqual(fresh_other.status(), 'ok')
        self.assertEqual(fresh_other.bootstrap(self.scope)['generation'], new)

    def test_reads_never_recreate_a_missing_ledger(self):
        _, (_, payload) = h.send(self.svc, self.scope)
        self.svc.db.unlink()
        fresh = self.env.service()
        for call in (lambda: fresh.receipt(self.scope, payload['send']['send_id']),
                     lambda: fresh.lookup(self.scope, 'x'), lambda: fresh.open_receipts(self.scope)):
            with self.assertRaises(cs.Refused) as caught:
                call()
            self.assertEqual(caught.exception.code, 'send_ledger_lost')
        self.assertFalse(self.svc.db.exists())
        with self.assertRaises(sqlite3.OperationalError):
            sp.connect(self.svc.db)

    def test_a_corrupt_ledger_is_lost(self):
        h.send(self.svc, self.scope)
        data = bytearray(self.svc.db.read_bytes())
        data[100:4096] = b'\xff' * (4096 - 100)
        self.svc.db.write_bytes(bytes(data))
        self.assertEqual(self.env.service().status(), 'lost')

    def test_installation_mutation_blocks_acceptance(self):
        """M-2d (acceptance leg): the installation lock is held by a mutation."""
        root = self.env.root / 'install'
        root.mkdir()
        svc = self.env.service(installation_root=root)
        with sp.held_lock(root / '.tamanitomo-installation.lock'):
            with self.assertRaises(cs.Refused) as caught:
                h.send(svc, self.scope)
        self.assertEqual(caught.exception.code, 'installation_busy')


# ---------------------------------------------------------------------------------------------
# Launch and settlement with the fake Hermes double
# ---------------------------------------------------------------------------------------------

@unittest.skipUnless(LINUX, POSIX_ONLY)
class Launch(unittest.TestCase):

    def setUp(self):
        self.env = h.Env(self)
        self.scope = h.scope_for(self.env.home)
        self.svc = self.env.service(turn_timeout=30, stop_grace=1.0, watchdog_interval=0.1)

    def run_send(self, message='A synthetic owner message', svc=None, **scenario):
        svc = svc or self.svc
        h.scenario(self.env.home, **scenario)
        body, (status, payload) = h.send(svc, self.scope, message=message)
        self.assertEqual(status, 202)
        deltas = []
        row = svc.launch(payload['send']['send_id'], message, deltas.append)
        return body, row, deltas

    def started(self, send_id):
        return sum(1 for k, _ in h.facts(self.svc, send_id) if k == 'executor_started')

    def state_rows(self):
        con = sqlite3.connect(self.env.home / 'state.db')
        try:
            return con.execute('SELECT id, session_id, role FROM messages ORDER BY id').fetchall()
        finally:
            con.close()

    def test_connected_path_then_same_key_replay_launches_nothing(self):
        """bootstrap -> intent -> acceptance -> go/S2 -> turn -> receipts -> finish -> quiescence
        -> settlement -> same-key replay (M-1 after completion)."""
        body, row, deltas = self.run_send()
        self.assertEqual((row['state'], row['owner_turn'], row['reply'], row['coverage'], row['liveness']),
                         ('complete', 'recorded', 'final', 'complete', 'quiescent'))
        self.assertIsNotNone(row['settled_at'])
        self.assertEqual(''.join(deltas), 'A synthetic reply.')
        receipt = self.svc.receipt(self.scope, row['send_id'], authorized_kinds={'workspace'})
        rows = self.state_rows()
        self.assertEqual(receipt['source_links'], {'owner': [[rows[0][1], rows[0][0]]],
                                                   'reply': [[rows[1][1], rows[1][0]]]})
        status, again = self.svc.accept(self.scope, body, h.workspace_only)
        self.assertEqual((status, again['send']['state']), (200, 'complete'))
        self.assertEqual(self.started(row['send_id']), 1)
        self.assertEqual(h.ledger_rows(self.svc, 'SELECT count(*) FROM lease')[0][0], 0)

    def test_links_are_withheld_when_the_binding_no_longer_authorises_the_kind(self):
        """M-14a (receipt leg)."""
        _, row, _ = self.run_send()
        self.assertNotIn('source_links', self.svc.receipt(self.scope, row['send_id'], authorized_kinds={'terminal'}))
        self.assertNotIn('source_links', self.svc.receipt(self.scope, row['send_id']))

    def test_no_chat_text_is_persisted_in_the_send_ledger_directory(self):
        """M-23 (privacy leg)."""
        secret, reply = 'Unmistakable owner text 7431', 'Unmistakable reply text 9152'
        self.run_send(message=secret, reply=reply)
        for path in self.svc.dir.rglob('*'):
            if path.is_file():
                data = path.read_bytes()
                self.assertNotIn(secret.encode(), data, path)
                self.assertNotIn(reply.encode(), data, path)
                self.assertNotIn(b'Unmistakable', data, path)

    def test_truncated_reply_is_failed_reply_incomplete(self):
        """M-9 (fake): exit 0 with finish_reason='length'."""
        _, row, _ = self.run_send(finish='length')
        self.assertEqual((row['state'], row['error_code'], row['reply'], row['owner_turn']),
                         ('failed', 'reply_incomplete', 'partial', 'recorded'))

    def test_hermes_failure_is_failed_with_the_owner_turn_from_receipts(self):
        _, row, _ = self.run_send(exit=1)
        self.assertEqual((row['state'], row['error_code'], row['owner_turn']), ('failed', 'hermes_failed', 'recorded'))

    def test_ineligible_owner_rows_do_not_establish_the_owner_turn(self):
        """Review R3 5.2 negative controls, through the executor and the derived receipt."""
        for owner in ('hidden', 'summary'):
            with self.subTest(owner=owner):
                env = h.Env(self)
                self.env, self.scope = env, h.scope_for(env.home)
                svc = env.service(turn_timeout=30)
                _, row, _ = self.run_send(svc=svc, owner=owner)
                self.assertEqual((row['state'], row['owner_turn'], row['error_code']),
                                 ('unknown', 'absent', 'owner_turn_not_established'))

    def test_two_owner_rows_are_ambiguous(self):
        """M-16b."""
        _, row, _ = self.run_send(owner='twice')
        self.assertEqual((row['state'], row['owner_turn'], row['correlation']), ('unknown', 'ambiguous', 'ambiguous'))

    def test_unidentified_clone_rows_leave_the_outcome_unknown(self):
        _, row, _ = self.run_send(clone=True)
        self.assertEqual((row['state'], row['coverage'], row['owner_turn'], row['reply'], row['error_code']),
                         ('unknown', 'incomplete', 'unknown', 'unknown', 'receipts_incomplete'))

    def test_receipt_gap_does_not_fail_the_committed_write_and_refuses_later_writes(self):
        """O-F / M-9c: the owner-row receipt fails after Hermes committed it."""
        _, row, _ = self.run_send(fail_receipt_for=2)
        kinds = [k for k, _ in h.facts(self.svc, row['send_id'])]
        self.assertIn('receipt_gap', kinds)
        self.assertEqual([r[2] for r in self.state_rows()], ['user'])      # committed; the reply refused
        self.assertIn(row['state'], ('failed', 'unknown'))
        self.assertEqual((row['owner_turn'], row['reply']), ('unknown', 'unknown'))
        finished = [d for k, d in h.facts(self.svc, row['send_id']) if k == 'executor_finished'][0]
        self.assertFalse(finished['receipts_complete'])
        self.assertIsNotNone(row['settled_at'])          # the gap does not block quiescence recovery

    def test_stop_interrupts_the_turn(self):
        """M-12 (fake): the ledger flag -> watchdog -> KeyboardInterrupt -> exit 130."""
        h.scenario(self.env.home, hang=20)
        body, (_, payload) = h.send(self.svc, self.scope)
        send_id = payload['send']['send_id']
        result = {}
        t = threading.Thread(target=lambda: result.update(row=self.svc.launch(send_id, body['message'])))
        t.start()
        self.assertTrue(_wait(lambda: h.ledger_rows(self.svc, 'SELECT state FROM sends')[0][0] == 'generating'))
        self.svc.stop(self.scope, send_id)
        t.join(30)
        row = result['row']
        self.assertEqual((row['state'], row['error_code'], row['owner_turn']), ('interrupted', 'stopped', 'recorded'),
                         h.facts(self.svc, send_id))
        self.assertIn('stop_seen', [k for k, _ in h.facts(self.svc, send_id)])

    def test_stop_works_when_the_app_was_started_with_sigint_ignored(self):
        """A process started with `&` from a non-interactive shell inherits SIGINT ignored; the
        executor must still be interruptible (interrupt_main is a no-op under SIG_IGN)."""
        import signal as _signal
        previous = _signal.signal(_signal.SIGINT, _signal.SIG_IGN)     # inherited by the executor
        self.addCleanup(_signal.signal, _signal.SIGINT, previous)
        svc = self.env.service(turn_timeout=1.0, stop_grace=30.0, watchdog_interval=0.1)
        _, row, _ = self.run_send(svc=svc, hang=20)
        self.assertEqual((row['state'], row['error_code']), ('interrupted', 'timeout'), h.facts(svc, row['send_id']))
        self.assertNotIn('kill_sent', [k for k, _ in h.facts(svc, row['send_id'])])

    def test_deadline_interrupts_the_turn(self):
        """M-13 (fake)."""
        svc = self.env.service(turn_timeout=1.0, stop_grace=5.0, watchdog_interval=0.1)
        _, row, _ = self.run_send(svc=svc, hang=20)
        self.assertEqual((row['state'], row['error_code']), ('interrupted', 'timeout'), h.facts(svc, row['send_id']))

    def test_a_missed_interrupt_reaches_the_kill_fallback(self):
        """M-13 kill leg: the turn swallows KeyboardInterrupt; the owner kills the group."""
        svc = self.env.service(turn_timeout=1.0, stop_grace=1.0, watchdog_interval=0.1)
        _, row, _ = self.run_send(svc=svc, hang=60, ignore_interrupt=True)
        kinds = [k for k, _ in h.facts(svc, row['send_id'])]
        self.assertIn('kill_sent', kinds)
        self.assertEqual((row['state'], row['error_code'], row['liveness']), ('unknown', 'executor_lost', 'quiescent'))
        self.assertIsNotNone(row['settled_at'])

    def test_a_descendant_left_in_the_group_holds_the_lease_until_killed(self):
        """M-7e: the executor exits, a child in its group still runs; the owner kills the group."""
        pid_file = self.env.root / 'child.pid'
        _, row, _ = self.run_send(child='group', child_pid_file=str(pid_file))
        child = int(pid_file.read_text())
        self.addCleanup(_kill, child)
        kinds = [k for k, _ in h.facts(self.svc, row['send_id'])]
        self.assertIn('kill_sent', kinds)
        self.assertEqual((row['state'], row['liveness']), ('complete', 'quiescent'))
        self.assertTrue(_wait(lambda: not _alive(child), 5))

    def test_an_escaped_descendant_is_outside_the_stated_boundary(self):
        """M-7e setsid leg: not contained, not detected; stated, not hidden (O-10)."""
        pid_file = self.env.root / 'child.pid'
        _, row, _ = self.run_send(child='escape', child_pid_file=str(pid_file))
        child = int(pid_file.read_text())
        self.addCleanup(_kill, child)
        self.assertEqual((row['state'], row['liveness']), ('complete', 'quiescent'))
        self.assertTrue(_alive(child))

    def test_spawn_failure_is_not_started_and_an_identical_retry_rearms(self):
        """4.8 'Popen raised' row, re-arm (5.3), and no unsafe re-arm of a settled outcome."""
        bad = self.env.root / 'not-executable'
        bad.write_text('')
        svc = self.env.service(cs.ExecutorSpec(python=str(bad), env={}, cwd=str(self.env.home)), turn_timeout=30)
        h.scenario(self.env.home)
        body, (_, payload) = h.send(svc, self.scope)
        row = svc.launch(payload['send']['send_id'], body['message'])
        self.assertEqual((row['state'], row['error_code'], row['settled_at'] is not None),
                         ('not_started', 'spawn_failed', True))
        svc.executor = h.fake_executor(self.env.home)
        status, again = svc.accept(self.scope, body, h.workspace_only)
        self.assertEqual((status, again.get('rearmed'), again['send']['send_id']),
                         (202, True, payload['send']['send_id']))
        row = svc.launch(payload['send']['send_id'], body['message'])
        self.assertEqual(row['state'], 'complete')
        status, third = svc.accept(self.scope, body, h.workspace_only)
        self.assertEqual((status, third['send']['state']), (200, 'complete'))
        self.assertEqual(sum(1 for k, _ in h.facts(svc, row['send_id']) if k == 'executor_started'), 1)

    def test_launch_refuses_a_different_message_for_the_accepted_digest(self):
        _, (_, payload) = h.send(self.svc, self.scope, message='accepted text')
        with self.assertRaises(cs.Refused) as caught:
            self.svc.launch(payload['send']['send_id'], 'different text')
        self.assertEqual(caught.exception.code, 'digest_mismatch')

    def test_installation_quiescence_reports_an_open_send(self):
        """4.7: installation mutations use the same contract."""
        h.scenario(self.env.home, hang=20)
        body, (_, payload) = h.send(self.svc, self.scope)
        send_id = payload['send']['send_id']
        t = threading.Thread(target=self.svc.launch, args=(send_id, body['message']))
        t.start()
        self.assertTrue(_wait(lambda: h.ledger_rows(self.svc, 'SELECT state FROM sends')[0][0] == 'generating'))
        blocked = cs.installation_quiescence(self.env.home)
        self.assertEqual([(b[1], b[2]) for b in blocked], [(send_id, 'live')])
        self.svc.stop(self.scope, send_id)
        t.join(30)
        self.assertEqual(cs.installation_quiescence(self.env.home), [])


# ---------------------------------------------------------------------------------------------
# Crash recovery with a controller in its own process (U6 harness)
# ---------------------------------------------------------------------------------------------

@unittest.skipUnless(LINUX, POSIX_ONLY)
class Recovery(unittest.TestCase):

    def setUp(self):
        self.env = h.Env(self)
        self.scope = h.scope_for(self.env.home)

    def controller(self, kill_at, executor=None, **cfg):
        executor = executor or h.fake_executor(self.env.home)
        key = cs.new_ulid()
        out = self.env.root / f'ctl-{key}.json'
        config = {'home': str(self.env.home), 'state': str(self.env.state), 'kill_at': kill_at, 'key': key,
                  'message': cfg.pop('message', 'A synthetic owner message'), 'out': str(out),
                  'executor': {'python': executor.python, 'env': executor.env, 'cwd': executor.cwd}, **cfg}
        path = self.env.root / f'cfg-{key}.json'
        path.write_text(json.dumps(config))
        proc = subprocess.Popen([sys.executable, str(HERE / 'phase1b_c1' / 'controller_proc.py'), str(path)],
                                cwd=str(HERE.parent), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        proc.wait(60)
        self.assertEqual(proc.returncode, -signal.SIGKILL, proc.stderr.read().decode()[-2000:])
        proc.stderr.close()
        return key, config

    def recovered(self, key, watch=30):
        svc = self.env.service(stop_grace=1.0)
        row = svc._lookup(self.scope.conversation_id, key)
        self.assertIsNotNone(row)
        return svc, svc.watch(row['send_id'], timeout=watch)

    def test_crash_after_acceptance_is_not_started_and_rearms(self):
        """4.8 row 2: accepted, no token -> not_started; the identical retry re-arms (same send_id)."""
        h.scenario(self.env.home)
        key, cfg = self.controller('after_accept')
        svc, row = self.recovered(key)
        self.assertEqual((row['state'], row['settled_at'] is not None), ('not_started', True))
        body = {'client_key': key, 'generation': svc.bootstrap(self.scope)['generation'],
                'conversation_id': self.scope.conversation_id, 'message': cfg['message'], 'session': None}
        status, payload = svc.accept(self.scope, body, h.workspace_only)
        self.assertEqual((status, payload['send']['send_id']), (202, row['send_id']))
        self.assertEqual(svc.launch(row['send_id'], cfg['message'])['state'], 'complete')

    def test_crash_after_T1_before_spawn(self):
        key, _ = self.controller('after_T1')
        _, row = self.recovered(key)
        self.assertEqual(row['state'], 'not_started')

    def test_crash_between_popen_and_go(self):
        """M-7a: the executor sees EOF and exits without importing Hermes; recovery fences."""
        h.scenario(self.env.home)
        key, _ = self.controller('after_popen')
        svc, row = self.recovered(key)
        self.assertEqual(row['state'], 'not_started')
        self.assertFalse((self.env.home / 'state.db').exists())       # Hermes never ran
        self.assertNotIn('executor_started', [k for k, _ in h.facts(svc, row['send_id'])])

    def test_crash_after_go_is_exactly_one_of_not_started_or_started(self):
        """M-7b: recovery fences concurrently with S2; never both, never an unrecorded executor."""
        h.scenario(self.env.home)
        key, _ = self.controller('after_go')
        svc, row = self.recovered(key)
        started = [k for k, _ in h.facts(svc, row['send_id'])].count('executor_started')
        if row['state'] == 'not_started':
            self.assertEqual(started, 0)
        else:
            self.assertEqual((started, row['state']), (1, 'complete'))
        self.assertIsNotNone(row['settled_at'])

    def test_controller_death_mid_turn_leaves_the_executor_running(self):
        """M-8: the executor finishes on its own; recovery supervises it through the lock and facts."""
        h.scenario(self.env.home, hang=1.5)
        key, _ = self.controller('first_delta', turn_timeout=60)
        svc, row = self.recovered(key)
        self.assertEqual((row['state'], row['owner_turn'], row['reply'], row['liveness']),
                         ('complete', 'recorded', 'final', 'quiescent'))
        self.assertEqual([k for k, _ in h.facts(svc, row['send_id'])].count('executor_started'), 1)

    def test_executor_killed_at_each_turn_boundary(self):
        """M-7 rows 'after S2', 'inside the owner write', 'after the owner row', 'after the reply'."""
        expected = {
            'before_owner_row': ('unknown', 'absent', 'none', 'bounded'),
            'inside_owner_write': ('unknown', 'possible', 'unknown', 'incomplete'),
            'after_owner_row': ('unknown', 'recorded', 'none', 'bounded'),
            'after_reply_row': ('unknown', 'recorded', 'partial', 'bounded'),
        }
        for point, want in expected.items():
            with self.subTest(point=point):
                env = h.Env(self)
                h.scenario(env.home, kill_at=point)
                svc, scope = env.service(turn_timeout=30), h.scope_for(env.home)
                body, (_, p) = h.send(svc, scope)
                row = svc.launch(p['send']['send_id'], body['message'])
                self.assertEqual((row['state'], row['owner_turn'], row['reply'], row['coverage']), want)
                self.assertEqual((row['error_code'], row['liveness']), ('executor_lost', 'quiescent'))

    def test_two_recovering_controllers_one_claim(self):
        """M-2b."""
        h.scenario(self.env.home)
        key, _ = self.controller('after_accept')
        a, b = self.env.service(), self.env.service()
        send_id = a._lookup(self.scope.conversation_id, key)['send_id']
        barrier = threading.Barrier(2)
        def go(svc):
            barrier.wait()
            svc.recover(send_id)
        threads = [threading.Thread(target=go, args=(s,)) for s in (a, b)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        recoveries = [k for k, _ in h.facts(a, send_id)].count('recovery')
        self.assertEqual(recoveries, 1)
        self.assertEqual(a._read(send_id)['state'], 'not_started')

    def test_a_stale_owner_cannot_transition_after_losing_its_claim(self):
        """M-8a."""
        h.scenario(self.env.home)
        old = self.env.service()
        body, (_, p) = h.send(old, self.scope)
        send_id = p['send']['send_id']
        old.close()                                   # the owner "dies" (its controller lock is released)
        new = self.env.service()
        self.assertEqual(new.recover(send_id)['state'], 'not_started')
        with self.assertRaises(cs.Refused):
            old.launch(send_id, body['message'])
        con = sp.connect(old.db)
        try:
            with sp.immediate(con):
                self.assertFalse(old._cas(con, send_id, 'not_started', 1, 'stale', state='accepted'))
        finally:
            con.close()


# ---------------------------------------------------------------------------------------------
# Reset, registration and acceptance under one hardened quiescence contract (review R3 5.1)
# ---------------------------------------------------------------------------------------------

@unittest.skipUnless(LINUX, POSIX_ONLY)
class ResetAndQuiescence(unittest.TestCase):

    def setUp(self):
        self.env = h.Env(self)
        self.scope = h.scope_for(self.env.home)
        self.svc = self.env.service(turn_timeout=60, stop_grace=60, watchdog_interval=0.1)

    def refused(self, fn, *a):
        with self.assertRaises(cs.Refused) as caught:
            fn(*a)
        return caught.exception

    def orphaned(self, **scenario):
        """A generating send whose controller died: the executor keeps running."""
        h.scenario(self.env.home, **scenario)
        key = cs.new_ulid()
        out, cfg = self.env.root / 'ctl.json', self.env.root / 'cfg.json'
        ex = h.fake_executor(self.env.home)
        cfg.write_text(json.dumps({'home': str(self.env.home), 'state': str(self.env.state), 'kill_at': 'generating',
                                   'key': key, 'message': 'hi', 'out': str(out), 'turn_timeout': 60, 'poll': 0.1,
                                   'executor': {'python': ex.python, 'env': ex.env, 'cwd': ex.cwd}}))
        proc = subprocess.run([sys.executable, str(HERE / 'phase1b_c1' / 'controller_proc.py'), str(cfg)],
                              cwd=str(HERE.parent), capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, -signal.SIGKILL, proc.stderr.decode()[-2000:])
        send_id = json.loads(out.read_text())['send_id']
        started = [d for k, d in h.facts(self.svc, send_id) if k == 'executor_started'][0]
        return send_id, started

    def assert_blocked(self, send_id, liveness):
        row = self.svc.recover(send_id)
        self.assertEqual((row['liveness'], row['settled_at']), (liveness, None))
        exc = self.refused(self.svc.reset)
        self.assertEqual(exc.code, 'executor_live')
        self.assertEqual(exc.extra['executors'][0]['liveness'], liveness)
        self.assertTrue(self.svc.db.exists())
        with self.assertRaises(cs.Refused) as caught:
            h.send(self.svc, self.scope, message='new')
        self.assertEqual(caught.exception.code, 'turn_in_progress')

    def test_reset_is_refused_while_the_executor_runs(self):
        send_id, started = self.orphaned(hang=30)
        self.addCleanup(_kill, started['pid'])
        self.assert_blocked(send_id, 'live')

    def test_executor_gone_but_managed_descendant_remains(self):
        pid_file = self.env.root / 'child.pid'
        send_id, started = self.orphaned(hang=0.5, child='group', child_pid_file=str(pid_file))
        self.assertTrue(_wait(lambda: pid_file.exists() and not _alive(started['pid'])))
        child = int(pid_file.read_text())
        self.addCleanup(_kill, child)
        self.assertEqual(sq.probe_lock(self.svc.dir / 'executors' / sp.lock_name(send_id, started['attempt_id']),
                                       started['lock_identity'])[0], 'acquired')
        self.assert_blocked(send_id, 'live')
        self.assertEqual(self.svc.recover(send_id)['state'], 'complete')     # outcome final, lease held
        _kill(child)
        self.assertTrue(_wait(lambda: not _alive(child)))
        self.assertIsNotNone(self.svc.recover(send_id)['settled_at'])
        self.assertIn('generation', self.svc.reset())

    def test_missing_or_replaced_lock_is_unproven(self):
        send_id, started = self.orphaned(hang=30)
        _kill(started['pid'])
        lock = self.svc.dir / 'executors' / sp.lock_name(send_id, started['attempt_id'])
        self.assertTrue(_wait(lambda: sq.probe_lock(lock, started['lock_identity'])[0] == 'acquired'))
        lock.unlink()
        self.assert_blocked(send_id, 'unproven')
        lock.touch()                                   # recreated (possibly with the same inode number)
        self.assert_blocked(send_id, 'unproven')

    def test_unreadable_process_data_is_unproven(self):
        send_id, started = self.orphaned(hang=30)
        _kill(started['pid'])
        lock = self.svc.dir / 'executors' / sp.lock_name(send_id, started['attempt_id'])
        self.assertTrue(_wait(lambda: sq.probe_lock(lock, started['lock_identity'])[0] == 'acquired'))
        proc = _fake_proc(self.env.root, {started['pgid']: None, 99: '99 (x) S 1 99 99'})
        (proc / str(started['pgid']) / 'stat').mkdir()          # cannot be read: EISDIR
        with mock.patch.object(sq, 'PROC', str(proc)):
            self.assert_blocked(send_id, 'unproven')
        self.assertIsNotNone(self.svc.recover(send_id)['settled_at'])   # the real /proc: gone -> quiescent

    def test_registration_racing_reset(self):
        """S2 holds the guard shared: a reset is ledger_busy. A reset first fences the token:
        the executor's S2 is then refused."""
        _, (_, p) = h.send(self.svc, self.scope)
        send_id = p['send']['send_id']
        con = sp.connect(self.svc.db)
        with sp.immediate(con):
            self.svc._cas(con, send_id, 'accepted', 1, 'test', state='launching', launch_token='K')
        con.close()
        with sp.guard(self.svc.dir, exclusive=False):
            self.assertEqual(self.refused(self.svc.reset).code, 'ledger_busy')
        import importlib.util
        spec = importlib.util.spec_from_file_location('c1_executor_under_test', cs.EXECUTOR)
        executor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(executor)
        self.svc.reset()
        self.assertFalse(executor.register(str(self.svc.dir), send_id, 'K', {'pid': 1}))

    def test_reset_racing_acceptance(self):
        generation = self.svc.bootstrap(self.scope)['generation']
        body = {'client_key': cs.new_ulid(), 'generation': generation, 'conversation_id': self.scope.conversation_id,
                'message': 'hi', 'session': None}
        with sp.guard(self.svc.dir, exclusive=True):
            self.assertEqual(self.refused(self.svc.accept, self.scope, body, h.workspace_only).code, 'ledger_busy')
        with sp.guard(self.svc.dir, exclusive=False):
            self.assertEqual(self.refused(self.svc.reset).code, 'ledger_busy')
        self.assertEqual(self.svc.accept(self.scope, body, h.workspace_only)[0], 202)

    def test_reset_with_an_unreadable_ledger_uses_the_identity_in_the_lock_file(self):
        send_id, started = self.orphaned(hang=30)
        self.addCleanup(_kill, started['pid'])
        self.svc.db.write_bytes(b'not a database' * 100)
        exc = self.refused(self.svc.reset)
        self.assertEqual((exc.code, exc.extra['executors'][0]['liveness']), ('executor_live', 'live'))
        _kill(started['pid'])
        lock = self.svc.dir / 'executors' / sp.lock_name(send_id, started['attempt_id'])
        self.assertTrue(_wait(lambda: sq.probe_lock(lock, started['lock_identity'])[0] == 'acquired'))
        self.assertIn('generation', self.svc.reset())
        self.assertTrue(list(self.svc.dir.glob('ledger.lost-*.sqlite3')))


# ---------------------------------------------------------------------------------------------
# Attempt lifecycle (PHASE1B_REVIEW_R4 C1-R4-1, C1-R4-2)
# ---------------------------------------------------------------------------------------------

class _Paused(cs.SendService):
    """Test-only subclass: blocks at named hooks until released (U6: no shipped switch)."""

    def __init__(self, *a, pause_at=(), **kw):
        super().__init__(*a, **kw)
        self.pause_at = set(pause_at)
        self.reached = {name: threading.Event() for name in self.pause_at}
        self.release = {name: threading.Event() for name in self.pause_at}

    def _hook(self, name):
        if name in self.pause_at:
            self.reached[name].set()
            self.release[name].wait(60)


@unittest.skipUnless(LINUX, POSIX_ONLY)
class AttemptLifecycle(unittest.TestCase):

    def setUp(self):
        self.env = h.Env(self)
        self.scope = h.scope_for(self.env.home)

    def paused(self, *names, **kw):
        kw.setdefault('turn_timeout', 60)
        kw.setdefault('stop_grace', 60)
        kw.setdefault('watchdog_interval', 0.1)
        svc = _Paused(self.env.home, self.env.state, h.fake_executor(self.env.home), pause_at=names, **kw)
        self.addCleanup(svc.close)
        for name in names:
            self.addCleanup(svc.release[name].set)
        return svc

    def refused(self, fn, *a):
        with self.assertRaises(cs.Refused) as caught:
            fn(*a)
        return caught.exception

    def leases(self, svc):
        return h.ledger_rows(svc, 'SELECT count(*) FROM lease')[0][0]

    def test_refused_reset_then_controller_death_keeps_a_registered_attempt_started(self):
        """C1-R4-1: S2 committed, controller not yet promoted to generating; a refused reset
        fences the token; the controller dies; another controller recovers. The attempt must
        stay started: lease held, new key refused, the old key never re-armed."""
        h.scenario(self.env.home, hang=30)
        key = cs.new_ulid()
        out, cfg = self.env.root / 'ctl.json', self.env.root / 'cfg.json'
        ex = h.fake_executor(self.env.home)
        cfg.write_text(json.dumps({'home': str(self.env.home), 'state': str(self.env.state),
                                   'kill_at': 'started_event', 'key': key, 'message': 'hi', 'out': str(out),
                                   'turn_timeout': 60, 'poll': 0.1,
                                   'executor': {'python': ex.python, 'env': ex.env, 'cwd': ex.cwd}}))
        proc = subprocess.run([sys.executable, str(HERE / 'phase1b_c1' / 'controller_proc.py'), str(cfg)],
                              cwd=str(HERE.parent), capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, -signal.SIGKILL, proc.stderr.decode()[-2000:])
        info = json.loads(out.read_text())
        svc = self.env.service(stop_grace=60)
        started = [d for k, d in h.facts(svc, info['send_id']) if k == 'executor_started']
        self.assertEqual(len(started), 1)
        self.addCleanup(lambda: os.killpg(started[0]['pgid'], signal.SIGKILL) if _alive(started[0]['pid']) else None)
        self.assertEqual(h.ledger_rows(svc, 'SELECT state FROM sends')[0][0], 'launching')
        self.assertEqual(self.refused(svc.reset).code, 'executor_live')
        row = svc.recover(info['send_id'])
        self.assertNotEqual(row['state'], 'not_started')
        self.assertEqual((row['state'], row['liveness'], row['settled_at']), ('generating', 'live', None))
        self.assertEqual(self.leases(svc), 1)
        self.assertEqual(self.refused(h.send, svc, self.scope, 'new text').code, 'turn_in_progress')
        body = {'client_key': key, 'generation': info['generation'], 'conversation_id': self.scope.conversation_id,
                'message': 'hi', 'session': None}
        status, payload = svc.accept(self.scope, body, h.workspace_only)
        self.assertEqual((status, payload.get('rearmed')), (200, None))
        os.killpg(started[0]['pgid'], signal.SIGKILL)
        lock_ok = lambda: svc.recover(info['send_id'])['settled_at'] is not None
        self.assertTrue(_wait(lock_ok))
        self.assertEqual(svc._read(info['send_id'])['state'], 'unknown')

    def test_refused_reset_without_controller_death_settles_from_the_facts(self):
        """C1-R4-1, same gap, the controller survives: the receipt reflects the executor's
        facts (complete), never not_started. The refused reset is repeated."""
        h.scenario(self.env.home, hang=1.0)
        svc = self.paused('started_event')
        other = self.env.service()
        body, (_, p) = h.send(svc, self.scope)
        result = {}
        t = threading.Thread(target=lambda: result.update(row=svc.launch(p['send']['send_id'], body['message'])))
        t.start()
        self.assertTrue(svc.reached['started_event'].wait(30))
        for _ in range(2):
            self.assertEqual(self.refused(other.reset).code, 'executor_live')
        svc.release['started_event'].set()
        t.join(60)
        row = result['row']
        self.assertEqual((row['state'], row['owner_turn'], row['reply'], row['liveness']),
                         ('complete', 'recorded', 'final', 'quiescent'))
        self.assertIsNotNone(row['settled_at'])

    def test_a_reset_that_wins_before_registration_means_never_started(self):
        """The fence-wins side of the race: reset before the executor's S2 (here before `go`).
        The executor is refused and never runs Hermes."""
        h.scenario(self.env.home)
        svc = self.paused('after_popen')
        body, (_, p) = h.send(svc, self.scope)
        result = {}
        t = threading.Thread(target=lambda: result.update(row=svc.launch(p['send']['send_id'], body['message'])))
        t.start()
        self.assertTrue(svc.reached['after_popen'].wait(30))
        self.env.service().reset()
        svc.release['after_popen'].set()
        t.join(60)
        self.assertFalse((self.env.home / 'state.db').exists())
        self.assertEqual(h.ledger_rows(svc, 'SELECT count(*) FROM sends')[0][0], 0)

    def rearm_after_stale(self, pause_a, hang=None, release_a_when='before_finalize'):
        """A launches and is paused at `pause_a`; A's controller dies; B recovers and re-arms the
        same send_id and runs attempt 2 (paused before finalize); then A resumes."""
        h.scenario(self.env.home, **({'hang': hang} if hang else {}))
        a = self.paused(pause_a)
        body, (_, p) = h.send(a, self.scope)
        send_id = p['send']['send_id']
        ta = threading.Thread(target=lambda: a.launch(send_id, body['message']))
        ta.start()
        self.assertTrue(a.reached[pause_a].wait(30))
        a.close()                                     # A's controller lock is released: A is "dead"
        b = self.paused('before_finalize', 'generating')
        b.release['generating'].set()
        self.assertEqual(b.recover(send_id)['state'], 'not_started')
        status, again = b.accept(self.scope, body, h.workspace_only)
        self.assertEqual((status, again.get('rearmed')), (202, True))
        result = {}
        tb = threading.Thread(target=lambda: result.update(row=b.launch(send_id, body['message'])))
        tb.start()
        self.assertTrue(b.reached[release_a_when].wait(30))
        a.release[pause_a].set()                      # the stale attempt resumes now
        ta.join(60)
        b.release['before_finalize'].set()
        tb.join(60)
        return b, result['row']

    def test_a_stale_executor_cannot_touch_the_newer_attempts_lock(self):
        """C1-R4-2: E1 delayed after `go`... here before `go` (same effect: it reaches S1 only
        after the newer attempt E2 has finished, before E2's settlement)."""
        b, row = self.rearm_after_stale('after_popen')
        self.assertEqual((row['state'], row['liveness']), ('complete', 'quiescent'))
        self.assertIsNotNone(row['settled_at'])
        self.assertEqual([k for k, _ in h.facts(b, row['send_id'])].count('executor_started'), 1)

    def test_a_stale_executor_resuming_while_the_newer_attempt_holds_its_lock(self):
        b, row = self.rearm_after_stale('after_popen', hang=1.0, release_a_when='generating')
        self.assertEqual((row['state'], row['liveness']), ('complete', 'quiescent'))

    def gated_stale(self, release_when, hang=None):
        """The review's exact interleaving: E1 has received `go` and is held just before S1."""
        h.scenario(self.env.home, **({'hang': hang} if hang else {}))
        gate = self.env.root / 'gate'
        gate.mkdir()
        self.addCleanup(lambda: (gate / 'release').touch())
        ex = h.fake_executor(self.env.home, extra_path=[HERE / 'phase1b_c1' / 'inject_delay'])
        ex.env['C1_TEST_S1_GATE'] = str(gate)
        a = _Paused(self.env.home, self.env.state, ex, turn_timeout=60, stop_grace=60, watchdog_interval=0.1)
        body, (_, p) = h.send(a, self.scope)
        send_id = p['send']['send_id']
        ta = threading.Thread(target=lambda: a.launch(send_id, body['message']))
        ta.start()
        self.assertTrue(_wait(lambda: (gate / 'reached').exists(), 30))   # E1: after go, before S1
        a.close()
        b = self.paused('before_finalize', 'generating')
        b.release['generating'].set()
        self.assertEqual(b.recover(send_id)['state'], 'not_started')
        self.assertEqual(b.accept(self.scope, body, h.workspace_only)[0], 202)
        result = {}
        tb = threading.Thread(target=lambda: result.update(row=b.launch(send_id, body['message'])))
        tb.start()
        self.assertTrue(b.reached[release_when].wait(30))
        (gate / 'release').touch()                    # E1 resumes: S1 on ITS attempt's lock, S2 refused
        ta.join(60)
        time.sleep(0.5)                               # give E1 time to reach S1/S2 and exit
        b.release['before_finalize'].set()
        tb.join(60)
        return b, result['row'], send_id

    def test_stale_executor_released_after_the_newer_attempt_finished(self):
        b, row, send_id = self.gated_stale('before_finalize')
        self.assertEqual((row['state'], row['liveness']), ('complete', 'quiescent'))
        self.assertIsNotNone(row['settled_at'])
        locks = sorted(p.name for p in (b.dir / 'executors').glob(f'{send_id}.*.lock'))
        self.assertEqual(len(locks), 2)               # one per attempt, resolvable independently

    def test_stale_executor_released_while_the_newer_attempt_holds_its_lock(self):
        b, row, _ = self.gated_stale('generating', hang=1.0)
        self.assertEqual((row['state'], row['liveness']), ('complete', 'quiescent'))

    def test_a_stale_launcher_losing_T1_does_not_fence_the_newer_attempt(self):
        """The launch() compare-and-set-loss cleanup must stay bound to its own attempt."""
        b, row = self.rearm_after_stale('before_T1')
        self.assertEqual((row['state'], row['liveness']), ('complete', 'quiescent'))


# ---------------------------------------------------------------------------------------------
# The pinned lane's acceptance verdict (review R4 section 5)
# ---------------------------------------------------------------------------------------------

def _lane():
    import importlib.util
    spec = importlib.util.spec_from_file_location('c1_lane_tool', HERE.parent / 'tools' / 'pinned_hermes_lane.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LaneVerdict(unittest.TestCase):

    def setUp(self):
        self.lane = _lane()
        self.full = [{'id': i, 'status': 'passed'} for i in self.lane.REQUIRED_CASES]

    def test_the_manifest_is_exactly_the_pinned_test_module(self):
        import ast
        tree = ast.parse((HERE / 'test_phase1b_c1_pinned.py').read_text())
        found = {f'tests.test_phase1b_c1_pinned.{c.name}::{f.name}' for c in tree.body if isinstance(c, ast.ClassDef)
                 for f in c.body if isinstance(f, ast.FunctionDef) and f.name.startswith('test_')}
        self.assertEqual(set(self.lane.REQUIRED_CASES), found)
        self.assertEqual(len(self.lane.REQUIRED_CASES), len(set(self.lane.REQUIRED_CASES)))

    def test_only_the_complete_manifest_passes(self):
        self.assertEqual(self.lane.verdict(self.full, 0), ('pass', []))

    def test_a_subset_with_one_passing_case_fails(self):
        """The reviewer's probe: the old prefix rule passed this."""
        self.assertEqual(self.lane.verdict(self.full[:1], 0)[0], 'fail')

    def test_missing_skipped_duplicated_failed_or_errored_cases_fail(self):
        for mutate in (lambda c: c[1:],
                       lambda c: [{**c[0], 'status': 'skipped'}] + c[1:],
                       lambda c: c + [c[0]],
                       lambda c: [{**c[0], 'status': 'failure'}] + c[1:],
                       lambda c: [{**c[0], 'status': 'error'}] + c[1:],
                       lambda c: c + [{'id': 'tests.other::x', 'status': 'failure'}]):
            with self.subTest(mutate=mutate):
                self.assertEqual(self.lane.verdict(mutate(list(self.full)), 0)[0], 'fail')
        self.assertEqual(self.lane.verdict(self.full, 1)[0], 'fail')


# ---------------------------------------------------------------------------------------------
# Retention (5.5)
# ---------------------------------------------------------------------------------------------

@unittest.skipUnless(LINUX, POSIX_ONLY)
class Retention(unittest.TestCase):

    def test_prune_removes_only_settled_sends_past_retention_and_is_bounded(self):
        """M-6d."""
        env = h.Env(self)
        clock = [time.time()]
        svc = env.service(clock=lambda: clock[0])
        scope = h.scope_for(env.home)
        svc.bootstrap(scope)
        con = sp.connect(svc.db)
        old = clock[0] - 31 * 24 * 3600
        with sp.immediate(con):
            for i in range(620):
                con.execute("INSERT INTO sends(send_id, conversation_id, client_key, key_time, request_digest, "
                            "destination, source_kind, generation, operation_id, state, claim_owner, capability, "
                            "created_at, updated_at, settled_at) VALUES (?,?,?,?,?, 'workspace','workspace','g',?,"
                            "?, 'c', 'full', ?, ?, ?)",
                            (f'snd_{i:026d}', scope.conversation_id, f'k{i}', old, 'd', f'{i:032x}',
                             'generating' if i < 3 else 'complete', old, old, None if i < 3 else old))
        con.close()
        self.assertEqual(svc.prune()[0], 500)
        self.assertEqual(svc.prune()[0], 117)
        states = h.ledger_rows(svc, 'SELECT state FROM sends')
        self.assertEqual(sorted(s for (s,) in states), ['generating'] * 3)


# ---------------------------------------------------------------------------------------------
# The recorder under in-process concurrency and interruption (O-F)
# ---------------------------------------------------------------------------------------------

def _load_executor():
    import importlib.util
    spec = importlib.util.spec_from_file_location('c1_executor_recorder_test', cs.EXECUTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _SessionDB:
    """A minimal class with the pinned calling convention, for in-process recorder tests."""

    def __init__(self, path):
        self._conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False, timeout=5)
        self._conn.execute('CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, '
                           'session_id TEXT, role TEXT, content TEXT, timestamp REAL, finish_reason TEXT)')
        self._lock = threading.RLock()

    def _execute_write(self, fn, patience_s=None):
        with self._lock:
            self._conn.execute('BEGIN IMMEDIATE')
            try:
                result = fn(self._conn)
                self._conn.execute('COMMIT')
            except BaseException:
                self._conn.execute('ROLLBACK')
                raise
        return result

    def append_message(self, session, role):
        return self._execute_write(lambda c: c.execute(
            'INSERT INTO messages(session_id, role, content, timestamp) VALUES (?,?,?,?)',
            (session, role, 'x', time.time())).lastrowid)


class RecorderConcurrency(unittest.TestCase):

    def setUp(self):
        self.ex = _load_executor()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        con = sp.connect(self.dir / 'ledger.sqlite3', create=True)
        con.executescript(sp.SCHEMA)
        con.execute("INSERT INTO sends(send_id, conversation_id, client_key, key_time, request_digest, destination, "
                    "source_kind, generation, operation_id, state, claim_owner, capability, created_at, updated_at) "
                    "VALUES ('snd_x','c','k',0,'d','workspace','workspace','g','o','generating','c','full',0,0)")
        con.close()
        self.facts = self.ex.Facts(str(self.dir / 'ledger.sqlite3'), 'snd_x', 'T')
        self.addCleanup(self.facts.con.close)
        self.db_class = type('DB', (_SessionDB,), {})
        self.ex.install_recorder(self.db_class, self.facts)
        self.db = self.db_class(self.dir / 'state.db')
        self.addCleanup(self.db._conn.close)

    def ledger(self):
        con = sp.connect(self.dir / 'ledger.sqlite3', readonly=True)
        try:
            return [(k, json.loads(d)) for k, d in con.execute('SELECT kind, data FROM send_facts ORDER BY seq')]
        finally:
            con.close()

    def test_concurrent_writers_with_a_receipt_failure(self):
        """Each committed write is either receipted or recorded as a gap; the committed write is
        not failed; after the gap every later write, from any thread, is refused."""
        original, failed = self.ex.Facts._insert, []
        def flaky(facts, kind, data):
            if kind == 'write_committed' and not failed and data['wid'] == 7:
                failed.append(data['wid'])
                raise sqlite3.OperationalError('injected')
            return original(facts, kind, data)
        errors, rows = [], []
        with mock.patch.object(self.ex.Facts, '_insert', flaky):
            def writer(n):
                for _ in range(6):
                    try:
                        rows.append(self.db.append_message(f'S{n}', 'user'))
                    except self.ex.ReceiptsIncomplete:
                        errors.append(n)
            threads = [threading.Thread(target=writer, args=(n,)) for n in range(3)]
            [t.start() for t in threads]
            [t.join(30) for t in threads]
        facts = self.ledger()
        committed = {d['wid'] for k, d in facts if k == 'write_committed'}
        gaps = {d['wid'] for k, d in facts if k == 'receipt_gap'}
        intents = {d['wid'] for k, d in facts if k == 'write_intent'}
        self.assertEqual(gaps, {7})
        self.assertEqual(len(rows), len(committed) + len(gaps))           # every committed write accounted for
        self.assertTrue(errors)                                            # later writes were refused
        con = sqlite3.connect(self.dir / 'state.db')
        self.assertEqual(con.execute('SELECT count(*) FROM messages').fetchone()[0], len(rows))
        con.close()
        self.assertLessEqual(committed | gaps, intents)
        self.assertTrue(self.facts.gap)

    def test_an_interrupt_after_the_fact_commit_does_not_duplicate_it(self):
        original = self.ex.Facts._insert
        def interrupted_after(facts, kind, data):
            original(facts, kind, data)
            raise KeyboardInterrupt
        with mock.patch.object(self.ex.Facts, '_insert', interrupted_after):
            with self.assertRaises(KeyboardInterrupt):
                self.facts.write('stop_seen', reason='stop')
        self.assertEqual([k for k, _ in self.ledger()], ['stop_seen'])

    def test_an_interrupt_before_the_fact_commit_still_records_it_once(self):
        original, calls = self.ex.Facts._insert, []
        def interrupted_before(facts, kind, data):
            calls.append(kind)
            if len(calls) == 1:
                raise KeyboardInterrupt
            return original(facts, kind, data)
        with mock.patch.object(self.ex.Facts, '_insert', interrupted_before):
            with self.assertRaises(KeyboardInterrupt):
                self.facts.write('write_intent', wid=1, method='m')
        self.assertEqual([k for k, _ in self.ledger()], ['write_intent'])

    def test_an_interrupt_inside_hermes_after_commit_is_unsettled_not_published(self):
        """A KeyboardInterrupt that escapes after the callback returned: settlement unknown."""
        cls = type('DB2', (_SessionDB,), {})
        def execute_write(self, fn, patience_s=None):
            _SessionDB._execute_write(self, fn, patience_s)
            raise KeyboardInterrupt                      # e.g. delivered during a post-commit checkpoint
        cls._execute_write = execute_write
        self.ex.install_recorder(cls, self.facts)
        db = cls(self.dir / 'state.db')
        self.addCleanup(db._conn.close)
        with self.assertRaises(KeyboardInterrupt):
            db.append_message('S', 'user')
        self.assertEqual([k for k, _ in self.ledger()], ['write_intent', 'write_unsettled'])


if __name__ == '__main__':
    unittest.main()
