"""Edge cases that used to take a worker, a plan or a disk down quietly."""
import ast
import datetime as dt
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest
from zoneinfo import ZoneInfo
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
sys.path.insert(0,str(ROOT))
import companion_platform as cp
import companion_plan as plan
import companion_text_provider as provider
import update_release


class VenvDiscoveryTests(unittest.TestCase):
    """`uv venv` writes .venv, and every bridge only ever looked for venv."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
        self.leaf='Scripts/python.exe' if os.name=='nt' else 'bin/python'

    def make(self,folder,name='python'):
        leaf=(f'Scripts/{name}.exe' if os.name=='nt' else f'bin/{name}')
        path=self.root/folder/leaf;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('#!/bin/sh\n');return path

    def test_a_uv_style_checkout_is_found(self):
        modern=self.make('.venv')
        self.assertEqual(cp.venv_executable(self.root),modern)

    def test_a_classic_venv_still_wins_when_both_exist(self):
        classic=self.make('venv');self.make('.venv')
        self.assertEqual(cp.venv_executable(self.root),classic)

    def test_neither_gives_a_stable_path_for_the_error_message(self):
        self.assertEqual(cp.venv_executable(self.root),self.root/'venv'/self.leaf)

    def test_named_entry_points_resolve_too(self):
        hermes=self.make('.venv','hermes')
        self.assertEqual(cp.venv_executable(self.root,'hermes'),hermes)


class BackupRetentionTests(unittest.TestCase):
    """Every update snapshotted the app and nothing ever removed one."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name);self.folder=self.root/'.update-backups'
        self.folder.mkdir()

    def make(self,name,age_seconds):
        d=self.folder/name;d.mkdir();(d/'kit').mkdir();(d/'kit/thing.py').write_text('x')
        os.utime(d,(time.time()-age_seconds,time.time()-age_seconds));return d

    def test_the_newest_three_survive_and_the_rest_go(self):
        for i in range(6):self.make(f'b{i}',i*100)
        removed=update_release._prune_backups(self.root,keep=3)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()),['b0','b1','b2'])
        self.assertEqual(sorted(removed),['b3','b4','b5'])

    def test_this_updates_own_rollback_copy_is_never_the_one_deleted(self):
        newest=self.make('just-taken',0)
        for i in range(1,5):self.make(f'older{i}',i*3600)
        update_release._prune_backups(self.root,keep=3)
        self.assertTrue((newest/'kit/thing.py').is_file())

    def test_tidying_up_never_fails_an_update_that_worked(self):
        self.assertEqual(update_release._prune_backups(pathlib.Path(self.tmp.name)/'gone'),[])


class Companion:
    def __init__(self,life,timezone='America/New_York'):
        self.life=pathlib.Path(life);self.timezone=timezone


class StalePlanTests(unittest.TestCase):
    """A quiet morning left items reading as 'planned' well into the afternoon."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.c=Companion(self.tmp.name)
        self.tz=ZoneInfo('America/New_York')
        self.day=dt.date(2026,9,21)
        plan.settle(self.c,self.day,'an ordinary day',items=[
            {'what':'morning walk','start':'08:00','end':'09:00','kind':'idea'},
            {'what':'lunch at the pier','start':'12:00','end':'13:00','kind':'idea'},
            {'what':'evening reading','start':'21:00','end':'22:00','kind':'idea'}])

    def at(self,hour,minute=0):
        return dt.datetime(2026,9,21,hour,minute,tzinfo=self.tz)

    def items(self,day=None):
        return {x['what']:x for x in plan.read(self.c,day or self.day)['items']}

    def test_windows_that_have_gone_by_are_retired_and_the_rest_left_alone(self):
        stale=plan.reconcile(self.c,self.day,now=self.at(16))
        self.assertEqual(sorted(x['what'] for x in stale),['lunch at the pier','morning walk'])
        items=self.items()
        self.assertEqual(items['morning walk']['status'],'moved')
        self.assertEqual(items['evening reading']['status'],'planned')

    def test_a_retired_item_is_not_a_completed_one(self):
        plan.reconcile(self.c,self.day,now=self.at(16))
        self.assertNotEqual(self.items()['morning walk']['status'],'done')
        self.assertIn('nothing recorded',self.items()['morning walk']['reason'])

    def test_the_thing_she_is_in_the_middle_of_is_not_swept_away(self):
        plan.reconcile(self.c,self.day,now=self.at(12,30))
        self.assertEqual(self.items()['lunch at the pier']['status'],'planned')

    def test_a_second_sweep_changes_nothing(self):
        plan.reconcile(self.c,self.day,now=self.at(16))
        self.assertEqual(plan.reconcile(self.c,self.day,now=self.at(16)),[])

    def test_tomorrow_is_never_late(self):
        self.assertEqual(plan.reconcile(self.c,dt.date(2026,9,22),now=self.at(16)),[])

    def test_a_day_with_no_plan_is_not_an_error(self):
        self.assertEqual(plan.reconcile(self.c,dt.date(2026,1,1),now=self.at(16)),[])


class DisplacementTests(unittest.TestCase):
    """The reason a day bent was recorded and then never read back."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.c=Companion(self.tmp.name);self.day=dt.date(2026,9,21)
        plan.settle(self.c,self.day,'an ordinary day',items=[
            {'what':'a walk','start':'14:00','end':'15:00','kind':'idea'}])
        walk=plan.read(self.c,self.day)['items'][0]
        plan.add(self.c,self.day,{'what':'help with the deploy','start':'14:00','end':'16:00',
                                  'kind':'commitment','reason':'pushed my walk to help with the deploy'},
                 displaces=walk['id'])

    def test_her_own_reason_survives_to_the_prompt(self):
        text=plan.render_displacements(plan.displacements(self.c,self.day))
        self.assertIn('a walk',text)
        self.assertIn('pushed my walk to help with the deploy',text)

    def test_a_day_that_went_as_written_adds_nothing(self):
        quiet=Companion(tempfile.mkdtemp())
        plan.settle(quiet,self.day,'a simple day',
                    items=[{'what':'reading','start':'10:00','end':'11:00','kind':'idea'}])
        self.assertEqual(plan.displacements(quiet,self.day),[])
        self.assertEqual(plan.render_displacements([]),'')


class Message:
    def __init__(self,content):self.content=content;self.reasoning_content=None
class Choice:
    def __init__(self,content):self.message=Message(content);self.finish_reason='stop'
class Reply:
    def __init__(self,content=None,choices=None):
        self.choices=choices if choices is not None else [Choice(content)]
        self.usage=None


class ProviderResilienceTests(unittest.TestCase):
    """A background worker should not die of the retry meant to help it."""
    SCHEMA={'type':'object','required':['mood'],'properties':{'mood':{'type':'string'}}}

    def run_chat(self,replies,**extra):
        calls=[]
        class Completions:
            def create(inner,**request):
                calls.append(request)
                out=replies[min(len(calls)-1,len(replies)-1)]
                if isinstance(out,Exception):raise out
                return out
        class Client:
            chat=type('C',(),{'completions':Completions()})()
        import agent.auxiliary_client as aux
        aux.resolve_provider_client=lambda provider,model:(Client(),model)
        payload={'provider':'p','model':'m','messages':[{'role':'user','content':'hi'}],
                 'response_format':{'type':'json_schema','json_schema':{'schema':self.SCHEMA}}}
        payload.update(extra)
        return provider.chat(payload),calls

    def setUp(self):
        # The bridge resolves its client through Hermes, which is not installed here.
        import types
        agent=sys.modules.setdefault('agent',types.ModuleType('agent'))
        aux=types.ModuleType('agent.auxiliary_client')
        aux.resolve_provider_client=lambda provider,model:(None,model)
        sys.modules['agent.auxiliary_client']=aux;agent.auxiliary_client=aux
        self.addCleanup(sys.modules.pop,'agent.auxiliary_client',None)

    def test_a_failed_correction_keeps_the_answer_already_in_hand(self):
        result,calls=self.run_chat([Reply('{"wrong":1}'),RuntimeError('rate limited')])
        self.assertEqual(len(calls),2)
        self.assertEqual(result['content'],'{"wrong":1}')

    def test_a_correction_that_returns_nothing_is_not_adopted(self):
        result,_=self.run_chat([Reply('{"wrong":1}'),Reply(choices=[])])
        self.assertEqual(result['content'],'{"wrong":1}')

    def test_a_good_correction_is_used(self):
        result,_=self.run_chat([Reply('{"wrong":1}'),Reply('{"mood":"ok"}')])
        self.assertEqual(result['content'],'{"mood":"ok"}')

    def test_no_choices_at_all_says_so_instead_of_an_index_error(self):
        with self.assertRaises(ValueError) as caught:
            self.run_chat([Reply(choices=[])])
        self.assertIn('no choices',str(caught.exception))

    def test_a_reasoning_budget_leaves_room_for_the_answer(self):
        _,calls=self.run_chat([Reply('{"mood":"ok"}')],reasoning_effort='high')
        self.assertGreaterEqual(calls[0]['max_tokens'],8000)
        _,calls=self.run_chat([Reply('{"mood":"ok"}')])
        self.assertEqual(calls[0]['max_tokens'],3600)

    def test_an_explicit_budget_is_still_exactly_honoured(self):
        _,calls=self.run_chat([Reply('{"mood":"ok"}')],reasoning_effort='high',max_tokens=1200)
        self.assertEqual(calls[0]['max_tokens'],1200)


if __name__=='__main__':unittest.main()


class LocalImportShadowTests(unittest.TestCase):
    """A function-local import binds its name for the WHOLE function.

    `_settle_import` read `media` near the top and imported it again further
    down. Python makes the name local to all of the function, so the earlier
    read raised UnboundLocalError and no ComfyUI workflow carrying a negative
    prompt could be imported at all. The shape is invisible on inspection and
    only fires on the path that reaches the earlier line, so it is worth
    checking for across the app rather than fixing the one instance.
    """
    NESTED=(ast.FunctionDef,ast.AsyncFunctionDef,ast.Lambda,ast.ClassDef)

    def own_scope(self,func):
        """Every node belonging to this function, not to one nested inside it."""
        out=[]
        def walk(node,top=False):
            for child in ast.iter_child_nodes(node):
                if isinstance(child,self.NESTED) and not top:continue
                out.append(child);walk(child)
        for stmt in func.body:
            out.append(stmt)
            if not isinstance(stmt,self.NESTED):walk(stmt)
        return out

    def offenders(self,path):
        tree=ast.parse(path.read_text(encoding='utf-8'))
        bad=[]
        for func in ast.walk(tree):
            if not isinstance(func,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
            nodes=self.own_scope(func)
            bound={}
            for node in nodes:
                if isinstance(node,(ast.Import,ast.ImportFrom)):
                    for alias in node.names:
                        bound.setdefault((alias.asname or alias.name).split('.')[0],node.lineno)
            for node in nodes:
                if not (isinstance(node,ast.Name) and isinstance(node.ctx,ast.Load)):continue
                line=bound.get(node.id)
                if line is not None and node.lineno<line:
                    bad.append(f'{path.name}:{node.lineno} reads {node.id} before the local '
                               f'import on line {line} (in {func.name})')
        return bad

    def test_no_function_reads_a_name_it_imports_further_down(self):
        found=[]
        for path in sorted((ROOT/'kit').rglob('*.py')):
            found+=self.offenders(path)
        self.assertEqual(found,[])
