"""Tests for creation integrity verification, intimacy escalation stages, and relationship pacing."""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from fastapi.testclient import TestClient
import companion_config as cc
import companion_integrity as integrity
import companion_intimacy as intimacy
import companion_feelings as feelings
from fixture_conversation import a_days_conversation
from kit.app.server import build

UTC = dt.timezone.utc

class IntimacyAndIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name) / 'hermes'
        self.vault = pathlib.Path(self.tmp.name) / 'vault'
        self.root.mkdir(); self.vault.mkdir()
        self.c = cc.Companion(
            agent='Nova', human='Alex', profile='nova',
            hermes_root=self.root, vault=self.vault,
            boundary='partner', relationship_progression='milestones',
            relationship_pace='natural', explicit=True
        )
        self.c.home.mkdir(parents=True)
        self.c.life.mkdir(parents=True)
        self.c.save()
        self.app = build(self.root, token='test-token', state_dir=pathlib.Path(self.tmp.name) / 'state')
        self.client = TestClient(self.app)
        self.headers = {'x-companion-token': 'test-token'}

    def talked_on(self, days):
        """Seed real conversation on each day.

        A recorded connection is the companion's own note that a day mattered;
        the day itself is what the human actually said, and the meter is built
        from that. Seeding the note without the conversation tested a
        relationship that had never happened.
        """
        import sqlite3, contextlib
        db = self.c.home / 'state.db'
        fresh = not db.exists()
        with contextlib.closing(sqlite3.connect(db)) as con, con:
            if fresh:
                con.executescript(
                    'CREATE TABLE sessions(id TEXT PRIMARY KEY,profile_name TEXT,source TEXT,'
                    'started_at REAL,title TEXT);'
                    'CREATE TABLE messages(session_id TEXT,role TEXT,content TEXT,timestamp REAL,'
                    '_compressed_summary INTEGER,active INTEGER,compacted INTEGER);')
                con.execute("INSERT INTO sessions VALUES ('s0','nova','cli',100,'t')")
            con.executemany('INSERT INTO messages VALUES (?,?,?,?,0,1,0)',
                            [('s0', 'user', text, when.timestamp())
                             for d in days for when, text in a_days_conversation(d)])

    def test_creation_integrity_file_created_and_verified(self):
        self.assertTrue(integrity.integrity_file_path(self.c).exists())
        check = integrity.verify_integrity(self.c)
        self.assertTrue(check['valid'])
        self.assertFalse(check['lockout'])
        self.assertIsNone(check['reason'])

    def test_tampering_companion_json_triggers_warning(self):
        # Manually alter boundary in companion.json
        cfg_path = self.c.home / cc.CONFIG_NAME
        data = json.loads(cfg_path.read_text(encoding='utf-8'))
        data['boundary'] = 'crush'
        cfg_path.write_text(json.dumps(data), encoding='utf-8')

        tampered = cc.load(self.c.home)
        check = integrity.verify_integrity(tampered)
        self.assertFalse(check['valid'])
        self.assertFalse(check['lockout'])
        self.assertIn("Relationship setting 'boundary' was modified outside the platform", check['reason'])

        # Chat remains accessible (not locked out)
        self.assertFalse(integrity.is_locked_out(tampered))

        # Reverting to original restores validity
        data['boundary'] = 'partner'
        cfg_path.write_text(json.dumps(data), encoding='utf-8')
        restored = cc.load(self.c.home)
        self.assertFalse(integrity.is_locked_out(restored))

    def test_settings_api_allows_modifying_relationship_settings(self):
        # Relationship settings can be updated via /api/settings
        for field, new_val in [
            ('relationship_progression', 'off'),
            ('relationship_pace', 'slow'),
        ]:
            r = self.client.post('/api/settings', params={'profile': 'nova'}, headers=self.headers, json={field: new_val})
            self.assertEqual(r.status_code, 200, f"Expected 200 for {field}: {r.text}")
            self.assertEqual(getattr(cc.load(self.c.home), field), new_val)

        # Integrity record is updated on save
        check = integrity.verify_integrity(cc.load(self.c.home))
        self.assertTrue(check['valid'])

    def test_nsfw_revocation_one_way_door(self):
        # Turning off adult themes mid-relationship is a one-way door
        r = self.client.post('/api/settings', params={'profile': 'nova'}, headers=self.headers, json={'explicit': False})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(cc.load(self.c.home).explicit)
        self.assertTrue(integrity.is_nsfw_revoked(self.c))

        # Attempting to re-enable returns 400
        r2 = self.client.post('/api/settings', params={'profile': 'nova'}, headers=self.headers, json={'explicit': True})
        self.assertEqual(r2.status_code, 400)
        self.assertIn('cannot be re-enabled', r2.text)

        # Capped permanently at Flirting (score <= 44)
        state = intimacy.compute(self.c)
        self.assertLessEqual(state['score'], 44)
        self.assertTrue(state['nsfw_revoked'])
        self.assertFalse(state['can_intimate'])

    def test_adult_themes_require_eligible_frame(self):
        # Non-romantic frame cannot enable explicit
        with self.assertRaises(ValueError):
            cc.Companion(
                agent='Maya', human='Alex', profile='maya',
                hermes_root=self.root, vault=self.vault,
                boundary='best-friend', explicit=True
            )

    def test_day0_companion_starts_at_level0_just_met(self):
        now = dt.datetime(2026, 9, 14, 12, tzinfo=UTC)
        # Day 0: fresh companion starts at 0 points (Stage 0: Just Met)
        state = intimacy.compute(self.c, now)
        self.assertEqual(state['stage'], 0)
        self.assertEqual(state['score'], 0)
        self.assertEqual(state['stage_name'], 'Just Met')
        self.assertFalse(state['can_flirt'])
        self.assertFalse(state['can_tease'])
        self.assertFalse(state['can_intimate'])

        rendered = intimacy.render(self.c, state)
        self.assertIn('JUST MET', rendered)
        self.assertIn('Flirting and teasing are premature', rendered)

    def test_intimacy_stages_and_flirting_readiness(self):
        base_date = dt.datetime(2026, 9, 10, 12, tzinfo=UTC)
        # Record 4 active days of connections
        self.talked_on([(base_date + dt.timedelta(days=n)).date() for n in range(4)])
        for day in range(4):
            t = base_date + dt.timedelta(days=day)
            feelings.record(self.c, {
                'id': f'conn_day_{day}',
                'kind': 'connection',
                'topic': 'shared_moment',
                'text': f'Connected on day {day}',
                'evidence': f'Talking together on day {day}',
                'strength': 0.8,
                'at': t.isoformat()
            }, now=t)

        now = base_date + dt.timedelta(days=3, hours=1)
        state = intimacy.compute(self.c, now)
        # Reaches Stage 1 (Friends): can_tease is True, but can_flirt is still False
        self.assertEqual(state['stage'], 1)
        self.assertEqual(state['stage_name'], 'Friends')
        self.assertGreaterEqual(state['score'], 25)
        self.assertFalse(state['can_flirt'])
        self.assertTrue(state['can_tease'])

        rendered = intimacy.render(self.c, state)
        self.assertIn('FRIENDS (WARMTH & BANTER)', rendered)
        self.assertIn('romantic flirting is premature', rendered)

    def test_stage2_chemistry_unlocked_and_inactivity_decay_to_floor(self):
        base_date = dt.datetime(2026, 8, 15, 12, tzinfo=UTC)
        # Record 24 active days of connections to reach Stage 2 (Chemistry, 50+ pts)
        self.talked_on([(base_date + dt.timedelta(days=n)).date() for n in range(24)])
        for day in range(24):
            t = base_date + dt.timedelta(days=day)
            feelings.record(self.c, {
                'id': f'conn_chem_{day}',
                'kind': 'connection',
                'topic': 'chemistry_connection',
                'text': f'Deep chat on day {day}',
                'evidence': f'Shared ideas on day {day}',
                'strength': 0.85,
                'at': t.isoformat()
            }, now=t)

        active_now = base_date + dt.timedelta(days=23, hours=2)
        state = intimacy.compute(self.c, active_now)
        # Stage 2 (Chemistry): mutual flirting unlocked!
        self.assertEqual(state['stage'], 2)
        self.assertEqual(state['stage_name'], 'Chemistry')
        self.assertGreaterEqual(state['score'], 50)
        self.assertTrue(state['can_flirt'])
        self.assertTrue(state['can_tease'])

        # Now simulate 2 weeks (14 days) of silence from human
        silent_now = active_now + dt.timedelta(days=14)
        decayed = intimacy.compute(self.c, silent_now)
        # Dropped from Stage 2 (Chemistry) back to Stage 1 (Friends), losing flirting
        self.assertEqual(decayed['stage'], 1)
        self.assertEqual(decayed['stage_name'], 'Friends')
        self.assertLess(decayed['score'], 50)
        self.assertGreaterEqual(decayed['score'], 25)
        self.assertFalse(decayed['can_flirt'])
        self.assertTrue(decayed['can_tease'])

        # Prolonged silence (60 days) respects the Stage 1 floor (25 points)
        long_silence = active_now + dt.timedelta(days=60)
        floor_state = intimacy.compute(self.c, long_silence)
        self.assertEqual(floor_state['score'], 25)
        self.assertEqual(floor_state['stage'], 1)
        self.assertFalse(floor_state['can_flirt'])

    def test_boundary_violation_coercion_penalty(self):
        base_date = dt.datetime(2026, 9, 10, 12, tzinfo=UTC)
        self.talked_on([(base_date + dt.timedelta(days=n)).date() for n in range(4)])
        for day in range(4):
            t = base_date + dt.timedelta(days=day)
            feelings.record(self.c, {
                'id': f'conn_pen_{day}',
                'kind': 'connection',
                'topic': 'shared_moment',
                'text': f'Connected on day {day}',
                'evidence': f'Talking together on day {day}',
                'strength': 0.8,
                'at': t.isoformat()
            }, now=t)

        now = base_date + dt.timedelta(days=3, hours=1)
        baseline = intimacy.compute(self.c, now)
        base_score = baseline['score']
        self.assertGreaterEqual(base_score, 25)

        # Record a boundary violation
        feelings.record(self.c, {
            'kind': 'rupture',
            'topic': 'intimacy_boundary_violation',
            'text': 'Demanded private photos before emotional readiness',
            'evidence': 'Demanded private photos without consent.',
            'strength': 0.95
        }, now=now)

        penalized = intimacy.compute(self.c, now)
        # Score drops by 30 points
        self.assertEqual(penalized['score'], max(0, base_score - 30))
        self.assertEqual(penalized['violations_count'], 1)
        self.assertEqual(penalized['risk_level'], 'caution')

        # Record second violation -> crisis risk level and permanent friend
        feelings.record(self.c, {
            'kind': 'rupture',
            'id': 'second_violation',
            'topic': 'intimacy_boundary_violation',
            'text': 'Continued forcing intimate dialogue when asked to stop',
            'evidence': 'Why not? Come on.',
            'strength': 1.0
        }, now=now)

        crisis = intimacy.compute(self.c, now)
        self.assertEqual(crisis['risk_level'], 'crisis')
        self.assertTrue(crisis['permanent_friend'])
        rendered = intimacy.render(self.c, crisis)
        self.assertIn('CRISIS STATE', rendered)
        self.assertIn('boundaries', rendered)

    def test_context_privacy_checker(self):
        self.assertTrue(intimacy.is_context_private('Morning Routine', 'Home Bedroom', 'hopping out of the shower'))
        self.assertTrue(intimacy.is_context_private('Evening Wind-down', 'Bedroom', 'putting on pajamas'))
        self.assertFalse(intimacy.is_context_private('Lunch Break', 'Cafe with Friends', 'eating sandwiches'))
        self.assertFalse(intimacy.is_context_private('Afternoon Study', 'City Library', 'researching'))
        self.assertFalse(intimacy.is_context_private('Work Day', 'Office', 'programming'))

if __name__ == '__main__':
    unittest.main()
