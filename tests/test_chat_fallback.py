"""Chat recovery swaps providers inside one native turn, never replays tools."""
import json
from types import SimpleNamespace

from kit.app.hermes_stream import configure_fallbacks


def test_installs_ordered_native_chain_and_reports_provider_switch(monkeypatch):
    chain = [
        {'provider': 'deepseek', 'model': 'secondary'},
        {'provider': 'ollama', 'model': 'local', 'base_url': 'http://127.0.0.1:11434/v1'},
    ]
    monkeypatch.setenv('TAMANITOMO_CHAT_FALLBACKS', json.dumps(chain))
    attempts, events = [], []
    agent = SimpleNamespace(provider='primary', _api_max_retries=3)

    def activate(*args, **kwargs):
        if agent._fallback_index == len(agent._fallback_chain):
            return False
        route = agent._fallback_chain[agent._fallback_index]
        agent._fallback_index += 1
        agent.provider = route['provider']
        return True

    agent._try_activate_fallback = activate
    configure_fallbacks(agent, lambda event, **fields: events.append(event))
    while True:
        attempts.append(agent.provider)
        if agent.provider == 'ollama':
            break
        assert agent._try_activate_fallback(reason="unavailable")
    assert attempts == ['primary', 'deepseek', 'ollama']
    assert events == ['fallback', 'fallback']
    assert agent._api_max_retries == 1
    assert agent._fallback_chain[-1]['base_url'] == 'http://127.0.0.1:11434/v1'


def test_no_override_preserves_native_configuration(monkeypatch):
    monkeypatch.delenv('TAMANITOMO_CHAT_FALLBACKS', raising=False)
    agent = SimpleNamespace(_fallback_chain=['native'])
    configure_fallbacks(agent, lambda *args, **kw: None)
    assert agent._fallback_chain == ['native']


def test_explicit_empty_chain_disables_stale_native_backups(monkeypatch):
    monkeypatch.setenv('TAMANITOMO_CHAT_FALLBACKS', '[]')
    agent = SimpleNamespace(_fallback_chain=['stale'], _try_activate_fallback=lambda: False)
    configure_fallbacks(agent, lambda *args, **kw: None)
    assert agent._fallback_chain == []
    assert agent._fallback_model is None


def test_older_native_runtime_keeps_its_quiet_cli_behavior(monkeypatch):
    monkeypatch.setenv('TAMANITOMO_CHAT_FALLBACKS', '[{"provider":"secondary","model":"backup"}]')
    agent = SimpleNamespace()
    configure_fallbacks(agent, lambda *args, **kw: None)
    assert not hasattr(agent, '_fallback_chain')


def test_local_adapter_and_profile_credentials_are_scoped(tmp_path, monkeypatch):
    import companion_config as cc
    from kit.app.runtime import _chat_fallbacks
    monkeypatch.delenv('SECONDARY_KEY', raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'primary-key-never-forwarded')
    c = cc.Companion(hermes_root=tmp_path / 'home', vault=tmp_path / 'vault')
    c.home.mkdir(parents=True)
    (c.home / '.env').write_text('SECONDARY_KEY=secondary-only\n')
    (c.home / 'config.yaml').write_text('model:\n  provider: openai\n  default: primary\n')
    c.models['fallbacks'] = [
        {'provider': 'deepseek', 'model': 'secondary', 'api_key_env': 'SECONDARY_KEY'},
        {'provider': 'ollama', 'model': 'local'},
    ]
    chain = _chat_fallbacks(c)
    assert chain[0]['api_key'] == 'secondary-only'
    assert chain[1]['provider'] == 'custom'
    assert chain[1]['api_key'] == 'no-key-required'
    assert chain[1]['base_url'] == 'http://127.0.0.1:11434/v1'
    assert 'primary-key-never-forwarded' not in json.dumps(chain)
