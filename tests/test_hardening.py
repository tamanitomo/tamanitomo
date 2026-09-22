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


class QualityTagsTests(unittest.TestCase):
    """A LoRA does nothing until its trigger word is in the positive prompt.

    That word belongs to the companion, not to the workflow: two companions can
    share one lane and each fire her own trigger. So it is stored on her image
    contract and merged into `quality`, which is the box that carries activation
    keywords and style tags.
    """
    def setUp(self):
        sys.path.insert(0,str(ROOT/'kit/scripts'))
        import companion_media
        self.media=companion_media

    def test_her_tags_lead_the_quality_box(self):
        self.assertEqual(self.media.merge_tags('photographic, dr0skait','sharp focus'),
                         'photographic, dr0skait, sharp focus')

    def test_a_trigger_the_lane_repeats_is_not_doubled(self):
        # Asking for a trigger twice pulls the LoRA harder than asking once.
        self.assertEqual(self.media.merge_tags('photographic, dr0skait','dr0skait, sharp focus'),
                         'photographic, dr0skait, sharp focus')

    def test_case_and_padding_do_not_defeat_that(self):
        self.assertEqual(self.media.merge_tags('DR0SKait',' dr0skait ,  soft light'),
                         'DR0SKait, soft light')

    def test_either_side_may_be_empty(self):
        self.assertEqual(self.media.merge_tags('','sharp focus'),'sharp focus')
        self.assertEqual(self.media.merge_tags('photographic',''),'photographic')
        self.assertEqual(self.media.merge_tags('',''),'')

    def test_tags_must_be_a_short_string(self):
        for bad in (123,['a'],'x'*2001):
            with self.assertRaises(ValueError):
                self.media.validate({'version':1,'presets':[],'quality_tags':bad})

    def test_a_companion_with_no_image_file_yet_still_has_the_field(self):
        class Home:
            home=pathlib.Path(tempfile.mkdtemp())
        self.assertEqual(self.media.load(Home()).get('quality_tags'),'')


class ContactRecordTests(unittest.TestCase):
    """Whether anyone was actually there is a fact, not a memory.

    A journal that asks the model to recall whether the human spoke to it will
    fill the silence, because filling silences is what it is for. The session
    record already knows, and a day whose every session came from cron had
    nobody in it.
    """
    def setUp(self):
        sys.path.insert(0,str(ROOT/'kit/scripts'))
        import companion_life
        self.life=companion_life
        self.home=pathlib.Path(tempfile.mkdtemp())

    def profile(self,rows):
        import sqlite3,datetime as dt
        con=sqlite3.connect(self.home/'state.db')
        con.execute('create table sessions (source text, started_at real, title text)')
        for source,when,title in rows:
            con.execute('insert into sessions values (?,?,?)',
                        (source,when.timestamp(),title))
        con.commit();con.close()
        class C:
            home=self.home
            timezone='UTC'
        return C()

    def day(self,hour=12):
        import datetime as dt
        return dt.datetime(2026,9,21,hour,tzinfo=dt.timezone.utc)

    def test_a_day_of_only_cron_had_nobody_in_it(self):
        c=self.profile([('cron',self.day(h),f'job {h}') for h in range(0,23,2)])
        out=self.life.contact(c,'2026-09-21')
        self.assertEqual(out['human_sessions'],0)
        self.assertEqual(out['verdict'],'no recorded contact')
        self.assertEqual(out['titles'],[])

    def test_a_real_conversation_is_reported_with_its_time(self):
        c=self.profile([('cron',self.day(3),'job'),('telegram',self.day(9),'Morning chat')])
        out=self.life.contact(c,'2026-09-21')
        self.assertEqual(out['human_sessions'],1)
        self.assertEqual(out['verdict'],'contact recorded')
        self.assertEqual(out['titles'],['09:00 Morning chat'])

    def test_companions_talking_to_each_other_is_not_the_human(self):
        # Two companions holding a dialogue is not somebody visiting her.
        c=self.profile([('companion-dialogue',self.day(14),'Invite her to swim'),
                        ('subagent',self.day(15),'helper'),('tool',self.day(16),'tool run')])
        self.assertEqual(self.life.contact(c,'2026-09-21')['human_sessions'],0)

    def test_another_day_does_not_bleed_into_this_one(self):
        import datetime as dt
        c=self.profile([('cli',dt.datetime(2026,9,20,9,tzinfo=dt.timezone.utc),'yesterday')])
        self.assertEqual(self.life.contact(c,'2026-09-21')['human_sessions'],0)
        self.assertEqual(self.life.contact(c,'2026-09-20')['human_sessions'],1)

    def test_no_session_record_says_unknown_rather_than_none(self):
        class C:
            home=pathlib.Path(tempfile.mkdtemp())
            timezone='UTC'
        out=self.life.contact(C(),'2026-09-21')
        # "I could not check" must never read as "nobody was there".
        self.assertNotEqual(out['verdict'],'no recorded contact')
        self.assertIn('unknown',out['verdict'])


class MediaCachingTests(unittest.TestCase):
    """A gallery scrolls past the same pictures over and over.

    Everything under /api and /media was stamped `no-store`, which is right for
    a JSON answer and ruinous for a multi-megabyte photograph: the browser was
    forbidden from keeping one even for a second, so every pass re-fetched the
    whole library. On a phone that is the whole library, repeatedly.
    """
    def client(self):
        import tempfile, pathlib as pl
        from fastapi.testclient import TestClient
        from kit.app.server import build
        sys.path.insert(0,str(ROOT))
        return TestClient(build(home=pl.Path(tempfile.mkdtemp())))

    def test_json_is_still_never_stored(self):
        r=self.client().get('/api/overview')
        self.assertEqual(r.headers.get('cache-control'),'no-store')

    def build_home(self):
        """A companion with one picture in its timeline."""
        import tempfile, json, io, pathlib as pl
        from PIL import Image
        sys.path.insert(0,str(ROOT/'kit/scripts'))
        import companion_config as cc
        root=pl.Path(tempfile.mkdtemp())
        home,vault=root/'h',root/'v'
        c=cc.Companion(hermes_root=home,vault=vault,timezone='UTC')
        c.home.mkdir(parents=True,exist_ok=True)
        (home/'companion.json').write_text(json.dumps({'agent':'Probe','vault':str(vault)}))
        images=vault/'image-timeline'/'images'
        images.mkdir(parents=True,exist_ok=True)
        name='a'*24+'.png'
        Image.new('RGB',(8,8),(20,20,20)).save(images/name)
        return home,name

    def test_a_photo_is_kept_and_revalidates_without_resending_it(self):
        from fastapi.testclient import TestClient
        from kit.app.server import build
        sys.path.insert(0,str(ROOT))
        home,name=self.build_home()
        client=TestClient(build(home=home))
        first=client.get(f'/media/timeline/{name}')
        if first.status_code==404:
            self.skipTest('timeline media path not resolvable in this fixture')
        self.assertEqual(first.status_code,200)
        cache=first.headers.get('cache-control','')
        self.assertIn('private',cache)
        self.assertNotIn('no-store',cache)   # the whole point
        self.assertIn('max-age=',cache)
        etag=first.headers.get('etag')
        self.assertTrue(etag)
        again=client.get(f'/media/timeline/{name}',headers={'If-None-Match':etag})
        self.assertEqual(again.status_code,304)
        self.assertEqual(len(again.content),0)  # no image bytes at all


class VisibleOutfitTests(unittest.TestCase):
    """An outfit is a stack; a photograph is of the outside of it.

    Every layer was handed to the image model at once, so a record of jeans
    over briefs came back with the briefs drawn riding out of the jeans -- in
    every picture, because she is wearing underwear in every picture.
    """
    CLOSET = [{'id': 'jeans', 'category': 'day'},
              {'id': 'briefs', 'category': 'underwear'},
              {'id': 'trainers', 'category': 'footwear'},
              {'id': 'pjs', 'category': 'sleep'},
              {'id': 'unknown', 'category': ''}]
    DESC = {'jeans': 'blue jeans', 'briefs': 'dusty rose briefs',
            'trainers': 'white sneakers', 'pjs': 'ivory sleep set',
            'unknown': 'something not in the closet'}

    def setUp(self):
        sys.path.insert(0, str(ROOT / 'kit/scripts'))
        import companion_presence
        self.p = companion_presence

    def worn(self, *ids):
        return {'outfit': [{'id': i, 'description': self.DESC[i]} for i in ids]}

    def shown(self, *ids):
        return self.p.visible_outfit(self.worn(*ids), self.CLOSET)[1]

    def test_a_base_layer_under_clothes_is_not_in_the_picture(self):
        self.assertEqual(self.shown('jeans', 'briefs', 'trainers'),
                         'blue jeans, white sneakers')

    def test_it_is_in_the_picture_when_nothing_covers_it(self):
        self.assertEqual(self.shown('briefs'), 'dusty rose briefs')

    def test_shoes_do_not_count_as_covering_it(self):
        self.assertEqual(self.shown('briefs', 'trainers'),
                         'dusty rose briefs, white sneakers')

    def test_pyjamas_cover_it_too(self):
        self.assertEqual(self.shown('pjs', 'briefs'), 'ivory sleep set')

    def test_an_uncategorised_garment_counts_as_covering(self):
        # The bias is deliberate: leaving out underwear that is showing makes a
        # picture slightly wrong; adding underwear that is not makes one nobody
        # asked for.
        self.assertEqual(self.shown('unknown', 'briefs'),
                         'something not in the closet')

    def test_the_undressed_and_towel_states_are_untouched(self):
        self.assertEqual(self.p.visible_outfit({'outfit': []}, self.CLOSET), ('undressed', ''))
        towel = {'outfit': [{'id': 'towel', 'description': 'wrapped in a bath towel'}]}
        kind, text = self.p.visible_outfit(towel, self.CLOSET)
        self.assertEqual(kind, 'towel')
        self.assertEqual(text, 'wrapped in a bath towel')

    def test_without_a_closet_it_describes_everything_rather_than_failing(self):
        """A known limit, stated rather than discovered.

        Which item is a base layer is a fact held in the wardrobe, not on the
        worn item, so with no wardrobe to consult there is no signal and every
        layer is described -- the old behaviour. A render is never failed over
        it. If this ever matters, the fix is to carry the category onto the
        worn item when the outfit is recorded, not to guess from the words.
        """
        text = self.p.visible_outfit(self.worn('jeans', 'briefs'), ())[1]
        self.assertIn('blue jeans', text)
        self.assertIn('dusty rose briefs', text)
