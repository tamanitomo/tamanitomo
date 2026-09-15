"""Regression coverage for sharing, containment, repair, concurrency and portability."""
import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
import companion_platform as cp
import companion_render as render
import companion_rotate as rotate
import companion_self as slf
import companion_peer as peer
import companion_wizard as wiz
from test_cli import run,answers,CORE_JOBS
sys.path.insert(0,str(ROOT))
from kit.cli import common, questions, scaffold

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='companion space ');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.home=self.root/'hermes';self.vault=self.root/'vault'
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=self.home,vault=self.vault,timezone='UTC')

    def test_remove_rejects_traversal_absolute_reserved_and_symlink(self):
        sentinel=self.root/'keep.txt';sentinel.write_text('keep')
        for value in ('../..','..','/tmp','a/b','a\\b','CON','nul','default','root'):
            result=run('--home',str(self.home),'remove',value,'--force','--purge')
            self.assertNotEqual(result.returncode,0,value)
        self.assertEqual(sentinel.read_text(),'keep')
        (self.home/'profiles').mkdir(parents=True)
        try:(self.home/'profiles/escape').symlink_to(self.root,target_is_directory=True)
        except OSError:return  # Windows fallback is tested separately below.
        result=run('--home',str(self.home),'remove','escape','--force','--purge')
        self.assertNotEqual(result.returncode,0)
        self.assertTrue(sentinel.exists())

    def test_symlink_failure_retains_identity_and_single_canonical_location(self):
        self.home.mkdir();original='# Original identity\n';self.c.soul.write_text(original)
        with patch.object(Path,'symlink_to',side_effect=OSError('Privilege not held')):
            scaffold.place_soul(self.c,[],{'move_soul':True})
        self.assertEqual(self.c.soul.read_text(),original)
        self.assertFalse(self.c.soul_in_vault)
        self.assertEqual(self.c.canonical_soul,self.c.soul)
        self.assertFalse((self.vault/'soul/SOUL.md').exists())

    def test_default_answers_are_choice_values_and_booleans_are_strict(self):
        with patch.object(sys.stdin,'isatty',return_value=False):
            self.assertEqual(questions.ask('q',2,[('a','A'),('b','B')]),'b')
        self.assertFalse(wiz.as_bool('false'))
        self.assertFalse(questions.confirm('q',{'confirm':'false'},'confirm'))
        with self.assertRaises(ValueError):wiz.as_bool('maybe')

    def test_json_template_escapes_names_and_backslashes(self):
        c=cc.dataclasses.replace(self.c,agent='Nova "Star" \\ River')
        value=json.loads(render.render_template('routine.json.tmpl',render.mapping_for(c)))
        self.assertIn(c.agent,value['status'])

    def test_native_command_quotes_spaces_without_shell_expansion(self):
        args=[sys.executable,str(self.root/'$data & notes.py'),'--home',str(self.home)]
        if os.name!='nt':self.assertEqual(shlex.split(cp.command(args)),args)
        self.assertEqual(cp.terminal_command(['plain','two words']),"plain 'two words'")

    def test_repair_retries_pending_jobs_without_modifying_identity(self):
        run('--home',str(self.home),'init','--vault',str(self.vault),'--answers',answers(),
            env={'COMPANION_NO_HERMES_CRON':'1'},expect=0)
        original=(self.home/'SOUL.md').read_bytes()
        result=run('--home',str(self.home),'repair')
        self.assertIn(f'{CORE_JOBS} added',result.stdout)
        self.assertEqual(original,(self.home/'SOUL.md').read_bytes())
        self.assertFalse((self.home/'companion-pending-jobs.json').exists())
        run('--home',str(self.home),'repair')
        self.assertEqual(len(json.loads((self.home/'cron/jobs.json').read_text())['jobs']),CORE_JOBS)

    def test_doctor_catches_empty_hook_and_missing_registration(self):
        run('--home',str(self.home),'init','--vault',str(self.vault),'--answers',answers(),expect=0)
        (self.home/'SOUL.md').write_text((self.home/'SOUL.md').read_text().replace('✎ EDIT','done'))
        (self.home/'hooks/companion-context.py').write_text("print('{}')\n")
        self.assertNotEqual(run('--home',str(self.home),'doctor').returncode,0)

    def test_unrelated_hook_is_preserved_and_reported(self):
        self.home.mkdir();config=self.home/'config.yaml'
        config.write_text('hooks:\n  pre_llm_call:\n    - command: /other/inject-continuity.sh\n')
        before=config.read_bytes();report=[]
        scaffold.install_hook(self.c,{},report)
        self.assertEqual(config.read_bytes(),before)
        self.assertIn('unrelated',str(report))

    def test_hook_refuses_cross_profile_context(self):
        run('--home',str(self.home),'init','--vault',str(self.vault),'--answers',answers(),expect=0)
        out=subprocess.check_output([sys.executable,str(self.home/'hooks/companion-context.py')],input='{}',text=True,
            env={**os.environ,'HERMES_HOME':str(self.root/'other'),'PYTHONUTF8':'1'})
        self.assertEqual(json.loads(out),{'context':''})

    def test_fact_evidence_and_confidence_survive_summary_and_recall(self):
        from companion_recall import search
        slf.record_fact(self.c.human_dir,'May enjoy Lisbon','Mentioned wanting to visit',dt.datetime.now(dt.timezone.utc),confidence='inferred')
        self.assertIn('[inferred]',slf.summary(self.c)['human_profile'])
        result=search(self.c,'Lisbon')['results'][0]
        self.assertEqual(result['confidence'],'inferred')
        self.assertEqual(result['evidence'],'Mentioned wanting to visit')

    def test_peer_root_cannot_reach_named_agents_or_overwrite_identity(self):
        with self.assertRaises(ValueError):peer.resolve_in(self.c,'vault/agents/other/private.md')

    def test_parallel_soul_appends_preserve_every_entry_and_unique_backup(self):
        self.home.mkdir();self.c.soul_in_vault=False
        self.c.soul.write_text('# Identity\n\n'+slf.BEGIN+'\n'+slf.END+'\n');self.c.save()
        children=[subprocess.Popen([sys.executable,str(ROOT/'kit/scripts/companion_self.py'),
            '--home',str(self.home),'soul','--append',f'Entry {i}'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env={**os.environ,'PYTHONUTF8':'1'}) for i in range(8)]
        for child in children:
            out,err=child.communicate(timeout=30);self.assertEqual(child.returncode,0,err)
        text=self.c.soul.read_text()
        for i in range(8):self.assertEqual(text.count(f'Entry {i}'),1)
        self.assertEqual(len(list(self.c.soul_backups.glob('SOUL.md.*'))),8)
        self.assertTrue(text.startswith('# Identity\n\n'))

    def test_rotation_retains_concurrent_edits_and_retry_does_not_duplicate_archive(self):
        path=self.root/'Log.md';text='# Log\n\n## 2020-01-01\nold\n';path.write_text(text)
        real_write=rotate.atomic_write
        def concurrent(dest,value):
            real_write(dest,value)
            if dest.parent.name=='archive':path.write_text(text+'\n## 2026-09-09\nnew\n')
        with patch.object(rotate,'atomic_write',side_effect=concurrent):
            with self.assertRaisesRegex(ValueError,'Source changed'):
                rotate.rotate(path,today=dt.date(2026,9,9),apply=True)
        self.assertIn('new',path.read_text())
        rotate.rotate(path,today=dt.date(2026,9,9),apply=True)
        archive=self.root/'archive/Log-2020-01.md'
        self.assertEqual(archive.read_text().count('## 2020-01-01'),1)
        self.assertIn('new',path.read_text())

    def test_windows_default_home_and_terminal_quoting(self):
        import types
        fake_os=types.SimpleNamespace(name='nt',environ={'LOCALAPPDATA':'C:/Users/Example/AppData/Local'})
        with patch.object(cp,'os',fake_os):
            self.assertEqual(str(cp.default_home()).replace('\\','/'),'C:/Users/Example/AppData/Local/hermes')
            native=cp.command(['C:/Program Files/Python/python.exe','C:/My Kit/hook.py'])
            self.assertIn('"C:/Program Files/Python/python.exe"',native)
            terminal=cp.terminal_command(['C:\\Program Files\\Python\\python.exe','C:\\My Kit\\hook.py'])
            self.assertEqual(shlex.split(terminal),['C:/Program Files/Python/python.exe','C:/My Kit/hook.py'])

    def test_doctor_identifies_missing_consent(self):
        run('--home',str(self.home),'init','--vault',str(self.vault),'--answers',answers(),expect=0)
        result=run('--home',str(self.home),'doctor')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('hook consent missing',result.stdout)

    def test_no_color_has_no_ansi_even_for_empty_environment_value(self):
        with patch.dict(os.environ,{'NO_COLOR':''}),patch.object(wiz,'_tty',return_value=True):
            self.assertEqual(wiz.C.cyan('hello'),'hello')

if __name__=='__main__':unittest.main()


class CapParserTests(unittest.TestCase):
    def test_explicit_caps_and_unlimited(self):
        for value,want in [('10',10),('7 a day',7),('7/day',7),('7 times per day',7),('0',0),('no limit',0),('unlimited',0)]:
            self.assertEqual(questions.parse_cap(value),want)
    def test_ambiguous_or_malformed_caps_cannot_enable_unlimited(self):
        for value in ('off','never','none','no',None,False,'7 times x2','7 times -1','1.5','-1','101','１','5 per day 0'):
            with self.subTest(value=value),self.assertRaises(ValueError):questions.parse_cap(value)


class PlaceholderStatusTests(unittest.TestCase):
    def test_explanatory_comments_do_not_make_completed_setup_incomplete(self):
        self.assertEqual(common.edit_count('<!-- Anything skipped is marked ✎ EDIT below. -->\nAll answered.'),0)
        self.assertEqual(common.edit_count('<!-- Intro ✎ EDIT -->\n✎ EDIT: real question'),1)


class VaultIgnorePortabilityTests(unittest.TestCase):
    def test_crlf_and_existing_rules_survive_with_git_portable_paths(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);path=root/'.gitignore';before=b'# personal\r\nkeep-this/\r\n'
            path.write_bytes(before);scaffold.ensure_vault_gitignore(root)
            data=path.read_bytes();self.assertTrue(data.startswith(before))
            self.assertIn(b'.obsidian/\r\n',data);self.assertNotIn(b'\\',data)
            scaffold.ensure_vault_gitignore(root);self.assertEqual(path.read_bytes(),data)
    def test_symlinked_ignore_file_is_not_modified(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);outside=root/'original';outside.write_text('keep')
            try:(root/'.gitignore').symlink_to(outside)
            except OSError:self.skipTest('symlinks unavailable')
            self.assertFalse(scaffold.ensure_vault_gitignore(root));self.assertEqual(outside.read_text(),'keep')
