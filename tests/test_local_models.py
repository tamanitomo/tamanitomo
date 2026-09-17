"""Local stack boundary tests: verified provisioning, profile isolation and OAuth dispatch."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile
import yaml
from tests import test_workspace as fixtures
from kit.app import local_models as lm
import companion_config as cc
import companion_media as media
import companion_image_provider as bridge

class LocalStackTests(unittest.TestCase):
    setUp=fixtures.WorkspaceTests.setUp
    get=fixtures.WorkspaceTests.get
    post=fixtures.WorkspaceTests.post
    wait=fixtures.WorkspaceTests.wait

    def test_timezone_catalog_and_editor_sync_hermes(self):
        zones=self.get('/api/catalog').json()['timezones']
        self.assertIn('America/New_York',zones);self.assertIn('UTC',zones)
        d=self.get('/api/profile/editor').json();d['config']['timezone']='Pacific/Auckland'
        self.assertEqual(self.post('/api/profile/editor',d).status_code,200)
        self.assertEqual(yaml.safe_load((self.c.home/'config.yaml').read_text())['timezone'],'Pacific/Auckland')
        self.assertFalse((self.other.home/'config.yaml').exists())

    def test_assign_requires_installed_tool_capable_local_model_and_successful_inference(self):
        ident=lm.MODELS[0]['id']
        self.c.models={'loops':{'model':'cloud','provider':'openrouter'}};self.c.save()
        companion_path=self.c.home/cc.CONFIG_NAME
        raw=json.loads(companion_path.read_text());raw['future_extension']={'keep':True};companion_path.write_text(json.dumps(raw))
        (self.c.home/'config.yaml').write_text(yaml.safe_dump({'tts':{'provider':'pockettts'},'model':{'api_key':'old-credential','api_mode':'responses'},'fallback_providers':[{'model':'cloud'}]}))
        before=(self.other.home/cc.CONFIG_NAME).read_bytes()
        def request(path,payload=None,timeout=5):
            if path=='/api/tags':return {'models':[{'name':ident}]}
            if path=='/api/show':return {'capabilities':['completion','tools']}
            self.assertEqual(payload['model'],ident);return {'message':{'content':'OK'},'done':True}
        with patch.object(lm,'request',side_effect=request):
            row=self.wait(self.post('/api/local-models/assign',{'model':ident}))
        self.assertEqual(row['status'],'complete',row)
        cfg=yaml.safe_load((self.c.home/'config.yaml').read_text())
        self.assertEqual(cfg['model']['provider'],'ollama');self.assertEqual(cfg['fallback_providers'],[])
        self.assertNotIn('api_key',cfg['model']);self.assertEqual(cfg['tts']['provider'],'pockettts')
        self.assertEqual(cc.load(self.c.home).models,{})
        self.assertEqual(json.loads(companion_path.read_text())['future_extension'],{'keep':True})
        self.assertEqual((self.other.home/cc.CONFIG_NAME).read_bytes(),before)
        saved=(self.c.home/'config.yaml').read_bytes()
        for info in ({'capabilities':['completion']},{'capabilities':['tools'],'remote_host':'https://ollama.com'}):
            with patch.object(lm,'request',side_effect=[{'models':[{'name':ident}]},info]):
                row=self.wait(self.post('/api/local-models/assign',{'model':ident}))
                self.assertEqual(row['status'],'failed')
        with patch.object(lm,'request',side_effect=[{'models':[{'name':ident}]},{'capabilities':['tools']},ValueError('out of memory')]):
            row=self.wait(self.post('/api/local-models/assign',{'model':ident}));self.assertEqual(row['status'],'failed')
        self.assertEqual((self.c.home/'config.yaml').read_bytes(),saved)

    def test_model_download_rejects_unlisted_names_without_network_or_launch(self):
        with patch.object(lm,'start') as start:
            row=self.wait(self.post('/api/local-models/pull',{'model':'someone/cloud:latest'}))
            self.assertEqual(row['status'],'failed');start.assert_not_called()
        self.assertEqual(self.client.post('/api/local-models/install').status_code,401)

    def test_memory_guardrails_and_mobile_status(self):
        mem = lm.get_host_memory()
        self.assertIn('total_mb', mem)
        self.assertIn('available_mb', mem)
        self.assertIn('is_mobile', mem)

        # Test safety validation on mobile
        safe, msg = lm.validate_model_safety(5.2, {'is_mobile': True, 'available_mb': 5000, 'total_mb': 12000})
        self.assertFalse(safe)
        self.assertIn('exceeds mobile safety limit', msg)

        # Safe compact model on mobile
        safe_mob, msg_mob = lm.validate_model_safety(1.5, {'is_mobile': True, 'available_mb': 5000, 'total_mb': 12000})
        self.assertTrue(safe_mob)

        # Model exceeding available RAM on mobile
        safe_tight, msg_tight = lm.validate_model_safety(2.0, {'is_mobile': True, 'available_mb': 1000, 'total_mb': 12000})
        self.assertFalse(safe_tight)
        self.assertIn('requires more than the available system RAM', msg_tight)

        # Mobile-aware status endpoint
        with patch.object(lm, 'is_mobile', return_value=True):
            data = self.get('/api/local-models').json()
            self.assertTrue(data['is_mobile'])
            self.assertEqual(data['safety_limit_gb'], 2.8)
            self.assertEqual(data['recommendations'], lm.MOBILE_MODELS)

        with patch.object(lm, 'is_mobile', return_value=False):
            data_desktop = self.get('/api/local-models').json()
            self.assertFalse(data_desktop['is_mobile'])
            self.assertIsNone(data_desktop['safety_limit_gb'])
            self.assertEqual(data_desktop['recommendations'], lm.MODELS)

    def test_mobile_pull_blocks_large_models(self):
        with patch.object(lm, 'is_mobile', return_value=True), patch.object(lm, 'start') as start:
            row = self.wait(self.post('/api/local-models/pull', {'model': 'qwen3:8b-q4_K_M'}))
            self.assertEqual(row['status'], 'failed')
            self.assertIn('exceeds mobile safety limit', row.get('error', ''))
            start.assert_not_called()


    def test_connected_oauth_presets_are_drafts_and_preserve_saved_routes(self):
        connected=[{'id':'hermes-openai-codex','name':'ChatGPT','provider':'hermes','hermes_provider':'openai-codex',
                    'model':'','category':'realistic','parts':{},'endpoint':'','active':True,'available':True}]
        with patch.object(media,'discovered_presets',return_value=connected):
            response=self.get('/api/images');self.assertEqual(response.status_code,200,response.text)
            data=response.json();self.assertEqual(data['settings']['default_preset'],'hermes-openai-codex')
            self.assertFalse((self.c.home/media.CONFIG).exists())
            data['settings']['routes']={'realistic':'hermes-openai-codex'}
            self.assertEqual(self.post('/api/images',{'settings':data['settings'],'revision':data['revision']}).status_code,200)
            again=self.get('/api/images').json()['settings'];self.assertEqual(len(again['presets']),1)
            self.assertEqual(again['routes']['realistic'],'hermes-openai-codex')
        with patch.object(media,'discovered_presets',side_effect=ValueError('Reconnect Hermes')):
            data=self.get('/api/images').json();self.assertEqual(len(data['settings']['presets']),1)
            self.assertIn('Reconnect',data['provider_warning'])

    def test_hermes_plugin_dispatch_pins_provider_without_writing_config(self):
        fake=types.ModuleType('tools.image_generation_tool')
        fake._read_image_gen_key=lambda key:'other-provider' if key=='provider' else 'other-model'
        def handler(payload):
            self.assertEqual(fake._read_image_gen_key('provider'),'openai-codex')
            self.assertIsNone(fake._read_image_gen_key('model'))
            self.assertEqual(payload['prompt'],'a realistic portrait')
            return json.dumps({'success':True,'image':'/tmp/photo.png'})
        fake._handle_image_generate=handler
        package=types.ModuleType('tools');package.image_generation_tool=fake
        with patch.dict('sys.modules',{'tools':package,'tools.image_generation_tool':fake}):
            result=bridge.generate({'hermes_provider':'openai-codex','prompt':'a realistic portrait'})
        self.assertTrue(result['success']);self.assertFalse((self.c.home/'config.yaml').exists())

class ArchiveTests(unittest.TestCase):
    def test_install_checks_digest_before_extracting_and_can_retry(self):
        from kit.app.runtime import Runtime
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:z.writestr('ollama.exe',b'test binary')
        raw=data.getvalue()
        with tempfile.TemporaryDirectory() as temp:
            rt=Runtime(Path(temp))
            asset={'name':'ollama-windows-amd64.zip','digest':'sha256:'+hashlib.sha256(raw).hexdigest(),
                   'size':len(raw),'browser_download_url':'https://github.com/ollama/ollama/releases/download/vtest/test.zip'}
            for valid in (False,True):
                body=raw if valid else raw[:-1]+b'x'
                metadata=json.dumps({'tag_name':'vtest','assets':[asset]}).encode()
                with patch.object(lm,'binary',return_value=None),patch.object(lm,'asset_name',return_value=asset['name']),patch.object(lm.urllib.request,'urlopen',side_effect=[io.BytesIO(metadata),io.BytesIO(body)]):
                    if valid:lm.install(rt,lambda x:None)
                    else:
                        with self.assertRaisesRegex(ValueError,'integrity'):lm.install(rt,lambda x:None)
                        self.assertFalse((lm.directory(rt)/'runtime').exists())
            self.assertEqual((lm.directory(rt)/'runtime/ollama.exe').read_bytes(),b'test binary')

    def test_linux_zstd_archive_preserves_executable(self):
        import zstandard
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w') as bundle:
            item=tarfile.TarInfo('bin/ollama');item.mode=0o755;item.size=4;bundle.addfile(item,io.BytesIO(b'test'))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);dest=root/'runtime';dest.mkdir();archive=root/'linux.tar.zst'
            archive.write_bytes(zstandard.ZstdCompressor().compress(data.getvalue()))
            lm.extract(archive,dest)
            self.assertEqual((dest/'bin/ollama').read_bytes(),b'test')
            self.assertTrue((dest/'bin/ollama').stat().st_mode & 0o100)

    def test_archives_cannot_escape_staging(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);dest=root/'stage';dest.mkdir()
            archive=root/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape',b'bad')
            with self.assertRaises(ValueError):lm.extract(archive,dest)
            archive=root/'bad.tgz'
            with tarfile.open(archive,'w:gz') as t:
                item=tarfile.TarInfo('outside');item.type=tarfile.SYMTYPE;item.linkname='../../escape';t.addfile(item)
            with self.assertRaises(tarfile.FilterError):lm.extract(archive,dest)
            self.assertFalse((root/'escape').exists())

if __name__=='__main__':unittest.main()
