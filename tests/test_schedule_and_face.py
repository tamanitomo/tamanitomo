"""The companion's expected day, and whose face the home screen shows.

Four faults that all amount to the app knowing something and not showing it:
the chosen visual style never reached the prompt, the profile photo was not the
profile photo, a blurred picture was used as the hero and merely blurred in
place, and a companion with a full imagined week showed an empty calendar.
"""
import datetime as dt
import json
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

import companion_config as cc
import companion_life as life
import companion_media as media
from kit.app.server import build
from fastapi.testclient import TestClient

ROUTINE = {
    'kind': 'imagined_routine',
    'daily': [
        {'start': '08:00', 'end': '09:30', 'activity': 'wake and breakfast', 'setting': 'home'},
        {'start': '12:00', 'end': '13:00', 'activity': 'lunch', 'setting': 'home'},
        {'start': '22:00', 'end': '23:30', 'activity': 'wind down', 'setting': 'home'},
    ],
    'weekly': [
        {'day': 'tuesday', 'start': '09:00', 'end': '10:00', 'activity': 'Pilates',
         'setting': 'a fictional local class'},
        {'day': 'saturday', 'start': '11:00', 'end': '13:00', 'activity': 'farmers market',
         'setting': 'downtown'},
    ],
    'routines_catalog': {'coast': {'anchors': [
        {'start': '07:00', 'end': '19:00', 'activity': 'drive to the coast', 'setting': 'the car'}]}},
}


class ExpectedDayTests(unittest.TestCase):
    """What does her Thursday look like -- the question a calendar is for.

    `routine` answers "what is she doing right now", which the prompt needs and
    which is no use at all for looking ahead.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex', profile='nova',
                              hermes_root=base / 'hermes', vault=base / 'vault',
                              timezone='America/New_York', context_mode='fixed')
        self.c.home.mkdir(parents=True)
        self.c.soul_dir.mkdir(parents=True)
        self.c.life.mkdir(parents=True, exist_ok=True)
        self.c.save()
        (self.c.life / 'routine.json').write_text(json.dumps(ROUTINE), encoding='utf-8')

    def day(self, iso, now=None):
        return life.expected_day(self.c.life, dt.date.fromisoformat(iso), now)

    def test_a_weekday_gets_the_daily_anchors_in_order(self):
        result = self.day('2026-09-21')   # a Monday
        self.assertTrue(result['configured'])
        self.assertEqual([a['activity'] for a in result['anchors']],
                         ['wake and breakfast', 'lunch', 'wind down'])
        self.assertEqual([a['start'] for a in result['anchors']],
                         sorted(a['start'] for a in result['anchors']))

    def test_the_weekly_anchor_lands_on_its_own_weekday_only(self):
        tuesday = [a['activity'] for a in self.day('2026-09-22')['anchors']]
        monday = [a['activity'] for a in self.day('2026-09-21')['anchors']]
        self.assertIn('Pilates', tuesday)
        self.assertNotIn('Pilates', monday)
        self.assertIn('farmers market', [a['activity'] for a in self.day('2026-09-26')['anchors']])

    def test_a_weekly_anchor_is_marked_as_one(self):
        rows = {a['activity']: a for a in self.day('2026-09-22')['anchors']}
        self.assertEqual(rows['Pilates']['recurrence'], 'weekly')
        self.assertEqual(rows['lunch']['recurrence'], 'daily')

    def test_what_she_intends_replaces_the_usual_shape_for_that_day_alone(self):
        now = dt.datetime(2026, 9, 21, 9, tzinfo=dt.timezone.utc)
        (self.c.life / 'tomorrow.json').write_text(json.dumps(
            {'intent': 'a day out', 'date': '2026-09-22', 'theme': 'coast'}), encoding='utf-8')
        intended = self.day('2026-09-22', now)
        self.assertEqual(intended['source'], 'intended')
        self.assertEqual([a['activity'] for a in intended['anchors']], ['drive to the coast'])
        # Every other day keeps its ordinary shape.
        self.assertEqual(self.day('2026-09-23', now)['source'], 'routine')

    def test_a_line_missing_its_times_is_skipped_not_fatal(self):
        """One hand-edited entry must not take the whole day's schedule down."""
        broken = dict(ROUTINE, daily=ROUTINE['daily'] + [{'activity': 'no times at all'}])
        (self.c.life / 'routine.json').write_text(json.dumps(broken), encoding='utf-8')
        activities = [a['activity'] for a in self.day('2026-09-21')['anchors']]
        self.assertNotIn('no times at all', activities)
        self.assertIn('lunch', activities)

    def test_no_routine_at_all_says_so_rather_than_failing(self):
        (self.c.life / 'routine.json').unlink()
        result = self.day('2026-09-21')
        self.assertFalse(result['configured'])
        self.assertEqual(result['anchors'], [])

    def test_anchors_are_never_presented_as_commitments(self):
        self.assertIn('not commitments', self.day('2026-09-21')['note'])


class ScheduleRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex', profile='nova',
                              hermes_root=base / 'hermes', vault=base / 'vault',
                              timezone='America/New_York', context_mode='fixed')
        self.c.home.mkdir(parents=True); self.c.soul_dir.mkdir(parents=True)
        self.c.life.mkdir(parents=True, exist_ok=True); self.c.save()
        (self.c.life / 'routine.json').write_text(json.dumps(ROUTINE), encoding='utf-8')
        self.client = TestClient(build(self.c.home, token='private', state_dir=base / 'state'))
        self.headers = {'x-companion-token': 'private'}

    def test_the_route_answers_for_any_day_asked_for(self):
        response = self.client.get('/api/schedule?day=2026-09-22', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('Pilates', [a['activity'] for a in response.json()['anchors']])

    def test_it_needs_the_token_like_everything_else(self):
        self.assertEqual(self.client.get('/api/schedule').status_code, 401)

    def test_a_nonsense_date_is_refused_rather_than_guessed_at(self):
        self.assertEqual(self.client.get('/api/schedule?day=not-a-day',
                                         headers=self.headers).status_code, 400)

    def test_no_day_means_her_today(self):
        response = self.client.get('/api/schedule', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['day'])


class VisualStyleReachesThePromptTests(unittest.TestCase):
    """A companion set to a drawn style came back photorealistic.

    Quality was the one prompt part with no fallback, so a preset that did not
    spell out a style sent no style direction whatsoever -- and a hosted model
    handed no style renders a photograph.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex', profile='nova',
                              hermes_root=base / 'hermes', vault=base / 'vault',
                              context_mode='fixed', image_style='anime-retro')
        self.c.home.mkdir(parents=True); self.c.soul_dir.mkdir(parents=True)
        self.c.soul.write_text('# SOUL\n\n## Appearance\n\nNova has short dark hair.\n',
                               encoding='utf-8')
        self.c.save()

    def preset(self, parts):
        media.save(self.c, {'version': 1, 'default_preset': 'p', 'presets': [
            {'id': 'p', 'name': 'Hosted', 'provider': 'hermes', 'hermes_provider': 'openai-codex',
             'category': 'portrait', 'parts': parts}]}, media.revision(self.c))

    def test_the_chosen_style_is_used_when_the_preset_names_none(self):
        self.preset({})
        compiled = media.compile(self.c, 'p', 'portrait')
        self.assertIn('1990s hand-painted cel', compiled['parts']['quality'])
        self.assertIn('VISUAL QUALITY', compiled['structured_prompt'])

    def test_a_preset_that_names_a_quality_still_wins(self):
        self.preset({'quality': 'charcoal sketch'})
        self.assertEqual(media.compile(self.c, 'p', 'portrait')['parts']['quality'],
                         'charcoal sketch')

    def test_a_drawn_style_never_silently_renders_as_a_photograph(self):
        self.preset({})
        prompt = media.compile(self.c, 'p', 'portrait')['structured_prompt'].lower()
        self.assertNotIn('photorealistic', prompt)
        self.assertIn('illustrated', prompt)

    def test_a_companion_with_no_style_set_is_unchanged(self):
        self.c.image_style = 'none'
        self.c.save()
        self.preset({})
        self.assertFalse(media.compile(self.c, 'p', 'portrait')['parts'].get('quality'))


class HomeScreenFaceTests(unittest.TestCase):
    """Whose face the home screen shows, and which pictures it may never use."""

    def source(self):
        return (ROOT / 'kit/app/static/product.js').read_text(encoding='utf-8')

    def hero(self):
        js = self.source()
        start = js.index('workspaceHandlers.now=')
        return js[start:js.index('presence-atmosphere-column', start)]

    def test_the_profile_photo_is_what_the_home_screen_shows(self):
        block = self.hero()
        self.assertIn('portraitStored', block,
                      'the hero ignores the chosen profile photo again')
        self.assertIn('/media/portrait', block)

    def test_a_blurred_picture_is_never_chosen_as_the_face(self):
        block = self.hero()
        chooser = re.search(r'const shownPhoto=content\.items\.find\(([^;]+)\);', block)
        self.assertIsNotNone(chooser, 'the hero picture is chosen somewhere else now')
        self.assertIn('!x.blur', chooser.group(1))
        self.assertIn("x.rating!=='nsfw'", chooser.group(1))

    def test_choosing_a_profile_photo_redraws_the_screen_that_shows_it(self):
        js = self.source()
        handler = js.split("post('/portrait/from-content'")[1][:400]
        self.assertIn("current==='now'", handler,
                      'the home screen keeps the old face until a full reload')

    def test_today_is_the_companions_today_not_greenwichs(self):
        """After about seven in the evening in New York, UTC is already tomorrow."""
        js = self.source()
        self.assertIn('const companionToday=', js)
        calendar = js[js.index('function buildCalendarHtml('):js.index('function wireCalendarComponent(')]
        self.assertIn('companionToday()', calendar)
        self.assertNotIn("new Date().toISOString().slice(0,10)", calendar)


if __name__ == '__main__':
    unittest.main()
