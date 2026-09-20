# Companion management and media studios

Run `companion app` on the machine hosting Hermes. All installers, provider requests, files, and profile writes run on that host, even when the browser is on another computer.

## Companion editor

The top-left selector switches the active companion. Clicking a card in Companions opens that profile’s complete editor. It reads the current `companion.json` and actual SOUL document, rather than rerunning onboarding. Fields absent from old installs use the kit’s defaults; unknown configuration extensions are preserved. Display-name changes live here. Saves require the revision loaded by the editor and keep backups in `companion-config-backups`.

SOUL remains authored text. Review its wording when changing identity or relationship fields; the editor does not regenerate it and erase custom writing. Installation, vault, and profile paths are read-only. Use Jobs & health to repair jobs after changing the daily rhythm.

## Image studio

Open Identity → Image studio. The identity preview reads the marked appearance block, or an explicitly titled Physical Description / Appearance / Visual Identity section in an adopted SOUL. A studio override is shared with `companion_portrait.py`, so the prompt editor and subsequent portrait requests agree.

Image settings are stored in the selected profile’s `companion-images.json`. Named presets can use ComfyUI, the profile’s native Hermes image provider, or an OpenAI-compatible image endpoint. Select a default preset and optional overrides for portrait, anime, realistic, landscape, and other. Named companions can inherit the default installation profile’s image settings. Turn off “Include companion identity” for scenery.

The downloadable ComfyUI preset follows a seven-part structure: quality/trigger words, identity, wardrobe, scene, feeling, lighting, and camera. It uses standard ComfyUI nodes and deliberately requires the user to choose their own checkpoint and LoRAs. No model weights or personal identity are bundled. Import API-format workflows using ComfyUI’s Export (API); visual-editor workflow JSON is rejected with an explanation.

A preset contains `id`, `name`, `provider`, `category`, `endpoint`, `parts`, `negative`, generation controls, `workflow`, and `mappings`. Mappings address `[node_id, input_name]`, for example `"prompt": ["4", "text"]` or `"identity": ["20", "pos_identity"]`. Supported mapping names are `prompt`, the seven prompt parts, `negative`, `seed`, `width`, `height`, `steps`, `cfg`, and `reference_image`. Every named part with its own mapping is written directly to that ComfyUI node input; only a workflow with a single `prompt` mapping receives the combined diffusion-style prompt. GPT, xAI/Grok, Mistral and other hosted providers instead receive a labelled brief that keeps identity, wardrobe, scene, feeling, lighting and camera separate. A reference mapping uploads the saved portrait to ComfyUI before queueing. Without it, generation is text-only. Imported workflows may require custom nodes; the connection check and generation preflight identify missing node types and model choices.

Test connection lists installed checkpoints and LoRAs. Add LoRA node inserts a standard `LoraLoader` into a single-checkpoint graph. Download a preset to transfer the full recipe; API keys stay in Hermes environment variables and never in exported presets. The native Hermes preset follows that profile’s currently selected image model. OpenAI-compatible APIs must implement `/images/generations`; model IDs and supported sizes vary by server.

Generation saves verified PNG/JPEG/WebP files and prompt metadata under `creations/image-studio`, visible in Creations. Test generation is an explicit user action; it does not send a message. Scheduled timeline jobs use `companion_portrait.py generate --recorded` when an Image Studio default exists, preserving the recorded scene and outfit. Run job repair to refresh already-installed job prompts. Agent context advertises the saved recipe IDs and category command.

Install ComfyUI creates `companion-engines/comfyui` beside Hermes, then installs its requirements in a separate environment. Start binds to `127.0.0.1:8188`; remote browsers reach generation through the kit server. Model weights and custom nodes are user-selected separately. The ComfyUI process continues after closing the browser; its log is `companion-server.log` in that directory.

## Voice studio

The UI shows only controls wired to each provider. Chatterbox, Audio8, Pocket TTS, and Qwen3-TTS are registered as Hermes `tts.providers` command providers; selecting one sets `tts.provider` to its ID. The adapter reads its current profile block on every request. No patched Hermes source is required; the installed Hermes must support command providers.

Local packages use separate `companion-engines/<provider>/venv` environments. When uv is available, installation uses Python 3.11 for broader model-library compatibility. Reference clips and transcripts are per provider and per companion. Preview calls Hermes’s actual TTS tool. A saved configuration is not evidence that synthesis succeeded: use preview after installing the engine and downloading its weights.

Named companions can inherit the installation’s voice through a command adapter that resolves the root profile at synthesis time. Unchecking inheritance and saving restores independent settings. Existing provider blocks remain available when switching engines.

Provider sources: [Chatterbox](https://github.com/resemble-ai/chatterbox), [Audio8](https://github.com/Edge0-AI/Audio8_TTS), [Pocket TTS](https://github.com/kyutai-labs/pocket-tts), [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS). Qwen custom, clone, and design modes require their matching CustomVoice, Base, and VoiceDesign models. Audio8’s short-utterance model works best with short preview text. Hardware and package availability affect installation and synthesis.

## Hermes settings

This view serves the complete installed native dashboard, including its extensions, beneath the companion app. It is intentionally not a maintained copy of a subset of native forms. A private, loopback-only backend starts on demand with an ephemeral port; the app forwards HTTP and WebSocket traffic using a server-held session token. Browser requests use an HttpOnly, SameSite cookie scoped to the dashboard proxy. The existing native command-line setup console remains in “Companion environment & native command-line setup.”

This integration requires a Hermes dashboard build supporting `X-Forwarded-Prefix` and its injected `__HERMES_BASE_PATH__`. Missing/older dashboard dependencies or missing frontend builds produce a visible error and leave native setup available. Backend processes started by the workspace are cleaned up when the workspace exits; independently running gateways and the normal dashboard on port 9119 are not stopped.

## Vault

Back, Parent, Vault root, and clickable breadcrumbs remain available while reading notes or search results. Move to trash stores the original file and metadata in `.trash/tamanitomo/<id>/` (with fallback to legacy `.trash/companion-kit/<id>/`); Restore refuses to overwrite a newer file at the original location. There is no permanent-delete control.

Installation code, identity documents, companion runtime state, and databases are marked read-only and omit trash/edit controls. The server enforces the same restrictions. Identity documents remain editable through the dedicated companion/Identity editors. Credentials and hidden paths remain excluded entirely.

See [Guided image workflows](WORKFLOW_CREATOR.md) for model slots, Civitai downloads, family checks and image-to-image presets.

## Deleting and reviewing media

Open a saved photo or creation to see its recorded provider/workflow, mark it safe or NSFW, or delete the selected file. Deletion requires a second confirmation and refuses files that changed since the gallery loaded. Canonical appearance references and identity documents are protected. This removes the vault copy, not separate album copies, upstream Comfy files or messages already delivered on another service. Older images without recorded provenance display “Generation source not recorded.”

Preferences → Media privacy & review contains **Blur NSFW initially**, enabled by default per companion. Only NSFW-labelled images are blurred. Opening photo details keeps the blur; reveal explicitly inside that menu. Unreviewed images retain their separate status. This is a viewing preference, not access control: downloading or opening the raw image returns the original file. Marking a photo safe affects display; it does not approve it for automated delivery.

**Review generated images before delivery** defaults on. The reviewer sees the actual pixels and the intended scene/wardrobe, returning an NSFW classification and match decision. Failed, malformed or unavailable reviews hold the generated file in Photos for inspection and return an error rather than a successful delivery-ready generation result. Review is fallible and adds a model request and latency. Set an explicit vision-capable provider/model in Media preferences, or the configured compression provider/model is used. The bridge calls that provider directly with no conversational fallback chain and refuses an OpenRouter reviewer.

For intentionally adult images, select the explicit checkbox in Image Studio or pass `--allow-nsfw` to the portrait generate/review command. This permits intentional adult output; it does not waive scene matching. Casual scenes default to holding nudity.

The Companion outbox rechecks image review evidence before delivery and verifies it belongs to the same image bytes. External image tools can be reviewed with `companion_portrait.py --home HOME review --source /absolute/file.png --scene "intended scene"`. Companion skills instruct models to use this before any direct send. This is not a universal interceptor for arbitrary third-party tools or direct Telegram uploads.

Browser push-to-talk uses recording → Hermes transcription → the selected companion chat session → configured TTS playback. Use Talk, Send recording, Cancel recording and Stop playback. Microphone capture needs HTTPS or localhost and browser permission. Full-duplex calls also need interruption, cancellation and echo handling.
