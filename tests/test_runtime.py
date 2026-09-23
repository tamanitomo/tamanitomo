"""Ported runtime: injection budgets, disclosure, isolation, and read-only guarantees."""
import os,sys,shutil,pathlib,tempfile,hashlib,datetime as dt,unittest
from zoneinfo import ZoneInfo
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc, companion_self as slf, companion_life as life, companion_context as ctx
import companion_recall as rec
import companion_outreach as out
import companion_memory as mem
import companion_rotate as rot
import companion_peer as peer
import companion_prune as prune
import json

TZ=ZoneInfo('America/New_York')
WINDOWS=[4096,8192,16384,32768,65536,131072,272000]

def make(tmp,**kw):
    base=dict(agent='Nova',human='Alex',pronoun_set='she',timezone='America/New_York',
              hermes_root=tmp/'.hermes',vault=tmp/'vault')
    base.update(kw)
    c=cc.Companion(**base)
    c.soul_dir.mkdir(parents=True,exist_ok=True)
    (c.soul_dir/'ActiveContext.md').write_text(
        "## Right now\nAt the desk.\n\n## Active open loops\n"
        "### Porch light\n- waiting on the switch\n### Dentist\n- open since Tuesday\n\n"
        "## Ignore me\nnot injected\n")
    return c

def seed(c,facts=25):
    now=dt.datetime.now(TZ)
    life.record(c.life,'Stayed too long in the bookstore.','bookstore','completed',now,
                agent=c.agent,human=c.human)
    for i in range(facts):
        slf.record_fact(c.human_dir,f'Alex detail {i} recorded at some length',f'said it {i}',
                        now,category='likes')
    slf.record_pref(c.life,'The quiet before he wakes.',now,valence='like',agent=c.agent)
    slf.ask(c.life,'Has Alex ever lived abroad?',now)


class InjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=pathlib.Path(tempfile.mkdtemp());self.c=make(self.tmp);seed(self.c)

    def test_fits_its_budget_at_every_window(self):
        for w in WINDOWS:
            c=make(self.tmp,context_tokens=w)
            out=ctx.build(c,{'extra':{'user_message':'hi'}})
            self.assertLessEqual(len(out),c.budgets()['total'],f'over budget at {w}')

    def test_lookup_tail_survives_at_every_window(self):
        for w in WINDOWS:
            c=make(self.tmp,context_tokens=w)
            out=ctx.build(c,{'extra':{'user_message':'hi'}})
            self.assertIn('proof of never',out,f'tail lost at {w}')

    def test_open_loops_with_nested_subheadings_are_not_lost(self):
        """The live regression: '## Active open loops' whose body is all '###'."""
        out=ctx.build(self.c,{'extra':{'user_message':'hi'}})
        self.assertIn('Porch light',out);self.assertIn('Dentist',out)
        self.assertNotIn('not injected',out)   # stops at the next same-level heading

    def test_overflow_is_disclosed_not_hidden(self):
        """25 recorded facts must never just fail to appear. On a roomy window
        they are trimmed with a count; on a window too small to carry them at all
        the section is named in the omissions line."""
        for w in (4096,8192,32768):
            c=make(self.tmp,context_tokens=w);seed(c)
            out=ctx.build(c,{'extra':{'user_message':'hi'}})
            trimmed='more facts not shown' in out or 'no room in this context' in out
            omitted='Omitted this turn' in out and 'facts' in out.split('Omitted this turn')[1]
            self.assertTrue(trimmed or omitted,f'silent loss at {w}')

    def test_counts_are_always_truthful(self):
        out=ctx.build(self.c,{'extra':{'user_message':'hi'}})
        self.assertIn('25 recorded facts',out)

    def test_recall_only_fires_on_a_history_question(self):
        plain=ctx.build(self.c,{'extra':{'user_message':'what is the weather'}})
        asked=ctx.build(self.c,{'extra':{'user_message':'do you remember when I traveled?'}})
        self.assertNotIn('Personal-history retrieval',plain)
        self.assertIn('Personal-history retrieval',asked)

    def test_build_writes_nothing(self):
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.tmp.rglob('*') if p.is_file()}
        ctx.build(self.c,{'extra':{'user_message':'do you remember paris?'}})
        after={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
               for p in self.tmp.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_malformed_payload_does_not_crash(self):
        for bad in (None,{},{'extra':None},{'extra':{'user_message':None}},'nonsense',[1,2]):
            self.assertTrue(ctx.build(self.c,bad))

    def test_missing_data_degrades_to_a_usable_injection(self):
        bare=make(pathlib.Path(tempfile.mkdtemp()))
        out=ctx.build(bare,{'extra':{'user_message':'hi'}})
        self.assertIn('Nova',out);self.assertIn('No episodes recorded today',out)

    def test_agent_and_human_names_are_not_hardcoded(self):
        # A fresh tree: any Nova/Alex string here would come from the code, not
        # from seeded content.
        c=make(pathlib.Path(tempfile.mkdtemp()),agent='Kit',human='Rowan',pronoun_set='he')
        out=ctx.build(c,{'extra':{'user_message':'hi'}})
        self.assertIn('Kit',out);self.assertIn('Rowan',out)
        self.assertNotIn('Nova',out);self.assertNotIn('Alex',out)
        for banned in ('ExampleAgent','Alex'):self.assertNotIn(banned,out)


class IsolationTests(unittest.TestCase):
    def test_two_agents_cannot_see_each_others_ledgers(self):
        tmp=pathlib.Path(tempfile.mkdtemp())
        root=make(tmp);nova=make(tmp,profile='nova',agent='Nova2')
        seed(root,facts=3)
        self.assertEqual(len(slf.facts(root.human_dir)),3)
        self.assertEqual(len(slf.facts(nova.human_dir)),0)
        out=ctx.build(nova,{'extra':{'user_message':'hi'}})
        self.assertNotIn('Alex detail 0',out)

    def test_recall_scopes_sessions_to_the_owning_profile(self):
        tmp=pathlib.Path(tempfile.mkdtemp())
        root=make(tmp);sub=make(tmp,profile='nova')
        self.assertTrue(root.is_root);self.assertFalse(sub.is_root)
        # no state.db present: must degrade quietly, not raise
        self.assertEqual(rec.search(root,'travel')['status'],'no_evidence_found_in_searched_sources')

    def test_native_default_sessions_are_recalled_without_named_profiles(self):
        import sqlite3
        c=make(pathlib.Path(tempfile.mkdtemp()))
        c.home.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(c.home/'state.db') as db:
            db.executescript("""CREATE TABLE sessions(id TEXT, profile_name TEXT, source TEXT);
                CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,
                content TEXT, timestamp REAL, _compressed_summary INTEGER);
                CREATE VIRTUAL TABLE messages_fts USING fts5(content);""")
            for i,profile in enumerate(('default','other'),1):
                db.execute('INSERT INTO sessions VALUES (?,?,?)',(str(i),profile,'cli'))
                db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?)',
                    (i,str(i),'user','Paris visit '+profile,1,0))
                db.execute('INSERT INTO messages_fts(rowid,content) VALUES (?,?)',
                    (i,'Paris visit '+profile))
        db.close()
        results=rec.search(c,'Paris')['results']
        self.assertEqual([r['source'] for r in results],['hermes:message:1'])

    def test_stopwords_include_both_names(self):
        c=make(pathlib.Path(tempfile.mkdtemp()),agent='Nova',human='Alex')
        got=rec.terms('did Nova ask Alex about Japan',rec.stopwords(c))
        self.assertIn('japan',got)
        self.assertNotIn('nova',got);self.assertNotIn('alex',got)   # names carry no signal


class SoulBlockTests(unittest.TestCase):
    def setUp(self):
        self.tmp=pathlib.Path(tempfile.mkdtemp());self.c=make(self.tmp)
        self.c.home.mkdir(parents=True,exist_ok=True)
        self.c.soul.write_text('# SOUL\n\nWritten by the human.\n\n## Essence\nChosen.\n')

    def test_init_appends_without_altering_existing_text(self):
        before=self.c.soul.read_text()
        r=slf.soul_init(self.c)
        self.assertTrue(r['written']);self.assertTrue(r['appended'])
        after=self.c.soul.read_text()
        self.assertTrue(after.startswith(before.rstrip('\n')))
        self.assertIn('Written by the human.',after)

    def test_writes_only_touch_the_block(self):
        slf.soul_init(self.c)
        head,_,tail=slf._split_soul(self.c.soul)
        slf.soul_write(self.c,'- likes thunderstorms','append')
        slf.soul_write(self.c,'- rewritten','set')
        h2,b2,t2=slf._split_soul(self.c.soul)
        self.assertEqual((h2,t2),(head,tail))
        self.assertEqual(b2.strip(),'- rewritten')

    def test_warning_scales_with_the_model_window(self):
        small=make(self.tmp,context_tokens=8192);big=make(self.tmp,context_tokens=272000)
        self.assertLess(small.soul_warn,big.soul_warn)
        slf.soul_init(self.c)
        r=slf.soul_write(self.c,'x'*(self.c.soul_warn+50),'set')
        self.assertIn('truncates',r['warning'])
        self.assertEqual(len(slf._split_soul(self.c.soul)[1].strip()),self.c.soul_warn+50)

    def test_every_write_is_backed_up(self):
        slf.soul_init(self.c);slf.soul_write(self.c,'- one','append')
        self.assertTrue(list(self.c.soul_backups.glob('SOUL.md.*')))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=pathlib.Path(tempfile.mkdtemp());self.c=make(self.tmp)
        self.now=dt.datetime.now(TZ)

    def test_evidence_is_mandatory(self):
        with self.assertRaises(ValueError):
            slf.record_fact(self.c.human_dir,'Alex loves Paris','',self.now)

    def test_compact_history_pages_cover_the_whole_day_and_disclose_shortening(self):
        start=self.now.replace(hour=12,minute=0,second=0,microsecond=0)
        for i in range(19):
            life.record(self.c.life,str(i)+' '+('x'*500),'reading','in_progress',
                        start+dt.timedelta(seconds=i),event_id=f'episode-{i}')
        day=self.now.date().isoformat()
        first=life.history_page(self.c.life,day,0,8,True)
        second=life.history_page(self.c.life,day,first['next_offset'],8,True)
        last=life.history_page(self.c.life,day,second['next_offset'],8,True)
        self.assertEqual(first['total'],19)
        self.assertEqual([r['id'] for p in (first,second,last) for r in p['episodes']],
                         [f'episode-{i}' for i in range(19)])
        self.assertIsNone(last['next_offset'])
        self.assertTrue(first['episodes'][0]['text_truncated'])
        full=life.history_page(self.c.life,day,0,1)
        self.assertEqual(len(full['episodes'][0]['text']),502)
        digest=life.history_digest(self.c.life,day)
        self.assertEqual([r['offset'] for r in digest['episodes']],list(range(19)))
        self.assertIsNone(digest['next_offset'])
        self.assertLess(len(json.dumps(digest)),22000)
        self.assertIn('shortened excerpts',digest['detail'])

    def test_supersede_retires_without_erasing(self):
        old=slf.record_fact(self.c.human_dir,'works nights','rota',self.now,category='work')['entry']
        slf.record_fact(self.c.human_dir,'works days','corrected me',self.now,
                        category='work',supersedes=old['id'])
        self.assertEqual([f['statement'] for f in slf.facts(self.c.human_dir)],['works days'])
        self.assertIn('works nights',(self.c.human_dir/'facts.jsonl').read_text())

    def test_retract_mistaken_fact_preserves_history_and_is_idempotent(self):
        old=slf.record_fact(self.c.human_dir,'Misclassified agent thought','wrong evidence',self.now)['entry']
        slf.retract_fact(self.c.human_dir,old['id'],'This was not about Alex.',self.now)
        again=slf.retract_fact(self.c.human_dir,old['id'],'This was not about Alex.',self.now)
        self.assertFalse(again['written'])
        self.assertEqual(slf.facts(self.c.human_dir),[])
        self.assertIn('Misclassified agent thought',(self.c.human_dir/'facts.jsonl').read_text())
        with self.assertRaises(ValueError):
            slf.retract_fact(self.c.human_dir,'missing','No such fact.',self.now)

    def test_ledger_cli_reports_partial_failure_to_scheduler(self):
        from unittest.mock import patch
        import contextlib,io
        path=self.tmp/'input.json'
        path.write_text(json.dumps([{'kind':'pref','text':'A quiet room'}, {'kind':'episode'}]))
        with patch.object(sys,'argv',['companion_self.py','ledger','--file',str(path)]), \
             patch.object(cc,'load',return_value=self.c),contextlib.redirect_stdout(io.StringIO()), \
             self.assertRaises(SystemExit) as caught:
            slf.main()
        self.assertEqual(caught.exception.code,1)
        self.assertEqual(len(slf._read(self.c.life/'preferences.jsonl')),1)

    def test_question_lifecycle(self):
        q=slf.ask(self.c.life,'Has Alex lived abroad?',self.now)['entry']
        slf.resolve(self.c.life,q['id'],'asked',self.now)
        slf.resolve(self.c.life,q['id'],'answered',self.now,'Two years in Osaka.')
        done=slf.questions(self.c.life,'answered')[0]
        self.assertEqual(done['answer'],'Two years in Osaka.')
        self.assertEqual(slf.questions(self.c.life,'open'),[])

    def test_episode_plan_is_not_completion(self):
        r=life.record(self.c.life,'Thinking about the pool.','swim','planned',self.now)
        self.assertEqual(r['episode']['status'],'planned')

    def test_episode_retry_is_idempotent(self):
        a=life.record(self.c.life,'same','walk','completed',self.now)
        b=life.record(self.c.life,'same','walk','completed',self.now)
        self.assertTrue(a['written']);self.assertFalse(b['written'])

    def test_a_batch_file_records_prose_no_shell_could_carry(self):
        """The reason the batch exists: apostrophes and newlines reach the ledger
        intact, because they never pass through a shell argument."""
        prose="Alex's mother — she's called \"Bee\" — lives\nin Osaka."
        path=self.tmp/'reflection.json'
        path.write_text(json.dumps({'entries':[
            {'kind':'fact','category':'people','statement':prose,'evidence':"he said so on 2026-09-09"},
            {'kind':'pref','valence':'curious','subject':'Osaka','text':"I want to know what it's like there."},
            {'kind':'ask','text':'What was Osaka like?'}]}),encoding='utf-8')
        r=slf.ledger_batch(self.c,path,self.now)
        self.assertEqual(r['applied'],3);self.assertIsNone(r['failed_at'])
        self.assertEqual(slf.facts(self.c.human_dir)[0]['statement'],prose)
        self.assertEqual(len(slf.questions(self.c.life,'open')),1)

    def test_a_bad_entry_stops_the_batch_and_the_file_can_be_rerun(self):
        path=self.tmp/'reflection.json'
        path.write_text(json.dumps([
            {'kind':'fact','category':'likes','statement':'likes rain','evidence':'said so'},
            {'kind':'fact','category':'likes','statement':'likes snow','evidence':''}]),encoding='utf-8')
        r=slf.ledger_batch(self.c,path,self.now)
        self.assertEqual(r['failed_at'],1);self.assertEqual(r['applied'],1)
        self.assertFalse(r['results'][1]['ok'])
        # Fix the file and re-run: the good entry is not recorded a second time.
        path.write_text(json.dumps([
            {'kind':'fact','category':'likes','statement':'likes rain','evidence':'said so'},
            {'kind':'fact','category':'likes','statement':'likes snow','evidence':'said so too'}]),encoding='utf-8')
        r=slf.ledger_batch(self.c,path,self.now)
        self.assertEqual(r['applied'],2);self.assertFalse(r['results'][0]['written'])
        self.assertEqual(len(slf.facts(self.c.human_dir)),2)

    def test_a_batch_refuses_shapes_it_cannot_read(self):
        path=self.tmp/'reflection.json'
        for body in ('{"entries": {}}','[]','[{"kind":"gossip"}]','["not an object"]'):
            path.write_text(body,encoding='utf-8')
            with self.assertRaises(ValueError):
                r=slf.ledger_batch(self.c,path,self.now)
                if r['failed_at'] is not None:raise ValueError(r['results'][-1]['error'])

    def test_corrupt_lines_are_skipped(self):
        slf.record_fact(self.c.human_dir,'likes rain','said so',self.now)
        with (self.c.human_dir/'facts.jsonl').open('a') as f:f.write('{bad\n\n')
        self.assertEqual(len(slf.facts(self.c.human_dir)),1)

if __name__=='__main__':unittest.main()


class HandoffFreshnessTests(unittest.TestCase):
    """When the model stops running, the context must say the present is old
    rather than presenting it as now.

    The handoff used to be a file a job rewrote, so its mtime was the measure.
    It is rebuilt whenever it is read now, which makes the mtime always a moment
    ago and useless: freshness is the age of the newest state a model actually
    confirmed, which is the thing the label was always really about."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'h',vault=root/'v',
                            timezone='UTC',context_tokens=131072)
        self.c.soul_dir.mkdir(parents=True,exist_ok=True)
        self.c.life.mkdir(parents=True,exist_ok=True)
        self.active=self.c.soul_dir/'ActiveContext.md'
        self.active.write_text('## Right now\n\nMid-way through the roof repair.\n',encoding='utf-8')
        self.now=dt.datetime(2026,9,9,14,0,tzinfo=dt.timezone.utc)

    def age(self,hours):
        """Say when a model last confirmed the present."""
        import companion_presence as presence
        when=self.now-dt.timedelta(hours=hours)
        presence.record(self.c.life,'Mid-way through the roof repair.','roof repair',
                        'in_progress',when,f'confirmed-{hours}',self.c.agent,self.c.human,
                        state={'activity':'roof repair','location':'the roof','outfit':[],
                               'mood':'focused','confirmed':True})

    def handoff_label(self):
        for line in ctx.build(self.c,{},self.now).splitlines():
            if line.startswith('[Current handoff'):return line
        return ''

    def test_a_fresh_handoff_is_stamped_but_not_flagged(self):
        self.age(0.5)
        label=self.handoff_label()
        self.assertIn('confirmed 30 minutes ago',label)
        self.assertNotIn('STALE',label)

    def test_an_old_handoff_says_so_and_defers_to_the_ledger(self):
        self.age(9)
        label=self.handoff_label()
        self.assertIn('9 hours ago',label)
        self.assertIn('STALE',label)
        self.assertIn('past snapshot',label)

    def test_a_fresher_episode_outranks_the_handoff(self):
        self.age(2)
        life.record(self.c.life,'Read on the balcony.','reading','completed',
                    self.now-dt.timedelta(minutes=5))
        out=ctx.build(self.c,{},self.now)
        self.assertIn('more recent than the handoff',out)
        self.assertIn('The episode ledger above is more recent',self.handoff_label())
        # In a window too small to hold both, the older handoff is the one that
        # gives way, and it is named as omitted. (This used to assert the phrase
        # "imagined episodes", which it only ever found in the rules text: a 4k
        # window gives the day's entries no budget at all.)
        small=cc.dataclasses.replace(self.c,context_tokens=4096)
        self.assertRegex(ctx.build(small,{},self.now),r'Omitted this turn[^\]]*Current handoff')

    def test_six_hours_and_future_clock_skew_are_stale(self):
        self.age(6)
        self.assertIn('STALE',self.handoff_label())
        self.age(-1)
        label=self.handoff_label()
        self.assertIn('future timestamp',label);self.assertIn('STALE',label)

    def test_a_handoff_that_cannot_be_built_is_not_reported_as_current(self):
        """There is no 'Right now' to show, so nothing claims one."""
        self.active.unlink()
        self.c.soul_dir.chmod(0o500)
        self.addCleanup(lambda:self.c.soul_dir.chmod(0o700))
        self.assertEqual(self.handoff_label(),'')


class OutreachGateTests(unittest.TestCase):
    """Quiet hours and the daily cap decided in code, with no model involved."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'h',vault=root/'v',
                            timezone='UTC',outreach='free',outreach_per_day=3)
        self.noon=dt.datetime(2026,9,9,12,0,tzinfo=dt.timezone.utc)
        self.night=dt.datetime(2026,9,9,2,0,tzinfo=dt.timezone.utc)

    def test_quiet_hours_wrap_midnight(self):
        self.assertTrue(out.in_quiet_hours(self.c,self.night))
        self.assertFalse(out.in_quiet_hours(self.c,self.noon))
        for hour in (23,0,3,7):
            self.assertTrue(out.in_quiet_hours(self.c,self.noon.replace(hour=hour)),hour)
        for hour in (8,12,22):
            self.assertFalse(out.in_quiet_hours(self.c,self.noon.replace(hour=hour)),hour)

    def test_the_daily_cap_is_counted_not_trusted(self):
        self.assertTrue(out.decide(self.c,self.noon)['allowed'])
        for _ in range(3):out.record(self.c,'hello',self.noon)
        d=out.decide(self.c,self.noon)
        self.assertFalse(d['allowed']);self.assertIn('3 of 3',d['reason'])
        # tomorrow starts clean
        self.assertTrue(out.decide(self.c,self.noon+dt.timedelta(days=1))['allowed'])

    def test_quiet_hours_beat_a_free_policy_but_urgent_passes(self):
        self.assertFalse(out.decide(self.c,self.night)['allowed'])
        self.assertTrue(out.decide(self.c,self.night,urgent=True)['allowed'])
        # urgent never buys past the daily cap
        for _ in range(3):out.record(self.c,'x',self.night)
        self.assertFalse(out.decide(self.c,self.night,urgent=True)['allowed'])

    def test_never_means_never_and_no_limit_means_only_quiet_hours(self):
        quiet=cc.dataclasses.replace(self.c,outreach='never')
        self.assertFalse(out.decide(quiet,self.noon)['allowed'])
        free=cc.dataclasses.replace(self.c,outreach_per_day=0)
        for _ in range(9):out.record(free,'x',self.noon)
        self.assertTrue(out.decide(free,self.noon)['allowed'])
        self.assertFalse(out.decide(free,self.night)['allowed'])

    def test_a_corrupt_ledger_line_does_not_unlock_the_gate(self):
        for _ in range(3):out.record(self.c,'x',self.noon)
        with out.path(self.c).open('a',encoding='utf-8') as f:f.write('{not json\n\n')
        self.assertFalse(out.decide(self.c,self.noon)['allowed'])


    def test_claim_reserves_once_and_refuses_after_cap(self):
        for i in range(3):self.assertTrue(out.claim(self.c,'test',self.noon)['allowed'])
        self.assertFalse(out.claim(self.c,'test',self.noon)['allowed'])
        self.assertEqual(out.sent_today(self.c,self.noon),3)
        self.assertFalse(out.path(self.c).read_bytes().startswith(b'\0'))
        self.assertTrue(out.path(self.c).with_suffix('.jsonl.lock').exists())

    def test_corruption_cannot_create_an_available_slot(self):
        out.path(self.c).parent.mkdir(parents=True,exist_ok=True)
        for content in ('{bad\n','[]\n','{"kind":"outreach","day":"bad"}\n'):
            out.path(self.c).write_text(content)
            self.assertFalse(out.claim(self.c,'test',self.noon)['allowed'])
            self.assertEqual(out.path(self.c).read_text(),content)

    def test_simultaneous_processes_cannot_overbook_the_daily_cap(self):
        import subprocess,json
        c=cc.dataclasses.replace(self.c,quiet_start='00:00',quiet_end='00:00');c.save()
        script=pathlib.Path(out.__file__)
        children=[subprocess.Popen([sys.executable,str(script),'claim','--home',str(c.home)],
                  stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(8)]
        results=[]
        for child in children:
            stdout,stderr=child.communicate(timeout=30)
            self.assertIn(child.returncode,(0,1),stderr);results.append(json.loads(stdout))
        self.assertEqual(sum(r['allowed'] for r in results),3)


class MemoryPressureTests(unittest.TestCase):
    """Hermes stops accepting memories at its cap. The kit has to see it coming."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'h',vault=root/'v',
                            timezone='UTC',context_tokens=8192)
        self.dir=mem.memory_dir(self.c);self.dir.mkdir(parents=True)
        # Pin the caps these tests were written against. They used to come from
        # the library default, so raising that default silently stopped the
        # pressure they exist to create -- a test should say what it is testing.
        (self.c.home/'config.yaml').write_text(
            'memory:\n  memory_char_limit: 2200\n  user_char_limit: 1375\n',encoding='utf-8')

    def fill(self,name,n):
        (self.dir/name).write_text(mem.ENTRY_DELIMITER.join(
            f'- Fact number {i} about an ordinary day, recorded plainly.' for i in range(n)),
            encoding='utf-8')

    def test_status_reports_the_fraction_and_flags_the_warning_line(self):
        self.fill('MEMORY.md',20)
        row=[r for r in mem.status(self.c) if r['file']=='MEMORY.md'][0]
        self.assertFalse(row['over_warn'])
        self.fill('MEMORY.md',900)
        row=[r for r in mem.status(self.c) if r['file']=='MEMORY.md'][0]
        self.assertTrue(row['over_warn'])
        self.assertGreater(row['fraction'],1)

    def test_archiving_moves_the_oldest_and_keeps_every_entry(self):
        self.fill('MEMORY.md',900)
        before=(self.dir/'MEMORY.md').read_text(encoding='utf-8')
        result=mem.archive(self.c,'MEMORY.md',apply=True)
        after=(self.dir/'MEMORY.md').read_text(encoding='utf-8')
        archived=mem.archive_for(self.c,'MEMORY.md').read_text(encoding='utf-8')
        self.assertEqual(result['moved']+result['kept'],900)
        self.assertLess(len(after),len(before))
        self.assertIn('Fact number 899',after)          # newest stays put
        self.assertNotIn('Fact number 0 ',after)        # oldest moved out
        self.assertIn('Fact number 0 ',archived)
        for i in range(900):self.assertIn(f'Fact number {i} ',after+archived)

    def test_a_dry_run_changes_nothing_and_a_second_run_is_a_no_op(self):
        self.fill('MEMORY.md',900)
        before=(self.dir/'MEMORY.md').read_text(encoding='utf-8')
        mem.archive(self.c,'MEMORY.md',apply=False)
        self.assertEqual((self.dir/'MEMORY.md').read_text(encoding='utf-8'),before)
        mem.archive(self.c,'MEMORY.md',apply=True)
        again=mem.archive(self.c,'MEMORY.md',apply=True)
        self.assertEqual(again['moved'],0)

    def test_archives_stay_reachable_through_recall(self):
        self.dir.joinpath('MEMORY.md').write_text(
            mem.ENTRY_DELIMITER.join(['- Alex mentioned the lighthouse at Montauk.']+
            [f'- Filler {i}.' for i in range(900)]),encoding='utf-8')
        mem.archive(self.c,'MEMORY.md',apply=True)
        self.assertNotIn('lighthouse',(self.dir/'MEMORY.md').read_text(encoding='utf-8'))
        hits=rec.search(self.c,'lighthouse Montauk',limit=3)
        self.assertTrue(any('lighthouse' in r['excerpt'] for r in hits['results']))

    def test_native_delimiters_keep_headings_inside_their_entries(self):
        (self.dir/'USER.md').write_text(mem.ENTRY_DELIMITER.join(
            f'## Entry {i}\n\nSomething recorded on an ordinary day, at some length.'
            for i in range(400)),encoding='utf-8')
        result=mem.archive(self.c,'USER.md',apply=True)
        self.assertEqual(result['moved']+result['kept'],400)
        self.assertTrue(mem.archive_for(self.c,'USER.md').read_text(encoding='utf-8').startswith('\n<!-- archived'))


    def test_native_entry_with_headings_and_blank_lines_is_not_split(self):
        text='One entry\n\n## Detail\nparagraph § literal'
        self.assertEqual(mem.entries(text),('',[text]))
        self.assertEqual(mem.entries(text+mem.ENTRY_DELIMITER+'Next')[1],[text,'Next'])

    def test_caps_are_per_file_characters_not_context_budget_or_utf8_bytes(self):
        (self.c.home/'config.yaml').write_text('memory:\n  memory_char_limit: 100\n  user_char_limit: 50\n')
        (self.dir/'MEMORY.md').write_text('é'*80,encoding='utf-8')
        rows={r['file']:r for r in mem.status(self.c)}
        self.assertEqual(rows['MEMORY.md']['chars'],80)
        self.assertEqual(rows['MEMORY.md']['bytes'],160)
        self.assertEqual(rows['USER.md']['cap'],50)
        self.assertTrue(rows['MEMORY.md']['over_warn'])

    def test_interrupted_archive_recovers_without_duplicating_entries(self):
        from unittest.mock import patch
        self.fill('MEMORY.md',100);source=self.dir/'MEMORY.md';before=source.read_text()
        original=mem.atomic_write
        def fail_source(path,text):
            if pathlib.Path(path)==source:raise OSError('simulated source replacement failure')
            return original(path,text)
        with patch.object(mem,'atomic_write',side_effect=fail_source):
            with self.assertRaises(OSError):mem.archive(self.c,'MEMORY.md',apply=True)
        dest=mem.archive_for(self.c,'MEMORY.md');once=dest.read_text()
        self.assertEqual(source.read_text(),before)
        mem.archive(self.c,'MEMORY.md',apply=True)
        self.assertEqual(dest.read_text(),once)
        self.assertFalse(dest.with_suffix('.pending.json').exists())
        self.assertEqual(mem.archive(self.c,'MEMORY.md',apply=True)['moved'],0)

    def test_uncooperative_writer_is_preserved_and_recovery_refuses_conflict(self):
        from unittest.mock import patch
        self.fill('MEMORY.md',100);source=self.dir/'MEMORY.md';before=source.read_text()
        dest=mem.archive_for(self.c,'MEMORY.md');original=mem.atomic_write
        def concurrent_write(path,text):
            result=original(path,text)
            if pathlib.Path(path)==dest:source.write_text(before+mem.ENTRY_DELIMITER+'Concurrent fact')
            return result
        with patch.object(mem,'atomic_write',side_effect=concurrent_write):
            with self.assertRaisesRegex(ValueError,'changed'):mem.archive(self.c,'MEMORY.md',apply=True)
        self.assertIn('Concurrent fact',source.read_text())
        with self.assertRaisesRegex(ValueError,'unfinished'):mem.archive(self.c,'MEMORY.md',apply=True)

    def test_archive_uses_the_native_sidecar_lock_and_preserves_original(self):
        self.fill('MEMORY.md',100);p=self.dir/'MEMORY.md';before=p.read_bytes()
        mem.archive(self.c,'MEMORY.md',apply=True)
        self.assertTrue(p.with_suffix('.md.lock').exists())
        backups=list((mem.archive_dir(self.c)/'originals').glob('*.bak'))
        self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),before)

    def test_invalid_targets_are_rejected_without_changing_data(self):
        self.fill('MEMORY.md',100)
        for target in (0,-1,True):
            with self.assertRaises(ValueError):mem.archive(self.c,'MEMORY.md',keep_chars=target,apply=True)
        with self.assertRaises(ValueError):mem.archive(self.c,'../SOUL.md',apply=True)


class RecallScopeTests(unittest.TestCase):
    """A named profile must never surface another companion's messages, whether
    each profile owns its store or they all share one."""
    SCHEMA="""CREATE TABLE sessions(id TEXT, profile_name TEXT, source TEXT);
        CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,
        content TEXT, timestamp REAL, _compressed_summary INTEGER);
        CREATE VIRTUAL TABLE messages_fts USING fts5(content);"""

    def seed(self,path,rows):
        import sqlite3
        path.parent.mkdir(parents=True,exist_ok=True)
        con=sqlite3.connect(path);con.executescript(self.SCHEMA)
        for i,(profile,text) in enumerate(rows,1):
            con.execute('INSERT INTO sessions VALUES (?,?,?)',(str(i),profile,'cli'))
            con.execute('INSERT INTO messages VALUES (?,?,?,?,?,?)',(i,str(i),'user',text,1,0))
            con.execute('INSERT INTO messages_fts(rowid,content) VALUES (?,?)',(i,text))
        con.commit();con.close()

    def test_rewind_rows_stay_hidden_but_compaction_history_is_recalled(self):
        import sqlite3
        tmp=pathlib.Path(tempfile.mkdtemp());c=make(tmp,profile='nova')
        self.seed(c.home/'state.db',[('nova','Paris active'),('nova','Paris rewound'),('nova','Paris archived')])
        with sqlite3.connect(c.home/'state.db') as con:
            con.execute('ALTER TABLE messages ADD COLUMN active INTEGER DEFAULT 1')
            con.execute('ALTER TABLE messages ADD COLUMN compacted INTEGER DEFAULT 0')
            con.execute('UPDATE messages SET active=0 WHERE id IN (2,3)')
            con.execute('UPDATE messages SET compacted=1 WHERE id=3')
        got=[r['excerpt'] for r in rec.search(c,'Paris')['results']]
        self.assertCountEqual(got,['Paris active','Paris archived'])

    def test_its_own_store_treats_unlabelled_sessions_as_its_own(self):
        tmp=pathlib.Path(tempfile.mkdtemp());c=make(tmp,profile='nova')
        self.seed(c.home/'state.db',[('','Paris unlabelled'),('nova','Paris nova'),
                                     ('rowan','Paris rowan')])
        got=[r['excerpt'] for r in rec.search(c,'Paris')['results']]
        self.assertEqual(len(got),2)
        self.assertFalse(any('rowan' in g for g in got))

    def test_a_shared_store_hides_everything_but_this_profiles_own_name(self):
        tmp=pathlib.Path(tempfile.mkdtemp());c=make(tmp,profile='nova')
        rootdb=pathlib.Path(c.hermes_root)/'state.db'
        self.seed(rootdb,[('','Paris unlabelled'),('default','Paris default'),
                          ('nova','Paris nova'),('rowan','Paris rowan')])
        c.home.mkdir(parents=True,exist_ok=True)
        try:(c.home/'state.db').symlink_to(rootdb)
        except OSError:self.skipTest('symlinks unavailable')
        out=rec.search(c,'Paris')
        got=[r['excerpt'] for r in out['results']]
        self.assertEqual(got,['Paris nova'])
        self.assertIn('shared session store: scoped strictly to this profile',out['warnings'])

    def test_the_root_agent_never_reads_a_named_profile(self):
        tmp=pathlib.Path(tempfile.mkdtemp());c=make(tmp)
        self.seed(c.home/'state.db',[('','Paris unlabelled'),('nova','Paris nova')])
        got=[r['excerpt'] for r in rec.search(c,'Paris')['results']]
        self.assertEqual(got,['Paris unlabelled'])


    def test_a_sibling_shared_store_excludes_unlabelled_messages(self):
        tmp=pathlib.Path(tempfile.mkdtemp());c=make(tmp,profile='nova')
        peer=c.hermes_root/'profiles/other/state.db'
        self.seed(peer,[('','Paris private peer'),('nova','Paris explicit owner')])
        c.home.mkdir(parents=True,exist_ok=True)
        try:(c.home/'state.db').symlink_to(peer)
        except OSError:self.skipTest('symlinks unavailable')
        self.assertEqual([r['excerpt'] for r in rec.search(c,'Paris')['results']],['Paris explicit owner'])

    def test_hard_linked_store_is_also_strict(self):
        import os
        tmp=pathlib.Path(tempfile.mkdtemp());c=make(tmp,profile='nova')
        peer=c.hermes_root/'profiles/other/state.db'
        self.seed(peer,[('default','Paris private peer'),('nova','Paris explicit owner')])
        c.home.mkdir(parents=True,exist_ok=True)
        try:os.link(peer,c.home/'state.db')
        except OSError:self.skipTest('hard links unavailable')
        self.assertEqual([r['excerpt'] for r in rec.search(c,'Paris')['results']],['Paris explicit owner'])

    def test_root_redirected_into_a_profile_does_not_read_its_messages(self):
        tmp=pathlib.Path(tempfile.mkdtemp());c=make(tmp)
        peer=c.hermes_root/'profiles/other/state.db';self.seed(peer,[('default','Paris private peer')])
        try:(c.home/'state.db').symlink_to(peer)
        except OSError:self.skipTest('symlinks unavailable')
        self.assertEqual(rec.search(c,'Paris')['results'],[])


class LifelogRotationTests(unittest.TestCase):
    """The journal is a lifetime record: rotation moves entries, never drops them."""
    def setUp(self):
        self.tmp=pathlib.Path(tempfile.mkdtemp())
        self.today=dt.date(2026,9,9)
        self.path=self.tmp/'Lifelog.md'

    def write(self,days,heading='## {date}'):
        entries=''.join(heading.format(date=(self.today-dt.timedelta(days=d)).isoformat())+
                        f'\n\nEntry from day minus {d}.\n\n' for d in days)
        self.path.write_text('# Lifelog — Nova\n\n'+entries,encoding='utf-8')

    def test_six_months_stay_live_and_older_months_are_filed(self):
        self.write(range(0,400,7))
        report=rot.rotate(self.path,today=self.today,keep_days=180,apply=True)
        live=self.path.read_text(encoding='utf-8')
        archived=''.join(f.read_text(encoding='utf-8') for f in (self.tmp/'archive').glob('*.md'))
        self.assertEqual(report['keep']+report['archive'],report['entries'])
        for d in range(0,400,7):                       # nothing is lost
            self.assertIn(f'day minus {d}.',live+archived)
        self.assertIn(f'day minus 0.',live)            # today stays put
        self.assertNotIn('day minus 399.',live)        # last year does not
        self.assertTrue(sorted(f.name for f in (self.tmp/'archive').glob('*.md'))[0]
                        .startswith('Lifelog-2025-'))

    def test_a_run_inside_the_window_moves_nothing(self):
        self.write(range(0,90,7))
        before=self.path.read_text(encoding='utf-8')
        rot.rotate(self.path,today=self.today,keep_days=180,apply=True)
        self.assertEqual(self.path.read_text(encoding='utf-8'),before)
        self.assertFalse((self.tmp/'archive').exists())

    def test_undated_headings_are_reported_rather_than_filed_by_guess(self):
        # Date parsing edge case: a heading like "## Tuesday, September 8" has no ISO date.
        self.write(range(0,400,7),heading='## Some day in the past')
        report=rot.rotate(self.path,today=self.today,keep_days=180,apply=False)
        self.assertEqual(report['entries'],len(range(0,400,7)))
        self.assertTrue(any('undated' in str(k) for k in report.get('buckets',{})) or
                        report['keep']>0)


class MalformedRoutineTests(unittest.TestCase):
    """One hand-edited routine line must not take the whole injection down."""
    def setUp(self):
        self.tmp=pathlib.Path(tempfile.mkdtemp())
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=self.tmp/'h',vault=self.tmp/'v',
                            timezone='UTC',context_tokens=131072)
        self.c.life.mkdir(parents=True,exist_ok=True)
        self.c.soul_dir.mkdir(parents=True,exist_ok=True)
        self.now=dt.datetime(2026,9,9,10,0,tzinfo=dt.timezone.utc)   # a Wednesday

    def write_routine(self,weekly):
        (self.c.life/'routine.json').write_text(
            json.dumps({'kind':'imagined_routine','weekly':weekly}),encoding='utf-8')

    def test_an_entry_missing_its_hours_is_skipped_not_raised(self):
        self.write_routine([
            {'day':'wednesday','activity':'swim','start':'09:00','end':'11:00'},
            {'day':'wednesday','activity':'broken'},                     # no start/end
            {'day':'wednesday','activity':'bad hours','start':'nine','end':'ten'},
        ])
        got=life.routine(self.c.life,self.now,'Nova')
        self.assertEqual([x['activity'] for x in got['active_suggestions']],['swim'])
        self.assertEqual(sorted(got['malformed_entries']),['bad hours','broken'])

    def test_the_context_hook_still_builds_around_it(self):
        self.write_routine([{'day':'wednesday','activity':'broken'}])
        out=ctx.build(self.c,{},self.now)
        self.assertIn('continuity',out.lower())
        self.assertNotIn('Episode data unavailable',out)

    def test_a_clean_routine_is_unaffected(self):
        self.write_routine([{'day':'wednesday','activity':'swim','start':'09:00','end':'11:00'}])
        got=life.routine(self.c.life,self.now,'Nova')
        self.assertNotIn('malformed_entries',got)


class SecretFilterTests(unittest.TestCase):
    """A peer may read a document about tokens; it may not read a token."""
    def test_words_inside_longer_names_are_not_secrets(self):
        for ok in ('notes/tokenizer-comparison.md','skills/tokens-101.md','monkeys.md',
                   'docs/secretary-notes.md','notes/keyboard-shortcuts.md',
                   'vault/passwordless-ssh-guide.md'):
            self.assertFalse(peer.is_secret(pathlib.Path(ok)),ok)

    def test_actual_secrets_are_still_refused(self):
        for bad in ('.env','profiles/x/.env.local','auth.json','secrets/a.md','tokens/gh.json',
                    'my-secret-note.txt','id_rsa','keys/server.pem','api_key.txt','api-key.txt',
                    'x/credentials','conf/.netrc','ssh/my.key','store/.credentials'):
            self.assertTrue(peer.is_secret(pathlib.Path(bad)),bad)


class HandoffClockBoundaryTests(unittest.TestCase):
    def test_age_uses_elapsed_time_across_both_dst_transitions(self):
        from zoneinfo import ZoneInfo
        tz=ZoneInfo('America/New_York')
        self.assertEqual(ctx.age_phrase(dt.datetime(2026,3,8,1,30,tzinfo=tz),dt.datetime(2026,3,8,3,30,tzinfo=tz)),'60 minutes ago')
        self.assertEqual(ctx.age_phrase(dt.datetime(2026,11,1,1,30,tzinfo=tz,fold=0),dt.datetime(2026,11,1,1,30,tzinfo=tz,fold=1)),'60 minutes ago')
    def test_age_boundaries_and_clock_skew(self):
        now=dt.datetime(2026,9,9,12,tzinfo=dt.timezone.utc)
        for seconds,want in [(0,'just now'),(60,'1 minute ago'),(5399,'89 minutes ago'),(5400,'1 hour ago'),(172800,'2 days ago'),(-61,'future timestamp (check the clock)')]:
            self.assertEqual(ctx.age_phrase(now-dt.timedelta(seconds=seconds),now),want)
        self.assertEqual(ctx.age_phrase(None,now),'age unknown')
    def test_invalid_mtime_is_unknown_instead_of_crashing_the_hook(self):
        from unittest.mock import patch,Mock
        with patch.object(pathlib.Path,'stat',return_value=Mock(st_mtime=float('inf'))):
            self.assertIsNone(ctx.written_at('unused',dt.timezone.utc))

class OutreachDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.c=make(pathlib.Path(tempfile.mkdtemp()),outreach='updates_only',outreach_per_day=1,quiet_start='00:00',quiet_end='00:00')

    def test_send_uses_profile_native_cli_and_reserves_once(self):
        from unittest.mock import patch
        import subprocess
        with patch.object(out.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'{"success":true}','')) as run:
            result=out.send(self.c,'hello')
            self.assertTrue(result['delivered'])
            self.assertEqual(run.call_args.kwargs['env']['HERMES_HOME'],str(self.c.home))
            self.assertEqual(run.call_args.kwargs['input'],'hello')
            self.assertIn('send',run.call_args.args[0])
            self.assertFalse(out.send(self.c,'second')['allowed'])
            self.assertEqual(run.call_count,1)

    def test_failure_does_not_retry_or_release_slot(self):
        from unittest.mock import patch
        import subprocess
        for response in [subprocess.CompletedProcess([],0,'[]',''),subprocess.CompletedProcess([],1,'{}','private error'),subprocess.CompletedProcess([],0,'{"success":true,"skipped":true}','')]:
            c=make(pathlib.Path(tempfile.mkdtemp()),outreach_per_day=1,quiet_start='00:00',quiet_end='00:00')
            with patch.object(out.subprocess,'run',return_value=response) as run:
                self.assertFalse(out.send(c,'hello')['delivered'])
                self.assertFalse(out.send(c,'again')['allowed'])
                self.assertEqual(run.call_count,1)

    def test_empty_or_quiet_message_never_starts_transport(self):
        from unittest.mock import patch
        with patch.object(out.subprocess,'run') as run:
            self.assertFalse(out.send(self.c,'  ')['allowed'])
            self.c.outreach='never'
            self.assertFalse(out.send(self.c,'hello')['allowed'])
            run.assert_not_called()

    def test_transport_timeout_retains_reservation(self):
        from unittest.mock import patch
        import subprocess
        with patch.object(out.subprocess,'run',side_effect=subprocess.TimeoutExpired('hermes',90)) as run:
            result=out.send(self.c,'hello')
            self.assertFalse(result['delivered'])
            self.assertTrue(result['reserved'])
            self.assertFalse(out.send(self.c,'again')['allowed'])
            self.assertEqual(run.call_count,1)

    def test_named_profile_and_explicit_target_are_forwarded_without_shell(self):
        from unittest.mock import patch
        import subprocess
        c=make(pathlib.Path(tempfile.mkdtemp()),profile='rowan',quiet_start='00:00',quiet_end='00:00')
        with patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':'test-parent-token'}), patch.object(out.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'{"success":true}','')) as run:
            self.assertTrue(out.send(c,'literal $(text)',target='telegram:123')['delivered'])
            self.assertEqual(run.call_args.kwargs['env']['HERMES_HOME'],str(c.home))
            self.assertEqual(run.call_args.kwargs['input'],'literal $(text)')
            self.assertNotIn('TELEGRAM_BOT_TOKEN',run.call_args.kwargs['env'])
            self.assertEqual(run.call_args.args[0][-3:],['--to','telegram:123','--json'])
            self.assertFalse(run.call_args.kwargs.get('shell',False))

class LiteralProseTests(unittest.TestCase):
    def test_episode_stdin_preserves_shell_metacharacters(self):
        import subprocess,shlex,shutil
        if os.name=='nt' or not shutil.which('bash'):self.skipTest('native POSIX shell check')
        c=make(pathlib.Path(tempfile.mkdtemp()));c.save()
        prose='I read "A Room of One\'s Own"; $HOME and $(printf expanded) and `printf expanded` stay literal.'
        cmd=shlex.join([sys.executable,str(ROOT/'kit/scripts/companion_life.py'),'--home',str(c.home),'record','--activity','reading','--status','in_progress'])
        result=subprocess.run(['bash','-c',cmd+" <<'COMPANION_EPISODE'\n"+prose+'\nCOMPANION_EPISODE\n'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['episode']['text'],prose)

class ProseFileInputTests(unittest.TestCase):
    def test_episode_file_preserves_literal_prose(self):
        import subprocess
        c=make(pathlib.Path(tempfile.mkdtemp()));c.save()
        p=c.home/'episode text.txt';text='I read "A Room of One\'s Own"; $HOME and `words` stay literal.';p.write_text(text,encoding='utf-8')
        run=subprocess.run([sys.executable,str(ROOT/'kit/scripts/companion_life.py'),'--home',str(c.home),'record','--activity','reading','--status','in_progress','--text-file',str(p)],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout)['episode']['text'],text)
        self.assertEqual(p.read_text(encoding='utf-8'),text)

    def test_message_file_is_read_before_reserving_and_sent_literally(self):
        from unittest.mock import patch
        import subprocess,io
        c=make(pathlib.Path(tempfile.mkdtemp()),quiet_start='00:00',quiet_end='00:00');c.save()
        p=c.home/'message.txt';text='Apostrophe: isn\'t. Literal: $HOME.';p.write_text(text,encoding='utf-8')
        with patch.object(sys,'argv',['outreach','--home',str(c.home),'send','--message-file',str(p)]),patch.object(sys,'stdout',io.StringIO()),patch.object(out.subprocess,'run') as run:
            self.assertEqual(out.main(),0)
            # The command line queues; only the dispatcher delivers.
            run.assert_not_called()
        import companion_outbox as outbox
        queued=[e for e in outbox.fold(c) if e['status']=='queued']
        self.assertEqual([e['body'] for e in queued],[text.strip()])
        self.assertFalse(out.path(c).exists(),'queueing must not use a daily slot')

    def test_missing_message_input_does_not_consume_a_slot(self):
        from unittest.mock import patch
        import io
        c=make(pathlib.Path(tempfile.mkdtemp()));c.save()
        with patch.object(sys,'argv',['outreach','--home',str(c.home),'send','--message-file',str(c.home/'missing.txt')]),patch.object(sys,'stdout',io.StringIO()),patch.object(out.subprocess,'run') as run:
            self.assertEqual(out.main(),1)
            run.assert_not_called()
        self.assertFalse(out.path(c).exists())

class AutomaticMemoryTests(unittest.TestCase):
    def test_hook_archives_before_build_and_keeps_archive_searchable(self):
        import tempfile,subprocess,json,sys,pathlib
        import companion_config as cc
        import companion_memory as memory
        import companion_recall as recall
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);home=root/'home';home.mkdir()
            c=cc.Companion(hermes_root=home,vault=root/'vault');c.save()
            (home/'config.yaml').write_text('memory:\n  memory_char_limit: 1000\n')
            (home/'memories').mkdir()
            entries=['oldmap '+('x'*290),'middle '+('y'*290),'recent '+('z'*290)]
            source=home/'memories/MEMORY.md';source.write_text(memory.ENTRY_DELIMITER.join(entries))
            command=[sys.executable,str(pathlib.Path(memory.__file__).with_name('companion_context.py')),'--home',str(home)]
            first=subprocess.run(command,input='{}',text=True,capture_output=True,check=True)
            self.assertTrue(json.loads(first.stdout)['context'])
            self.assertLess(memory.status(c)[1]['fraction'],.8)
            archive=memory.archive_for(c,'MEMORY.md').read_text()
            self.assertIn(entries[0],archive)
            self.assertIn(entries[-1],source.read_text())
            subprocess.run(command,input='{}',text=True,capture_output=True,check=True)
            self.assertEqual(archive,memory.archive_for(c,'MEMORY.md').read_text())
            self.assertIn('oldmap',json.dumps(recall.search(c,'oldmap')))


class PruneTests(unittest.TestCase):
    """The only two directories the kit ever removes files from."""
    def setUp(self):
        self.tmp=pathlib.Path(tempfile.mkdtemp());self.c=make(self.tmp)
        self.now=dt.datetime.now(dt.timezone.utc)
        self.inputs=self.c.life/'.inputs';self.inputs.mkdir(parents=True)
        self.output=self.c.home/'cron/output';self.output.mkdir(parents=True)

    def aged(self,folder,name,days):
        path=folder/name;path.write_text('x')
        when=(self.now-dt.timedelta(days=days)).timestamp()
        os.utime(path,(when,when));return path

    def test_old_staging_and_cron_output_go_and_recent_files_stay(self):
        for folder in (self.inputs,self.output):
            self.aged(folder,'old.txt',9)
            (folder/'new.txt').write_text('y')
        report=prune.prune(self.c,now=self.now,apply=True)
        self.assertEqual([r['removed'] for r in report],[1,1])
        self.assertEqual([r['kept'] for r in report],[1,1])
        for folder in (self.inputs,self.output):
            self.assertFalse((folder/'old.txt').exists())
            self.assertTrue((folder/'new.txt').exists())

    def test_a_dry_run_removes_nothing(self):
        self.aged(self.inputs,'old.txt',30)
        report=prune.prune(self.c,now=self.now)
        self.assertEqual(report[0]['removed'],1);self.assertFalse(report[0]['applied'])
        self.assertTrue((self.inputs/'old.txt').exists())

    def test_it_can_only_ever_see_those_two_directories(self):
        """No path argument exists, so nothing that matters can be aimed at."""
        paths={pathlib.Path(t[1]) for t in prune.targets(self.c)}
        self.assertEqual(paths,{self.inputs,self.output})
        for keeper in ('Lifelog.md','ActiveContext.md'):
            self.assertFalse(any(str(self.c.soul_dir/keeper).startswith(str(p)) for p in paths))

    def test_missing_directories_are_not_an_error(self):
        shutil.rmtree(self.inputs);shutil.rmtree(self.output)
        self.assertEqual([r['removed'] for r in prune.prune(self.c,now=self.now,apply=True)],[0,0])
        self.assertEqual([r['files'] for r in prune.survey(self.c)],[0,0])


if __name__=='__main__':unittest.main()


class MemoryCapTests(unittest.TestCase):
    """Hermes ships a page and a half of memory. That is a fine default for an
    assistant and nothing at all for somebody who is meant to know you next year."""
    def setUp(self):
        self.tmp=pathlib.Path(tempfile.mkdtemp());self.c=make(self.tmp)
        (self.c.home).mkdir(parents=True,exist_ok=True)
        (self.c.home/'config.yaml').write_text('model:\n  default: test\n',encoding='utf-8')
        self.c.soul.parent.mkdir(parents=True,exist_ok=True)
        self.c.soul.write_text('x'*8000,encoding='utf-8')

    def test_a_bigger_window_earns_a_bigger_memory(self):
        big=mem.recommend_caps(cc.dataclasses.replace(self.c,context_tokens=272_000))
        small=mem.recommend_caps(cc.dataclasses.replace(self.c,context_tokens=8192))
        self.assertGreater(big['caps']['MEMORY.md'],small['caps']['MEMORY.md'])
        self.assertEqual(big['tier'],'large');self.assertEqual(small['tier'],'tiny')

    def test_a_large_soul_raises_the_floor_rather_than_being_squeezed(self):
        self.c.soul.write_text('x'*40_000,encoding='utf-8')
        plan=mem.recommend_caps(cc.dataclasses.replace(self.c,context_tokens=8192))
        self.assertGreaterEqual(plan['caps']['MEMORY.md'],40_000*3)

    def test_the_caps_are_written_where_hermes_reads_them(self):
        plan=mem.recommend_caps(self.c)
        mem.write_caps(self.c,plan['caps'])
        self.assertEqual(mem.caps(self.c),plan['caps'])
        import yaml
        cfg=yaml.safe_load((self.c.home/'config.yaml').read_text())
        self.assertEqual(cfg['model']['default'],'test')   # nothing else disturbed

    def test_it_explains_itself_in_words_a_person_can_check(self):
        plan=mem.recommend_caps(self.c)
        self.assertIn('tokens',plan['reason'])
        self.assertIn('nothing is lost',plan['note'])


if __name__=='__main__':unittest.main()
