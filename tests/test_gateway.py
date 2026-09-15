"""Gateway enrollment is explicit and never double-owns a profile."""
import json,os,pathlib,sys,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_gateway as gw
import companion_config as cc
import yaml

class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)/'hermes'
        for name in ('nova','rowan'):(self.root/'profiles'/name).mkdir(parents=True)
        self.c=cc.Companion(profile='nova',hermes_root=self.root,vault=pathlib.Path(self.tmp.name)/'vault')
    def config(self,data):
        (self.root/'config.yaml').write_text(yaml.safe_dump(data))
    def test_later_preserves_routing(self):
        self.config({'gateway':{'multiplex_profiles':True}})
        old=(self.root/'config.yaml').read_bytes();gw.configure(self.c,'later')
        self.assertEqual((self.root/'config.yaml').read_bytes(),old)
    def test_shared_only_enrolls_selected_profile_when_previously_disabled(self):
        self.config({'gateway':{'multiplex_profiles':False}})
        gw.configure(self.c,'shared')
        self.assertEqual(gw.routing(self.c)[1:],(True,['nova']))
        self.assertEqual(gw.status(self.c)['owner_home'],str(self.root))
    def test_dedicated_preserves_peers_and_excludes_selected(self):
        self.config({'gateway':{'multiplex_profiles':True}})
        gw.configure(self.c,'dedicated')
        self.assertEqual(gw.routing(self.c)[1:],(True,['rowan']))
    def test_legacy_keys_do_not_override_changes(self):
        self.config({'multiplex_profiles':True,'multiplex_profile_allowlist':['nova','rowan']})
        gw.configure(self.c,'dedicated')
        self.assertEqual(gw.routing(self.c)[1:],(True,['rowan']))
    def test_existing_dedicated_record_blocks_shared(self):
        (self.c.home/'gateway.pid').write_text('{"pid": 999}')
        with self.assertRaisesRegex(ValueError,'PID record'):gw.configure(self.c,'shared')
    def test_shared_cannot_install_a_second_service(self):
        gw.configure(self.c,'shared')
        with patch.object(gw.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'multiplexer'):gw.native(self.c,'install')
            run.assert_not_called()
    def test_routing_change_requires_restart_acknowledgment(self):
        self.config({'gateway':{'multiplex_profiles':True}});gw.configure(self.c,'dedicated')
        with self.assertRaisesRegex(ValueError,'Restart'):gw.native(self.c,'start')
    def test_native_actions_are_scoped_and_status_uses_owner(self):
        gw.configure(self.c,'shared')
        with patch.object(gw.subprocess,'run') as run:
            run.return_value.returncode=0
            gw.native(self.c,'status')
            self.assertEqual(run.call_args.kwargs['env']['HERMES_HOME'],str(self.root))
            gw.native(self.c,'setup')
            self.assertEqual(run.call_args.kwargs['env']['HERMES_HOME'],str(self.c.home))
    def test_original_installed_service_is_not_replaced(self):
        with patch.object(gw,'service_units',return_value=[{'scope':'system','unit':'original.service'}]):
            with self.assertRaisesRegex(ValueError,'installed service'):gw.native(self.c,'install')
    def test_root_cannot_disable_other_agents(self):
        self.config({'gateway':{'multiplex_profiles':True}})
        root=cc.Companion(hermes_root=self.root)
        with self.assertRaisesRegex(ValueError,'refusing'):gw.configure(root,'dedicated')
    def test_invalid_allowlist_fails_without_writing(self):
        self.config({'gateway':{'multiplex_profile_allowlist':'nova'}})
        with self.assertRaises(ValueError):gw.configure(self.c,'shared')
    def test_environment_override_cannot_silently_defeat_routing(self):
        with patch.dict(os.environ,{'GATEWAY_MULTIPLEX_PROFILES':'true'}):
            with self.assertRaisesRegex(ValueError,'override'):gw.configure(self.c,'dedicated')

    def test_five_agents_keep_separate_job_stores_and_prompt_homes(self):
        from test_cli import run,answers, CORE_JOBS, scripted_job_names
        for i in range(5):
            name='agent'+str(i)
            run('--home',str(self.root),'add',name,'--answers',answers(agent='Agent'+str(i),vault=str(self.root/'vault'),cron_active=False,gateway_mode='dedicated'),expect=0)
            home=self.root/'profiles'/name
            jobs=json.loads((home/'cron/jobs.json').read_text())['jobs']
            self.assertEqual(len(jobs),CORE_JOBS)
            self.assertTrue(all(not j['enabled'] for j in jobs if j['name'] not in
                                scripted_job_names('Agent'+str(i))))
            scripted=scripted_job_names('Agent'+str(i))
            for job in jobs:
                # A model-free job carries this profile's path in its generated
                # script rather than in a prompt, so check that instead.
                text=(job['prompt'] if job['name'] not in scripted
                      else (home/'scripts'/job['script']).read_text())
                self.assertIn(str(home).replace('\\','/'),text.replace('\\','/'))
                for other in range(5):
                    if other!=i:self.assertNotIn('profiles/agent'+str(other),text.replace('\\','/'))

    def test_repeated_setup_cannot_bypass_pending_root_restart(self):
        self.config({'gateway':{'multiplex_profiles':True}})
        gw.configure(self.c,'dedicated')
        self.assertTrue(gw.configure(self.c,'dedicated')['restart_required'])
        self.assertTrue(gw.configure(self.c,'later')['restart_required'])
        with self.assertRaisesRegex(ValueError,'Restart'):gw.native(self.c,'start')

    def seed_readiness(self):
        import sqlite3
        self.config({'gateway':{'multiplex_profiles':False}})
        (self.c.home/'config.yaml').write_text('model:\n  default: test-model\n')
        (self.c.home/'.env').write_text('TELEGRAM_BOT_TOKEN="test-only-token"\n')
        (self.c.home/'gateway.pid').write_text(json.dumps({'pid':123,'start_time':456}))
        (self.c.home/'gateway_state.json').write_text(json.dumps({'pid':123,'gateway_state':'running',
            'platforms':{'telegram':{'state':'connected','writer_pid':123}}}))
        with sqlite3.connect(self.c.home/'state.db') as db:
            db.executescript("CREATE TABLE sessions(id TEXT,source TEXT,started_at REAL); CREATE TABLE messages(session_id TEXT,role TEXT);")
            db.execute("INSERT INTO sessions VALUES ('one','telegram',1)")
            db.executemany('INSERT INTO messages VALUES (?,?)',[('one','user'),('one','assistant')])
        db.close()

    def test_ready_profile_preserves_existing_bot_without_network_calls(self):
        self.seed_readiness()
        with patch.object(gw,'_alive',return_value=True),patch.object(gw.subprocess,'run') as run:
            result=gw.preflight(self.c)
            self.assertTrue(result['ready']);run.assert_not_called()
            self.assertNotIn('test-only-token',json.dumps(result))

    def test_duplicate_tokens_are_flagged_without_disclosing_values(self):
        self.seed_readiness();(self.root/'.env').write_text('TELEGRAM_BOT_TOKEN=test-only-token\n')
        with patch.object(gw,'_alive',return_value=True):result=gw.preflight(self.c)
        self.assertFalse(result['checks']['unique_bot_token']);self.assertFalse(result['ready'])
        self.assertNotIn('test-only-token',json.dumps(result))

    def test_stale_process_record_is_not_ready(self):
        self.seed_readiness()
        with patch.object(gw,'_alive',return_value=False):result=gw.preflight(self.c)
        self.assertFalse(result['ready']);self.assertFalse(result['checks']['gateway_running'])

    def test_old_platform_writer_does_not_prove_current_connection(self):
        self.seed_readiness();p=self.c.home/'gateway_state.json';d=json.loads(p.read_text())
        d['platforms']['telegram']['writer_pid']=999;p.write_text(json.dumps(d))
        with patch.object(gw,'_alive',return_value=True):result=gw.preflight(self.c)
        self.assertFalse(result['checks']['telegram_connected'])

    def test_missing_first_exchange_is_reported(self):
        self.seed_readiness();(self.c.home/'state.db').unlink()
        with patch.object(gw,'_alive',return_value=True):result=gw.preflight(self.c)
        self.assertFalse(result['checks']['telegram_exchange_recorded'])
        self.assertIn('Send /start',' '.join(result['notes']))

    def test_windows_preflight_does_not_claim_unverified_liveness(self):
        self.seed_readiness()
        with patch.object(gw,'_alive',return_value=None):result=gw.preflight(self.c)
        self.assertFalse(result['ready']);self.assertIn('Native process verification',' '.join(result['notes']))

    def test_restart_uses_original_service_scope_and_exact_home(self):
        with patch.object(gw,'service_units',return_value=[{'scope':'system','unit':'original.service'}]),patch.object(gw.subprocess,'run') as run:
            run.return_value.returncode=0
            gw.native(self.c,'restart')
            self.assertEqual(run.call_args.args[0][-3:],['gateway','restart','--system'])
            self.assertEqual(run.call_args.kwargs['env']['HERMES_HOME'],str(self.c.home))

    def test_existing_profile_name_is_suggested_without_overwriting_identity(self):
        from test_cli import run,BASE,CORE_JOBS,scripted_job_names
        (self.c.home/'profile.yaml').write_text('display_name: Existing Name\n')
        data={**BASE,'vault':str(self.root/'vault')};data.pop('agent')
        run('--home',str(self.c.home),'init','--answers',json.dumps(data),expect=0)
        self.assertEqual(json.loads((self.c.home/'companion.json').read_text())['agent'],'Existing Name')

    def test_first_run_defaults_to_paused_until_hook_approval_and_restart(self):
        from test_cli import run,BASE,scripted_job_names
        data={**BASE,'vault':str(self.root/'vault')};data.pop('cron_active')
        out=run('--home',str(self.c.home),'init','--answers',json.dumps(data),expect=0)
        jobs=json.loads((self.c.home/'cron/jobs.json').read_text())['jobs']
        scripted=scripted_job_names()
        # Every job that would call a model starts paused. The model-free ones do
        # not: they are what keeps the present honest before anything is approved.
        self.assertTrue(all(not j['enabled'] for j in jobs if j['name'] not in scripted))
        self.assertTrue(all(j['enabled'] for j in jobs if j['name'] in scripted))
        self.assertIn('gateway --action restart',out.stdout)
