import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'kit/scripts')]
import companion_workflow as wf
import companion_media as media
import companion_model_download as downloader
from kit.app import workflows
from tests.test_workspace import WorkspaceTests

class WorkflowTests(unittest.TestCase):
    def test_modular_branches_and_img2img_keep_models(self):
        p=wf.modular_template();media.validate({'version':1,'presets':[p]})
        self.assertEqual(set(wf.PROMPT_NODES),set(p['mappings'])&set(media.PARTS))
        original=copy.deepcopy(p);derived=wf.image_to_image(p,.3)
        self.assertEqual(p,original)
        self.assertEqual(derived['workflow']['1'],p['workflow']['1'])
        self.assertEqual(derived['workflow']['302']['inputs']['positive'],['115',0])
        self.assertEqual(derived['workflow']['302']['inputs']['denoise'],.3)
        self.assertTrue(derived['requires_reference']);media.validate({'version':1,'presets':[derived]})
        derived['workflow']['900']=copy.deepcopy(derived['workflow']['302'])
        with self.assertRaises(ValueError):wf.image_to_image(derived)

    def test_family_guard_and_disabled_lora(self):
        spec={'family':'sdxl','name':'Example','model':{'filename':'model.safetensors','family':'sdxl'},'loras':[{'filename':'foreign.safetensors','family':'krea2','enabled':True}]}
        with self.assertRaisesRegex(ValueError,'belongs'):wf.create_recipe(spec)
        spec['loras'][0]['enabled']=False
        result=wf.create_recipe(spec)
        self.assertFalse(any(n['class_type']=='LoraLoader' for n in result['workflow'].values()))
        spec['model']['family']='unknown'
        with self.assertRaisesRegex(ValueError,'Confirm'):wf.create_recipe(spec)
        spec['model']['confirm_family']=True;wf.create_recipe(spec)

    def test_krea_slots_and_lora_wiring(self):
        spec={'family':'krea2','name':'Example',**{k:{'filename':name,'family':'krea2'} for k,name in [('model','model.gguf'),('clip','encoder.safetensors'),('vae','vae.safetensors')]},'loras':[{'filename':'detail.safetensors','family':'krea2','strength_model':.5,'strength_clip':.25}]}
        p=wf.create_recipe(spec);self.assertEqual(p['workflow']['1']['class_type'],'UnetLoaderGGUF')
        self.assertEqual(p['workflow']['302']['inputs']['model'],['500',0])
        self.assertEqual(p['workflow']['101']['inputs']['clip'],['500',1])
        self.assertEqual(p['workflow']['303']['inputs']['vae'],['10',0])
        media.validate({'version':1,'presets':[p]})

    def test_download_checks_hash_and_never_overwrites(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'main.py').write_text('');body=b'weights'
            payload={'root':tmp,'slot':'lora','filename':'test.safetensors','url':'https://civitai.com/api/download/models/1','sha256':hashlib.sha256(body).hexdigest(),'size_bytes':len(body)}
            with patch.object(downloader,'open_url',return_value=io.BytesIO(body)):
                result=downloader.download(payload)
            self.assertEqual(result['bytes'],len(body))
            self.assertTrue(downloader.download(payload)['reused'])
            payload['sha256']='a'*64
            with self.assertRaisesRegex(ValueError,'different file'):downloader.download(payload)
            payload['filename']='other.safetensors'
            with patch.object(downloader,'open_url',return_value=io.BytesIO(body)),self.assertRaisesRegex(ValueError,'SHA-256'):downloader.download(payload)
            self.assertFalse((root/'models/loras/other.safetensors').exists())
            self.assertFalse(list((root/'models/loras').glob('*.partial')))
            payload['filename']='../escape.safetensors'
            with self.assertRaises(ValueError):downloader.download(payload)

    def test_redirect_does_not_forward_civitai_key_to_cdn(self):
        import urllib.request
        import urllib.parse
        request=urllib.request.Request('https://civitai.com/api/download/models/1',headers={'Authorization':'Bearer private-key'})
        with patch.object(downloader,'public_https',side_effect=urllib.parse.urlsplit):
            redirected=downloader.Redirects().redirect_request(request,None,302,'Found',{},'https://cdn.example.com/file')
            self.assertIsNone(redirected.get_header('Authorization'))
            same_host=downloader.Redirects().redirect_request(request,None,302,'Found',{},'https://civitai.com/other')
            self.assertEqual(same_host.get_header('Authorization'),'Bearer private-key')
        with patch.object(downloader.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaisesRegex(ValueError,'Private'):downloader.public_https('https://example.com/file')

    def test_url_and_secret_boundaries(self):
        self.assertEqual(workflows.identify('https://civitai.com/models/123/name?modelVersionId=456'),(123,456))
        for url in ['http://civitai.com/models/1','https://example.com/models/1','https://civitai.com@localhost/models/1']:
            with self.assertRaises(ValueError):workflows.identify(url)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);public=workflows.save_settings(root,{'api_key':'secret'})
            self.assertNotIn('secret',json.dumps(public));self.assertTrue(public['api_key_configured'])
            workflows.save_settings(root,{'api_key':''});self.assertEqual(workflows.settings(root)['api_key'],'secret')
            with self.assertRaises(ValueError):workflows.save_settings(root,{'mode':'ssh','host':'-oProxyCommand=bad'})

class WorkflowRoutes(unittest.TestCase):
    setUp=WorkspaceTests.setUp
    post=WorkspaceTests.post
    get=WorkspaceTests.get
    def test_build_checks_installed_schema_and_returns_private_free_template(self):
        spec={'name':'Example','family':'sdxl','model':{'filename':'model.safetensors','family':'sdxl'},'loras':[]}
        graph=wf.create_recipe(spec)['workflow'];schema={n['class_type']:{'input':{'required':{}}} for n in graph.values()}
        with patch.object(media,'request_json',return_value=schema):
            response=self.post('/api/workflows/build',spec)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['mappings']['identity'],['102','text'])
        self.assertEqual(response.json()['parts'].get('identity',''),'')
        with patch.object(media,'request_json',return_value={}):self.assertEqual(self.post('/api/workflows/build',spec).status_code,400)
