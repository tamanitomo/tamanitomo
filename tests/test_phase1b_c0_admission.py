"""Phase 1B C0 evidence for B3: first-use admission, the reset fence, reset
serialisation, and the same-generation rollback limitation.

HARNESS / PROTOTYPE (tests/phase1b_c0/admission_proto.py) over a real SQLite
ledger file and real flock locks. `floor` is revision 2's rule; `generation` is
the amended rule. Clocks are injected so skew is exact.
"""
import os
import pathlib
import shutil
import sys
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'phase1b_c0'))
import admission_proto as proto  # noqa: E402

T0 = 1_790_000_000.0


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@unittest.skipIf(os.name == 'nt', 'the prototype guard is flock-based; Windows not exercised in C0')
class Admission(unittest.TestCase):
    def ledger(self, rule, clock):
        tmp = tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        return proto.Ledger(pathlib.Path(tmp.name) / '.tamanitomo-sends', rule, clock)

    # --- 3.1 first use -------------------------------------------------------
    def test_revision_two_rejects_the_first_ordinary_send(self):
        clock = Clock(T0)
        ledger = self.ledger('floor', clock)
        key_time = clock()                      # the client mints, then POSTs
        clock.t += 0.2                          # the POST arrives; it initialises the ledger
        with self.assertRaises(proto.Refused) as caught:
            ledger.accept('k1', key_time, 'd1')
        self.assertEqual(caught.exception.code, 'key_predates_ledger')

    def test_bootstrap_before_minting_admits_the_first_send(self):
        clock = Clock(T0)
        ledger = self.ledger('generation', clock)
        generation = ledger.bootstrap()         # before the pending send is frozen
        key_time = clock();clock.t += 0.2
        self.assertEqual(ledger.accept('k1', key_time, 'd1', generation), 'accepted')

    def test_a_post_without_bootstrap_is_refused_not_initialised(self):
        ledger = self.ledger('generation', Clock(T0))
        with self.assertRaises(proto.Refused) as caught:
            ledger.accept('k1', T0, 'd1', None)
        self.assertEqual(caught.exception.code, 'not_bootstrapped')
        self.assertFalse(ledger.db.exists())

    # --- 3.2 the reviewer's clock-skew trace --------------------------------
    def skew_trace(self, rule):
        clock = Clock(T0 + 12 * 3600)            # server 12:00
        ledger = self.ledger(rule, clock)
        generation = ledger.bootstrap()
        key_time = clock() + 240                 # client four minutes ahead: 12:04
        self.assertEqual(ledger.accept('k', key_time, 'd', generation), 'accepted')
        clock.t += 60                            # 12:01: ledger lost and explicitly reset
        ledger.reset()
        clock.t += 60                            # 12:02: retry of the old key, same frozen generation
        return ledger.accept('k', key_time, 'd', generation)

    def test_revision_two_readmits_an_accepted_key_after_reset(self):
        self.assertEqual(self.skew_trace('floor'), 'accepted')     # a second launch

    def test_generation_fence_refuses_a_prior_generation_request(self):
        with self.assertRaises(proto.Refused) as caught:
            self.skew_trace('generation')
        self.assertEqual(caught.exception.code, 'generation_changed')

    def test_freshness_is_separate_from_the_fence(self):
        clock = Clock(T0)
        ledger = self.ledger('generation', clock)
        generation = ledger.bootstrap()
        for key_time, code in ((T0 - 2 * 86400, 'key_expired'), (T0 + 600, 'key_in_future')):
            with self.subTest(code), self.assertRaises(proto.Refused) as caught:
                ledger.accept(f'k{code}', key_time, 'd', generation)
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(ledger.accept('behind', T0 - 3600, 'd', generation), 'accepted')

    def test_existing_receipt_replays_and_payload_stays_bound(self):
        ledger = self.ledger('generation', Clock(T0))
        generation = ledger.bootstrap()
        ledger.accept('k', T0, 'd', generation)
        self.assertEqual(ledger.accept('k', T0, 'd', generation), 'replay')
        with self.assertRaises(proto.Refused) as caught:
            ledger.accept('k', T0, 'other', generation)
        self.assertEqual(caught.exception.code, 'key_conflict')

    # --- reset serialisation -------------------------------------------------
    def test_reset_cannot_interleave_with_executor_registration(self):
        ledger = self.ledger('generation', Clock(T0))
        generation = ledger.bootstrap()
        ledger.accept('k', T0, 'd', generation)
        token = ledger.token('k')
        inside, release, outcome = threading.Event(), threading.Event(), {}
        def register():
            outcome['registered'] = ledger.register_executor('k', token, hold=lambda: (inside.set(), release.wait(5)))
        worker = threading.Thread(target=register);worker.start()
        self.assertTrue(inside.wait(5))
        with self.assertRaises(proto.Refused) as caught:        # a concurrent reset is excluded
            ledger.reset()
        self.assertEqual(caught.exception.code, 'ledger_busy')
        release.set();worker.join(5)
        self.assertTrue(outcome['registered'])

    def test_reset_fences_launch_tokens_before_replacing_the_ledger(self):
        ledger = self.ledger('generation', Clock(T0))
        generation = ledger.bootstrap()
        ledger.accept('k', T0, 'd', generation)
        token = ledger.token('k')
        new = ledger.reset()
        self.assertNotEqual(new, generation)
        self.assertFalse(ledger.register_executor('k', token))   # old token cannot start

    def test_reset_is_refused_while_an_executor_lock_is_held(self):
        import fcntl
        ledger = self.ledger('generation', Clock(T0))
        ledger.bootstrap()
        with (ledger.dir / 'executors' / 'snd_live.lock').open('a+b') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            with self.assertRaises(proto.Refused) as caught:
                ledger.reset()
            self.assertEqual(caught.exception.code, 'executor_live')
        self.assertTrue(ledger.db.exists())

    # --- 3.3 same-generation rollback ---------------------------------------
    def test_a_database_only_rollback_replays_a_missing_key_under_either_rule(self):
        """The stated limitation, demonstrated: the static ledger identity does not
        detect it and neither does the generation."""
        for rule in ('floor', 'generation'):
            with self.subTest(rule):
                ledger = self.ledger(rule, Clock(T0))
                generation = ledger.bootstrap()
                backup = ledger.dir.parent / 'backup.sqlite3'
                shutil.copy(ledger.db, backup)
                self.assertEqual(ledger.accept('k', T0, 'd', generation), 'accepted')
                shutil.copy(backup, ledger.db)                    # restore only the database file
                self.assertEqual(ledger.accept('k', T0, 'd', generation), 'accepted')

    def test_explicit_reset_after_a_known_restore_closes_it(self):
        ledger = self.ledger('generation', Clock(T0))
        generation = ledger.bootstrap()
        backup = ledger.dir.parent / 'backup.sqlite3'
        shutil.copy(ledger.db, backup)
        ledger.accept('k', T0, 'd', generation)
        shutil.copy(backup, ledger.db)
        ledger.reset()                                            # the mandatory procedure
        with self.assertRaises(proto.Refused) as caught:
            ledger.accept('k', T0, 'd', generation)
        self.assertEqual(caught.exception.code, 'generation_changed')
