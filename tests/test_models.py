"""Configured provider cascades, isolated dry-run probes, and model settings."""

import dataclasses
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlunsplit

import companion_config as cc
import companion_config as config
import companion_inference as inference
import companion_local_reflection as reflection
import companion_text_provider as provider
import companion_worker_model as worker
import pytest
import yaml
from fastapi.testclient import TestClient

from kit.app.runtime import Runtime
from kit.app.server import build
from tests.support import WorkspaceFixture

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "home",
        vault=tmp_path / "vault",
        timezone="UTC",
    )
    c.home.mkdir(parents=True)
    return c


@contextmanager
def api(responses):
    calls = []

    class Handler(BaseHTTPRequestHandler):

        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(
                {
                    "path": self.path,
                    "body": body,
                    "authorization": self.headers.get("Authorization"),
                }
            )
            status = responses.get(self.path.split("/")[1], 200)
            if status == "timeout":
                time.sleep(0.12)
                status = 200
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            reply = {
                "choices": [
                    {"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3},
            }
            try:
                self.wfile.write(
                    json.dumps(
                        reply if status == 200 else {"error": "temporarily unavailable"}
                    ).encode()
                )
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=lambda: server.serve_forever(poll_interval=0.005), daemon=True
    )
    thread.start()
    try:
        yield (f"http://127.0.0.1:{server.server_port}", calls)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def route(base, name):
    return {"provider": name, "model": name + "-model", "base_url": base + "/" + name}


def payload():
    return {
        "messages": [{"role": "user", "content": "synthetic prompt"}],
        "max_tokens": 64,
    }


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_http_failure_advances_to_secondary_then_local(companion, status):
    with api({"primary": status, "secondary": 503}) as (base, calls):
        companion.models["fallbacks"] = [route(base, "secondary"), route(base, "local")]
        result = worker.complete(companion, payload(), route(base, "primary"))
    assert [call["path"] for call in calls] == [
        "/primary/chat/completions",
        "/secondary/chat/completions",
        "/local/chat/completions",
    ]
    assert result["model"] == "local-model"
    assert json.loads(result["content"]) == {"ok": True}


@pytest.mark.parametrize("status", [400, 401])
def test_invalid_request_or_credentials_do_not_silently_change_provider(
    companion, status
):
    with api({"primary": status}) as (base, calls):
        companion.models["fallbacks"] = [route(base, "local")]
        with pytest.raises(HTTPError) as failure:
            worker.complete(companion, payload(), route(base, "primary"))
    assert failure.value.code == status
    assert len(calls) == 1


def test_http_timeout_uses_configured_fallback(companion):
    with api({"primary": "timeout"}) as (base, calls):
        companion.models["fallbacks"] = [route(base, "local")]
        result = worker.complete(
            companion, payload(), route(base, "primary"), timeout=0.04
        )
    assert result["model"] == "local-model"
    assert len(calls) == 2


def test_configured_order_deduplicates_and_finishes_locally(companion):
    companion.models = {
        "chat": {"provider": "openrouter", "model": "primary"},
        "fallbacks": [{"provider": "deepseek", "model": "old"}],
    }
    (companion.home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "fallback_providers": [
                    {"provider": "ollama", "model": "qwen"},
                    {"provider": "deepseek", "model": "secondary"},
                    {"provider": "deepseek", "model": "secondary"},
                    {"provider": "lmstudio", "model": "small"},
                ]
            }
        ),
        encoding="utf-8",
    )
    routes = inference.configured_routes(companion)
    assert [row["model"] for row in routes] == ["primary", "secondary", "qwen", "small"]
    assert routes[2]["base_url"] == "http://127.0.0.1:11434/v1"
    assert routes[3]["base_url"] == "http://127.0.0.1:1234/v1"


def test_all_eight_fallbacks_and_custom_endpoints_survive_config_and_cli(companion):
    from kit.cli.models import write_fallbacks

    entries = [
        {
            "provider": "custom",
            "model": f"backup-{i}",
            "base_url": f"http://127.0.0.1:{8000 + i}/v1",
        }
        for i in range(8)
    ]
    c = dataclasses.replace(companion, models={"fallbacks": entries})
    assert c.fallbacks() == entries
    assert write_fallbacks(c, entries) == entries
    assert (
        yaml.safe_load((c.home / "config.yaml").read_text(encoding="utf-8"))[
            "fallback_providers"
        ]
        == entries
    )


@pytest.mark.parametrize(
    "entry",
    [
        {"provider": "deepseek"},
        {"model": "x", "base_url": "file:///tmp/model"},
        {"model": "x", "api_key_env": "a secret value"},
    ],
)
def test_invalid_fallback_entries_are_rejected(companion, entry):
    with pytest.raises(ValueError):
        dataclasses.replace(companion, models={"fallbacks": [entry]})


def test_loopback_worker_does_not_send_prompts_to_configured_cloud_fallback(
    companion, monkeypatch
):

    def cloud(*args, **kwargs):
        pytest.fail("The loopback-only worker must not call a cloud provider")

    monkeypatch.setattr(worker, "_bridge", cloud)
    with api({"primary": 503}) as (base, calls):
        companion.models["fallbacks"] = [
            {"provider": "deepseek", "model": "cloud"},
            route(base, "local"),
        ]
        result = worker.complete(
            companion, payload(), route(base, "primary"), allow_remote=False
        )
    assert result["model"] == "local-model"
    assert len(calls) == 2


def test_each_route_uses_only_its_own_profile_credential(companion, monkeypatch):
    monkeypatch.delenv("PRIMARY_TEST_KEY", raising=False)
    monkeypatch.delenv("BACKUP_TEST_KEY", raising=False)
    (companion.home / ".env").write_text(
        "PRIMARY_TEST_KEY=first-key\nBACKUP_TEST_KEY=second-key\n", encoding="utf-8"
    )
    with api({"primary": 429}) as (base, calls):
        companion.models["fallbacks"] = [
            {**route(base, "local"), "api_key_env": "BACKUP_TEST_KEY"}
        ]
        worker.complete(
            companion, payload(), route(base, "primary"), api_key_env="PRIMARY_TEST_KEY"
        )
    assert [call["authorization"] for call in calls] == [
        "Bearer first-key",
        "Bearer second-key",
    ]


def test_reflection_uses_same_fallback_cascade(companion):
    companion.soul.parent.mkdir(parents=True, exist_ok=True)
    companion.soul.write_text("A synthetic companion.", encoding="utf-8")
    with api({"primary": 503}) as (base, calls):
        companion.models["fallbacks"] = [route(base, "local")]
        result, usage = reflection.request_plan(
            companion,
            "daily",
            {"existing_questions": []},
            {},
            base + "/primary",
            "primary-model",
            1,
        )
    assert result == {"ok": True}
    assert usage["completion_tokens"] == 3
    assert len(calls) == 2


def test_bridge_preserves_transient_error_metadata(companion, monkeypatch):
    python = companion.hermes_root / "hermes-agent/venv/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(worker.cp, "venv_executable", lambda checkout: python)
    monkeypatch.setattr(
        worker.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args,
            1,
            'COMPANION_TEXT={"error":"overloaded","status_code":503,"transient":true}\n',
            "",
        ),
    )
    with pytest.raises(inference.ProviderFailure) as failure:
        worker._bridge(companion, {"timeout": 1})
    assert inference.is_transient(failure.value)
    assert failure.value.status_code == 503


def test_provider_does_not_retry_transient_failure_as_schema_rejection(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        raise HTTPError("https://example.invalid", 429, "rate limited", {}, None)

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )
    aux = types.ModuleType("agent.auxiliary_client")
    aux.resolve_provider_client = lambda **kwargs: (client, "model")
    monkeypatch.setitem(sys.modules, "agent", types.ModuleType("agent"))
    monkeypatch.setitem(sys.modules, "agent.auxiliary_client", aux)
    with pytest.raises(HTTPError):
        provider.chat(
            {
                "provider": "test",
                "model": "model",
                **payload(),
                "reasoning_effort": "high",
            }
        )
    assert len(calls) == 1


def test_provider_error_redacts_credentials():
    error = inference.ProviderFailure(
        "Authorization: Bearer secret-secret token=other-secret sk-1234567890abcdefgh {'api_key': 'quoted-secret'}",
        "503",
    )
    assert "secret-secret" not in str(error)
    assert "other-secret" not in str(error)
    assert "1234567890abcdefgh" not in str(error)
    assert "quoted-secret" not in str(error)
    assert inference.is_transient(error)


def test_native_credentials_and_api_adapter_survive_without_public_exposure(companion):
    (companion.home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "model": {
                    "provider": "custom",
                    "default": "primary",
                    "base_url": "https://example.invalid/v1",
                    "api_key": "saved-primary",
                    "api_mode": "chat_completions",
                },
                "fallback_providers": [
                    {
                        "provider": "custom",
                        "model": "backup",
                        "base_url": "http://127.0.0.1:1234/v1",
                        "api_key": "saved-backup",
                        "api_mode": "chat_completions",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    routes = inference.configured_routes(companion)
    assert inference.credential(companion, routes[0]) == "saved-primary"
    assert inference.credential(companion, routes[1]) == "saved-backup"
    assert routes[1]["api_mode"] == "chat_completions"
    with pytest.raises(ValueError, match="Unknown model tier field"):
        dataclasses.replace(
            companion, models={"chat": {"model": "x", "api_key": "secret"}}
        )


def test_native_adapter_receives_only_its_selected_endpoint_and_credential(
    companion, monkeypatch
):
    captured = {}

    def bridge(c, request):
        captured.update(request)
        return {"content": "ok"}

    monkeypatch.setattr(worker, "_bridge", bridge)
    primary = {
        "provider": "custom",
        "model": "test",
        "base_url": "https://example.invalid/v1",
        "api_key": "selected-key",
        "api_mode": "anthropic_messages",
    }
    worker.complete(companion, payload(), primary, allow_remote=True)
    assert captured["api_mode"] == "anthropic_messages"
    assert captured["base_url"] == primary["base_url"]
    assert captured["api_key"] == "selected-key"


def test_endpoint_fallbacks_never_borrow_primary_credentials(companion, monkeypatch):
    from kit.app.runtime import _chat_fallbacks

    monkeypatch.setenv("OPENAI_API_KEY", "primary-secret")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "named-provider-secret")
    monkeypatch.setenv("SECONDARY_ROUTE_KEY", "route-secret")
    (companion.home / "config.yaml").write_text(
        "model:\n  provider: openai\n  default: primary\n", encoding="utf-8"
    )
    companion.models["fallbacks"] = [
        {
            "provider": "custom",
            "model": "custom-local",
            "base_url": "http://127.0.0.1:1234/v1",
        },
        {"model": "endpoint-only", "base_url": "http://127.0.0.1:11434/v1"},
        {
            "provider": "custom",
            "model": "custom-remote",
            "base_url": "https://example.invalid/v1",
        },
        {"provider": "deepseek", "model": "named"},
        {
            "provider": "custom",
            "model": "authenticated",
            "base_url": "http://127.0.0.1:9999/v1",
            "api_key_env": "SECONDARY_ROUTE_KEY",
        },
    ]
    chain = {entry["model"]: entry for entry in _chat_fallbacks(companion)}
    for name in ("custom-local", "endpoint-only", "custom-remote"):
        assert chain[name]["api_key"] == "no-key-required"
    assert chain["endpoint-only"]["provider"] == "custom"
    assert chain["named"]["api_key"] == "named-provider-secret"
    assert chain["authenticated"]["api_key"] == "route-secret"
    assert "primary-secret" not in json.dumps(chain)
    with api({"primary": 503}) as (base, calls):
        companion.models["fallbacks"] = [
            {"provider": "custom", "model": "local", "base_url": base + "/local"}
        ]
        worker.complete(companion, payload(), route(base, "primary"))
    assert calls[-1]["authorization"] is None


def test_anthropic_endpoint_uses_native_adapter_unless_openai_mode_is_explicit(
    companion, monkeypatch
):
    replies = []

    def native(c, request):
        replies.append(request)
        return {"content": "native answer"}

    monkeypatch.setattr(worker, "_bridge", native)
    (companion.home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "model": {
                    "provider": "anthropic",
                    "default": "claude-test",
                    "base_url": "https://api.anthropic.com",
                }
            }
        ),
        encoding="utf-8",
    )
    result = worker.complete(
        companion, payload(), worker.resolve(companion), allow_remote=True
    )
    assert result["content"] == "native answer"
    assert replies[0]["provider"] == "anthropic"
    with api({}) as (base, calls):
        direct = {
            "provider": "anthropic",
            "model": "compatible",
            "base_url": base + "/compatible",
            "api_mode": "chat_completions",
        }
        worker.complete(companion, payload(), direct)
    assert len(replies) == 1
    assert len(calls) == 1


def test_rate_limited_schema_correction_cascades_instead_of_returning_invalid_answer(
    monkeypatch,
):
    attempted = []
    schema = {
        "type": "object",
        "required": ["mood"],
        "properties": {"mood": {"type": "string"}},
    }

    def reply(content):
        message = types.SimpleNamespace(content=content, reasoning_content=None)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=message, finish_reason="stop")],
            usage=None,
        )

    def resolve_client(provider, model):

        def create(**kwargs):
            attempted.append(provider)
            if provider == "primary" and attempted.count("primary") == 1:
                return reply('{"wrong": 1}')
            if provider == "primary":
                raise HTTPError("https://example.invalid", 429, "limited", {}, None)
            return reply('{"mood": "calm"}')

        return (
            types.SimpleNamespace(
                chat=types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=create)
                )
            ),
            model,
        )

    aux = types.ModuleType("agent.auxiliary_client")
    aux.resolve_provider_client = resolve_client
    monkeypatch.setitem(sys.modules, "agent", types.ModuleType("agent"))
    monkeypatch.setitem(sys.modules, "agent.auxiliary_client", aux)
    result = inference.cascade(
        [
            {"provider": "primary", "model": "first"},
            {"provider": "secondary", "model": "second"},
        ],
        lambda selected: provider.chat(
            {
                **selected,
                **payload(),
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"schema": schema},
                },
            }
        ),
    )
    assert json.loads(result["content"]) == {"mood": "calm"}
    assert attempted == ["primary", "primary", "secondary"]


@pytest.fixture
def probe_workspace(tmp_path):
    home = tmp_path / "hermes"
    vault = tmp_path / "vault"
    home.mkdir()
    vault.mkdir()
    companion = config.Companion(hermes_root=home, vault=vault, context_mode="fixed")
    companion.save()
    (vault / "Keep.md").write_text("Original note.\n", encoding="utf-8")
    (home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "model": {
                    "provider": "openrouter",
                    "default": "primary-model",
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key": "fixture-native-key",
                },
                "fallback_providers": [
                    {"provider": "deepseek", "model": "backup-model"}
                ],
                "terminal": {"backend": "local"},
            }
        ),
        encoding="utf-8",
    )
    app = build(home, token="probe-token", state_dir=tmp_path / "app-state")
    with TestClient(app) as client:
        yield (client, home, vault)
    app.state.operations.pool.shutdown(wait=True)


def snapshot(*roots):
    return {
        str(path): (path.read_bytes(), path.stat().st_mtime_ns)
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
    }


def finish(client, response):
    assert response.status_code == 200, response.text
    ident = response.json()["id"]
    for _ in range(500):
        response = client.get(
            "/api/operations/" + ident, headers={"x-companion-token": "probe-token"}
        )
        assert response.status_code == 200, response.text
        row = response.json()
        if row["status"] != "running":
            return row
        time.sleep(0.002)
    pytest.fail("The mocked probe operation did not finish")


def test_probe_calls_only_the_requested_route_and_preserves_saved_data(probe_workspace):
    client, home, vault = probe_workspace
    before = snapshot(home, vault)
    response = {
        "choices": [{"message": {"content": "CONNECTION_OK"}, "finish_reason": "stop"}]
    }
    with (
        patch("companion_worker_model.complete", wraps=worker.complete) as complete,
        patch(
            "urllib.request.urlopen",
            return_value=io.BytesIO(json.dumps(response).encode()),
        ) as request,
        patch("companion_worker_model._bridge") as bridge,
    ):
        row = finish(
            client,
            client.post(
                "/api/models/probe",
                headers={"x-companion-token": "probe-token"},
                json={
                    "provider": "custom",
                    "model": "explicit-test",
                    "base_url": "https://models.example.test/v1",
                },
            ),
        )
    assert row["status"] == "complete"
    assert row["result"]["model_requested"] == "explicit-test"
    assert row["result"]["response"] == "CONNECTION_OK"
    complete.assert_called_once()
    companion, payload, route = complete.call_args.args
    assert companion.home == home
    assert route["model"] == "explicit-test" and route["provider"] == "custom"
    assert route["base_url"] == "https://models.example.test/v1" and route["direct"]
    assert "api_key" not in route
    assert complete.call_args.kwargs["allow_fallback"] is False
    assert complete.call_args.kwargs["require_thinking"] is False
    assert payload["max_tokens"] == 64 and len(payload["messages"]) == 1
    assert "Original note" not in str(payload)
    request.assert_called_once()
    body = json.loads(request.call_args.args[0].data)
    assert body["max_tokens"] == 64 and "reasoning_effort" not in body
    assert (
        request.call_args.args[0].full_url
        == "https://models.example.test/v1/chat/completions"
    )
    bridge.assert_not_called()
    assert snapshot(home, vault) == before


def test_default_probe_uses_saved_route_and_provider_change_drops_old_url(
    probe_workspace,
):
    client, home, vault = probe_workspace
    before = snapshot(home, vault)
    with patch(
        "companion_worker_model.complete", return_value={"content": "CONNECTION_OK"}
    ) as complete:
        for payload in (
            {},
            {"provider": "deepseek", "model": "explicit-model"},
            {"base_url": "https://different.example.test/v1"},
        ):
            row = finish(
                client,
                client.post(
                    "/api/models/probe",
                    headers={"x-companion-token": "probe-token"},
                    json=payload,
                ),
            )
            assert row["status"] == "complete"
            assert "fixture-native-key" not in json.dumps(row)
    first, second, third = [call.args[2] for call in complete.call_args_list]
    assert first["provider"] == "openrouter" and first["model"] == "primary-model"
    assert first["base_url"] == "https://openrouter.ai/api/v1"
    assert first["api_key"] == "fixture-native-key"
    assert second["provider"] == "deepseek" and second["model"] == "explicit-model"
    assert second["base_url"] == "" and (not second["direct"])
    assert "api_key" not in second and "api_key" not in third
    assert snapshot(home, vault) == before


def test_probe_failure_is_sanitized_and_does_not_fall_back(probe_workspace):
    client, home, vault = probe_workspace
    before = snapshot(home, vault)
    with patch(
        "companion_worker_model.complete",
        side_effect=ValueError("HTTP 429: api_key=private-test-credential"),
    ) as complete:
        row = finish(
            client,
            client.post(
                "/api/models/probe",
                headers={"x-companion-token": "probe-token"},
                json={},
            ),
        )
    assert row["status"] == "failed"
    assert "429" in row["error"] and "private-test-credential" not in row["error"]
    complete.assert_called_once()
    assert complete.call_args.kwargs["allow_fallback"] is False
    assert snapshot(home, vault) == before


def test_probe_requires_auth_and_rejects_invalid_routes_without_requests(
    probe_workspace,
):
    client, home, vault = probe_workspace
    before = snapshot(home, vault)
    with patch("companion_worker_model.complete") as complete:
        assert client.post("/api/models/probe", json={}).status_code in (401, 403)
        for payload in (
            {"base_url": "file:///secret"},
            {
                "base_url": urlunsplit(
                    (
                        "https",
                        "fixture-user:fixture-password@example.test",
                        "/v1",
                        "",
                        "",
                    )
                )
            },
            {"fallbacks": []},
            {"model": ["invalid"]},
        ):
            response = client.post(
                "/api/models/probe",
                headers={"x-companion-token": "probe-token"},
                json=payload,
            )
            assert response.status_code == 400, response.text
        complete.assert_not_called()
    assert snapshot(home, vault) == before


def test_fallback_settings_validate_before_writing_and_preserve_order(probe_workspace):
    client, home, vault = probe_workspace
    headers = {"x-companion-token": "probe-token"}
    before = snapshot(home, vault)
    for chain in (
        {"model": "invalid-list"},
        [{}],
        [{"model": "x", "base_url": "file:///secret"}],
        [{"model": "x"}] * 9,
    ):
        response = client.post(
            "/api/environment", headers=headers, json={"fallbacks": chain}
        )
        assert response.status_code == 400, response.text
        assert snapshot(home, vault) == before
    chain = [
        {"provider": "deepseek", "model": "backup"},
        {
            "provider": "custom",
            "model": "local",
            "base_url": "http://127.0.0.1:1234/v1",
        },
    ]
    response = client.post(
        "/api/environment", headers=headers, json={"fallbacks": chain}
    )
    assert response.status_code == 200, response.text
    saved = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert saved["fallback_providers"] == chain
    assert saved["terminal"] == {"backend": "local"}
    assert saved["model"]["default"] == "primary-model"
    assert (vault / "Keep.md").read_text(encoding="utf-8") == "Original note.\n"


BUDGET_WINDOWS = [2048, 4096, 8192, 16384, 32768, 65536, 131072, 200192, 272000, 900000]


class DynamicContextTests(unittest.TestCase):

    def test_reload_follows_model_changes_and_fixed_mode_preserves_override(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            (home / "companion.json").write_text(
                json.dumps({"context_tokens": 65536}), encoding="utf-8"
            )
            (home / "config.yaml").write_text(
                "model:\n  default: first\n  provider: example\n  base_url: https://api.example.test/v1\n",
                encoding="utf-8",
            )
            (home / "models_dev_cache.json").write_text(
                json.dumps(
                    {
                        "example": {
                            "api": "https://api.example.test",
                            "models": {
                                "first": {"limit": {"context": 1000000}},
                                "second": {"limit": {"context": 8192}},
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(cc.load(home).context_tokens, 1000000)
            (home / "config.yaml").write_text(
                "model:\n  default: second\n  provider: example\n  base_url: https://api.example.test/v1\n",
                encoding="utf-8",
            )
            self.assertEqual(cc.load(home).context_tokens, 8192)
            (home / "companion.json").write_text(
                json.dumps({"context_tokens": 32768, "context_mode": "fixed"}),
                encoding="utf-8",
            )
            self.assertEqual(cc.load(home).context_tokens, 32768)

    def test_other_endpoints_do_not_inherit_native_model_capacity(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            (home / "config.yaml").write_text(
                "model:\n  default: first\n  provider: example\n  base_url: https://other.example.test/v1\n",
                encoding="utf-8",
            )
            (home / "context_length_cache.yaml").write_text(
                "context_lengths:\n  first@https://api.example.test/v1: 1000000\n",
                encoding="utf-8",
            )
            (home / "models_dev_cache.json").write_text(
                json.dumps(
                    {
                        "example": {
                            "api": "https://api.example.test",
                            "models": {"first": {"limit": {"context": 1000000}}},
                        }
                    }
                ),
                encoding="utf-8",
            )
            value, source = cc.detect_context_tokens(home)
            self.assertFalse(cc.detected_for_real(source))
            (home / "config.yaml").write_text(
                "model:\n  context_length: 8192\n", encoding="utf-8"
            )
            self.assertEqual(cc.detect_context_tokens(home)[0], 8192)


class RemotePinTests(unittest.TestCase):

    def test_valid_pins_are_accepted(self):
        c1 = cc.Companion(remote_pin="1234")
        self.assertEqual(c1.remote_pin, "1234")
        c2 = cc.Companion(remote_pin="0000")
        self.assertEqual(c2.remote_pin, "0000")
        c3 = cc.Companion(remote_pin="")
        self.assertEqual(c3.remote_pin, "")

    def test_invalid_pins_raise_value_error(self):
        for bad in ("123", "12345", "abcd", "12a4", "", "-123", " 123"):
            if bad == "":
                continue
            with self.assertRaises(ValueError):
                cc.Companion(remote_pin=bad)

    def test_remote_pin_serializes_and_round_trips(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        home = tmp / ".hermes"
        c = cc.Companion(hermes_root=home, remote_pin="9876")
        c.save()
        loaded = cc.load(c.home)
        self.assertEqual(loaded.remote_pin, "9876")


class ModelsApiTests(WorkspaceFixture):

    def test_model_configuration_preserves_unrelated_keys_and_hides_secrets(self):
        before = {
            "model": {
                "default": "old",
                "provider": "openrouter",
                "api_key": "private-inline",
                "context_length": 32768,
            },
            "unrelated": {"keep": True},
            "hooks": {"x": "echo hello"},
        }
        (self.c.home / "config.yaml").write_text(
            yaml.safe_dump(before), encoding="utf-8"
        )
        response = self.post(
            "/api/environment",
            {
                "model": {"model": "new", "provider": "openrouter"},
                "fallbacks": [{"provider": "anthropic", "model": "backup"}],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        after = yaml.safe_load(
            (self.c.home / "config.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(after["unrelated"], before["unrelated"])
        self.assertEqual(after["model"]["context_length"], 32768)
        self.assertEqual(after["hooks"], before["hooks"])
        self.assertNotIn("private-inline", self.get("/api/environment").text)
        self.assertTrue(list((self.c.home / "companion-config-backups").iterdir()))

    def test_invalid_model_config_does_not_write(self):
        for payload in (
            {"model": {"provider": "x"}},
            {"model": {"model": "x", "base_url": "file:///etc/passwd"}},
            {"fallbacks": [{}] * 9},
            {"secret": "oops"},
        ):
            self.assertEqual(self.post("/api/environment", payload).status_code, 400)
        self.assertFalse((self.c.home / "config.yaml").exists())

    def test_credentials_are_write_only_and_preserve_other_values(self):
        (self.c.home / ".env").write_text(
            "KEEP=value\nOPENROUTER_API_KEY=old\n", encoding="utf-8"
        )
        with patch.object(Runtime, "catalog", return_value=[]):
            response = self.post(
                "/api/credentials",
                {"name": "OPENROUTER_API_KEY", "value": "a-private-key"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertNotIn("a-private-key", self.get("/api/providers").text)
        self.assertIn("KEEP=value", (self.c.home / ".env").read_text(encoding="utf-8"))
        self.assertEqual(
            self.post(
                "/api/credentials", {"name": "PATH", "value": "/bad"}
            ).status_code,
            400,
        )
        if os.name != "nt":
            self.assertEqual((self.c.home / ".env").stat().st_mode & 511, 384)
