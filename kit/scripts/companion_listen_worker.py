#!/usr/bin/env python3
"""Speech to text for watching together: faster-whisper over chunks of a film's sound, in a process of its own.

It runs under an interpreter that has faster_whisper (Hermes installs one for its own voice transcription), so the
app's interpreter stays light. The protocol is line-framed: the parent writes one JSON line
{"offset_ms": N, "bytes": M} followed by M bytes of 16 kHz mono signed 16-bit PCM; the worker answers one JSON line
{"offset_ms": N, "cues": [{"start", "end", "text"}]} with times on the film's own clock. The first line it writes is
{"ready": true} once the model is loaded. Stretches the model doubts (music, effects, silence) are left out rather
than guessed at: a hallucinated line would be a thing she reacts to that nobody said.
"""

import json
import sys

MIN_LOGPROB = -1.0
MAX_NO_SPEECH = 0.6


def main():
    model_name = sys.argv[1] if len(sys.argv) > 1 else "small.en"
    language = sys.argv[2] if len(sys.argv) > 2 else "en"
    import numpy as np
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    out = sys.stdout
    out.write(json.dumps({"ready": True}) + "\n")
    out.flush()
    stdin = sys.stdin.buffer
    while True:
        head = stdin.readline()
        if not head:
            return
        try:
            meta = json.loads(head)
            data = stdin.read(int(meta["bytes"]))
            offset = int(meta["offset_ms"])
        except (ValueError, KeyError, TypeError):
            return
        audio = np.frombuffer(data, np.int16).astype(np.float32) / 32768.0
        segments, _info = model.transcribe(
            audio,
            language=language or None,
            vad_filter=True,
            beam_size=1,
            condition_on_previous_text=False,
        )
        cues = []
        for seg in segments:
            text = " ".join((seg.text or "").split())
            if not text:
                continue
            if seg.avg_logprob < MIN_LOGPROB or seg.no_speech_prob > MAX_NO_SPEECH:
                continue
            cues.append(
                {
                    "start": offset + int(seg.start * 1000),
                    "end": offset + int(seg.end * 1000),
                    "text": text,
                }
            )
        out.write(json.dumps({"offset_ms": offset, "cues": cues}) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
