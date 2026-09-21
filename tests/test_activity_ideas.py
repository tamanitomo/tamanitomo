"""Ideas for a day, so she is not at home reading every one of them.

She had seven generic anchors, five scripted days and a one-in-a-hundred chance
of a detour. Nothing pushed against the safe answer, so the safe answer is what
came back, daily. Enumerating hundreds of whole days would be unmaintainable and
still fixed; a palette she draws from and adds to is neither.
"""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

import companion_life as life


class SeedPaletteTests(unittest.TestCase):
    """The shipped ideas have to be usable data, not decoration."""

    def setUp(self):
        self.data = json.loads((ROOT / 'kit/personas/activity_ideas.json').read_text(encoding='utf-8'))
        self.ideas = self.data['ideas']

    def test_there_are_enough_of_them_to_matter(self):
        self.assertGreaterEqual(len(self.ideas), 60)

    def test_every_idea_is_complete_and_uniquely_named(self):
        seen = set()
        for idea in self.ideas:
            with self.subTest(idea=idea.get('id')):
                for key in ('id', 'title', 'tags', 'season', 'energy', 'cost', 'social', 'setting', 'hours'):
                    self.assertIn(key, idea)
                self.assertNotIn(idea['id'], seen)
                seen.add(idea['id'])
                self.assertIn(idea['season'], ('any', 'spring', 'summer', 'autumn', 'winter'))
                self.assertIn(idea['social'], ('solo', 'cast', 'crowd'))
                self.assertIn(idea['setting'], ('home', 'local', 'city', 'outdoors', 'nature', 'water'))

    def test_she_is_not_offered_a_life_spent_indoors_alone(self):
        """The actual complaint. A palette that is mostly home-and-solo fixes nothing."""
        settings = Counter(x['setting'] for x in self.ideas)
        social = Counter(x['social'] for x in self.ideas)
        self.assertLess(settings['home'] / len(self.ideas), 0.45, 'too much of this is staying in')
        self.assertGreater(social['cast'] + social['crowd'], 15, 'too few involve anyone else')
        self.assertGreater(sum(v for k, v in settings.items() if k != 'home'), len(self.ideas) / 2)


class SuggestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)

    def ids(self, day='2026-09-22', count=6):
        return [x['id'] for x in life.suggest(self.root, day, count)['suggestions']]

    def test_the_same_day_always_offers_the_same_ideas(self):
        """An evening's suggestions must not reshuffle if anything asks twice."""
        self.assertEqual(self.ids(), self.ids())

    def test_different_days_offer_different_ideas(self):
        days = [tuple(self.ids(f'2026-09-{n:02d}')) for n in range(10, 25)]
        self.assertGreater(len(set(days)), 10, 'the suggestions barely move from day to day')

    def test_what_she_just_did_is_not_offered_straight_back(self):
        """A life repeats; a rut repeats this week."""
        every = {x['id'] for x in life.palette(self.root)}
        yesterday = dt.date(2026, 9, 21).isoformat()
        for ident in list(every)[:40]:
            life.record_choice(self.root, ident, yesterday)
        offered = set(self.ids(count=12))
        self.assertTrue(offered - set(list(every)[:40]),
                        'everything offered was done yesterday')

    def test_something_done_long_ago_comes_back(self):
        life.record_choice(self.root, 'cafe-with-a-book', '2026-01-01')
        found = any('cafe-with-a-book' in self.ids(f'2026-09-{n:02d}', 20) for n in range(10, 28))
        self.assertTrue(found, 'an old favourite should be allowed round again')

    def test_a_refused_idea_stops_being_offered(self):
        life.decline_idea(self.root, 'skate-or-fall')
        for n in range(1, 29):
            self.assertNotIn('skate-or-fall', self.ids(f'2026-09-{n:02d}', 20))

    def test_a_long_day_out_is_kept_for_a_day_that_has_room(self):
        def share(day, wanted):
            hits = 0
            for _ in range(1):
                ids = self.ids(day, 20)
                pool = {x['id']: x for x in life.palette(self.root)}
                hits = sum(1 for i in ids if float(pool[i].get('hours', 2)) >= 5)
            return hits
        weekend = sum(share(f'2026-09-{n:02d}', 5) for n in (5, 6, 12, 13, 19, 20, 26, 27))
        weekday = sum(share(f'2026-09-{n:02d}', 5) for n in (7, 8, 9, 10, 11, 14, 15, 16))
        self.assertGreater(weekend, weekday, 'the big days should favour the weekend')

    def test_her_own_ideas_join_the_palette_and_are_favoured(self):
        life.add_idea(self.root, {'title': 'sit on the pier and watch the boats',
                                  'tags': ['quiet'], 'setting': 'water'})
        pool = {x['id']: x for x in life.palette(self.root)}
        self.assertIn('her-sit-on-the-pier-and-watch-the-boats', pool)
        self.assertTrue(pool['her-sit-on-the-pier-and-watch-the-boats']['hers'])
        found = any('her-sit-on-the-pier-and-watch-the-boats' in self.ids(f'2026-09-{n:02d}', 8)
                    for n in range(10, 25))
        self.assertTrue(found, "her own idea is never offered back to her")

    def test_an_idea_needs_something_to_call_it(self):
        with self.assertRaises(ValueError):
            life.add_idea(self.root, {'title': '   '})

    def test_choosing_something_that_does_not_exist_is_refused(self):
        with self.assertRaises(ValueError):
            life.record_choice(self.root, 'a-thing-she-made-up', '2026-09-21')

    def test_the_season_shapes_what_is_offered(self):
        pool = {x['id']: x for x in life.palette(self.root)}
        def wrong_season(day, season):
            return sum(1 for i in self.ids(day, 20)
                       if pool[i]['season'] not in ('any', season))
        self.assertLessEqual(wrong_season('2026-12-15', 'winter'), 6)

    def test_nothing_in_the_offer_is_read_out_of_her_prose(self):
        """Recency is a fact about ids. Nothing here inspects what she wrote."""
        source = (ROOT / 'kit/scripts/companion_life.py').read_text(encoding='utf-8')
        block = source[source.index('def suggest('):source.index('def save_tomorrow_plan(')]
        for smell in ('.lower()', ' in text', 'activity.'):
            self.assertNotIn(smell, block, 'suggestion is reading wording again')


class PlanCarriesTheChoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        (self.root / 'routine.json').write_text(json.dumps(
            {'kind': 'imagined_routine', 'routines_catalog': {},
             'daily': [{'start': '12:00', 'end': '13:00', 'activity': 'lunch', 'setting': 'home'}],
             'weekly': []}), encoding='utf-8')

    def test_the_day_says_what_she_chose_to_do(self):
        life.save_tomorrow_plan(self.root, {
            'date': '2026-09-22', 'intent': 'out for the day', 'theme': 'custom',
            'ideas': ['bus-to-the-end', 'cafe-with-a-book']})
        day = life.expected_day(self.root, dt.date(2026, 9, 22),
                                dt.datetime(2026, 9, 21, 22, tzinfo=dt.timezone.utc))
        self.assertEqual([i['title'] for i in day['ideas']],
                         ['take a bus to the end of its route and walk back',
                          'one coffee, one book, no phone, two hours'])

    def test_an_idea_she_invented_does_not_break_the_day(self):
        life.save_tomorrow_plan(self.root, {
            'date': '2026-09-22', 'intent': 'something of my own', 'theme': 'custom',
            'ideas': ['not-a-real-id']})
        day = life.expected_day(self.root, dt.date(2026, 9, 22),
                                dt.datetime(2026, 9, 21, 22, tzinfo=dt.timezone.utc))
        self.assertEqual(day['ideas'], [])
        self.assertEqual(day['intended_plan']['intent'], 'something of my own')


if __name__ == '__main__':
    unittest.main()
