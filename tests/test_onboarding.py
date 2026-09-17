"""Tests for onboarding environment detection and setup endpoints."""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from fastapi.testclient import TestClient
import companion_config as cc
from kit.app.server import build

class OnboardingApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name) / 'hermes'
        self.vault = pathlib.Path(self.tmp.name) / 'vault'
        self.root.mkdir(); self.vault.mkdir()
        self.app = build(self.root, token='test-token', state_dir=pathlib.Path(self.tmp.name) / 'state')
        self.client = TestClient(self.app)
        self.headers = {'x-companion-token': 'test-token'}

    def test_onboarding_environment_initial_state(self):
        r = self.client.get('/api/onboarding/environment', headers=self.headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn('profiles_count', data)
        self.assertIn('has_installed_profiles', data)
        self.assertIn('telegram', data)
        self.assertIn('inference', data)
        self.assertEqual(data['profiles_count'], 0)
        self.assertFalse(data['has_installed_profiles'])
        self.assertFalse(data['telegram']['configured'])

    def test_onboarding_telegram_setup_and_validation(self):
        # Invalid token format rejected
        bad_token = self.client.post('/api/onboarding/telegram', headers=self.headers, json={'token': 'invalid-token', 'user_id': '12345'})
        self.assertEqual(bad_token.status_code, 400)
        self.assertIn('Invalid Telegram Bot Token', bad_token.text)

        # Invalid user_id rejected
        bad_user = self.client.post('/api/onboarding/telegram', headers=self.headers, json={'token': '123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ1234', 'user_id': 'abc-not-numeric'})
        self.assertEqual(bad_user.status_code, 400)
        self.assertIn('must be numeric', bad_user.text)

        # Valid token and user_id saved
        good = self.client.post('/api/onboarding/telegram', headers=self.headers, json={
            'token': '123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ1234',
            'user_id': '987654321'
        })
        self.assertEqual(good.status_code, 200)
        self.assertTrue(good.json()['saved'])
        self.assertTrue(good.json()['configured'])

        # Now environment reports configured telegram
        env_r = self.client.get('/api/onboarding/environment', headers=self.headers)
        self.assertEqual(env_r.status_code, 200)
        env_data = env_r.json()
        self.assertTrue(env_data['telegram']['configured'])
        self.assertTrue(env_data['telegram']['has_token'])
        self.assertTrue(env_data['telegram']['has_user_id'])
        self.assertEqual(env_data['telegram']['user_id'], '987654321')

    def test_onboarding_inference_setup(self):
        good = self.client.post('/api/onboarding/inference', headers=self.headers, json={
            'provider': 'openrouter',
            'model': 'anthropic/claude-3.5-sonnet',
            'api_key': 'test-openrouter-mock-key-123'
        })
        self.assertEqual(good.status_code, 200)
        self.assertTrue(good.json()['saved'])

        # Verify environment detects inference setup
        env_r = self.client.get('/api/onboarding/environment', headers=self.headers)
        self.assertEqual(env_r.status_code, 200)
        env_data = env_r.json()
        self.assertTrue(env_data['inference']['configured'])
        self.assertEqual(env_data['inference']['provider'], 'openrouter')
        self.assertEqual(env_data['inference']['model'], 'anthropic/claude-3.5-sonnet')

    def test_onboarding_oauth_endpoints(self):
        # Unknown provider rejected
        bad = self.client.post('/api/onboarding/oauth/start', headers=self.headers, json={'provider': 'unknown_provider'})
        self.assertEqual(bad.status_code, 400)

        # Nonexistent poll returns 404
        poll = self.client.get('/api/onboarding/oauth/poll/nonexistent123', headers=self.headers)
        self.assertEqual(poll.status_code, 404)

    def test_onboarding_environment_local_models(self):
        r = self.client.get('/api/onboarding/environment', headers=self.headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn('local_models', data)
        loc = data['local_models']
        self.assertIn('is_mobile', loc)
        self.assertIn('host_memory', loc)
        self.assertIn('recommendations', loc)
        self.assertIn('recommended_gguf', loc)
        self.assertTrue(len(loc['recommended_gguf']) > 0)

    def test_onboarding_local_setup(self):
        from unittest.mock import patch
        import time
        from kit.app import local_models as lm
        mock_res = {'ok': True, 'path': '/fake/path/model.gguf', 'model': 'qwen2.5-1.5b-instruct-q4_k_m'}
        with patch.object(lm, 'download_gguf', return_value=mock_res), patch.object(lm, 'status', return_value={'online': True}):
            r = self.client.post('/api/onboarding/local-setup', headers=self.headers, json={
                'model_id': 'qwen2.5-1.5b-instruct-q4_k_m',
                'type': 'gguf'
            })
            self.assertEqual(r.status_code, 200)
            data = r.json()
            self.assertIn('id', data)
            op_id = data['id']
            for _ in range(20):
                poll = self.client.get(f'/api/operations/{op_id}', headers=self.headers).json()
                if poll['status'] in ('complete', 'failed'):
                    break
                time.sleep(0.05)
            self.assertEqual(poll['status'], 'complete', poll)
            self.assertEqual(poll['result']['model'], 'qwen2.5-1.5b')

if __name__ == '__main__':
    unittest.main()
