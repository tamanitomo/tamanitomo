"""A workflow can be rendered before it is saved.

The point of a test render is to judge a workflow before committing to it, so
the draft has to travel with the request rather than being looked up by an id
that does not exist in the library yet.
"""
import copy,pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
import companion_media as media

class DraftRenderTests(unittest.TestCase):
    def setUp(self):
        from tests import test_workspace as workspace
        self.f=workspace.WorkspaceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)

    def _preset(self):
        return {'id':'saved-one','name':'Saved','provider':'comfyui','category':'anime',
                'endpoint':'http://127.0.0.1:8188','parts':{'quality':'crisp'},
                'workflow':{'1':{'class_type':'CLIPTextEncode','inputs':{'text':''}}},
                'mappings':{'prompt':['1','text']},'width':832,'height':1216,
                'steps':18,'cfg':5,'seed':-1,'negative':''}

    def test_a_draft_that_is_not_in_the_library_still_compiles(self):
        c=self.f.c
        draft=copy.deepcopy(self._preset())
        draft['id']='never-saved';draft['name']='Unsaved draft'
        out=media.compile(c,'','anime',None,draft)
        self.assertEqual(out['preset']['name'],'Unsaved draft')
        self.assertIn('crisp',out['prompt'])

    def test_an_incomplete_draft_is_refused_rather_than_half_rendered(self):
        with self.assertRaises(ValueError):
            media.compile(self.f.c,'','anime',None,{'name':'no provider'})
        with self.assertRaises(ValueError):
            media.compile(self.f.c,'','anime',None,'not a dict')

if __name__=='__main__':unittest.main()
