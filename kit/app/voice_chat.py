"""Browser voice uses the selected Hermes profile's STT and TTS providers."""

import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from fastapi import Request, HTTPException
from fastapi.responses import FileResponse
import companion_platform as cp
from .runtime import redact

MAX_AUDIO = 12 * 1024**2
TYPES = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
}


def bridge(rt, home, mode, payload):
    python = cp.venv_executable(rt.root / "hermes-agent")
    if not python.is_file():
        python = Path(rt.command()[0]).resolve().parent / (
            "python.exe" if os.name == "nt" else "python"
        )
    if not python.is_file():
        raise ValueError("Hermes Python is unavailable; finish Hermes setup first")
    script = Path(__file__).resolve().parents[1] / "scripts/companion_voice_chat.py"
    from companion_gateway import _env_values

    env = {**rt.env(home), **_env_values(home)}
    env["PYTHONPATH"] = str(rt.root / "hermes-agent")
    run = subprocess.run(
        [str(python), str(script), mode],
        input=json.dumps(payload),
        env=env,
        capture_output=True,
        text=True,
        timeout=660,
    )
    try:
        result = json.loads(
            next(
                x.split("=", 1)[1]
                for x in run.stdout.splitlines()
                if x.startswith("COMPANION_AUDIO=")
            )
        )
    except (StopIteration, ValueError):
        raise ValueError(
            "Voice engine failed. Check speech/transcription settings in Hermes."
        )
    if run.returncode or not result.get("success"):
        raise ValueError(redact(str(result.get("error", "Voice engine failed")))[:1000])
    return result


def register(app, select, load):
    @app.post("/api/voice-chat/transcribe")
    async def transcribe(request: Request):
        mime = request.headers.get("content-type", "").split(";")[0]
        if mime not in TYPES:
            raise ValueError("Use a supported audio recording")
        rt, p = select()
        home = rt.home(p)
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_AUDIO:
                raise HTTPException(
                    413, "Recording exceeds 12 MB; record a shorter turn"
                )
            chunks.append(chunk)
        if size < 16:
            raise ValueError("The recording is empty")
        folder = home / ".companion-voice"
        if folder.is_symlink():
            raise ValueError("Voice cache cannot be a symbolic link")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (uuid.uuid4().hex + TYPES[mime])
        path.write_bytes(b"".join(chunks))

        def run(report):
            try:
                report("Transcribing your recording")
                r = bridge(rt, home, "transcribe", {"path": str(path)})
                text = r.get("transcript", "")
                if not isinstance(text, str) or not text.strip() or len(text) > 30000:
                    raise ValueError(
                        "No usable speech recognized. Try again or type your message."
                    )
                return {"transcript": text.strip()}
            finally:
                path.unlink(missing_ok=True)

        try:
            return app.state.operations.submit(
                str(rt.root), "Transcribe voice", run, profile=p
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @app.post("/api/voice-chat/speak")
    def speak(payload: dict):
        text = payload.get("text", "")
        if not isinstance(text, str) or not text.strip() or len(text) > 1000:
            raise ValueError("Speech replies must contain 1–1,000 characters")
        rt, p = select()
        home = rt.home(p)
        folder = home / ".companion-voice"
        if folder.is_symlink():
            raise ValueError("Voice cache cannot be a symbolic link")
        folder.mkdir(parents=True, exist_ok=True)
        ident = uuid.uuid4().hex

        def run(report):
            report("Preparing spoken reply")
            r = bridge(
                rt,
                home,
                "speak",
                {"text": text, "path": str(folder / (ident + ".wav"))},
            )
            path = Path(r.get("file_path", "")).resolve()
            if (
                path.parent != folder.resolve()
                or not path.name.startswith(ident + ".")
                or path.suffix not in (".wav", ".ogg", ".mp3")
                or not path.is_file()
            ):
                raise ValueError("Speech engine returned an invalid audio file")
            # Keep only a bounded recent playback cache, separate from companion creations.
            for old in sorted(
                folder.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True
            )[40:]:
                if old.is_file() and not old.is_symlink():
                    old.unlink(missing_ok=True)
            return {"audio": "/api/voice-chat/audio?name=" + path.name}

        return app.state.operations.submit(str(rt.root), "Speak reply", run, profile=p)

    @app.get("/api/voice-chat/audio")
    def audio(name: str):
        if not re.fullmatch(r"[a-f0-9]{32}\.(wav|mp3|ogg)", name):
            raise HTTPException(404)
        rt, p = select()
        folder = rt.home(p) / ".companion-voice"
        path = folder / name
        if folder.is_symlink() or path.is_symlink() or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, headers={"Cache-Control": "private, no-store"})
