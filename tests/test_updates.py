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
            with self.assertRaisesRegex(ValueError, 'Local code changes'):
                stage(raw,root)
            malicious,_=package({'../escape':b'bad'})
            with self.assertRaisesRegex(ValueError, 'Unsafe release path'):
                stage(malicious,root)
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
            'body': 'Release notes for 2.3.0',
            'assets': [{'name': 'tamanitomo-release.zip', 'browser_download_url': 'https://github.com/tamanitomo/tamanitomo/releases/download/v2.3.0/tamanitomo-release.zip'}]
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

            def fake_run(cmd, **kwargs):
                res = MagicMock()
                res.returncode = 0
                res.stdout = ''
                res.stderr = ''
                if cmd[:2] == ['git', 'status']:
                    res.stdout = ''
                elif cmd[:2] == ['git', 'show']:
                    res.stdout = '2.3.0' if cmd[-1].endswith(':VERSION') else 'fastapi'
                elif cmd[:2] == ['git', 'merge']:
                    (root / 'VERSION').write_text('2.3.0\n')
                return res

            with patch('subprocess.run', side_effect=fake_run), \
                 patch('kit.app.updates.check_github_update', return_value={'checked': True, 'has_update': True, 'latest_version': '2.3.0', 'tag': 'v2.3.0'}), \
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

class OfficialReleaseTests(unittest.TestCase):
    def info(self, **overrides):
        return dict(checked=True, has_update=True, latest_version='2.3.0',
                    download_url='https://github.com/tamanitomo/tamanitomo/releases/download/v2.3.0/tamanitomo-release.zip', **overrides)

    def install(self, root):
        _,files=package({'VERSION':b'2.2.1', 'requirements.txt':b'fastapi\n', 'README.md':b'old'})
        for name,data in files.items():(root/name).write_bytes(data)

    def test_zip_update_restarts_and_preserves_external_state(self):
        from unittest.mock import patch, MagicMock
        from kit.app.updates import perform_in_app_update
        raw,_=package({'VERSION':b'2.3.0','requirements.txt':b'fastapi\n','README.md':b'new'})
        response=MagicMock();response.__enter__.return_value=response;response.read.return_value=raw
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'app';root.mkdir();self.install(root)
            vault=Path(tmp)/'vault';vault.mkdir();(vault/'memory').write_bytes(b'private memory')
            (root/'local-note.txt').write_bytes(b'private note')
            with patch('kit.app.updates.check_github_update',return_value=self.info(digest='sha256:'+hashlib.sha256(raw).hexdigest())), \
                 patch('urllib.request.urlopen',return_value=response), patch('threading.Thread') as thread, \
                 patch('subprocess.run') as run:
                result=perform_in_app_update(lambda _:None,root)
            self.assertTrue(result['restarting']);thread.return_value.start.assert_called_once();run.assert_not_called()
            self.assertEqual((root/'VERSION').read_text(),'2.3.0')
            self.assertEqual((vault/'memory').read_bytes(),b'private memory')
            self.assertEqual((root/'local-note.txt').read_bytes(),b'private note')
            self.assertEqual(next((root/'.update-backups').glob('*/README.md')).read_bytes(),b'old')

    def test_failed_dependencies_leave_code_unchanged_and_clear_staging(self):
        from unittest.mock import patch,MagicMock
        from kit.app.updates import perform_in_app_update
        raw,_=package({'VERSION':b'2.3.0','requirements.txt':b'new-dependency\n','README.md':b'new'})
        response=MagicMock();response.__enter__.return_value=response;response.read.return_value=raw
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.install(root)
            with patch('kit.app.updates.check_github_update',return_value=self.info()), \
                 patch('urllib.request.urlopen',return_value=response), \
                 patch('subprocess.run',return_value=MagicMock(returncode=1,stderr='offline')),patch('threading.Thread') as thread:
                with self.assertRaisesRegex(ValueError,'Dependency installation failed'):
                    perform_in_app_update(lambda _:None,root)
            self.assertEqual((root/'VERSION').read_text(),'2.2.1')
            self.assertFalse((root/'.pending-update').exists());thread.assert_not_called()

    def test_corrupt_download_is_refused_before_staging(self):
        from unittest.mock import patch,MagicMock
        from kit.app.updates import perform_in_app_update
        response=MagicMock();response.__enter__.return_value=response;response.read.return_value=b'corrupt'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.install(root)
            with patch('kit.app.updates.check_github_update',return_value=self.info(digest='sha256:incorrect')), \
                 patch('urllib.request.urlopen',return_value=response):
                with self.assertRaisesRegex(ValueError,'digest'):
                    perform_in_app_update(lambda _:None,root)
            self.assertFalse((root/'.pending-update').exists())
            self.assertEqual((root/'VERSION').read_text(),'2.2.1')

    def test_no_update_does_not_restart_or_download(self):
        from unittest.mock import patch
        from kit.app.updates import perform_in_app_update
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.install(root)
            with patch('kit.app.updates.check_github_update',return_value={'checked':True,'has_update':False}), \
                 patch('urllib.request.urlopen') as download, patch('threading.Thread') as thread:
                result=perform_in_app_update(lambda _:None,root)
            self.assertFalse(result['restarting']);download.assert_not_called();thread.assert_not_called()

    def test_newer_local_version_is_not_downgraded_and_errors_are_not_cached(self):
        from unittest.mock import patch,MagicMock
        from kit.app.updates import check_github_update,_UPDATE_CACHE
        response=MagicMock();response.__enter__.return_value=response
        response.read.return_value=json.dumps({'tag_name':'v2.3.0','assets':[{
            'name':'tamanitomo-release.zip',
            'browser_download_url':'https://github.com/tamanitomo/tamanitomo/releases/download/v2.3.0/tamanitomo-release.zip'}]}).encode()
        with patch('urllib.request.urlopen',return_value=response) as get:
            self.assertFalse(check_github_update('2.4.0',force=True)['has_update'])
            self.assertTrue(check_github_update('2.2.1')['has_update'])
            self.assertEqual(get.call_count,2)
        _UPDATE_CACHE.clear()
        with patch('urllib.request.urlopen',side_effect=OSError('offline')) as get:
            self.assertFalse(check_github_update('2.2.1')['checked'])
            self.assertIn('offline',check_github_update('2.2.1')['error'])
            self.assertEqual(get.call_count,2)

    def test_restart_targets_only_current_workspace(self):
        import os
        from unittest.mock import patch,MagicMock
        from kit.app.updates import _delayed_restart
        commands=[]
        def run(args,**kwargs):
            commands.append(args)
            return MagicMock(returncode=0,stdout=str(os.getpid()) if 'companion-workspace.service' in args else '123')
        with patch('time.sleep'),patch('shutil.which',return_value='/usr/bin/systemctl'), \
             patch('subprocess.run',side_effect=run),patch('os.execv') as execute:
            _delayed_restart()
        self.assertEqual(commands[-1],['systemctl','--user','restart','--no-block','companion-workspace.service'])
        self.assertFalse(any('gateway' in ' '.join(c) for c in commands));execute.assert_not_called()
