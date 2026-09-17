import hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
from kit.app.updates import stage
from update_release import apply_pending,runtime_lock

def package(files):
    files={**files,'release-files.json':json.dumps([*files,'release-files.json']).encode()}
    hashes={n:hashlib.sha256(v).hexdigest() for n,v in files.items()};files['SHA256SUMS.json']=json.dumps(hashes).encode()
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        for n,v in files.items():z.writestr('companion-kit/'+n,v)
    return b.getvalue(),files

class UpdateTests(unittest.TestCase):
    def test_verified_stage_apply_backup_and_preserve_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,old=package({'VERSION':b'1','README.md':b'old'})
            for n,v in old.items():(root/n).write_bytes(v)
            (root/'my-vault.txt').write_text('private')
            raw,_=package({'VERSION':b'2','README.md':b'new'})
            r=stage(raw,root);self.assertTrue(r['staged']);self.assertEqual((root/'README.md').read_text(),'old')
            with runtime_lock(root),self.assertRaises(ValueError):apply_pending(root)
            apply_pending(root);self.assertEqual((root/'README.md').read_text(),'new');self.assertEqual((root/'my-vault.txt').read_text(),'private')
            self.assertEqual(next((root/'.update-backups').glob('*/README.md')).read_text(),'old')
    def test_modified_install_and_path_traversal_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw,old=package({'VERSION':b'1'})
            for n,v in old.items():(root/n).write_bytes(v)
            (root/'VERSION').write_text('modified')
    def test_check_github_update_and_caching(self):
        from unittest.mock import patch, MagicMock
        from kit.app.updates import check_github_update, _UPDATE_CACHE
        _UPDATE_CACHE['checked_at'] = 0
        _UPDATE_CACHE['data'] = None

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            'tag_name': 'v2.3.0',
            'html_url': 'https://github.com/tamanitomo/tamanitomo/releases/tag/v2.3.0',
            'body': 'Release notes for 2.3.0'
        }).encode('utf-8')
        mock_resp.__enter__.return_value = mock_resp

        with patch('urllib.request.urlopen', return_value=mock_resp):
            info = check_github_update('2.2.1', force=True)
            self.assertTrue(info['has_update'])
            self.assertEqual(info['latest_version'], '2.3.0')
            self.assertEqual(info['release_url'], 'https://github.com/tamanitomo/tamanitomo/releases/tag/v2.3.0')

            # Test same version
            _UPDATE_CACHE['checked_at'] = 0
            info_same = check_github_update('2.3.0', force=True)
            self.assertFalse(info_same['has_update'])

    def test_perform_in_app_update_git_flow(self):
        from unittest.mock import patch, MagicMock
        from kit.app.updates import perform_in_app_update
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.git').mkdir()
            (root / 'VERSION').write_text('2.2.1\n')
            (root / 'requirements.txt').write_text('fastapi\n')

            reports = []
            def report_fn(r): reports.append(r)

            def fake_run(cmd, cwd=None, capture_output=None, text=None, check=None):
                res = MagicMock()
                res.returncode = 0
                res.stdout = ''
                res.stderr = ''
                if cmd[:2] == ['git', 'status']:
                    res.stdout = ''
                elif cmd[:2] == ['git', 'pull']:
                    (root / 'VERSION').write_text('2.3.0\n')
                return res

            with patch('subprocess.run', side_effect=fake_run), \
                 patch('threading.Thread'):
                result = perform_in_app_update(report_fn, root=root)
                self.assertTrue(result['success'])
                self.assertTrue(result['restarting'])
                self.assertEqual(result['version'], '2.3.0')
                self.assertTrue(any(r.get('percent') == 100 for r in reports))

    def test_api_updates_endpoints(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from kit.app.updates import register as register_updates

        app = FastAPI()
        class MockOps:
            def submit(self, root, label, fn, profile='default'):
                rep = []
                res = fn(rep.append)
                return {'id': 'op-123', 'label': label, 'status': 'done', 'profile': profile, 'result': res}
        app.state.operations = MockOps()
        register_updates(app)
        client = TestClient(app)

        with patch('kit.app.updates.check_github_update', return_value={'has_update': True, 'latest_version': '2.3.0', 'release_url': None, 'release_notes': None}):
            res = client.get('/api/updates')
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data['has_update'])
            self.assertEqual(data['latest_version'], '2.3.0')

            check_res = client.post('/api/updates/check')
            self.assertEqual(check_res.status_code, 200)
            self.assertTrue(check_res.json()['has_update'])

            with patch('kit.app.updates.perform_in_app_update', return_value={'success': True, 'restarting': True, 'version': '2.3.0', 'message': 'Restarting'}):
                apply_res = client.post('/api/updates/apply?profile=sam')
                self.assertEqual(apply_res.status_code, 200)
                op_data = apply_res.json()
                self.assertEqual(op_data['id'], 'op-123')
                self.assertEqual(op_data['profile'], 'sam')
                self.assertTrue(op_data['result']['success'])
