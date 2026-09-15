import copy,datetime as dt,json,pathlib,sqlite3,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc,companion_local_reflection as reflection,companion_checkin as checkin,companion_self as slf,companion_journal as journal

def empty(text='A quiet day of reading, in my own imagined life.'):
    return dict(reflection=text,preferences=[],questions=[],facts=[],standing=[],moments=[],answers=[],open_loops=[],soul_append='')
class ReflectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name);self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'home',vault=root/'vault',timezone='UTC')
        self.c.home.mkdir(parents=True);self.c.soul_dir.mkdir(parents=True)
        self.c.soul.write_text('A companion.\n'+slf.BEGIN+'\nI like books.\n'+slf.END+'\n')
        self.now=dt.datetime(2026,9,12,11,tzinfo=dt.timezone.utc)
    def db(self):
        db=sqlite3.connect(self.c.home/'state.db')
        db.executescript('CREATE TABLE sessions(id TEXT, source TEXT,user_id TEXT); CREATE TABLE messages(id INTEGER,session_id TEXT,role TEXT,content TEXT,timestamp REAL,active INTEGER,compacted INTEGER,_compressed_summary INTEGER);')
        db.execute('INSERT INTO sessions VALUES (?,?,?)',('chat','telegram','human'))
        db.execute('INSERT INTO sessions VALUES (?,?,?)',('cron','cron','human'))
        return db
    def test_evidence_is_exact_user_quote_and_dates_are_code_owned(self):
        source={'1':{'id':'1','role':'user','content':'My sister is Bee.','timestamp':self.now.timestamp(),'session_id':'chat'}}
        plan=empty();plan['facts']=[{'quote_id':'1','category':'people'}]
        reflection.validate(plan,'daily',source,[])
        reflection.apply_plan(self.c,'daily','2026-09-11',plan,source,self.now)
        self.assertIn('## 2026-09-11',journal.path_for(self.c,'daily').read_text())
        self.assertEqual(slf.facts(self.c.human_dir)[0]['statement'],'Alex said: "My sister is Bee."')
        bad=copy.deepcopy(plan);bad['facts'][0]['quote_id']='not-a-human-quote'
        with self.assertRaises(ValueError):reflection.validate(bad,'daily',source,[])
        bad=empty();bad['soul_append']='Change my identity'
        with self.assertRaises(ValueError):reflection.validate(bad,'daily',source,[])
    def test_daily_retry_does_not_call_model_or_duplicate_journal(self):
        calls=[]
        def planner(*args):calls.append(1);return empty(),{'completion_tokens':20}
        first=reflection.reflect(self.c,'daily','http://127.0.0.1:1','test',now=self.now,planner=planner)
        second=reflection.reflect(self.c,'daily','http://127.0.0.1:1','test',now=self.now,planner=planner)
        self.assertEqual(first['status'],'recorded');self.assertEqual(second['status'],'skipped');self.assertEqual(len(calls),1)
        self.assertEqual(journal.path_for(self.c,'daily').read_text().count('## 2026-09-11'),1)
    def test_checkin_does_not_clear_a_conversation_that_arrives_during_generation(self):
        db=self.db();stamp=self.now-dt.timedelta(minutes=1)
        db.execute('INSERT INTO messages VALUES(1,?,?,?,?,1,0,0)',('chat','user','My sister is Bee.',stamp.timestamp()));db.commit();db.close()
        checkin.flag(self.c,self.now)
        def planner(*args):
            checkin.flag(self.c,self.now+dt.timedelta(seconds=10));plan=empty('')
            plan['facts']=[{'quote_id':'1:0','category':'people'}]
            return plan,{}
        result=reflection.reflect(self.c,'checkin','http://127.0.0.1:1','test','human',now=self.now,planner=planner)
        self.assertEqual(result['status'],'recorded');self.assertGreater(checkin.read(self.c)['pending'],0)
        self.assertEqual(checkin.read(self.c)['last_reflected'],self.now.isoformat())
    def test_trusted_sources_and_same_timestamp_pagination_preserve_evidence(self):
        db=self.db();stamp=self.now.timestamp()
        for i in range(1,4):db.execute('INSERT INTO messages VALUES(?,?,?,?,?,1,0,0)',(i,'chat','user','x'*200,stamp))
        db.execute('INSERT INTO messages VALUES(4,?,?,?,?,1,0,0)',('cron','user','Not human evidence',stamp))
        db.execute('INSERT INTO messages VALUES(5,?,?,?,?,0,1,0)',('chat','user','Compacted original',stamp))
        db.commit();db.close()
        rows,more,through,cursor=reflection.messages(self.c,self.now-dt.timedelta(seconds=1),self.now,'human',limit_chars=500)
        self.assertEqual([r['id'] for r in rows],['1']);self.assertTrue(more)
        rest,_,_,_=reflection.messages(self.c,dt.datetime.fromisoformat(through),self.now,'human',after_id=cursor)
        self.assertEqual([r['id'] for r in rest],['2','3','5'])

    def test_long_unbroken_evidence_is_bounded_without_losing_characters(self):
        content='x'*901
        result=reflection.quotation_sources([dict(id='1',role='user',content=content)])
        self.assertEqual(''.join(s['content'] for s in result.values()),content)
        self.assertTrue(all(len(s['content'])<=300 for s in result.values()))
        plan=empty();plan['questions']=['q-deadbeef']
        with self.assertRaises(ValueError):reflection.validate(plan,'daily',{},[])

    def test_periodic_midnight_boundary_does_not_include_the_next_day(self):
        db=self.db();start=self.now.replace(hour=0)-dt.timedelta(days=1);end=start+dt.timedelta(days=1)
        db.execute('INSERT INTO messages VALUES(1,?,?,?,?,1,0,0)',('chat','user','At the start',start.timestamp()))
        db.execute('INSERT INTO messages VALUES(2,?,?,?,?,1,0,0)',('chat','user','Next day',end.timestamp()))
        db.commit();db.close()
        rows,*_=reflection.messages(self.c,start,end,'human',end_inclusive=False)
        self.assertEqual([r['id'] for r in rows],['1'])
        rows,*_=reflection.messages(self.c,start,end,'human',end_inclusive=True)
        self.assertEqual([r['id'] for r in rows],['1','2'])
