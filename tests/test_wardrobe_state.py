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
            parts = portrait.recorded_parts(self.c, self.rec(activity, location, DRESSED))
            with self.subTest(activity=activity):
                self.assertIn('a green cotton tee', parts['wardrobe'])

    def test_the_recorded_tokens_do_undress_her(self):
        for outfit, expected in ((NUDE, ''), ([], ''), (TOWEL, 'wrapped in a bath towel')):
            parts = portrait.prompt_parts(self.c, self.rec('showering', 'the bathroom', outfit))
            with self.subTest(outfit=outfit):
                self.assertEqual(parts['wardrobe'], expected)

    def test_the_towel_reads_as_a_sentence(self):
        from companion_presence import wardrobe_clause
        parts = portrait.recorded_parts(self.c, self.rec('drying off', 'the bedroom', TOWEL))
        clause = wardrobe_clause(parts['wardrobe'])
        self.assertEqual(clause, 'wrapped in a bath towel')
        self.assertNotIn('wearing wrapped', clause)

    def test_both_prompt_paths_agree_about_how_dressed_she_is(self):
        """Three copies of the rule meant the towel survived one path and not another,
        so which preset you used decided whether she had anything on."""
        for outfit in (DRESSED, TOWEL, NUDE, []):
            record = self.rec('stepping out of the shower', 'the bathroom', outfit)
            with self.subTest(outfit=outfit):
                self.assertEqual(portrait.recorded_parts(self.c, record)['wardrobe'],
                                 portrait.prompt_parts(self.c, record)['wardrobe'])

    def test_the_scene_is_only_the_scene(self):
        """Camera, light and clothing each have a box; the scene is where she is
        and what she is doing, and nothing else."""
        record = self.rec('drying off', 'the bedroom', TOWEL)
        record['state']['visual'] = {'framing': 'close from the doorway',
                                     'lighting': 'warm bulb overhead',
                                     'pose': 'towelling her hair'}
        scene, _ = portrait.scene_block(self.c, record)
        self.assertIn('drying off', scene)
        self.assertIn('towelling her hair', scene)
        for elsewhere in ('wrapped in a bath towel', 'close from the doorway', 'warm bulb overhead'):
            self.assertNotIn(elsewhere, scene, elsewhere)


class PublicIsAPlaceNotAWordTests(unittest.TestCase):
    """Public is a field she declares. The words of the location never decide it."""
    def test_the_declaration_decides_whatever_the_words_say(self):
        for location in ('the Home Depot', 'a public bathroom at the mall', 'my home office',
                         'the bedroom', 'the office'):
            with self.subTest(location=location):
                self.assertTrue(presence.in_public({'location': location, 'setting': 'public'}))
                self.assertFalse(presence.in_public({'location': location, 'setting': 'private'}))
                # Undeclared is not public -- and, separately, never counts as private.
                self.assertFalse(presence.in_public({'location': location}))

    def test_words_only_flag_an_obvious_contradiction(self):
        for location in ('the park', 'the mall', 'a cafe', 'the train'):
            with self.subTest(location=location):
                self.assertTrue(presence.reads_public(location))
        # "carpool" is not a pool, and a changing room at the mall is the private part of it.
        for location in ('stuck in the carpool lane', 'a changing room at the mall', 'the bedroom'):
            with self.subTest(location=location):
                self.assertFalse(presence.reads_public(location))

    def test_changing_in_private_is_allowed_and_in_public_is_not(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = pathlib.Path(tmp.name)
        c = cc.Companion(agent='A', human='Z', profile='p', hermes_root=base / 'h', vault=base / 'v')
        c.home.mkdir(parents=True); c.life.mkdir(parents=True); c.save()
        presence.update_wardrobe(c, [{'id': 'bra', 'description': 'plain bra', 'use': 'underwear',
                                      'category': 'underwear'}])
        now = dt.datetime(2026, 9, 21, 10, tzinfo=UTC)
        base_row = {'previous_id': None, 'outfit': ['bra'], 'mood': 'fine', 'text': 'x'}
        presence.update(c, {**base_row, 'location': 'the bedroom', 'activity': 'texting friends',
                            'setting': 'private'}, now)
        previous = presence.current(c)
        self.assertEqual(previous['state']['setting'], 'private')
        moved = {**base_row, 'previous_id': previous['id'], 'location': 'the library',
                 'activity': 'reading', 'transition': 'Went out.'}
        with self.assertRaisesRegex(ValueError, 'private setting'):
            presence.update(c, {**moved, 'setting': 'public'}, now + dt.timedelta(minutes=30))
        # Moving on without saying where she is now does not inherit "private".
        with self.assertRaisesRegex(ValueError, 'say where you are'):
            presence.update(c, moved, now + dt.timedelta(minutes=30))
        # A declaration that contradicts a plainly public place is asked about.
        with self.assertRaisesRegex(ValueError, 'reads as a public place'):
            presence.update(c, {**moved, 'setting': 'private'}, now + dt.timedelta(minutes=30))


if __name__ == '__main__':
    unittest.main()
