"""Each box describes one thing, and nothing describes it twice.

The recorded path built the scene box from the joined single-prompt line, which
already carried the outfit, the light and the framing, and then set those again
as their own boxes. So a wardrobe the model was told to "SHOW EXACTLY" was also
sitting inside the scene, and the framing appeared three times: its own box, the
scene, and the tag list.
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

UTC = dt.timezone.utc
WARDROBE = 'dusty blue oversized slouchy sleep tee with micro cotton shorts'
LIGHTING = 'low pre-dawn darkness with no artificial light'
FRAMING = 'quiet bedroom from bedside height'
POSE = 'lying under the covers, still and listening'


class SectionsDoNotBleedTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = pathlib.Path(tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex', profile='n',
                              hermes_root=base / 'h', vault=base / 'v')
        self.c.home.mkdir(parents=True); self.c.life.mkdir(parents=True); self.c.save()
        self.record = {'id': 'x', 'recorded_at': '2026-09-21T06:00:00+00:00', 'state': {
            'activity': 'waiting for morning', 'location': 'bedroom',
            'outfit': [{'id': 'pj', 'description': WARDROBE}],
            'mood': 'sleepy', 'wants': [],
            'visual': {'pose': POSE, 'framing': FRAMING, 'lighting': LIGHTING}}}

    def parts(self):
        return portrait.recorded_overrides(self.c, self.record)

    def test_the_wardrobe_is_described_in_one_place(self):
        parts = self.parts()
        self.assertEqual(parts['wardrobe'], WARDROBE)
        self.assertNotIn(WARDROBE, parts['scene'], 'the outfit is inside the scene as well')

    def test_the_light_and_the_framing_keep_to_their_own_boxes(self):
        parts = self.parts()
        self.assertEqual(parts['lighting'], LIGHTING)
        self.assertEqual(parts['camera'], FRAMING)
        self.assertNotIn(LIGHTING, parts['scene'])
        self.assertNotIn(FRAMING, parts['scene'])

    def test_what_she_is_doing_stays_with_the_scene(self):
        """Separating the boxes must not drop the pose on the floor."""
        parts = self.parts()
        self.assertIn('waiting for morning', parts['scene'])
        self.assertIn('bedroom', parts['scene'])
        self.assertIn(POSE, parts['scene'])

    def test_no_section_repeats_another(self):
        parts = self.parts()
        values = {k: v for k, v in parts.items() if v}
        for name, text in values.items():
            for other, body in values.items():
                if name == other:
                    continue
                with self.subTest(section=name, inside=other):
                    self.assertNotIn(text, body, f'{name} is repeated inside {other}')

    def test_the_recorded_path_and_the_parts_helper_agree(self):
        """Two functions splitting the same moment is how they drifted apart."""
        split = portrait.recorded_parts(self.c, self.record)
        overrides = self.parts()
        for key in ('scene', 'wardrobe', 'lighting', 'camera', 'feeling'):
            with self.subTest(key=key):
                self.assertEqual(overrides.get(key, ''), split.get(key, ''))

    def test_the_single_line_form_still_carries_everything(self):
        """`scene_block` is for workflows with one box; it must stay complete."""
        line, _ = portrait.scene_block(self.c, self.record)
        for piece in ('waiting for morning', 'bedroom', WARDROBE):
            self.assertIn(piece, line)


if __name__ == '__main__':
    unittest.main()


class WardrobeWinsOverAGeneralDescriptionTests(unittest.TestCase):
    """An appearance description often says what someone usually wears.

    That sentence then argues with the outfit recorded for this particular moment:
    IDENTITY says sweats and hoodies while WARDROBE says a sleep tee, and the model
    is left to pick. Which sentences of someone's own description are about clothes
    is not a thing to guess at, so the contract says plainly which section wins.
    """

    def build(self, identity, wardrobe):
        import companion_media as media
        labels = {'identity': 'IDENTITY — KEEP CONSISTENT', 'wardrobe': 'WARDROBE — SHOW EXACTLY'}
        parts = {'identity': identity, 'wardrobe': wardrobe}
        preamble = 'Create one coherent image. Treat every section below as a separate visual constraint.'
        if parts.get('identity', '').strip() and parts.get('wardrobe', '').strip():
            preamble += (' Where IDENTITY mentions clothing in general, WARDROBE is what she is'
                         ' wearing now and overrides it.')
        return preamble

    def test_precedence_is_stated_when_both_sections_exist(self):
        self.assertIn('WARDROBE is what she is wearing now',
                      self.build('she is small-framed; her default is sweats', 'a sleep tee'))

    def test_nothing_is_claimed_when_there_is_no_wardrobe_to_prefer(self):
        self.assertNotIn('overrides it', self.build('she is small-framed', ''))

    def test_the_rule_lives_in_the_compiler(self):
        media = (pathlib.Path(__file__).resolve().parents[1] / 'kit/scripts/companion_media.py').read_text(encoding='utf-8')
        self.assertIn('WARDROBE is what she is', media)
        # Deciding this by looking for clothing words in someone's description is the
        # habit this codebase keeps having to undo.
        self.assertNotIn("for w in ('sweat','hoodie'", media)
