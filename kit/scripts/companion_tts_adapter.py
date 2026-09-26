#!/usr/bin/env python3
"""Executable adapter for Hermes tts.providers command protocol; emits real WAV."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import yaml


def synthesize(home, provider, text, output):
    cfg = yaml.safe_load((home / "config.yaml").read_text()) or {}
    block = (cfg.get("tts") or {}).get(provider) or {}
    if provider == "pockettts":
        binary = Path(sys.executable).parent / (
            "pocket-tts.exe" if os.name == "nt" else "pocket-tts"
        )
        args = [
            str(binary),
            "generate",
            "--text",
            text,
            "--voice",
            block.get("ref_audio") or block.get("voice") or "alba",
            "--language",
            block.get("language", "english"),
            "--output-path",
            str(output),
        ]
        for key in ("device", "temperature", "sampler_decode_steps", "eos_threshold"):
            if key in block:
                args.extend(
                    [
                        "--"
                        + (
                            "lsd-decode-steps"
                            if key == "sampler_decode_steps"
                            else key.replace("_", "-")
                        ),
                        str(block[key]),
                    ]
                )
        subprocess.run(args, check=True, timeout=600)
        return
    if provider == "audio8":
        repo = Path(sys.executable).resolve().parent.parent.parent / "Audio8_TTS"
        # venv python may resolve to a system symlink; use its un-resolved path.
        repo = Path(sys.executable).parent.parent.parent / "Audio8_TTS"
        args = [
            sys.executable,
            str(repo / "audio8_tts_infer.py"),
            "--text",
            text,
            "--output",
            str(output),
            "--overwrite",
        ]
        for key in (
            "model",
            "device",
            "temperature",
            "top_p",
            "top_k",
            "max_new_tokens",
            "seed",
        ):
            value = block.get(key)
            if key == "seed" and value == -1:
                value = int.from_bytes(os.urandom(4), "big") % 2147483647
            if value is not None:
                args.extend(["--" + key.replace("_", "-"), str(value)])
        if block.get("ref_audio"):
            if not block.get("ref_text"):
                raise ValueError("Audio8 requires the reference transcript")
            args.extend(
                [
                    "--reference-audio",
                    block["ref_audio"],
                    "--reference-text",
                    block["ref_text"],
                ]
            )
        subprocess.run(args, cwd=repo, check=True, timeout=600)
        return
    import torch
    import soundfile as sf

    device = block.get("device", "auto")
    if device == "auto":
        device = (
            "cuda"
            if torch.cuda.is_available()
            else ("mps" if torch.backends.mps.is_available() else "cpu")
        )
    seed = block.get("seed", -1)
    if seed >= 0:
        torch.manual_seed(seed)
    if provider == "chatterbox":
        from chatterbox.tts import ChatterboxTTS

        model = ChatterboxTTS.from_pretrained(device=device)
        kwargs = {
            k: block[k]
            for k in (
                "exaggeration",
                "cfg_weight",
                "temperature",
                "top_p",
                "repetition_penalty",
            )
            if k in block
        }
        if block.get("ref_audio"):
            kwargs["audio_prompt_path"] = block["ref_audio"]
        wav = model.generate(text, **kwargs)
        sf.write(str(output), wav.squeeze().detach().cpu().numpy(), model.sr)
    elif provider == "qwen3tts":
        from qwen_tts import Qwen3TTSModel

        model = Qwen3TTSModel.from_pretrained(
            block.get("model") or "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
            device_map=device,
            dtype=torch.float32 if device in ("cpu", "mps") else torch.bfloat16,
            attn_implementation="sdpa",
        )
        kwargs = {k: block[k] for k in ("temperature", "top_p") if k in block}
        kwargs.update(text=text, language=block.get("language") or "Auto")
        mode = block.get("mode", "custom")
        if mode == "clone":
            if not block.get("ref_audio"):
                raise ValueError(
                    "Upload reference audio for clone mode and select a Base model"
                )
            wavs, sr = model.generate_voice_clone(
                **kwargs,
                ref_audio=block["ref_audio"],
                ref_text=block.get("ref_text") or None,
                x_vector_only_mode=not bool(block.get("ref_text")),
            )
        elif mode == "design":
            wavs, sr = model.generate_voice_design(
                **kwargs, instruct=block.get("instruct", "")
            )
        else:
            wavs, sr = model.generate_custom_voice(
                **kwargs,
                speaker=block.get("voice") or "Ryan",
                instruct=block.get("instruct", ""),
            )
        sf.write(str(output), wavs[0], sr)
    else:
        raise ValueError("Unsupported local speech provider")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--home", required=True, type=Path)
    p.add_argument("--provider", required=True)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    synthesize(a.home, a.provider, a.input.read_text(encoding="utf-8"), a.output)
    if not a.output.is_file() or a.output.stat().st_size < 44:
        raise ValueError("The engine did not produce audio")
