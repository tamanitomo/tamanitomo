"""Isolated voice worker running in Hermes's environment."""

import json
import sys

if __name__ == "__main__":
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
