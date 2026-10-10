"""Isolated voice worker running in Hermes's environment."""

import json
import os
import sys

if __name__ == "__main__":
    # Importing Hermes can re-run this script under Hermes's own Python (execv, in
    # isolated mode). Let that happen before stdin is read: the re-run inherits stdin
    # only while it is unread, and isolated mode leaves this folder off the path. With
    # stdin read first, every request through this bridge arrived empty.
    try:
        import hermes_bootstrap  # noqa: F401
    except ImportError:
        pass
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        data = json.load(sys.stdin)
        if sys.argv[1] == "transcribe":
            from tools.transcription_tools import transcribe_audio

            result = transcribe_audio(data["path"])
        else:
            from tools.tts_tool import text_to_speech_tool

            result = text_to_speech_tool(data["text"], data["path"])
        if isinstance(result, str):
            result = json.loads(result)
        print("COMPANION_AUDIO=" + json.dumps(result))
    except Exception as exc:
        print("COMPANION_AUDIO=" + json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)
