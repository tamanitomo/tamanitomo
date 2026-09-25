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
        checkin.flag(self.c,self.now,platform='telegram')
        def planner(*args):
            checkin.flag(self.c,self.now+dt.timedelta(seconds=10),platform='telegram');plan=empty('')
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
        self.assertEqual([d['text'] for d in reflection.validate(plan,'daily',{},[])['omitted']],['q-deadbeef'])

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
    def converse(self,*quotes):
        """Yesterday's conversation in state.db, for tests that run reflect().
        Returns the quote IDs, in order."""
        db=sqlite3.connect(self.c.home/'state.db')
        db.executescript('CREATE TABLE IF NOT EXISTS sessions(id TEXT, source TEXT,user_id TEXT); CREATE TABLE IF NOT EXISTS messages(id INTEGER,session_id TEXT,role TEXT,content TEXT,timestamp REAL,active INTEGER,compacted INTEGER,_compressed_summary INTEGER);')
        db.execute('INSERT INTO sessions VALUES (?,?,?)',('chat','telegram','robin'))
        at=(self.now-dt.timedelta(days=1)).timestamp()
        for i,q in enumerate(quotes,1):db.execute('INSERT INTO messages VALUES (?,?,?,?,?,1,0,0)',(i,'chat','user',q,at+i))
        db.commit();db.close()
        return [f'{i}:0' for i in range(1,len(quotes)+1)]
    def run_daily(self,plan,**kw):
        return reflection.reflect(self.c,'daily','http://127.0.0.1:1','m',human_id='robin',now=self.now,
                                  planner=kw.pop('planner',lambda *a:(plan,None)),**kw)

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

    WRAPPERS=('Robin said: "I play Fire Emblem all the time."','Robin said that he plays Fire Emblem.',
              'robin mentioned: Fire Emblem','Robin told me he plays Fire Emblem.','The human said: I play Fire Emblem',
              'The user said he plays Fire Emblem.')
    def test_transcript_wrappers_are_held_not_fatal(self):
        for bad in self.WRAPPERS:
            found=reflection.validate(self.plan(statement=bad),'daily',self.source,[],'Robin')
            self.assertEqual(found['held'],[{'kind':'fact','quote_id':'7','statement':bad,'reason':'transcript_wrapper'}],bad)
            # A contract-2 plan was saved when this was fatal, and stays so on resume.
            with self.assertRaises(ValueError,msg=bad):reflection.validate(self.plan(statement=bad),'daily',self.source,[],'Robin',contract=2)
        # Only that shape: the human's name leading an ordinary proposition is fine.
        found=reflection.validate(self.plan(statement='Robin saids nothing; Robin plays Fire Emblem often.'),'daily',self.source,[],'Robin')
        self.assertEqual(found['held'],[])

    def test_a_wrapper_fact_is_held_as_written_and_its_siblings_are_kept(self):
        quotes=self.converse('I play Fire Emblem all the time.','I have three cats.')
        plan=empty()
        plan['facts']=[{'quote_id':quotes[0],'category':'likes','statement':'Robin said: "I play Fire Emblem all the time."'},
                       {'quote_id':quotes[1],'category':'other','statement':'Robin has 3 cats.'}]
        calls=[]
        result=self.run_daily(None,planner=lambda *a:(calls.append(1),(plan,None))[1])
        self.assertEqual(result['status'],'recorded');self.assertFalse(result['clean']);self.assertEqual(result['held_facts'],1)
        self.assertEqual(len(calls),1,'no second request is made for style')
        self.assertEqual([f['statement'] for f in slf.facts(self.c.human_dir)],['Robin has 3 cats.'])
        [held]=slf.held_facts(self.c.human_dir)
        self.assertEqual(held['statement'],'Robin said: "I play Fire Emblem all the time."','not re-worded')
        self.assertIn('transcript_wrapper',held['reasons'])
        self.assertTrue(held['evidence'].endswith('I play Fire Emblem all the time.'))

    def test_a_saved_plan_resumes_with_its_saved_diagnostics(self):
        [quote]=self.converse('I play Fire Emblem all the time.')
        plan=self.plan(statement='Robin plays Fire Emblem.');plan['facts'][0]['quote_id']=quote
        plan['questions']=['Which Fire Emblem did you play first?']
        folder=self.c.life/'local-reflections';folder.mkdir(parents=True)
        day=(self.now-dt.timedelta(days=1)).date().isoformat()
        sources=reflection.quotation_sources(reflection.messages(self.c,self.now-dt.timedelta(days=1),self.now,'robin')[0])
        # Saved with a diagnostic today's rules would not produce: that decision stands.
        (folder/f'daily-{day}.json').write_text(json.dumps({'id':f'daily-{day}','kind':'daily','day':day,'plan':plan,
            'sources':sources,'usage':None,'authored_at':self.now.isoformat(),'contract':3,'complete':False,
            'diagnostics':{'omitted':[{'kind':'question','text':plan['questions'][0],'reason':'saved'}],'warnings':[],'held':[]}}))
        result=self.run_daily(None,planner=lambda *a:self.fail('a saved plan is not re-requested'))
        self.assertEqual(result['status'],'recorded');self.assertEqual(slf.questions(self.c.life),[])
        self.assertEqual([d['reason'] for d in result['omitted']],['saved'])

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
        def check(q,name='Robin'):
            plan=empty();plan['questions']=[q];return reflection.validate(plan,'daily',{},[],name)
        for good in ('Why did you stop playing guitar?','What happened next?','Did your sister like the gift she got?',
                     'What was he like, your old roommate?','Robin, how was the trip?','How was the trip, Robin?',
                     'Did Robin the cat ever come home to you?',"Is robin's sister older?"):
            self.assertEqual(check(good),{'omitted':[],'warnings':[],'held':[]},good)
        # A name that is also a word is not the person.
        self.assertEqual(check('What will you do tomorrow?','Will'),{'omitted':[],'warnings':[],'held':[]})
        self.assertEqual(check('May I ask about your trip?','May'),{'omitted':[],'warnings':[],'held':[]})
        # Machine wording is left out; a question about the human in the third person is kept and reported.
        for bad in ('How does the human feel about moving again?','Why did the user stop playing guitar?','q-0123abcd'):
            found=check(bad);self.assertEqual([d['text'] for d in found['omitted']],[bad]);self.assertEqual(found['warnings'],[])
        found=check('What was Robin like in high school?')
        self.assertEqual(found['omitted'],[]);self.assertIn('third person',found['warnings'][0]['reason'])

    def test_a_poorly_worded_question_does_not_cost_the_reflection(self):
        [quote]=self.converse('I play Fire Emblem all the time.')
        plan=self.plan(statement='Robin plays Fire Emblem.');plan['facts'][0]['quote_id']=quote
        plan['questions']=['How does the human feel about Fire Emblem?','Which Fire Emblem did you play first?']
        result=self.run_daily(plan)
        self.assertEqual(result['status'],'recorded');self.assertFalse(result['clean'])
        self.assertEqual([d['text'] for d in result['omitted']],['How does the human feel about Fire Emblem?'])
        self.assertEqual([q['text'] for q in slf.questions(self.c.life)],['Which Fire Emblem did you play first?'])
        self.assertEqual([f['statement'] for f in slf.facts(self.c.human_dir)],['Robin plays Fire Emblem.'])
        saved=json.loads((self.c.life/'local-reflections'/(result['id']+'.json')).read_text())
        self.assertEqual(saved['diagnostics']['omitted'][0]['kind'],'question')
        self.assertEqual(saved['plan']['questions'],plan['questions'],'the plan is saved as authored')
        again=self.run_daily(None,planner=lambda *a:self.fail('committed'))
        self.assertEqual(again['status'],'skipped')

    def test_a_clean_run_says_so(self):
        [quote]=self.converse('I play Fire Emblem all the time.')
        plan=self.plan(statement='Robin plays Fire Emblem.');plan['facts'][0]['quote_id']=quote
        result=self.run_daily(plan)
        self.assertTrue(result['clean']);self.assertEqual(result['held_facts'],0)

    def test_refused_plans_are_retried_a_bounded_number_of_times(self):
        self.converse('I play Fire Emblem all the time.')
        bad=self.plan(statement='Robin plays Fire Emblem.');bad['facts'][0]['quote_id']='not-a-quote'
        calls=[]
        def planner(*a):calls.append(1);return bad,None
        for _ in range(reflection.MAX_ATTEMPTS):
            with self.assertRaises(ValueError):
                self.run_daily(None,planner=planner)
            self.now+=dt.timedelta(hours=2)
        held=self.run_daily(None,planner=planner)
        self.assertEqual(held['status'],'held');self.assertEqual(len(calls),reflection.MAX_ATTEMPTS,'the model is not asked again')
        self.assertEqual(len(held['errors']),reflection.MAX_ATTEMPTS)
        folder=self.c.life/'local-reflections'
        self.assertEqual(len(list(folder.glob(held['id']+'.rejected-*.json'))),reflection.MAX_ATTEMPTS,'each refused plan is kept for review')
        self.assertEqual(slf.facts(self.c.human_dir),[])

    def attempts(self,key=None):
        folder=self.c.life/'local-reflections'
        [path]=[folder/f'{key}.attempts.json'] if key else list(folder.glob('*.attempts.json'))
        return json.loads(path.read_text())

    def test_the_whole_attempt_is_counted_before_the_request(self):
        self.converse('I play Fire Emblem all the time.')
        seen=[]
        def planner(*a):
            seen.append(self.attempts()['count'])
            raise OSError('connection refused')
        with self.assertRaises(OSError):self.run_daily(None,planner=planner)
        self.assertEqual(seen,[1],'accounted on disk before inference')
        self.assertEqual(self.attempts()['errors'][0]['error'],'connection refused')
        # A truncated or undecodable reply is an attempt too.
        for exc in (ValueError('reflection was truncated; nothing recorded'),json.JSONDecodeError('bad','x',0)):
            self.now+=dt.timedelta(hours=2)
            def fail(*a,exc=exc):raise exc
            with self.assertRaises(ValueError):self.run_daily(None,planner=fail)
        self.now+=dt.timedelta(hours=2)
        held=self.run_daily(None,planner=lambda *a:self.fail('budget spent'))
        self.assertEqual((held['status'],held['attempts']),('held',3))

    def test_a_crash_mid_generation_still_spends_the_attempt(self):
        self.converse('I play Fire Emblem all the time.')
        class Killed(BaseException):pass
        def planner(*a):raise Killed()
        with self.assertRaises(Killed):self.run_daily(None,planner=planner)
        self.assertEqual(self.attempts()['count'],1)

    def test_failed_attempts_back_off(self):
        self.converse('I play Fire Emblem all the time.')
        def fail(*a):raise OSError('down')
        with self.assertRaises(OSError):self.run_daily(None,planner=fail)
        waiting=self.run_daily(None,planner=lambda *a:self.fail('too soon'))
        self.assertEqual(waiting['status'],'waiting')
        self.assertEqual(waiting['retry_after'],(self.now+reflection.BACKOFF[0]).isoformat())
        self.now+=reflection.BACKOFF[0]
        [quote]=['1:0'];plan=self.plan(statement='Robin plays Fire Emblem.');plan['facts'][0]['quote_id']=quote
        self.assertEqual(self.run_daily(plan)['status'],'recorded')

    def test_a_reset_is_explicit_and_audited(self):
        self.converse('I play Fire Emblem all the time.')
        def fail(*a):raise OSError('down')
        for _ in range(reflection.MAX_ATTEMPTS):
            with self.assertRaises(OSError):self.run_daily(None,planner=fail)
            self.now+=dt.timedelta(hours=2)
        held=self.run_daily(None,planner=fail)
        self.assertEqual(held['status'],'held')
        with self.assertRaises(ValueError):reflection.reset_attempts(self.c,held['budget'],'')
        with self.assertRaises(ValueError):reflection.reset_attempts(self.c,'../escape','why')
        out=reflection.reset_attempts(self.c,held['budget'],'model server was down all night',self.now)
        self.assertEqual(out['resets'],1)
        audit=self.attempts(held['budget'])
        self.assertEqual((audit['count'],audit['resets'][0]['spent'],len(audit['resets'][0]['errors'])),(0,3,3))
        plan=self.plan(statement='Robin plays Fire Emblem.');plan['facts'][0]['quote_id']='1:0'
        self.assertEqual(self.run_daily(plan)['status'],'recorded')

    def test_a_new_checkin_arrival_does_not_reset_the_budget(self):
        self.converse('I play Fire Emblem all the time.')
        checkin.flag(self.c,self.now-dt.timedelta(hours=1),platform='telegram')
        def fail(*a):raise OSError('down')
        run=lambda planner:reflection.reflect(self.c,'checkin','http://127.0.0.1:1','m','robin',now=self.now,planner=planner)
        for i in range(reflection.MAX_ATTEMPTS):
            # Every attempt sees a batch the next conversation has grown, so a new plan key.
            checkin.flag(self.c,self.now,platform='telegram');db=sqlite3.connect(self.c.home/'state.db')
            db.execute('INSERT INTO messages VALUES (?,?,?,?,?,1,0,0)',(10+i,'chat','user',f'more {i}',self.now.timestamp()-5))
            db.commit();db.close()
            with self.assertRaises(OSError):run(fail)
            self.now+=dt.timedelta(hours=2)
        before=checkin.read(self.c)
        held=run(lambda *a:self.fail('budget spent across arrivals'))
        self.assertEqual(held['status'],'held')
        after=checkin.read(self.c)
        self.assertEqual((after.get('last_reflected'),after.get('last_reflected_id'),after['pending']),
                         (before.get('last_reflected'),before.get('last_reflected_id'),before['pending']),
                         'the watermark does not move past unprocessed evidence')
        self.assertGreater(after['pending'],0)

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
        self.assertNotIn('statement_origin',slf.facts(self.c.human_dir)[0],'a quoted statement is not a paraphrase')
        self.assertEqual([q['text'] for q in slf.questions(self.c.life)],['What was Robin like in school?'])
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
        again=self.fact('  Robin enjoys   playing Fire Emblem.  ',evidence='2026-09-24T09:00:00+00:00: Fire Emblem again',
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

    def test_only_formatting_is_folded(self):
        cases=json.loads((ROOT/'tests/canonical_statement_cases.json').read_text(encoding='utf-8'))
        for a,b in cases['same']:
            self.assertEqual(slf.canonical_statement(a),slf.canonical_statement(b),(a,b))
        # 'revised' pairs were folded before the closure; case and punctuation are now kept.
        for a,b in cases['different']+cases['revised']:
            self.assertNotEqual(slf.canonical_statement(a),slf.canonical_statement(b),(a,b))
        # ...and at write time: the second of each different pair is a new memory, not a duplicate.
        for i,(a,b) in enumerate(cases['different']+cases['revised']):
            root=self.root.parent/f'pair-{i}'
            slf.record_fact(root,a,'2026-09-23: said so',self.now,human='Robin')
            self.assertTrue(slf.record_fact(root,b,'2026-09-23: said so',self.now,human='Robin')['written'],(a,b))

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

    def test_a_correction_is_not_cancelled_by_an_equal_fact(self):
        coffee=self.fact('Robin likes coffee.')['entry'];tea=self.fact('Robin likes tea.',source='session:b message:2')['entry']
        fixed=self.fact('Robin likes tea.',evidence='2026-09-24T09:00:00+00:00: tea, not coffee',supersedes=coffee['id'])
        self.assertTrue(fixed['written']);self.assertEqual(fixed['entry']['supersedes'],coffee['id'])
        self.assertEqual(fixed['equal_to'],[tea['id']],'the overlap is reported, not merged')
        active={f['id'] for f in slf.facts(self.root)}
        self.assertNotIn(coffee['id'],active,'the corrected fact is no longer active')
        self.assertEqual(active,{tea['id'],fixed['entry']['id']})

    def test_retrying_a_correction_is_idempotent(self):
        original=self.fact('Robin likes tea.')['entry']
        first=self.fact('Robin likes green tea.',supersedes=original['id'])
        again=self.fact('Robin likes green tea.',supersedes=original['id'])
        self.assertTrue(first['written']);self.assertFalse(again['written'])
        self.assertEqual(again['entry']['id'],first['entry']['id'])

    def test_a_correction_target_is_checked_inside_the_lock(self):
        """The target has to still be active when the row is appended, not just
        when record_fact began: a rival correction may land in between."""
        original=self.fact('Robin likes tea.')['entry']
        real=slf._append
        def rival_first(path,row,**kw):
            if row.get('statement')=='Robin likes coffee.':
                real(path,{**row,'id':'fact-rival','statement':'Robin likes cocoa.'})
            return real(path,row,**kw)
        slf._append=rival_first
        try:
            with self.assertRaisesRegex(ValueError,'active fact'):self.fact('Robin likes coffee.',supersedes=original['id'])
        finally:slf._append=real
        self.assertEqual([f['statement'] for f in slf.facts(self.root)],['Robin likes cocoa.'])

    def test_concurrent_corrections_of_one_fact_leave_one_winner(self):
        import threading
        original=self.fact('Robin likes tea.')['entry'];gate=threading.Barrier(8);results=[]
        def correct(i):
            gate.wait()
            try:results.append(self.fact(f'Robin likes tea number {i}.',supersedes=original['id']))
            except ValueError as exc:results.append(exc)
        threads=[threading.Thread(target=correct,args=(i,)) for i in range(8)]
        for t in threads:t.start()
        for t in threads:t.join()
        written=[r for r in results if isinstance(r,dict) and r['written']]
        self.assertEqual(len(written),1);self.assertEqual(sum(isinstance(r,ValueError) for r in results),7)
        self.assertEqual([f['id'] for f in slf.facts(self.root)],[written[0]['entry']['id']])

    def test_a_retry_written_by_a_newer_release_is_the_same_row(self):
        old=self.fact('Robin plays Fire Emblem.')['entry']
        path=self.root/'facts.jsonl';before=path.read_bytes()
        again=slf.record_fact(self.root,'Robin plays Fire Emblem.','2026-09-23T10:00:00+00:00: I said so',self.now,'likes','stated',
                              'session:a message:1',human='Robin',statement_origin='model_paraphrase')
        self.assertFalse(again['written']);self.assertEqual(again['entry']['id'],old['id'])
        self.assertEqual(path.read_bytes(),before)

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

class ParaphraseScreenTests(unittest.TestCase):
    """The statement of a reflected fact is the model's wording of an exact
    quote. paraphrase_concerns() screens for obvious changes; it does not verify
    meaning. Each case is (quote, statement, what the screen should find)."""
    NAMES=('Robin','Nova')
    FAITHFUL=[
        ('I play Fire Emblem all the time.','Robin enjoys playing Fire Emblem.'),
        ('My sister is Bee.',"Robin's sister is Bee."),
        ("I don't like olives.",'Robin dislikes olives.'),
        ("I can't stand mornings.",'Robin is not a morning person.'),
        ("I'm 34.",'Robin is 34.'),
        ('I have three cats.','Robin has 3 cats.'),
        ('I came second in the race.','Robin placed 2nd in the race.'),
        ('No, I work as a nurse.','Robin works as a nurse.'),
        ('I might move to Denver next year.','Robin might move to Denver next year.'),
        ('I want you to remind me about it.','Robin wants Nova to remind him about it.'),
        ('I have a 4 GB GTX 1050 Ti.','Robin has a 4 GB GTX 1050 Ti.'),
        ('I turned 34.','Robin is 34.'),
        ('It cost $1,200.','Robin paid $1200 for it.'),
    ]
    CAUGHT=[
        # changed quantities
        ('I have three cats.','Robin has 4 cats.','number'),
        ('My card has 4.5 GB.','Robin has a 45 GB card.','number'),
        ('It was -5 out.','Robin measured +5 degrees.','number'),
        ('I got a raise.','Robin got a 5% raise.','number'),
        # negation
        ('I like olives.','Robin does not like olives.','negation'),
        ("I don't drink coffee.",'Robin drinks coffee.','negation'),
        ('I quit smoking.','Robin smokes.','negation'),
        # names
        ('My sister lives in Raleigh.','Robin\'s sister Alice lives in Raleigh.','name'),
        ('I work at a bank.','Robin works at Larkspur Savings.','name'),
        # dates and times
        ('I have a dentist appointment.','Robin has a dentist appointment tomorrow.','time'),
        ('I went hiking.','Robin goes hiking every weekend.','time'),
        ('I started a new job.','Robin started a new job in March.','name'),
        ('I started a new job.','Robin started a new job on 2026-09-01.','number'),
        # uncertainty
        ('I might move to Denver.','Robin is moving to Denver.','certain'),
        ("I'm thinking about getting a dog.",'Robin is getting a dog.','certain'),
        ('Maybe I will learn piano.','Robin is learning piano.','certain'),
        # misattribution
        ('My sister loves hiking.','Robin loves hiking.','someone else'),
        ('She plays the cello.','Robin plays the cello.','someone else'),
        ('My friend thinks I should quit.','Robin wants to quit.','someone else'),
    ]
    # Known misses. They document what a lexical screen cannot see; a case that
    # starts being caught should move to CAUGHT on purpose, not silently.
    MISSED=[
        ('I love tea.','Robin loves coffee.'),                      # substituted object, no new name
        ('My sister and I went to Paris.','Robin went to Paris alone.'),  # a detail contradicted in prose
        ('I used to live in Ohio.','Robin lives in Ohio.'),        # tense and habit changed
        ('I play Fire Emblem all the time.','Robin is a professional Fire Emblem player.'),  # exaggeration
    ]

    def test_faithful_paraphrases_pass(self):
        for quote,statement in self.FAITHFUL:
            self.assertEqual(slf.paraphrase_concerns(statement,quote,self.NAMES),[],(quote,statement))

    def test_obvious_changes_are_found(self):
        for quote,statement,expected in self.CAUGHT:
            found=slf.paraphrase_concerns(statement,quote,self.NAMES)
            self.assertTrue(any(expected in f for f in found),(quote,statement,found))

    def test_known_limitations_are_stated_not_hidden(self):
        for quote,statement in self.MISSED:
            self.assertEqual(slf.paraphrase_concerns(statement,quote,self.NAMES),[],
                             f'now caught -- move to CAUGHT: {quote!r} / {statement!r}')
        self.assertIn('not otherwise verified',slf.PARAPHRASE_CHECK)

class HeldFactTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name);self.c=cc.Companion(agent='Nova',human='Robin',hermes_root=root/'home',vault=root/'vault',timezone='UTC')
        self.c.home.mkdir(parents=True);self.c.soul_dir.mkdir(parents=True)
        self.c.soul.write_text('A companion.\n'+slf.BEGIN+'\n'+slf.END+'\n')
        self.now=dt.datetime(2026,9,23,11,tzinfo=dt.timezone.utc)
        self.source={'1':{'id':'1','role':'user','content':'I have three cats.','timestamp':self.now.timestamp(),'session_id':'chat'},
                     '2':{'id':'2','role':'user','content':'My sister loves hiking.','timestamp':self.now.timestamp(),'session_id':'chat'}}
    def plan(self):
        plan=empty();plan['facts']=[{'quote_id':'1','category':'other','statement':'Robin has 3 cats.'},
                                    {'quote_id':'2','category':'likes','statement':'Robin loves hiking.'}]
        return plan

    def test_a_mismatched_statement_is_held_not_remembered(self):
        results=reflection.apply_plan(self.c,'daily','2026-09-22',self.plan(),self.source,self.now)
        [fact]=slf.facts(self.c.human_dir)
        self.assertEqual(fact['statement'],'Robin has 3 cats.')
        self.assertEqual(fact['statement_origin'],'model_paraphrase');self.assertIn('not otherwise verified',fact['statement_check'])
        self.assertTrue(fact['evidence'].endswith('I have three cats.'),'the quote stays exact')
        [held]=slf.held_facts(self.c.human_dir)
        self.assertEqual(held['statement'],'Robin loves hiking.');self.assertIn('someone else',held['reasons'][0])
        self.assertTrue(any(r.get('held') for r in results))
        known=slf.fact_statements(self.c.human_dir)['facts']
        self.assertEqual([(f['statement'],f.get('origin')) for f in known],[('Robin has 3 cats.','model_paraphrase')],
                         'a held statement is not offered back as known; a paraphrase says so')

    def test_reapplying_a_plan_does_not_duplicate_held_or_active_rows(self):
        for _ in range(2):reflection.apply_plan(self.c,'daily','2026-09-22',self.plan(),self.source,self.now)
        self.assertEqual(len(slf._read(self.c.human_dir/'facts-held.jsonl')),1)
        self.assertEqual(len(slf._read(self.c.human_dir/'facts.jsonl')),1)

    def test_a_person_accepts_or_dismisses_a_held_statement(self):
        reflection.apply_plan(self.c,'daily','2026-09-22',self.plan(),self.source,self.now)
        [held]=slf.held_facts(self.c.human_dir)
        out=slf.decide_held(self.c.human_dir,held['id'],'accept',self.now,'Robin')
        self.assertTrue(out['written']);self.assertEqual(slf.held_facts(self.c.human_dir),[])
        self.assertIn('Robin loves hiking.',[f['statement'] for f in slf.facts(self.c.human_dir)])
        with self.assertRaises(slf.HeldDecisionConflict):slf.decide_held(self.c.human_dir,held['id'],'dismiss',self.now)

class HeldDecisionProtocolTests(unittest.TestCase):
    """decide_held: one serialized, recoverable decision per held fact."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)/'robin'
        self.now=dt.datetime(2026,9,23,11,tzinfo=dt.timezone.utc)
        self.held=slf.hold_fact(self.root,'Robin loves hiking.','2026-09-20: My sister loves hiking.',self.now,'likes',
                                'session:a message:2',['the quote is about someone else'])['entry']
    def decide(self,decision,**kw):return slf.decide_held(self.root,self.held['id'],decision,self.now,'Robin',**kw)
    def rows(self,kind,name='facts-held.jsonl'):return slf._read(self.root/name,kind=kind)
    def active_from_held(self):return [f for f in slf.facts(self.root) if f.get('statement')=='Robin loves hiking.']

    def test_accept_keeps_the_held_record_and_marks_an_override(self):
        before=self.held
        out=self.decide('accept')
        [fact]=self.active_from_held()
        self.assertEqual(out['fact_id'],fact['id'])
        self.assertEqual(fact['held_decision']['held_id'],self.held['id'])
        self.assertIn('not a machine verification',fact['held_decision']['note'])
        self.assertEqual(fact['statement_origin'],'model_paraphrase')
        [kept]=self.rows('held_fact');self.assertEqual(kept,before,'held row, reasons and exact evidence unchanged')
        [decision]=self.rows('held_fact_decision')
        self.assertEqual((decision['decision'],decision['fact_id'],decision['op_id']),('accept',fact['id'],out['op_id']))

    def test_the_same_decision_repeated_is_idempotent(self):
        first=self.decide('accept');again=self.decide('accept')
        self.assertTrue(again['already_decided']);self.assertEqual(again['fact_id'],first['fact_id'])
        self.assertEqual(len(self.active_from_held()),1)
        self.assertEqual(len(self.rows('held_fact_decision')),1)
        self.assertEqual(self.decide('accept')['op_id'],first['op_id'])

    def test_an_opposite_later_decision_conflicts_before_any_effect(self):
        self.decide('dismiss')
        before=(self.root/'facts-held.jsonl').read_bytes()
        with self.assertRaises(slf.HeldDecisionConflict):self.decide('accept')
        self.assertEqual(self.active_from_held(),[],'dismissed stays dismissed')
        self.assertFalse((self.root/'facts.jsonl').exists())
        self.assertEqual((self.root/'facts-held.jsonl').read_bytes(),before)

    def test_a_retry_after_the_fact_was_retracted_does_not_resurrect_it(self):
        out=self.decide('accept')
        slf.retract_fact(self.root,out['fact_id'],'Not me, my sister',self.now)
        again=self.decide('accept')
        self.assertTrue(again['already_decided']);self.assertEqual(self.active_from_held(),[])
        self.assertEqual(len(self.rows('human_fact','facts.jsonl')),1,'no second row written')

    def test_accepting_when_an_equal_fact_is_active_records_duplicate_of(self):
        equal=slf.record_fact(self.root,'Robin loves hiking.','2026-09-19: I love hiking',self.now,'likes',human='Robin')['entry']
        other=slf.record_fact(self.root,'Robin likes tea.','2026-09-19: tea',self.now,'likes',human='Robin')['entry']
        out=self.decide('accept')
        self.assertEqual(out['duplicate_of'],equal['id']);self.assertNotIn('fact_id',out)
        self.assertEqual({f['id'] for f in slf.facts(self.root)},{equal['id'],other['id']},'nothing retracted to compensate')
        self.assertEqual(self.decide('accept')['duplicate_of'],equal['id'])

    def test_every_interruption_boundary_recovers_to_one_outcome(self):
        from unittest import mock
        real_append,real_record=slf._append,slf.record_fact
        class Crash(Exception):pass
        def crash_on(kind):
            def append(path,row,*a,**k):
                if row.get('kind')==kind:raise Crash(kind)
                return real_append(path,row,*a,**k)
            return mock.patch.object(slf,'_append',append)
        def crash_record(*a,**k):raise Crash('fact')
        boundaries={'before intent':crash_on('held_fact_intent'),
                    'after intent, before fact':mock.patch.object(slf,'record_fact',crash_record),
                    'after fact, before decision':crash_on('held_fact_decision')}
        for name,patch in boundaries.items():
            for decision in ('accept','dismiss'):
                if decision=='dismiss' and name=='after intent, before fact':continue  # dismiss writes no fact
                with self.subTest(boundary=name,decision=decision):
                    self.tmp.cleanup();self.setUp()
                    with patch,self.assertRaises(Crash):self.decide(decision)
                    pending=slf.held_facts(self.root)
                    self.assertEqual(len(pending),1,'still undecided after the crash')
                    if name!='before intent':
                        self.assertEqual(pending[0]['pending_decision'],decision)
                        opposite='dismiss' if decision=='accept' else 'accept'
                        with self.assertRaises(slf.HeldDecisionConflict):self.decide(opposite)
                    out=self.decide(decision)
                    self.assertEqual(out['resumed'],name!='before intent')
                    self.assertEqual(slf.held_facts(self.root),[])
                    self.assertEqual(len(self.active_from_held()),1 if decision=='accept' else 0)
                    self.assertEqual(len(self.rows('human_fact','facts.jsonl')),1 if decision=='accept' else 0)
                    self.assertEqual(len(self.rows('held_fact_intent')),1)
                    [done]=self.rows('held_fact_decision');self.assertEqual(done['op_id'],out['op_id'])

    def test_concurrent_threads_settle_one_decision(self):
        import threading
        barrier=threading.Barrier(8);outcomes=[]
        def run(decision):
            barrier.wait()
            try:outcomes.append(('ok',self.decide(decision)['decision']))
            except slf.HeldDecisionConflict:outcomes.append(('conflict',decision))
        threads=[threading.Thread(target=run,args=('accept' if i%2 else 'dismiss',)) for i in range(8)]
        for t in threads:t.start()
        for t in threads:t.join()
        [winner]={d for kind,d in outcomes if kind=='ok'}
        self.assertEqual(sum(1 for kind,d in outcomes if kind=='conflict'),4,'every opposite decision conflicted')
        self.assertEqual(len(self.rows('held_fact_decision')),1)
        self.assertEqual(len(self.active_from_held()),1 if winner=='accept' else 0)

    def test_concurrent_processes_settle_one_decision(self):
        import subprocess
        script=('import sys,json,datetime as dt;sys.path.insert(0,sys.argv[1]);import companion_self as slf\n'
                'try:print(json.dumps(slf.decide_held(sys.argv[2],sys.argv[3],sys.argv[4],dt.datetime(2026,9,23,11,tzinfo=dt.timezone.utc),"Robin")["decision"]))\n'
                'except slf.HeldDecisionConflict:print(json.dumps("conflict"))')
        procs=[subprocess.Popen([sys.executable,'-c',script,str(ROOT/'kit/scripts'),str(self.root),self.held['id'],
                                 'accept' if i%2 else 'dismiss'],stdout=subprocess.PIPE,text=True) for i in range(6)]
        answers=[json.loads(p.communicate(timeout=60)[0]) for p in procs]
        self.assertTrue(all(p.returncode==0 for p in procs))
        [winner]={a for a in answers if a!='conflict'}
        self.assertEqual(answers.count('conflict'),3)
        self.assertEqual(len(self.rows('held_fact_decision')),1)
        self.assertEqual(len(self.active_from_held()),1 if winner=='accept' else 0)

class ReadOnlyTests(unittest.TestCase):
    """Reading and reporting never change a byte of the history they read."""
    def test_reads_and_reports_leave_history_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);c=cc.Companion(agent='Nova',human='Robin',hermes_root=root/'home',vault=root/'vault',timezone='UTC')
            c.home.mkdir(parents=True);c.soul_dir.mkdir(parents=True);c.soul.write_text('A companion.\n'+slf.BEGIN+'\n'+slf.END+'\n')
            now=dt.datetime(2026,9,23,11,tzinfo=dt.timezone.utc)
            a=slf.record_fact(c.human_dir,'Robin likes tea.','2026-09-20: I like tea',now,'likes',human='Robin')['entry']
            slf.record_fact(c.human_dir,'Robin likes green tea.','2026-09-20: green tea',now,'likes',supersedes=a['id'],human='Robin')
            slf.record_fact(c.human_dir,'Robin has an older 4 GB card for the spare PC.','2026-09-20: card',now,'other',human='Robin')
            slf.record_fact(c.human_dir,'Robin has an older 4 GB card to install in a spare PC.','2026-09-21: card',now,'logistics',human='Robin')
            slf.hold_fact(c.human_dir,'Robin loves hiking.','2026-09-20: My sister loves hiking.',now,'likes','s',['someone else'])
            db=sqlite3.connect(c.home/'state.db')
            db.executescript('CREATE TABLE sessions(id TEXT, source TEXT,user_id TEXT); CREATE TABLE messages(id INTEGER,session_id TEXT,role TEXT,content TEXT,timestamp REAL,active INTEGER,compacted INTEGER,_compressed_summary INTEGER);')
            db.execute("INSERT INTO sessions VALUES ('chat','telegram','robin')")
            db.execute("INSERT INTO messages VALUES (1,'chat','user','hello',?,1,0,0)",(now.timestamp()-3600,));db.commit();db.close()
            snapshot=lambda:{p:p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file() and not p.name.endswith('.lock')}
            before=snapshot()
            slf.facts(c.human_dir);slf.fact_statements(c.human_dir);slf.duplicate_facts(c.human_dir);slf.held_facts(c.human_dir)
            rows,*_=reflection.messages(c,now-dt.timedelta(days=1),now,'robin')
            reflection.context(c,'checkin',now-dt.timedelta(days=1),now,'2026-09-23',rows)
            self.assertEqual(len(rows),1)
            self.assertEqual(snapshot(),before)
