"""The chat feed is one conversation across every channel, and only conversation.

A companion reachable on Telegram, Discord and in this workspace keeps a session
per channel, so the history of talking to it is split across rows that each tell
only part of it. The feed reads across all of them. What it must never pick up is
the companion's own machinery: scheduled runs, sub-agents and tool calls are the
companion working, not the companion talking.
"""
import contextlib,sqlite3,unittest
from tests import test_workspace as workspace
from kit.app import runtime

class FeedTests(unittest.TestCase):
    def setUp(self):
        self.f=workspace.WorkspaceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        with contextlib.closing(sqlite3.connect(self.f.c.home/'state.db')) as db, db:
            db.executescript(
                'CREATE TABLE sessions(id TEXT PRIMARY KEY,profile_name TEXT,source TEXT,started_at REAL,title TEXT);'
                'CREATE TABLE messages(session_id TEXT,role TEXT,content TEXT,timestamp REAL,'
                '_compressed_summary INTEGER,active INTEGER,compacted INTEGER);')
            rows=[('tg','nova','telegram',10,'On the train'),
                  ('dc','nova','discord',20,'With friends'),
                  ('web','nova','desktop',30,'At the desk'),
                  ('job','nova','cron',40,'Nightly reflection'),
                  ('sub','nova','subagent',50,'Tool run'),
                  ('mine','rowan','telegram',60,'Private to Rowan')]
            db.executemany('INSERT INTO sessions VALUES (?,?,?,?,?)',rows)
            # Interleaved in time, so ordering across channels is exercised.
            said=[('tg','user','on the train',11),('tg','assistant','safe travels',12),
                  ('web','user','at the desk',31),('web','assistant','evening',32),
                  ('dc','user','with friends',21),('dc','assistant','have fun',22),
                  ('job','assistant','nightly summary',41),
                  ('sub','assistant','tool output',51),
                  ('mine','user','not yours',61)]
            db.executemany('INSERT INTO messages VALUES (?,?,?,?,0,1,0)',said)
            db.execute("INSERT INTO messages VALUES ('web','assistant','hidden summary',33,1,1,0)")
            db.execute("INSERT INTO messages VALUES ('web','assistant','inactive',34,0,0,0)")
            # Half of a real history looks like this: an assistant row with no
            # text, carrying only the tool call the model decided to make.
            db.execute("INSERT INTO messages VALUES ('web','assistant','',35,0,1,0)")
            db.execute("INSERT INTO messages VALUES ('web','assistant','   ',36,0,1,0)")

    def get(self,path,**params):
        return self.f.client.get('/api'+path,params={'profile':'nova',**params},headers=self.f.headers)

    def test_every_channel_lands_in_one_feed_in_time_order(self):
        rows=self.get('/feed').json()['messages']
        self.assertEqual([r['content'] for r in rows],
                         ['on the train','safe travels','with friends','have fun','at the desk','evening'])
        self.assertEqual([r['source'] for r in rows],
                         ['telegram','telegram','discord','discord','desktop','desktop'])

    def test_the_companions_own_machinery_stays_out(self):
        rows=self.get('/feed').json()['messages']
        self.assertNotIn('cron',{r['source'] for r in rows})
        self.assertNotIn('subagent',{r['source'] for r in rows})
        for hidden in ('nightly summary','tool output','hidden summary','inactive'):
            self.assertNotIn(hidden,[r['content'] for r in rows])

    def test_a_message_with_no_text_is_not_a_message(self):
        """Empty assistant rows carry a tool call and nothing to read. On a real
        history they are about half of everything, and every one of them was
        drawn as an empty bubble."""
        rows=self.get('/feed').json()['messages']
        self.assertTrue(all(row['content'].strip() for row in rows))
        self.assertEqual(len(rows),6)

    def test_another_companions_conversation_is_never_shown(self):
        rows=self.get('/feed').json()['messages']
        self.assertNotIn('not yours',[r['content'] for r in rows])

    def test_paging_back_reaches_the_beginning_without_gaps_or_repeats(self):
        seen=[];cursor=None
        while True:
            page=self.get('/feed',limit=2,**({'before':cursor} if cursor else {})).json()
            seen=[r['content'] for r in page['messages']]+seen
            cursor=page['next_cursor']
            if not cursor:break
        self.assertEqual(seen,['on the train','safe travels','with friends','have fun','at the desk','evening'])

    def test_the_feed_points_at_the_conversation_a_reply_continues(self):
        self.assertEqual(self.get('/feed').json()['session'],'web')

    def test_bad_input_is_refused_and_the_feed_needs_a_token(self):
        for params in ({'before':'nonsense'},{'limit':0},{'limit':201}):
            self.assertEqual(self.get('/feed',**params).status_code,400)
        self.assertEqual(self.get('/feed',before=runtime._encode_cursor(10,'not-a-rowid')).status_code,400)
        self.assertEqual(self.f.client.get('/api/feed').status_code,401)

if __name__=='__main__':unittest.main()
