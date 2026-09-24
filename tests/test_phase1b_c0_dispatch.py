"""Phase 1B C0 evidence for B4: the daily-slot charge and its outbox marker are
separate durable writes. HARNESS / PROTOTYPE (tests/phase1b_c0/dispatch_proto.py);
slot accounting uses the real companion_outreach ledger and the real outbox
format. Production companion_dispatch.py is unchanged.

Every case asserts both the daily-budget effect (outreach.sent_today) and the
number of delivery calls.
"""
import datetime as dt
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'kit/scripts'))
sys.path.insert(0, str(ROOT / 'tests/phase1b_c0'))
import companion_config as cc  # noqa: E402
import companion_outbox as outbox  # noqa: E402
import companion_outreach as outreach  # noqa: E402
import dispatch_proto as proto  # noqa: E402

TZ = dt.timezone.utc
DAY = dt.datetime(2026, 9, 10, 14, 0, tzinfo=TZ)


@unittest.skipIf(os.name == 'nt', 'the prototype run lock is flock-based; Windows not exercised in C0')
class SlotBoundaries(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex', hermes_root=root / 'home', vault=root / 'vault',
                              timezone='UTC', quiet_start='23:00', quiet_end='08:00', outreach_per_day=3)
        self.c.life.mkdir(parents=True, exist_ok=True)
        self.entry = outbox.queue(self.c, {'kind': 'text', 'body': 'thinking about you', 'reason': 'test'}, DAY)['entry']
        self.deliveries = []

    def deliver(self, entry):
        self.deliveries.append(entry['id'])
        return True, 'sent'

    def status(self):
        return proto._status(self.c, self.entry['id'])

    def slots(self):
        return outreach.sent_today(self.c, DAY)

    def crash_then_recover(self, rule, boundary):
        with self.assertRaises(proto.Crash):
            proto.run(self.c, DAY, self.deliver, rule=rule, crash_at=boundary)
        first = proto.run(self.c, DAY, self.deliver, rule=rule)   # the next run: recovery, then maybe a send
        return first

    def test_revision_two_charges_twice_after_a_charge_before_marker_crash(self):
        """The review's B4 trace, reproduced: one message, two slots."""
        self.crash_then_recover('rev2', 'after_charge')
        self.assertEqual(self.deliveries, [self.entry['id']])
        self.assertEqual(self.slots(), 2)
        self.assertEqual(self.status(), 'sent')

    def test_amended_rule_at_every_boundary(self):
        expected = {
            # boundary: (status after the next run, delivery calls, slots used)
            'after_claim': ('sent', 1, 1),                    # no reservation intent: provably uncharged
            'after_reservation_intent': ('sent', 1, 1),       # intent, no charge row for the attempt
            'after_charge': ('failed', 0, 1),                 # charge row found: consumed, not dispatched
            'after_slot_marker': ('failed', 0, 1),
            'after_sending_marker': ('unknown', 0, 1),        # hermes send may have run: never resent
        }
        for boundary, (status, calls, slots) in expected.items():
            with self.subTest(boundary):
                self.setUp()
                self.crash_then_recover('amended', boundary)
                self.assertEqual(self.status(), status)
                self.assertEqual(len(self.deliveries), calls)
                self.assertEqual(self.slots(), slots)
                # a further run changes nothing for this entry
                proto.run(self.c, DAY, self.deliver, rule='amended')
                self.assertEqual((self.status(), len(self.deliveries), self.slots()), (status, calls, slots))

    def test_an_unreadable_slot_ledger_leaves_the_reservation_unresolved(self):
        with self.assertRaises(proto.Crash):
            proto.run(self.c, DAY, self.deliver, rule='amended', crash_at='after_reservation_intent')
        outreach.path(self.c).parent.mkdir(parents=True, exist_ok=True)
        with outreach.path(self.c).open('a', encoding='utf-8') as f:
            f.write('{"kind": "outreach", "day": "2026-09-10", "rea')     # torn line
        proto.run(self.c, DAY, self.deliver, rule='amended')
        self.assertEqual(self.status(), 'reservation_unresolved')
        self.assertEqual(self.deliveries, [])

    def test_a_stale_snapshot_cannot_claim_a_claimed_entry(self):
        stale = outbox.waiting(self.c, DAY)
        proto.run(self.c, DAY, self.deliver, rule='amended')
        second = proto.run(self.c, DAY, self.deliver, rule='amended', snapshot=stale)
        self.assertEqual(second['result'], 'claim_refused')
        self.assertEqual(len(self.deliveries), 1)
        self.assertEqual(self.slots(), 1)

    def test_a_second_dispatcher_is_refused_by_the_run_lock(self):
        import fcntl
        path = pathlib.Path(self.c.life) / '.dispatch.run.lock'
        with path.open('a+b') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            with self.assertRaises(proto.RunLockBusy):
                proto.run(self.c, DAY, self.deliver, rule='amended')
        self.assertEqual(self.deliveries, [])
        self.assertEqual(self.slots(), 0)

    def test_pre_1b_fold_does_not_requeue_new_phases(self):
        for boundary in ('after_reservation_intent', 'after_charge', 'after_sending_marker'):
            with self.subTest(boundary):
                self.setUp()
                with self.assertRaises(proto.Crash):
                    proto.run(self.c, DAY, self.deliver, rule='amended', crash_at=boundary)
                self.assertEqual(outbox.waiting(self.c, DAY), [])     # the unchanged production fold
