"""Journal archive (Day | Reflection) in a real browser, with synthetic records.

BOUNDARY: headless Chromium (Playwright) -> the actual page (index.html, product.js,
journal.js, the persistent Chat client) -> a real uvicorn server (tests/phase1b_c3/fixture.py,
fake Hermes) -> synthetic profile files written by the app's own writers. No model,
platform, credential or live profile.

TAMANITOMO_C3_REQUIRE_BROWSER=1 makes a missing browser a failure, never a skip.
TAMANITOMO_JOURNAL_SHOTS=<dir> saves phone/tablet/desktop screenshots of the archive.
"""
import datetime as dt
import json
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from tests.test_phase1b_c3_browser import Browser, until          # noqa: E402
from tests.test_journal_archive import state                    # noqa: E402

SHOTS = os.environ.get('TAMANITOMO_JOURNAL_SHOTS')
UTC = dt.timezone.utc
DRAFT = 'A half-written thought about the market'


def seed(c):
    """Two days of Nova's life: scenes, one photographed scene, two reflections."""
    import companion_life as life
    from PIL import Image
    rec = lambda when, activity, ident, **kw: life.record(c.life, activity + '.', activity, 'in_progress', when, ident,
                                                          c.agent, c.human, state=state(activity, **kw))['episode']
    rec(dt.datetime(2026, 9, 20, 9, 0, tzinfo=UTC), 'walking to the market', 'walk-1', location='market street')
    rec(dt.datetime(2026, 9, 20, 9, 15, tzinfo=UTC), 'walking to the market', 'walk-2', location='market street')
    reading = rec(dt.datetime(2026, 9, 20, 11, 0, tzinfo=UTC), 'reading by the window', 'read-1', location='library')
    rec(dt.datetime(2026, 9, 20, 12, 0, tzinfo=UTC), 'reading by the window', 'read-2', location='library', confirmed=False)
    folder = c.data / 'image-timeline'
    (folder / 'captures').mkdir(parents=True)
    (folder / 'images').mkdir()
    ident = 'a' * 24
    Image.new('RGB', (64, 80), (90, 140, 200)).save(folder / 'images' / f'{ident}.png')
    (folder / 'captures' / f'{ident}.json').write_text(json.dumps(
        {'id': ident, 'created_at': reading['recorded_at'], 'status': 'saved', 'scene': reading,
         'filename': f'{ident}.png', 'primary_filename': f'{ident}.png', 'variants': [{'filename': f'{ident}.png'}]}))
    c.soul_dir.mkdir(parents=True, exist_ok=True)
    (c.soul_dir / 'Lifelog.md').write_text(
        '## 2026-09-18\n\nThe day before the market. Rain all afternoon.\n\n'
        '## 2026-09-20\n\nA slow **market** morning, then the library until the light went.\n')
    # an owner who pinned Timeline to the bottom bar before this change
    (c.home / 'companion-appearance.json').write_text(json.dumps({'nav_pins': ['chat', 'timeline', 'journals']}))


class JournalArchive(Browser):

    def setUp(self):
        super().setUp()
        seed(self.s.companions['nova'])

    # ----- helpers -----
    def hash(self):
        return self.page.evaluate('location.hash')

    def go(self, tab):
        self.page.evaluate(f"()=>showTab('{tab}')")
        until(lambda: self.page.evaluate(f"current==='{tab}'"), what=f'tab {tab}')

    def page_text(self):
        return self.page.inner_text('#journal-page')

    def at_route(self, day, view, text):
        until(lambda: self.hash() == f'#journals/{day}/{view}' and text in self.page_text(),
              what=f'{day}/{view} showing {text!r}')
        selected = self.page.get_attribute(f'#journal-view-{view}', 'aria-selected')
        self.assertEqual(selected, 'true')

    def shot(self, name):
        if SHOTS:
            pathlib.Path(SHOTS).mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(pathlib.Path(SHOTS) / f'{name}.png'), full_page=True)

    def writes(self):
        return [r for r in self.requests if r[0] not in ('GET', 'HEAD') and '/api/' in r[1]]

    # ----- journeys -----
    def test_archive_journey_with_back_refresh_timeline_and_chat_draft(self):
        self.open('nova', 'chat')
        self.page.fill('#chat-message', DRAFT)
        before = len(self.writes())

        # Journal opens where it always did: the latest reflection, now with its date in the address
        self.go('journals')
        self.at_route('2026-09-20', 'reflection', 'slow market morning')
        self.assertIn('Lifelog.md', self.page_text())              # the source reference is kept

        # choose a historical date from the calendar
        self.page.click('#journal-browse')
        self.page.click('[data-pick-day="2026-09-18"]')
        self.at_route('2026-09-18', 'reflection', 'Rain all afternoon')

        # switch to Day: same date, honest about having no scenes
        self.page.click('#journal-view-day')
        self.at_route('2026-09-18', 'day', 'No scenes were recorded on this day.')

        # back, back: the history Journal pushed
        self.page.go_back()
        self.at_route('2026-09-18', 'reflection', 'Rain all afternoon')
        self.page.go_back()
        self.at_route('2026-09-20', 'reflection', 'slow market morning')

        # the Day view of the 20th: collapsed snapshots, carried-forward state, the one real photo
        self.page.click('#journal-view-day')
        self.at_route('2026-09-20', 'day', 'Reading by the window')
        text = self.page_text()
        self.assertIn('2 unchanged snapshots', text)
        self.assertIn('Carried forward · unconfirmed', text)
        self.assertIn('not a record of what you did', text)
        self.assertNotIn('You two', text)
        shots = self.page.locator('#journal-page [data-archive-photo]')
        self.assertEqual(shots.count(), 1)
        reading = self.page.locator('#journal-page [data-scene="read-1"] [data-archive-photo]')
        self.assertEqual(reading.count(), 1, 'the photo sits in the scene its capture names')
        self.shot('desktop-day')

        # follow a source: the photo opens in the existing viewer
        reading.click()
        until(lambda: self.page.evaluate("document.getElementById('photo-viewer').open"), what='photo viewer')
        self.page.click('#viewer-close')
        until(lambda: not self.page.evaluate("document.getElementById('photo-viewer').open"), what='viewer closed')

        # and the reflection link from the Day view
        self.page.click('#journal-to-reflection')
        self.at_route('2026-09-20', 'reflection', 'slow market morning')
        self.shot('desktop-reflection')

        # refresh keeps the date and view
        self.page.reload()
        self.page.wait_for_selector('#journal-page .paper')
        self.at_route('2026-09-20', 'reflection', 'slow market morning')

        # a shared link to a date and view lands there directly
        self.page.goto(self.s.url('nova', 'journals/2026-09-20/day'))
        self.at_route('2026-09-20', 'day', 'Walking to the market')

        # Timeline: its old link and the saved pin still work, and its diary link lands in Journal
        self.page.goto(self.s.url('nova', 'timeline'))
        until(lambda: self.page.evaluate("current==='timeline'"), what='old #timeline link')
        self.page.wait_for_selector('#timeline-feed [data-journal]')
        pin = self.page.locator('#tabbar button[data-tab="timeline"]')
        self.assertEqual(pin.count(), 1, 'saved Timeline pin still rendered')
        self.go('photos')
        self.page.set_viewport_size({'width': 390, 'height': 844})   # the bottom bar is the phone's navigation
        pin.click()
        until(lambda: self.hash() == '#timeline', what='pin opens Timeline')
        self.page.set_viewport_size({'width': 1280, 'height': 720})
        self.page.wait_for_selector('#timeline-feed [data-journal]')
        self.page.locator('#timeline-feed [data-journal]').first.click()
        self.at_route('2026-09-20', 'reflection', 'slow market morning')

        # the Chat draft survived all of it (tab switches, back/forward, reloads)
        self.go('chat')
        self.page.wait_for_selector('#chat-message')
        until(lambda: self.page.input_value('#chat-message') == DRAFT, what='draft kept')
        self.assertEqual(self.writes()[before:], [], 'archive navigation made no write request')

    def test_back_from_another_tab_returns_to_the_journal_date(self):
        self.open('nova', 'journals/2026-09-18/reflection')
        self.at_route('2026-09-18', 'reflection', 'Rain all afternoon')
        self.page.click('#journal-view-day')
        self.at_route('2026-09-18', 'day', 'No scenes')
        self.go('photos')                                  # replaces the current entry
        self.page.go_back()
        self.at_route('2026-09-18', 'reflection', 'Rain all afternoon')
        # switching tabs and returning keeps the chosen date and view
        self.go('now')
        self.go('journals')
        self.at_route('2026-09-18', 'reflection', 'Rain all afternoon')

    def test_a_slow_answer_for_an_old_date_does_not_replace_the_new_one(self):
        self.open('nova', 'journals/2026-09-20/reflection')
        self.at_route('2026-09-20', 'reflection', 'slow market morning')
        held = []
        self.page.route('**/api/journal/archive/2026-09-18*', lambda route: held.append(route))
        self.page.evaluate("()=>{location.hash='#journals/2026-09-18/day'}")
        until(lambda: held, what='old request held')
        self.page.evaluate("()=>{location.hash='#journals/2026-09-20/day'}")
        self.at_route('2026-09-20', 'day', 'Reading by the window')
        held[0].continue_()
        self.page.wait_for_timeout(600)
        self.assertEqual(self.hash(), '#journals/2026-09-20/day')
        self.assertIn('Reading by the window', self.page_text())
        self.assertNotIn('No scenes were recorded', self.page_text())

    def test_another_profile_sees_only_its_own_empty_archive(self):
        self.open('rowan', 'journals/2026-09-20/day')
        self.at_route('2026-09-20', 'day', 'Nothing on record for this day')
        self.assertNotIn('market', self.page_text().lower())
        self.page.click('#journal-view-reflection')
        self.at_route('2026-09-20', 'reflection', 'No journal entries yet')
        self.assertTrue(all('profile=rowan' in r[1] for r in self.requests if '/api/journal' in r[1]))

    def test_representative_widths(self):
        for name, size in (('phone', (390, 844)), ('tablet', (820, 1180)), ('desktop', (1366, 900))):
            self.page.set_viewport_size({'width': size[0], 'height': size[1]})
            self.open('nova', 'journals/2026-09-20/day')
            self.at_route('2026-09-20', 'day', 'Reading by the window')
            overflow = self.page.evaluate('document.documentElement.scrollWidth-document.documentElement.clientWidth')
            self.assertLessEqual(overflow, 1, f'{name}: no horizontal page scroll')
            for control in ('#journal-view-day', '#journal-view-reflection', '#journal-browse', '#journal-older-btn'):
                box = self.page.locator(control).bounding_box()
                self.assertIsNotNone(box, control)
                self.assertLessEqual(box['x'] + box['width'], size[0] + 1, f'{name}: {control} on screen')
            self.shot(f'{name}-day')
            if name == 'phone':
                self.page.click('#journal-browse')
                self.page.wait_for_selector('[data-pick-day="2026-09-18"]')
                self.shot('phone-picker')
                # keyboard: the view tabs answer arrow keys
                self.page.keyboard.press('Escape')
                self.page.focus('#journal-view-day')
                self.page.keyboard.press('ArrowRight')
                self.at_route('2026-09-20', 'reflection', 'slow market morning')
                self.shot('phone-reflection')


if __name__ == '__main__':
    unittest.main()
