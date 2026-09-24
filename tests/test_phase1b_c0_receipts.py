"""Phase 1B C0 evidence: source receipts against the PINNED Hermes (0e9fc2cc15).

HARNESS / PROTOTYPE. These tests drive the real pinned SessionDB and real quiet
one-shot Hermes turns against tests/mock_provider.py in synthetic homes. The
recorders under test live in tests/phase1b_c0/receipt_probe.py; no production
sending code exists yet, so a pass here is evidence about Hermes's boundaries
and about the prototype rule, not an integrated production result.

`rev2` tests assert the DEFECT the reviewer described is real (they pass when the
revision-2 recorder misbehaves). `commit` tests assert the amended rule.

Skips with a named reason when the pinned Hermes is not configured
(tests/phase1b_c0/pinned.py). CI does not have it.
"""
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'phase1b_c0'))
import pinned  # noqa: E402
from mock_provider import MockProvider  # noqa: E402

PIN, WHY = pinned.hermes()


def committed(facts):
    return [f for f in facts if f['kind'] == 'write_committed']


def receipt_rows(facts):
    return [r for f in committed(facts) for r in f['rows']]


def evidence(name, data):
    out = os.environ.get('TAMANITOMO_C0_EVIDENCE_DIR')
    if out:
        pathlib.Path(out).mkdir(parents=True, exist_ok=True)
        (pathlib.Path(out) / f'{name}.json').write_text(json.dumps(data, indent=1, sort_keys=True))


@unittest.skipUnless(PIN, WHY)
class RevisionTwoDefects(unittest.TestCase):
    """The review's B2.1/B2.2 traces, reproduced on the pinned code with the rev2 recorder."""

    def test_rolled_back_batch_is_published_as_written(self):
        out = pinned.seam(PIN, 'rev2', 'batch_rollback_after_inner_insert')
        evidence('rev2_batch_rollback', out)
        written = [f['row_id'] for f in out['facts'] if f['kind'] == 'row_written']
        self.assertEqual(out['state_rows'], [])                 # nothing committed
        self.assertEqual(written, [1, 2])                       # yet two rows "written"

    def test_a_retried_callback_publishes_every_attempt(self):
        out = pinned.seam(PIN, 'rev2', 'batch_retry_after_locked')
        evidence('rev2_batch_retry', out)
        self.assertEqual(out['notes']['attempts'], 2)
        written = [f['row_id'] for f in out['facts'] if f['kind'] == 'row_written']
        self.assertEqual(sorted(written), [1, 1, 2, 2])         # the same ids, twice
        self.assertEqual([r['row_id'] for r in out['state_rows']], [1, 2])

    def test_a_rolled_back_id_is_reused_by_a_foreign_writer(self):
        out = pinned.seam(PIN, 'rev2', 'rolled_back_id_reused_by_foreign_writer')
        evidence('rev2_foreign_reuse', out)
        written = [f['row_id'] for f in out['facts'] if f['kind'] == 'row_written']
        self.assertEqual(out['notes']['foreign_row_id'], 1)
        self.assertEqual(written, [1])                          # the terminal's row, claimed

    def test_an_upsert_of_an_existing_session_is_reported_as_created(self):
        out = pinned.seam(PIN, 'rev2', 'sessions_create_vs_upsert')
        created = [f['session_id'] for f in out['facts'] if f['kind'] == 'session_created']
        self.assertIn('c0-session', created)                    # existed before; not created here

    def test_compression_child_is_created_outside_create_session(self):
        out = pinned.seam(PIN, 'rev2', 'compression_child_and_clone')
        evidence('rev2_compression_child', out)
        self.assertIn('c0-child', out['sessions'])
        self.assertFalse([f for f in out['facts'] if f['kind'] == 'session_created'])
        written = {f['row_id'] for f in out['facts'] if f['kind'] == 'row_written'}
        child_rows = {r['row_id'] for r in out['state_rows'] if r['session_id'] == 'c0-child'}
        self.assertTrue(child_rows - written)                   # the cloned tail row is unseen

    def test_a_receipt_failure_after_commit_is_raised_into_hermes(self):
        out = pinned.seam(PIN, 'rev2', 'receipt_write_fails_after_source_commit')
        self.assertEqual(out['notes'].get('caller_saw'), 'OperationalError')
        self.assertIn(1, [r['row_id'] for r in out['state_rows']])   # Hermes had committed it


@unittest.skipUnless(PIN, WHY)
class CommitAwareReceipts(unittest.TestCase):

    def assertExactCover(self, out):
        """Every receipt row is a committed row, and no committed row has two receipts."""
        rows = [r['row_id'] for r in receipt_rows(out['facts'])]
        self.assertEqual(len(rows), len(set(rows)), 'a row was receipted twice')
        state = {r['row_id'] for r in out['state_rows']}
        self.assertLessEqual(set(rows), state, 'a receipt names a row that is not committed')
        return set(rows), state

    def test_plain_append(self):
        out = pinned.seam(PIN, 'commit', 'append_ok')
        rows, state = self.assertExactCover(out)
        self.assertEqual(rows, state)

    def test_rollback_after_inner_insert_publishes_nothing(self):
        out = pinned.seam(PIN, 'commit', 'batch_rollback_after_inner_insert')
        self.assertExactCover(out)
        self.assertEqual(receipt_rows(out['facts']), [])
        self.assertEqual([f['kind'] for f in out['facts']], ['write_intent', 'write_rolled_back'])

    def test_retried_callback_gives_one_receipt(self):
        out = pinned.seam(PIN, 'commit', 'batch_retry_after_locked')
        rows, state = self.assertExactCover(out)
        self.assertEqual(rows, state)
        self.assertEqual([f['attempts'] for f in committed(out['facts'])], [2])

    def test_foreign_reuse_of_a_rolled_back_id_is_never_claimed(self):
        out = pinned.seam(PIN, 'commit', 'rolled_back_id_reused_by_foreign_writer')
        self.assertEqual(out['state_rows'][0]['row_id'], out['notes']['foreign_row_id'])
        self.assertEqual(receipt_rows(out['facts']), [])

    def test_chunked_batch_is_one_receipt_per_committed_chunk(self):
        out = pinned.seam(PIN, 'commit', 'chunked_batch')
        rows, state = self.assertExactCover(out)
        self.assertEqual(rows, state)
        self.assertEqual([len(f['rows']) for f in committed(out['facts'])], [2, 2, 1])

    def test_rewrites_are_copies_not_turn_output(self):
        out = pinned.seam(PIN, 'commit', 'replace_messages_copies')
        self.assertExactCover(out)
        rewrite = [f for f in committed(out['facts']) if f['method'] == 'replace_messages'][0]
        self.assertEqual({r['class'] for r in rewrite['rows']}, {'rewrite_copy'})

    def test_public_output_is_distinguished_from_tool_and_internal_rows(self):
        out = pinned.seam(PIN, 'commit', 'public_vs_internal_rows')
        self.assertEqual([r['class'] for r in receipt_rows(out['facts'])],
                         ['user_turn', 'assistant_internal', 'internal', 'public_output'])

    def test_receipt_failure_after_source_commit_is_a_gap_then_fails_closed(self):
        out = pinned.seam(PIN, 'commit', 'receipt_write_fails_after_source_commit')
        self.assertNotIn('caller_saw', out['notes'])            # Hermes's committed write is not failed
        self.assertEqual(out['receipt_gap'], 1)                   # held in memory for executor_finished
        self.assertIn('receipt_gap', [f['kind'] for f in out['facts']])
        self.assertEqual(receipt_rows(out['facts']), [])         # never recovered by guessing
        self.assertEqual(out['notes'].get('later_write'), 'OperationalError')
        self.assertEqual([r['row_id'] for r in out['state_rows']], [1])   # the later write never landed

    def test_commit_failure_after_the_callback_is_unsettled(self):
        out = pinned.seam(PIN, 'commit', 'commit_raises_after_callback')
        self.assertEqual([f['kind'] for f in out['facts']], ['write_intent', 'write_unsettled'])

    def test_only_a_fresh_insert_is_a_created_session(self):
        out = pinned.seam(PIN, 'commit', 'sessions_create_vs_upsert')
        evidence('commit_sessions', out)
        seen = [(s['session_id'], s['fresh']) for f in committed(out['facts']) for s in f['sessions']]
        self.assertEqual(seen, [('c0-fresh', True), ('c0-session', False), ('c0-session', False),
                                ('c0-ensured-fresh', True)])
        self.assertEqual(out['facts'][-1]['kind'], 'write_rolled_back')
        self.assertNotIn('c0-failed', out['sessions'])

    def test_compression_child_and_clone_are_seen_and_the_clone_is_unidentified(self):
        out = pinned.seam(PIN, 'commit', 'compression_child_and_clone')
        evidence('commit_compression_child', out)
        publish = [f for f in committed(out['facts']) if f['method'] == 'publish_compression_child'][0]
        self.assertEqual(publish['sessions'], [{'session_id': 'c0-child', 'fresh': True, 'existed_before': False}])
        self.assertEqual(publish['unidentified'], 1)             # receipts incomplete: said, not guessed
        self.assertEqual({r['class'] for r in publish['rows']}, {'rewrite_copy'})

    def test_in_place_compaction_clone_is_unidentified(self):
        out = pinned.seam(PIN, 'commit', 'archive_and_compact_clone')
        compact = [f for f in committed(out['facts']) if f['method'] == 'archive_and_compact'][0]
        self.assertEqual(compact['unidentified'], 1)


@unittest.skipUnless(PIN, WHY)
class RealTurns(unittest.TestCase):
    """One real quiet one-shot turn per path, pinned Hermes, mock provider, synthetic home."""

    def run_turn(self, scenario, **kw):
        tmp = tempfile.TemporaryDirectory(prefix='c0-turn-');self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        with MockProvider() as provider:
            home = pinned.synthetic_home(root, provider, scenario)
            resume = None
            if kw.pop('resume_first', False):
                first = pinned.turn(PIN, home, root / 'first.sqlite3', root / 'first.json')
                resume = first['session_id']
                provider.requests.clear();provider.request_times.clear()
            report = pinned.turn(PIN, home, root / 'r.sqlite3', root / 'r.json', resume=resume, **kw)
            requests, times = list(provider.requests), list(provider.request_times)
        facts = pinned.facts(root / 'r.sqlite3')
        rows = pinned.rows(home)
        out = {'report': report, 'facts': facts, 'rows': rows, 'sessions': pinned.session_ids(home),
               'requests': requests, 'request_times': times, 'resumed': resume}
        user = [f for f in committed(facts) for r in f['rows'] if r['class'] == 'user_turn']
        out['owner_committed_at'] = user[0]['at'] if user else None
        evidence(f'turn_{scenario}' + ('_resume' if resume else '') + ('_interrupt' if kw.get('interrupt_after') else ''),
                 {k: v for k, v in out.items() if k != 'facts'} | {'fact_kinds': [f['kind'] for f in facts]})
        return out

    def assertCovered(self, out, own_rows):
        receipted = [r['row_id'] for r in receipt_rows(out['facts'])]
        self.assertEqual(len(receipted), len(set(receipted)))
        self.assertEqual(set(receipted), own_rows)

    def test_fresh_turn(self):
        out = self.run_turn('deltas')
        self.assertEqual(out['report']['exit'], 0)
        self.assertCovered(out, {r['row_id'] for r in out['rows']})
        classes = [r['class'] for r in receipt_rows(out['facts'])]
        self.assertEqual(classes, ['user_turn', 'public_output'])
        fresh = [s['session_id'] for f in committed(out['facts']) for s in f['sessions'] if s['fresh']]
        self.assertEqual(fresh, [out['report']['session_id']])
        self.assertEqual([r['finish_reason'] for r in out['rows']], [None, 'stop'])

    def test_resumed_turn_creates_no_session(self):
        out = self.run_turn('deltas', resume_first=True)
        self.assertEqual(out['report']['session_id'], out['resumed'])
        self.assertFalse([s for f in committed(out['facts']) for s in f['sessions'] if s['fresh']])
        self.assertCovered(out, {3, 4})                          # this executor's rows only

    def test_provider_error_before_first_byte(self):
        out = self.run_turn('error_before_first_byte')
        self.assertEqual(out['report']['exit'], 1)
        self.assertEqual([r['class'] for r in receipt_rows(out['facts'])], ['user_turn'])
        self.assertGreater(len(out['requests']), 1)              # Hermes's own retries, one executor

    def test_truncated_and_disconnected_replies_exit_zero(self):
        for scenario in ('truncated', 'disconnect_before_done'):
            with self.subTest(scenario):
                out = self.run_turn(scenario)
                self.assertEqual(out['report']['exit'], 0)
                assistant = [r for r in out['rows'] if r['role'] == 'assistant']
                self.assertEqual([r['finish_reason'] for r in assistant], ['length'])
                # classified as text-bearing output by role alone -- so exit 0 plus an
                # assistant row is NOT completion evidence; finish_reason must be checked.
                self.assertIn('public_output', [r['class'] for r in receipt_rows(out['facts'])])

    def test_interrupt_main_reaches_the_turn_during_a_stream(self):
        out = self.run_turn('hang', interrupt_after=2)
        self.assertEqual(out['report']['exit'], 130)
        self.assertEqual([r['role'] for r in out['rows']], ['user'])     # no partial row persisted
        latency = out['report']['finished'] - out['report']['interrupt_sent_at']
        self.assertLess(latency, 15)                              # within the proposed grace

    def test_state_db_is_written_before_the_turn_but_not_during_import(self):
        out = self.run_turn('deltas')
        report = out['report']
        self.assertFalse([c for c in report['connects'] if c['db'] == 'state.db' and c['stage'] == 'import'])
        pre = [f for f in committed(out['facts']) if f['at'] < report['quiet_entered_at']]
        self.assertTrue(pre, 'startup maintenance writes were expected before the turn')
        self.assertFalse([r for f in pre for r in f['rows']])   # but no transcript rows
