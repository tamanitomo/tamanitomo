import dataclasses,os,pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'));sys.path.insert(0,str(ROOT))
import companion_config as cc
import companion_local_context as local
import companion_vault_index as vi

def note(root,rel,text='',age=0):
    p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
    t=1_700_000_000-age;os.utime(p,(t,t))
    return p

class VaultIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name);self.vault=root/'vault'
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'home',vault=self.vault,
                            timezone='UTC',context_tokens=272_000)
        note(self.vault,'README.md','# README\n')
        note(self.vault,'projects/garden/plan.md','# Garden plan\n## Beds\n## Watering\n```\n# not a heading\n```\n',age=10)
        note(self.vault,'projects/garden/old.md','# Old\n## Ancient history\n',age=99_999)
        note(self.vault,'.obsidian/workspace.md','# hidden')
        note(self.vault,'agents/sam/diary.md','# Private to Sam')
        note(self.vault,'agents/nova/mine.md','# Mine')
        note(self.vault,'archive/big/one.md');note(self.vault,'image.png')

    def names(self,c=None):
        return {(n['dir'],n['name']) for n in vi.scan(c or self.c)}

    def test_scan_skips_hidden_and_other_agents_private_folders(self):
        found=self.names()
        self.assertIn(('projects/garden','plan'),found)
        self.assertNotIn(('.obsidian','workspace'),found)
        self.assertFalse(any(d.startswith('agents') for d,_ in found),'the root agent maps no profile subtree')
        nova=dataclasses.replace(self.c,profile='nova')
        self.assertIn(('agents/nova','mine'),self.names(nova))
        self.assertNotIn(('agents/sam','diary'),self.names(nova))
        self.assertNotIn(('archive/big','one'),self.names(dataclasses.replace(self.c,vault_index_exclude=['archive'])))

    def test_headings_skip_code_fences_and_a_title_restating_the_name(self):
        by={n['name']:n['headings'] for n in vi.scan(self.c)}
        self.assertEqual(by['plan'],['Garden plan','Beds','Watering'])
        self.assertEqual(by['README'],[])

    def test_every_name_and_section_when_the_budget_allows(self):
        text=vi.render(self.c,vi.scan(self.c),100_000)
        self.assertIn('projects/garden/ (2)',text)
        self.assertIn('- plan: Garden plan · Beds · Watering',text)
        self.assertIn('- old: Old · Ancient history',text)
        self.assertNotIn('Partial for space',text)

    def test_sections_go_to_recent_notes_first_and_the_omission_is_stated(self):
        long=''.join(f'## A long section heading number {i}\n' for i in range(6))
        for i in range(5):note(self.vault,f'history/h{i}.md',long,age=50_000+i)
        notes=vi.scan(self.c)
        full=vi.render(self.c,notes,10**9)
        tight=vi.render(self.c,notes,len(full)-400)
        self.assertLessEqual(len(tight),len(full)-400)
        self.assertIn('- plan: Garden plan · Beds · Watering',tight,'the newest note keeps its sections')
        self.assertIn('\n- h4\n',tight,'the oldest loses them first')
        self.assertIn('sections omitted for',tight)

    def test_small_budgets_fold_folders_and_never_hide_that_they_did(self):
        for i in range(200):note(self.vault,f'archive/big/n{i:03}.md')
        notes=vi.scan(self.c)
        full=vi.render(self.c,notes,10**9)
        text=vi.render(self.c,notes,len(full)-300)
        self.assertLessEqual(len(text),len(full)-300)
        self.assertIn('201 notes not listed for space: show archive/big',text)
        self.assertIn('1 folder(s) folded to a count',text)
        self.assertIn('- plan',text)
        head=len(vi.render(self.c,[],10**9))
        tiny=vi.render(self.c,notes,head+250)
        self.assertIn('Folder note counts only',tiny);self.assertIn('- archive/',tiny)
        self.assertLessEqual(len(tiny),head+250)

    def test_sent_once_per_session_and_again_once_compression_drops_it(self):
        first=vi.for_prompt(self.c,{'extra':{'conversation_history':[]}})
        self.assertTrue(first.startswith(vi.BEGIN) and first.endswith(vi.END))
        carried=[{'role':'user','content':'hi','api_content':'hi\n\n'+first},{'role':'assistant','content':'hey'}]
        self.assertEqual(vi.for_prompt(self.c,{'extra':{'conversation_history':carried}}),'')
        summarised=[{'role':'user','content':'[summary of earlier turns]'}]
        self.assertTrue(vi.for_prompt(self.c,{'extra':{'conversation_history':summarised}}))
        self.assertEqual(vi.for_prompt(dataclasses.replace(self.c,vault_index_tokens=0),{}),'')

    def test_cache_is_reused_while_fresh_and_rebuilt_on_demand(self):
        first=vi.build(self.c)
        note(self.vault,'new-note.md')
        self.assertEqual(vi.build(self.c),first)
        self.assertIn('- new-note',vi.build(self.c,force=True))

    def test_the_local_context_engine_keeps_the_map_when_it_drops_old_snapshots(self):
        snapshot=local.BEGIN+'\n[Nova — continuity]\nstate\n'+local.END
        index=vi.BEGIN+'\nmap\n'+vi.END
        self.assertEqual(local.without_snapshot('hi\n\n'+snapshot+'\n\n'+index,'hi','Nova'),'hi\n\n'+index)

    def test_budget_follows_the_window_and_the_setting(self):
        self.assertEqual(cc.vault_index_cap(272_000),100_000)
        self.assertEqual(cc.vault_index_cap(32_768),int(32_768*0.10)*4)
        self.assertEqual(cc.vault_index_cap(272_000,0),0)
        self.assertEqual(cc.vault_index_cap(272_000,70_000),280_000)
        self.assertEqual(cc.vault_index_cap(32_768,70_000),32_768*2,'never more than half the window')
        with self.assertRaises(ValueError):cc.Companion(vault_index_tokens=-2)
        with self.assertRaises(ValueError):cc.Companion(vault_index_exclude='archive')

    def test_scaffold_recognises_its_hook_under_any_interpreter(self):
        from kit.cli.scaffold import _runs_hook
        hook=pathlib.Path('/home/x/.hermes/hooks/companion-context.py')
        self.assertTrue(_runs_hook('/usr/bin/python3 /home/x/.hermes/hooks/companion-context.py',hook))
        self.assertTrue(_runs_hook('/venv/bin/python "/home/x/.hermes/hooks/companion-context.py"',hook))
        self.assertFalse(_runs_hook('/usr/bin/python3 /home/x/.hermes/hooks/other.py',hook))
        self.assertFalse(_runs_hook('',hook))

if __name__=='__main__':unittest.main()
