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

    def test_intimacy_stages_and_flirting_readiness(self):
        now = dt.datetime(2026, 9, 14, 12, tzinfo=UTC)
        # Stage 1: can_flirt and can_tease are True
        state = intimacy.compute(self.c, now)
        self.assertGreaterEqual(state['stage'], 1)
        self.assertTrue(state['can_flirt'])
        self.assertTrue(state['can_tease'])

        rendered = intimacy.render(self.c, state)
        self.assertIn('WARMTH & BANTER', rendered)
        self.assertIn('banter and warmth', rendered)

    def test_boundary_violation_coercion_penalty(self):
        now = dt.datetime(2026, 9, 14, 12, tzinfo=UTC)
        baseline = intimacy.compute(self.c, now)
        base_score = baseline['score']

        # Record a boundary violation
        feelings.record(self.c, {
            'kind': 'rupture',
            'topic': 'intimacy_boundary_violation',
            'text': 'Demanded private photos before emotional readiness',
            'evidence': 'Demanded private photos without consent.',
            'strength': 0.95
        }, now=now)

        penalized = intimacy.compute(self.c, now)
        # Score drops by at least 30 points
        self.assertLessEqual(penalized['score'], base_score - 30)
        self.assertEqual(penalized['violations_count'], 1)
        self.assertEqual(penalized['risk_level'], 'caution')

        # Record second violation -> crisis risk level
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
