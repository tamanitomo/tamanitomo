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
        return {'negative': 'blurry, low quality', 'safety_negative': 'extra fingers',
                'modesty_negative': 'nude, topless', **over}

    def terms(self, preset, intimate=False):
        return {t.strip().lower() for t in media.negative_prompt(preset, intimate).split(',')}

    def test_the_floor_survives_every_bucket_being_empty(self):
        """A cleared box, or an imported workflow that never had one, changes nothing."""
        for preset in ({}, {'negative': '', 'safety_negative': '', 'modesty_negative': ''},
                       {'safety_negative': None, 'modesty_negative': None}):
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
        sneaky = self.preset(safety_negative='', negative='', modesty_negative='child, loli')
        self.assertIn('child', self.terms(sneaky, intimate=True))
        self.assertIn('loli', self.terms(sneaky, intimate=True))

    def test_terms_are_not_repeated(self):
        doubled = self.preset(safety_negative='child, blurry', negative='blurry')
        joined = media.negative_prompt(doubled)
        self.assertEqual(joined.lower().count('blurry'), 1)
        self.assertEqual(joined.lower().split(',').count(' child'), 0)

    def test_new_workflows_carry_a_modesty_bucket_and_no_floor_copy(self):
        template = wf.modular_template()
        self.assertTrue(template['modesty_negative'])
        self.assertEqual(template['safety_negative'], '')
        media.validate({'version': 1, 'presets': [template]})


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
