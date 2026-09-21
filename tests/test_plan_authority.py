"""One day, one plan — and nothing else allowed to claim the day.

Three stores could each assert what a companion was doing on a date: an intended
day, a dated commitment inside her presence record, and an event a person had
entered. Nothing compared them, so all three could be true at once and the model
blended them: she was going to the beach, and getting her hair cut, and renewing
her licence. That is the failure every test here exists to prevent.
"""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

import companion_config as cc
import companion_plan as plan

DAY = '2026-09-22'


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex', profile='nova',
                              hermes_root=base / 'hermes', vault=base / 'vault',
                              timezone='UTC', context_mode='fixed')
        self.c.home.mkdir(parents=True)
        self.c.soul_dir.mkdir(parents=True)
        self.c.life.mkdir(parents=True, exist_ok=True)
        self.c.save()

    def item(self, what, start, end, kind='idea', **kw):
        return {'what': what, 'start': start, 'end': end, 'kind': kind, **kw}

    def settled(self, *items, intent='a day'):
        return plan.settle(self.c, DAY, intent, items=[self.item(*i) for i in items])

    # ---- the invariant -----------------------------------------------------

    def test_the_beach_the_haircut_and_the_licence_cannot_all_be_true(self):
        plan.settle(self.c, DAY, 'a day at the coast',
                    items=[self.item('the beach', '10:00', '16:00')])
        with self.assertRaises(ValueError) as caught:
            plan.add(self.c, DAY, self.item('haircut', '11:00', '12:00', 'commitment'))
        self.assertIn('the beach', str(caught.exception))
        with self.assertRaises(ValueError):
            plan.add(self.c, DAY, self.item('renew the licence', '14:00', '15:00'))
        self.assertEqual([x['what'] for x in plan.read(self.c, DAY)['items']], ['the beach'])

    def test_something_may_take_a_slot_if_it_says_what_it_displaces(self):
        plan.settle(self.c, DAY, 'a day at the coast',
                    items=[self.item('the beach', '10:00', '16:00')])
        beach = plan.read(self.c, DAY)['items'][0]['id']
        after = plan.add(self.c, DAY, self.item('haircut', '11:00', '12:00', 'commitment',
                                                reason='booked weeks ago'), displaces=beach)
        rows = {x['what']: x for x in after['items']}
        self.assertEqual(rows['haircut']['status'], 'planned')
        self.assertEqual(rows['the beach']['status'], 'moved')
        self.assertEqual(rows['the beach']['reason'], 'booked weeks ago')
        self.assertIn('displaced', after['history'][-1]['change'])

    def test_displacing_something_that_is_not_there_is_refused(self):
        self.settled(('the beach', '10:00', '16:00'))
        with self.assertRaises(ValueError):
            plan.add(self.c, DAY, self.item('haircut', '11:00', '12:00'), displaces='i-nonsense')

    def test_touching_slots_are_not_an_overlap(self):
        self.settled(('lunch', '12:00', '13:00'))
        plan.add(self.c, DAY, self.item('a walk', '13:00', '14:00'))
        self.assertEqual(len(plan.read(self.c, DAY)['items']), 2)

    def test_a_day_cannot_be_written_holding_two_things_at_once(self):
        """Not just adds — a whole plan that overlaps itself is refused too."""
        with self.assertRaises(ValueError) as caught:
            self.settled(('the beach', '10:00', '16:00'), ('haircut', '11:00', '12:00'))
        self.assertIn('overlaps', str(caught.exception))

    def test_a_moved_item_stops_blocking_the_slot(self):
        self.settled(('the beach', '10:00', '16:00'))
        beach = plan.read(self.c, DAY)['items'][0]['id']
        plan.amend(self.c, DAY, beach, status='dropped', reason='weather')
        plan.add(self.c, DAY, self.item('haircut', '11:00', '12:00', 'commitment'))
        rows = {x['what']: x['status'] for x in plan.read(self.c, DAY)['items']}
        self.assertEqual(rows, {'the beach': 'dropped', 'haircut': 'planned'})

    # ---- promised vs fancied ----------------------------------------------

    def test_she_can_tell_a_promise_from_a_whim(self):
        self.settled(('haircut', '11:00', '12:00', 'commitment'),
                     ('make a zine', '14:00', '16:00', 'idea'))
        rows = {x['what']: x['kind'] for x in plan.read(self.c, DAY)['items']}
        self.assertEqual(rows['haircut'], 'commitment')
        self.assertEqual(rows['make a zine'], 'idea')

    def test_a_promise_sorts_ahead_of_a_whim_at_the_same_hour(self):
        """Only for ordering when merging; neither silently wins a real clash."""
        self.assertLess(plan.PRECEDENCE['commitment'], plan.PRECEDENCE['idea'])

    def test_an_unknown_kind_is_refused_rather_than_stored(self):
        with self.assertRaises(ValueError):
            plan.settle(self.c, DAY, 'a day', items=[self.item('x', '10:00', '11:00', 'errand')])

    # ---- ordinary care -----------------------------------------------------

    def test_a_day_needs_a_sentence_saying_what_it_is_for(self):
        with self.assertRaises(ValueError):
            plan.settle(self.c, DAY, '   ')

    def test_times_must_be_times_and_run_forwards(self):
        for start, end in (('nine', '10:00'), ('10:00', 'later'), ('16:00', '10:00'), ('10:00', '10:00')):
            with self.subTest(start=start, end=end):
                with self.assertRaises(ValueError):
                    plan.settle(self.c, DAY, 'a day', items=[self.item('x', start, end)])

    def test_nothing_is_ever_deleted_only_marked(self):
        self.settled(('the beach', '10:00', '16:00'))
        beach = plan.read(self.c, DAY)['items'][0]['id']
        plan.amend(self.c, DAY, beach, status='done')
        self.assertEqual(len(plan.read(self.c, DAY)['items']), 1)
        self.assertEqual(plan.read(self.c, DAY)['items'][0]['status'], 'done')

    def test_history_records_what_changed_and_survives_resettling(self):
        self.settled(('the beach', '10:00', '16:00'))
        plan.settle(self.c, DAY, 'a quieter day', items=[self.item('read', '10:00', '12:00')])
        history = plan.read(self.c, DAY)['history']
        self.assertGreaterEqual(len(history), 2)
        self.assertIn('a quieter day', history[-1]['change'])

    def test_a_missing_day_is_simply_empty(self):
        self.assertIsNone(plan.read(self.c, '2026-12-25'))
        board = plan.timeline(self.c, '2026-12-25')
        self.assertFalse(board['settled'])
        self.assertEqual(board['items'], [])

    def test_the_timeline_says_which_habits_the_day_still_leaves_room_for(self):
        self.settled(('the beach', '10:00', '16:00'))
        board = plan.timeline(self.c, DAY, routine=[
            {'start': '08:00', 'end': '09:30', 'activity': 'breakfast'},
            {'start': '12:00', 'end': '13:00', 'activity': 'lunch at home'}])
        free = {a['activity']: a['free'] for a in board['anchors']}
        self.assertTrue(free['breakfast'])
        self.assertFalse(free['lunch at home'], 'a habit inside a planned block is not free')


class MigrationTests(unittest.TestCase):
    """Nothing is thrown away, and the merge itself cannot create a clash."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex', profile='nova',
                              hermes_root=base / 'hermes', vault=base / 'vault',
                              timezone='UTC', context_mode='fixed')
        self.c.home.mkdir(parents=True)
        self.c.soul_dir.mkdir(parents=True)
        self.c.life.mkdir(parents=True, exist_ok=True)
        self.c.save()

    def seed_tomorrow(self, **kw):
        (self.c.life / 'tomorrow.json').write_text(json.dumps({
            'date': DAY, 'intent': 'a day at the coast', 'theme': 'beach_day',
            'anchors': [{'start': '10:00', 'end': '16:00', 'activity': 'the beach',
                         'setting': 'the coast'}], **kw}), encoding='utf-8')

    def seed_commitment(self, title, start, end):
        import companion_presence as presence
        presence.update_wardrobe(self.c, [{'id': 'tee', 'description': 'a tee', 'use': 'day'}])
        presence.update(self.c, {'previous_id': None, 'outfit': ['tee'], 'location': 'home',
                                 'activity': 'reading', 'mood': 'calm', 'text': 'At home.',
                                 'commitments': [{'id': 'c1', 'title': title,
                                                  'starts_at': f'{DAY}T{start}:00+00:00',
                                                  'ends_at': f'{DAY}T{end}:00+00:00',
                                                  'buffer_minutes': 0, 'status': 'planned',
                                                  'reason': 'booked'}]},
                        dt.datetime(2026, 9, 21, 12, tzinfo=dt.timezone.utc))

    def test_a_dry_run_writes_nothing(self):
        self.seed_tomorrow()
        report = plan.migrate(self.c, apply=False, now=dt.datetime(2026, 9, 21, 22, tzinfo=dt.timezone.utc))
        self.assertEqual(report['written'], 0)
        self.assertIsNone(plan.read(self.c, DAY))
        self.assertEqual(report['days'][0]['date'], DAY)

    def test_the_intended_day_becomes_the_plan(self):
        self.seed_tomorrow()
        plan.migrate(self.c, apply=True, now=dt.datetime(2026, 9, 21, 22, tzinfo=dt.timezone.utc))
        got = plan.read(self.c, DAY)
        self.assertEqual(got['intent'], 'a day at the coast')
        self.assertEqual(got['theme'], 'beach_day')
        self.assertEqual([x['what'] for x in got['items']], ['the beach'])

    def test_a_commitment_keeps_its_kind_through_the_merge(self):
        self.seed_commitment('haircut', '11:00', '12:00')
        plan.migrate(self.c, apply=True, now=dt.datetime(2026, 9, 21, 22, tzinfo=dt.timezone.utc))
        rows = plan.read(self.c, DAY)['items']
        self.assertEqual(rows[0]['kind'], 'commitment')
        self.assertEqual(rows[0]['what'], 'haircut')

    def test_when_both_claim_the_day_the_promise_keeps_the_slot(self):
        self.seed_tomorrow()
        self.seed_commitment('haircut', '11:00', '12:00')
        plan.migrate(self.c, apply=True, now=dt.datetime(2026, 9, 21, 22, tzinfo=dt.timezone.utc))
        rows = {x['what']: x for x in plan.read(self.c, DAY)['items']}
        self.assertEqual(rows['haircut']['status'], 'planned')
        self.assertEqual(rows['the beach']['status'], 'moved',
                         'the merge left two things claiming the same hours')
        self.assertIn('overlapped', rows['the beach']['reason'])

    def test_a_day_already_settled_by_hand_is_left_alone(self):
        plan.settle(self.c, DAY, 'something she already decided',
                    items=[{'what': 'reading', 'start': '10:00', 'end': '11:00', 'kind': 'idea'}])
        self.seed_tomorrow()
        report = plan.migrate(self.c, apply=True, now=dt.datetime(2026, 9, 21, 22, tzinfo=dt.timezone.utc))
        self.assertEqual(plan.read(self.c, DAY)['intent'], 'something she already decided')
        self.assertTrue(any('already has a settled plan' in s['why'] for s in report['skipped']))

    def test_migrating_twice_changes_nothing_the_second_time(self):
        self.seed_tomorrow()
        when = dt.datetime(2026, 9, 21, 22, tzinfo=dt.timezone.utc)
        plan.migrate(self.c, apply=True, now=when)
        first = plan.read(self.c, DAY)
        second_report = plan.migrate(self.c, apply=True, now=when)
        self.assertEqual(second_report['written'], 0)
        self.assertEqual(plan.read(self.c, DAY)['items'], first['items'])


if __name__ == '__main__':
    unittest.main()
