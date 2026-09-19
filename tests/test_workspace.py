"""Workspace contracts: isolation, credentials, notes, jobs and recoverable actions."""
import concurrent.futures
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'kit/scripts')]
from fastapi.testclient import TestClient
import companion_config as cc
import companion_render as cr
from kit.app.server import build
from kit.app.runtime import Operations, Runtime, messages, sessions

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'hermes';self.vault=Path(self.tmp.name)/'vault'
        self.root.mkdir();self.vault.mkdir()
        self.c=cc.Companion(agent='Nova',human='Alex',profile='nova',hermes_root=self.root,vault=self.vault,soul_in_vault=False,context_mode='fixed')
        self.c.home.mkdir(parents=True);self.c.life.mkdir(parents=True)
        self.c.save();self.c.soul.write_text(cr.render_template('SOUL.md.tmpl',cr.mapping_for(self.c,'warm','none')))
        self.other=cc.Companion(agent='Rowan',profile='rowan',hermes_root=self.root,vault=self.vault,context_mode='fixed')
        self.other.home.mkdir(parents=True);self.other.save()
        self.app=build(self.root,token='workspace-token',state_dir=Path(self.tmp.name)/'state')
        self.client=TestClient(self.app)
        self.headers={'x-companion-token':'workspace-token'}
        self.fake=patch.dict(os.environ,{'COMPANION_HERMES_COMMAND':json.dumps([sys.executable,str(ROOT/'tests/fake_hermes.py')])})
        self.fake.start();self.addCleanup(self.fake.stop)

    def get(self,path,profile='nova'):
        return self.client.get(path,params={'profile':profile},headers=self.headers)
    def post(self,path,data=None,profile='nova'):
        return self.client.post(path,params={'profile':profile},headers=self.headers,json=data or {})
    def wait(self,response,profile='nova'):
        self.assertEqual(response.status_code,200,response.text)
        ident=response.json()['id']
        for _ in range(1000):
            row=self.get('/api/operations/'+ident,profile).json()
            if row['status']!='running':return row
            time.sleep(.01)
        self.fail('Operation did not finish')

    def test_named_provider_refresh_keeps_hermes_reported_catalog(self):
        (self.c.home/'provider_models_cache.json').write_text(json.dumps({'openai-codex':{'models':['fixture-model']}}))
        row=self.client.get('/api/models/catalog',params={'profile':'nova','provider':'openai-codex','refresh':1},headers=self.headers).json()
        self.assertEqual(row['models'],['fixture-model'])
        self.assertEqual(row['source'],'cache')

    def test_full_soul_conflict_backup_and_repair(self):
        self.c.soul.write_text('# Nova\nOriginal custom personality.\n')
        doc=self.get('/api/soul-document').json()
        self.assertEqual(self.post('/api/identity-repair',{'appearance':'Adult with dark curly hair.'}).status_code,200)
        body=self.c.soul.read_text()
        self.assertTrue(body.startswith(doc['text']))
        import companion_portrait as portrait
        self.assertEqual(portrait.identity_block(self.c),'Adult with dark curly hair.')
        self.assertEqual(self.post('/api/soul-document',{**doc,'text':'stale'}).status_code,409)
        current=self.get('/api/soul-document').json()
        self.assertEqual(self.post('/api/soul-document',{**current,'text':body+'\nNew detail.'}).status_code,200)
        self.assertTrue(list(self.c.soul_backups.iterdir()))

    def test_document_paths_and_voice_reference(self):
        (self.c.home/'AGENTS.md').write_text('Original instructions')
        self.assertIn('AGENTS.md',self.get('/api/documents').json()['documents'])
        self.assertEqual(self.client.get('/api/soul-document',params={'profile':'nova','document':'../outside.md'},headers=self.headers).status_code,404)
        import io,wave
        data=io.BytesIO()
        with wave.open(data,'wb') as clip:
            clip.setnchannels(1);clip.setsampwidth(2);clip.setframerate(16000);clip.writeframes(bytes(32000))
        url='/api/voice/reference?profile=nova'
        headers={**self.headers,'content-type':'application/octet-stream'}
        response=self.client.post(url,headers=headers,content=data.getvalue())
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((self.c.data/'voice/reference.wav').read_bytes(),data.getvalue())
        self.assertEqual(self.client.post(url,headers=headers,content=b'not audio').status_code,400)

    def test_voice_settings_preserve_other_configuration(self):
        from kit.app.manage import config
        row=self.wait(self.post('/api/voice',{'provider':'xai','voice':'eve','speed':1.2}))
        self.assertEqual(row['status'],'complete')
        self.assertEqual(config(self.c.home)['tts']['xai']['voice_id'],'eve')
        self.assertEqual(self.post('/api/voice',{'provider':'bad'}).status_code,400)
        self.assertEqual(self.post('/api/voice',{'provider':'edge','speed':99}).status_code,400)

    def test_display_name_keeps_identity_and_profiles_intact(self):
        before=(self.c.home/cc.CONFIG_NAME).read_bytes()
        row=self.wait(self.post('/api/profile/display-name',{'name':'Evening companion'}))
        self.assertEqual(row['status'],'complete')
        profiles=self.get('/api/profiles').json()['profiles']
        self.assertEqual(next(p['name'] for p in profiles if p['id']=='nova'),'Evening companion')
        self.assertEqual((self.c.home/cc.CONFIG_NAME).read_bytes(),before)
        self.assertEqual(cc.load(self.other.home).agent,'Rowan')
        self.assertEqual(self.post('/api/profile/display-name',{'name':'  '}).status_code,400)
        (self.root/'config.yaml').write_text('{}')
        self.assertEqual(self.wait(self.post('/api/profile/display-name',{'name':'Hermes at home'},'default'),'default')['status'],'complete')
        profiles=self.get('/api/profiles','default').json()['profiles']
        self.assertEqual(next(p['name'] for p in profiles if p['id']=='default'),'Hermes at home')

    def test_hosted_origin_still_requires_token(self):
        with patch.dict(os.environ,{'COMPANION_PUBLIC_ORIGIN':'https://companion.example.com'}):
            app=build(self.root,token='secret',state_dir=Path(self.tmp.name)/'hosted')
        client=TestClient(app)
        path='/api/settings?profile=nova'
        self.assertEqual(client.post(path,headers={'origin':'https://companion.example.com'},json={}).status_code,401)
        headers={'origin':'https://companion.example.com','x-companion-token':'secret'}
        self.assertEqual(client.post(path,headers=headers,json={'location':'home'}).status_code,200)
        headers['origin']='https://untrusted.example'
        self.assertEqual(client.post(path,headers=headers,json={}).status_code,403)

    def test_activity_is_profile_scoped(self):
        cron=self.c.home/'cron';cron.mkdir()
        (cron/'jobs.json').write_text(json.dumps({'jobs':[{'id':'job','name':'Nova journal','last_status':'error','enabled':True}]}))
        self.assertTrue(any(r['title']=='Nova journal' for r in self.get('/api/activity').json()['events']))
        self.assertFalse(any(r['title']=='Nova journal' for r in self.get('/api/activity','rowan').json()['events']))

    def test_chat_media_only_resolves_own_visible_vault_files(self):
        self.c.data.mkdir(parents=True,exist_ok=True)
        own=self.c.data/'shared.png';own.write_bytes(b'image')
        self.other.data.mkdir(parents=True,exist_ok=True)
        foreign=self.other.data/'private.png';foreign.write_bytes(b'image')
        content=f'![Own]({own}) ![Foreign]({foreign}) ![Remote](https://example.com/track.png)'
        with sqlite3.connect(self.c.home/'state.db') as con:
            con.executescript('CREATE TABLE sessions(id TEXT,source TEXT,started_at REAL); CREATE TABLE messages(session_id TEXT,role TEXT,content TEXT,timestamp REAL);')
            con.execute('INSERT INTO sessions VALUES (?,?,?)',('own','cli',1))
            con.execute('INSERT INTO messages VALUES (?,?,?,?)',('own','assistant',content,1))
        response=self.get('/api/sessions/own')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual([a['path'] for a in response.json()['messages'][0]['attachments']],['shared.png'])

    def test_old_chat_media_resolves_album_copies_before_catalog_paging(self):
        import companion_media_review as review
        for i in range(1501):
            image=self.c.data/f'new-{i}.png';image.write_bytes(str(i).encode());os.utime(image,(200,200))
        original=self.c.data/'old.png';original.write_bytes(b'old image');os.utime(original,(1,1))
        album=self.c.data/'albums/Favorites';album.mkdir(parents=True)
        copy=album/'kept.png';copy.write_bytes(original.read_bytes());os.utime(copy,(1,1))
        review.write_metadata(original,{'rating':'nsfw'});review.write_metadata(copy,{'rating':'safe'})
        with contextlib.closing(sqlite3.connect(self.c.home/'state.db')) as con,con:
            con.executescript('CREATE TABLE sessions(id TEXT,source TEXT,started_at REAL); CREATE TABLE messages(session_id TEXT,role TEXT,content TEXT,timestamp REAL);')
            con.execute('INSERT INTO sessions VALUES (?,?,?)',('old-media','cli',1))
            con.execute('INSERT INTO messages VALUES (?,?,?,?)',('old-media','assistant','![kept](albums/Favorites/kept.png)',1))
            con.execute('INSERT INTO sessions VALUES (?,?,?)',('plain','cli',2))
            con.execute('INSERT INTO messages VALUES (?,?,?,?)',('plain','assistant','A text-only reply',2))
        response=self.get('/api/sessions/old-media')
        self.assertEqual(response.status_code,200,response.text)
        attachments=response.json()['messages'][0]['attachments']
        self.assertEqual(len(attachments),1);self.assertEqual(attachments[0]['path'],'albums/Favorites/kept.png')
        self.assertTrue(attachments[0]['blur']);self.assertEqual(attachments[0]['rating'],'nsfw')
        with patch('kit.app.content.catalog',side_effect=AssertionError('Text chat should not scan media')):
            self.assertEqual(self.get('/api/sessions/plain').status_code,200)

    def test_first_run_needs_no_companion_config(self):
        response=self.get('/api/profiles','default')
        self.assertEqual(response.status_code,200)
        self.assertEqual({r['id'] for r in response.json()['profiles']},{'nova','rowan'})
        self.assertEqual(self.get('/api/installations').status_code,200)
        self.assertEqual(self.get('/api/catalog').status_code,200)

    def test_parallel_requests_keep_their_profiles(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            rows=list(pool.map(lambda name:self.get('/api/overview',name).json()['agent'],['nova','rowan']*12))
        self.assertEqual(rows,['Nova','Rowan']*12)
        self.assertEqual(self.post('/api/settings',{'location':'Boston'},'rowan').status_code,200)
        self.assertEqual(cc.load(self.c.home).location,'')
        self.assertEqual(cc.load(self.other.home).location,'Boston')

    def test_profile_traversal_and_foreign_installations_refused(self):
        self.assertEqual(self.get('/api/overview','../../outside').status_code,400)
        response=self.client.get('/api/profiles?installation=unknown',headers=self.headers)
        self.assertEqual(response.status_code,400)

    def test_cross_origin_writes_and_private_media(self):
        response=self.client.post('/api/settings?profile=nova',json={'location':'x'},headers={**self.headers,'origin':'https://other.test'})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.client.get('/media/portrait?profile=nova').status_code,401)
        self.assertEqual(self.client.get('/media/timeline/missing.png').status_code,401)
        self.assertEqual(self.get('/api/overview').headers['cache-control'],'no-store')

    def test_model_configuration_preserves_unrelated_keys_and_hides_secrets(self):
        before={'model':{'default':'old','provider':'openrouter','api_key':'private-inline','context_length':32768},'unrelated':{'keep':True},'hooks':{'x':'echo hello'}}
        (self.c.home/'config.yaml').write_text(yaml.safe_dump(before))
        response=self.post('/api/environment',{'model':{'model':'new','provider':'openrouter'},'fallbacks':[{'provider':'anthropic','model':'backup'}]})
        self.assertEqual(response.status_code,200,response.text)
        after=yaml.safe_load((self.c.home/'config.yaml').read_text())
        self.assertEqual(after['unrelated'],before['unrelated'])
        self.assertEqual(after['model']['context_length'],32768)
        self.assertEqual(after['hooks'],before['hooks'])
        self.assertNotIn('private-inline',self.get('/api/environment').text)
        self.assertTrue(list((self.c.home/'companion-config-backups').iterdir()))

    def test_invalid_model_config_does_not_write(self):
        for payload in ({'model':{'provider':'x'}},{'model':{'model':'x','base_url':'file:///etc/passwd'}},{'fallbacks':[{}]*9},{'secret':'oops'}):
            self.assertEqual(self.post('/api/environment',payload).status_code,400)
        self.assertFalse((self.c.home/'config.yaml').exists())

    def test_credentials_are_write_only_and_preserve_other_values(self):
        (self.c.home/'.env').write_text('KEEP=value\nOPENROUTER_API_KEY=old\n')
        with patch.object(Runtime,'catalog',return_value=[]):
            response=self.post('/api/credentials',{'name':'OPENROUTER_API_KEY','value':'a-private-key'})
            self.assertEqual(response.status_code,200,response.text)
            self.assertNotIn('a-private-key',self.get('/api/providers').text)
        self.assertIn('KEEP=value',(self.c.home/'.env').read_text())
        self.assertEqual(self.post('/api/credentials',{'name':'PATH','value':'/bad'}).status_code,400)
        if os.name!='nt':self.assertEqual((self.c.home/'.env').stat().st_mode&0o777,0o600)

    def test_vault_boundaries_and_note_conflicts(self):
        (self.vault/'notes').mkdir();note=self.vault/'notes/hello.md';note.write_text('# Hello\n')
        response=self.client.get('/api/vault/file?profile=nova&path=notes/hello.md',headers=self.headers)
        body=response.json();self.assertTrue(body['editable'])
        note.write_text('Changed elsewhere')
        write=self.client.put('/api/vault/file?profile=nova',headers=self.headers,json={**body,'text':'overwrite'})
        self.assertEqual(write.status_code,409)
        self.assertEqual(note.read_text(),'Changed elsewhere')
        for path in ('../outside.md','/etc/passwd','.git/config','notes/.env','notes/../../other'):
            r=self.client.get('/api/vault/file',params={'profile':'nova','path':path},headers=self.headers)
            self.assertEqual(r.status_code,400,path)
        r=self.client.put('/api/vault/file?profile=nova',headers=self.headers,json={'path':'notes/new.md','revision':'','text':'# New'})
        self.assertEqual(r.status_code,200,r.text)
        r=self.client.put('/api/vault/file?profile=nova',headers=self.headers,json={'path':'soul/SOUL.md','revision':'','text':'bad'})
        self.assertEqual(r.status_code,400)

    def test_symlink_cannot_escape_vault(self):
        outside=Path(self.tmp.name)/'outside.md';outside.write_text('not in vault')
        try:(self.vault/'escape.md').symlink_to(outside)
        except OSError:self.skipTest('Symlinks unavailable')
        r=self.client.get('/api/vault/file?profile=nova&path=escape.md',headers=self.headers)
        self.assertEqual(r.status_code,400)

    def test_relationship_settings_and_milestones(self):
        # Relationship progression and pace can be updated via /api/settings
        response=self.post('/api/settings',{'relationship_progression':'milestones'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(cc.load(self.c.home).relationship_progression,'milestones')
        # Non-locked settings like peer_interaction succeed
        self.assertEqual(self.post('/api/settings',{'peer_interaction':False}).status_code,200)
        self.assertEqual(self.post('/api/relationship',{'moment':'ritual','text':'Sunday tea'}).status_code,200)
        result=self.get('/api/relationship').json()
        self.assertEqual(sum(m['earned'] for m in result['milestones']),1)
        self.assertIn('intimacy',result)
        ident=result['moments'][0]['id']
        self.assertEqual(self.post('/api/relationship/'+ident+'/retire').status_code,200)
        self.assertEqual(self.get('/api/relationship').json()['moments'][0]['status'],'retired')

    def test_bars_default_on_and_explicit_opt_out_is_preserved(self):
        self.assertTrue(cc.Companion().bars)
        self.assertIsNotNone(self.get('/api/relationship').json()['bars'])
        self.assertEqual(self.post('/api/settings',{'bars':False}).status_code,200)
        self.assertFalse(cc.load(self.c.home).bars)
        self.assertIsNone(self.get('/api/relationship').json()['bars'])
        self.assertEqual(self.post('/api/settings',{'bars':True}).status_code,200)
        self.assertIsNotNone(self.get('/api/relationship').json()['bars'])

    def test_hook_approval_requires_exact_current_review(self):
        digest=self.get('/api/hooks').json()['digest']
        (self.c.home/'config.yaml').write_text('hooks:\n  changed: echo changed\n')
        self.assertEqual(self.post('/api/hooks/approve',{'digest':digest}).status_code,400)

    def test_operations_persist_failure_and_recover_interrupted_status(self):
        ops=Operations(Path(self.tmp.name)/'operations')
        row=ops.submit('scope','Example',lambda report:(_ for _ in ()).throw(ValueError('expected failure')))
        for _ in range(100):
            if ops.get(row['id'])['status']!='running':break
            time.sleep(.01)
        self.assertEqual(ops.get(row['id'])['status'],'failed')
        persisted=Operations(ops.directory)
        self.assertEqual(persisted.get(row['id'])['error'],'expected failure')
        path=ops.directory/(row['id']+'.json');data=json.loads(path.read_text());data['status']='running';path.write_text(json.dumps(data))
        self.assertEqual(persisted.get(row['id'])['status'],'interrupted')

    def test_create_then_archive_restore_preserves_vault(self):
        created=self.wait(self.post('/api/profiles',{'profile':'mira','answers':{'agent':'Mira','human_names':'Alex','boundary':'best-friend','vault':str(self.vault),'visual':'none'}}))
        self.assertEqual(created['status'],'complete',created)
        home=self.root/'profiles/mira'
        self.assertTrue((home/'companion.json').exists())
        self.assertTrue((home/'cron/jobs.json').exists())
        before=(self.vault/'agents/mira/soul/SOUL.md').read_bytes()
        archived=self.wait(self.post('/api/profile/archive',{'confirm':'mira'},'mira'),'mira')
        self.assertEqual(archived['status'],'complete',archived)
        name=next((self.root/'profiles-removed').iterdir()).name
        restored=self.wait(self.post('/api/profile/restore',{'archive':name,'profile':'mira'}))
        self.assertEqual(restored['status'],'complete',restored)
        self.assertTrue(home.exists())
        self.assertEqual((self.vault/'agents/mira/soul/SOUL.md').read_bytes(),before)

    def test_create_accepts_the_full_payload_the_web_wizard_sends(self):
        """The browser wizard submits every answer it collected, not a minimal
        subset. An answer key the CLI does not know is rejected outright, so a
        creation path that works only for a trimmed payload works for nobody."""
        answers={'agent':'Ash','human_names':'Alex','pronoun_set':'she','human_pronoun_set':'he',
                 'timezone':'UTC','age':29,'persona':'steady','agent_type':'companion',
                 'boundary':'best-friend','relationship_pace':'natural',
                 'outreach':'updates_only','outreach_per_day':3,
                 'quiet_start':'23:00','quiet_end':'08:00',
                 'permit_image':'ask','permit_voice':'ask',
                 'share_people':'no','visual':'none','image_style':'none',
                 'human_boundary':'Give me space when I am busy.',
                 'vault':str(self.vault)}
        created=self.wait(self.post('/api/profiles',{'profile':'ash','answers':answers}))
        self.assertEqual(created['status'],'complete',created)
        saved=json.loads((self.root/'profiles/ash/companion.json').read_text())
        self.assertEqual(saved['persona'],'steady')
        self.assertEqual(saved['boundary'],'best-friend')
        self.assertEqual(saved['relationship_pace'],'natural')
        # A non-romantic frame must never be recorded as permitting adult themes.
        self.assertFalse(saved['explicit'])

    def test_create_rejects_an_unknown_answer_key(self):
        bad=self.post('/api/profiles',{'profile':'nope','answers':{'agent':'X','boundary':'best-friend','explicit':True}})
        self.assertEqual(bad.status_code,400)
        self.assertIn('Unknown setup answers',bad.json()['detail'])

    def test_appearance_round_trips_and_validates(self):
        d=self.get('/api/appearance').json()
        self.assertEqual(d['appearance']['theme'],'midnight')
        self.assertIn('daylight',d['themes']['light'])
        saved=self.post('/api/appearance',{'theme':'nord','accent':'#FF8800',
                                           'nav_pins':['chat','photos'],'follow_system':True}).json()
        self.assertEqual(saved['appearance']['theme'],'nord')
        self.assertEqual(saved['appearance']['accent'],'#ff8800')
        self.assertEqual(saved['appearance']['nav_pins'],['chat','photos'])
        self.assertTrue(self.get('/api/appearance').json()['appearance']['follow_system'])
        # A partial update must not discard the rest of the record.
        self.post('/api/appearance',{'accent':''})
        again=self.get('/api/appearance').json()['appearance']
        self.assertEqual(again['theme'],'nord')
        self.assertEqual(again['accent'],'')

    def test_appearance_rejects_bad_values(self):
        for payload,fragment in (({'theme':'chartreuse'},'Unknown theme'),
                                 ({'light_theme':'nord'},'light theme'),
                                 ({'dark_theme':'daylight'},'dark theme'),
                                 ({'accent':'red'},'rrggbb'),
                                 ({'nav_pins':['chat','not-a-page']},'Cannot pin'),
                                 ({'nav_pins':[]},'between 1 and 4'),
                                 ({'nav_pins':['now','chat','photos','journals','vault']},'between 1 and 4')):
            r=self.post('/api/appearance',payload)
            self.assertEqual(r.status_code,400,payload)
            self.assertIn(fragment,r.json()['detail'],payload)

    def test_every_navigable_destination_can_be_pinned(self):
        """The More page shows a pin control beside each destination. If the
        server's allowlist and the client's navigation map drift apart, those
        controls fail on click instead of at review time."""
        import re
        root=Path(__file__).resolve().parents[1]
        block=re.search(r'const navGroups=\[(.*?)\n\];',
                        (root/'kit/app/static/product.js').read_text(),re.S).group(1)
        destinations=[]
        for line in block.strip().split('\n'):
            ids=re.search(r'\[([^\[\]]*)\]\s*\]',line)
            if ids: destinations+=re.findall(r"'([a-z0-9-]+)'",ids.group(1))
        self.assertTrue(destinations)
        allowed=self.get('/api/appearance').json()['pinnable']
        self.assertEqual(sorted(set(destinations)-set(allowed)),[])
        for name in destinations[:4]:
            r=self.post('/api/appearance',{'nav_pins':[name]})
            self.assertEqual(r.status_code,200,f'{name}: {r.text}')

    def test_appearance_is_per_profile(self):
        self.post('/api/appearance',{'theme':'ocean'},'nova')
        self.post('/api/appearance',{'theme':'ember'},'rowan')
        self.assertEqual(self.get('/api/appearance','nova').json()['appearance']['theme'],'ocean')
        self.assertEqual(self.get('/api/appearance','rowan').json()['appearance']['theme'],'ember')

    def test_calendar_ics_export(self):
        self.post('/api/missions',{'title':'Dinner with Alex','detail':'Table for two','wanted_by':'2026-09-20'})
        res=self.get('/api/calendar.ics')
        self.assertEqual(res.status_code,200)
        self.assertIn('text/calendar',res.headers.get('content-type',''))
        self.assertIn('BEGIN:VCALENDAR',res.text)
        self.assertIn('SUMMARY:Dinner with Alex',res.text)
        self.assertIn('DTSTART;VALUE=DATE:20260920',res.text)
        self.assertIn('END:VCALENDAR',res.text)

    def test_shared_session_database_never_returns_another_profile(self):
        db=self.root/'state.db'
        with contextlib.closing(sqlite3.connect(db)) as con:
            con.executescript('CREATE TABLE sessions(id TEXT,source TEXT,started_at REAL,profile_name TEXT); CREATE TABLE messages(session_id TEXT,role TEXT,content TEXT,timestamp REAL);')
            con.executemany('INSERT INTO sessions VALUES (?,?,?,?)',[('n','telegram',1,'nova'),('r','cli',2,'rowan'),('d','cli',3,'')])
            con.executemany('INSERT INTO messages VALUES (?,?,?,?)',[('n','user','Nova only',1),('r','user','Rowan only',2)])
            con.commit()
        try:(self.c.home/'state.db').symlink_to(db)
        except OSError:self.skipTest('Symlinks unavailable')
        self.assertEqual([r['id'] for r in sessions(self.c)],['n'])
        self.assertEqual(messages(self.c,'n')[0]['content'],'Nova only')
        with self.assertRaises(ValueError):messages(self.c,'r')
        self.assertEqual(self.get('/api/sessions/r').status_code,400)

    def test_undergarment_privacy_gating_in_overview_and_closet(self):
        import companion_presence as presence
        (self.c.life / 'wardrobe.json').write_text(json.dumps({'items': [
            {'id': 'top-1', 'description': 'cream knit sweater'},
            {'id': 'pants-1', 'description': 'dark blue denim jeans'},
            {'id': 'bra-sports', 'description': 'sage green low-cut ribbed active sports bra'},
            {'id': 'closet-underwear-1', 'description': 'sage green soft stretch-cotton bikini panties with subtle lace trim'}
        ]}))
        presence.update(self.c, {
            'previous_id': None,
            'outfit': ['top-1', 'pants-1', 'bra-sports', 'closet-underwear-1'],
            'location': 'the living room',
            'activity': 'reading',
            'mood': 'content',
            'text': 'Quiet afternoon reading.'
        })
        res = self.get('/api/overview').json()
        descriptions = [it.get('description', '') for it in res['state']['state']['outfit']]
        self.assertIn('cream knit sweater', descriptions)
        self.assertIn('dark blue denim jeans', descriptions)
        self.assertIn('sage green low-cut ribbed active sports bra', descriptions)
        self.assertNotIn('sage green soft stretch-cotton bikini panties with subtle lace trim', descriptions)
        self.assertIsNone(res.get('integrity_warning'))
        self.assertFalse(res.get('integrity_lockout'))

class ModelPinTests(unittest.TestCase):
    def test_apply_preserves_ids_and_history_and_skips_script_jobs(self):
        from kit.cli.models import apply_job_models
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            c=cc.Companion(hermes_root=Path(directory),models={'loops':{'model':'small','provider':'local','reasoning_effort':'low'}})
            (c.home/'cron').mkdir()
            original={'jobs':[{'id':'pulse','name':'Companion companion pulse','enabled':False,'history':['old']},
                              {'id':'script','name':'Companion health watch','no_agent':True}]}
            (c.home/'cron/jobs.json').write_text(json.dumps(original))
            calls=[]
            def run(args):calls.append(args);return SimpleNamespace(stdout='--model --provider --reasoning-effort')
            result=apply_job_models(c,run)
            self.assertEqual(result['updated'],['Companion companion pulse'])
            self.assertEqual(calls[1],['cron','edit','pulse','--model','small','--provider','local','--reasoning-effort','low'])
            self.assertEqual(json.loads((c.home/'cron/jobs.json').read_text()),original)

    def test_tier_endpoint_requires_hermes_support_and_reaches_job_edit(self):
        from kit.cli.models import apply_job_models
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            c=cc.Companion(hermes_root=Path(directory),models={'loops':{'model':'small','provider':'custom','base_url':'http://localhost:11434/v1'}})
            (c.home/'cron').mkdir()
            (c.home/'cron/jobs.json').write_text(json.dumps({'jobs':[{'id':'pulse','name':'Companion companion pulse'}]}))
            calls=[]
            def old(args):
                calls.append(args)
                return SimpleNamespace(stdout='--model --provider --reasoning-effort')
            with self.assertRaisesRegex(ValueError,'No jobs were changed'):apply_job_models(c,old)
            self.assertEqual(len(calls),1)
            calls.clear()
            def modern(args):
                calls.append(args)
                return SimpleNamespace(stdout='--model --provider --reasoning-effort --base-url')
            apply_job_models(c,modern)
            self.assertEqual(calls[1][-2:],['--base-url','http://localhost:11434/v1'])
            c.save()
            self.assertEqual(cc.load(c.home).tier_model('loops')['base_url'],'http://localhost:11434/v1')
            with self.assertRaises(ValueError):
                cc.Companion(models={'loops':{'base_url':'file:///tmp/model-endpoint'}})

    def test_native_prompt_whitespace_is_not_a_user_edit(self):
        from kit.cli import scaffold
        from kit.cli.common import load_manifest,mapping,T
        with tempfile.TemporaryDirectory() as directory:
            c=cc.Companion(hermes_root=Path(directory),vault=Path(directory)/'vault')
            (c.home/'cron').mkdir()
            spec=load_manifest(c)['jobs'][0];m=mapping(c,{})
            rendered=cr.render((T/'cron'/spec['file']).read_text(),m)
            name=cr.render(spec['name'],m)
            (c.home/'cron/jobs.json').write_text(json.dumps({'jobs':[{'id':'pulse','name':name,'prompt':rendered.strip()}]}))
            scaffold.record_fingerprint(c,name,rendered)
            report=[]
            with patch.object(scaffold,'_edit_prompt') as edit:
                scaffold.refresh_templates(c,m,report)
                edit.assert_not_called()
            self.assertFalse(any('edited' in line for line in report))

class InstallRecoveryTests(unittest.TestCase):
    def test_partial_runtime_is_retried_and_only_marked_complete_at_end(self):
        import io
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            runtime=Runtime(Path(directory),managed=True)
            binary=runtime.root/'hermes-agent/venv'/('Scripts/hermes.exe' if os.name=='nt' else 'bin/hermes')
            binary.parent.mkdir(parents=True);binary.touch()
            stages=(['uv','git','node','system-packages','repository','python','venv','dependencies','node-deps','config-templates','platform-sdks','bootstrap-marker'] if os.name=='nt' else ['prerequisites','repository','venv','python-deps','node-deps','config','complete'])
            manifest=json.dumps({'protocol_version':1,'stages':[{'name':s} for s in stages]})
            def run(args,**kwargs):
                if '--manifest' in args or '-Manifest' in args:return SimpleNamespace(returncode=0,stdout=manifest)
                self.assertFalse((runtime.root/'.companion-runtime.json').exists())
                return SimpleNamespace(returncode=0,stdout='',stderr='')
            with patch('kit.app.runtime.urllib.request.urlopen',return_value=io.BytesIO(b'official script')),patch('kit.app.runtime.subprocess.run',side_effect=run) as proc:
                result=runtime.install(lambda _:None)
                self.assertTrue(result['installed']);self.assertEqual(proc.call_count,len(stages)+1)
                self.assertTrue(runtime.install(lambda _:None)['already_installed'])
                self.assertEqual(proc.call_count,len(stages)+1)

    def test_changed_installer_protocol_runs_no_stages(self):
        import io
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            with patch('kit.app.runtime.urllib.request.urlopen',return_value=io.BytesIO(b'official script')),patch('kit.app.runtime.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='{"protocol_version":2,"stages":[]}')) as proc:
                with self.assertRaisesRegex(ValueError,'interface changed'):Runtime(directory,managed=True).install(lambda _:None)
                self.assertEqual(proc.call_count,1)
                self.assertFalse((Path(directory)/'.companion-runtime.json').exists())

    def test_token_counts_visible_but_credentials_redacted(self):
        from kit.app.manage import public_config,sensitive_key
        result=public_config({'max_tokens':1000,'access_token':'private','nested':{'api_key':'private','output_tokens':200}})
        self.assertEqual(result['max_tokens'],1000)
        self.assertEqual(result['nested']['output_tokens'],200)
        self.assertNotIn('private',json.dumps(result))
        self.assertFalse(sensitive_key('model.max_tokens'))
        self.assertTrue(sensitive_key('model.api_key'))

if __name__=='__main__':unittest.main()
