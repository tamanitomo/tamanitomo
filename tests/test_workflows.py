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

class InteractiveExportTests(unittest.TestCase):
    """The editor format has to be rebuilt from the API graph plus /object_info.

    Widget order is the whole game: a workflow whose widgets_values are off by
    one opens in ComfyUI with the steps in the cfg box. These cases are drawn
    from a real ComfyUI schema and a real saved workflow.
    """
    SCHEMA={
      'CheckpointLoaderSimple':{'input':{'required':{'ckpt_name':[['a.safetensors','b.safetensors']]}},
        'output':['MODEL','CLIP','VAE'],'output_name':['MODEL','CLIP','VAE']},
      'CLIPTextEncode':{'input':{'required':{'text':['STRING',{'multiline':True,'default':''}],'clip':['CLIP']}},
        'output':['CONDITIONING'],'output_name':['CONDITIONING']},
      'StringConcatenate':{'input':{'required':{'string_a':['STRING',{'default':''}],
        'string_b':['STRING',{'default':''}],'delimiter':['STRING',{'default':''}]}},
        'output':['STRING'],'output_name':['STRING']},
      'EmptyLatentImage':{'input':{'required':{'width':['INT',{'default':512}],'height':['INT',{'default':512}],
        'batch_size':['INT',{'default':1}]}},'output':['LATENT'],'output_name':['LATENT']},
      'KSampler':{'input':{'required':{'model':['MODEL'],'seed':['INT',{'default':0}],
        'steps':['INT',{'default':20}],'cfg':['FLOAT',{'default':8.}],'sampler_name':[['euler','dpmpp_2m']],
        'scheduler':[['normal','karras']],'positive':['CONDITIONING'],'negative':['CONDITIONING'],
        'latent_image':['LATENT'],'denoise':['FLOAT',{'default':1.}]}},'output':['LATENT'],'output_name':['LATENT']},
      'VAEDecode':{'input':{'required':{'samples':['LATENT'],'vae':['VAE']}},'output':['IMAGE'],'output_name':['IMAGE']},
      'SaveImage':{'input':{'required':{'images':['IMAGE'],'filename_prefix':['STRING',{'default':'ComfyUI'}]}},
        'output':[],'output_name':[]}}

    def graph(self):
        return {'1':{'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':'b.safetensors'}},
          '2':{'class_type':'CLIPTextEncode','inputs':{'clip':['1',1],'text':'a cat'}},
          '3':{'class_type':'CLIPTextEncode','inputs':{'clip':['1',1],'text':'blurry'}},
          '4':{'class_type':'EmptyLatentImage','inputs':{'width':832,'height':1216,'batch_size':1}},
          '5':{'class_type':'KSampler','inputs':{'model':['1',0],'positive':['2',0],'negative':['3',0],
            'latent_image':['4',0],'seed':7,'steps':22,'cfg':5.,'sampler_name':'euler','scheduler':'normal','denoise':1.}},
          '6':{'class_type':'VAEDecode','inputs':{'samples':['5',0],'vae':['1',2]}},
          '7':{'class_type':'SaveImage','inputs':{'images':['6',0],'filename_prefix':'Companion'}}}

    def nodes(self,ui):
        return {str(n['id']):n for n in ui['nodes']}

    def test_widgets_keep_their_declared_order_and_seed_control(self):
        ui=wf.interactive_graph(self.graph(),self.SCHEMA,'Test')
        sampler=self.nodes(ui)['5']
        # Sockets never enter widgets_values; the seed's control widget does.
        self.assertEqual(sampler['widgets_values'],[7,'randomize',22,5.,'euler','normal',1.])
        self.assertEqual([i['name'] for i in sampler['inputs']],
                         ['model','positive','negative','latent_image'])
        self.assertEqual([o['type'] for o in self.nodes(ui)['1']['outputs']],['MODEL','CLIP','VAE'])

    def test_converted_widgets_keep_their_slot_in_widgets_values(self):
        """A linked widget still occupies its place, or later widgets shift."""
        graph=self.graph()
        graph['8']={'class_type':'StringConcatenate','inputs':{'string_a':['2',0],'string_b':['3',0],'delimiter':', '}}
        ui=wf.interactive_graph(graph,self.SCHEMA,'Test')
        joiner=self.nodes(ui)['8']
        self.assertEqual(joiner['widgets_values'],['','',', '])
        self.assertEqual([i['name'] for i in joiner['inputs']],['string_a','string_b'])
        self.assertTrue(all('widget' in i for i in joiner['inputs']))

    def test_links_are_numbered_and_agree_from_both_ends(self):
        ui=wf.interactive_graph(self.graph(),self.SCHEMA,'Test')
        nodes=self.nodes(ui)
        ids=[l[0] for l in ui['links']]
        self.assertEqual(sorted(ids),list(range(1,len(ids)+1)))
        self.assertEqual(ui['last_link_id'],len(ids))
        for link,origin,slot,target,target_slot,wire in ui['links']:
            self.assertEqual(nodes[str(target)]['inputs'][target_slot]['link'],link)
            self.assertIn(link,nodes[str(origin)]['outputs'][slot]['links'])
            self.assertEqual(nodes[str(origin)]['outputs'][slot]['type'],wire)

    def test_execution_order_follows_the_links(self):
        ui=wf.interactive_graph(self.graph(),self.SCHEMA,'Test')
        order={str(n['id']):n['order'] for n in ui['nodes']}
        self.assertLess(order['1'],order['2'])
        self.assertLess(order['2'],order['5'])
        self.assertLess(order['5'],order['6'])
        self.assertLess(order['6'],order['7'])

    def test_it_refuses_rather_than_guessing(self):
        with self.assertRaises(ValueError):wf.interactive_graph({},self.SCHEMA)
        with self.assertRaises(ValueError):wf.interactive_graph(self.graph(),{})
        unknown=self.graph();unknown['9']={'class_type':'SomeCustomNode','inputs':{}}
        with self.assertRaisesRegex(ValueError,'SomeCustomNode'):wf.interactive_graph(unknown,self.SCHEMA)
        loop=self.graph();loop['4']['inputs']['width']=['5',0]
        with self.assertRaisesRegex(ValueError,'loop'):wf.interactive_graph(loop,self.SCHEMA)


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
