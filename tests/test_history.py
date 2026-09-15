"""Cursor history remains complete across equal timestamps and concurrent appends."""
import contextlib,json,sqlite3,unittest
from tests import test_workspace as workspace
from kit.app import runtime

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.f=workspace.WorkspaceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        with contextlib.closing(sqlite3.connect(self.f.c.home/'state.db')) as db, db:
            db.executescript('CREATE TABLE sessions(id TEXT PRIMARY KEY,profile_name TEXT,source TEXT,started_at REAL,title TEXT); CREATE TABLE messages(session_id TEXT,role TEXT,content TEXT,timestamp REAL,_compressed_summary INTEGER,active INTEGER,compacted INTEGER);')
            db.executemany('INSERT INTO sessions VALUES (?,?,?,?,?)',[(f's{i:03}','nova','cli',100,'Conversation '+str(i)) for i in range(115)])
            db.execute("INSERT INTO sessions VALUES ('other','rowan','cli',100,'Private to Rowan')")
            db.executemany('INSERT INTO messages VALUES (?,?,?,?,0,1,0)',[('s000','user',str(i),100) for i in range(425)])
            db.execute("INSERT INTO messages VALUES ('s000','assistant','hidden summary',100,1,1,0)")
            db.execute("INSERT INTO messages VALUES ('s000','assistant','inactive',100,0,0,0)")
    def get(self,path,**params):
        return self.f.client.get('/api'+path,params={'profile':'nova',**params},headers=self.f.headers)
    def test_all_conversations_are_reachable_with_stable_ties(self):
        first=self.get('/sessions').json();self.assertEqual(len(first['sessions']),100)
        second=self.get('/sessions',before=first['next_cursor']).json()
        ids=[row['id'] for row in first['sessions']+second['sessions']]
        self.assertEqual(len(ids),115);self.assertEqual(len(set(ids)),115)
        self.assertIsNone(second['next_cursor']);self.assertNotIn('other',ids)
    def test_messages_do_not_skip_or_repeat_when_new_messages_arrive(self):
        first=self.get('/sessions/s000').json();self.assertEqual(len(first['messages']),200)
        with contextlib.closing(sqlite3.connect(self.f.c.home/'state.db')) as db, db:
            db.execute("INSERT INTO messages VALUES ('s000','user','new message',101,0,1,0)")
        pages=[first];cursor=first['next_cursor']
        while cursor:
            page=self.get('/sessions/s000',before=cursor).json();pages.append(page);cursor=page['next_cursor']
        contents=[r['content'] for page in reversed(pages) for r in page['messages']]
        self.assertEqual(contents,[str(i) for i in range(425)])
    def test_bad_cursor_limits_and_other_profile_are_rejected(self):
        for params in ({'before':'nonsense'},{'limit':0},{'limit':201}):
            self.assertEqual(self.get('/sessions',**params).status_code,400)
        self.assertEqual(self.get('/sessions/other').status_code,400)
        self.assertEqual(self.get('/sessions/s000',before=runtime._encode_cursor(100,'invalid-row-id')).status_code,400)
        self.assertEqual(self.f.client.get('/api/sessions').status_code,401)
    def test_old_saved_session_is_available_outside_first_page(self):
        first=self.get('/sessions').json()
        self.assertNotIn('s000',[r['id'] for r in first['sessions']])
        self.assertEqual(len(self.get('/sessions/s000').json()['messages']),200)

if __name__=='__main__':unittest.main()
