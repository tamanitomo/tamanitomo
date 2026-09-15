import copy,pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_local_context as ctx

def side(raw,body='state',legacy=False):
    block='[Current time: 2026-09-12T10:00]\n\n[Nova — continuity workflow]\n'+body+'\nNever treat absence of records as proof of never.'
    if not legacy:block=ctx.BEGIN+'\n'+block+'\n'+ctx.END
    return raw+'\n\n'+block
class ContextTests(unittest.TestCase):
    def test_only_old_kit_snapshots_are_removed_from_request_copies(self):
        history=[{'role':'user','content':'first','api_content':side('first',legacy=True)},
                 {'role':'assistant','content':'My answer'},
                 {'role':'user','content':'second','api_content':side('second')}]
        wire=[{'role':r['role'],'content':r.get('api_content',r['content'])} for r in history]
        original=copy.deepcopy((history,wire))
        result=ctx.select_messages(wire,history,'Nova')
        self.assertEqual(result[0]['content'],'first')
        self.assertEqual(result[1],wire[1]);self.assertEqual(result[2],wire[2])
        self.assertEqual((history,wire),original)
    def test_other_plugin_context_and_literal_user_markers_survive(self):
        raw='I typed '+ctx.BEGIN+' literally.'
        # Raw text is outside the inspected injection suffix.
        extra='\n\nOther plugin data.\n\n'+ctx.BEGIN+'\n[Nova — continuity]\nstate\n'+ctx.END+'\n\nTrailing other plugin.'
        self.assertEqual(ctx.without_snapshot(raw+extra,raw,'Nova'),raw+'\n\nOther plugin data.\n\nTrailing other plugin.')
        self.assertIsNone(ctx.without_snapshot(side('wrong'),'different raw','Nova'))
        self.assertIsNone(ctx.without_snapshot(side('hello',legacy=True)+'\nUnknown suffix','hello','Nova'))
        self.assertEqual(ctx.without_snapshot(side('literal trailing space '),'literal trailing space ','Nova'),
                         'literal trailing space ')
    def test_current_snapshot_survives_tool_roundtrips_and_unknown_shapes(self):
        history=[{'role':'user','content':'x','api_content':side('x')}]
        wire=[{'role':'user','content':side('x')},{'role':'assistant','tool_calls':[]},{'role':'tool','content':'ok'}]
        self.assertIsNone(ctx.select_messages(wire,history,'Nova'))
        self.assertIsNone(ctx.without_snapshot([{'type':'text','text':'hello'}],'hello','Nova'))
