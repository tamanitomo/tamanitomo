"""Model probes exercise one explicit route without changing companion data."""
import io
import json
import time
from unittest.mock import patch
from urllib.parse import urlunsplit

from fastapi.testclient import TestClient
import pytest
import yaml

import companion_config as config
import companion_worker_model as worker
from kit.app.server import build


@pytest.fixture
def probe_workspace(tmp_path):
    home = tmp_path / 'hermes'
    vault = tmp_path / 'vault'
    home.mkdir()
    vault.mkdir()
    companion = config.Companion(hermes_root=home, vault=vault, context_mode='fixed')
    companion.save()
    (vault / 'Keep.md').write_text('Original note.\n', encoding='utf-8')
    (home / 'config.yaml').write_text(yaml.safe_dump({
        'model': {'provider': 'openrouter', 'default': 'primary-model',
                  'base_url': 'https://openrouter.ai/api/v1', 'api_key': 'fixture-native-key'},
        'fallback_providers': [{'provider': 'deepseek', 'model': 'backup-model'}],
        'terminal': {'backend': 'local'},
    }), encoding='utf-8')
    app = build(home, token='probe-token', state_dir=tmp_path / 'app-state')
    with TestClient(app) as client:
        yield client, home, vault
    app.state.operations.pool.shutdown(wait=True)


def snapshot(*roots):
    return {str(path): (path.read_bytes(), path.stat().st_mtime_ns)
            for root in roots for path in root.rglob('*') if path.is_file()}


def finish(client, response):
    assert response.status_code == 200, response.text
    ident = response.json()['id']
    for _ in range(500):
        response = client.get('/api/operations/' + ident, headers={'x-companion-token': 'probe-token'})
        assert response.status_code == 200, response.text
        row = response.json()
        if row['status'] != 'running':
            return row
        time.sleep(0.002)
    pytest.fail('The mocked probe operation did not finish')


def test_probe_calls_only_the_requested_route_and_preserves_saved_data(probe_workspace):
    client, home, vault = probe_workspace
    before = snapshot(home, vault)
    response = {'choices': [{'message': {'content': 'CONNECTION_OK'}, 'finish_reason': 'stop'}]}
    with patch('companion_worker_model.complete', wraps=worker.complete) as complete, patch(
        'urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())
    ) as request, patch('companion_worker_model._bridge') as bridge:
        row = finish(client, client.post('/api/models/probe',
            headers={'x-companion-token': 'probe-token'},
            json={'provider': 'custom', 'model': 'explicit-test', 'base_url': 'https://models.example.test/v1'}))
    assert row['status'] == 'complete'
    assert row['result']['model_requested'] == 'explicit-test'
    assert row['result']['response'] == 'CONNECTION_OK'
    complete.assert_called_once()
    companion, payload, route = complete.call_args.args
    assert companion.home == home
    assert route['model'] == 'explicit-test' and route['provider'] == 'custom'
    assert route['base_url'] == 'https://models.example.test/v1' and route['direct']
    assert 'api_key' not in route
    assert complete.call_args.kwargs['allow_fallback'] is False
    assert complete.call_args.kwargs['require_thinking'] is False
    assert payload['max_tokens'] == 64 and len(payload['messages']) == 1
    assert 'Original note' not in str(payload)
    request.assert_called_once()
    body = json.loads(request.call_args.args[0].data)
    assert body['max_tokens'] == 64 and 'reasoning_effort' not in body
    assert request.call_args.args[0].full_url == 'https://models.example.test/v1/chat/completions'
    bridge.assert_not_called()
    assert snapshot(home, vault) == before


def test_default_probe_uses_saved_route_and_provider_change_drops_old_url(probe_workspace):
    client, home, vault = probe_workspace
    before = snapshot(home, vault)
    with patch('companion_worker_model.complete', return_value={'content': 'CONNECTION_OK'}) as complete:
        for payload in ({}, {'provider': 'deepseek', 'model': 'explicit-model'},
                        {'base_url': 'https://different.example.test/v1'}):
            row = finish(client, client.post('/api/models/probe',
                headers={'x-companion-token': 'probe-token'}, json=payload))
            assert row['status'] == 'complete'
            assert 'fixture-native-key' not in json.dumps(row)
    first, second, third = [call.args[2] for call in complete.call_args_list]
    assert first['provider'] == 'openrouter' and first['model'] == 'primary-model'
    assert first['base_url'] == 'https://openrouter.ai/api/v1'
    assert first['api_key'] == 'fixture-native-key'
    assert second['provider'] == 'deepseek' and second['model'] == 'explicit-model'
    assert second['base_url'] == '' and not second['direct']
    assert 'api_key' not in second and 'api_key' not in third
    assert snapshot(home, vault) == before


def test_probe_failure_is_sanitized_and_does_not_fall_back(probe_workspace):
    client, home, vault = probe_workspace
    before = snapshot(home, vault)
    with patch('companion_worker_model.complete', side_effect=ValueError(
        'HTTP 429: api_key=private-test-credential'
    )) as complete:
        row = finish(client, client.post('/api/models/probe',
            headers={'x-companion-token': 'probe-token'}, json={}))
    assert row['status'] == 'failed'
    assert '429' in row['error'] and 'private-test-credential' not in row['error']
    complete.assert_called_once()
    assert complete.call_args.kwargs['allow_fallback'] is False
    assert snapshot(home, vault) == before


def test_probe_requires_auth_and_rejects_invalid_routes_without_requests(probe_workspace):
    client, home, vault = probe_workspace
    before = snapshot(home, vault)
    with patch('companion_worker_model.complete') as complete:
        assert client.post('/api/models/probe', json={}).status_code in (401, 403)
        for payload in ({'base_url': 'file:///secret'},
                        {'base_url': urlunsplit(('https', 'fixture-user:fixture-password@example.test', '/v1', '', ''))},
                        {'fallbacks': []}, {'model': ['invalid']}):
            response = client.post('/api/models/probe',
                headers={'x-companion-token': 'probe-token'}, json=payload)
            assert response.status_code == 400, response.text
        complete.assert_not_called()
    assert snapshot(home, vault) == before


def test_fallback_settings_validate_before_writing_and_preserve_order(probe_workspace):
    client, home, vault = probe_workspace
    headers = {'x-companion-token': 'probe-token'}
    before = snapshot(home, vault)
    for chain in ({'model': 'invalid-list'}, [{}],
                  [{'model': 'x', 'base_url': 'file:///secret'}],
                  [{'model': 'x'}] * 9):
        response = client.post('/api/environment', headers=headers, json={'fallbacks': chain})
        assert response.status_code == 400, response.text
        assert snapshot(home, vault) == before
    chain = [{'provider': 'deepseek', 'model': 'backup'},
             {'provider': 'custom', 'model': 'local', 'base_url': 'http://127.0.0.1:1234/v1'}]
    response = client.post('/api/environment', headers=headers, json={'fallbacks': chain})
    assert response.status_code == 200, response.text
    saved = yaml.safe_load((home / 'config.yaml').read_text())
    assert saved['fallback_providers'] == chain
    assert saved['terminal'] == {'backend': 'local'}
    assert saved['model']['default'] == 'primary-model'
    assert (vault / 'Keep.md').read_text() == 'Original note.\n'
