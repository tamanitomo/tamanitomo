"""Realtime audio and explicit interruption stay inside the selected profile."""

import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI

from kit.app import realtime_speech as speech
from kit.app import runtime
from kit.app.hermes_stream import watch_cancellation
from tests.support import WorkspaceFixture


class Audio(httpx.AsyncByteStream):
    def __init__(self):
        self.closed = False

    async def __aiter__(self):
        yield b"\x01"
        yield b"\x02\x03\x04"

    async def aclose(self):
        self.closed = True


def client_factory(handler):
    original = httpx.AsyncClient
    return lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs)


class RealtimeAPI(WorkspaceFixture):
    def enable(self, profile="nova", **values):
        settings = {**speech.DEFAULTS, "enabled": True, **values}
        response = self.post("/api/voice-chat/settings", settings, profile)
        assert response.status_code == 200, response.text
        return response.json()

    def test_saved_settings_preserve_hermes_voice_and_hide_key(self):
        from kit.app.manage import config, save_config

        save_config(self.c.home, lambda c: c.update(tts={
            "provider": "pockettts", "pockettts": {"voice": "alba"},
            "realtime": {"api_key": "private-test-key"},
        }))
        self.enable()
        public = self.get("/api/voice-chat/settings").json()
        assert "private-test-key" not in json.dumps(public)
        saved = config(self.c.home)["tts"]
        assert saved["provider"] == "pockettts"
        assert saved["realtime"]["api_key"] == "private-test-key"
        assert not self.get("/api/voice-chat/settings", "rowan").json()["enabled"]

    def test_stream_uses_profile_voice_and_endpoint_without_cloud_keys(self):
        requests, audio = [], Audio()
        self.enable(base_url="http://speech.test:8771/v1", voice_ja="nova-ja")

        def upstream(request):
            requests.append(request)
            return httpx.Response(200, headers={"content-type": "audio/pcm"}, stream=audio)

        with patch.object(httpx, "AsyncClient", client_factory(upstream)):
            response = self.post("/api/voice-chat/stream", {"text": "こんにちは！"})
        assert response.status_code == 200, response.text
        assert response.content == b"\x01\x02\x03\x04"
        assert response.headers["x-audio-sample-rate"] == "24000"
        assert "content-encoding" not in response.headers
        assert audio.closed
        assert str(requests[0].url) == "http://speech.test:8771/v1/audio/speech"
        body = json.loads(requests[0].content)
        assert body["voice"] == "nova-ja"
        assert body["language"] == "Japanese"
        assert body["response_format"] == "pcm"
        assert "stream" not in body
        assert "authorization" not in requests[0].headers

    def test_openai_shaped_service_gets_standard_fields_and_named_key(self):
        (self.c.home / ".env").write_text("OPENAI_API_KEY=speech-test-key\n")
        saved = self.enable(
            base_url="https://speech.example/v1",
            model="gpt-4o-mini-tts",
            voice_en="coral",
            voice_ja="coral",
            api_key_env="OPENAI_API_KEY",
        )
        assert saved["has_api_key"]
        public = self.get("/api/voice-chat/settings").json()
        assert public["api_key_env"] == "OPENAI_API_KEY"
        assert "speech-test-key" not in json.dumps(public)
        requests = []

        def upstream(request):
            requests.append(request)
            return httpx.Response(200, headers={"content-type": "audio/pcm"}, stream=Audio())

        with patch.object(httpx, "AsyncClient", client_factory(upstream)):
            response = self.post("/api/voice-chat/stream", {"text": "こんにちは！"})
        assert response.status_code == 200, response.text
        assert json.loads(requests[0].content) == {
            "model": "gpt-4o-mini-tts",
            "voice": "coral",
            "input": "こんにちは！",
            "response_format": "pcm",
        }
        assert requests[0].headers["authorization"] == "Bearer speech-test-key"

    def test_missing_named_key_is_reported_not_invented(self):
        saved = self.enable(api_key_env="ROBIN_SPEECH_KEY")
        assert not saved["has_api_key"]
        requests = []

        def upstream(request):
            requests.append(request)
            return httpx.Response(200, headers={"content-type": "audio/pcm"}, stream=Audio())

        with patch.object(httpx, "AsyncClient", client_factory(upstream)):
            assert self.post("/api/voice-chat/stream", {"text": "hello"}).status_code == 200
        assert "authorization" not in requests[0].headers

    def test_auth_origin_and_profile_still_protect_stream(self):
        self.enable()
        with patch.object(httpx, "AsyncClient") as client:
            assert self.client.post("/api/voice-chat/stream", json={"text": "hello"}).status_code == 401
            assert self.client.post("/api/voice-chat/stream?profile=nova", json={"text": "hello"}, headers={**self.headers, "Origin": "https://evil.test"}).status_code == 403
            assert self.post("/api/voice-chat/stream", {"text": "hello"}, "rowan").status_code == 409
            assert self.post("/api/voice-chat/stream", {"text": "hello"}, "unknown").status_code == 400
            client.assert_not_called()

    def test_stream_allowed_during_chat_but_mutation_and_wrong_cancel_refused(self):
        self.enable()
        release = threading.Event()
        operation = self.app.state.operations.submit(str(self.root), "Chat", lambda report: release.wait(2), profile="nova", cancellable=True)
        try:
            assert self.post("/api/voice-chat/settings", speech.DEFAULTS).status_code == 409
            assert self.post(f"/api/chat/{operation['id']}/interrupt", profile="rowan").status_code == 404
            with patch.object(httpx, "AsyncClient", client_factory(lambda req: httpx.Response(200, headers={"content-type": "audio/pcm"}, stream=Audio()))):
                assert self.post("/api/voice-chat/stream", {"text": "hello"}).status_code == 200
            assert self.post(f"/api/chat/{operation['id']}/interrupt").status_code == 200
        finally:
            release.set()
        final = self.wait(SimpleNamespace(status_code=200, text="", json=lambda: operation))
        assert final["status"] == "cancelled"
        assert str(self.root) not in self.app.state.operations.busy

    def test_bad_upstream_releases_slot_and_hides_upstream_error(self):
        self.enable()
        with patch.object(httpx, "AsyncClient", client_factory(lambda req: httpx.Response(500, text="private upstream details"))):
            response = self.post("/api/voice-chat/stream", {"text": "hello"})
        assert response.status_code == 502
        assert "private upstream" not in response.text
        with patch.object(httpx, "AsyncClient", client_factory(lambda req: httpx.Response(200, headers={"content-type": "audio/pcm"}, stream=Audio()))):
            assert self.post("/api/voice-chat/stream", {"text": "again"}).status_code == 200

    def test_non_pcm_or_wrong_rate_is_refused(self):
        self.enable()
        for headers in ({"content-type": "audio/wav"}, {"content-type": "audio/pcm", "x-audio-sample-rate": "48000"}):
            with patch.object(httpx, "AsyncClient", client_factory(lambda req: httpx.Response(200, headers=headers, stream=Audio()))):
                assert self.post("/api/voice-chat/stream", {"text": "hello"}).status_code == 502


@pytest.mark.parametrize("changes", [
    {"base_url": "file:///etc/passwd"}, {"base_url": "http://robin@host/v1"},
    {"base_url": "http://host/v1?key=secret"}, {"enabled": "yes"},
    {"language": "other"}, {"voice_en": "bad\nvoice"}, {"api_key": "browser-key"},
    {"api_key_env": "lower_case"}, {"api_key_env": "KEY=value"}, {"api_key_env": "$HOME"},
])
def test_invalid_settings(changes):
    with pytest.raises(ValueError):
        speech.validate({**speech.DEFAULTS, **changes})


def test_closing_stream_stops_upstream_and_allows_next_request(tmp_path):
    (tmp_path / "config.yaml").write_text("tts:\n  realtime:\n    enabled: true\n")
    app = FastAPI()
    speech.register(app, lambda: (SimpleNamespace(home=lambda p: tmp_path), "nova"))
    endpoint = next(route.endpoint for route in app.routes if route.path == "/api/voice-chat/stream")
    audio = []

    def upstream(req):
        stream = Audio()
        audio.append(stream)
        return httpx.Response(200, headers={"content-type": "audio/pcm"}, stream=stream)

    async def run():
        request = SimpleNamespace(is_disconnected=lambda: asyncio.sleep(0, result=False))
        with patch.object(httpx, "AsyncClient", client_factory(upstream)):
            response = await endpoint({"text": "hello"}, request)
            assert await anext(response.body_iterator) == b"\x01"
            await response.body_iterator.aclose()
            assert audio[0].closed
            second = await endpoint({"text": "next"}, request)
            assert await anext(second.body_iterator) == b"\x01"
            await second.body_iterator.aclose()
            assert audio[1].closed
    asyncio.run(run())


def test_bridge_cancellation_calls_native_interrupt(tmp_path, monkeypatch):
    cancel = tmp_path / "cancel"
    done = threading.Event()
    monkeypatch.setenv("TAMANITOMO_CHAT_CANCEL_FILE", str(cancel))
    watch_cancellation(SimpleNamespace(interrupt=done.set))
    assert not done.is_set()
    cancel.touch()
    assert done.wait(1)


def test_runtime_cooperative_cancel_keeps_session_and_does_not_replay(tmp_path, monkeypatch):
    cancel = threading.Event()
    worker = tmp_path / "worker.py"
    worker.write_text('''import json,sys,time
from pathlib import Path
turn=json.loads(sys.stdin.readline())
while not Path(turn['cancel_file']).exists(): time.sleep(.01)
print(json.dumps({'event':'session','id':'same-session'}),flush=True)
print(json.dumps({'event':'final','text':'partial reply'}),flush=True)
''')
    rt = runtime.Runtime(tmp_path)
    monkeypatch.setattr(rt, "command", lambda: [sys.executable])
    monkeypatch.setattr(rt, "env", lambda home: {})
    monkeypatch.setattr(runtime, "_chat_fallbacks", lambda c: [])
    monkeypatch.setattr(runtime.cc, "load", lambda home: None)
    starts = []

    def take(python, env):
        starts.append(1)
        errors = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        process = subprocess.Popen([sys.executable, str(worker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True)
        return process, errors

    monkeypatch.setattr(runtime._warm_bridges, "take", take)
    monkeypatch.setattr(runtime._warm_bridges, "prepare", lambda *args: None)
    def report(message): pass
    report.stream = lambda message: None
    report.cancelled = cancel.is_set
    timer = threading.Timer(.05, cancel.set)
    timer.start()
    try:
        result = rt.chat(["chat", "hello"], tmp_path, report)
    finally:
        timer.cancel()
    assert result.interrupted
    assert result.session == "same-session"
    assert result.stdout == "partial reply"
    assert starts == [1]
