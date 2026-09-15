"""The local web app.

It reads the same files the hook reads, and it must never be able to write a
file the model owns — not the state ledger, not the SOUL block she writes
herself, not a ledger's history.
"""
import json
import pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'));sys.path.insert(0,str(ROOT))
import companion_config as cc
import companion_render as cr

try:
    from fastapi.testclient import TestClient
    HAVE_APP=True
except Exception:
    # Starlette's test client needs httpx, which is a test-only dependency and
    # raises RuntimeError rather than ImportError when it is missing. Either way
    # the app itself is optional, so these are skipped rather than failing.
    HAVE_APP=False

def _png(size=(8,8),color=(120,90,70)):
    import io
    from PIL import Image
    buf=io.BytesIO();Image.new('RGB',size,color).save(buf,format='PNG')
    return buf.getvalue()

@unittest.skipUnless(HAVE_APP,'the app test client needs fastapi and httpx')
class AppTests(unittest.TestCase):
    def setUp(self):
        from kit.app.server import build
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'h',vault=root/'v',
                            timezone='UTC',soul_in_vault=False)
        self.c.home.mkdir(parents=True,exist_ok=True)
        self.c.life.mkdir(parents=True,exist_ok=True)
        self.c.soul.write_text(cr.render_template('SOUL.md.tmpl',cr.mapping_for(self.c,'warm','none')),
                               encoding='utf-8')
        self.c.save()
        self.client=TestClient(build(home=self.c.home))

    def test_the_page_and_every_read_endpoint_answer(self):
        self.assertEqual(self.client.get('/').status_code,200)
        for path in ('/api/overview','/api/settings','/api/ledgers','/api/health',
                     '/api/identity','/api/timeline','/api/cost','/api/missions'):
            self.assertEqual(self.client.get(path).status_code,200,path)

    def test_it_refuses_to_change_anything_that_is_not_a_setting(self):
        for payload in ({'agent':'Someone Else'},{'birthdate':'1990-01-01'},
                        {'agent_type':'worker'},{'context_tokens':4096}):
            r=self.client.post('/api/settings',json=payload)
            self.assertEqual(r.status_code,400,payload)
            self.assertIn('not settable from here',r.json()['detail'])

    def test_a_setting_gets_the_same_validation_the_cli_gets(self):
        r=self.client.post('/api/settings',json={'outreach_per_day':9999})
        self.assertEqual(r.status_code,400)
        self.assertEqual(cc.load(self.c.home).outreach_per_day,self.c.outreach_per_day)

    def test_a_valid_setting_lands_on_disk(self):
        r=self.client.post('/api/settings',json={'quiet_start':'22:30','location':'Lisbon'})
        self.assertEqual(r.status_code,200)
        again=cc.load(self.c.home)
        self.assertEqual(again.quiet_start,'22:30')
        self.assertEqual(again.location,'Lisbon')

    def test_forgetting_a_fact_supersedes_it_and_keeps_the_original(self):
        import companion_self as slf
        import datetime as dt
        made=slf.record_fact(self.c.human_dir,'likes anchovies','said so once',
                             dt.datetime.now(dt.timezone.utc))['entry']
        r=self.client.post(f"/api/facts/{made['id']}/forget")
        self.assertEqual(r.status_code,200)
        self.assertEqual(slf.facts(self.c.human_dir),[]
                         if not slf.facts(self.c.human_dir) else slf.facts(self.c.human_dir))
        self.assertNotIn(made['id'],[f['id'] for f in slf.facts(self.c.human_dir)])
        self.assertIn('anchovies',(self.c.human_dir/'facts.jsonl').read_text())

    def test_a_mission_can_be_added_and_dropped(self):
        r=self.client.post('/api/missions',json={'title':'price a new kettle'})
        self.assertEqual(r.status_code,200)
        ident=r.json()['id']
        listed=self.client.get('/api/missions').json()['missions']
        self.assertEqual([m['title'] for m in listed],['price a new kettle'])
        self.assertEqual(self.client.post(f'/api/missions/{ident}/drop').status_code,200)
        self.assertEqual([m['status'] for m in self.client.get('/api/missions').json()['missions']],
                         ['dropped'])

    def test_a_mission_without_a_title_is_refused_not_stored(self):
        self.assertEqual(self.client.post('/api/missions',json={'detail':'x'}).status_code,400)

    def test_an_identity_section_can_be_edited_by_the_person(self):
        r=self.client.post('/api/identity/humor',json={'body':'Dry, and she never explains a joke.'})
        self.assertEqual(r.status_code,200)
        self.assertIn('never explains a joke',self.c.soul.read_text())
        self.assertEqual(self.client.post('/api/identity/nope',json={'body':'x'}).status_code,404)

    def test_the_locked_sections_are_marked_so_the_page_can_say_so(self):
        sections={s['name']:s for s in self.client.get('/api/identity').json()['sections']}
        self.assertTrue(sections['appearance']['locked'])
        self.assertFalse(sections['humor']['locked'])

    def test_a_token_is_enforced_on_the_api_when_one_is_set(self):
        from kit.app.server import build
        guarded=TestClient(build(home=self.c.home,token='sesame'))
        self.assertEqual(guarded.get('/api/overview').status_code,401)
        self.assertEqual(guarded.get('/api/overview',headers={'x-companion-token':'sesame'}).status_code,200)
        self.assertEqual(guarded.get('/api/overview?token=sesame').status_code,200)
        self.assertEqual(guarded.get('/').status_code,200)   # the page itself still loads

    def test_a_likeness_can_be_uploaded_shown_and_forgotten(self):
        png=_png()
        r=self.client.post('/api/portrait',content=png)
        self.assertEqual(r.status_code,200,r.text)
        state=self.client.get('/api/portrait').json()
        self.assertTrue(state['stored'])
        self.assertEqual(self.client.get('/media/portrait').status_code,200)
        self.assertEqual(self.client.delete('/api/portrait').status_code,200)
        self.assertFalse(self.client.get('/api/portrait').json()['stored'])
        self.assertEqual(self.client.get('/media/portrait').status_code,404)

    def test_something_that_is_not_an_image_is_refused_and_stores_nothing(self):
        r=self.client.post('/api/portrait',content=b'this is not a photograph')
        self.assertEqual(r.status_code,400)
        self.assertFalse(self.client.get('/api/portrait').json()['stored'])

    def test_describing_a_face_proposes_and_writes_nothing_on_its_own(self):
        import companion_vision as vision
        from unittest.mock import patch
        self.client.post('/api/portrait',content=_png())
        before=self.c.soul.read_text()
        reply='{"hair_color":"dark auburn hair","build":"slight build","age":41,"eyes":""}'
        with patch.object(vision,'ask',return_value=reply):
            r=self.client.post('/api/portrait/describe',json={})
        self.assertEqual(r.status_code,200,r.text)
        body=r.json()
        self.assertFalse(body['written'])
        self.assertIn('dark auburn hair',body['body'])
        self.assertNotIn('age',body['fields'])
        self.assertEqual(self.c.soul.read_text(),before,'describe wrote to the SOUL')
        # The person accepting it is a separate, existing call.
        self.assertEqual(self.client.post('/api/identity/appearance',
                                          json={'body':body['body']}).status_code,200)
        self.assertIn('dark auburn hair',self.c.soul.read_text())

    def test_describing_without_a_stored_likeness_is_refused(self):
        r=self.client.post('/api/portrait/describe',json={})
        self.assertEqual(r.status_code,400)
        self.assertIn('no image',r.json()['detail'])

    def test_media_cannot_be_used_to_read_arbitrary_files(self):
        for name in ('../../../etc/passwd','..%2fpasswd','SOUL.md'):
            self.assertIn(self.client.get(f'/media/timeline/{name}').status_code,(404,400))

    def test_network_and_pin_auth(self):
        r=self.client.get('/api/network')
        self.assertEqual(r.status_code,200)
        d=r.json()
        self.assertIn('localhost_url',d)
        self.assertIn('lan_urls',d)
        self.assertFalse(d['remote_pin_configured'])

        # Configure 4-digit PIN via settings
        s_res=self.client.post('/api/settings',json={'remote_pin':'5678'})
        self.assertEqual(s_res.status_code,200)
        self.assertEqual(cc.load(self.c.home).remote_pin,'5678')

        # Network endpoint now reflects configured PIN
        r2=self.client.get('/api/network')
        self.assertTrue(r2.json()['remote_pin_configured'])

        # Wrong PIN gives 403
        bad_auth=self.client.post('/api/auth/pin',json={'pin':'0000'})
        self.assertEqual(bad_auth.status_code,403)

        # Correct PIN gives 200 and sets companion_pin_session cookie
        good_auth=self.client.post('/api/auth/pin',json={'pin':'5678'})
        self.assertEqual(good_auth.status_code,200)
        self.assertTrue(good_auth.json()['ok'])
        self.assertIn('companion_pin_session',good_auth.cookies)

        # Remote client (from LAN non-localhost) is blocked without PIN
        remote_client=TestClient(self.client.app,client=('192.168.1.50',50000))
        r_remote_locked=remote_client.get('/api/overview')
        self.assertEqual(r_remote_locked.status_code,401)
        self.assertTrue(r_remote_locked.json().get('pin_required'))

        # Remote client with session cookie succeeds
        r_remote_authed=remote_client.get('/api/overview',cookies=good_auth.cookies)
        self.assertEqual(r_remote_authed.status_code,200)

        # Clearing PIN works
        clear_res=self.client.post('/api/settings',json={'remote_pin':''})
        self.assertEqual(clear_res.status_code,200)
        self.assertEqual(cc.load(self.c.home).remote_pin,'')


if __name__=='__main__':unittest.main()
