# A local companion stack

Open Tamanitomo, install Hermes if needed, and create or adopt a companion. In **Hermes settings → Local models**, install Ollama on that Hermes host, start it, and download one model. **Use for this companion** tests the weights, selects the local endpoint, removes cloud fallbacks, and resets companion background-model overrides. Apply job model changes in Hermes settings and restart persistent gateway workers afterwards.

The installer selects the official Ollama archive for Linux x64/ARM64, Windows x64/ARM64, or macOS. It verifies the published SHA-256 before extracting beside Hermes, without sudo or a global installation. Existing Ollama installations are reused. New managed servers listen at `127.0.0.1:11434`, disable Ollama Cloud, and use an 8,192-token starting context. Model files live in `companion-engines/ollama/models` for a managed runtime; existing servers retain their own storage and settings. These are host resources shared by profiles. After a reboot, use **Start / refresh**, or configure the [Ollama operating-system service](https://docs.ollama.com/linux).

The installer does not install GPU drivers. NVIDIA, AMD, Apple, and Jetson support depends on the host. The standard Linux archive includes NVIDIA components; ROCm and Jetson may require the extra archives in the official platform instructions. CPU operation is possible but slower. Installation and inference have not been exercised on every supported platform.

## Choosing weights

| Starter model | Exact Ollama weight tag | Approximate download | Practical starting point |
| --- | --- | --- | --- |
| Compact | `qwen3:4b-q4_K_M` | 2.6 GB | 8 GB RAM minimum; more for image and voice engines |
| Balanced | `qwen3:8b-q4_K_M` | 5.2 GB | 16+ GB RAM; roughly 8 GB free VRAM for GPU inference |
| More capable | `qwen3:14b-q4_K_M` | 9.3 GB | 24–32+ GB RAM; roughly 12–16 GB free VRAM |

These are starting suggestions, not automatic hardware sizing or a guarantee of companion quality. Memory also holds context, the operating system, image models, and voice models. Q4_K_M reduces weight memory. All three models advertise tool support, which Hermes needs. Smaller models may follow complex instructions less reliably; test a conversation and a routine before enabling unattended work.

Sources: official [4B weights](https://ollama.com/library/qwen3:4b-q4_K_M), [8B weights](https://ollama.com/library/qwen3:8b-q4_K_M), and [14B weights](https://ollama.com/library/qwen3:14b-q4_K_M). Memory suggestions above are estimates rather than publisher requirements. The library tags select explicit quantization variants; publishers may update their contents.

An existing llama.cpp server also works: use Hermes's `custom` provider with its model name and local `/v1` endpoint. See the [official server documentation](https://github.com/ggml-org/llama.cpp/tree/master/tools/server). Ollama is the guided installer; Tamanitomo does not install llama.cpp in this release.

## Scheduled work alongside local chat

Measure cold prompt processing and concurrent speech as well as token generation.
A model that fits alone may run out of memory when speech, image review or a second
conversation starts. Keep memory guards enabled and validate the complete workload.

For llama.cpp, separate named Hermes custom providers can pin `extra_body.id_slot`
to different slots: one for chat and one for cron/auxiliary requests. With two
non-unified slots, `--ctx-size 131072 --parallel 2` gives each slot 65,536 tokens.
This preserves the chat cache across background jobs, but both slots still share
GPU compute; a long background prefill can slow an active reply. It requires more
memory than one slot. Do not copy these values without testing your machine.

Two optional script workers reduce model orchestration overhead:

- `companion_local_pulse.py --home PATH --base-url http://127.0.0.1:11434/v1 --model MODEL --slot 1`
  asks the local model for a structured presence record, then validates and writes
  it. It needs an existing presence and wardrobe. The model chooses among existing
  wardrobe items; the regular autonomy workflow can add new items. It preserves
  optimistic concurrency, skips an already-confirmed interval, and reports failed
  or truncated responses as failures. `--preview` produces an unwritten proposal.
- `companion_timeline_capture.py --home PATH` claims a current scene, generates
  through the saved Image Studio portrait preset, applies normal image review and
  imports the actual image. It freezes the claimed scene, never sends messages,
  never retries an already-claimed interval, and records generation failures.

Install these as Hermes `no_agent` script jobs only when choosing this workflow.
That flag skips the Hermes agent loop; the pulse script still performs one local
model request and reports its token usage. Keep their output delivery local.
Set the cron script timeout to accommodate the configured image generation limit.
The usual model-driven autonomy/reflection jobs remain available. Attach the
pre-read script to any prompt that says its state has already been assembled.

### Bounded requests and continuity

Set an explicit generation limit on the local server and in each provider route.
A disconnected client is not proof that its generation stopped. Long background
outputs can delay every task sharing that slot. Hermes cron also has its own
watchdog; retain a finite timeout.

`companion_local_context.py` supplies an optional Hermes context-engine factory.
Register `make_engine(config, companion_name)` through the documented plugin
`register_context_engine` API and select `context.engine: companion-local`.
It delegates compression to Hermes and removes obsolete Tamanitomo snapshots
only from outgoing request copies. Stored dialogue and API sidecars remain intact.
Use an explicit compression token cap when a percentage alone exceeds your tested
prompt budget. The plugin must be installed in the chosen profile; merely copying
the module does not activate it.

`companion_local_reflection.py --kind checkin --home PATH --base-url
http://127.0.0.1:11434/v1 --model MODEL --human-user-id ID` is an optional local
check-in worker. Configure the trusted Telegram user's ID explicitly. It reads
original conversation evidence, has the model select exact quotation IDs, and
uses the normal ledger helpers to save entries. It retains pending work on
failure and advances a timestamp/message-ID cursor only after successful writes.
Run it without an external fingerprint monitor so remaining batches are not
skipped. Its daily/weekly/monthly modes use bounded period excerpts and dated journal
appends; validate their semantic choices on copies before replacing journal jobs. Typed output prevents arbitrary
commands and invented quotations, but does not prove a memory is worth retaining.

What is and is not checked about a fact: its evidence is always the exact human
quote the model selected by ID, so the *origin* of the quote is established. Its
statement is the model's own wording and is not verified against that quote. It
is stored with `statement_origin: model_paraphrase`, and it is screened for
obvious mismatches (a number, negation, certainty, name or time the quote lacks,
or a quote about someone else). A statement that fails the screen is held in
`facts-held.jsonl` rather than remembered: `companion_self.py held-facts` lists
them and `decide-held --id ID --decision accept|dismiss` settles one; the Us
memory library shows the same queue under **Needs review**. A decision is
written as an intent, then its effect, then the decision, under one lock per
person, so an interrupted decision is finished by making it again and the
opposite decision afterwards is refused. Accepting is the owner's override,
recorded on the fact as `held_decision`; it is not a verification. The screen
has known misses, listed in `tests/test_memory.py`.

A badly worded new question (one calling the person "the human") is left out
and reported; a fact worded as a transcript ("Robin said: ...") is held with
reason `transcript_wrapper`. Neither costs the rest of the reflection, and
neither makes the run `clean`.

Each batch of evidence gets three generation attempts. An attempt -- request,
decode, truncation and validation -- is counted on disk before the request is
sent, so a crash or timeout spends it too; after a failure the next attempt
waits 15 minutes, then an hour (`status: waiting`). A refused plan is kept as
`<budget>.rejected-N.json`. After three the model is not asked again
(`status: held`) and the evidence watermark stays where it was, until someone
resets the budget with a reason:
`companion_local_reflection.py --kind daily --reset-attempts <budget> --reason "..."`
(the spent attempts stay in the file under `resets`). A check-in's budget
belongs to the evidence after its watermark, so a new conversation arriving
does not give it fresh attempts.

Use `--phase morning` or `--phase winddown` on the pulse worker for a daily
checkpoint with a code-owned unique ID. It can run as a pre-read script before
optional agent outreach, so state is saved independently of tool-call decisions.
`companion_local_hygiene.py --home PATH` previews fixed housekeeping; `--apply`
performs validated rotation and the existing age-limited working-file cleanup.
It rejects undated journals and leaves semantic open-loop decisions to the agent.

The journal helper provides bounded `tail` and append-only dated `append` commands.
Prefer it to asking an agent to rewrite an entire accumulated journal.

## Images and voice

In **Image studio**, install and start ComfyUI, add a workflow, and download its compatible checkpoints and LoRAs. The studio links to [Civitai](https://civitai.com/models), [Hugging Face](https://huggingface.co/models?pipeline_tag=text-to-image), and Civitai's [API instructions](https://github.com/civitai/civitai/wiki/REST-API-Reference). Create a Civitai API key in account settings for authenticated downloads on the host. Keep it out of exported presets. Follow model licenses and any account acceptance requirements.

Place checkpoints under `companion-engines/comfyui/models/checkpoints`, LoRAs under `models/loras`, and VAEs under `models/vae` in that ComfyUI installation. Some workflows need additional text encoders or custom nodes. The model card gives matching base family, trigger words, sampler, and LoRA strengths. Use **Test connection & list models** to select the files. Tamanitomo currently provides guidance and selection, not an authenticated Civitai model downloader.

Connected Hermes image providers, including OAuth providers, are offered as named preset drafts. Save image settings to persist them. Each saved provider preset pins its Hermes provider, so changing the general Hermes image default will not silently redirect that preset. You can map ChatGPT to Realistic and ComfyUI to Landscapes. Turn off **Include the companion's identity** for scenery. A ChatGPT preset uses an online service; select local ComfyUI routes for offline images.

In **Voice studio**, choose a local engine, install it, save a voice, and generate a preview. Some voice engines download weights on first use. Edge speech and cloud providers require a network even when the companion's conversation model is local.

For offline use, finish downloads and previews first; review every image route, voice provider, fallback, background job override, and enabled network tool. Local conversation alone does not make web search or cloud image generation offline. This setup does not disable Hermes network tools automatically.

## Browser and local network access

The normal `companion` launcher opens the browser and listens on `0.0.0.0:8770` by default. A generated access token is required for private API and media requests. Open the printed LAN link on another device on the same network. If no LAN IP is detected, replace `127.0.0.1` in the launch link with the host's LAN address, preserving its port and token. Host firewalls must allow the selected port. A busy default port may cause the launcher to choose another port.

Use `companion app --host 127.0.0.1` for host-only access. The dedicated reverse-proxy service retains its explicit `COMPANION_BIND` settings. For access over the internet, use an HTTPS reverse proxy or private VPN; direct HTTP access is intended for a trusted local network. Ollama and ComfyUI stay on loopback: browsers talk to Tamanitomo, which calls the engines on the Hermes host.
