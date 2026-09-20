## 2.3.4 — Reliable pulse-to-image handoff (2026-09-19)

- Teach companion pulses the smallest valid recovery when clothing-care timing rules conflict with a full bedtime transition, preventing stale state from needlessly starving image timeline captures.
- Flatten mood and current wants into clean emotional-tone text instead of leaking Python list notation into hosted image prompts.

## 2.3.3 — Simpler companion settings (2026-09-19)

- Move Daily rhythm into the Companion settings group and remove the now-empty Schedule & usage menu.

## 2.3.2 — Hot-fix update completion (2026-09-19)

- Let the rollback installer complete when an installed bootstrap file already exactly matches the verified staged release, while continuing to reject unrelated local edits.

## 2.3.1 — Reliable in-app updates (2026-09-19)

- Keep application-wide update operations visible to the browser while preserving installation and profile isolation.
- Allow a trusted release to adopt files that already exactly match it, so an official update can replace an earlier hot-fix without weakening local-change protection.
- Give the primary update action comfortable line height, spacing and mobile wrapping.

## 2.3.0 — Companion continuity and structured image routing (2026-09-19)

- Add Companion Continuity Settings under Models & providers with live provider/model dropdowns, the full Hermes reasoning-effort range, per-job guidance, bulk routing, failure details, and editable schedules/prompts.
- Migrate recognizable legacy Tamanitomo workers that bypassed Hermes through provider-pinned scripts back to native Hermes agent jobs without changing job IDs, schedules, enabled state, or run history.
- Keep script-only maintenance explicitly model-free while making every model-backed Tamanitomo job configurable through the UI.
- Give hosted image providers a labelled identity, wardrobe, scene, feeling, lighting, camera, and quality brief. Preserve ComfyUI's mapped-node contract: separately mapped parts remain separate, while single-prompt workflows retain their combined diffusion prompt.
- Bundle direct Mistral model and FLUX image-provider plugins, add Mistral model discovery, image-studio setup, and Voxtral voice model selection.
- Add photo multi-select album/delete actions and allow an existing vault image to become the companion's reference portrait.
- Preserve the current provider/model settings when repairing jobs and expose the expanded Hermes reasoning levels from `none` through `ultra`.

## 2.2.3 — Patch notes before updating (2026-09-19)

- Show the latest stable release notes directly in the Updates panel, with the Update button beneath them.
- Send the home-screen update notice to that review screen instead of installing immediately.
- Preserve line breaks, safely escape release text, and keep long notes usable on mobile in a bounded scrolling panel.

## 2.2.2 — Official release updates (2026-09-19)

- Publish a source-only `tamanitomo-release.zip` with an explicit file manifest and SHA-256 checksums for every stable release.
- The in-app update feature uses the latest published stable release for both ZIP and Git installations. It reports unavailable checks, rejects downgrades and missing assets, and verifies the downloaded asset digest when GitHub provides one.
- Dependency failures stop code installation. ZIP installs retain rollback backups and preserve executable permissions; locally edited installations are refused.
- Restart only the current workspace, retain Hermes profiles and private data, and wait for the new server instance before reconnecting.
- Include the onboarding and Termux lifecycle fixes already present on main.

## 2.2.1 — Interactive Onboarding, Intimacy Recalibration & Mobile Hardening (2026-09-17)

- **Interactive First-Visit Onboarding:** Zero-profile detection triggers guided birth wizard (Telegram BotFather/userinfobot guide, Relational vs Worker choice, 8 PMD-style dilemma questions, Sam companion card reveal with in-drawer customizer, and cloud device-code OAuth for xAI Grok and OpenAI Codex).
- **Default Companion Name:** Default companion is now officially **Sam** (gender-neutral).
- **Intimacy Recalibration & Neglect Decay:** Starts at Level 0 (Just Met), Stage 1 Friends floor (25 pts), Stage 2 Chemistry flirting (50 pts, can be lost from >24h neglect), Stage 4 Bonded taking ~2 months of daily interaction.
- **Finish Customizing Banner:** Secondary workspace notification banner and 3-card modal for Spoken Voice (with preview), Photos/Images, and Location/Sensors.
- **Emergency CLI PIN Reset:** `tamanitomo pin [--set PIN | --clear]` to inspect, change, or remove remote access network PIN.
- **Vault Backup & Export:** One-click web download (`/api/vault/export`) and `tamanitomo backup` CLI command.
- **Android & Mobile Hardening:** Battery optimization guidance for Termux, and Wi-Fi to cellular rollover delay/finish hooks for gateway stability.
- **Local LLM Memory Guardrails & On-Device Verification:** Automatic host RAM probing (`get_host_memory`), mobile platform detection (`is_mobile`), 2.8 GB model weight safety limit to prevent Android Low Memory Killer (LMK) crashes, 4,096-token context cap, 4-thread concurrency limits for mobile SoC thermal stability, mobile model recommendations (SmolLM2 1.7B, Qwen 2.5 1.5B, Llama 3.2 1B/3B), and live verified 17.3 t/s on-device inference on Google Pixel 8 Pro (Tensor G3).
- **"Keep It Local" Guided Onboarding:** 100% private on-device brain setup in the first-visit wizard, featuring hardware detection, mobile limitations guidance (RAM limits, battery drain, thermal pacing), 1-click downloading/configuration for mobile and desktop models, and automated companion activation.
- **In-App 1-Click Updates:** Interactive "⚡ Update Now" buttons in Settings and the Home notification banner for zero-terminal upgrades. Automatically fetches and applies verified releases, syncs dependencies, and reboots the workspace service with an automated browser reconnection heartbeat, while explicitly isolating the Hermes engine and leaving companion memories, journals, and vault files untouched.

## 2.2.0 — Initial Release (2026-09-17)

**Name change.** The project is now published as **tamanitomo** (魂の友 — "Soul of a Friend").
All user-facing references to `companion-kit` have been updated: CLI help, version strings,
User-Agent headers, Windows launcher (`tamanitomo.cmd`), git vault identity, setup wizard banner,
CI artifacts, and documentation. Internal script filenames (`companion_*.py`), config files
(`companion.json`), and environment variables (`COMPANION_HOME`) are unchanged in this release to
avoid breaking existing installations. A future compatibility pass will rename them with a
migration script.

## Unreleased — interface overhaul

**Licence.** Relicensed from AGPL-3.0 to PolyForm Noncommercial 1.0.0. Any noncommercial
purpose is permitted; commercial use is not. Fill in the `Required Notice:` line in `LICENSE`
with your name before publishing.

**Theming actually works now.** The stylesheet carried 492 hardcoded colours and 95 hardcoded
`rgba()` values that ignored the seven theme variables entirely, so every theme except the
default rendered partly in the default palette. All of them, plus 113 in inline styles, are now
design tokens, and themes derive the rest with `color-mix()`. Twelve themes (nine dark, three
light), a live accent-colour picker, and a Match-system mode. Appearance is stored per companion
on the server and mirrored to `localStorage`, so a companion looks the same on every device and
the first paint never flashes.

**Navigation.** Phones get a bottom bar instead of a hamburger drawer: four destinations you
choose, with More permanently in the last slot opening a directory of everything, each entry
explained in a line and starrable straight onto the bar. The desktop rail keeps its groups.

**Creating a companion is an interview.** Seven situational questions, one per screen, propose a
personality, a relationship frame, a pace and contact limits, then show every value they chose in
plain language. From there: save, edit, start over, or start over without the questions and fill
the fields in directly. Keyboard-answerable, skippable throughout.

**Fixed while rebuilding it:**
- Creating a companion from the browser always failed. The form submitted `explicit` and
  `relationship_pace`, which `POST /api/profiles` rejects as unknown setup answers. The existing
  test only ever sent a five-key subset, so nothing caught it. `relationship_pace` is now a real
  setup answer and reaches the saved config; `explicit` is no longer sent at all.
- The wizard had two `<select name="boundary">` controls, so the relationship frame chosen on
  step 2 was silently discarded on submit.
- Step 4's frames (`partner`, `crush`, `platonic`) were not real catalog keys, and its
  `explicit = boundary !== 'platonic'` rule set adult themes on frames that forbid them.
- The Profile ID field's `pattern` never validated anything: browsers compile `pattern` with the
  regex `v` flag, where its unescaped `-` is a syntax error.
- `.section-subheading` was used in the markup but never defined in the stylesheet.
- Theme preview swatches were hardcoded and disagreed with the themes they previewed; they now
  read the live token values.
- Identity opened on a configuration warning above the page title. It now opens on a profile
  header — who they are, their personality, your frame, their age and timezone.

**Licensing audit.** Added `THIRD-PARTY-NOTICES.md`. The interface icons derive from Feather
(MIT) and Lucide (ISC) and were shipping without their required notices; both are now reproduced.
Nothing else third-party is redistributed — Hermes (MIT), ComfyUI (GPL-3.0) and Ollama (MIT) are
fetched from their publishers, and release archives stay source-only, which is what keeps the
LGPL-3.0 `pyte` dependency an ordinary library import rather than a redistribution. The Civitai
downloader already read each model's permission flags but never showed them; it now displays
commercial-use, derivative, credit and relicensing terms before a download, marked when restricted.

**Tests.** 760 passing. New coverage for the appearance API, per-profile isolation and validation;
the full creation payload a browser actually sends; unknown-answer rejection; navigation/pin
allowlist parity; and the interview's derivation, checked against the real persona and
relationship-frame catalogs so it can never propose something the backend would refuse.

## 0.9.0-beta.1 — friend deployment beta

- Opening photo details never reveals an NSFW image; reveal is explicit inside the viewer. Unreviewed photos are no longer blurred automatically.
- Add push-to-talk browser voice with profile-owned STT/TTS, visible recording state, cancel, playback controls and bounded temporary audio.
- Add trusted release ZIP staging, managed-file checks, launcher-time updates, runtime locking and rollback copies.
- Add Windows-first setup/feature guide, private distribution plan and source-checked Android WebToApp settings.
- Improve mobile photo details and group update controls outside advanced command-line setup.

## Unreleased — companion editors and media studios

### Contextual feelings

- Browse older relationship experiences and select them for repair or correction, even after they leave the latest 30 records.

- Derive warmth, trust, hurt, irritation and missing-you indicators from expected routines, temperament and evidence-backed relationship experiences, alongside the existing authored mood.
- Carry the same live state into chat and scheduled context; preserve a returning human's preceding gap even when the new message is already saved.
- Add Together controls for overnight/weekly routines, temperament, connection, rupture, repair and correction. Repeated ruptures have stronger effects; repair softens without deleting history; corrections exclude mistaken records.
- Keep experience ledgers companion-private, protect settings with revisions, and make experience retries idempotent. Add a feelings shortcut beneath the companion's name in chat.
- Find the last human contact independently of the recent assistant-message tail, so long runs of updates do not hide it.

### Daily browsing and conversation

- Keep the composer and Send visible in short phone viewports; constrain long moods and names so they do not displace chat controls.
- Fix journal horizontal page overflow and add a collapsible vertical entry picker for narrow screens.
- Stop microphone capture and playback before refreshing Conversation or starting a new chat.

- Keep successful chat notices from covering Send; remove the empty welcome card when sending the first message.
- Resolve older chat media and album-copy references before gallery paging, preserving concealment across duplicates. Skip gallery scans for text-only history.
- Fix the empty Gateway & routine tab and make Gateway settings open its controls directly; add a shortcut from Hermes settings.

- Page through photo archives beyond 1,500 images; search and filter across the scanned collection. Preserve duplicate privacy and album membership, and update ratings across copies even outside the first page.

- Page through journal archives beyond 1,000 entries, search across the scanned archive, and load long entries fully in the reader. Keep the journal paging button reachable alongside the sticky list and report archive scan limits explicitly.
- Page through older conversations and messages using stable cursors, retaining the selected conversation even when it falls outside the latest 100. Loading earlier messages preserves the current scroll position and marks the beginning of the conversation.
- Put Conversation first, retain direct Hermes settings and Jobs & health navigation, and gather secondary destinations under More. Page search recognizes provider and administration terminology.
- Give chat the available window height, format saved messages with the shared escaped Markdown renderer, add date separators, and stop streamed replies pulling readers away from older messages.
- Ignore out-of-order conversation-history responses after another conversation has been selected.
- Group photos by day in a compact grid, move capture diagnostics into a disclosure, and keep journal/photo filters while visiting other pages. Keep the journal's selected entry and provide a sticky reading list on larger screens.

### Reliability and predictable editing

- Make unlimited proactive contact an explicit choice; numeric daily caps start at one, and Replies only is clearly labeled.
- Keep NSFW/unreviewed chat and activity images concealed until revealed, and fix authenticated URLs used for spoken replies and choosing photo references.
- Preserve existing human records when changing sharing, reject conflicting destinations, and apply the same photo validation and background-job synchronization from both preference editors.
- Scope operation results to their originating companion, retain status recovery after connection failures, and avoid blindly resubmitting work with an unknown outcome.
- Protect unsaved notes, documents, profile settings, and preferences with a visible indicator and Stay/Discard controls; recover the composer after failed transcription.
- Version page asset URLs by content so refreshed workspaces do not combine new and cached older scripts.
- Match whole mood words and suppress local negation in the basic wellbeing scorer; remove stale Markdown and JSON indicator snapshots when disabled or empty.

### Day continuity and self-directed images

- Every companion can retain previously / now / next, estimated activity duration and timed commitments in the presence ledger. Chat and scheduled context flag preparation deadlines and plans that will not fit; passing time never completes a promise automatically.
- Model-authored pose, hands, gaze, framing, props, expression and lighting direct images of the saved current moment. Recorded wardrobe and visual identity remain authoritative.
- Skip consecutive unchanged timeline scenes after a successful capture; failed renders remain retryable and unconfirmed carried state cannot trigger a photo.
- Existing histories require no rewrite. Repair updates shared presence guidance and adds the continuity instruction to existing pulse prompts while preserving custom text.

### Media deletion, provenance and pre-delivery review

- Add profile-scoped file deletion with change checks and protection for identity/reference files; preserve independent album copies.
- Show recorded generation sources and keep labels/ratings on album copies.
- Blur NSFW and unreviewed images by default, with per-profile preferences and manual rating controls.
- Review actual image pixels against intent before generation succeeds or the Companion outbox sends; hold mismatches and unavailable reviews, while supporting explicitly requested adult images.

### Guided Comfy workflow creator

- Compose six-section prompt recipes with checkpoint/model, encoder, VAE and LoRA slots, strengths, enable switches and architecture compatibility checks.
- Inspect Civitai versions and download selected SafeTensors/GGUF weights to a local or SSH Comfy host with SHA-256 verification and private API-key storage.
- Derive separate reference-based image-to-image presets from compatible single-sampler workflows.
- Install a reusable prompt-structure skill without overwriting companion-authored guidance.
- Disable supported Comfy API-node/frontend networking and telemetry in managed launches by default.

### Local stack setup and studio provider routing

- Added a host-local Ollama installer with official release SHA-256 verification, safe extraction, startup, streamed model downloads, and per-profile assignment after a real load test.
- Added Qwen3 4B/8B/14B Q4_K_M recommendations with weight sizes and memory guidance. Local assignment removes cloud fallbacks and resets companion job overrides.
- Added timezone dropdowns to onboarding and companion editing; timezone edits also update Hermes configuration.
- Discover configured/available Hermes image providers as named preset drafts, including OAuth; route saved presets through Hermes's plugin-aware dispatcher with a per-request provider selection.
- Added Civitai/Hugging Face model guidance and fixed preset ID creation on HTTP LAN origins.
- Normal browser launcher now supports host and LAN access by default with its access token; explicit reverse-proxy binds remain unchanged.
- Added the local stack guide and boundary tests for downloads, provider dispatch, profile isolation, and timezone synchronization.

### Companion editors and media studios

- Repair adopted identity documents by wrapping existing prose; empty markers no longer hide an authored appearance. Preserve self-authored blocks.
- Pass canonical reference images through saved Hermes image presets.
- Correct Pocket TTS decode-step arguments and enable voice-note conversion for local speech adapters.
- Move workspace renaming into the full companion editor; load current configuration and authored SOUL sections with backups and conflict checks.
- Add Image Studio under Identity: named provider/workflow presets, PlantMilk-style prompt components, per-category defaults, workflow downloads, LoRA controls, and ComfyUI installation on the Hermes host.
- Add Chatterbox, Audio8, Pocket TTS, and Qwen3-TTS through Hermes command providers, with provider-specific controls and independent or inherited companion settings.
- Integrate the complete installed Hermes dashboard and its WebSocket/API surface into settings while retaining native CLI setup.
- Add vault breadcrumbs/back navigation, recoverable trash, and server-enforced read-only protection for critical files.

## 2.2.0-beta.5 — hosted companion workspace

- Add an optional native Hermes streaming bridge and inline vault media in chat.
- Add an activity feed combining latest job results and saved creations.
- Add a persistent backend entry point and documented Authelia/Tailscale deployment.
- Verify signed-out access, admin policy, authenticated browser reads/actions, and native streaming with a local model fixture. All 548 tests pass on Linux.

## 2.2.0-beta.4 — conversation and gateway clarity

- Add a conversation header, collapsible history, remembered thread, saved draft, keyboard sending, and reply status.
- Support workspace display names for all profiles, including the default Hermes home.
- Show gateway checks alongside service controls and explain background independence.
- Validation: all 21 workspace contract tests pass; JavaScript syntax checked.

## 2.2.0-beta.3 — relationship preferences

- Enable the two computed indicators by default, preserving explicit opt-outs.
- Show indicators on Home and Together; move relationship pace and related choices into Preferences only.
- Add a first-install handoff checklist and document Android hosting limits.
- Validation: 543 tests pass on Linux/Python 3.14.

## 2.2.0-beta.2 — companion product interface

- Redesign the local desktop app with grouped navigation, quick page search, responsive layouts, and a content-focused home.
- Add photo browsing by day and collection, full-size viewing, downloads, and album copies for companion-owned images.
- Add a searchable journal reader for dated Lifelog entries and archived journals, and a creations library for writing, images, audio, video, and documents.
- Combine recorded life, photographs, and journal entries in the Timeline. Explain disabled, paused, missing, and failed photo capture states.
- Organize Hermes management and companion preferences into focused panels. Replace duplicate job listings with search, filters, run results, and schedule editing.
- Enforce profile boundaries and secret/symlink exclusions for new content routes; retain raw documents without executing their HTML.

## 2.2.0-beta.1 — companion workspace

- Bootstrap launchers for Windows/Linux, including Python provisioning when needed.
- Existing and kit-managed Hermes environments; explicit per-request profile scope.
- Profile creation/adoption/archive/restore; native-session chat and history.
- Primary/fallback providers, write-only credentials, native setup consoles, advanced config,
  gateway controls, job history/actions, and application of pins to existing jobs.
- Lived-state timeline, relationship preferences/milestones, vault browsing/search/edit/export.
- Private media authentication, cross-origin write protection, optimistic note editing.
- Normalize Hermes's trimmed job prompts when checking fingerprints; keep meaningful user edits protected.
- Reserve memory-omission disclosures when relationship preferences consume context.

This is a private-test beta. Native Windows and live model/day-long acceptance are not implied by unit tests.
See docs/DESKTOP.md for the complete limits and setup steps.

# Changelog

Versions are `companion --version`. Dates are the day the work landed.

## 2.1.0 — 2026-09-10

The first install by someone other than the author, and what it found. Ash, a
cold install on another machine from the release archive against Hermes 0.21.1,
is recorded in `docs/REVIEW.md`.

### Fixed

- **The kit would not run on Python 3.11 at all.** A backslash escape inside a
  nested f-string expression in `companion_wizard.py` is 3.12+ syntax; on the
  3.11 the README promises and CI tests, twenty-four tests errored out on the
  `SyntaxError`. The suite now passes on 3.11 and 3.14, and 3.14 joins the CI matrix. The 3.11 lane
  that should have caught this has existed all along; no run of it has ever been observed.
- **`companion init --home X` was rejected.** `--home` is accepted on either
  side of the subcommand now, which is what everybody tries first.
- **A birthday was computed in the caller's timezone rather than the
  companion's.** A companion whose day had not turned over yet could be told it
  was her birthday, or not told on the day. Her own timezone decides.
- **A likeness stored as a JPEG or WebP was invisible.** `save_reference` wrote
  `reference-portrait.jpg`; everything that looked for it looked only for the
  `.png`. The reference existed and was never passed to a provider. Replacing a
  likeness now also removes the old one, so there is exactly one canonical face.

### Added

- **A photograph can become the appearance section.** Upload a likeness in the
  app, and `companion_vision.py` asks a model to read the face and propose the
  locked `appearance` block, rendered through the same interview fields and the
  same fixed order a typed description uses. It proposes; a person reads it and
  keeps it. Nothing reaches `SOUL.md` without that. This is the only part of the
  kit that calls a model, and the only thing in the app that costs money; it runs
  with `--ignore-rules`, so it is a model looking at a picture rather than the
  companion looking at a picture of herself.
- The app grows `GET/POST/DELETE /api/portrait`, `GET /media/portrait` and
  `POST /api/portrait/describe`; the write still goes through the section editor
  that already existed.
- `hermes -p <profile> chat -q 'hello' --oneshot --accept-hooks` is documented as
  the hook-consent path for an unattended install, in the README, the migration
  steps, doctor and setup's own next steps.
- The README says to probe a model chain rather than pick it from a catalog
  listing, and that a fresh install generates no image until a model-backed job
  has recorded a present.

### Also fixed, found by running that loop against a real model

- **The compiled image prompt carried instructions meant for her.** The
  appearance section ends by telling her how to maintain a wardrobe, with the
  command that does it, and the identity block was handing that to image
  providers as part of her face. The template marks that paragraph as excluded
  from prompts; a SOUL written before the marker is cut at the paragraph holding
  the first inline code span. This predates the vision work and affected every
  companion.
- The vision prompt asks for a complete sentence rather than a fragment, so a
  described face is shaped like a typed one, and it refuses to describe the
  absence of something — "no visible facial hair" is a phrase an image generator
  will draw around.

## 2.0.0 — 2026-09-10

The v2 line, built from the three review rounds recorded in
`notes/companion-kit-*-2026-09-10.md`. Its target: install Hermes,
configure a messaging platform, run one command, meet your companion — and have
that companion stay honest when the model is down.

### Phase 0 — stabilize (2026-09-10)

- Reflections are recorded from one JSON file (`companion_self.py ledger --file`)
  instead of quoted shell arguments. An apostrophe in a remembered sentence no
  longer breaks an unattended daily, weekly or monthly run. A rendered-prompt
  scan in the suite fails if any cron template goes back to quoting prose.
- `companion_prune.py` removes files older than seven days from the only two
  directories that hold disposable work: staged prose and Hermes's capture of
  each job's stdout. Both are resolved from the profile config, never from an
  argument. The weekly hygiene job runs it dry first.
- `companion doctor` reports staging sizes, the episode ledger size, and any job
  running on a model other than the profile default.
- Setup replaces the stock `SOUL.md` that `hermes profile create` writes, after
  backing it up, so a fresh profile no longer keeps Hermes's system prompt in
  place of the companion's identity. A SOUL someone else wrote is still left
  alone, and doctor now says so instead of staying quiet.
- `bin/companion` is a thin entry point; the command lives in `kit/cli/`.
- `companion repair` can re-render installed job prompts from the current
  templates, so a prompt fix reaches companions that already exist. The kit
  records a hash of each prompt it writes and never overwrites one you edited
  without `--prompts force`, which backs your version up first.
- `companion --version`, and this file.
- The questionnaire test no longer touches a real terminal.

### Phase 1 — present, loops, resilience (2026-09-10)

- The presence state gains `wants` and `private_stance`, and `Emotive.md` is
  rendered from it rather than written by hand. One state, one author.
- Open loops become a ledger, each entry carrying a `gentle_use` line saying how
  and when to raise the thing.
- `ActiveContext.md` is assembled by `companion_active.py` from the state, that
  ledger and whatever sensors exist. The model no longer writes it. An absent
  sensor produces no section rather than a claim.
- A no-agent present advancer carries the state forward when no model is
  available, marked `confirmed: false`; the hook says `UNCONFIRMED since HH:MM`.
- The pulse and autonomy loop get an assembled pre-read through `--script`;
  autonomy is gated by `--monitor-script` on a stable fingerprint; both use
  `--continuity`.
- `companion models` chooses per-tier models and reasoning effort and writes up
  to two `fallback_providers` entries into Hermes's config.
- A no-agent health watch, and `companion status`.
- The continuity hook waits at most two seconds on a contended lock.

### Phase 2 — outreach and senses (2026-09-10)

- Nothing sends directly any more. Jobs queue into `companion_outbox.py`; a
  no-agent dispatcher decides what leaves, one message per run, enforcing
  expiry, earliest-send time, the sleep window, per-content permission and the
  daily cap. Expired messages are dropped rather than delivered late.
- Being visibly awake — a message from the human in the last 45 minutes — steps
  past the sleep window without raising the cap.
- Five optional sensors write into `ambient/`: weather, daylight, dates, care
  follow-ups, and the relationship thread. A sensor with nothing to say writes
  nothing and removes its stale file.
- A morning job and a wind-down job on the edges of the sleep window, moving
  with it. Overnight is script-only.
- Adaptive quiet hours, opt-in: evidence only, a fortnight not a night, half an
  hour at a time, never below six hours, mentioned once when it moves.
- Setup asks for a location, which sensors to switch on, and whether unprompted
  photos and voice notes are allowed.

### Phase 3 — agents and memory (2026-09-10)

- Three agent types chosen first at setup — companion, colleague, quiet worker —
  deciding which jobs are installed and what the SOUL says the agent is.
- Memory caps sized at the end of setup from the context window and the rendered
  SOUL, written where Hermes reads them, instead of its 2,200/1,375 defaults.
- The vault becomes a local git repo with a commit job, and `companion restore`
  brings an old version back beside the current file rather than over it.
- Standing instructions and a relationship ledger, both injected every turn.
  Zero-budget sections are now named in the omissions line rather than being
  quietly absent.
- People-sharing setting: one record of the human across agents, or private.
- Missions with exclusive claims and self-releasing stale ones, worked in
  configurable autonomy windows.
- A check-in gated on Hermes's `on_session_end`, reflecting within minutes of a
  conversation rather than at 04:00, and silent otherwise.

### Phase 4 — identity (2026-09-10)

- A birthdate instead of a frozen age. The age is computed at render time and on
  every turn, the appearance paragraph moves with it, and the hook marks the day.
- SOUL.md gains section markers; `companion identity <section> --rerender`
  rebuilds exactly one and verifies every other byte is unchanged.
- The build and the human's boundaries are LOCKED against the companion; the
  self-edit helper refuses a block that restates them.
- Texting style, pet-name mode, a "won't do" list, and a paragraph the human
  writes that the companion cannot edit or argue with.
- Five more relationship frames that are not a romance with the romance removed.
- A durations sensor: "married 13 years", counted rather than remembered.

### Phase 5 — media and voice (2026-09-10)

- `companion_portrait.py` compiles the image prompt: locked appearance in a
  fixed order, then the recorded scene, then the style. It refuses when there is
  no state, because a scene invented for the camera is the thing to prevent.
- Timeline retention is a storage budget rather than thirty days. Albums keep
  copies that retention never touches, and take the human's own pictures too.
- Voice notes go through the outbox with the words beside the audio. Cloning
  writes Hermes's own neutts keys and requires saying the recording is yours.

### Phase 6 — the app (2026-09-10)

- `companion app`: one companion on localhost — now, timeline scrubber, loops
  and missions, what she knows, settings, identity, health and token usage.
- Two optional computed bars, written as signals rather than a nag schedule.

### Phase 7 — adoption (2026-09-10)

- `upgrade --soul keep` leaves an existing SOUL byte-for-byte alone.
- Verified on a simulated long-lived agent: memories, session database and vault
  all stay where they are while the machinery is installed around them.

### Phase 8 — docs (2026-09-10)

- `docs/CONCEPTS.md` (why it is shaped this way), `docs/REFERENCE.md` (the full
  command, file and scripting reference) and `docs/TROUBLESHOOTING.md` (organized
  by symptom). The README was rewritten as an explainer and installation guide;
  the reference material it had accreted moved into `docs/REFERENCE.md`, and the
  stale claims in it — six jobs, six relationship frames, thirty-day image
  retention, Hermes's default memory caps — were corrected or removed.
