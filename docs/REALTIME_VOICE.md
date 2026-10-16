# Realtime voice conversations

Tamanitomo can stream a spoken reply while its conversation provider is still
answering. **Voice conversation** keeps the microphone open, detects your utterances and lets
you interrupt a reply by speaking. The existing record button and saved-message
playback remain available.

The speech service runs separately from Tamanitomo. It does not require a local
conversation model: chat continues to use the selected companion's Hermes
provider, reasoning settings and ordered fallbacks.

## Connect a speech service

Realtime voice needs a speech service that Tamanitomo can reach. It does not
download weights or start that service for you. In **Voice studio → Hands-free
conversation**, pick a starting point under **Fill in for**, adjust anything you
need, tick **Enable realtime speech**, and save.

| Service | Cost | Setup | Speech server URL | Model | Voices (English / Japanese) |
| --- | --- | --- | --- | --- | --- |
| OpenAI | Paid per reply | An `OPENAI_API_KEY` for the companion | `https://api.openai.com/v1` | `gpt-4o-mini-tts` | `coral` / `coral` |
| [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) | Free, local | Runs on most computers, CPU or GPU | `http://127.0.0.1:8880/v1` | `kokoro` | `af_heart` / `jf_alpha` |
| [Gufo](https://github.com/gufo-org/gufo) Qwen3-TTS | Free, local | AMD Strix Halo only; voices registered by you | `http://127.0.0.1:8771/v1` | `qwen3-tts-12hz-1.7b-base` | `companion-en` / `companion-ja` |

The quickest local start is Kokoro's CPU container:

```sh
docker run -d --name kokoro -p 127.0.0.1:8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

Any other service works if its OpenAI-style `POST /v1/audio/speech` endpoint
returns raw 24 kHz PCM (see the contract below). Voice names belong to that
service; use whatever it lists. Qwen3-TTS models also receive the reply's
language; every other service receives only OpenAI's standard fields.

The URL is reached from the Hermes host running Tamanitomo, so a browser on
another computer can still use `127.0.0.1` here. Keep a local speech endpoint
private; the browser goes through Tamanitomo's existing access controls.

**Keys.** A service that needs a key gets it from an environment variable you
name under **API-key environment variable**, read from that companion's `.env`
(the Models page writes `OPENAI_API_KEY` there). The key itself never reaches
the browser, and no conversation credential is sent anywhere unless you name
it. A key typed directly into `tts.realtime.api_key` in the profile's Hermes
config takes precedence.

Settings belong to the selected companion, under `tts.realtime` in that profile's
Hermes config. They do not replace `tts.provider` or the voice used by Hermes
voice notes.

**Listening.** Your speech is transcribed by the companion's Hermes
transcription provider (`stt` in its Hermes config), the same one that handles
voice messages. If voice messages already work, so does this.

`auto` selects Japanese for text containing Japanese script or kanji, and English
otherwise. Choose an explicit language for mixed-language conversations if this
heuristic picks the wrong voice. The language used for microphone transcription
is a separate setting in Hermes; an English-only recognizer cannot understand
Japanese simply because a Japanese output voice is selected.

## Talk and interrupt

Open chat, press **Voice conversation**, and allow microphone access. HTTPS or localhost is
required for browser microphone access. Speak naturally, then pause to send the
utterance. Headphones help the browser distinguish your voice from the reply.

Speech begins as complete clauses arrive. Starting a new utterance immediately
stops scheduled playback, discards pending speech, and requests interruption of
the active Hermes response. The next utterance is submitted after the previous
turn has finished its cleanup. It never resubmits a turn that may already have
used a tool. Completed tool actions cannot be undone by interruption.

Ending Voice conversation, leaving the page, changing companion, or hiding the document
releases the microphone and prevents late audio from that voice session playing.
A network disconnection alone does not cancel an ordinary chat: its durable
operation remains recoverable, just as it does for typed conversation.

## Service contract and validation

The server sends bounded text chunks to `POST /v1/audio/speech` with
`response_format: "pcm"`. The endpoint must return signed 16-bit little-endian,
mono PCM at 24 kHz. WAV files and other sample rates are refused. The proxy closes
the upstream request when browser playback is cancelled; it permits one active
speech request at a time and does not build a backlog of stale generations.

The browser and API have synthetic tests for profile scope, access checks,
stream cancellation, byte boundaries, queued-audio suppression and cooperative
Hermes interruption. Microphone quality, echo cancellation, end-of-speech timing,
Bluetooth behavior and uninterrupted gaming sessions still need acceptance on
the actual headset/browser. A measured synthesis first-audio time does not
include speech detection, transcription or the conversation provider's delay.
