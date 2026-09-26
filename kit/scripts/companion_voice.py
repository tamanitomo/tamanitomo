#!/usr/bin/env python3
"""Voice notes: synthesized with whatever TTS Hermes is already configured with.

The kit does not pick a voice, install a provider, or ship a model. Hermes
already has a `tts` block with a provider and a voice in it, and whatever is
there is what the companion sounds like. This module's whole job is to turn a
line of text into an audio file and hand it to the outbox, so a voice note goes
through the same expiry, quiet hours and daily cap as everything else.

Cloning a voice from a recording is a Hermes feature (`tts.neutts.ref_audio` and
`ref_text`), not something the kit implements. What the kit does is write those
two keys for you, and refuse to do it without an explicit statement that the
voice is yours to use.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write

CLONE_PROVIDER = "neutts"


def read_config(c):
    import yaml

    try:
        return (
            yaml.safe_load((c.home / "config.yaml").read_text(encoding="utf-8")) or {}
        )
    except (OSError, ValueError):
        return {}


def settings(c):
    """What this profile currently sounds like, as Hermes has it."""
    tts = read_config(c).get("tts") or {}
    provider = str(tts.get("provider") or "")
    block = tts.get(provider) or {} if provider else {}
    return {
        "configured": bool(provider),
        "provider": provider,
        "voice": block.get("voice") or block.get("voice_id") or "",
        "cloned": bool((tts.get(CLONE_PROVIDER) or {}).get("ref_audio")),
        "note": (
            ""
            if provider
            else "No TTS provider is configured in Hermes, so this companion has no voice yet. "
            "Set one up in Hermes; the kit deliberately does not choose one for you."
        ),
    }


def queue_note(c, text, audio_path, reason="", ttl_hours=4):
    """Queue an already-synthesized voice note.

    Hermes 0.21.1 exposes text-to-speech as an agent tool, not as a CLI command,
    so the agent synthesizes the audio itself with `text_to_speech` and passes
    the file it got back to this. That division is the right one anyway: the
    model does the part only the model can do, and the dispatcher still decides
    whether the result leaves the house.

    `text` is kept alongside the audio deliberately. A voice note that fails to
    play, or arrives somewhere audio does not, should still say something.
    """
    import companion_outbox as outbox

    text = (text or "").strip()
    if not text:
        raise ValueError("nothing to say")
    if len(text) > 1200:
        raise ValueError("a voice note over 1200 characters is a monologue; shorten it")
    state = settings(c)
    if not state["configured"]:
        return {"ok": False, "reason": state["note"]}
    audio = pathlib.Path(audio_path)
    if not audio.is_absolute():
        raise ValueError("the audio path must be absolute")
    if not audio.is_file():
        return {
            "ok": False,
            "reason": f"no audio at {audio}. Synthesize it with the text_to_speech "
            f"tool first and pass the file path it returns.",
        }
    queued = outbox.queue(
        c,
        {
            "kind": "voice",
            "body": text,
            "media_path": str(audio),
            "reason": reason,
            "ttl_hours": ttl_hours,
        },
    )
    return {
        "ok": True,
        "queued": queued["entry"]["id"],
        "file": str(audio),
        "note": "Queued, not sent. Voice notes obey the same permission, quiet hours and cap as "
        "anything else, and are withheld entirely when voice is set to no.",
    }


def synthesize(c, text, output_path=None):
    """Synthesize speech into a WAV file using Hermes's configured TTS provider."""
    import companion_tts_adapter as adapter
    import hashlib

    text = (text or "").strip()
    if not text:
        raise ValueError("nothing to say")
    cfg = read_config(c)
    provider = (cfg.get("tts") or {}).get("provider")
    if not provider:
        raise ValueError(
            "No TTS provider configured in Hermes (config.yaml tts.provider)."
        )
    if not output_path:
        out_dir = c.data / "creations" / "voice"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        ident = hashlib.sha256((text + stamp).encode()).hexdigest()[:8]
        output_path = out_dir / f"voice_{stamp}_{ident}.wav"
    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    adapter.synthesize(c.home, provider, text, output_path)
    if not output_path.exists() or output_path.stat().st_size < 44:
        raise ValueError("TTS engine did not produce an audio file")
    return output_path


def send_note(c, text, reason="", priority="normal", ttl_hours=4):
    """Synthesize and queue a spontaneous voice note for delivery."""
    audio_path = synthesize(c, text)
    res = queue_note(c, text, str(audio_path), reason=reason, ttl_hours=ttl_hours)
    return {**res, "audio_path": str(audio_path)}


def set_clone(c, ref_audio, ref_text, confirmed=False):
    """Write Hermes's own voice-cloning keys, with the one question that matters.

    A cloned voice is somebody's actual voice. The kit will not write these keys
    without being told, explicitly, that the recording is the user's own or that
    they have permission — not because a flag stops anyone, but because it should
    be a decision somebody made on purpose rather than a box they clicked past.
    """
    if not confirmed:
        raise ValueError(
            "Refused: confirm that this recording is your own voice, or one you have "
            "permission to use, before it becomes your companion's voice."
        )
    import yaml

    source = pathlib.Path(ref_audio)
    if not source.is_file():
        raise ValueError("that audio file does not exist")
    if not (ref_text or "").strip():
        raise ValueError(
            "ref_text is required: it must be a transcript of exactly what is said in "
            "the recording, or the clone comes out wrong"
        )
    stored = c.data / "soul" / ("voice-reference" + source.suffix)
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(source.read_bytes())
    config = read_config(c)
    tts = dict(config.get("tts") or {})
    block = dict(tts.get(CLONE_PROVIDER) or {})
    block["ref_audio"] = str(stored)
    block["ref_text"] = ref_text.strip()
    tts[CLONE_PROVIDER] = block
    tts["provider"] = CLONE_PROVIDER
    config["tts"] = tts
    atomic_write(
        c.home / "config.yaml",
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
    )
    return {
        "provider": CLONE_PROVIDER,
        "ref_audio": str(stored),
        "note": "Written into Hermes's own tts config. The reference lives in the vault, so it "
        "is covered by the same history as the rest of the companion.",
    }


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("status")
    sp = s.add_parser("say", help="queue a voice note you have already synthesized")
    sp.add_argument("--text-file", type=pathlib.Path, required=True)
    sp.add_argument("--audio", required=True, help="the file text_to_speech returned")
    sp.add_argument("--reason", default="")
    sp.add_argument("--ttl-hours", type=float, default=4)
    sn = s.add_parser("send", help="synthesize and queue a voice note")
    sn.add_argument("--text")
    sn.add_argument(
        "--file", type=pathlib.Path, help="path to UTF-8 file containing text"
    )
    sn.add_argument("--reason", default="")
    sn.add_argument("--ttl-hours", type=float, default=4)
    cl = s.add_parser("clone", help="write Hermes's voice-cloning keys")
    cl.add_argument("--audio", required=True)
    cl.add_argument("--transcript", required=True)
    cl.add_argument("--i-have-permission", action="store_true", dest="confirmed")
    a = p.parse_args()
    c = cc.load(a.home)
    if a.cmd == "status":
        out = settings(c)
    elif a.cmd == "say":
        out = queue_note(
            c, a.text_file.read_text(encoding="utf-8"), a.audio, a.reason, a.ttl_hours
        )
    elif a.cmd == "send":
        text = (a.file.read_text(encoding="utf-8") if a.file else a.text or "").strip()
        if not text:
            raise ValueError("either --file or --text with non-empty content required")
        out = send_note(c, text, a.reason, ttl_hours=a.ttl_hours)
    else:
        out = set_clone(c, a.audio, a.transcript, a.confirmed)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
