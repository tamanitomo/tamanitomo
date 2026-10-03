"""Regression contracts for automatic life and configured provider routing."""
import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

import companion_config as cc
import companion_free_models as free
import companion_inference as inference
import companion_routing as routing
import yaml

from kit.app.runtime import job_usage
from tests.support import WorkspaceFixture


def adapter():
    path = Path(__file__).resolve().parents[1] / 'kit/plugins/tamanitomo-routing/__init__.py'
    spec = importlib.util.spec_from_file_location('routing_adapter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pinned_cron_gets_chain_only_with_explicit_enrollment(tmp_path):
    scheduler = SimpleNamespace(_job_fallback_chain=lambda job, cfg: 'native policy')
    adapter().install(scheduler, lambda: tmp_path, free.expand)
    cfg = {'tamanitomo_routing': {'jobs': ['Nova pulse']}, 'fallback_providers': [
        {'provider': 'second', 'model': 'backup'}, {'provider': 'local', 'model': 'last'}]}
    job = {'name': 'Nova pulse', 'provider': 'openai-codex', 'model': 'gpt-5.6-luna'}
    assert scheduler._job_fallback_chain(job, cfg) == cfg['fallback_providers']
    assert scheduler._job_fallback_chain({**job, 'fallback_providers': []}, cfg) is None
    assert scheduler._job_fallback_chain({**job, 'name': 'Other job'}, cfg) == 'native policy'
    assert scheduler._job_fallback_chain(job, {}) == 'native policy'
    assert scheduler._job_fallback_chain({**job, 'no_agent': True}, cfg) == 'native policy'


def test_free_refresh_preserves_final_route_and_never_selects_paid_or_toolless(tmp_path):
    routes = [{'provider': 'primary', 'model': 'main'},
              {'provider': 'openrouter', 'model': 'openrouter/free'},
              {'provider': 'openrouter', 'model': 'retired:free'},
              {'provider': 'local', 'model': 'final'}]
    listed = [
        {'id': 'good:free', 'supported_parameters': ['tools'], 'pricing': {'prompt': '0', 'completion': '0'}},
        {'id': 'paid:free', 'supported_parameters': ['tools'], 'pricing': {'prompt': '0.01'}},
        {'id': 'no-tools:free', 'supported_parameters': []},
    ]
    with patch.object(free, 'listing', return_value=listed):
        out = free.expand(routes, tmp_path)
    assert [r['model'] for r in out] == ['main', 'good:free', 'openrouter/free', 'final']
    with patch.object(free, 'listing', return_value=None):
        assert free.expand(routes, tmp_path) == routes
    with patch.object(free, 'listing', return_value=[]):
        assert [r['model'] for r in free.expand(routes, tmp_path)] == ['main', 'openrouter/free', 'final']


def test_free_cache_throttles_failed_refresh_and_keeps_last_good_data(tmp_path):
    path = tmp_path / 'companion-free-models.json'
    path.write_text(json.dumps({'checked_at': 10, 'ok': True, 'data': [{'id': 'saved:free'}]}))
    with patch('urllib.request.urlopen', side_effect=OSError('offline')) as request:
        assert free.listing(tmp_path, now=30000) == [{'id': 'saved:free'}]
        assert free.listing(tmp_path, now=30001) == [{'id': 'saved:free'}]
        assert request.call_count == 1


class AutomaticRoutingApiTests(WorkspaceFixture):
    def setUp(self):
        super().setUp()
        self.backups = [{'provider': 'second', 'model': 'backup'}, {'provider': 'ollama', 'model': 'final'}]
        (self.c.home / 'config.yaml').write_text(yaml.safe_dump({'model': {
            'provider': 'custom', 'default': 'old', 'base_url': 'http://localhost:9000/v1', 'api_key': 'synthetic-old-key'},
            'fallback_providers': self.backups}))
        (self.root / 'auth.json').write_text(json.dumps({'active_provider': 'openai-codex'}))
        specs = json.loads((Path(__file__).resolve().parents[1] / 'kit/templates/cron/manifest.json').read_text())['jobs']
        self.jobs_path = self.c.home / 'cron/jobs.json'
        self.jobs_path.parent.mkdir()
        self.jobs_path.write_text(json.dumps({'jobs': [
            {'id': s['key'], 'name': s['name'].replace('{{AGENT}}', 'Nova'), 'enabled': False,
             'no_agent': s.get('no_agent', False), 'model': 'old', 'provider': 'custom',
             'base_url': 'http://localhost:9000/v1', 'last_run_at': 'history'} for s in specs]}))

    def test_codex_button_updates_shipped_jobs_by_workload_and_keeps_fallbacks(self):
        row = self.wait(self.post('/api/models/codex-preset'))
        assert row['status'] == 'complete', row
        cfg = yaml.safe_load((self.c.home / 'config.yaml').read_text())
        assert cfg['model']['default'] == 'gpt-5.6-sol'
        assert cfg['agent']['reasoning_effort'] == 'none'
        assert cfg['agent']['reasoning_overrides']['gpt-5.6-sol'] == 'none'
        assert 'base_url' not in cfg['model'] and 'api_key' not in cfg['model']
        assert cfg['fallback_providers'] == self.backups
        jobs = {j['id']: j for j in json.loads(self.jobs_path.read_text())['jobs']}
        for key, model, effort in [('pulse', 'gpt-5.6-luna', 'none'), ('autonomy', 'gpt-5.6-sol', 'low'),
                                   ('daily', 'gpt-5.6-sol', 'medium'), ('weekly', 'gpt-5.6-sol', 'high')]:
            assert (jobs[key]['provider'], jobs[key]['model'], jobs[key]['reasoning_effort']) == ('openai-codex', model, effort)
            assert not jobs[key]['base_url']
            assert jobs[key]['enabled'] is False and jobs[key]['last_run_at'] == 'history'
        assert jobs['dispatch']['model'] == 'old'  # no-agent jobs never contact it
        c = cc.load(self.c.home)
        assert inference.configured_routes(c, tier='loops')[0]['model'] == 'gpt-5.6-luna'
        assert 'tamanitomo-routing' in cfg['plugins']['enabled']
        # Native per-job overrides remain editable after the bulk preset.
        changed = self.wait(self.post('/api/jobs/pulse/edit', {'model': 'chosen', 'provider': 'other'}))
        assert changed['status'] == 'complete', changed

    def test_provider_preset_migrates_legacy_pinned_worker(self):
        data = json.loads(self.jobs_path.read_text())
        pulse = next(j for j in data['jobs'] if j['id'] == 'pulse')
        pulse.update(no_agent=True, script='companion-local-pulse.py', prompt='old hardcoded worker')
        self.jobs_path.write_text(json.dumps(data))
        row = self.wait(self.post('/api/models/codex-preset'))
        assert row['status'] == 'complete', row
        pulse = next(j for j in json.loads(self.jobs_path.read_text())['jobs'] if j['id'] == 'pulse')
        assert pulse['no_agent'] is False
        assert pulse['script'] == 'companion-pulse-preread.py'
        assert pulse['model'] == 'gpt-5.6-luna'
        assert (self.c.home / 'cron/prompt-backups/pulse-before-routing.md').read_text() == 'old hardcoded worker'

    def test_oauth_provider_state_is_recognized_without_being_the_active_provider(self):
        (self.root / 'auth.json').write_text(json.dumps({'active_provider': 'other', 'providers': {'openai-codex': {'access_token': 'synthetic'}}}))
        result = self.get('/api/models/providers').json()
        assert any(r['provider'] == 'openai-codex' and r['ready'] for r in result['providers'])
        row = self.wait(self.post('/api/models/codex-preset'))
        assert row['status'] == 'complete', row

    def test_codex_requires_signin_before_any_mutation(self):
        (self.root / 'auth.json').unlink()
        before = (self.c.home / 'config.yaml').read_bytes()
        response = self.post('/api/models/codex-preset')
        assert response.status_code == 400
        assert (self.c.home / 'config.yaml').read_bytes() == before

    def test_switch_preserves_native_fallback_credentials(self):
        cfg = yaml.safe_load((self.c.home / 'config.yaml').read_text())
        cfg['fallback_providers'][0]['api_key_env'] = 'MY_BACKUP_KEY'
        cfg['fallback_providers'][0]['api_mode'] = 'responses'
        (self.c.home / 'config.yaml').write_text(yaml.safe_dump(cfg))
        row = self.wait(self.post('/api/models/use-everywhere', {'provider': 'other', 'model': 'new'}))
        assert row['status'] == 'complete', row
        saved = yaml.safe_load((self.c.home / 'config.yaml').read_text())
        assert saved['fallback_providers'] == cfg['fallback_providers']


def test_usage_counts_input_and_output_across_compressed_runs(tmp_path):
    c = cc.Companion(hermes_root=tmp_path, vault=tmp_path / 'vault')
    con = sqlite3.connect(tmp_path / 'state.db')
    con.execute('CREATE TABLE sessions(id TEXT, source TEXT, started_at REAL, input_tokens INTEGER, output_tokens INTEGER, parent_session_id TEXT, api_call_count INTEGER)')
    con.executemany('INSERT INTO sessions VALUES(?,?,?,?,?,?,?)', [
        ('cron_pulse_20261002_120000', 'cron', 1000, 100, 20, None, 1),
        ('child', 'cron', 1010, 30, 7, 'cron_pulse_20261002_120000', 1),
        ('cron_other_20261002_120000', 'cron', 1000, 999, 999, None, 1),
    ])
    con.commit(); con.close()
    totals = job_usage(c, [{'id': 'pulse'}], now=1100)['jobs']['pulse']
    assert totals['last_run'] == 157
    assert totals['breakdown']['day'] == {'input': 130, 'output': 27}


def test_automatic_contact_and_quiet_drift_use_actual_owner_messages(tmp_path):
    import datetime as dt
    import companion_life as life
    import companion_quiet as quiet
    c = cc.Companion(hermes_root=tmp_path, vault=tmp_path / 'vault', timezone='UTC')
    now = dt.datetime(2026, 10, 2, 12, tzinfo=dt.timezone.utc)
    con = sqlite3.connect(tmp_path / 'state.db')
    con.execute('CREATE TABLE sessions(id TEXT, source TEXT, started_at REAL, profile_name TEXT)')
    con.execute('CREATE TABLE messages(id INTEGER, session_id TEXT, role TEXT, content TEXT, timestamp REAL)')
    con.executemany('INSERT INTO sessions VALUES(?,?,?,?)', [
        ('old-human', 'cli', now.timestamp()-86400*5, ''),
        ('cron', 'cron', now.timestamp(), ''),
        ('sibling', 'cli', now.timestamp(), 'other'),
        ('empty-chat', 'cli', now.timestamp(), ''),
    ])
    con.executemany('INSERT INTO messages VALUES(?,?,?,?,?)', [
        (1, 'old-human', 'user', 'Hello today', now.timestamp()-60),
        (2, 'cron', 'user', 'Reflect on the day', now.timestamp()-30),
        (3, 'sibling', 'user', 'Another person', now.timestamp()-20),
    ])
    con.commit();con.close()
    assert life.contact(c, '2026-10-02')['human_sessions'] == 1
    assert len(quiet.human_messages(c, now)) == 1
    assert life.contact(c, '2026-10-01')['human_sessions'] == 0


class UsageAuditApiTests(WorkspaceFixture):
    def test_native_cron_audit_schema_is_visible_and_unknown_is_not_zero(self):
        path = self.c.home / 'cron/usage_audit.jsonl'
        path.parent.mkdir()
        path.write_text('\n'.join(json.dumps(row) for row in [
            {'ts': '2026-10-02T12:00:00Z', 'prompt_tokens': 100, 'completion_tokens': 20},
            {'timestamp': '2026-10-02T13:00:00Z', 'input_tokens': 30, 'output_tokens': 7},
            {'ts': '2026-10-01T12:00:00Z', 'prompt_tokens': None, 'completion_tokens': None},
        ]))
        result = self.get('/api/cost').json()
        assert result['available']
        assert result['days'][-1] == {'day': '2026-10-02', 'input': 130, 'output': 27, 'runs': 2}
        assert result['days'][0]['input'] is None


def test_native_cron_and_gateway_refresh_when_free_bundle_is_primary(tmp_path):
    module = adapter()
    scheduler = SimpleNamespace(_job_fallback_chain=lambda j, c: None)
    loader = SimpleNamespace(get_fallback_chain=lambda c: c.get('fallback_providers', []))
    module.install(scheduler, lambda: tmp_path, free.expand)
    module.install_gateway(loader, lambda: tmp_path, free.expand)
    cfg = {'tamanitomo_routing': {'jobs': ['Nova pulse']},
           'model': {'provider': 'openrouter', 'default': 'openrouter/free'},
           'fallback_providers': [{'provider': 'openrouter', 'model': 'retired:free'}, {'provider': 'last', 'model': 'final'}]}
    job = {'name': 'Nova pulse', 'provider': 'openrouter', 'model': 'openrouter/free'}
    with patch.object(free, 'listing', return_value=[{'id': 'new:free', 'supported_parameters': ['tools']}]):
        assert [r['model'] for r in scheduler._job_fallback_chain(job, cfg)] == ['new:free', 'final']
        assert [r['model'] for r in loader.get_fallback_chain(cfg)] == ['new:free', 'final']
    cfg['plugins'] = {'disabled': ['tamanitomo-routing']}
    assert loader.get_fallback_chain(cfg) == cfg['fallback_providers']


def test_rollover_never_ends_a_sibling_profile_session(tmp_path):
    import datetime as dt
    import companion_rollover as rollover
    c = cc.Companion(hermes_root=tmp_path, profile='nova', vault=tmp_path/'vault')
    c.home.mkdir(parents=True)
    con = sqlite3.connect(c.home/'state.db')
    con.execute('CREATE TABLE sessions(id TEXT, source TEXT, started_at REAL, profile_name TEXT, end_reason TEXT, parent_session_id TEXT)')
    con.execute('CREATE TABLE messages(session_id TEXT, role TEXT, timestamp REAL)')
    con.executemany('INSERT INTO sessions VALUES(?,?,?,?,?,?)', [
        ('ours', 'telegram', 100, 'nova', None, None), ('theirs', 'telegram', 100, 'other', None, None)])
    con.commit();con.close()
    ended=[]
    with patch.object(rollover, 'routes', return_value={'ours:dm:1':'ours', 'bad:dm:2':'theirs'}), patch('companion_checkin.flag'):
        result=rollover.run(c, now=dt.datetime(2026,10,2,tzinfo=dt.timezone.utc), ender=lambda c,ids:ended.extend(ids))
    assert result['rolled']
    assert ended == ['ours']


def test_rollover_uses_store_launcher_when_no_venv_python(tmp_path):
    import json
    from types import SimpleNamespace
    from unittest.mock import patch
    import companion_rollover as rollover

    c = SimpleNamespace(home=tmp_path)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if '--print-runtime-command' in command:
            assert command[command.index('--module') + 1] == 'runpy'
            assert command[command.index('--') + 1] == 'rollover'
            return SimpleNamespace(returncode=0, stdout=json.dumps(
                ['store-python', '-I', '-c', 'import runpy; runpy.run_module("runpy", run_name="__main__")', 'rollover']))
        assert 'sys.path.insert' in command[3]
        assert kwargs['env']['HERMES_HOME'] == str(tmp_path)
        return SimpleNamespace(returncode=0)

    with patch.object(rollover, 'hermes_python', return_value=None), patch.object(rollover.subprocess, 'run', side_effect=run):
        rollover.end_sessions(c, ['fake-session'])
    assert len(calls) == 2
