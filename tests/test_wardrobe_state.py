"""Undress is a fact the record carries, not something a reader guesses from prose.

Inferring it from `activity` and `location` substrings stripped the clothes off
anyone brushing their teeth in the bathroom, sunbathing, or shopping for a bathing
suit -- while the record plainly said what she was wearing. The same habit applied
to public places read "homework" as work and "texting friends" as company, and
refused a change of clothes in her own bedroom.
"""
import datetime as dt
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

import companion_config as cc
import companion_portrait as portrait
import companion_presence as presence

UTC = dt.timezone.utc
DRESSED = [{'id': 'tee', 'description': 'a green cotton tee'}, {'id': 'jeans', 'description': 'blue jeans'}]
TOWEL = [{'id': 'towel', 'description': 'wrapped in a bath towel'}]
NUDE = [{'id': 'nude', 'description': 'undressed'}]


class WardrobeIsReadFromTheRecordTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = pathlib.Path(tmp.name)
        self.c = cc.Companion(agent='A', human='Z', profile='p',
                              hermes_root=base / 'h', vault=base / 'v')
        self.c.home.mkdir(parents=True); self.c.life.mkdir(parents=True); self.c.save()

    def rec(self, activity, location, outfit):
        return {'id': 'x', 'recorded_at': '2026-09-21T10:00:00-04:00',
                'state': {'activity': activity, 'location': location, 'outfit': outfit,
                          'mood': 'fine', 'visual': {}}}

    def test_a_word_in_the_sentence_never_undresses_her(self):
        """Every one of these stripped a fully dressed record."""
        for activity, location in (('brushing teeth', 'the bathroom'),
                                   ('cleaning the bathroom', 'home'),
                                   ('sunbathing on the deck', 'the back garden'),
                                   ('putting on a bathrobe', 'the bedroom'),
                                   ('shopping for a bathing suit', 'the mall')):
            scene, _ = portrait.scene_block(self.c, self.rec(activity, location, DRESSED))
            with self.subTest(activity=activity):
                self.assertIn('a green cotton tee', scene)

    def test_the_recorded_tokens_do_undress_her(self):
        for outfit, expected in ((NUDE, ''), ([], ''), (TOWEL, 'wrapped in a bath towel')):
            parts = portrait.prompt_parts(self.c, self.rec('showering', 'the bathroom', outfit))
            with self.subTest(outfit=outfit):
                self.assertEqual(parts['wardrobe'], expected)

    def test_the_towel_reads_as_a_sentence(self):
        scene, _ = portrait.scene_block(self.c, self.rec('drying off', 'the bedroom', TOWEL))
        self.assertIn('wrapped in a bath towel', scene)
        self.assertNotIn('wearing wrapped', scene)

    def test_both_prompt_paths_agree_about_how_dressed_she_is(self):
        """Three copies of the rule meant the towel survived one path and not another,
        so which preset you used decided whether she had anything on."""
        for outfit in (DRESSED, TOWEL, NUDE, []):
            record = self.rec('stepping out of the shower', 'the bathroom', outfit)
            scene, _ = portrait.scene_block(self.c, record)
            wardrobe = portrait.prompt_parts(self.c, record)['wardrobe']
            with self.subTest(outfit=outfit):
                if wardrobe:
                    self.assertIn(wardrobe, scene)
                else:
                    self.assertNotIn('wearing', scene)


class PublicIsAPlaceNotAWordTests(unittest.TestCase):
    def test_her_own_home_stays_private_whatever_she_is_doing(self):
        for location, activity in (('the spare room', 'working from home'),
                                   ('my home office', 'answering email'),
                                   ('the bedroom', 'doing homework'),
                                   ('the bedroom', 'texting friends'),
                                   ('the kitchen', 'making lunch'),
                                   ('the bathroom', 'showering after a walk')):
            with self.subTest(location=location, activity=activity):
                self.assertFalse(presence.in_public(location, activity))

    def test_actually_being_out_is_still_public(self):
        for location in ('the office', 'the park', 'the mall', 'the library', 'a cafe', 'the train'):
            with self.subTest(location=location):
                self.assertTrue(presence.in_public(location, 'out and about'))

    def test_changing_in_private_is_allowed_and_in_public_is_not(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = pathlib.Path(tmp.name)
        c = cc.Companion(agent='A', human='Z', profile='p', hermes_root=base / 'h', vault=base / 'v')
        c.home.mkdir(parents=True); c.life.mkdir(parents=True); c.save()
        presence.update_wardrobe(c, [{'id': 'bra', 'description': 'plain bra', 'use': 'underwear',
                                      'category': 'underwear'}])
        now = dt.datetime(2026, 9, 21, 10, tzinfo=UTC)
        base_row = {'previous_id': None, 'outfit': ['bra'], 'mood': 'fine', 'text': 'x'}
        presence.update(c, {**base_row, 'location': 'the bedroom', 'activity': 'texting friends'}, now)
        previous = presence.current(c)
        with self.assertRaisesRegex(ValueError, 'private setting'):
            presence.update(c, {**base_row, 'previous_id': previous['id'], 'location': 'the library',
                                'activity': 'reading', 'transition': 'Went out.'},
                            now + dt.timedelta(minutes=30))


if __name__ == '__main__':
    unittest.main()
