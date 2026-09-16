# Start here

Tamanitomo (魂の友 — "Soul of a Friend") is a browser workspace for a persistent Hermes companion: conversation, identity, memories, daily life, photos and voice. It contains no preconfigured person, credentials, private images, model weights or cloned voices. You set up your own companion and use your own model accounts — or your own hardware.

For the project overview and the two-minute install, see [README.md](README.md). This page is the longer walkthrough for a first install.

## Before you start

Any machine with internet access, a modern browser and room for Hermes plus optional model downloads. Keep it awake when you expect schedules, Telegram or remote access to work. Cloud model usage can cost money; local image and conversation models can need substantial RAM, VRAM and disk. Start with one working conversation model, then add images and voice.

**What is actually verified.** Development and testing happen on Linux. Windows and Android hosting are exercised but not certified on every configuration — see [docs/REVIEW.md](docs/REVIEW.md) for what has been demonstrated and what has not.

## Install

1. Put the kit somewhere permanent and writable — `git clone` it, or extract the release ZIP into a folder such as `C:\Tamanitomo`. Do not run it from inside the ZIP, and do not put your vault inside the application code folder.
2. Run **`./tamanitomo`** (or **`./companion`**) (Linux, macOS, WSL) or double-click **companion.cmd** (Windows). The launcher provisions Python when needed, installs dependencies into its own `.venv` and opens your browser. Keep the terminal window open — first launch needs internet, and errors stay visible there.
3. Select **Kit-managed Hermes** for a new Hermes installation, or **Existing Hermes** if you already use Hermes. Complete installation and provider sign-in under **Hermes settings**.
4. Open **Companions → Create a companion**. A short guided interview asks how you want things to feel and proposes a personality and a set of boundaries, then shows you every value it chose before anything is written — you can edit any of them, or skip the questions and fill the fields in directly. Already running Hermes? Use **Adopt** instead; your existing `SOUL.md` is left byte-for-byte alone.
5. Configure a primary model and only the fallback providers you want to pay for/use. Test the saved model chain. Open **Conversation**, send a short message and verify it appears in history.
6. Review the proposed hooks and scheduled jobs before enabling them. Telegram is optional. Configure its credentials with Hermes if wanted; test gateway startup and Windows reboot recovery before relying on unattended schedules.
7. Add optional image and voice providers using the guide below. Keep scheduled photos off until manual previews and the image reviewer work.

## What is included

- **Home, Timeline, Journal:** a view of recorded companion life and authored reflections. Empty sections are normal before jobs have run.
- **Conversation:** same profile identity and memory, with session history and push-to-talk voice.
- **Identity, Preferences:** appearance, reference portrait, boundaries, routines, timezone and media settings.
- **Photos & Creations:** view/download, keep album copies, see recorded generation source, label safe/NSFW and delete generated files. Opening NSFW details does not reveal the image; use Reveal there if wanted.
- **Image Studio:** named cloud/OAuth/Comfy presets, category routing, structured six-part prompts, guided weight/LoRA slots, Civitai downloads and compatible image-to-image conversion.
- **Image review:** checks actual pixels against intent. A held or unavailable review requires attention; it does not silently approve delivery. Choose a vision-capable review model. Intentional adult content is an explicit per-image option.
- **Voice Studio:** choose a TTS engine/voice, optional reference cloning where supported, and preview it. Your own licensed/authorized reference audio is required for a cloned voice.
- **Local models:** guided Ollama installation and model selection, with hardware guidance. ComfyUI, voice models and extra nodes are separate optional installs.
- **Hermes settings / Jobs & health:** full Hermes setup plus model/provider, gateway and schedule management.
- **Updates:** stage a trusted release ZIP with integrity checks and apply it on the next launcher start.

## Voice conversation

Configure speech recognition (STT) and speech output (TTS) in Hermes/Voice Studio first. Use **Conversation → Talk**, speak, then **Send recording**. The microphone stops, the transcript is sent to the currently selected conversation, and the reply is read with the configured voice. Cancel discards a recording. Stop playback stops listening/playback but does not undo a chat turn already submitted. Recordings are limited to 90 seconds / 12 MB; speech reads the first 1,000 reply characters while the full reply remains visible. This is turn-based voice, not a simultaneous full-duplex phone call.

Microphone capture works on localhost or HTTPS, with browser permission. A plain `http://192.168…` LAN URL is not sufficient for remote microphone access. If autoplay is blocked, press Play. If speech recognition fails, use the text box and check Hermes STT settings. Local STT/TTS may need first-use model downloads. Your provider selections determine which requests leave your computer.

## Images

Choose a connected provider and save a named preset. For Comfy, connect its endpoint and choose matching model families; install required custom nodes separately. Enter a personal Civitai key on the host if a download needs one. Run a preview, configure the vision reviewer, then assign the preset to the desired category. Appearance and canonical reference are per companion; do not import another person's private companion files.

Only images marked NSFW are blurred by default. Unreviewed images are identified separately, not assumed safe. In details you can mark safe/NSFW or delete without revealing. Deleting one file does not delete separate album copies, Comfy server originals or messages already sent elsewhere.

## Keep your data safe and available

Back up the Hermes home and vault to a private location. They contain credentials, memory and personal content. Keep them outside the Kit code folder. The launcher's access token grants workspace access: don't post it publicly. For remote devices, use authenticated HTTPS/private networking; do not expose a raw token-only HTTP service to the internet. Android wrapping does not move Hermes to the phone.

Close Kit with Ctrl-C in the host launcher window; closing the browser alone leaves it running. Installed Hermes gateways may continue separately. After reboot, verify the gateway and schedules on your Windows machine. Do not assume a sleeping host is available.

## Guides and first-session checklist

- [Detailed installation and hosting](docs/DESKTOP.md)
- [First-run checks](docs/FIRST_RUN.md)
- [Local models, image and voice stack](docs/LOCAL_STACK.md)
- [Studios and image review](docs/STUDIOS.md)
- [Workflow creator](docs/WORKFLOW_CREATOR.md)
- [Updates and rollback](docs/UPDATES.md)
- [Android wrapper settings](docs/ANDROID_WRAPPER.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

Before leaving it unattended: verify text chat, your intended provider costs/fallbacks, a voice turn, a reviewed image, photo deletion, one scheduled job, a vault backup and restart/reboot recovery. Report the Kit version, Windows version, browser, exact action and error text when requesting help. Do not send your .env, auth files, tokens or entire vault as a bug report.
