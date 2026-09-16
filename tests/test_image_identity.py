"""The stable block of words an image model is sent, and when it goes stale.

A likeness holds still across pictures because the same phrases are sent every
time. So the block is derived once, stamped against the appearance it came
from, and left alone — and when the SOUL moves out from under it, the block
says so rather than quietly rewriting itself.
"""
import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path[:0] = [str(Path(__file__).resolve().parents[1]),
                str(Path(__file__).resolve().parents[1] / 'kit/scripts')]
import companion_config as cc
import companion_image_identity as block
import companion_portrait as portrait

PROSE = ('Nova is a 30-year-old woman with a pale complexion and freckles across her nose. '
         'She has grey eyes and short black hair. She gives the impression of someone calm.')
TAGS = '30 year old woman, pale complexion, freckles across nose, grey eyes, short black hair'


class ImageIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.c = cc.Companion(profile='test', agent='Nova', vault=root / 'vault',
                              hermes_root=root / 'hermes', context_mode='fixed')
        self.c.home.mkdir(parents=True); self.c.soul_dir.mkdir(parents=True); self.c.save()
        self.prose = PROSE
        patcher = patch.object(portrait, 'identity_block',
                               side_effect=lambda c, use_override=True:
                                   block.state(c)['text'] if use_override and block.state(c)['saved']
                                   else self.prose)
        patcher.start(); self.addCleanup(patcher.stop)

    def test_nothing_saved_is_not_the_same_as_out_of_date(self):
        state = block.state(self.c)
        self.assertFalse(state['saved'])
        self.assertFalse(state['stale'], 'an unwritten block is not a stale one')
        self.assertTrue(state['has_appearance'])

    def test_saving_stamps_it_against_the_appearance_it_describes(self):
        state = block.save(self.c, TAGS)
        self.assertTrue(state['saved'])
        self.assertFalse(state['stale'])
        self.assertEqual(state['saved_fingerprint'], state['source_fingerprint'])

    def test_editing_the_appearance_marks_the_block_out_of_date(self):
        block.save(self.c, TAGS)
        self.prose = PROSE.replace('short black hair', 'long silver hair')
        state = block.state(self.c)
        self.assertTrue(state['stale'])
        # Stale means "say something", not "change something".
        self.assertEqual(state['text'], TAGS)

    def test_editing_the_block_by_hand_makes_it_current_again(self):
        block.save(self.c, TAGS)
        self.prose = PROSE.replace('short black hair', 'long silver hair')
        self.assertTrue(block.state(self.c)['stale'])
        state = block.save(self.c, TAGS + ', long silver hair')
        self.assertFalse(state['stale'], 'a person editing it is a person accepting it')

    def test_whitespace_alone_does_not_make_it_stale(self):
        """Reflowing a paragraph is not a change of appearance."""
        block.save(self.c, TAGS)
        self.prose = PROSE.replace(' ', '  ').replace('. ', '.\n')
        self.assertFalse(block.state(self.c)['stale'])

    def test_it_is_what_gets_sent_once_saved(self):
        import companion_media as media
        self.assertIsNone(media.load(self.c).get('identity_override'))
        block.save(self.c, TAGS)
        self.assertEqual(media.effective(self.c)['identity_override'], TAGS)

    def test_following_the_soul_again_forgets_everything(self):
        block.save(self.c, TAGS)
        state = block.follow(self.c)
        self.assertFalse(state['saved'])
        self.assertFalse(state['stale'])
        self.assertEqual(state['saved_fingerprint'], '')

    def test_an_empty_block_is_refused_rather_than_sending_nothing(self):
        with self.assertRaises(ValueError):
            block.save(self.c, '   ')

    def test_tidy_deduplicates_and_caps_length(self):
        self.assertEqual(block.tidy('a, b, a, B'), 'a, b')
        self.assertEqual(block.tidy('  spaced   out  ,  x '), 'spaced out, x')
        long = block.tidy(', '.join(f'phrase number {i}' for i in range(200)))
        self.assertLessEqual(len(long), block.MAX_CHARS)
        self.assertFalse(long.endswith(','), 'truncation must not leave a dangling comma')

    def test_a_model_that_answers_with_prose_is_refused(self):
        """Nothing is written on a reply that did not do the job."""
        with patch.object(block, 'hermes_command', return_value=['true']), \
             patch('subprocess.run') as run:
            run.return_value = type('R', (), {'returncode': 0, 'stdout': 'Sure! Here you go.'})()
            with self.assertRaisesRegex(ValueError, 'did not return JSON'):
                block.propose(self.c)
        self.assertFalse(block.state(self.c)['saved'])

    def test_a_proposal_is_tidied_but_not_saved(self):
        reply = '{"identity": "30 year old woman, grey eyes, grey eyes, short black hair"}'
        with patch.object(block, 'hermes_command', return_value=['true']), \
             patch('subprocess.run') as run:
            run.return_value = type('R', (), {'returncode': 0, 'stdout': reply})()
            out = block.propose(self.c)
        self.assertEqual(out['identity'], '30 year old woman, grey eyes, short black hair')
        self.assertFalse(out['written'])
        self.assertFalse(block.state(self.c)['saved'], 'proposing must not save')


class ImageIdentityRouteTests(unittest.TestCase):
    """These endpoints must not live under /api/identity/.

    `POST /api/identity/{section}` is a wildcard that writes SOUL sections, and
    it swallowed `/api/identity/image-block` whole — the reply was "no such
    section", from a handler that had never heard of this feature.
    """

    def setUp(self):
        from kit.app.server import build
        from fastapi.testclient import TestClient
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.c = cc.Companion(profile='test', agent='Nova', vault=root / 'vault',
                              hermes_root=root / 'hermes', context_mode='fixed')
        self.c.home.mkdir(parents=True); self.c.soul_dir.mkdir(parents=True); self.c.save()
        self.client = TestClient(build(self.c.home, token='secret', state_dir=root / 'state'))
        self.addCleanup(self.client.close)

    def head(self):
        return {'x-companion-token': 'secret'}

    def test_reading_and_writing_reach_their_own_handler(self):
        got = self.client.get('/api/image-identity', headers=self.head())
        self.assertEqual(got.status_code, 200)
        self.assertIn('stale', got.json())
        with patch.object(portrait, 'identity_block', return_value=PROSE):
            put = self.client.post('/api/image-identity', json={'text': TAGS}, headers=self.head())
        self.assertEqual(put.status_code, 200, put.text)
        self.assertTrue(put.json()['saved'])

    def test_no_route_hides_behind_the_section_wildcard(self):
        paths = {r.path for r in self.client.app.routes if hasattr(r, 'path')}
        self.assertIn('/api/image-identity', paths)
        for path in paths:
            self.assertFalse(path.startswith('/api/identity/image'),
                             f'{path} sits under the section wildcard and will be swallowed')


class PromptPartsTests(unittest.TestCase):
    """The recorded moment, split into the boxes a workflow actually has."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.c = cc.Companion(profile='test', agent='Nova', vault=root / 'vault',
                              hermes_root=root / 'hermes', context_mode='fixed')
        self.c.home.mkdir(parents=True); self.c.soul_dir.mkdir(parents=True); self.c.save()

    def record(self, **state):
        return {'state': {'activity': 'reading', 'location': 'the kitchen',
                          'outfit': [{'description': 'grey sweater'}, {'description': 'jeans'}],
                          **state}}

    def test_the_outfit_leaves_the_scene_and_becomes_the_wardrobe(self):
        with patch.object(portrait, 'identity_block', return_value=TAGS):
            parts = portrait.prompt_parts(self.c, self.record())
        self.assertEqual(parts['wardrobe'], 'grey sweater, jeans')
        self.assertEqual(parts['scene'], 'reading, the kitchen')
        self.assertNotIn('sweater', parts['scene'], 'the outfit has its own box now')
        self.assertNotIn('wearing', parts['scene'])

    def test_a_recorded_light_beats_the_guess(self):
        with patch.object(portrait, 'identity_block', return_value=TAGS):
            parts = portrait.prompt_parts(self.c, self.record(visual={'lighting': 'candlelight',
                                                                      'framing': 'close-up'}))
        self.assertEqual(parts['lighting'], 'candlelight')
        self.assertEqual(parts['camera'], 'close-up')

    def test_lighting_is_guessed_from_the_clock_and_the_place(self):
        import datetime as dt
        noon = dt.datetime(2026, 6, 1, 13, 0)
        night = dt.datetime(2026, 6, 1, 23, 0)
        self.assertEqual(portrait.lighting_guess(self.c, 'on the beach', noon), 'midday daylight')
        self.assertIn('through a window', portrait.lighting_guess(self.c, 'the kitchen', noon))
        self.assertEqual(portrait.lighting_guess(self.c, 'the bedroom', night), 'warm indoor lamplight')
        self.assertIn('night', portrait.lighting_guess(self.c, 'the street', night))

    def test_an_outdoor_word_wins_over_an_indoor_one(self):
        """"Driving home" is a car on a highway: the sky is what lights it."""
        import datetime as dt
        noon = dt.datetime(2026, 6, 1, 13, 0)
        self.assertEqual(portrait.lighting_guess(self.c, 'in the car on the highway', noon),
                         'midday daylight')

    def test_a_location_is_not_given_a_preposition_it_already_has(self):
        """Locations are recorded however they were written."""
        for place, expected in (('the kitchen', 'reading, in the kitchen'),
                                ('in the car', 'reading, in the car'),
                                ('on the beach', 'reading, on the beach'),
                                ('at work', 'reading, at work'),
                                ('', 'reading')):
            scene, _ = portrait.scene_block(self.c, {'state': {'activity': 'reading',
                                                              'location': place, 'outfit': []}})
            self.assertEqual(scene, expected)

    def test_no_recorded_moment_still_returns_every_box(self):
        with patch.object(portrait, 'identity_block', return_value=TAGS):
            parts = portrait.prompt_parts(self.c, {})
        self.assertEqual(set(parts), {'identity', 'scene', 'wardrobe', 'lighting', 'camera'})
        self.assertEqual(parts['identity'], TAGS)
        self.assertEqual(parts['scene'], '')


if __name__ == '__main__':
    unittest.main()


class ReleaseManifestTests(unittest.TestCase):
    """Every module the running kit imports has to be in the shipped file list.

    Four were not, including companion_intimacy — which two call sites import
    without catching ImportError, so a release install would have crashed on
    the first context build rather than degrading. An installed kit is the only
    kit most people will ever have.
    """

    def test_every_imported_companion_module_ships(self):
        import ast, json
        root = Path(__file__).resolve().parents[1]
        shipped = set(json.loads((root / 'release-files.json').read_text()))
        scripts = root / 'kit/scripts'
        available = {f.stem for f in scripts.glob('companion_*.py')}
        wanted = set()
        for source in list(scripts.glob('*.py')) + list((root / 'kit/app').glob('*.py')):
            if source.name.startswith('test_'):
                continue
            tree = ast.parse(source.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    wanted |= {a.name for a in node.names if a.name in available}
                elif isinstance(node, ast.ImportFrom) and node.module in available:
                    wanted.add(node.module)
                # companion_bars reaches for it as __import__('companion_intimacy')
                elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                      and node.func.id == '__import__' and node.args
                      and isinstance(node.args[0], ast.Constant)
                      and node.args[0].value in available):
                    wanted.add(node.args[0].value)
        missing = sorted(m for m in wanted if f'kit/scripts/{m}.py' not in shipped)
        self.assertEqual(missing, [], 'imported but not in release-files.json: ' + ', '.join(missing))

    def test_the_manifest_only_lists_files_that_exist(self):
        """A deleted file left in the list fails the release build, not a test."""
        import json
        root = Path(__file__).resolve().parents[1]
        names = json.loads((root / 'release-files.json').read_text())
        self.assertEqual(sorted(n for n in names if not (root / n).exists()), [])
        self.assertEqual(len(names), len(set(names)), 'the manifest lists something twice')
