"""Small, profile-scoped client for a separately managed PCM speech service.

This never loads a model or changes Hermes's conversation or voice-note provider.
The browser receives audio through the workspace's existing authenticated boundary.
"""

from urllib.parse import urlsplit
import re

DEFAULTS = {
    "enabled": False,
    "base_url": "http://127.0.0.1:8771/v1",
    "model": "qwen3-tts-12hz-1.7b-base",
    "voice_en": "companion-en",
    "voice_ja": "companion-ja",
    "language": "auto",
    "api_key_env": "",
}
LANGUAGES = {"auto", "English", "Japanese"}


def validate(values):
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise ValueError("Unsupported realtime voice setting")
    clean = {**DEFAULTS, **values}
    if not isinstance(clean["enabled"], bool):
        raise ValueError("Enabled must be true or false")
    for key in ("base_url", "model", "voice_en", "voice_ja", "language"):
        value = clean[key]
        if not isinstance(value, str) or not value.strip() or len(value) > 1000:
            raise ValueError("Invalid realtime voice " + key)
        if any(ord(c) < 32 for c in value):
            raise ValueError("Invalid realtime voice " + key)
        clean[key] = value.strip()
    parsed = urlsplit(clean["base_url"])
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Use an HTTP(S) speech API base URL without credentials or query"
        )
    try:
        parsed.port
    except ValueError:
        raise ValueError("Invalid speech API port") from None
    clean["base_url"] = clean["base_url"].rstrip("/")
    if clean["language"] not in LANGUAGES:
        raise ValueError("Choose auto, English or Japanese")
    # The key itself never crosses the browser boundary: only the name of a
    # variable in the profile's .env, as image presets already do.
    name = clean["api_key_env"]
    if not isinstance(name, str) or not re.fullmatch(
        r"(?:[A-Z][A-Z0-9_]{0,99})?", name.strip()
    ):
        raise ValueError("Use an environment variable name such as OPENAI_API_KEY")
    clean["api_key_env"] = name.strip()
    return clean


def api_key(home, raw):
    """Server-side only: a hand-set key, else the named .env variable."""
    import os

    if raw.get("api_key"):
        return str(raw["api_key"])
    name = raw.get("api_key_env")
    if not isinstance(name, str) or not name:
        return ""
    from companion_gateway import _env_values

    return str(_env_values(home).get(name) or os.environ.get(name) or "")


def settings(home):
    from .manage import config

    raw = (config(home).get("tts") or {}).get("realtime") or {}
    if not isinstance(raw, dict):
        raise ValueError("Invalid realtime speech settings")
    return validate({k: v for k, v in raw.items() if k in DEFAULTS})


def speech_request(settings, payload):
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise ValueError("Speech must contain 1–1,000 characters")
    language = payload.get("language") or settings["language"]
    if language not in LANGUAGES:
        raise ValueError("Choose auto, English or Japanese")
    if language == "auto":
        language = (
            "Japanese"
            if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text)
            else "English"
        )
    body = {
        "model": settings["model"],
        "voice": settings["voice_ja" if language == "Japanese" else "voice_en"],
        "input": text.strip(),
        "response_format": "pcm",
    }
    # Qwen3-TTS servers take these; OpenAI-shaped services reject unknown fields.
    if settings["model"].lower().startswith("qwen3-tts"):
        body.update(language=language, max_new_tokens=512)
    return body


def register(app, select):
    from fastapi import HTTPException, Request
    from fastapi.responses import StreamingResponse
    from starlette.background import BackgroundTask
    import httpx
    import anyio
    import threading

    # Gufo owns one model and generation slot. Fail promptly instead of piling
    # up voices from multiple tabs/profiles behind stale requests.
    slot = threading.BoundedSemaphore(1)

    def public(home, saved):
        from .manage import config

        raw = (config(home).get("tts") or {}).get("realtime") or {}
        return {
            **saved,
            "sample_rate": 24000,
            "configured": saved["enabled"],
            "has_api_key": bool(api_key(home, {**raw, **saved})),
        }

    @app.get("/api/voice-chat/settings")
    def get_settings():
        rt, profile = select()
        home = rt.home(profile)
        return public(home, settings(home))

    @app.post("/api/voice-chat/settings")
    def save_settings(payload: dict):
        from .manage import save_config

        clean = validate(payload)
        rt, profile = select()

        def mutate(config):
            block = config.setdefault("tts", {}).setdefault("realtime", {})
            block.update(clean)

        save_config(rt.home(profile), mutate)
        return public(rt.home(profile), clean)

    @app.post("/api/voice-chat/stream")
    async def stream_speech(payload: dict, request: Request):
        from .manage import config

        rt, profile = select()
        home = rt.home(profile)
        saved = settings(home)
        if not saved["enabled"]:
            raise HTTPException(409, "Enable realtime speech in Voice studio first")
        body = speech_request(saved, payload)
        headers = {}
        raw = (config(home).get("tts") or {}).get("realtime") or {}
        key = api_key(home, raw)
        if key:
            headers["Authorization"] = "Bearer " + str(key)
        if not slot.acquire(blocking=False):
            raise HTTPException(409, "Another voice request is finishing; try again")
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(30, connect=5),
            trust_env=False,
            follow_redirects=False,
        )
        upstream = None
        released = False

        async def close():
            nonlocal released
            if released:
                return
            released = True
            # Starlette cancels the body task on disconnect. Shield cleanup so
            # that this really closes generation and frees the shared slot.
            with anyio.CancelScope(shield=True):
                try:
                    if upstream is not None:
                        await upstream.aclose()
                finally:
                    try:
                        await client.aclose()
                    finally:
                        slot.release()

        try:
            upstream = await client.send(
                client.build_request(
                    "POST",
                    saved["base_url"] + "/audio/speech",
                    json=body,
                    headers=headers,
                ),
                stream=True,
            )
            if upstream.status_code != 200:
                raise HTTPException(502, "Speech service rejected the request")
            content_type = upstream.headers.get("content-type", "").lower()
            if not content_type.startswith(("audio/pcm", "application/octet-stream")):
                raise HTTPException(502, "Speech service did not return raw PCM audio")
            content_rate = re.search(r"(?:^|;)\s*rate\s*=\s*(\d+)", content_type)
            rate = upstream.headers.get(
                "x-audio-sample-rate",
                content_rate.group(1) if content_rate else "24000",
            )
            channels = upstream.headers.get("x-audio-channels", "1")
            if rate != "24000" or channels != "1":
                raise HTTPException(502, "Speech service must return 24 kHz mono PCM")
        except BaseException as exc:
            await close()
            if isinstance(exc, httpx.HTTPError):
                raise HTTPException(502, "Speech service is unavailable") from None
            raise

        async def chunks():
            size = 0
            try:
                async for chunk in upstream.aiter_bytes():
                    if await request.is_disconnected():
                        return
                    size += len(chunk)
                    if size > 16 * 1024 * 1024:
                        raise RuntimeError("Speech stream exceeded its audio limit")
                    yield chunk
            finally:
                await close()

        return StreamingResponse(
            chunks(),
            media_type="audio/pcm",
            headers={
                "X-Audio-Sample-Rate": "24000",
                "X-Audio-Channels": "1",
                "X-Audio-Format": "s16le",
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
            background=BackgroundTask(close),
        )
