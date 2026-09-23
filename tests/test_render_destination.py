"""Where a render lands, and why that is a question worth asking.

A picture the companion made because she was asked for one -- show me your
favourite animal at the zoo -- is a creation. A picture from the capture routine
is a look at what she is doing all day, which belongs to the timeline and to
whatever albums it is kept in. They were both written into Creations, and the
timeline then copied what it needed, so every automatic moment existed twice:
filed as her work, and duplicated as a byte-identical second file that the
library had to reconcile back into one photo.
"""
import datetime as dt
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

import companion_config as cc
import companion_media as media
import companion_media_review as review
import companion_timeline as timeline
from kit.app.content import catalog

UTC = dt.timezone.utc


class RenderDestinationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex', profile='nova',
                              hermes_root=base / 'hermes', vault=base / 'vault',
                              context_mode='fixed')
        self.c.home.mkdir(parents=True)
        self.c.soul_dir.mkdir(parents=True)
        self.c.image_timeline = True
        self.c.image_style = 'realistic'
        self.c.save()

    # -- a render, with the provider replaced by a picture of a known colour --

    def render(self, purpose, colour='blue', held=False, allow_nsfw=False):
        import io
        from PIL import Image
        buffer = io.BytesIO()
        Image.new('RGB', (12, 12), colour).save(buffer, format='PNG')
        raw = buffer.getvalue()
        compiled = {'preset': {'id': 'p', 'name': 'Test', 'provider': 'hermes',
                               'category': 'portrait', 'endpoint': ''},
                    'prompt': 'a prompt', 'structured_prompt': 'a prompt',
                    'prompts': {}, 'parts': {'scene': 'a scene'}, 'seed': 1,
                    'reference_image': None, 'workflow': {}}
        prefs = dict(review.preferences(self.c), review_before_delivery=held)
        with patch.object(media, 'compile', return_value=compiled), \
             patch.object(media, 'hermes_bridge', return_value={'success': True, 'image': 'x'}), \
             patch.object(timeline, 'load_image', return_value=(raw, 'png')), \
             patch.object(media, 'load_image', create=True, return_value=(raw, 'png')), \
             patch.object(review, 'preferences', return_value=prefs), \
             patch.object(review, 'inspect', return_value={'status': 'held', 'reason': 'unsure'}):
            return media.generate(self.c, 'p', 'portrait',
                                  allow_nsfw=allow_nsfw, purpose=purpose)

    def paths(self, folder):
        d = self.c.data / folder
        return sorted(p.name for p in d.glob('*')) if d.is_dir() else []

    def images_in(self, folder):
        return [n for n in self.paths(folder) if n.endswith('.png')]

    # -- creations -----------------------------------------------------------

    def test_a_creation_lands_in_creations_and_nowhere_else(self):
        result = self.render('creation')
        self.assertTrue(result['path'].endswith('.png'))
        self.assertIn('creations/image-studio', result['path'])
        self.assertEqual(len(self.images_in('creations/image-studio')), 1)
        self.assertEqual(self.images_in('image-timeline/images'), [])

    def test_creation_is_the_default_so_nothing_silently_becomes_a_capture(self):
        import inspect as _inspect
        self.assertEqual(_inspect.signature(media.generate).parameters['purpose'].default,
                         'creation')

    def test_a_render_is_a_creation_or_a_capture_and_nothing_else(self):
        with self.assertRaises(ValueError):
            self.render('whatever')

    # -- captures ------------------------------------------------------------

    def test_a_capture_is_rendered_out_of_sight_of_creations(self):
        result = self.render('capture')
        self.assertEqual(self.images_in('creations/image-studio'), [])
        self.assertEqual(pathlib.Path(result['path']).parent, media.scratch_dir(self.c))

    def test_the_scratch_render_is_invisible_to_the_library(self):
        """An in-flight render is not a photo, and a discarded one never becomes one."""
        self.render('capture')
        self.assertEqual(catalog(self.c, kind='image')['items'], [])

    def test_handing_a_capture_to_the_timeline_leaves_one_copy(self):
        import companion_presence as presence
        now = dt.datetime(2026, 9, 21, 12, tzinfo=UTC)
        presence.update_wardrobe(self.c, [{'id': 'tee', 'description': 'simple tee', 'use': 'day'}])
        presence.update(self.c, {'previous_id': None, 'outfit': ['tee'], 'location': 'zoo',
                                 'activity': 'watching the otters', 'mood': 'delighted',
                                 'text': 'At the zoo.'}, now)
        prepared = timeline.prepare(self.c, now)
        self.assertTrue(prepared['ready'], prepared)

        result = self.render('capture')
        timeline.save(self.c, prepared['capture_id'], result['path'], 'Test Provider', now)
        media.discard_scratch(result['path'])

        self.assertEqual(len(self.images_in('image-timeline/images')), 1)
        self.assertEqual(self.images_in('creations/image-studio'), [])
        self.assertEqual(self.paths('image-timeline/' + media.SCRATCH), [])

        items = catalog(self.c, kind='image')['items']
        self.assertEqual(len(items), 1, 'one moment is one photo')
        self.assertEqual([c['source'] for c in items[0]['copies']], ['photo session'])

    # -- the one capture that is kept ---------------------------------------

    def test_a_held_capture_is_surfaced_so_somebody_can_look_at_it(self):
        """Everything else about a capture is out of sight; a withheld picture
        is exactly the one a person has to be able to find."""
        # allow_nsfw, so the hold is re-raised as itself rather than sent round
        # the clothed-replacement path, which is a different behaviour entirely.
        from unittest.mock import patch
        with self.assertRaises(media.ImageHeld) as caught, \
                patch.object(media, 'adult_ready', return_value=(True, [])):
            self.render('capture', held=True, allow_nsfw=True)
        held = caught.exception.path
        self.assertEqual(pathlib.Path(held).parent, self.c.data / 'creations/image-studio')
        self.assertTrue(pathlib.Path(held).is_file())
        self.assertEqual(self.paths('image-timeline/' + media.SCRATCH), [])
        self.assertEqual(len(catalog(self.c, kind='image')['items']), 1)

    # -- housekeeping --------------------------------------------------------

    def test_an_abandoned_render_is_cleared_rather_than_hoarded(self):
        import os, time
        result = self.render('capture')
        path = pathlib.Path(result['path'])
        self.assertTrue(path.is_file())
        old = time.time() - 7 * 3600
        os.utime(path, (old, old))
        self.assertEqual(media.prune_scratch(self.c), 1)
        self.assertFalse(path.exists())

    def test_a_render_still_in_flight_is_left_alone(self):
        result = self.render('capture')
        self.assertEqual(media.prune_scratch(self.c), 0)
        self.assertTrue(pathlib.Path(result['path']).is_file())

    def test_discard_refuses_to_touch_anything_outside_the_scratch_folder(self):
        result = self.render('creation')
        self.assertFalse(media.discard_scratch(result['path']))
        self.assertTrue(pathlib.Path(result['path']).is_file())


if __name__ == '__main__':
    unittest.main()
