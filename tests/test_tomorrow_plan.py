"""What she means to do tomorrow, stated rather than guessed at.

The theme of an intended day is not a label on it: it replaces the whole day's
anchors with a scripted set, so a wrong one rewrites her day. It was picked by
looking for words in the sentence she wrote, which is the prose-keying this
codebase has been bitten by four times already. Every one of these was wrong:

    "an interest, creative project"  -> slow_rest_day   ("interest" contains "rest")
    "I would rather not go to the beach" -> beach_day   (negation is invisible)
    "finish the woodworking workshop"    -> shopping    ("workshop" contains "shop")
    "dinner at that restaurant"          -> slow_rest_day
    "a walk in the forest"               -> slow_rest_day
"""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

import companion_life as life
import companion_local_pulse as pulse

CATALOG = {
    'beach_day': {'anchors': [{'start': '10:00', 'end': '16:00',
                               'activity': 'the beach', 'setting': 'the coast'}]},
    'slow_rest_day': {'anchors': [{'start': '10:00', 'end': '16:00',
                                   'activity': 'rest', 'setting': 'home'}]},
}
ROUTINE = {'kind': 'imagined_routine', 'routines_catalog': CATALOG,
           'daily': [{'start': '12:00', 'end': '13:00', 'activity': 'lunch', 'setting': 'home'}],
           'weekly': []}


class ThemeIsChosenNotInferredTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        (self.root / 'routine.json').write_text(json.dumps(ROUTINE), encoding='utf-8')

    def save(self, **plan):
        return life.save_tomorrow_plan(self.root, {'date': '2026-09-22', **plan})

    def test_the_themes_offered_are_the_ones_she_actually_has(self):
        self.assertEqual(life.themes(self.root), ['custom', 'beach_day', 'slow_rest_day'])

    def test_a_theme_she_did_not_choose_is_refused_rather_than_guessed(self):
        with self.assertRaises(ValueError) as caught:
            self.save(intent='a day at the beach', theme='beach_vibes')
        self.assertIn('beach_day', str(caught.exception), 'the refusal should say what is valid')

    def test_the_wording_of_an_intention_never_selects_a_theme(self):
        """The whole point. Each of these once chose a theme by substring."""
        for intent in ('an interest, creative project, planned class',
                       'I would rather not go to the beach tomorrow',
                       'finish the woodworking workshop project',
                       'dinner at that restaurant',
                       'a walk in the forest'):
            with self.subTest(intent=intent):
                saved = self.save(intent=intent)
                self.assertEqual(saved['theme'], 'custom',
                                 'a theme was inferred from the sentence again')

    def test_custom_keeps_her_ordinary_day_while_recording_the_intention(self):
        self.save(intent='nothing special, a quiet one', theme='custom')
        day = life.expected_day(self.root, dt.date(2026, 9, 22),
                                dt.datetime(2026, 9, 21, 22, tzinfo=dt.timezone.utc))
        self.assertEqual([a['activity'] for a in day['anchors']], ['lunch'])
        self.assertEqual(day['intended_plan']['intent'], 'nothing special, a quiet one')

    def test_a_theme_she_did_choose_reshapes_the_day(self):
        self.save(intent='I want to go to the coast', theme='beach_day')
        day = life.expected_day(self.root, dt.date(2026, 9, 22),
                                dt.datetime(2026, 9, 21, 22, tzinfo=dt.timezone.utc))
        self.assertEqual(day['source'], 'intended')
        self.assertEqual([a['activity'] for a in day['anchors']], ['the beach'])

    def test_a_plan_with_no_intention_is_not_a_plan(self):
        for empty in ('', '   ', None, {'activity': 'beach'}):
            with self.subTest(intent=empty):
                with self.assertRaises(ValueError):
                    self.save(intent=empty, theme='custom')

    def test_a_missing_theme_defaults_to_keeping_her_ordinary_day(self):
        self.assertEqual(self.save(intent='an ordinary one')['theme'], 'custom')


class LayingOutClothesTests(unittest.TestCase):
    """Nightwear is excluded by what the wardrobe records it as, not by its name.

    It was excluded by looking for "pajama" or "sleep" anywhere in the stringified
    item, which both keeps nightwear that is named something else and discards day
    clothes that happen to mention it.
    """

    WARDROBE = [
        {'id': 'day-tee', 'category': 'day'},
        {'id': 'pj-set', 'category': 'sleep'},
        {'id': 'nightgown', 'category': 'sleep'},
        {'id': 'pajama-print-lounge-tee', 'category': 'day'},
    ]

    def test_nightwear_is_left_behind_whatever_it_is_called(self):
        out = pulse.lay_out(['day-tee', 'pj-set', 'nightgown'], self.WARDROBE)
        self.assertEqual(out, ['day-tee'])

    def test_a_day_garment_is_kept_even_if_its_name_says_pajama(self):
        out = pulse.lay_out(['pajama-print-lounge-tee'], self.WARDROBE)
        self.assertEqual(out, ['pajama-print-lounge-tee'])

    def test_items_may_arrive_as_records_or_as_ids(self):
        out = pulse.lay_out([{'id': 'day-tee'}, 'day-tee'], self.WARDROBE)
        self.assertEqual(out, ['day-tee'], 'the same garment twice is still one garment')

    def test_nothing_chosen_is_nothing_laid_out(self):
        self.assertEqual(pulse.lay_out(None, self.WARDROBE), [])


class WindDownAsksForTomorrowTests(unittest.TestCase):
    """The end of a day is the only moment anything looks past it."""

    WARDROBE = [{'id': 'day-tee', 'category': 'day'}]

    def test_the_theme_is_an_enum_of_her_own_day_shapes(self):
        schema = pulse.schema(self.WARDROBE, False, ['custom', 'beach_day'])
        field = schema['properties']['tomorrow']['anyOf'][0]
        self.assertEqual(field['properties']['theme']['enum'], ['custom', 'beach_day'])
        self.assertIn('tomorrow', schema['required'])

    def test_meaning_nothing_in_particular_is_expressible(self):
        schema = pulse.schema(self.WARDROBE, False, ['custom'])
        self.assertIn({'type': 'null'}, schema['properties']['tomorrow']['anyOf'])

    def test_an_ordinary_tick_is_not_asked_to_plan_tomorrow(self):
        self.assertNotIn('tomorrow', pulse.schema(self.WARDROBE, False, None)['properties'])

    def test_the_old_string_reading_of_next_is_gone(self):
        """`next` has been an object for some time; reading it as a string raised."""
        source = (ROOT / 'kit/scripts/companion_local_pulse.py').read_text(encoding='utf-8')
        self.assertNotIn(".get('next','').lower()", source)
        for word in ("'beach' in", "'ramen' in", "'shop' in", "'rest' in"):
            self.assertNotIn(word, source, 'the substring classifier is back')


if __name__ == '__main__':
    unittest.main()
