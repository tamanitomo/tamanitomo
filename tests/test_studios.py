"""Management contracts: isolation, protection, real provider payloads and recovery."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'kit/scripts')]
import companion_config as cc
import companion_media as media
import companion_portrait as portrait
from kit.app import vault,profile_editor,speech
from tests import test_workspace as workspace_tests

class StudioTests(unittest.TestCase):
    setUp=workspace_tests.WorkspaceTests.setUp
    get=workspace_tests.WorkspaceTests.get
    post=workspace_tests.WorkspaceTests.post
    wait=workspace_tests.WorkspaceTests.wait
    def test_identity_repair_wraps_authored_prose_instead_of_hiding_it(self):
        import companion_identity as identity
        self.c.soul.parent.mkdir(parents=True,exist_ok=True)
        original='## Physical Description\nAn adult with green eyes.\n\n<!-- COMPANION-SECTION:appearance LOCKED -->\n<!-- /COMPANION-SECTION:appearance -->\n'
        self.c.soul.write_text(original)
        r=self.post('/api/identity-repair',{})
        self.assertEqual(r.status_code,200,r.text)
        after=self.c.soul.read_text()
        self.assertIn('An adult with green eyes.',identity.sections(after)['appearance']['body'])
        self.assertEqual(portrait.identity_block(self.c),'An adult with green eyes.')

    def test_trash_restore_conflict_and_critical_protection(self):
        note=self.vault/'notes'/'hello.md';note.parent.mkdir();note.write_text('keep me')
        body=self.client.get('/api/vault/file?profile=nova&path=notes/hello.md',headers=self.headers).json()
        note.write_text('newer')
        self.assertEqual(self.post('/api/vault/trash',{'path':body['path'],'revision':body['revision']}).status_code,409)
        r=self.post('/api/vault/trash',{'path':'notes/hello.md'});self.assertEqual(r.status_code,200,r.text)
        ident=r.json()['id'];self.assertFalse(note.exists());self.assertEqual(len(self.get('/api/vault/trash').json()['files']),1)
        note.write_text('replacement');self.assertEqual(self.post('/api/vault/restore',{'id':ident}).status_code,409)
        self.assertEqual(note.read_text(),'replacement');note.unlink()
        self.assertEqual(self.post('/api/vault/restore',{'id':ident}).status_code,200)
        self.assertEqual(note.read_text(),'newer')
        for rel in ['soul/SOUL.md','agents/rowan/soul/identity.md','agents/nova/companion-life/PRESENCE.md','scripts/start.py','AGENTS.md']:
            path=self.vault/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('critical')
            info=vault.read(self.c,rel) if path.suffix=='.md' else vault.metadata(self.c,rel)
            self.assertTrue(info['protected']);self.assertFalse(info['deletable']);self.assertFalse(info['editable'])
            self.assertEqual(self.post('/api/vault/trash',{'path':rel}).status_code,400)
            self.assertEqual(path.read_text(),'critical')

    def test_trash_symlink_cannot_redirect_backups(self):
        outside=Path(self.tmp.name)/'outside';outside.mkdir()
        (self.vault/'.trash').symlink_to(outside,target_is_directory=True)
        (self.vault/'note.md').write_text('safe')
        self.assertEqual(self.post('/api/vault/trash',{'path':'note.md'}).status_code,400)
        self.assertEqual(list(outside.iterdir()),[])

    def test_editor_roundtrip_preserves_authored_identity_extensions_and_other_profile(self):
        path=self.c.home/cc.CONFIG_NAME;raw=json.loads(path.read_text());raw['future_extension']={'enabled':True};path.write_text(json.dumps(raw))
        d=self.get('/api/profile/editor').json();d['config']['agent']='Nova renamed';d['display_name']='Nova at home';d['soul']+='\nAn authored detail.\n'
        other=(self.other.home/cc.CONFIG_NAME).read_bytes()
        r=self.post('/api/profile/editor',d);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(cc.load(self.c.home).agent,'Nova renamed');self.assertTrue(self.c.soul.read_text().endswith('An authored detail.\n'))
        self.assertEqual(json.loads(path.read_text())['future_extension'],{'enabled':True})
        self.assertEqual((self.other.home/cc.CONFIG_NAME).read_bytes(),other)
        self.assertEqual(self.post('/api/profile/editor',d).status_code,409)
        latest=self.get('/api/profile/editor').json();latest['config']['vault']='/tmp/elsewhere'
        self.assertEqual(self.post('/api/profile/editor',latest).status_code,400)

    def test_four_voice_adapters_are_written_into_hermes_config(self):
        source=self.root/'hermes-agent/tools/tts_command_provider.py';source.parent.mkdir(parents=True);source.write_text('# supported')
        for provider in speech.LOCAL:
            controls={k:v['default'] for k,v in speech.FIELDS[provider].items()}
            response=self.post('/api/voice',{'provider':provider,'voice':'sample','controls':controls})
            row=self.wait(response);self.assertEqual(row['status'],'complete',row)
            import yaml
            cfg=yaml.safe_load((self.c.home/'config.yaml').read_text())
            self.assertEqual(cfg['tts']['provider'],provider)
            adapter=cfg['tts']['providers'][provider]
            self.assertTrue(adapter['voice_compatible']);self.assertEqual(adapter['type'],'command');self.assertIn('{input_path}',adapter['command']);self.assertIn(str(self.c.home),adapter['command'])
            self.assertEqual(cfg['tts'][provider]['voice'],'sample')
        self.assertFalse((self.other.home/'config.yaml').exists())
        self.assertEqual(self.post('/api/voice',{'provider':'chatterbox','controls':{'exaggeration':99}}).status_code,400)
        self.assertEqual(self.post('/api/voice',{'provider':'chatterbox','controls':{'not_real':1}}).status_code,400)

    def test_image_identity_workflow_roundtrip_and_category_routing(self):
        p=media.template();p['workflow']['1']['inputs']['ckpt_name']='plantmilk.safetensors'
        p['parts']['quality']='anime';p['parts']['wardrobe']='blue coat';p['seed']=123
        other=json.loads(json.dumps(p));other.update(id='landscape',name='Comfy – Landscapes',category='landscape');other['parts']['identity']=''
        settings={'version':1,'identity_override':'red hair, green eyes','presets':[p,other],'routes':{'anime':p['id'],'landscape':'landscape'},'default_preset':p['id'],'inherit':False}
        r=self.post('/api/images',{'settings':settings,'revision':media.revision(self.c)});self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(portrait.identity_block(self.c),'red hair, green eyes')
        compiled=media.compile(self.c,category='anime',overrides={'scene':'reading by a window'})
        self.assertEqual(compiled['workflow']['4']['inputs']['text'],compiled['prompt'])
        self.assertIn('red hair, green eyes',compiled['prompt']);self.assertIn('reading by a window',compiled['prompt'])
        self.assertEqual(compiled['workflow']['9']['inputs']['seed'],123)
        self.assertEqual(media.compile(self.c,category='landscape',overrides={'scene':'mountains'})['preset']['id'],'landscape')
        self.assertEqual(media.load(self.other)['presets'],[])
        self.assertEqual(self.post('/api/images',{'settings':settings,'revision':''}).status_code,409)
        saved=media.load(self.c);self.assertEqual(saved['presets'][0]['workflow']['4']['inputs']['text'],'')
        bad=json.loads(json.dumps(settings));bad['presets'][0]['mappings']['prompt']=['missing','text']
        self.assertEqual(self.post('/api/images',{'settings':bad,'revision':media.revision(self.c)}).status_code,400)

    def test_comfy_sends_mapped_prompt_and_saves_validated_image(self):
        import companion_media_review as review
        review.save_preferences(self.c,{'review_before_delivery':False})
        from PIL import Image
        p=media.template();p['seed']=321
        media.save(self.c,{'version':1,'identity_override':'Nova','presets':[p],'routes':{},'default_preset':p['id'],'inherit':False},media.revision(self.c))
        calls=[]
        def request(url,payload=None,headers=None):
            calls.append((url,payload))
            if url.endswith('/object_info'):return {n['class_type']:{'input':{'required':{}}} for n in p['workflow'].values()}
            if url.endswith('/prompt'):return {'prompt_id':'abc'}
            return {'abc':{'status':{'status_str':'success'},'outputs':{'11':{'images':[{'filename':'real.png','subfolder':'','type':'output'}]}}}}
        data=io.BytesIO();Image.new('RGB',(8,8),'blue').save(data,format='PNG')
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.read.return_value=data.getvalue()
        with patch.object(media,'request_json',side_effect=request),patch.object(media.urllib.request,'urlopen',return_value=response):
            result=media.generate(self.c,overrides={'scene':'in a garden'})
        self.assertEqual(Path(result['path']).read_bytes(),data.getvalue())
        sent=next(body for url,body in calls if url.endswith('/prompt'))
        self.assertIn('in a garden',sent['prompt']['4']['inputs']['text'])
        self.assertEqual(sent['prompt']['9']['inputs']['seed'],321)
        review.save_preferences(self.c,{'review_before_delivery':True})
        with patch.object(media,'request_json',side_effect=request),patch.object(media.urllib.request,'urlopen',return_value=response):
            with patch.object(media,'hermes_bridge',return_value={'matches_request':True,'nsfw':True,'reason':'Unintended nudity'}):
                with self.assertRaisesRegex(ValueError,'held'):media.generate(self.c,overrides={'scene':'casual garden photo'})
            with patch.object(media,'hermes_bridge',side_effect=ValueError('offline')):
                with self.assertRaisesRegex(ValueError,'review is unavailable'):media.generate(self.c,overrides={'scene':'casual garden photo'})
        self.assertEqual(len(list((self.c.data/'creations/image-studio').glob('*.png'))),4)


    def test_saved_portrait_is_not_sent_to_hermes(self):
        ref=portrait.portrait_path(self.c);ref.parent.mkdir(parents=True,exist_ok=True);ref.write_bytes(b'saved reference')
        preset={'id':'chatgpt','name':'ChatGPT','provider':'hermes','category':'portrait','parts':{}}
        data={'version':1,'presets':[preset],'routes':{},'default_preset':'chatgpt'}
        media.save(self.c,data,media.revision(self.c))
        with patch.object(media,'hermes_bridge',return_value={'success':False,'error':'test stop'}) as bridge:
            with self.assertRaisesRegex(ValueError,'test stop'):
                media.generate(self.c,overrides={'scene':'walking in the garden'})
        payload=bridge.call_args.args[2]
        self.assertIsNone(payload['image_url'])
        self.assertIn('walking in the garden',payload['prompt'])
        self.assertTrue(ref.is_file())

    def test_image_inheritance_keeps_companions_own_identity(self):
        root=cc.load(self.root);preset=media.template();preset['parts']['identity']='Parent-specific tags'
        parent={'version':1,'identity_override':'Parent face','presets':[preset],'routes':{},'default_preset':preset['id'],'inherit':False}
        media.save(root,parent,media.revision(root))
        child={'version':1,'identity_override':'Child face','presets':[],'routes':{},'default_preset':'','inherit':True}
        media.save(self.c,child,media.revision(self.c))
        result=media.compile(self.c,overrides={'scene':'reading'})
        self.assertIn('Child face',result['prompt']);self.assertNotIn('Parent',result['prompt'])
        self.assertEqual(media.load(root)['presets'][0]['parts']['identity'],'Parent-specific tags')

    def test_dashboard_proxy_requires_workspace_auth(self):
        r=self.client.get('/api/hermes/existing/api/config');self.assertEqual(r.status_code,401)
        r=self.client.get('/api/hermes/existing/api/config',headers=self.headers);self.assertEqual(r.status_code,503)

if __name__=='__main__':unittest.main()
