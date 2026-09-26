"""Configured inference cascades, using synthetic HTTP responses and no live models."""
from contextlib import contextmanager
import dataclasses
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import types
from urllib.error import HTTPError

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'kit/scripts'))
sys.path.insert(0, str(ROOT))

import companion_config as cc
import companion_inference as inference
import companion_local_reflection as reflection
import companion_text_provider as provider
import companion_worker_model as worker


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(agent='Nova', human='Robin', hermes_root=tmp_path / 'home',
                     vault=tmp_path / 'vault', timezone='UTC')
    c.home.mkdir(parents=True)
    return c


@contextmanager
def api(responses):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append({'path': self.path, 'body': body, 'authorization': self.headers.get('Authorization')})
            status = responses.get(self.path.split('/')[1], 200)
            if status == 'timeout':
                time.sleep(.12)
                status = 200
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            reply = {'choices': [{'message': {'content': '{"ok": true}'}, 'finish_reason': 'stop'}],
                     'usage': {'prompt_tokens': 2, 'completion_tokens': 3}}
            try:
                self.wfile.write(json.dumps(reply if status == 200 else {'error': 'temporarily unavailable'}).encode())
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.005), daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def route(base, name):
    return {'provider': name, 'model': name + '-model', 'base_url': base + '/' + name}


def payload():
    return {'messages': [{'role': 'user', 'content': 'synthetic prompt'}], 'max_tokens': 64}


@pytest.mark.parametrize('status', [429, 500, 502, 503, 504])
def test_transient_http_failure_advances_to_secondary_then_local(companion, status):
    with api({'primary': status, 'secondary': 503}) as (base, calls):
        companion.models['fallbacks'] = [route(base, 'secondary'), route(base, 'local')]
        result = worker.complete(companion, payload(), route(base, 'primary'))
    assert [call['path'] for call in calls] == ['/primary/chat/completions', '/secondary/chat/completions', '/local/chat/completions']
    assert result['model'] == 'local-model'
    assert json.loads(result['content']) == {'ok': True}


@pytest.mark.parametrize('status', [400, 401])
def test_invalid_request_or_credentials_do_not_silently_change_provider(companion, status):
    with api({'primary': status}) as (base, calls):
        companion.models['fallbacks'] = [route(base, 'local')]
        with pytest.raises(HTTPError) as failure:
            worker.complete(companion, payload(), route(base, 'primary'))
    assert failure.value.code == status
    assert len(calls) == 1


def test_http_timeout_uses_configured_fallback(companion):
    with api({'primary': 'timeout'}) as (base, calls):
        companion.models['fallbacks'] = [route(base, 'local')]
        result = worker.complete(companion, payload(), route(base, 'primary'), timeout=.04)
    assert result['model'] == 'local-model'
    assert len(calls) == 2


def test_configured_order_deduplicates_and_finishes_locally(companion):
    companion.models = {'chat': {'provider': 'openrouter', 'model': 'primary'},
                        'fallbacks': [{'provider': 'deepseek', 'model': 'old'}]}
    (companion.home / 'config.yaml').write_text(yaml.safe_dump({'fallback_providers': [
        {'provider': 'ollama', 'model': 'qwen'}, {'provider': 'deepseek', 'model': 'secondary'},
        {'provider': 'deepseek', 'model': 'secondary'}, {'provider': 'lmstudio', 'model': 'small'},
    ]}))
    routes = inference.configured_routes(companion)
    assert [row['model'] for row in routes] == ['primary', 'secondary', 'qwen', 'small']
    assert routes[2]['base_url'] == 'http://127.0.0.1:11434/v1'
    assert routes[3]['base_url'] == 'http://127.0.0.1:1234/v1'


def test_all_eight_fallbacks_and_custom_endpoints_survive_config_and_cli(companion):
    from kit.cli.models import write_fallbacks
    entries = [{'provider': 'custom', 'model': f'backup-{i}', 'base_url': f'http://127.0.0.1:{8000+i}/v1'}
               for i in range(8)]
    c = dataclasses.replace(companion, models={'fallbacks': entries})
    assert c.fallbacks() == entries
    assert write_fallbacks(c, entries) == entries
    assert yaml.safe_load((c.home / 'config.yaml').read_text())['fallback_providers'] == entries


@pytest.mark.parametrize('entry', [{'provider': 'deepseek'}, {'model': 'x', 'base_url': 'file:///tmp/model'},
                                  {'model': 'x', 'api_key_env': 'a secret value'}])
def test_invalid_fallback_entries_are_rejected(companion, entry):
    with pytest.raises(ValueError):
        dataclasses.replace(companion, models={'fallbacks': [entry]})


def test_loopback_worker_does_not_send_prompts_to_configured_cloud_fallback(companion, monkeypatch):
    def cloud(*args, **kwargs):
        pytest.fail('The loopback-only worker must not call a cloud provider')

    monkeypatch.setattr(worker, '_bridge', cloud)
    with api({'primary': 503}) as (base, calls):
        companion.models['fallbacks'] = [{'provider': 'deepseek', 'model': 'cloud'}, route(base, 'local')]
        result = worker.complete(companion, payload(), route(base, 'primary'), allow_remote=False)
    assert result['model'] == 'local-model'
    assert len(calls) == 2


def test_each_route_uses_only_its_own_profile_credential(companion, monkeypatch):
    monkeypatch.delenv('PRIMARY_TEST_KEY', raising=False)
    monkeypatch.delenv('BACKUP_TEST_KEY', raising=False)
    (companion.home / '.env').write_text('PRIMARY_TEST_KEY=first-key\nBACKUP_TEST_KEY=second-key\n')
    with api({'primary': 429}) as (base, calls):
        companion.models['fallbacks'] = [{**route(base, 'local'), 'api_key_env': 'BACKUP_TEST_KEY'}]
        worker.complete(companion, payload(), route(base, 'primary'), api_key_env='PRIMARY_TEST_KEY')
    assert [call['authorization'] for call in calls] == ['Bearer first-key', 'Bearer second-key']


def test_reflection_uses_same_fallback_cascade(companion):
    companion.soul.parent.mkdir(parents=True, exist_ok=True)
    companion.soul.write_text('A synthetic companion.')
    with api({'primary': 503}) as (base, calls):
        companion.models['fallbacks'] = [route(base, 'local')]
        result, usage = reflection.request_plan(companion, 'daily', {'existing_questions': []}, {},
                                               base + '/primary', 'primary-model', 1)
    assert result == {'ok': True}
    assert usage['completion_tokens'] == 3
    assert len(calls) == 2


def test_bridge_preserves_transient_error_metadata(companion, monkeypatch):
    python = companion.hermes_root / 'hermes-agent/venv/bin/python'
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(worker.cp, 'venv_executable', lambda checkout: python)
    monkeypatch.setattr(worker.subprocess, 'run', lambda *args, **kwargs: subprocess.CompletedProcess(
        args, 1, 'COMPANION_TEXT={"error":"overloaded","status_code":503,"transient":true}\n', ''))
    with pytest.raises(inference.ProviderFailure) as failure:
        worker._bridge(companion, {'timeout': 1})
    assert inference.is_transient(failure.value)
    assert failure.value.status_code == 503


def test_provider_does_not_retry_transient_failure_as_schema_rejection(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        raise HTTPError('https://example.invalid', 429, 'rate limited', {}, None)

    client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
    aux = types.ModuleType('agent.auxiliary_client')
    aux.resolve_provider_client = lambda **kwargs: (client, 'model')
    monkeypatch.setitem(sys.modules, 'agent', types.ModuleType('agent'))
    monkeypatch.setitem(sys.modules, 'agent.auxiliary_client', aux)
    with pytest.raises(HTTPError):
        provider.chat({'provider': 'test', 'model': 'model', **payload(), 'reasoning_effort': 'high'})
    assert len(calls) == 1


def test_provider_error_redacts_credentials():
    error = inference.ProviderFailure("Authorization: Bearer secret-secret token=other-secret "
                                      "sk-1234567890abcdefgh {'api_key': 'quoted-secret'}", '503')
    assert 'secret-secret' not in str(error)
    assert 'other-secret' not in str(error)
    assert '1234567890abcdefgh' not in str(error)
    assert 'quoted-secret' not in str(error)
    assert inference.is_transient(error)


def test_native_credentials_and_api_adapter_survive_without_public_exposure(companion):
    (companion.home / 'config.yaml').write_text(yaml.safe_dump({
        'model': {'provider': 'custom', 'default': 'primary', 'base_url': 'https://example.invalid/v1',
                  'api_key': 'saved-primary', 'api_mode': 'chat_completions'},
        'fallback_providers': [{'provider': 'custom', 'model': 'backup', 'base_url': 'http://127.0.0.1:1234/v1',
                                'api_key': 'saved-backup', 'api_mode': 'chat_completions'}],
    }))
    routes = inference.configured_routes(companion)
    assert inference.credential(companion, routes[0]) == 'saved-primary'
    assert inference.credential(companion, routes[1]) == 'saved-backup'
    assert routes[1]['api_mode'] == 'chat_completions'
    with pytest.raises(ValueError, match='Unknown model tier field'):
        dataclasses.replace(companion, models={'chat': {'model': 'x', 'api_key': 'secret'}})


def test_native_adapter_receives_only_its_selected_endpoint_and_credential(companion, monkeypatch):
    captured = {}

    def bridge(c, request):
        captured.update(request)
        return {'content': 'ok'}

    monkeypatch.setattr(worker, '_bridge', bridge)
    primary = {'provider': 'custom', 'model': 'test', 'base_url': 'https://example.invalid/v1',
               'api_key': 'selected-key', 'api_mode': 'anthropic_messages'}
    worker.complete(companion, payload(), primary, allow_remote=True)
    assert captured['api_mode'] == 'anthropic_messages'
    assert captured['base_url'] == primary['base_url']
    assert captured['api_key'] == 'selected-key'
