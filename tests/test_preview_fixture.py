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
