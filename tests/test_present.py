"""The assembled present: open loops, ActiveContext, and staying honest with no model.

These three cover the failure the v2 review opened with — a companion opening a
conversation on a Tuesday evening, on Thursday morning, because the job that
refreshes the present had been failing for two days and nothing said so.
"""
import datetime as dt
import json
import pathlib,sys,tempfile,unittest
import unittest.mock
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
import companion_presence as presence
import companion_loops as loops
import companion_active as active
import companion_context as context

TZ=dt.timezone.utc

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'home',vault=root/'vault')
        self.now=dt.datetime(2026,9,10,9,0,tzinfo=TZ)
        presence.update_wardrobe(self.c,[{'id':'pajamas','description':'blue pajamas','use':'sleep'}])

    def state(self,**kw):
        data={'previous_id':None,'outfit':['pajamas'],'location':'home','activity':'reading',
              'mood':'quiet','care':[],'transition':'','text':'Reading.'}
        data.update(kw);return data


class OpenLoopTests(Base):
    def test_a_loop_needs_a_gentle_use_line(self):
        with self.assertRaisesRegex(ValueError,'gentle_use'):
            loops.add(self.c,{'title':'His interview'},self.now)

    def test_closing_a_loop_keeps_it_on_the_record(self):
        made=loops.add(self.c,{'title':'His interview Thursday','gentle_use':'ask on Friday, not before'},self.now)
        ident=made['entry']['id']
        self.assertEqual([l['title'] for l in loops.loops(self.c)],['His interview Thursday'])
        loops.update(self.c,{'id':ident,'status':'closed','note':'He got it.'},self.now)
        self.assertEqual(loops.loops(self.c),[])
        closed=loops.loops(self.c,'closed')
        self.assertEqual(closed[0]['note'],'He got it.')
        self.assertIn('His interview Thursday',(self.c.life/'open-loops.jsonl').read_text())

    def test_a_batch_file_carries_prose_and_stops_at_the_first_bad_entry(self):
        path=pathlib.Path(self.tmp.name)/'loops.json'
        path.write_text(json.dumps([
            {'title':"Alex's mother's visit",'gentle_use':"don't raise it unless he does"},
            {'title':'No guidance here'}]),encoding='utf-8')
        r=loops.batch(self.c,path,self.now)
        self.assertEqual(r['applied'],1);self.assertEqual(r['failed_at'],1)
        self.assertEqual(loops.loops(self.c)[0]['title'],"Alex's mother's visit")

    def test_an_unknown_id_cannot_be_updated(self):
        with self.assertRaisesRegex(ValueError,'unknown loop id'):
            loops.update(self.c,{'id':'loop-nope','status':'closed'},self.now)


class AssemblyTests(Base):
    def test_the_file_is_assembled_from_sources_not_authored(self):
        presence.update(self.c,self.state(wants=['coffee']),self.now)
        loops.add(self.c,{'title':'Porch light','gentle_use':'only if he mentions the house'},self.now)
        text=active.build(self.c,self.now)
        self.assertIn('reading at home',text)
        self.assertIn('coffee',text)
        self.assertIn('### Porch light',text)
        self.assertIn('only if he mentions the house',text)

    def test_an_absent_sensor_produces_no_section_at_all(self):
        presence.update(self.c,self.state(),self.now)
        text=active.build(self.c,self.now)
        for heading in ('## The thread','## Ambient','## Queued to send'):
            self.assertNotIn(heading,text)

    def test_a_sensor_file_appears_once_it_exists(self):
        presence.update(self.c,self.state(),self.now)
        amb=self.c.soul_dir/'ambient';amb.mkdir(parents=True,exist_ok=True)
        (amb/'relationship-thread.md').write_text('Last message from Alex 3 hours ago.',encoding='utf-8')
        (amb/'weather.md').write_text('12C and raining.',encoding='utf-8')
        text=active.build(self.c,self.now)
        self.assertIn('## The thread',text)
        self.assertIn('Last message from Alex',text)
        self.assertIn('### weather',text)

    def test_an_unchanged_assembly_does_not_touch_the_file(self):
        """The hook reads this file's mtime to judge staleness, so a rewrite that
        changes nothing must not make an old present look fresh."""
        presence.update(self.c,self.state(),self.now)
        path=self.c.soul_dir/'ActiveContext.md'
        active.write(self.c,self.now)
        before=path.stat().st_mtime_ns
        self.assertFalse(active.write(self.c,self.now)['written'])
        self.assertEqual(path.stat().st_mtime_ns,before)

    def test_a_state_update_rewrites_it_without_being_asked(self):
        presence.update(self.c,self.state(),self.now)
        self.assertIn('reading at home',(self.c.soul_dir/'ActiveContext.md').read_text())


class AdvanceTests(Base):
    def test_a_recently_confirmed_state_is_left_alone(self):
        presence.update(self.c,self.state(),self.now)
        r=presence.advance(self.c,self.now+dt.timedelta(minutes=5))
        self.assertFalse(r['written'])
        self.assertTrue(presence.current(self.c)['state']['confirmed'])

    def test_an_old_state_is_carried_forward_and_marked_unconfirmed(self):
        presence.update(self.c,self.state(),self.now)
        later=self.now+dt.timedelta(hours=3)
        r=presence.advance(self.c,later)
        self.assertTrue(r['written'])
        now_state=presence.current(self.c)
        self.assertFalse(now_state['state']['confirmed'])
        # Nothing invented: the same scene, said to be unchecked.
        self.assertEqual(now_state['state']['activity'],'reading')
        self.assertIn('no model confirmed it',now_state['text'])
        self.assertEqual(presence.last_confirmed(self.c)['state']['confirmed'],True)

    def test_it_does_nothing_before_any_state_exists(self):
        self.assertFalse(presence.advance(self.c,self.now)['written'])

    def test_the_hook_says_the_present_is_unconfirmed_and_since_when(self):
        presence.update(self.c,self.state(),self.now)
        presence.advance(self.c,self.now+dt.timedelta(hours=3))
        out=context.build(self.c,now=self.now+dt.timedelta(hours=3))
        self.assertIn('UNCONFIRMED',out)
        self.assertIn('09:00',out)
        self.assertIn('reading at home',out)

    def test_a_confirmed_present_carries_no_such_warning(self):
        presence.update(self.c,self.state(),self.now)
        out=context.build(self.c,now=self.now)
        self.assertNotIn('UNCONFIRMED',out)


class ConversationShapeTests(Base):
    """Hermes tells the hook where the conversation is and whether it just began."""
    def payload(self,**extra):
        return {'extra':{'user_message':'hey','**':None,**extra}}

    def test_the_platform_changes_the_note_without_changing_the_facts(self):
        presence.update(self.c,self.state(),self.now)
        tg=context.build(self.c,self.payload(platform='telegram'),now=self.now)
        cli=context.build(self.c,self.payload(platform='cli'),now=self.now)
        self.assertIn('This is Telegram',tg)
        self.assertIn('terminal session',cli)
        for out in (tg,cli):self.assertIn('reading at home',out)

    def test_an_unknown_platform_is_named_rather_than_dropped(self):
        out=context.build(self.c,self.payload(platform='matrix'),now=self.now)
        self.assertIn('matrix',out)

    def test_the_first_turn_is_told_apart_from_a_continuing_one(self):
        first=context.build(self.c,self.payload(platform='cli',is_first_turn=True),now=self.now)
        later=context.build(self.c,self.payload(platform='cli',is_first_turn=False),now=self.now)
        self.assertIn('first turn of a new session',first)
        self.assertIn('already under way',later)
        self.assertNotIn('first turn of a new session',later)

    def test_nothing_is_said_when_hermes_tells_us_nothing(self):
        self.assertNotIn('[This conversation]',context.build(self.c,{'extra':{}},now=self.now))



class WatchdogTests(Base):
    """The failure this exists for: every scheduled job rate-limited for two days
    while nothing anywhere said so."""

    def setUp(self):
        super().setUp()
        import companion_watch
        self.watch=companion_watch
        self.c.cron_active=True
        (self.c.home/'cron').mkdir(parents=True,exist_ok=True)
        (self.c.life).mkdir(parents=True,exist_ok=True)
        (self.c.life/'PRESENCE.md').write_text('x')
        (self.c.soul_dir).mkdir(parents=True,exist_ok=True)
        (self.c.soul_dir/'ActiveContext.md').write_text('x')
        self.c.soul.parent.mkdir(parents=True,exist_ok=True)
        self.c.soul.write_text('x')

    def jobs(self,rows):
        (self.c.home/'cron/jobs.json').write_text(json.dumps({'jobs':rows}))

    def test_a_failing_job_is_named_with_its_error(self):
        self.jobs([{'name':'Nova companion pulse','enabled':True,'last_status':'error',
                    'last_error':'HTTP 429 rate limited\nstack trace'}])
        found=self.watch.check_jobs(self.c,{j['name']:j for j in
                json.loads((self.c.home/'cron/jobs.json').read_text())['jobs']})
        self.assertTrue(any('429' in p and 'companion pulse' in p for p in found))

    def test_an_unconfirmed_present_is_noticed_after_a_few_hours(self):
        presence.update(self.c,self.state(),self.now)
        self.assertEqual(self.watch.check_state(self.c,self.now+dt.timedelta(hours=1)),[])
        late=self.watch.check_state(self.c,self.now+dt.timedelta(hours=9))
        self.assertTrue(late and 'not been confirmed' in late[0])

    def test_a_paused_schedule_is_a_choice_not_a_fault(self):
        self.c.cron_active=False
        self.assertEqual(self.watch.check_state(self.c,self.now+dt.timedelta(days=2)),[])

    def test_it_is_silent_when_healthy_and_says_it_once_when_not(self):
        self.jobs([])
        first=self.watch.run(self.c,self.now)
        self.assertFalse(first['healthy']);self.assertTrue(first['message'])
        again=self.watch.run(self.c,self.now+dt.timedelta(minutes=30))
        self.assertTrue(again['repeat_suppressed']);self.assertEqual(again['message'],'')
        later=self.watch.run(self.c,self.now+dt.timedelta(hours=7))
        self.assertTrue(later['message'])

    def test_the_companion_can_tell_she_is_unwell(self):
        self.jobs([])
        self.watch.run(self.c,self.now)
        health=self.c.soul_dir/'ambient/health.md'
        self.assertTrue(health.exists())
        self.assertIn('not working right now',health.read_text())
        # and the ambient file goes away when the problem does
        self.c.cron_active=False
        with unittest.mock.patch.object(self.watch,'problems',return_value=[]):
            self.watch.run(self.c,self.now+dt.timedelta(hours=8))
        self.assertFalse(health.exists())


if __name__=='__main__':unittest.main()
