"""Journal archive (Day | Reflection): one date's existing records, read and never written.

Synthetic profiles only. Scenes are written through companion_life.record, the writer the
presence loop uses, so the files are laid out exactly as the app lays them out; captures
are the JSON records companion_timeline keeps.
"""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]
import companion_config as cc          # noqa: E402
import companion_life as life          # noqa: E402
from fastapi.testclient import TestClient   # noqa: E402
from kit.app import journal_archive as ja   # noqa: E402
from kit.app.server import build            # noqa: E402

NY = ZoneInfo('America/New_York')
TOKEN = 'journal-token'


def at(text, tz=NY):
    return dt.datetime.fromisoformat(text).replace(tzinfo=tz)


def state(activity, location='home', mood='calm', confirmed=True):
    return {'activity': activity, 'location': location, 'mood': mood, 'outfit': ['tee'],
            'transition': '', 'confirmed': confirmed}


class Fixture:
    """Two companions in one Hermes root; nova keeps a New York clock."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix='journal-')
        base = Path(self._tmp.name)
        self.root = base / 'hermes'
        vault = base / 'vault'
        self.root.mkdir()
        vault.mkdir()
        self.nova = cc.Companion(agent='Nova', human='Alex', profile='nova', hermes_root=self.root, vault=vault,
                                 soul_in_vault=False, context_mode='fixed', timezone='America/New_York')
        self.rowan = cc.Companion(agent='Rowan', human='Alex', profile='rowan', hermes_root=self.root, vault=vault,
                                  soul_in_vault=False, context_mode='fixed', timezone='America/New_York')
        for c in (self.nova, self.rowan):
            c.home.mkdir(parents=True)
            c.life.mkdir(parents=True, exist_ok=True)
            c.soul_dir.mkdir(parents=True, exist_ok=True)
            c.save()
        self.client = TestClient(build(self.root, token=TOKEN, state_dir=base / 'state'))

    def close(self):
        self._tmp.cleanup()

    def get(self, path, profile='nova'):
        return self.client.get(path, params={'profile': profile}, headers={'x-companion-token': TOKEN})

    # ----- records, written the way the app writes them -----
    def scene(self, c, when, activity, ident, status='in_progress', text=None, **kw):
        return life.record(c.life, text or f'{activity}.', activity, status, when, ident, c.agent, c.human,
                           state=state(activity, **kw))['episode']

    def capture(self, c, episode, ident, colour='green'):
        from PIL import Image
        folder = c.data / 'image-timeline'
        (folder / 'captures').mkdir(parents=True, exist_ok=True)
        (folder / 'images').mkdir(parents=True, exist_ok=True)
        name = ident + '.png'
        Image.new('RGB', (8, 8), colour).save(folder / 'images' / name)
        (folder / 'captures' / f'{ident}.json').write_text(json.dumps(
            {'id': ident, 'created_at': episode['recorded_at'], 'status': 'saved', 'scene': episode,
             'filename': name, 'primary_filename': name, 'variants': [{'filename': name}]}))
        return name

    def reflection(self, c, day, text):
        path = c.soul_dir / 'Lifelog.md'
        old = path.read_text() if path.exists() else ''
        path.write_text(old + f'\n## {day}\n\n{text}\n')


def tree(path):
    """Every file under a profile with its bytes and mtime: the mutation witness."""
    out = {}
    for p in sorted(Path(path).rglob('*')):
        if p.is_file() and not p.is_symlink():
            st = p.stat()
            out[str(p.relative_to(path))] = (hashlib.sha256(p.read_bytes()).hexdigest(), st.st_mtime_ns)
    return out


class HistoricalDay(unittest.TestCase):
    """Test 1: a past date with scenes, a genuinely associated photo and reflection text."""

    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)
        n = self.f.nova
        self.walk = self.f.scene(n, at('2026-09-20T09:00'), 'walking to the market', 'walk-1', location='market street')
        self.f.scene(n, at('2026-09-20T09:15'), 'walking to the market', 'walk-2', location='market street')
        self.read = self.f.scene(n, at('2026-09-20T11:00'), 'reading', 'read-1', location='library')
        self.photo = self.f.capture(n, self.read, 'a' * 24)
        # the second snapshot of the walk has its own capture: it must join the collapsed walk
        self.f.capture(n, {**self.walk, 'id': 'walk-2'}, 'b' * 24, 'blue')
        self.f.reflection(n, '2026-09-20', 'A slow **market** morning, then the library.')
        self.f.reflection(n, '2026-09-19', 'The day before.')

    def test_day_and_reflection_agree_on_date_and_sources(self):
        r = self.f.get('/api/journal/archive/2026-09-20')
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d['day'], '2026-09-20')
        self.assertEqual([s['activity'] for s in d['scenes']], ['walking to the market', 'reading'])
        walk, read = d['scenes']
        # adjacent identical snapshots collapse for display, every id kept
        self.assertEqual(walk['snapshots'], 2)
        self.assertEqual(walk['ids'], ['walk-1', 'walk-2'])
        self.assertEqual(walk['until'], read['at'])
        self.assertIsNone(read['until'])                     # no invented end for the last scene
        self.assertEqual([p['capture_id'] for p in read['photos']], ['a' * 24])
        self.assertEqual([p['capture_id'] for p in walk['photos']], ['b' * 24])
        self.assertTrue(read['photos'][0]['url'].startswith('/api/content/file?path=image-timeline'))
        self.assertIn('not evidence about Alex', read['provenance'])
        self.assertEqual(d['reflection']['state'], 'available')
        entry, = d['reflection']['entries']
        self.assertEqual((entry['day'], entry['source']), ('2026-09-20', 'Lifelog.md'))
        # the Reflection view reads the same entry through the existing journal route
        full = self.f.get('/api/journals/' + entry['id']).json()['entry']
        self.assertEqual(full['day'], d['day'])
        self.assertIn('**market**', full['text'])
        # stored history is untouched by the display collapse
        rows = life.read_events(self.f.nova.life, '2026-09-20', limit=0)
        self.assertEqual([x['id'] for x in rows], ['walk-1', 'walk-2', 'read-1'])

    def test_index_marks_days_with_records(self):
        d = self.f.get('/api/journal/archive').json()
        self.assertEqual(d['days']['2026-09-20'], {'scenes': True, 'reflection': True})
        self.assertEqual(d['days']['2026-09-19'], {'scenes': False, 'reflection': True})

    def test_reading_writes_nothing_and_calls_no_model(self):
        before = tree(self.f.root), tree(self.f.nova.vault)
        calls = []

        def refuse(*a, **k):
            calls.append(a)
            raise AssertionError('archive reads must not start a process')
        with patch.object(subprocess, 'run', refuse), patch.object(subprocess, 'Popen', refuse), \
                patch.object(os, 'system', refuse):
            for path in ('/api/journal/archive', '/api/journal/archive/2026-09-20', '/api/journal/archive/2026-09-19',
                         '/api/journals?limit=1000', '/api/journal/archive/2031-01-01'):
                self.assertEqual(self.f.get(path).status_code, 200, path)
        self.assertEqual(calls, [])
        self.assertEqual((tree(self.f.root), tree(self.f.nova.vault)), before)


class TruthfulStates(unittest.TestCase):
    """Test 2: empty profile, no reflection, unreadable sources, planned/unconfirmed, no false links."""

    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)

    def test_new_profile_is_honestly_empty(self):
        d = self.f.get('/api/journal/archive/2026-09-20').json()
        self.assertEqual(d['scenes'], [])
        self.assertEqual(d['sources'], {'scenes': 'none', 'photos': 'available'})
        self.assertEqual(d['reflection'], {'state': 'none', 'entries': [], 'warnings': []})
        self.assertEqual(d['plan']['state'], 'none')
        self.assertEqual(d['together'], {'state': 'none', 'moments': []})
        self.assertEqual(self.f.get('/api/journal/archive').json()['days'], {})

    def test_scenes_without_reflection(self):
        self.f.scene(self.f.nova, at('2026-09-21T08:00'), 'coffee', 'c-1')
        d = self.f.get('/api/journal/archive/2026-09-21').json()
        self.assertEqual(len(d['scenes']), 1)
        self.assertEqual(d['reflection']['state'], 'none')

    def test_unreadable_scene_file_is_unavailable_not_empty(self):
        folder = self.f.nova.life / 'episodes'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / '2026-09-22.jsonl').mkdir()                 # present, but cannot be read as a file
        d = self.f.get('/api/journal/archive/2026-09-22').json()
        self.assertEqual(d['sources']['scenes'], 'unavailable')
        self.assertEqual(d['scenes'], [])

    def test_unreadable_journal_is_unavailable_not_absent(self):
        (self.f.nova.soul_dir / 'Lifelog.md').write_bytes(b'## 2026-09-22\n\n\xff\xfe broken')
        d = self.f.get('/api/journal/archive/2026-09-22').json()
        self.assertEqual(d['reflection']['state'], 'unavailable')
        self.assertTrue(d['reflection']['warnings'])

    def test_corrupt_capture_record_is_unavailable(self):
        ep = self.f.scene(self.f.nova, at('2026-09-22T10:00'), 'painting', 'p-1')
        self.f.capture(self.f.nova, ep, 'c' * 24)
        (self.f.nova.data / 'image-timeline/captures' / ('d' * 24 + '.json')).write_text('{not json')
        d = self.f.get('/api/journal/archive/2026-09-22').json()
        self.assertEqual(d['sources']['photos'], 'unavailable')
        self.assertEqual(d['scenes'][0]['photos'], [])

    def test_deleted_photo_is_reported_missing_not_relinked(self):
        ep = self.f.scene(self.f.nova, at('2026-09-22T10:00'), 'painting', 'p-1')
        name = self.f.capture(self.f.nova, ep, 'c' * 24)
        (self.f.nova.data / 'image-timeline/images' / name).unlink()
        scene, = self.f.get('/api/journal/archive/2026-09-22').json()['scenes']
        self.assertEqual((scene['photos'], scene['missing_photos']), ([], 1))

    def test_a_neighbouring_file_does_not_make_an_empty_day_look_recorded(self):
        self.f.scene(self.f.nova, at('2026-09-21T12:00'), 'next day', 'n-1')
        d = self.f.get('/api/journal/archive/2026-09-20').json()
        self.assertEqual((d['scenes'], d['sources']['scenes']), ([], 'none'))

    def test_a_scan_limited_library_is_partial_not_missing(self):
        from kit.app import content
        ep = self.f.scene(self.f.nova, at('2026-09-22T10:00'), 'painting', 'p-1')
        self.f.capture(self.f.nova, ep, 'c' * 24)
        with patch.object(content, 'catalog', lambda *a, **k: {'items': [], 'scan_limited': True}):
            d = self.f.get('/api/journal/archive/2026-09-22').json()
        self.assertEqual(d['sources']['photos'], 'partial')
        self.assertEqual((d['scenes'][0]['photos'], d['scenes'][0]['missing_photos']), ([], 0))

    def test_planned_skipped_and_carried_forward_keep_their_meaning(self):
        n = self.f.nova
        self.f.scene(n, at('2026-09-23T08:00'), 'yoga', 'y-1')
        self.f.scene(n, at('2026-09-23T08:30'), 'yoga', 'y-2', confirmed=False)     # carried forward
        self.f.scene(n, at('2026-09-23T08:45'), 'yoga', 'y-3', confirmed=False)
        life.record(n.life, 'Will bake later.', 'baking', 'planned', at('2026-09-23T09:00'), 'plan-1', n.agent, n.human)
        life.record(n.life, 'Did not swim.', 'swimming', 'skipped', at('2026-09-23T10:00'), 'skip-1', n.agent, n.human)
        plans = n.life / 'plans'
        plans.mkdir()
        (plans / '2026-09-23.json').write_text(json.dumps({'intent': 'A quiet day', 'items': [
            {'start': '14:00', 'end': '15:00', 'what': 'visit the gallery', 'status': 'planned', 'kind': 'intended'}]}))
        d = self.f.get('/api/journal/archive/2026-09-23').json()
        self.assertEqual([(s['activity'], s['status'], s['snapshots']) for s in d['scenes']],
                         [('yoga', 'recorded', 1), ('yoga', 'carried_forward', 2),
                          ('baking', 'planned', 1), ('swimming', 'skipped', 1)])
        self.assertEqual(d['plan']['state'], 'available')
        self.assertEqual(d['plan']['items'][0]['what'], 'visit the gallery')

    def test_same_date_media_and_authored_activity_make_no_association(self):
        n = self.f.nova
        ep = self.f.scene(n, at('2026-09-24T15:00'), 'having coffee with Alex', 'coffee-1', text='Coffee with Alex.')
        # a creation saved the same afternoon, and a capture for a DIFFERENT scene that is not in the record
        from PIL import Image
        (n.data / 'creations').mkdir(parents=True)
        Image.new('RGB', (8, 8), 'red').save(n.data / 'creations/same-day.png')
        stamp = at('2026-09-24T15:05').timestamp()
        os.utime(n.data / 'creations/same-day.png', (stamp, stamp))
        ghost = {**ep, 'id': 'gone-1', 'state': state('stretching')}
        self.f.capture(n, ghost, 'e' * 24)
        d = self.f.get('/api/journal/archive/2026-09-24').json()
        scene, = d['scenes']
        self.assertEqual(scene['photos'], [])                # neither the creation nor the ghost capture
        self.assertEqual([x['activity'] for x in d['unplaced_photos']], ['stretching'])
        # the companion wrote "with Alex"; that is not a shared moment on record
        self.assertEqual(d['together'], {'state': 'none', 'moments': []})
        self.assertIn('not evidence about Alex', scene['provenance'])

    def test_you_two_only_from_an_explicit_dated_moment(self):
        import companion_notes as notes
        now = dt.datetime(2026, 9, 25, tzinfo=dt.timezone.utc)
        notes.add_moment(self.f.nova, {'moment': 'first', 'text': 'First picnic together', 'happened_on': '2026-09-24'}, now)
        notes.add_moment(self.f.nova, {'moment': 'joke', 'text': 'The umbrella joke', 'happened_on': 'last spring'}, now)
        notes.add_moment(self.f.nova, {'moment': 'ritual', 'text': 'Sunday calls'}, now)
        self.assertEqual([m['text'] for m in self.f.get('/api/journal/archive/2026-09-24').json()['together']['moments']],
                         ['First picnic together'])
        # recorded on the 25th, happened on the 24th: the recording date is not the event date
        self.assertEqual(self.f.get('/api/journal/archive/2026-09-25').json()['together']['moments'], [])


class Dates(unittest.TestCase):
    """Test 3: the profile's timezone decides the day, across midnight and DST."""

    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)

    def test_midnight_uses_the_profile_clock_not_the_file_name(self):
        n = self.f.nova
        # 23:30 in New York is already the next day in UTC; written by a UTC clock it lands in the 21st's file
        self.f.scene(n, dt.datetime(2026, 9, 21, 3, 30, tzinfo=dt.timezone.utc), 'late tea', 'tea-1')
        self.f.scene(n, at('2026-09-21T00:10'), 'asleep', 'sleep-1')
        self.assertTrue((n.life / 'episodes/2026-09-21.jsonl').exists())
        on20 = self.f.get('/api/journal/archive/2026-09-20').json()['scenes']
        on21 = self.f.get('/api/journal/archive/2026-09-21').json()['scenes']
        self.assertEqual([s['activity'] for s in on20], ['late tea'])
        self.assertEqual([s['activity'] for s in on21], ['asleep'])
        self.assertTrue(on20[0]['at'].startswith('2026-09-20T23:30'))
        days = self.f.get('/api/journal/archive').json()['days']
        self.assertIn('2026-09-20', days)

    def test_daylight_saving_boundaries(self):
        n = self.f.nova
        # spring forward: 2026-03-08 02:00 does not exist in New York
        self.f.scene(n, at('2026-03-08T01:30'), 'before the jump', 's-1')
        self.f.scene(n, dt.datetime(2026, 3, 8, 7, 30, tzinfo=dt.timezone.utc), 'after the jump', 's-2')
        self.f.scene(n, at('2026-03-08T23:59'), 'last minute', 's-3')
        spring = self.f.get('/api/journal/archive/2026-03-08').json()['scenes']
        self.assertEqual([s['activity'] for s in spring], ['before the jump', 'after the jump', 'last minute'])
        self.assertTrue(spring[1]['at'].startswith('2026-03-08T03:30:00-04:00'))
        self.assertEqual(spring[0]['until'], spring[1]['at'])
        # fall back: 01:30 happens twice on 2026-11-01; both stay on the 1st, in order
        self.f.scene(n, dt.datetime(2026, 11, 1, 5, 30, tzinfo=dt.timezone.utc), 'first 1:30', 'f-1')
        self.f.scene(n, dt.datetime(2026, 11, 1, 6, 30, tzinfo=dt.timezone.utc), 'second 1:30', 'f-2')
        self.f.scene(n, dt.datetime(2026, 11, 2, 4, 30, tzinfo=dt.timezone.utc), 'still the 1st', 'f-3')
        fall = self.f.get('/api/journal/archive/2026-11-01').json()['scenes']
        self.assertEqual([s['activity'] for s in fall], ['first 1:30', 'second 1:30', 'still the 1st'])
        self.assertEqual([s['at'][11:] for s in fall[:2]], ['01:30:00-04:00', '01:30:00-05:00'])

    def test_date_only_and_invalid_values_get_no_invented_time(self):
        folder = self.f.nova.life / 'episodes'
        folder.mkdir(parents=True, exist_ok=True)
        rows = [{'id': 'd-1', 'kind': 'imagined_episode', 'recorded_at': '2026-09-26', 'status': 'in_progress',
                 'activity': 'date only', 'text': 'x', 'state': state('date only')},
                {'id': 'd-2', 'kind': 'imagined_episode', 'recorded_at': 'not a time', 'status': 'in_progress',
                 'activity': 'garbled', 'text': 'x', 'state': state('garbled')},
                {'id': 'd-3', 'kind': 'imagined_episode', 'recorded_at': '2026-09-26T10:00:00', 'status': 'in_progress',
                 'activity': 'naive', 'text': 'x', 'state': state('naive')}]
        (folder / '2026-09-26.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        # a neighbouring file's untimed row must not wander onto this day
        (folder / '2026-09-27.jsonl').write_text(json.dumps({**rows[1], 'id': 'd-4', 'activity': 'elsewhere'}) + '\n')
        scenes = self.f.get('/api/journal/archive/2026-09-26').json()['scenes']
        self.assertEqual([(s['activity'], s['at'], s['time_known']) for s in scenes],
                         [('date only', None, False), ('garbled', None, False), ('naive', None, False)])
        for bad in ('2026-02-30', '26-09-2026', '2026-9-1', 'today'):
            self.assertEqual(self.f.get('/api/journal/archive/' + bad).status_code, 400, bad)

    def test_local_helpers(self):
        self.assertIsNone(ja.local_moment('2026-09-26', NY))
        self.assertIsNone(ja.local_moment('2026-09-26T10:00:00', NY))
        self.assertIsNone(ja.local_moment(None, NY))
        self.assertEqual(ja.local_day('2026-09-27T01:00:00+00:00', NY), '2026-09-26')
        self.assertEqual(ja.parse_day('2024-02-29'), dt.date(2024, 2, 29))


class Isolation(unittest.TestCase):
    """Test 4 (server side): each profile reads only its own records."""

    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)

    def test_profiles_do_not_see_each_other(self):
        ep = self.f.scene(self.f.nova, at('2026-09-20T09:00'), 'nova only', 'n-1')
        self.f.capture(self.f.nova, ep, 'f' * 24)
        self.f.reflection(self.f.nova, '2026-09-20', 'Nova wrote this.')
        self.f.scene(self.f.rowan, at('2026-09-20T09:00'), 'rowan only', 'r-1')
        nova = self.f.get('/api/journal/archive/2026-09-20', 'nova').json()
        rowan = self.f.get('/api/journal/archive/2026-09-20', 'rowan').json()
        self.assertEqual([s['activity'] for s in nova['scenes']], ['nova only'])
        self.assertEqual([s['activity'] for s in rowan['scenes']], ['rowan only'])
        self.assertEqual(rowan['scenes'][0]['photos'], [])
        self.assertEqual(rowan['reflection']['state'], 'none')
        self.assertEqual(rowan['agent'], 'Rowan')
        self.assertNotIn('2026-09-20', {k for k, v in self.f.get('/api/journal/archive', 'rowan').json()['days'].items()
                                        if v['reflection']})

    def test_token_is_required(self):
        r = self.f.client.get('/api/journal/archive/2026-09-20', params={'profile': 'nova'})
        self.assertEqual(r.status_code, 401)

    def test_linked_episode_file_is_not_followed(self):
        other = Path(self.f._tmp.name) / 'elsewhere.jsonl'
        other.write_text(json.dumps({'id': 'x', 'kind': 'imagined_episode', 'recorded_at': '2026-09-20T09:00:00-04:00',
                                     'status': 'in_progress', 'activity': 'foreign', 'text': 'x',
                                     'state': state('foreign')}) + '\n')
        folder = self.f.nova.life / 'episodes'
        folder.mkdir(parents=True, exist_ok=True)
        try:
            (folder / '2026-09-20.jsonl').symlink_to(other)
        except OSError:
            self.skipTest('Symlinks unavailable')
        d = self.f.get('/api/journal/archive/2026-09-20').json()
        self.assertEqual(d['scenes'], [])
        self.assertEqual(d['sources']['scenes'], 'unavailable')



if __name__ == '__main__':
    unittest.main()
