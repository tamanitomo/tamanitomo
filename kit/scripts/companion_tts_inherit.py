#!/usr/bin/env python3
"""Resolve the installation's current TTS settings for a named companion."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser()
p.add_argument("--root", type=Path, required=True)
p.add_argument("--input", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
os.environ["HERMES_HOME"] = str(a.root)
os.environ.pop("HERMES_PROFILE", None)
from tools.tts_tool import text_to_speech_tool

result = json.loads(
    text_to_speech_tool(a.input.read_text(encoding="utf-8"), str(a.output))
)
if not result.get("success"):
    raise ValueError(result.get("error", "Default voice failed"))
actual = Path(result.get("file_path", a.output))
if actual != a.output:
    if actual.suffix.lower() == ".wav":
        shutil.copyfile(actual, a.output)
    else:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(actual), str(a.output)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
