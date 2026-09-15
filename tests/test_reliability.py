"""Regressions for the fresh-eyes audit, using disposable profiles only."""
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_workspace as workspace
import companion_config as cc
from kit.app.runtime import Runtime


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = workspace.WorkspaceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_page_versions_its_assets_to_avoid_mixed_cached_controllers(self):
        response = self.fixture.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.text, r'/static/editing\.js\?v=[a-f0-9]{16}')
        self.assertRegex(response.text, r'/static/product\.js\?v=[a-f0-9]{16}')
        self.assertEqual(response.headers['cache-control'], 'no-cache')

    def test_operation_result_is_only_available_to_its_originating_profile(self):
        f = self.fixture
        response = f.post('/api/profile/display-name', {'name': 'Nova workspace'})
        row = f.wait(response)
        self.assertEqual(row['profile'], 'nova')
        self.assertEqual(f.get('/api/operations/' + row['id'], 'rowan').status_code, 404)
        self.assertEqual(f.get('/api/operations/' + row['id']).status_code, 200)

    def test_sharing_preserves_facts_in_both_directions_and_leaves_relationship_alone(self):
        f = self.fixture
        private = f.c.human_dir
        private.mkdir(parents=True, exist_ok=True)
        fact = {'id': 'known', 'kind': 'human_fact', 'category': 'preference',
                'statement': 'Likes tea', 'evidence': 'I like tea', 'source': 'chat',
                'confidence': 'stated', 'status': 'active', 'recorded_at': '2026-09-12T12:00:00+00:00'}
        (private / 'facts.jsonl').write_text(json.dumps(fact) + '\n')
        relationship = f.c.life / 'relationship.jsonl'
        relationship.write_text('relationship stays local\n')
        for shared in (True, False):
            response = f.post('/api/settings', {'share_people': shared})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(f.get('/api/ledgers').json()['facts']), 1)
            self.assertTrue((cc.load(f.c.home).human_dir / 'facts.jsonl').is_file())
            self.assertEqual(relationship.read_text(), 'relationship stays local\n')
        self.assertTrue((private / 'facts.jsonl').is_file())

    def test_sharing_conflict_preserves_configuration_and_both_ledgers(self):
        f = self.fixture
        private = f.c.human_dir
        shared = dataclasses.replace(f.c, share_people=True).human_dir
        for folder, text in ((private, 'private facts'), (shared, 'different shared facts')):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'facts.jsonl').write_text(text)
        before = (f.c.home / cc.CONFIG_NAME).read_bytes()
        response = f.post('/api/settings', {'share_people': True})
        self.assertEqual(response.status_code, 400)
        self.assertEqual((f.c.home / cc.CONFIG_NAME).read_bytes(), before)
        self.assertEqual((private / 'facts.jsonl').read_text(), 'private facts')
        self.assertEqual((shared / 'facts.jsonl').read_text(), 'different shared facts')

    def test_both_editors_reject_photo_sessions_without_style(self):
        f = self.fixture
        before = (f.c.home / cc.CONFIG_NAME).read_bytes()
        payload = f.get('/api/profile/editor').json()
        payload['config'].update(image_timeline=True, image_style='none')
        self.assertEqual(f.post('/api/profile/editor', payload).status_code, 400)
        self.assertEqual(f.post('/api/settings', {'image_timeline': True, 'image_style': 'none'}).status_code, 400)
        self.assertEqual((f.c.home / cc.CONFIG_NAME).read_bytes(), before)

    def test_both_editors_synchronize_and_report_failed_job_updates(self):
        f = self.fixture
        cron = f.c.home / 'cron'
        cron.mkdir(exist_ok=True)
        (cron / 'jobs.json').write_text('{"jobs": []}')
        for route, hour in (('/api/settings', '22:00'), ('/api/profile/editor', '21:00')):
            with self.subTest(route=route):
                payload = {'quiet_start': hour}
                if route.endswith('editor'):
                    payload = f.get('/api/profile/editor').json()
                    payload['config']['quiet_start'] = hour
                with patch.object(Runtime, 'run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='offline')):
                    response = f.post(route, payload)
                    self.assertEqual(response.status_code, 200, response.text)
                    operation = response.json()['operation']
                    row = f.wait(SimpleNamespace(status_code=200, text='', json=lambda: operation))
                self.assertEqual(row['status'], 'failed')
                self.assertIn('Preferences were saved', row['error'])
                self.assertEqual(cc.load(f.c.home).quiet_start, hour)

    def test_browser_regressions(self):
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is needed for browser state regression tests')
        subprocess.run([node, str(Path(__file__).with_name('test_reliability_ui.js'))], check=True)

    def test_model_licence_notice(self):
        """Weights carry their publisher's terms, which are independent of this
        project's licence. The downloader has to show them before fetching."""
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is needed for the model licence regression')
        subprocess.run([node, str(Path(__file__).with_name('test_licence_ui.js'))], check=True)

    def test_creation_interview_stays_inside_the_catalogs(self):
        """The browser interview proposes a persona, a relationship frame and a
        set of answers on its own. Every one of them has to be something the
        backend will actually accept."""
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is needed for the creation interview regression')
        import companion_catalog as catalog
        from kit.cli.questions import known_answer_keys
        subprocess.run([node, str(Path(__file__).with_name('test_onboarding_ui.js')),
                        ','.join(catalog.BOUNDARIES), ','.join(sorted(known_answer_keys()))],
                       check=True)
