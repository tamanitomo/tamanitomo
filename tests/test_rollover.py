"""The nightly fresh conversation: only the human's DM, never mid-conversation, nothing lost."""
import datetime as dt, json, sqlite3, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'kit/scripts')]
import companion_config as cc, companion_rollover as rollover, companion_checkin as checkin


class RolloverTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.c=cc.Companion(agent='Mira',human='Alex',profile='m',vault=root/'v',hermes_root=root/'h',timezone='UTC')
        self.c.home.mkdir(parents=True);self.c.life.mkdir(parents=True);self.c.save()
        con=sqlite3.connect(self.c.home/'state.db')
        con.execute('create table sessions(id text primary key,source text,parent_session_id text,started_at real,ended_at real,end_reason text)')
        con.execute('create table messages(id integer primary key,session_id text,role text,content text,timestamp real)')
        self.now=dt.datetime(2026,9,24,6,0,tzinfo=dt.timezone.utc)
        t=self.now.timestamp()
        con.executemany('insert into sessions values(?,?,?,?,?,?)',[
            ('dm1','telegram',None,t-90000,t-50000,'compression'),('dm2','telegram','dm1',t-50000,None,None),
            ('grp','discord',None,t-90000,None,None)])
        con.execute('insert into messages(session_id,role,content,timestamp) values(?,?,?,?)',('dm2','user','night',t-5*3600))
        con.commit();con.close()
        (self.c.home/'sessions').mkdir()
        (self.c.home/'sessions/sessions.json').write_text(json.dumps({
            'agent:main:telegram:dm:1':{'session_id':'dm1','platform':'telegram'},
            'agent:main:discord:group:9:9':{'session_id':'grp','platform':'discord'}}))
        self.ended=[]

    def run_at(self,now):return rollover.run(self.c,now,ender=lambda c,ids:self.ended.extend(ids))

    def test_ends_the_newest_link_of_the_dm_only(self):
        out=self.run_at(self.now)
        self.assertTrue(out['rolled'])
        self.assertEqual(self.ended,['dm2'])                     # the compression tip, not the group
        self.assertTrue(checkin.read(self.c)['pending'])         # details recorded first
        self.assertTrue((self.c.life/'rollover.jsonl').exists())

    def test_never_mid_conversation(self):
        con=sqlite3.connect(self.c.home/'state.db')
        con.execute('insert into messages(session_id,role,content,timestamp) values(?,?,?,?)',('dm2','user','hi',self.now.timestamp()-600))
        con.commit();con.close()
        out=self.run_at(self.now)
        self.assertFalse(out['rolled']);self.assertIn('minutes ago',out['reason']);self.assertEqual(self.ended,[])

    def test_an_already_fresh_chat_is_left_alone(self):
        con=sqlite3.connect(self.c.home/'state.db');con.execute("update sessions set end_reason='x' where id='dm2'");con.commit();con.close()
        self.assertEqual(self.run_at(self.now)['reason'],'the chat is already fresh')

    def test_scheduled_before_morning_and_voice_rule_reaches_readable_jobs(self):
        import companion_render as cr
        m=cr.mapping_for(cc.Companion(quiet_end='08:00'))
        self.assertEqual(m['ROLLOVER_CRON'],'30 6 * * *')
        for name in ('autonomy','wake','winddown','window','daily','weekly','monthly'):
            text=(ROOT/f'kit/templates/cron/{name}.md.tmpl').read_text()
            self.assertIn('{{VOICE_RULE}}',text,name)
        daily=(ROOT/'kit/templates/cron/daily.md.tmpl').read_text()
        self.assertIn('This is your diary',daily);self.assertIn('never mention records, sessions, logs',daily)


class ThinkingAndDiaryTests(unittest.TestCase):
    def test_setup_hides_model_thinking_unless_already_chosen(self):
        import yaml
        from kit.cli import scaffold
        from kit.cli.common import mapping
        with tempfile.TemporaryDirectory() as tmp:
            c=cc.Companion(agent='Mira',human='Alex',profile='m',vault=Path(tmp)/'v',hermes_root=Path(tmp)/'h',context_mode='fixed')
            c.home.mkdir(parents=True);c.soul_dir.mkdir(parents=True);c.save()
            (c.home/'config.yaml').write_text('model: {}\n')
            scaffold.install_hook(c,mapping(c,{}),[])
            self.assertIs(yaml.safe_load((c.home/'config.yaml').read_text())['display']['show_reasoning'],False)
            (c.home/'config.yaml').write_text('display: {show_reasoning: true}\n')
            scaffold.install_hook(c,mapping(c,{}),[])
            self.assertIs(yaml.safe_load((c.home/'config.yaml').read_text())['display']['show_reasoning'],True)

    def test_the_web_chat_final_reply_drops_thinking(self):
        src=(ROOT/'kit/app/hermes_stream.py').read_text()
        self.assertIn("re.sub(r'<(think|thinking|reasoning)>",src)
        import re
        pat=r'<(think|thinking|reasoning)>[\s\S]*?(</\1>|$)'
        self.assertEqual(re.sub(pat,'','<think>plan it</think>Hey you.',flags=re.I).strip(),'Hey you.')

    def test_the_diary_is_her_day_and_facts_go_elsewhere(self):
        daily=(ROOT/'kit/templates/cron/daily.md.tmpl').read_text()
        self.assertIn('the story of YOUR day',daily)
        self.assertIn('The diary is not where facts about {{HUMAN}} are kept',daily)


if __name__=='__main__':unittest.main()
