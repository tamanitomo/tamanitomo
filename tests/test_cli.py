"""CLI lifecycle: init, add, remove, upgrade, doctor — and containment."""
import sys,os,re,json,shutil,pathlib,tempfile,subprocess,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
CLI=[sys.executable,str(ROOT/'bin/companion')]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
sys.path.insert(0,str(ROOT))
from kit.cli import doctor, questions, settings

BASE={"agent":"Nova","pronoun_set":"she","human":"Alex","human_pronoun_set":"he",
      "persona":"sharp","boundary":"non-sexual","image_mode":"codex",
      "image_style":"anime-modern","outreach":"free","timezone":"America/New_York",
      "context_tokens":131072,"cron_active":True}

def run(*args,expect=None,env=None):
    # Most tests take the direct-store path: six `hermes cron create` subprocesses
    # per install makes the suite unusable. Delegation itself is covered by
    # HermesCronTests below.
    e={**os.environ,'COMPANION_NO_HERMES_CRON':'0','PYTHONUTF8':'1',
       'COMPANION_HERMES_COMMAND':json.dumps([sys.executable,str(ROOT/'tests/fake_hermes.py')])}
    if env:e.update(env)
    if 'init' in args:
        home=pathlib.Path(args[args.index('--home')+1]);home.mkdir(parents=True,exist_ok=True)
        config=home/'config.yaml'
        if not config.exists():config.write_text('model:\n  default: test-model\n  provider: test-provider\n',encoding='utf-8')
    r=subprocess.run(CLI+list(args),capture_output=True,text=True,timeout=300,env=e,stdin=subprocess.DEVNULL)
    if expect is not None:
        assert r.returncode==expect,f'exit {r.returncode}: {r.stdout}{r.stderr}'
    return r


def core_job_count():
    """How many jobs a default install gets, read from the manifest rather than
    written down here, so adding one does not mean editing a dozen assertions."""
    manifest=json.loads((ROOT/'kit/templates/cron/manifest.json').read_text())
    return len([s for s in manifest['jobs'] if not s.get('optional')])
CORE_JOBS=core_job_count()

def scripted_job_names(agent='Nova'):
    manifest=json.loads((ROOT/'kit/templates/cron/manifest.json').read_text())
    return {s['name'].replace('{{AGENT}}',agent) for s in manifest['jobs'] if s.get('no_agent')}

def manifest_toolsets_for(job_name,agent='Nova'):
    manifest=json.loads((ROOT/'kit/templates/cron/manifest.json').read_text())
    for spec in manifest['jobs']:
        if spec['name'].replace('{{AGENT}}',agent)==job_name:return spec.get('toolsets') or []
    return []

def answers(**kw):
    d=dict(BASE);d.update(kw);return json.dumps(d)

class ContainmentTests(unittest.TestCase):
    """The incident this guards against: init resolved to the real ~/.hermes and
    wrote six cron jobs plus a SOUL block into a live install."""

    def test_init_writes_nothing_outside_the_home_and_vault_it_was_given(self):
        sb=pathlib.Path(tempfile.mkdtemp())
        home=sb/'.hermes';vault=sb/'vault'
        # Use a decoy default installation. A live gateway can legitimately add
        # SQLite WAL files during this test, making a real-home snapshot flaky.
        decoy_user=sb/'unselected-user';real=decoy_user/'.hermes'
        real.mkdir(parents=True);(real/'sentinel').write_text('untouched')
        before={str(p.relative_to(real)):p.read_bytes() for p in real.rglob('*') if p.is_file()}
        run('--home',str(home),'init','--answers',answers(vault=str(vault)),expect=0,
            env={'HOME':str(decoy_user),'USERPROFILE':str(decoy_user),'HERMES_HOME':str(real),
                 'LOCALAPPDATA':str(decoy_user/'AppData/Local')})
        self.assertTrue((home/'companion.json').exists())
        self.assertTrue((vault/'companion-life/PROTOCOL.md').exists())
        after={str(p.relative_to(real)):p.read_bytes() for p in real.rglob('*') if p.is_file()}
        self.assertEqual(before,after,'init touched the real Hermes home')

    def test_home_is_accepted_after_the_subcommand_too(self):
        """The natural first attempt. It used to fail with `unrecognized arguments`."""
        sb=pathlib.Path(tempfile.mkdtemp())
        home=sb/'.hermes'
        run('init','--home',str(home),'--answers',answers(vault=str(sb/'v')),expect=0)
        self.assertTrue((home/'companion.json').exists())
        r=run('doctor','--home',str(home))
        self.assertNotIn('unrecognized arguments',r.stdout+r.stderr)

    def test_home_asked_for_is_home_used(self):
        sb=pathlib.Path(tempfile.mkdtemp())
        home=sb/'nested/deep/.hermes'
        run('--home',str(home),'init','--answers',answers(vault=str(sb/'v')),expect=0)
        cfg=json.loads((home/'companion.json').read_text())
        self.assertEqual(cfg['hermes_root'],str(home))


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.sb=pathlib.Path(tempfile.mkdtemp())
        self.home=self.sb/'.hermes';self.vault=self.sb/'vault'
        run('--home',str(self.home),'init','--answers',answers(vault=str(self.vault)),expect=0)

    def test_init_installs_the_full_job_set(self):
        jobs=json.loads((self.home/'cron/jobs.json').read_text())['jobs']
        self.assertEqual(len(jobs),CORE_JOBS)
        for j in jobs:
            self.assertTrue(j['enabled']);self.assertIn('Nova',j['name'])
            self.assertNotIn('{{',j['prompt'])

    def test_repair_adds_memory_check_once_without_replacing_custom_prompt(self):
        path=self.home/'cron/jobs.json';data=json.loads(path.read_text())
        original=data['jobs'][0]['id']
        data['jobs'][0]['prompt']='My custom routine. Keep this text.'
        path.write_text(json.dumps(data))
        run('--home',str(self.home),'repair')
        run('--home',str(self.home),'repair')
        jobs=json.loads(path.read_text())['jobs']
        self.assertEqual(len(jobs),CORE_JOBS)
        job=next(j for j in jobs if j['id']==original)
        self.assertEqual(job['prompt'].count('MEMORY CHECK:'),1)
        self.assertTrue(job['prompt'].endswith('My custom routine. Keep this text.'))

    def test_chat_history_and_checklist_use_the_exact_selected_home(self):
        for tail in [('chat',),('schedule','history')]:
            result=run('--home',str(self.home),*tail,expect=0)
            self.assertIn('Hermes home: '+str(self.home),result.stdout)
        todo=(self.home/'COMPANION-TODO.md').read_text()
        self.assertIn('schedule history',todo)
        self.assertIn(str(self.home)+' chat',todo)
        self.assertNotIn('Six sections are marked',todo)

    def test_timeline_opt_in_adds_two_jobs_and_opt_out_preserves_cleanup(self):
        run('--home',str(self.home),'timeline','on',expect=0)
        jobs=json.loads((self.home/'cron/jobs.json').read_text())['jobs']
        self.assertEqual(len(jobs),CORE_JOBS+2)
        cleanup=next(j for j in jobs if j['name'].endswith('timeline cleanup'))
        self.assertTrue(cleanup['no_agent']);self.assertTrue(cleanup['enabled'])
        self.assertTrue((self.home/'scripts'/cleanup['script']).exists())
        run('--home',str(self.home),'timeline','off',expect=0)
        jobs=json.loads((self.home/'cron/jobs.json').read_text())['jobs']
        self.assertFalse(next(j for j in jobs if j['name']=='Nova image timeline')['enabled'])
        self.assertTrue(next(j for j in jobs if j['name'].endswith('timeline cleanup'))['enabled'])
        run('--home',str(self.home),'timeline','on',expect=0)
        jobs=json.loads((self.home/'cron/jobs.json').read_text())['jobs']
        self.assertEqual(len(jobs),CORE_JOBS+2)
        self.assertTrue(next(j for j in jobs if j['name']=='Nova image timeline')['enabled'])
        run('--home',str(self.home),'schedule','paused',expect=0)
        jobs=json.loads((self.home/'cron/jobs.json').read_text())['jobs']
        self.assertTrue(next(j for j in jobs if j['name'].endswith('timeline cleanup'))['enabled'])
        self.assertFalse(next(j for j in jobs if j['name']=='Nova image timeline')['enabled'])

    def test_timeline_can_be_selected_in_setup_but_cleanup_is_model_free(self):
        home=self.sb/'second-home'
        run('--home',str(home),'init','--answers',answers(vault=str(self.sb/'second-vault'),image_timeline=True,cron_active=False),expect=0)
        jobs=json.loads((home/'cron/jobs.json').read_text())['jobs']
        self.assertEqual(len(jobs),CORE_JOBS+2)
        # Only the model-free jobs run while setup is paused.
        active={j['name'] for j in jobs if j['enabled']}
        self.assertEqual(active,scripted_job_names()|{'Nova image timeline cleanup'})
        cleanup=next(j for j in jobs if j['name'].endswith('timeline cleanup'))
        self.assertTrue(cleanup['no_agent'])
        self.assertEqual(cleanup['script'],'companion-timeline-cleanup.py')
        pulse=next(j for j in jobs if j['name'].endswith('companion pulse'))
        self.assertEqual(pulse['schedule']['expr'],'*/15 * * * *')
        self.assertIn('LIVED STATE v1:',pulse['prompt'])
        self.assertTrue((self.sb/'second-vault/companion-life/PRESENCE.md').exists())

    def test_init_is_refused_twice_without_force(self):
        r=run('--home',str(self.home),'init','--answers',answers())
        self.assertNotEqual(r.returncode,0)
        self.assertIn('already a companion',r.stderr+r.stdout)

    def test_doctor_flags_unfinished_soul_then_passes_when_edited(self):
        soul=self.home/'SOUL.md'
        soul.write_text(soul.read_text()+'\n✎ EDIT: an actual unanswered question\n')
        r=run('--home',str(self.home),'doctor')
        self.assertEqual(r.returncode,1);self.assertIn('EDIT placeholders',r.stdout)
        soul=self.home/'SOUL.md'
        soul.write_text(soul.read_text().replace('✎ EDIT','done'))
        import yaml
        command=yaml.safe_load((self.home/'config.yaml').read_text())['hooks']['pre_llm_call'][0]['command']
        (self.home/'shell-hooks-allowlist.json').write_text(json.dumps({'approvals':[{'event':'pre_llm_call','command':command}]}))
        r=run('--home',str(self.home),'doctor',expect=0)
        self.assertIn('OK',r.stdout)

    def test_add_creates_an_isolated_agent(self):
        run('--home',str(self.home),'add','kit',
            '--answers',answers(agent='Kit',pronoun_set='he',context_tokens=8192),
            '--vault',str(self.vault),expect=0)
        prof=self.home/'profiles/kit'
        self.assertTrue((prof/'companion.json').exists())
        self.assertTrue((self.vault/'agents/kit/companion-life').is_dir())
        # kit has its own people dir; the root agent's ledger is a different file
        self.assertNotEqual(self.vault/'people/alex',self.vault/'agents/kit/people/alex')
        self.assertFalse((self.vault/'agents/kit/people/alex/facts.jsonl').exists())
        self.assertFalse(str(self.vault/'agents/kit').startswith(str(self.vault/'people')))

    def test_small_window_agent_gets_a_smaller_injection(self):
        run('--home',str(self.home),'add','kit','--answers',
            answers(agent='Kit',context_tokens=8192),'--vault',str(self.vault),expect=0)
        big=run('--home',str(self.home),'doctor').stdout
        small=run('--home',str(self.home/'profiles/kit'),'doctor').stdout
        self.assertIn('9000 chars',big);self.assertIn('1200 chars',small)

    def test_remove_refuses_without_force(self):
        run('--home',str(self.home),'add','kit','--answers',answers(agent='Kit'),
            '--vault',str(self.vault),expect=0)
        r=run('--home',str(self.home),'remove','kit')
        self.assertNotEqual(r.returncode,0)
        self.assertTrue((self.home/'profiles/kit').exists())

    def test_remove_force_archives_rather_than_deleting(self):
        run('--home',str(self.home),'add','kit','--answers',answers(agent='Kit'),
            '--vault',str(self.vault),expect=0)
        run('--home',str(self.home),'remove','kit','--force',expect=0)
        self.assertFalse((self.home/'profiles/kit').exists())
        archived=list((self.home/'profiles-removed').glob('kit-*'))
        self.assertEqual(len(archived),1)
        self.assertTrue((archived[0]/'SOUL.md').exists())

    def test_removal_says_what_goes_and_what_stays(self):
        run('--home',str(self.home),'add','kit','--answers',answers(agent='Kit'),
            '--vault',str(self.vault),expect=0)
        out=run('--home',str(self.home),'remove','kit','--force',expect=0)
        self.assertIn('ARCHIVE',out.stdout)
        self.assertIn('not deleted',out.stdout)
        self.assertIn(str(self.vault/'agents'/'kit'),out.stdout)      # the life left behind
        self.assertIn('its life is still at',out.stdout)

    def test_purge_is_refused_when_the_vault_lives_inside_the_profile(self):
        inside=self.home/'profiles/kit/vault'
        run('--home',str(self.home),'add','kit','--answers',answers(agent='Kit'),
            '--vault',str(inside),expect=0)
        out=run('--home',str(self.home),'remove','kit','--force','--purge')
        self.assertNotEqual(out.returncode,0)
        self.assertIn('vault data lives inside the profile',out.stdout+out.stderr)
        self.assertTrue((self.home/'profiles/kit').exists())
        # An archive of the same profile is refused for the same reason.
        out=run('--home',str(self.home),'remove','kit','--force')
        self.assertNotEqual(out.returncode,0)
        self.assertTrue((self.home/'profiles/kit').exists())

    def test_purge_deletes_only_after_the_name_is_typed(self):
        run('--home',str(self.home),'add','kit','--answers',answers(agent='Kit'),
            '--vault',str(self.vault),expect=0)
        out=run('--home',str(self.home),'remove','kit','--force','--purge',expect=0)
        self.assertIn('PURGE',out.stdout)
        self.assertIn('no archive and no undo',out.stdout)
        self.assertFalse((self.home/'profiles/kit').exists())
        self.assertTrue((self.vault/'agents'/'kit').exists())   # the vault is not purged

    def test_remove_never_touches_the_root_agent(self):
        for name in ('root',''):
            r=run('--home',str(self.home),'remove',name)
            self.assertNotEqual(r.returncode,0)
        self.assertTrue((self.home/'SOUL.md').exists())


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.sb=pathlib.Path(tempfile.mkdtemp());self.home=self.sb/'.hermes'
        self.home.mkdir(parents=True)
        self.original='# SOUL.md — Rook\n\nTerse sysadmin helper. No small talk.\n'
        (self.home/'SOUL.md').write_text(self.original)

    def up(self,soul='append',**kw):
        r=run('--home',str(self.home),'upgrade','--vault',str(self.sb/'vault'),
              '--answers',answers(agent='Rook',soul=soul,**kw),expect=0)
        self.backups=self.sb/'vault/soul/soul-backups'   # backups follow the soul
        return r

    def test_append_keeps_the_original_on_top_and_backs_it_up(self):
        self.up('append')
        text=(self.home/'SOUL.md').read_text()
        self.assertTrue(text.startswith(self.original.rstrip('\n')))
        self.assertIn('tamanitomo appended',text)
        self.assertEqual((self.backups/'SOUL.md.pre-companion').read_text(),self.original)

    def test_append_tells_the_user_to_merge(self):
        r=self.up('append')
        self.assertIn('Still to do',r.stdout)
        self.assertIn('Merge the appended scaffold',r.stdout)
        self.assertIn('inconsistent character',r.stdout)

    def test_replace_backs_up_first(self):
        self.up('replace')
        self.assertEqual((self.backups/'SOUL.md.pre-companion').read_text(),self.original)
        self.assertNotIn('No small talk',(self.home/'SOUL.md').read_text())

    def test_keep_preserves_every_word_and_only_adds_the_block_marker(self):
        self.up('keep')
        text=(self.home/'SOUL.md').read_text()
        self.assertTrue(text.startswith(self.original))      # not one word changed
        self.assertNotIn('tamanitomo appended',text)      # no scaffold
        self.assertIn('COMPANION-SELF-AUTHORED',text)        # machinery the agent needs

    def test_upgrade_still_installs_the_machinery(self):
        self.up('keep')
        self.assertTrue((self.home/'hooks/companion-context.py').exists())
        self.assertEqual(len(json.loads((self.home/'cron/jobs.json').read_text())['jobs']),CORE_JOBS)

    def test_second_upgrade_is_a_no_op(self):
        self.up('append')
        r=run('--home',str(self.home),'upgrade','--answers',answers(agent='Rook'))
        self.assertIn('already a companion',r.stdout)
        self.assertEqual((self.home/'SOUL.md').read_text().count('tamanitomo appended'),1)

    def test_upgrade_refuses_when_there_is_no_agent_there(self):
        r=run('--home',str(self.sb/'empty'),'upgrade','--answers',answers())
        self.assertNotEqual(r.returncode,0)
        self.assertIn('does not look like a Hermes agent',r.stderr+r.stdout)

if __name__=='__main__':unittest.main()


class VaultPlacementTests(unittest.TestCase):
    """A second agent must join the vault the others already use, not start a
    fresh one somewhere else."""

    def setUp(self):
        self.sb=pathlib.Path(tempfile.mkdtemp())
        self.home=self.sb/'.hermes'
        self.vault=self.sb/'custom-vault'          # deliberately NOT ~/vault
        run('--home',str(self.home),'init','--answers',answers(agent='Root'),
            '--vault',str(self.vault),expect=0)

    def vault_of(self,home):
        return pathlib.Path(json.loads((home/'companion.json').read_text())['vault'])

    def test_added_agent_inherits_the_existing_vault(self):
        run('--home',str(self.home),'add','kit',
            '--answers',answers(agent='Kit'),expect=0)      # no --vault on purpose
        self.assertEqual(self.vault_of(self.home/'profiles/kit'),self.vault)

    def test_upgraded_profile_inherits_the_existing_vault(self):
        prof=self.home/'profiles/rowan';prof.mkdir(parents=True)
        (prof/'SOUL.md').write_text('# SOUL.md — Rowan\n')
        run('--home',str(prof),'upgrade','--answers',answers(agent='Rowan',soul='append'),expect=0)
        self.assertEqual(self.vault_of(prof),self.vault)

    def test_agents_sit_side_by_side_under_one_vault(self):
        run('--home',str(self.home),'add','kit','--answers',answers(agent='Kit'),expect=0)
        self.assertTrue((self.vault/'companion-life').is_dir())          # root agent
        self.assertTrue((self.vault/'agents/kit/companion-life').is_dir())

    def test_nothing_is_written_to_the_default_vault_when_another_is_in_use(self):
        """Twice during development an ad-hoc run without --vault created agent
        directories in the real ~/vault. The default must follow the existing
        agents, not the home directory."""
        real=pathlib.Path.home()/'vault'
        before=sorted(p.name for p in real.iterdir()) if real.is_dir() else None
        run('--home',str(self.home),'add','kit','--answers',answers(agent='Kit'),expect=0)
        prof=self.home/'profiles/rowan';prof.mkdir(parents=True)
        (prof/'SOUL.md').write_text('# SOUL.md — Rowan\n')
        run('--home',str(prof),'upgrade','--answers',answers(agent='Rowan',soul='append'),expect=0)
        after=sorted(p.name for p in real.iterdir()) if real.is_dir() else None
        self.assertEqual(before,after,'wrote into the default vault instead of the one in use')

    def test_explicit_vault_flag_still_wins(self):
        other=self.sb/'elsewhere'
        run('--home',str(self.home),'add','kit','--answers',answers(agent='Kit'),
            '--vault',str(other),expect=0)
        self.assertEqual(self.vault_of(self.home/'profiles/kit'),other)


class SoulInVaultTests(unittest.TestCase):
    """The identity file lives in the vault so it is covered by the same backups
    and history as the rest of the agent's life; Hermes reads it through a link."""

    def setUp(self):
        self.sb=pathlib.Path(tempfile.mkdtemp())
        self.home=self.sb/'.hermes';self.vault=self.sb/'vault'

    def test_init_puts_the_real_file_in_the_vault_and_links_to_it(self):
        run('--home',str(self.home),'init','--answers',answers(),
            '--vault',str(self.vault),expect=0)
        link=self.home/'SOUL.md';real=self.vault/'soul/SOUL.md'
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(),real.resolve())
        self.assertIn('Nova',real.read_text())

    def test_upgrade_moves_an_existing_soul_in_without_losing_a_word(self):
        self.home.mkdir(parents=True)
        original='# SOUL.md — Rook\n\nYears of identity here.\n'
        (self.home/'SOUL.md').write_text(original)
        run('--home',str(self.home),'upgrade','--vault',str(self.vault),
            '--answers',answers(agent='Rook',soul='append',move_soul=True),expect=0)
        real=self.vault/'soul/SOUL.md'
        self.assertTrue((self.home/'SOUL.md').is_symlink())
        self.assertIn('Years of identity here.',real.read_text())
        self.assertEqual((self.vault/'soul/soul-backups/SOUL.md.pre-move').read_text(),original)

    def test_declining_the_move_leaves_the_soul_where_it_was(self):
        self.home.mkdir(parents=True)
        (self.home/'SOUL.md').write_text('# SOUL.md — Rook\n')
        run('--home',str(self.home),'upgrade','--vault',str(self.vault),
            '--answers',answers(agent='Rook',soul='keep',move_soul=False),expect=0)
        self.assertFalse((self.home/'SOUL.md').is_symlink())
        self.assertFalse((self.vault/'soul/SOUL.md').exists())

    def test_an_atomic_write_does_not_replace_the_link(self):
        """os.replace() onto a symlink path would swap the link for a regular
        file and orphan the vault copy."""
        run('--home',str(self.home),'init','--answers',answers(),
            '--vault',str(self.vault),expect=0)
        subprocess.run([sys.executable,str(ROOT/'kit/scripts/companion_self.py'),
                        '--home',str(self.home),'soul','--append','- a new line'],
                       capture_output=True,text=True,timeout=60,check=True)
        self.assertTrue((self.home/'SOUL.md').is_symlink())
        self.assertIn('- a new line',(self.vault/'soul/SOUL.md').read_text())

    def test_doctor_reports_a_broken_link_as_loss_of_identity(self):
        run('--home',str(self.home),'init','--answers',answers(),
            '--vault',str(self.vault),expect=0)
        (self.vault/'soul/SOUL.md').unlink()          # vault unreachable / removed
        out=run('--home',str(self.home),'doctor').stdout
        self.assertIn('broken link',out)
        self.assertIn('NO identity',out)


class HermesNativeProfileTests(unittest.TestCase):
    """A new agent must be a real Hermes profile, not a lookalike directory.
    `hermes profile create` also seeds a 0600 .env (without which the profile
    silently inherits shell API keys), bootstraps skills, and installs a wrapper."""

    def setUp(self):
        self.sb=pathlib.Path(tempfile.mkdtemp())
        self.home=self.sb/'.hermes';self.vault=self.sb/'vault'
        run('--home',str(self.home),'init','--answers',answers(),'--vault',str(self.vault),expect=0)


    def test_add_delegates_to_hermes_and_gets_a_real_profile(self):
        out=run('--home',str(self.home),'add','kit','--answers',answers(agent='Kit'),expect=0).stdout
        self.assertIn('hermes profile create',out)
        prof=self.home/'profiles/kit'
        env=prof/'.env'
        self.assertTrue(env.exists(),'Hermes did not seed .env')
        if os.name!='nt':self.assertEqual(oct(env.stat().st_mode)[-3:],'600')
        for d in ('skills','memories','sessions'):
            self.assertTrue((prof/d).is_dir(),f'missing {d}/')
        self.assertTrue((prof/'companion.json').exists())   # our layer on top


    def test_profile_is_created_under_the_requested_root_not_the_real_one(self):
        real=pathlib.Path.home()/'.hermes/profiles'
        before=sorted(p.name for p in real.iterdir()) if real.is_dir() else []
        run('--home',str(self.home),'add','kit','--answers',answers(agent='Kit'),expect=0)
        after=sorted(p.name for p in real.iterdir()) if real.is_dir() else []
        self.assertEqual(before,after,'created a profile in the real Hermes install')
        self.assertTrue((self.home/'profiles/kit').is_dir())

    def test_missing_hermes_does_not_create_fake_profile(self):
        r=run('--home',str(self.home),'add','kit','--answers',answers(agent='Kit'),
              env={'COMPANION_HERMES_COMMAND':json.dumps(['companion-nonexistent-test-command'])})
        self.assertNotEqual(r.returncode,0)
        self.assertFalse((self.home/'profiles/kit/companion.json').exists())


class HermesCronTests(unittest.TestCase):
    """The job set is created through Hermes' own cron API, not by writing its
    store. Toolset flags are used only when advertised by the installed CLI."""


    def test_jobs_are_created_by_hermes_and_it_can_list_them(self):
        sb=pathlib.Path(tempfile.mkdtemp());home=sb/'.hermes'
        r=run('--home',str(home),'init','--answers',answers(),'--vault',str(sb/'vault'))
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertIn('via `hermes cron create`',r.stdout)
        jobs=json.loads((home/'cron/jobs.json').read_text())['jobs']
        self.assertEqual(len(jobs),CORE_JOBS)
        for j in jobs:
            self.assertTrue(j['next_run_at'],'Hermes scheduler fields preserved')
            self.assertNotIn('{{',j['prompt'])
        listing=subprocess.run([sys.executable,str(ROOT/'tests/fake_hermes.py'),'cron','list'],capture_output=True,text=True,
                               timeout=120,env={**os.environ,'HERMES_HOME':str(home)})
        self.assertIn('Nova companion pulse',listing.stdout)

    def test_opt_out_stages_jobs_without_touching_store(self):
        sb=pathlib.Path(tempfile.mkdtemp());home=sb/'.hermes'
        out=run('--home',str(home),'init','--answers',answers(),
                '--vault',str(sb/'vault'),expect=0,env={'COMPANION_NO_HERMES_CRON':'1'}).stdout
        self.assertIn('pending',out)
        self.assertFalse((home/'cron/jobs.json').exists())
        self.assertEqual(len(json.loads((home/'companion-pending-jobs.json').read_text())),CORE_JOBS)


class MenuTests(unittest.TestCase):
    """The no-argument program: a roster and a menu, not a script invocation."""

    def setUp(self):
        self.sb=pathlib.Path(tempfile.mkdtemp());self.home=self.sb/'.hermes'
        run('--home',str(self.home),'init','--answers',answers(agent='Nova'),
            '--vault',str(self.sb/'vault'),expect=0)
        # an agent that exists in Hermes but has not been set up by the kit
        bare=self.home/'profiles/bare';bare.mkdir(parents=True)
        (bare/'SOUL.md').write_text('# SOUL.md — Bare\n')
        (bare/'config.yaml').write_text('model:\n  provider: openai\n')

    def test_no_subcommand_lists_every_agent_and_its_state(self):
        r=run('--home',str(self.home))
        self.assertEqual(r.returncode,0)
        lines={l.split('\t')[0]:l for l in r.stdout.strip().splitlines()}
        self.assertIn('default',lines);self.assertIn('bare',lines)
        self.assertIn('set-up',lines['default'])
        self.assertIn('not-set-up',lines['bare'])
        self.assertIn('Nova',lines['default'])

    def test_roster_reports_a_profile_that_needs_adopting(self):
        from kit.cli import roster
        rows={r['name']:r for r in roster.agent_rows(self.home)}
        self.assertTrue(rows['default']['set_up'])
        self.assertFalse(rows['bare']['set_up'])
        self.assertTrue(rows['bare']['has_soul'])
        self.assertTrue(rows['default']['is_root'])
        self.assertFalse(rows['bare']['is_root'])


class ContextDriftTests(unittest.TestCase):
    """The window is detected once at setup; switching models must not leave the
    budgets sized for a model that is no longer there."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=pathlib.Path(self.tmp.name)/'hermes';self.vault=pathlib.Path(self.tmp.name)/'vault'
        run('--home',str(self.home),'init','--vault',str(self.vault),'--answers',answers(),expect=0)

    def set_window(self,tokens):
        cfg=self.home/'config.yaml'
        cfg.write_text(f'model:\n  default: test-model\n  provider: test-provider\n'
                       f'  context_length: {tokens}\n',encoding='utf-8')

    def recorded(self):
        return json.loads((self.home/'companion.json').read_text())['context_tokens']

    def test_doctor_notices_the_window_changed(self):
        self.set_window(8192)
        out=run('--home',str(self.home),'doctor')
        self.assertNotEqual(out.returncode,0)
        self.assertIn('the model now reports 8,192 tokens',out.stdout)
        self.assertTrue('tamanitomo repair' in out.stdout or 'companion repair' in out.stdout)

    def test_repair_adopts_the_new_window_and_resizes_budgets(self):
        before=self.recorded()
        self.set_window(8192)
        out=run('--home',str(self.home),'repair')
        self.assertIn(f'context window {before:,} -> 8,192 tokens',out.stdout)
        self.assertEqual(self.recorded(),8192)
        # and doctor stops reporting the drift
        self.assertNotIn('the model now reports',run('--home',str(self.home),'doctor').stdout)

    def test_an_unchanged_window_is_left_alone(self):
        before=self.recorded()
        run('--home',str(self.home),'repair')
        self.assertEqual(self.recorded(),before)

    def test_a_guessed_window_is_never_treated_as_a_change(self):
        # config.yaml names no context_length, so detection falls back to its
        # default. That is a guess, not evidence the recorded window is stale.
        self.assertFalse(cc.detected_for_real('fallback default'))
        self.assertTrue(cc.detected_for_real('config.yaml model.context_length'))
        out=run('--home',str(self.home),'doctor')
        self.assertNotIn('the model now reports',out.stdout)
        self.assertEqual(self.recorded(),131072)


class ToolsetTests(unittest.TestCase):
    """The manifest says which toolsets each job needs; a job that cannot reach the
    terminal cannot run the commands its own prompt gives it."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=pathlib.Path(self.tmp.name)/'hermes';self.vault=pathlib.Path(self.tmp.name)/'vault'

    def jobs(self):
        return json.loads((self.home/'cron/jobs.json').read_text())['jobs']

    def test_each_job_is_created_with_the_toolsets_its_manifest_declares(self):
        run('--home',str(self.home),'init','--vault',str(self.vault),'--answers',answers(),expect=0)
        manifest={j['key']:j['toolsets'] for j in
                  json.loads((ROOT/'kit/templates/cron/manifest.json').read_text())['jobs']}
        got={j['name']:j['enabled_toolsets'] for j in self.jobs()}
        self.assertEqual(len(got),CORE_JOBS)
        for name,sets in got.items():
            if not manifest_toolsets_for(name):continue   # model-free jobs declare none
            self.assertIsNotNone(sets)          # the flag reached Hermes
            self.assertIn('terminal',sets)      # every prompt shells out
        self.assertEqual(sorted(got[[n for n in got if 'pulse' in n][0]]),sorted(manifest['pulse']))
        self.assertIn('session_search',got[[n for n in got if 'autonomy' in n][0]])

    def test_a_hermes_that_rejects_the_flag_still_gets_its_jobs(self):
        # A build that exits non-zero on --toolsets must not leave setup jobless.
        stub=pathlib.Path(self.tmp.name)/'picky.py'
        stub.write_text(
            'import sys,runpy\n'
            'if "--help" in sys.argv: print("usage: cron create --name NAME"); sys.exit(0)\n'
            'if "--toolsets" in sys.argv: sys.exit(2)\n'
            f'sys.argv[0]={str(ROOT/"tests/fake_hermes.py")!r}\n'
            f'runpy.run_path({str(ROOT/"tests/fake_hermes.py")!r},run_name="__main__")\n',
            encoding='utf-8')
        out=run('--home',str(self.home),'init','--vault',str(self.vault),'--answers',answers(),
                expect=0,env={'COMPANION_HERMES_COMMAND':json.dumps([sys.executable,str(stub)])})
        self.assertEqual(len(self.jobs()),CORE_JOBS)
        self.assertTrue(all(j['enabled_toolsets'] is None for j in self.jobs()))
        self.assertIn('no supported per-job toolset flag',out.stdout)


    def test_failed_create_is_not_retried_after_committing_a_job(self):
        stub=pathlib.Path(self.tmp.name)/'partial.py'
        stub.write_text('import sys,runpy\n'+
            f'runpy.run_path({str(ROOT/"tests/fake_hermes.py")!r},run_name="__main__")\n'+
            'if "--help" not in sys.argv: sys.exit(1)\n',encoding='utf-8')
        run('--home',str(self.home),'init','--vault',str(self.vault),'--answers',answers(),expect=0,
            env={'COMPANION_HERMES_COMMAND':json.dumps([sys.executable,str(stub)])})
        self.assertEqual(len(self.jobs()),CORE_JOBS)
        self.assertTrue((self.home/'companion-pending-jobs.json').exists())


class VaultHousekeepingTests(unittest.TestCase):
    """The vault is a folder people point Obsidian and git at."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=pathlib.Path(self.tmp.name)/'hermes';self.vault=pathlib.Path(self.tmp.name)/'vault'

    def ignores(self):
        return (self.vault/'.gitignore').read_text(encoding='utf-8')

    def test_setup_writes_the_editor_ignores_before_the_editor_exists(self):
        run('--home',str(self.home),'init','--vault',str(self.vault),'--answers',answers(),expect=0)
        self.assertFalse((self.vault/'.obsidian').exists())   # nothing created it yet
        for rule in ('.obsidian/','.trash/','.DS_Store','**/companion-life/.inputs/'):
            self.assertIn(rule,self.ignores())

    def test_an_existing_gitignore_is_added_to_never_replaced(self):
        self.vault.mkdir(parents=True)
        (self.vault/'.gitignore').write_text('# mine\nsecrets/\n.trash/\n',encoding='utf-8')
        run('--home',str(self.home),'init','--vault',str(self.vault),'--answers',answers(),expect=0)
        body=self.ignores()
        self.assertIn('# mine',body);self.assertIn('secrets/',body)
        self.assertEqual(body.count('.trash/'),1)             # already there, not duplicated
        self.assertIn('.obsidian/',body)

    def test_repair_backfills_an_install_made_before_this_existed(self):
        run('--home',str(self.home),'init','--vault',str(self.vault),'--answers',answers(),expect=0)
        (self.vault/'.gitignore').unlink()
        out=run('--home',str(self.home),'repair')
        self.assertIn('vault .gitignore',out.stdout)
        self.assertIn('.obsidian/',self.ignores())


class OutreachCapTests(unittest.TestCase):
    def test_answers_give_the_number_not_a_menu_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=pathlib.Path(tmp)/'hermes';vault=pathlib.Path(tmp)/'vault'
            run('--home',str(home),'init','--vault',str(vault),
                '--answers',answers(outreach_per_day=10),expect=0)
            self.assertEqual(json.loads((home/'companion.json').read_text())['outreach_per_day'],10)

    def test_replies_only_forces_the_cap_to_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=pathlib.Path(tmp)/'hermes';vault=pathlib.Path(tmp)/'vault'
            run('--home',str(home),'init','--vault',str(vault),
                '--answers',answers(outreach='never'),expect=0)
            self.assertEqual(json.loads((home/'companion.json').read_text())['outreach_per_day'],0)


class LegacyConfigTests(unittest.TestCase):
    """A config this kit wrote in an older version must still open."""
    def test_a_retired_pronoun_set_is_migrated_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=pathlib.Path(tmp)/'hermes';vault=pathlib.Path(tmp)/'vault'
            run('--home',str(home),'init','--vault',str(vault),'--answers',answers(),expect=0)
            cfg=home/'companion.json';data=json.loads(cfg.read_text())
            data['pronoun_set']='it';data['human_pronoun_set']='it'
            cfg.write_text(json.dumps(data),encoding='utf-8')
            c=cc.load(home)
            self.assertEqual((c.pronoun_set,c.human_pronoun_set),('she','he'))
            out=run('--home',str(home),'doctor')
            self.assertIn("no longer supports",out.stdout)
            self.assertNotEqual(out.returncode,0)

    def test_they_them_pronoun_set_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=pathlib.Path(tmp)/'hermes';vault=pathlib.Path(tmp)/'vault'
            run('--home',str(home),'init','--vault',str(vault),'--answers',answers(pronoun_set='they',human_pronoun_set='they'),expect=0)
            c=cc.load(home)
            self.assertEqual((c.pronoun_set,c.human_pronoun_set),('they','they'))
            self.assertEqual(c.subj(),'they')
            self.assertEqual(c.obj(),'them')
            self.assertEqual(c.poss(),'their')
            self.assertEqual(c.refl(),'themselves')
            out=run('--home',str(home),'doctor')
            self.assertNotIn("no longer supports",out.stdout)


class SettingsTests(unittest.TestCase):
    """Changing a setting after setup has to reach both places it lives: the
    config the outreach gate reads, and the cron prompts that quote it."""

    def install(self,tmp,**kw):
        home=pathlib.Path(tmp)/'hermes';vault=pathlib.Path(tmp)/'vault'
        run('--home',str(home),'init','--vault',str(vault),'--answers',answers(**kw),expect=0)
        return home

    def prompts(self,home):
        return {j['name']:j.get('prompt','') for j in json.loads((home/'cron/jobs.json').read_text())['jobs']}

    def test_quiet_hours_reach_the_config_and_every_prompt_that_quotes_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=self.install(tmp)
            run('--home',str(home),'settings','--set','quiet_start=22:30','--set','quiet_end=07:15',expect=0)
            data=json.loads((home/'companion.json').read_text())
            self.assertEqual((data['quiet_start'],data['quiet_end']),('22:30','07:15'))
            for name,prompt in self.prompts(home).items():
                if 'Do not contact' not in prompt:continue
                self.assertIn('between 22:30 and 07:15',prompt,name)
                self.assertNotIn('between 23:00 and 08:00',prompt,name)
            schedules={j['name']:j.get('schedule',{}).get('expr') for j in json.loads((home/'cron/jobs.json').read_text())['jobs']}
            c=cc.load(home)
            self.assertEqual(schedules.get(c.agent+' morning'),'25 7 * * *')
            self.assertEqual(schedules.get(c.agent+' wind-down'),'10 22 * * *')

    def test_the_gate_honours_the_new_window_without_a_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=self.install(tmp)
            run('--home',str(home),'settings','--set','quiet_start=09:00','--set','quiet_end=17:00',expect=0)
            import datetime as dt
            from zoneinfo import ZoneInfo
            import companion_outreach as out
            c=cc.load(home)
            noon=dt.datetime(2026,3,4,12,0,tzinfo=ZoneInfo(c.timezone))
            self.assertTrue(out.in_quiet_hours(c,noon))
            self.assertFalse(out.in_quiet_hours(c,noon.replace(hour=20)))

    def test_outreach_policy_is_rewritten_and_replies_only_clears_the_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=self.install(tmp)
            run('--home',str(home),'settings','--set','outreach=never',expect=0)
            data=json.loads((home/'companion.json').read_text())
            self.assertEqual((data['outreach'],data['outreach_per_day']),('never',0))
            autonomy=next(p for n,p in self.prompts(home).items() if 'autonomy' in n)
            self.assertIn('Do not initiate messages',autonomy)
            self.assertNotIn('whenever you genuinely want to',autonomy)

    def test_a_prompt_edited_by_hand_keeps_that_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=self.install(tmp)
            store=home/'cron/jobs.json';data=json.loads(store.read_text())
            for job in data['jobs']:
                job['prompt']=job.get('prompt','').replace('Quiet hours:','KEEP THIS. Quiet hours:')
            store.write_text(json.dumps(data),encoding='utf-8')
            run('--home',str(home),'settings','--set','quiet_start=21:00',expect=0)
            pulse=next(p for n,p in self.prompts(home).items() if 'pulse' in n)
            self.assertIn('KEEP THIS.',pulse)
            self.assertIn('between 21:00',pulse)

    def test_wording_the_kit_no_longer_recognises_is_reported_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=self.install(tmp)
            store=home/'cron/jobs.json';data=json.loads(store.read_text())
            for job in data['jobs']:
                job['prompt']=re.sub(r'Do not contact .*? messages first\.','(hours described my own way)',
                                     job.get('prompt',''),flags=re.S)
            store.write_text(json.dumps(data),encoding='utf-8')
            out=run('--home',str(home),'settings','--set','quiet_start=21:00',expect=0)
            self.assertIn('edited by hand',out.stdout)

    def test_timezone_change_updates_hermes_config_and_the_quoted_hours(self):
        with tempfile.TemporaryDirectory() as tmp:
            import yaml
            home=self.install(tmp)
            run('--home',str(home),'settings','--set','timezone=Europe/London',expect=0)
            self.assertEqual(yaml.safe_load((home/'config.yaml').read_text())['timezone'],'Europe/London')
            pulse=next(p for n,p in self.prompts(home).items() if 'pulse' in n)
            self.assertIn('(Europe/London)',pulse)

    def test_bad_values_and_unknown_keys_change_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=self.install(tmp)
            before=(home/'companion.json').read_text()
            for bad in ('quiet_start=25:99','timezone=Mars/Olympus','outreach=maybe',
                        'outreach_per_day=999','image_style=crayon','persona=warm','quiet_start'):
                self.assertNotEqual(run('--home',str(home),'settings','--set',bad).returncode,0,bad)
            self.assertEqual((home/'companion.json').read_text(),before)

    def test_a_rejected_value_does_not_half_apply_the_rest_of_the_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=self.install(tmp)
            run('--home',str(home),'settings','--set','quiet_start=22:00','--set','timezone=Mars/Olympus',expect=1)
            self.assertEqual(json.loads((home/'companion.json').read_text())['quiet_start'],'23:00')

    def test_listing_settings_needs_no_arguments_and_touches_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=self.install(tmp)
            before=(home/'companion.json').read_text()
            out=run('--home',str(home),'settings',expect=0)
            self.assertEqual(json.loads(out.stdout)['quiet_hours'],'23:00-08:00')
            self.assertEqual((home/'companion.json').read_text(),before)

    def test_quiet_hours_drift_updates_cron_schedules_and_prose(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=self.install(tmp)
            import companion_quiet as quiet
            import datetime as dt
            from zoneinfo import ZoneInfo
            c=cc.load(home);c.adaptive_quiet=True;c.save()
            now=dt.datetime(2026,3,15,12,0,tzinfo=ZoneInfo(c.timezone))
            # 5 nights of activity just after 23:00
            messages=[dt.datetime(2026,3,day,23,15,tzinfo=ZoneInfo(c.timezone)) for day in range(1,6)]
            # apply() runs in-process, so unlike run() it inherits this process's
            # environment -- without the shim it reaches for a real `hermes` on PATH,
            # which a developer machine has and a clean checkout does not.
            with patch.dict(os.environ,{
                    'COMPANION_HERMES_COMMAND':json.dumps([sys.executable,str(ROOT/'tests/fake_hermes.py')])}):
                plan=quiet.apply(c,now=now,messages=messages)
            self.assertTrue(plan.get('applied'))
            self.assertEqual(plan.get('quiet_start'),'23:30')
            schedules={j['name']:j.get('schedule',{}).get('expr') for j in json.loads((home/'cron/jobs.json').read_text())['jobs']}
            self.assertEqual(schedules.get(c.agent+' wind-down'),'10 23 * * *')
            pulse=next(p for n,p in self.prompts(home).items() if 'pulse' in n)
            self.assertIn('between 23:30 and 08:00',pulse)





class PromptRefreshTests(unittest.TestCase):
    """A fix to a cron template has to be able to reach a companion that already
    exists, without ever overwriting a prompt the user edited in Hermes."""

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name);self.home=root/'hermes';self.vault=root/'vault'
        run('--home',str(self.home),'init','--vault',str(self.vault),'--answers',answers(),expect=0)
        self.c=cc.load(self.home)
        # refresh_templates is exercised in-process, so point it at the same
        # contract double `run` uses rather than at a real Hermes install.
        patched=patch.dict(os.environ,{'COMPANION_HERMES_COMMAND':
            json.dumps([sys.executable,str(ROOT/'tests/fake_hermes.py')]),'HERMES_HOME':str(self.home)})
        patched.start();self.addCleanup(patched.stop)
        from kit.cli import scaffold
        self.scaffold=scaffold
        self.m=scaffold.mapping(self.c,{})

    def jobs(self):
        return {j['name']:j for j in json.loads((self.home/'cron/jobs.json').read_text())['jobs']}

    def age_prompt(self,name,text):
        """Rewrite an installed prompt directly, standing in for an older kit version."""
        path=self.home/'cron/jobs.json';data=json.loads(path.read_text())
        for j in data['jobs']:
            if j['name']==name:j['prompt']=text
        path.write_text(json.dumps(data))

    def test_day_continuity_upgrade_preserves_custom_prompt(self):
        name=next(name for name in self.jobs() if 'pulse' in name.lower())
        custom='My personal pulse instructions stay here.'
        self.age_prompt(name,custom)
        self.scaffold.install_jobs(self.c,self.m,[])
        upgraded=self.jobs()[name]['prompt']
        self.assertTrue(upgraded.endswith(custom))
        self.assertIn('DAY CONTINUITY v2:',upgraded)
        self.assertIn('commitments', (self.c.life/'PRESENCE.md').read_text())
        self.scaffold.install_jobs(self.c,self.m,[])
        self.assertEqual(self.jobs()[name]['prompt'],upgraded)

    def test_setup_records_a_fingerprint_for_every_prompt_it_wrote(self):
        prints=self.scaffold.read_fingerprints(self.c)
        self.assertEqual(set(prints),set(self.jobs()))

    def test_an_unedited_prompt_is_re_rendered_from_the_current_template(self):
        name='Nova daily journal and reflection'
        installed=self.jobs()[name]['prompt']
        self.scaffold.record_fingerprint(self.c,name,'an older kit wrote this')
        self.age_prompt(name,'an older kit wrote this')
        report=[]
        self.scaffold.refresh_templates(self.c,self.m,report)
        self.assertEqual(self.jobs()[name]['prompt'],installed)
        self.assertTrue(any('re-rendered' in line for line in report))

    def test_a_hand_edited_prompt_is_left_alone_and_named(self):
        name='Nova daily journal and reflection'
        self.age_prompt(name,'I rewrote this myself.')
        report=[]
        self.scaffold.refresh_templates(self.c,self.m,report)
        self.assertEqual(self.jobs()[name]['prompt'],'I rewrote this myself.')
        self.assertTrue(any(name in line and line.lstrip().startswith('!') for line in report))

    def test_force_re_renders_it_but_keeps_a_copy_first(self):
        name='Nova daily journal and reflection'
        self.age_prompt(name,'I rewrote this myself.')
        report=[]
        self.scaffold.refresh_templates(self.c,self.m,report,force=True)
        self.assertIn('Daily continuity ritual',self.jobs()[name]['prompt'])
        saved=list((self.home/'cron/prompt-backups').glob(name+'-*.md'))
        self.assertEqual([p.read_text() for p in saved],['I rewrote this myself.'])

    def test_repair_leaves_everything_alone_when_asked_to(self):
        name='Nova daily journal and reflection'
        self.age_prompt(name,'I rewrote this myself.')
        run('--home',str(self.home),'repair','--prompts','skip')
        # repair still prefixes a missing memory check — that predates this flag —
        # but the template body is not re-rendered over the user's text.
        prompt=self.jobs()[name]['prompt']
        self.assertTrue(prompt.endswith('I rewrote this myself.'))
        self.assertNotIn('Daily continuity ritual',prompt)


class StockSoulTests(unittest.TestCase):
    """`hermes profile create` ships a default SOUL.md. Setup must not leave the
    companion wearing Hermes's stock system prompt in silence."""

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
        self.home=self.root/'hermes';self.vault=self.root/'vault'

    def init_with_soul(self,text):
        self.home.mkdir(parents=True,exist_ok=True)
        (self.home/'SOUL.md').write_text(text,encoding='utf-8')
        run('--home',str(self.home),'init','--vault',str(self.vault),'--answers',answers(),expect=0)
        return cc.load(self.home)

    def test_the_hermes_default_is_backed_up_and_replaced(self):
        stock='You are Hermes Agent, built by Nous Research. Be direct.\n'
        c=self.init_with_soul(stock)
        written=c.soul.read_text(encoding='utf-8')
        self.assertIn('Generated by tamanitomo',written)
        self.assertNotIn('built by Nous Research',written)
        saved=list(c.soul_backups.glob('SOUL.md.hermes-default*'))
        self.assertEqual([p.read_text() for p in saved],[stock])

    def test_a_soul_someone_wrote_is_left_alone_and_said_so(self):
        mine='# My own careful prompt\n\nDo not touch this.\n'
        c=self.init_with_soul(mine)
        self.assertIn('Do not touch this.',c.soul.read_text(encoding='utf-8'))
        r=run('--home',str(self.home),'doctor')
        self.assertIn('no rendered companion identity',r.stdout)
        self.assertEqual(r.returncode,1)


class ScriptedAnswerTests(unittest.TestCase):
    """A --answers file is written by hand or by a script, and both write JSON
    booleans where the interview shows a labelled choice."""

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)

    def test_booleans_are_accepted_where_a_person_picks_an_option(self):
        for value,expected in ((True,True),(False,False)):
            home=self.root/f'h{value}';vault=self.root/f'v{value}'
            run('--home',str(home),'init','--vault',str(vault),
                '--answers',answers(share_people=value,cron_active=value),expect=0)
            c=cc.load(home)
            self.assertIs(c.share_people,expected)
            self.assertIs(c.cron_active,expected)

    def test_the_string_forms_still_work(self):
        home=self.root/'hs';vault=self.root/'vs'
        run('--home',str(home),'init','--vault',str(vault),
            '--answers',answers(share_people='yes'),expect=0)
        self.assertTrue(cc.load(home).share_people)


class DoctorReportingTests(unittest.TestCase):
    """Doctor reports drift and sizes; it does not decide them."""

    def test_a_job_on_another_model_is_reported_without_failing_the_check(self):
        config={'model':{'default':'big-model'}}
        jobs=[{'name':'Nova companion pulse','model':'cheap-model'},
              {'name':'Nova autonomy loop','model':'big-model'},
              {'name':'Nova daily lifelog'}]
        lines=doctor.job_model_drift(cc.Companion(agent='Nova',human='Alex'),jobs,config)
        self.assertEqual(len([l for l in lines if 'companion pulse' in l]),1)
        self.assertFalse(any('autonomy loop' in l or 'daily lifelog' in l for l in lines))
        # No "!" anywhere: a cheap model on a frequent loop is a choice, not a fault.
        self.assertFalse(any(l.lstrip().startswith('!') for l in lines))

    def test_nothing_is_reported_when_the_profile_model_is_unknown(self):
        c=cc.Companion(agent='Nova',human='Alex')
        self.assertEqual(doctor.job_model_drift(c,[{'name':'x','model':'a'}],{}),[])

    def test_sizes_are_readable_rather_than_exact(self):
        self.assertEqual(doctor._human_bytes(0),'0 B')
        self.assertEqual(doctor._human_bytes(2048),'2.0 KB')
        self.assertTrue(doctor._human_bytes(5*1024**3).endswith('GB'))


class SettingsScreenTests(unittest.TestCase):
    """The menu itself: aligned columns, and a timezone you pick rather than type."""
    def test_values_line_up_in_one_column_under_the_header(self):
        c=cc.Companion(agent='Nova',human='Alex',image_style='anime-modern')
        options,header=settings.settings_table(settings.settings_rows(c))
        bars={label.index('|') for label,_ in options if '|' in label}
        self.assertEqual(len(bars),1,'value column is ragged')
        self.assertEqual(header.splitlines()[0].strip().index('|'),bars.pop(),'header sits off the column')
        self.assertNotIn('|',dict((v,k) for k,v in options)['back'])

    def test_the_cap_row_disappears_when_it_cannot_apply(self):
        rows=settings.settings_rows(cc.Companion(outreach='never',outreach_per_day=0))
        self.assertNotIn('cap',[key for key,_,_ in rows])
        # and the column still lines up without it
        options,_=settings.settings_table(rows)
        self.assertEqual(len({label.index('|') for label,_ in options if '|' in label}),1)

    def test_eastern_leads_the_timezone_list_and_every_zone_stays_reachable(self):
        from zoneinfo import available_timezones
        self.assertEqual(questions.US_TIMEZONES[0][0],'America/New_York')
        regions=questions.zones_by_region()
        self.assertEqual(sum(len(v) for v in regions.values()),len(available_timezones()))
        for zone,_ in questions.US_TIMEZONES:self.assertIn(zone,available_timezones())

    def test_a_current_zone_outside_the_shortlist_is_offered_once(self):
        shortlist=[key for key,_ in questions.US_TIMEZONES]
        self.assertNotIn('Europe/London',shortlist)
        self.assertIn('America/New_York',shortlist)

    def test_setup_still_takes_a_timezone_from_answers_without_a_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=pathlib.Path(tmp)/'hermes';vault=pathlib.Path(tmp)/'vault'
            run('--home',str(home),'init','--vault',str(vault),
                '--answers',answers(timezone='Asia/Tokyo'),expect=0)
            self.assertEqual(json.loads((home/'companion.json').read_text())['timezone'],'Asia/Tokyo')


class PinAndBackupCliTests(unittest.TestCase):
    def test_pin_set_get_and_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=pathlib.Path(tmp)/'hermes';vault=pathlib.Path(tmp)/'vault'
            run('--home',str(home),'init','--vault',str(vault),'--answers',answers(),expect=0)

            # Initially no PIN
            r=run('--home',str(home),'pin',expect=0)
            self.assertIn('No workspace remote PIN configured',r.stdout)

            # Set valid PIN
            r=run('--home',str(home),'pin','--set','5678',expect=0)
            self.assertIn('configured',r.stdout)
            self.assertNotIn('5678',r.stdout)
            c=cc.load(home)
            self.assertEqual(cc.access_pin(home),'5678')

            # Inspect configured PIN
            r=run('--home',str(home),'pin',expect=0)
            self.assertIn('CONFIGURED',r.stdout)

            # Reject invalid PIN
            r=run('--home',str(home),'pin','--set','abc')
            self.assertNotEqual(r.returncode,0)

            # Clear PIN
            r=run('--home',str(home),'pin','--clear',expect=0)
            self.assertIn('cleared',r.stdout)
            c=cc.load(home)
            self.assertEqual(cc.access_pin(home),'')

    def test_vault_backup_creates_zip(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            home=pathlib.Path(tmp)/'hermes';vault=pathlib.Path(tmp)/'vault'
            run('--home',str(home),'init','--vault',str(vault),'--answers',answers(),expect=0)
            (vault/'test_note.md').write_text('Hello from backup test')

            zip_out=pathlib.Path(tmp)/'my_backup.zip'
            r=run('--home',str(home),'backup','--output',str(zip_out),expect=0)
            self.assertTrue(zip_out.is_file())
            self.assertGreater(zip_out.stat().st_size,0)

            with zipfile.ZipFile(zip_out,'r') as z:
                names=z.namelist()
                self.assertIn('test_note.md',names)
                self.assertIn('soul/SOUL.md',names)

