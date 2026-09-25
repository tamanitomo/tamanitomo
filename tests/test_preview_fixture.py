"""The synthetic preview workspace stays synthetic and still builds."""
import pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'kit/scripts')]
import companion_self as slf
import preview_fixture

class PreviewFixtureTests(unittest.TestCase):
    def test_seeds_invented_memories_in_a_temporary_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,c=preview_fixture.seed(pathlib.Path(tmp))
            self.assertTrue(str(root).startswith(tmp))
            self.assertEqual(len(slf.facts(c.human_dir)),len(preview_fixture.FACTS),'every seeded fact is active')
            self.assertEqual(len(slf.held_facts(c.human_dir)),1)
            self.assertEqual((c.human,c.agent),('Robin','Nova'))
            from kit.app.server import build
            build(root,token='disposable',state_dir=pathlib.Path(tmp)/'state')

    def test_seeds_a_synthetic_conversation_for_the_chat_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,c=preview_fixture.seed(pathlib.Path(tmp))
            from fastapi.testclient import TestClient
            from kit.app.server import build
            client=TestClient(build(root,token='disposable',state_dir=pathlib.Path(tmp)/'state'))
            body=client.get('/api/chat/snapshot',params={'profile':'nova'},headers={'x-companion-token':'disposable'}).json()
            said=[m['content'] for m in body['messages']]
            self.assertIn('Morning! On the train again.',said);self.assertIn('Back at my desk now.',said)
            self.assertEqual(said.count('hi'),3)
            self.assertFalse([s for s in said if 'must not appear' in s])

    def test_persistent_chat_preview_is_synthetic_and_serves_the_keyed_page(self):
        """--persistent-chat: a second companion and ordinary notes, all in the temporary home;
        the app it builds serves the persistent Chat, and its newest session is one keyed
        sends may resume."""
        with tempfile.TemporaryDirectory() as tmp:
            root,c=preview_fixture.seed(pathlib.Path(tmp))
            rowan=preview_fixture.seed_persistent_chat(root,c)
            for path in (root,c.home,rowan.home,c.vault):self.assertTrue(str(path).startswith(tmp))
            for note in preview_fixture.NOTES:self.assertTrue((c.vault/note).is_file())
            from fastapi.testclient import TestClient
            from kit.app import chat_send_routes as csr
            from kit.app.server import build
            from tests.phase1b_c1 import harness as h
            app=build(root,token='disposable',state_dir=pathlib.Path(tmp)/'state',
                      chat_sends=csr.Options(executor=lambda rt,home:h.fake_executor(home),client=True))
            try:
                client=TestClient(app)
                page=client.get('/').text
                self.assertIn('chat-controller.js',page)
                auth={'x-companion-token':'disposable'}
                feed=client.get('/api/feed',params={'profile':'nova'},headers=auth).json()
                self.assertEqual(feed['session'],'web-evening')
                profiles=[p['id'] for p in client.get('/api/profiles',headers=auth).json()['profiles'] if p['installed']]
                self.assertEqual(sorted(profiles),['nova','rowan'])
            finally:
                app.state.chat_sends.close()
