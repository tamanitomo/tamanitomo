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


class CommitmentChannelTests(unittest.TestCase):
    """A commitment is how she says "I have promised to be somewhere".

    That is a fine way to express a change and a poor place to keep one: it was a
    second store of dated plans that nothing compared against the first. The
    presence record is the channel now; the plan is the store.
    """

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

    def commitment(self, title, start, end, ident='c1', status='planned', reason=''):
        return {'id': ident, 'title': title, 'starts_at': f'{DAY}T{start}:00+00:00',
                'ends_at': f'{DAY}T{end}:00+00:00', 'buffer_minutes': 0,
                'status': status, 'reason': reason}

    def sync(self, *rows):
        return plan.sync_commitments(self.c, list(rows))

    def rows(self):
        return {x['what']: x for x in (plan.read(self.c, DAY) or {'items': []})['items']}

    def test_a_commitment_lands_in_the_day_it_belongs_to(self):
        self.sync(self.commitment('haircut', '11:00', '12:00'))
        got = self.rows()['haircut']
        self.assertEqual(got['kind'], 'commitment')
        self.assertEqual((got['start'], got['end']), ('11:00', '12:00'))
        self.assertEqual(got['status'], 'planned')

    def test_a_promise_displaces_a_whim_and_says_so(self):
        plan.settle(self.c, DAY, 'a day at the coast',
                    items=[{'what': 'the beach', 'start': '10:00', 'end': '16:00', 'kind': 'idea'}])
        self.sync(self.commitment('haircut', '11:00', '12:00'))
        rows = self.rows()
        self.assertEqual(rows['haircut']['status'], 'planned')
        self.assertEqual(rows['the beach']['status'], 'moved')
        self.assertIn('promised', rows['the beach']['reason'])
        self.assertIn('haircut', plan.read(self.c, DAY)['history'][-1]['change'])

    def test_two_promises_at_once_is_left_for_her_to_resolve(self):
        """Code should not pick which promise she breaks."""
        self.sync(self.commitment('haircut', '11:00', '12:00', ident='c1'))
        self.sync(self.commitment('the dentist', '11:30', '12:30', ident='c2'))
        rows = self.rows()
        self.assertEqual(rows['haircut']['status'], 'planned')
        self.assertEqual(rows['the dentist']['status'], 'moved')
        self.assertIn('needs resolving', rows['the dentist']['reason'])

    def test_the_same_commitment_twice_updates_rather_than_duplicates(self):
        self.sync(self.commitment('haircut', '11:00', '12:00'))
        self.sync(self.commitment('haircut', '15:00', '16:00'))
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows['haircut']['start'], rows['haircut']['end']), ('15:00', '16:00'))

    def test_completing_a_commitment_marks_it_done_in_the_plan(self):
        self.sync(self.commitment('haircut', '11:00', '12:00'))
        self.sync(self.commitment('haircut', '11:00', '12:00', status='completed'))
        self.assertEqual(self.rows()['haircut']['status'], 'done')

    def test_cancelling_one_drops_it_and_frees_the_hours(self):
        self.sync(self.commitment('haircut', '11:00', '12:00'))
        self.sync(self.commitment('haircut', '11:00', '12:00', status='cancelled'))
        self.assertEqual(self.rows()['haircut']['status'], 'dropped')
        plan.add(self.c, DAY, {'what': 'a long lunch', 'start': '11:00',
                               'end': '13:00', 'kind': 'idea'})
        self.assertEqual(self.rows()['a long lunch']['status'], 'planned')

    def test_a_malformed_commitment_is_skipped_not_fatal(self):
        self.sync({'id': 'x', 'title': '', 'starts_at': 'not a time'},
                  self.commitment('haircut', '11:00', '12:00'))
        self.assertEqual(list(self.rows()), ['haircut'])

    def test_a_day_that_only_has_a_promise_still_says_what_it_is(self):
        self.sync(self.commitment('haircut', '11:00', '12:00'))
        self.assertTrue(plan.read(self.c, DAY)['intent'])


class TheDayIsReadFromThePlanTests(unittest.TestCase):
    """What the calendar shows has to be the same thing the plan says."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex', profile='nova',
                              hermes_root=base / 'hermes', vault=base / 'vault',
                              timezone='UTC', context_mode='fixed')
        self.c.home.mkdir(parents=True); self.c.soul_dir.mkdir(parents=True)
        self.c.life.mkdir(parents=True, exist_ok=True); self.c.save()
        (self.c.life / 'routine.json').write_text(json.dumps(
            {'kind': 'imagined_routine', 'routines_catalog': {},
             'daily': [{'start': '12:00', 'end': '13:00', 'activity': 'lunch', 'setting': 'home'}],
             'weekly': []}), encoding='utf-8')

    def test_a_settled_plan_replaces_the_usual_shape_of_the_day(self):
        import companion_life as life
        plan.settle(self.c, DAY, 'a day at the coast', items=[
            {'what': 'the beach', 'start': '10:00', 'end': '16:00', 'kind': 'idea'},
            {'what': 'haircut', 'start': '17:00', 'end': '18:00', 'kind': 'commitment'}])
        day = life.expected_day(self.c.life, dt.date.fromisoformat(DAY))
        self.assertEqual(day['source'], 'intended')
        self.assertEqual([a['activity'] for a in day['anchors']], ['the beach', 'haircut'])
        self.assertEqual(day['intended_plan']['intent'], 'a day at the coast')

    def test_an_unplanned_day_still_has_its_ordinary_shape(self):
        import companion_life as life
        day = life.expected_day(self.c.life, dt.date.fromisoformat('2026-09-23'))
        self.assertEqual(day['source'], 'routine')
        self.assertEqual([a['activity'] for a in day['anchors']], ['lunch'])

    def test_something_moved_aside_is_not_shown_as_the_plan(self):
        import companion_life as life
        plan.settle(self.c, DAY, 'a day at the coast',
                    items=[{'what': 'the beach', 'start': '10:00', 'end': '16:00', 'kind': 'idea'}])
        beach = plan.read(self.c, DAY)['items'][0]['id']
        plan.amend(self.c, DAY, beach, status='dropped', reason='rain')
        day = life.expected_day(self.c.life, dt.date.fromisoformat(DAY))
        self.assertEqual([a['activity'] for a in day['anchors']], [])


class BridgeShapeTests(unittest.TestCase):
    """A provider that accepts a schema and then ignores it.

    It returns 200 and answers in prose, or in a shape of its own choosing. No
    exception is raised, so a worker expecting a record got a sentence and failed
    somewhere far away on a field that was never there. Checking that the reply
    was JSON is not enough either: a well-formed object with the wrong keys
    passes that and fails everywhere after it.
    """

    SCHEMA = {'type': 'object',
              'properties': {'intent': {'type': 'string'}, 'items': {'type': 'array'},
                             'tomorrow': {'type': 'object'}},
              'required': ['intent', 'items']}

    def missing(self, body):
        import companion_text_provider as provider
        return provider._missing(body, self.SCHEMA)

    def test_prose_is_caught(self):
        self.assertIn('not JSON', self.missing('An apple is a crisp fruit.'))

    def test_a_list_at_the_top_is_caught(self):
        self.assertIn('not an object', self.missing('[1, 2, 3]'))

    def test_an_absent_required_field_is_named(self):
        self.assertIn('items', self.missing('{"intent": "a day"}'))

    def test_a_field_of_the_wrong_type_is_named(self):
        """The case that reached `set()` and raised about hashability."""
        complaint = self.missing('{"intent": 1, "items": {}}')
        self.assertIn('intent must be a string', complaint)
        self.assertIn('items must be an array', complaint)

    def test_a_good_answer_produces_no_complaint(self):
        self.assertEqual(self.missing('{"intent": "a day", "items": []}'), '')

    def test_the_schema_is_put_in_the_prompt_rather_than_trusted_to_the_provider(self):
        source = (ROOT / 'kit/scripts/companion_text_provider.py').read_text(encoding='utf-8')
        self.assertIn('if schema:request=restate(request)', source,
                      'the bridge is trusting json_schema enforcement again')


class PresenceValidationTests(unittest.TestCase):
    """Everything the writer objects to, objected to where the model can hear it.

    Half the rules lived past the end of the pulse's correction loop, so a record
    that failed them raised out of the job instead of coming back corrected.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex', profile='nova',
                              hermes_root=base / 'hermes', vault=base / 'vault',
                              timezone='UTC', context_mode='fixed')
        self.c.home.mkdir(parents=True); self.c.soul_dir.mkdir(parents=True)
        self.c.life.mkdir(parents=True, exist_ok=True); self.c.save()
        import companion_presence as presence
        self.presence = presence
        presence.update_wardrobe(self.c, [{'id': 'tee', 'description': 'a tee', 'use': 'day'}])
        self.now = dt.datetime(2026, 9, 21, 12, tzinfo=dt.timezone.utc)
        presence.update(self.c, {'previous_id': None, 'outfit': ['tee'], 'location': 'home',
                                 'activity': 'reading', 'mood': 'calm', 'text': 'At home.'}, self.now)

    def record(self, **over):
        base = {'previous_id': self.presence.current(self.c)['id'], 'outfit': ['tee'],
                'location': 'home', 'activity': 'reading', 'mood': 'calm', 'text': 'Still here.'}
        return {**base, **over}

    def test_a_good_record_checks_clean_and_writes_nothing(self):
        before = len(list(self.presence.events(self.c)))
        self.assertTrue(self.presence.check(self.c, self.record())['valid'])
        self.assertEqual(len(list(self.presence.events(self.c))), before, 'check must not write')

    def test_objects_in_the_outfit_are_a_message_not_a_crash(self):
        """This used to raise TypeError about hashability, which the pulse's
        correction loop does not catch, so the whole tick died."""
        with self.assertRaises(ValueError) as caught:
            self.presence.check(self.c, self.record(outfit=[{'id': 'tee'}]))
        self.assertIn('plain strings', str(caught.exception))

    def test_an_empty_narrative_is_a_message_too(self):
        with self.assertRaises(ValueError):
            self.presence.check(self.c, self.record(text=''))

    def test_check_and_update_agree_about_what_is_acceptable(self):
        bad = self.record(outfit=[{'id': 'tee'}])
        with self.assertRaises(ValueError):
            self.presence.check(self.c, bad)
        with self.assertRaises(ValueError):
            self.presence.update(self.c, bad, self.now + dt.timedelta(minutes=30))


class HandoffRendersOnReadTests(unittest.TestCase):
    """The handoff is a rendering of files that already know the answer.

    A scheduled job kept it fresh by writing its own presence episode every
    quarter hour, which made it the fourth writer of a field that should have
    one. Rebuilding it where it is read removes the writer and the job with it.
    """

    def test_the_advancer_is_no_longer_a_shipped_job(self):
        manifest = json.loads((ROOT / 'kit/templates/cron/manifest.json').read_text(encoding='utf-8'))
        keys = [j.get('key') for j in manifest['jobs']]
        self.assertNotIn('present', keys, 'the present advancer is back as a job')

    def test_every_presence_write_refreshes_the_handoff(self):
        """Which is why the advancer's rendering job was never needed: the pulse,
        the morning and the wind-down all go through update(), and it rebuilds."""
        source = (ROOT / 'kit/scripts/companion_presence.py').read_text(encoding='utf-8')
        body = source[source.index('def update(c,data'):source.index('def advance(')]
        self.assertIn('companion_active.write', body)

    def test_freshness_is_the_age_of_the_present_not_of_the_file(self):
        source = (ROOT / 'kit/scripts/companion_context.py').read_text(encoding='utf-8')
        block = source[source.index("handoff_at=written_at(active_path,tz)"):][:900]
        self.assertIn('last_confirmed', block,
                      'the label is measuring the file again, not the present')

    def test_presence_now_has_one_writer_family(self):
        """pulse, morning and wind-down are the same worker at three times."""
        source = (ROOT / 'kit/scripts/companion_presence.py').read_text(encoding='utf-8')
        self.assertIn('def advance(', source, 'advance() is still available for a manual run')
        manifest = json.loads((ROOT / 'kit/templates/cron/manifest.json').read_text(encoding='utf-8'))
        writers = [j['key'] for j in manifest['jobs']
                   if j.get('key') in ('pulse', 'wake', 'winddown', 'present')]
        self.assertEqual(sorted(writers), ['pulse', 'wake', 'winddown'])
