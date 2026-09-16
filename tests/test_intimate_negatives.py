"""The always-on negatives, and the one bucket a companion may set aside.

A companion who has reached Bonded readiness can choose to render without its
workflow's modesty negatives. Everything here exists to prove that the choice
is theirs alone, that it is the *only* thing the switch moves, and that the
safety floor is reachable by no path at all.
"""
import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path[:0] = [str(Path(__file__).resolve().parents[1]),
                str(Path(__file__).resolve().parents[1] / 'kit/scripts')]
import companion_config as cc
import companion_media as media
import companion_workflow as wf


class NegativeCompositionTests(unittest.TestCase):
    """What actually reaches the sampler, bucket by bucket."""

    def preset(self, **over):
        return {'negative': 'blurry, low quality, extra fingers',
                'modesty_negative': 'nude, topless', **over}

    def terms(self, preset, intimate=False):
        return {t.strip().lower() for t in media.negative_prompt(preset, intimate).split(',')}

    def test_the_floor_survives_every_bucket_being_empty(self):
        """A cleared box, or an imported workflow that never had one, changes nothing."""
        for preset in ({}, {'negative': '', 'modesty_negative': ''},
                       {'negative': None, 'modesty_negative': None}):
            for intimate in (False, True):
                terms = self.terms(preset, intimate)
                for floor in media.SAFETY_FLOOR:
                    self.assertIn(floor.lower(), terms,
                                  f'{floor!r} missing with preset={preset} intimate={intimate}')

    def test_only_the_modesty_bucket_is_ever_set_aside(self):
        clothed, intimate = self.terms(self.preset()), self.terms(self.preset(), True)
        # The modesty terms, and nothing else, differ between the two.
        self.assertEqual(clothed - intimate, {'nude', 'topless'})
        self.assertEqual(intimate - clothed, set())
        # Quality and the person's own safety additions survive the switch.
        for kept in ('blurry', 'low quality', 'extra fingers'):
            self.assertIn(kept, intimate)

    def test_the_floor_is_not_a_preset_field(self):
        """Nothing a preset can say removes a floor term, including saying it differently."""
        sneaky = self.preset(negative='', modesty_negative='child, loli')
        self.assertIn('child', self.terms(sneaky, intimate=True))
        self.assertIn('loli', self.terms(sneaky, intimate=True))

    def test_terms_are_not_repeated(self):
        doubled = self.preset(negative='child, blurry, blurry')
        joined = media.negative_prompt(doubled)
        self.assertEqual(joined.lower().count('blurry'), 1)
        self.assertEqual(joined.lower().split(',').count(' child'), 0)

    def test_new_workflows_carry_a_modesty_bucket_and_no_floor_copy(self):
        template = wf.modular_template()
        self.assertTrue(template['modesty_negative'])
        self.assertNotIn('safety_negative', template)
        media.validate({'version': 1, 'presets': [template]})


class NegativeSortingTests(unittest.TestCase):
    """Turning one monolithic negative prompt into the two buckets."""

    def test_a_weight_containing_commas_is_one_term(self):
        """`(white dress, ivory:1.3)` is a weighted group, not two terms."""
        self.assertEqual(
            media.split_terms('(white dress, ivory dress:1.3), lowres, (two people:1.3)'),
            ['(white dress, ivory dress:1.3)', 'lowres', '(two people:1.3)'])

    def test_weights_survive_sorting(self):
        always, modesty = media.sort_negative('(nsfw:1.2), (white dress, ivory:1.3), lowres')
        self.assertEqual(modesty, '(nsfw:1.2)')
        self.assertEqual(always, '(white dress, ivory:1.3), lowres')

    def test_floor_terms_are_dropped_not_copied(self):
        """A copy in a preset invites editing the copy and believing it mattered."""
        always, modesty = media.sort_negative('child, loli, underage, lowres, nude')
        self.assertEqual(always, 'lowres')
        self.assertEqual(modesty, 'nude')

    def test_anatomy_and_wardrobe_stay_always_on(self):
        """Body words are not modesty words; only the listed ones move."""
        always, modesty = media.sort_negative(
            'body horror, contorted body, white clothing, plastic skin, extra legs, bad anatomy')
        self.assertEqual(modesty, '')
        self.assertEqual(len(media.split_terms(always)), 6)

    def test_bare_term_strips_brackets_and_weights_only(self):
        self.assertEqual(media.bare_term('(nsfw:1.2)'), 'nsfw')
        self.assertEqual(media.bare_term('[blurry]'), 'blurry')
        self.assertEqual(media.bare_term('  Nude  '), 'nude')
        # A colon that is not a weight is part of the term.
        self.assertEqual(media.bare_term('style: painterly'), 'style: painterly')

    def test_sorting_loses_nothing_except_the_floor(self):
        source = ('lowres, worst quality, nsfw, nude, (two people:1.3), child, '
                  'bad hands, lingerie, melted clothing')
        always, modesty = media.sort_negative(source)
        recovered = set(media.split_terms(always)) | set(media.split_terms(modesty))
        floor = {t.lower() for t in media.SAFETY_FLOOR}
        expected = {t for t in media.split_terms(source) if media.bare_term(t) not in floor}
        self.assertEqual(recovered, expected)


class IntimacyGateTests(unittest.TestCase):
    """Who may open the switch, and what happens when they may not."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.c = cc.Companion(profile='test', agent='Test', vault=root / 'vault',
                              hermes_root=root / 'hermes', context_mode='fixed')
        self.c.home.mkdir(parents=True); self.c.soul_dir.mkdir(parents=True); self.c.save()
        self.preset = {**wf.modular_template(), 'id': 'p', 'category': 'portrait',
                       'parts': {'quality': 'a portrait'}, 'include_identity': False}

    def compile(self, intimate, ready, blockers=()):
        state = {'intimacy_ready': ready, 'intimacy_blockers': list(blockers)}
        with patch('companion_intimacy.compute', return_value=state):
            return media.compile(self.c, intimate=intimate, draft=self.preset)

    def test_a_closed_gate_refuses_and_says_why(self):
        with self.assertRaises(ValueError) as caught:
            self.compile(True, False, ['Intimacy stage (Chemistry) is not yet at Bonded readiness.'])
        self.assertIn('Bonded readiness', str(caught.exception))

    def test_a_closed_gate_still_renders_the_ordinary_way(self):
        """Refusing the switch must never refuse the picture."""
        result = self.compile(False, False, ['not yet'])
        self.assertFalse(result['intimate'])
        self.assertIn('nude', result['negative'])

    def test_an_open_gate_sets_aside_the_modesty_bucket_only(self):
        result = self.compile(True, True)
        self.assertTrue(result['intimate'])
        self.assertNotIn('nude', result['negative'])
        for floor in media.SAFETY_FLOOR:
            self.assertIn(floor, result['negative'])

    def test_an_unreadable_closeness_state_is_a_closed_gate(self):
        """If the judgement cannot be made, the answer is no, not yes."""
        with patch('companion_intimacy.compute', side_effect=RuntimeError('boom')):
            allowed, blockers = media.intimacy_gate(self.c)
        self.assertFalse(allowed)
        self.assertTrue(blockers)

    def test_a_workflow_with_no_negative_input_cannot_render_intimately(self):
        """The floor has to be able to reach the sampler, or nothing may proceed."""
        self.preset = {**self.preset, 'mappings': {k: v for k, v in self.preset['mappings'].items()
                                                   if k != 'negative'}}
        with self.assertRaisesRegex(ValueError, 'negative prompt input'):
            self.compile(True, True)


if __name__ == '__main__':
    unittest.main()
