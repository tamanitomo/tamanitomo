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
        plan=empty();plan['facts']=[{'quote_id':'1','category':'people','statement':"Alex's sister is Bee."}]
        reflection.validate(plan,'daily',source,[],'Alex')
        reflection.apply_plan(self.c,'daily','2026-09-11',plan,source,self.now)
        self.assertIn('## 2026-09-11',journal.path_for(self.c,'daily').read_text())
        fact=slf.facts(self.c.human_dir)[0]
        self.assertEqual(fact['statement'],"Alex's sister is Bee.")
        self.assertTrue(fact['evidence'].endswith(': My sister is Bee.'),'the exact quote stays the evidence')
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
            plan['facts']=[{'quote_id':'1:0','category':'people','statement':"Alex's sister is Bee."}]
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

class FactQualityTests(unittest.TestCase):
    """Facts are propositions backed by a verbatim quote; questions are asked to the human."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name);self.c=cc.Companion(agent='Nova',human='Robin',hermes_root=root/'home',vault=root/'vault',timezone='UTC')
        self.c.home.mkdir(parents=True);self.c.soul_dir.mkdir(parents=True)
        self.c.soul.write_text('A companion.\n'+slf.BEGIN+'\nI like books.\n'+slf.END+'\n')
        self.now=dt.datetime(2026,9,23,11,tzinfo=dt.timezone.utc)
        self.source={'7':{'id':'7','role':'user','content':'I play Fire Emblem all the time.','timestamp':self.now.timestamp(),'session_id':'chat'},
                     '8':{'id':'8','role':'assistant','content':'You love Fire Emblem.','timestamp':self.now.timestamp(),'session_id':'chat'}}
    def plan(self,**facts):
        plan=empty();plan['facts']=[{'quote_id':'7','category':'likes',**facts}];return plan

    def test_schema_requires_a_statement_on_every_fact(self):
        fact=reflection.schema('daily',self.source,[])['properties']['facts']['items']
        self.assertEqual(set(fact['required']),{'quote_id','category','statement'})
        with self.assertRaises(ValueError):reflection.validate(self.plan(),'daily',self.source,[],'Robin')
        for bad in ('','   ','x'*401):
            with self.assertRaises(ValueError):reflection.validate(self.plan(statement=bad),'daily',self.source,[],'Robin')

    def test_the_proposition_is_stored_and_the_quote_is_the_evidence(self):
        plan=self.plan(statement='Robin enjoys playing Fire Emblem.')
        reflection.validate(plan,'daily',self.source,[],'Robin')
        reflection.apply_plan(self.c,'daily','2026-09-22',plan,self.source,self.now)
        [fact]=slf.facts(self.c.human_dir)
        self.assertEqual(fact['statement'],'Robin enjoys playing Fire Emblem.')
        self.assertIn('I play Fire Emblem all the time.',fact['evidence'])
        self.assertNotIn('said:',fact['statement'])
        self.assertIn('session:chat message:7',fact['source'])
        self.assertEqual(fact['confidence'],'stated')

    def test_a_statement_still_needs_trusted_human_evidence(self):
        for quote in ('8','missing'):
            plan=self.plan(statement='Robin enjoys playing Fire Emblem.');plan['facts'][0]['quote_id']=quote
            with self.assertRaises(ValueError):reflection.validate(plan,'daily',self.source,[],'Robin')

    def test_transcript_wrappers_are_refused(self):
        for bad in ('Robin said: "I play Fire Emblem all the time."','Robin said that he plays Fire Emblem.',
                    'robin mentioned: Fire Emblem','Robin told me he plays Fire Emblem.','The human said: I play Fire Emblem',
                    'The user said he plays Fire Emblem.'):
            with self.assertRaises(ValueError,msg=bad):reflection.validate(self.plan(statement=bad),'daily',self.source,[],'Robin')
        # Only that shape: the human's name leading an ordinary proposition is fine.
        reflection.validate(self.plan(statement='Robin saids nothing; Robin plays Fire Emblem often.'),'daily',self.source,[],'Robin')

    def test_the_prompt_asks_for_propositions_and_sees_what_is_known(self):
        slf.record_fact(self.c.human_dir,'Robin has a sister.','2026-09-01: my sister',self.now,'people',human='Robin')
        data=reflection.context(self.c,'checkin',self.now,self.now,'2026-09-23',[])
        self.assertEqual([f['statement'] for f in data['existing_facts']],['Robin has a sister.'])
        self.assertNotIn('evidence',data['existing_facts'][0])
        self.assertIn('every fact',data['existing_facts_note'])
        seen={}
        class Stop(Exception):pass
        def fake(req,timeout):seen['body']=json.loads(req.data);raise Stop
        original=reflection.urllib.request.urlopen;reflection.urllib.request.urlopen=fake
        try:
            with self.assertRaises(Stop):reflection.request_plan(self.c,'daily',{'existing_questions':[]},self.source,'http://127.0.0.1:1','m',1)
        finally:reflection.urllib.request.urlopen=original
        prompt=seen['body']['messages'][0]['content']
        self.assertIn('facts[].statement is a concise durable proposition',prompt)
        self.assertIn('not permission to infer additional facts',prompt)
        self.assertIn('Do not record a fact that merely restates an existing fact',prompt)
        self.assertIn('ask Robin directly',prompt)
        self.assertIn('use "you"/"your" when referring to Robin',prompt)
        self.assertIn('Do not invent a question merely to fill the array',prompt)

    def test_existing_facts_are_bounded_and_say_so(self):
        for i in range(40):
            slf.record_fact(self.c.human_dir,f'Robin owns board game number {i} of a long collection.',f'2026-09-01: game {i}',
                            self.now+dt.timedelta(minutes=i),'likes',human='Robin')
        known=slf.fact_statements(self.c.human_dir,1000)
        self.assertLess(len(known['facts']),40);self.assertEqual(len(known['facts'])+known['omitted'],40)
        self.assertIn('not everything already known',known['note'])
        self.assertIn('number 39',known['facts'][0]['statement'],'newest first')

    def test_questions_are_addressed_to_the_human(self):
        for good in ('Why did you stop playing guitar?','What happened next?','Did your sister like the gift she got?',
                     'What was he like, your old roommate?'):
            plan=empty();plan['questions']=[good];reflection.validate(plan,'daily',{},[],'Robin')
        for bad in ('What was Robin like in high school?','How does the human feel about moving again?',
                    'Why did the user stop playing guitar?',"Is robin's sister older?"):
            plan=empty();plan['questions']=[bad]
            with self.assertRaises(ValueError,msg=bad):reflection.validate(plan,'daily',{},[],'Robin')

    def test_a_plan_saved_under_the_old_contract_still_applies(self):
        (self.c.life/'local-reflections').mkdir(parents=True)
        old=empty();old['facts']=[{'quote_id':'7','category':'likes'}];old['questions']=['What was Robin like in school?']
        path=self.c.life/'local-reflections'/'daily-2026-09-22.json'
        path.write_text(json.dumps({'id':'daily-2026-09-22','kind':'daily','day':'2026-09-22','plan':old,'sources':self.source,
                                    'usage':None,'authored_at':self.now.isoformat(),'complete':False}))
        result=reflection.reflect(self.c,'daily','http://127.0.0.1:1','m',now=self.now+dt.timedelta(days=0),
                                  planner=lambda *a:self.fail('a saved plan is not re-requested'))
        self.assertEqual(result['status'],'recorded')
        self.assertEqual(slf.facts(self.c.human_dir)[0]['statement'],'Robin said: "I play Fire Emblem all the time."')
        with self.assertRaises(ValueError):reflection.validate(old,'daily',self.source,[],'Robin')

class FactLedgerTests(unittest.TestCase):
    """Write-time duplicates are refused only on an exact canonical match; the rest is report-only."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)/'robin'
        self.now=dt.datetime(2026,9,23,11,tzinfo=dt.timezone.utc)
    def fact(self,statement,evidence='2026-09-23T10:00:00+00:00: I said so',category='likes',source='session:a message:1',**kw):
        return slf.record_fact(self.root,statement,evidence,self.now,category,'stated',source,human='Robin',**kw)

    def test_the_same_proposition_is_one_fact_whatever_its_category_source_or_evidence(self):
        first=self.fact('Robin enjoys playing Fire Emblem.')
        again=self.fact('  robin ENJOYS playing “Fire   Emblem”!  ',evidence='2026-09-24T09:00:00+00:00: Fire Emblem again',
                        category='other',source='session:b message:9')
        self.assertTrue(first['written'])
        self.assertEqual(again,{'written':False,'reason':'fact already recorded','duplicate_of':first['entry']['id']})
        self.assertEqual(len(slf.facts(self.root)),1)
        self.assertEqual(len(slf._read(self.root/'facts.jsonl')),1,'nothing appended')

    def test_different_facts_are_kept(self):
        for s in ('Robin likes tea.','Robin dislikes tea.','Robin does not like tea.',
                  "Robin's sister Alice lives in Raleigh.","Robin's sister Beth lives in Raleigh.",
                  'Robin has a GTX 1050 Ti in the first spare PC.','Robin has a GTX 1050 Ti in the second spare PC.',
                  'Robin has a 4.5 GB card.','Robin has a 45 GB card.'):
            self.assertTrue(self.fact(s)['written'],s)
        self.assertEqual(len(slf.facts(self.root)),9)

    def test_corrections_and_retractions_still_work(self):
        original=self.fact('Robin likes tea.')['entry']
        # A correction may restate the fact it replaces, e.g. to fix its category.
        fixed=self.fact('Robin likes tea.',category='dislikes',supersedes=original['id'])
        self.assertTrue(fixed['written'])
        self.assertEqual([f['id'] for f in slf.facts(self.root)],[fixed['entry']['id']])
        slf.retract_fact(self.root,fixed['entry']['id'],'Never said it',self.now)
        self.assertEqual(slf.facts(self.root),[])
        self.assertEqual(len(slf._read(self.root/'facts.jsonl',kind='human_fact')),2,'history retained')
        # Once withdrawn, the same proposition can be recorded again.
        self.assertTrue(self.fact('Robin likes tea.',evidence='2026-09-25T09:00:00+00:00: I do like tea')['written'])

    def test_rerunning_the_same_write_is_still_idempotent(self):
        first=self.fact('Robin enjoys tea.');again=self.fact('Robin enjoys tea.')
        self.assertFalse(again['written']);self.assertEqual(again['entry']['id'],first['entry']['id'])

    def test_duplicate_report_finds_candidates_and_changes_nothing(self):
        self.fact('Robin has an older 4 GB GTX 1050 Ti available to install in his old office tower.',category='logistics')
        self.fact('Robin has an older 4 GB GTX 1050 Ti available for the old office tower.',category='other')
        self.fact('Robin has a GTX 1050 Ti in the first spare PC.');self.fact('Robin has a GTX 1050 Ti in the second spare PC.')
        self.fact('Robin likes Fire Emblem.');self.fact('Robin dislikes Fire Emblem.')
        before=(self.root/'facts.jsonl').read_bytes()
        report=slf.duplicate_facts(self.root)
        self.assertEqual((self.root/'facts.jsonl').read_bytes(),before,'report only')
        pairs={tuple(sorted(f['statement'] for f in c['facts'])):c for c in report['candidates']}
        dell=pairs[tuple(sorted(['Robin has an older 4 GB GTX 1050 Ti available to install in his old office tower.',
                                 'Robin has an older 4 GB GTX 1050 Ti available for the old office tower.']))]
        self.assertIn('contains every word',dell['reason'])
        self.assertEqual({f['category'] for f in dell['facts']},{'logistics','other'})
        self.assertTrue(all(f['id'] for f in dell['facts']))
        spare=pairs[tuple(sorted(['Robin has a GTX 1050 Ti in the first spare PC.','Robin has a GTX 1050 Ti in the second spare PC.']))]
        self.assertIn('probably distinct',spare['reason'])
        self.assertEqual(len(slf.facts(self.root)),6)
