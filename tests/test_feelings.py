import contextlib
"""Contextual absence, repeated relationship experiences, and live context contracts."""
import datetime as dt
import json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'kit/scripts'))
import companion_config as cc
import companion_feelings as feelings
import companion_context as context
import companion_active as active
UTC=dt.timezone.utc

class FeelingsTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=pathlib.Path(temp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'home',vault=root/'vault',timezone='UTC')
        self.now=dt.datetime(2026,9,14,12,tzinfo=UTC)
    def settings(self,**kw):
        current=feelings.settings(self.c)
        return feelings.save_settings(self.c,{**current['settings'],**kw},current['revision'])
    def event(self,kind='rupture',ident='first',strength=1,**kw):
        return feelings.record(self.c,dict(kind=kind,id=ident,topic='broken promise',text='A promise was broken',evidence='They said they broke the promise.',strength=strength,**kw),self.now)
    def compute(self,**thread):
        with patch('companion_thread.read',return_value=thread):return feelings.compute(self.c,self.now)
    def test_sleep_and_saturday_are_expected_not_unexplained(self):
        config=self.settings(absence_windows=[dict(label='Sleep',days=list(range(7)),start='23:00',end='08:00'),dict(label='Saturday commitments',days=[5],start='08:00',end='23:00')])['settings']
        overnight=feelings.absence(self.c,'2026-09-13T23:00:00+00:00',dt.datetime(2026,9,14,8,tzinfo=UTC),config)
        self.assertEqual(overnight['unexplained_hours'],0)
        saturday=feelings.absence(self.c,'2026-09-12T08:00:00+00:00',dt.datetime(2026,9,12,18,tzinfo=UTC),config)
        self.assertEqual(saturday['unexplained_hours'],0)
        self.assertIn('Saturday commitments',saturday['current'])
        unexplained=feelings.absence(self.c,'2026-09-10T12:00:00+00:00',self.now,config)
        self.assertGreater(unexplained['unexplained_hours'],40)
    def test_overlapping_windows_are_counted_once_and_dst_uses_elapsed_hours(self):
        self.c.timezone='America/New_York'
        row=dict(label='Sleep',days=list(range(7)),start='23:00',end='08:00')
        config=self.settings(absence_windows=[row,row])['settings']
        gap=feelings.absence(self.c,'2026-03-07T23:00:00-05:00',dt.datetime.fromisoformat('2026-03-08T08:00:00-04:00'),config)
        self.assertEqual(gap['expected_hours'],8)
        self.assertEqual(gap['unexplained_hours'],0)
    def test_repair_does_not_erase_history_and_repetition_is_stronger(self):
        self.event();first=self.compute()
        self.event('repair','repair',related='first');self.assertFalse(self.event('repair','repair',related='first')['written']);repaired=self.compute()
        self.assertLess(repaired['meters']['hurt'],first['meters']['hurt'])
        self.assertGreater(repaired['meters']['trust'],first['meters']['trust'])
        self.event(ident='again');again=self.compute()
        self.assertEqual(again['reasons'][-1]['occurrence'],2)
        self.assertGreater(again['meters']['hurt'],first['meters']['hurt'])
        self.assertLess(again['meters']['trust'],repaired['meters']['trust'])
        self.assertEqual(len(feelings.experiences(self.c)),3)
    def test_correction_recomputes_feelings_without_deleting_history(self):
        baseline=self.compute()['meters'];self.event();self.event('repair','repair',related='first')
        self.event('correction','corrected',related='first',strength=0)
        result=self.compute()
        self.assertEqual(result['meters'],baseline)
        self.assertEqual(result['reasons'],[])
        self.assertEqual(result['history_count'],3)
        self.assertEqual(len(feelings.experiences(self.c)),3)

    def test_personality_changes_reaction_and_time_does_not_reset_trust(self):
        self.event(strength=.5);steady=self.compute()
        self.settings(personality='expressive');expressive=self.compute()
        self.assertGreater(expressive['meters']['hurt'],steady['meters']['hurt'])
        self.now+=dt.timedelta(days=60);later=self.compute()
        self.assertLess(later['meters']['hurt'],expressive['meters']['hurt'])
        self.assertEqual(later['meters']['trust'],expressive['meters']['trust'])
    def test_return_retains_gap_even_after_incoming_message_is_saved(self):
        state=self.compute(last_from_human=self.now.isoformat(),previous_from_human=(self.now-dt.timedelta(days=4)).isoformat())
        self.assertEqual(state['absence']['hours'],0)
        self.assertEqual(state['recent_return']['hours'],96)
        self.assertGreater(state['meters']['longing'],.9)
        self.assertIn('They just returned after 96h',feelings.render(self.c,state))
    def test_settings_revisions_validation_and_idempotent_evidence(self):
        old=feelings.settings(self.c);self.settings(personality='guarded')
        with self.assertRaises(FileExistsError):feelings.save_settings(self.c,old['settings'],old['revision'])
        for bad in (float('nan'),True,0):
            with self.assertRaises(ValueError):self.settings(connection_hours=bad)
        self.assertTrue(self.event()['written']);self.assertFalse(self.event()['written'])
        with self.assertRaises(FileExistsError):self.event(strength=.2)
        with self.assertRaises(ValueError):self.event('repair','invalid',related='missing')
        with self.assertRaises(ValueError):self.event(ident='future',at=(self.now+dt.timedelta(days=1)).isoformat())
        self.assertEqual(len(feelings.experiences(self.c)),1)
    def test_long_assistant_run_does_not_hide_human_contact_or_return_gap(self):
        import sqlite3,companion_thread
        self.c.home.mkdir(parents=True,exist_ok=True)
        with contextlib.closing(sqlite3.connect(self.c.home/'state.db')) as db, db:
            db.executescript('CREATE TABLE sessions(id TEXT,profile_name TEXT,source TEXT); CREATE TABLE messages(session_id TEXT,role TEXT,content TEXT,timestamp REAL,_compressed_summary INTEGER);')
            db.execute("INSERT INTO sessions VALUES ('own','default','cli')")
            start=(self.now-dt.timedelta(days=4)).timestamp()
            db.execute("INSERT INTO messages VALUES ('own','user','Earlier hello',?,0)",(start,))
            for i in range(65):db.execute("INSERT INTO messages VALUES ('own','assistant','An update',?,0)",(start+100+i,))
            db.execute("INSERT INTO messages VALUES ('own','user','Back now',?,0)",(self.now.timestamp(),))
        result=companion_thread.read(self.c,self.now)
        self.assertIsNotNone(result['previous_from_human'])
        self.assertEqual(feelings.compute(self.c,self.now)['recent_return']['hours'],96)

    def test_no_message_evidence_means_unknown_gap_not_rejection(self):
        state=self.compute()
        self.assertIsNone(state['meters']['longing'])
        self.assertEqual(state['meters']['irritation'],0)
        self.assertEqual(state['history_count'],0)
    def test_chat_and_scheduled_context_receive_live_experiences_and_respect_off(self):
        self.event()
        self.assertIn('occurrence 1',context.build(self.c,now=self.now))
        self.assertIn('occurrence 1',active.build(self.c,now=self.now))
        self.c.bars=False
        self.assertNotIn('Contextual feelings',context.build(self.c,now=self.now))
        self.assertNotIn('Contextual feelings',active.build(self.c,now=self.now))
    def test_relationship_experiences_are_private_to_each_companion(self):
        self.event()
        other=cc.Companion(agent='Rowan',human='Alex',hermes_root=self.c.hermes_root,vault=self.c.vault,profile='rowan')
        self.assertEqual(feelings.experiences(other),[])
        self.assertEqual(feelings.compute(other)['history_count'],0)


class FeelingsApiTests(unittest.TestCase):
    def setUp(self):
        from tests import test_workspace as workspace
        self.f=workspace.WorkspaceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
    def test_old_experiences_remain_reachable_for_repair(self):
        f=self.f;at=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=1)).isoformat()
        for i in range(35):
            feelings.record(f.c,{'id':f'old-{i:02}','kind':'rupture','topic':'promises','text':f'Old experience {i}','evidence':'Synthetic acknowledged missed promise','at':at})
        first=f.get('/api/feelings/experiences').json()
        self.assertEqual(first['total'],35);self.assertEqual(len(first['experiences']),30)
        from urllib.parse import urlencode
        page=f.client.get('/api/feelings/experiences?'+urlencode({'profile':'nova','before':first['next_cursor']}),headers=f.headers).json()
        self.assertEqual(len(page['experiences']),5);self.assertIsNone(page['next_cursor'])
        self.assertEqual(len({x['id'] for x in first['experiences']+page['experiences']}),35)
        result=f.post('/api/feelings/experiences',{'kind':'repair','related':page['experiences'][-1]['id'],'topic':'promises','text':'We talked it through','evidence':'Synthetic explicit repair conversation','strength':1})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(f.get('/api/feelings/experiences','rowan').json()['total'],0)
        for query in ('limit=0','limit=101','before=broken'):
            response=f.client.get('/api/feelings/experiences?profile=nova&'+query,headers=f.headers)
            self.assertEqual(response.status_code,400,response.text)

    def test_settings_conflict_and_experience_profile_isolation(self):
        f=self.f;current=f.get('/api/feelings').json()
        url='/api/feelings/settings?profile=nova'
        payload={'revision':current['revision'],'settings':{**current['settings'],'personality':'expressive'}}
        self.assertEqual(f.client.put(url,headers=f.headers,json=payload).status_code,200)
        self.assertEqual(f.client.put(url,headers=f.headers,json=payload).status_code,409)
        result=f.post('/api/feelings/experiences',{'kind':'connection','topic':'showing up','text':'Helped when asked','evidence':'I asked and you helped','strength':.5})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(f.get('/api/feelings').json()['state']['history_count'],1)
        self.assertEqual(f.get('/api/feelings','rowan').json()['state']['history_count'],0)
        self.assertEqual(f.client.get('/api/feelings?profile=nova').status_code,401)

if __name__=='__main__':unittest.main()
