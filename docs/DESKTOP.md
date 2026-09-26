# Tamanitomo workspace

The app runs alongside Hermes. Its Python environment, UI, and release files are
separate from Hermes's runtime. Hermes continues to own profiles, model calls,
conversation storage, messaging, and scheduling. The vault remains plain files.

For a first-time recipient, start with [the handoff checklist](FIRST_RUN.md).

## Start on Linux, macOS or Windows

Extract the release into a permanent, writable folder. On Linux or macOS:

```sh
chmod +x tamanitomo
./tamanitomo
```

On Windows, double-click `tamanitomo.cmd`, or run it from a terminal:

```powershell
.\tamanitomo.cmd
```

The launcher creates `.venv`, installs the app dependencies, and opens the local
workspace. If Python 3.11+ is absent, it provisions Python using the official uv
installer. Internet access is required on first setup. Later launches reuse the
installed environment. Existing CLI commands still work, for example
`./tamanitomo --home /path/to/profile doctor`.

The app binds to `0.0.0.0:8770` for host and LAN browser access by default. A second launch opens the existing authenticated
workspace when it belongs to the same Hermes root; if that port belongs to a
different service, a free port is chosen. `app --no-open` suppresses browser launch.
The existing terminal menu remains available through `bin/tamanitomo` (or `bin/companion`) with no arguments.

## Choose an installation

**Existing Hermes** uses the usual Hermes home, or the home provided with `--home`.
It discovers existing profiles without adopting or rewriting them. Choose a profile,
then **Adopt as a companion** if it does not have the kit installed. Adoption keeps
its existing SOUL and memories.

**Kit-managed Hermes** provisions a separate home and runtime below the app's data
directory. The staged official installer omits the global Hermes command/PATH stage,
so it does not replace an existing `hermes` command. Host prerequisites and package
caches may still be shared; this is data/runtime isolation, not an OS sandbox.

The app's data directory is `%LOCALAPPDATA%\tamanitomo` on Windows or
`$XDG_DATA_HOME/tamanitomo` (normally `~/.local/share/tamanitomo`) on Linux (with legacy
fallback to `companion-kit`). `TAMANITOMO_APP_STATE` (or `COMPANION_APP_STATE`) overrides it. Installation progress is resumable by rerunning
Install after an error; completed profiles and vault records are not rolled back.

Installer references: [Hermes installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation)
and [uv installer options](https://docs.astral.sh/uv/configuration/installer/).

## Complete onboarding

1. Create a companion or adopt an existing profile. Choose its relationship frame,
   identity, contact limits, and vault. The kit installs the appropriate job set.
2. In **Settings**, configure the primary model and ordered fallbacks.
   Paste an API key, or use **Provider sign-in** for Hermes's own OAuth flow.
3. Use **Test saved model**. This makes a small real inference request to the
   selected provider with fallback disabled and can incur provider charges. It
   leaves the saved configuration and vault unchanged. See [inference routing](INFERENCE.md)
   for the separate fallback behavior used by ordinary chat and background work.
4. Review the exact hooks and approve them with an explicit first message. This
   is separate from granting general tool permissions.
5. Configure messaging if wanted, choose gateway ownership, and install/start the
   native gateway service. Activate the routine after the setup checks pass.

Hermes's native consoles are embedded for account login, messaging, tools, voice,
images, and MCP. Use the arrow buttons and Enter for menus; the input field can send
pasted text. Consoles are profile-scoped, keep their screen only in memory, and stop
after 30 minutes without access. Close one before changing settings elsewhere.
Configuration details can also be changed one dotted key at a time through **All
Hermes settings**. Secret fields are masked; credential input is write-only.

## Conversations and shared experience

App chats execute Hermes in the selected profile. They use that profile's SOUL,
continuity hooks, memories, and vault, just as its Telegram conversations do.
Open the floating **Chat** dock from any page. It shows the owner’s eligible
conversation history, offers **Earlier messages**, and resumes the selected local
session. A first app conversation creates a native session with the same underlying
companion. App replies are not mirrored into Telegram.

Compatible Hermes runtimes stream reply text through the dock. The dock preserves
its draft and session while navigating between pages; see [the chat contract](CHAT_CONTRACT.md).
Approval-heavy interactive conversations can be handled in Hermes's native client.
The app never automatically grants unseen tool approvals.

## Background operation and updates

**Health** exposes job status, native run history, schedule edits, pause/resume, and
Run next tick. Running a job requires its owning gateway. Model-free maintenance is
kept active when pausing the routine. **Apply job models** updates existing pins
through `hermes cron edit` and preserves IDs and history.

Changing routine preferences synchronizes kit-managed prompts and matching schedules.
Hand-edited prompts/schedules remain protected and appear in repair output for review.
A full outage is shown as unavailable state; the kit does not invent a successful
run or promise that every failure is recoverable. Native Hermes owns retries and
provider failover.

**Update Hermes** invokes its updater without patching the Hermes source tree.
The kit discovers providers from the installed catalog, scopes CLI calls explicitly,
and checks session schemas before reading them. If a future Hermes version removes
a required interface, the affected feature reports an error; the vault remains
accessible. No application can guarantee compatibility with every future upstream
change. Run Health and a response probe after updating.

## Find companion content

**Home** brings together the current scene, recent creations, a journal preview,
and links to conversations and activities. **Timeline** combines lived moments,
photos, and journal entries. It labels scenes carried forward without confirmation.

**Photos & albums** includes both scheduled captures and other images saved in the
selected companion's vault. Filter by day, search, or collection; open a full-size
image, download it, or keep a copy in an album. Existing images remain visible when
photo sessions are off. The status panel distinguishes disabled sessions, missing
jobs, paused jobs, and recent failed capture attempts.

To enable scheduled captures, choose **Preferences → Photo sessions**, select an
image style and storage budget, enable 15-minute sessions, and save. This synchronizes
the job set. A working image provider, running gateway, and current scene are still
required; each capture can incur inference and image charges.

**Journal** reads dated `## YYYY-MM-DD` entries from Lifelog.md and its monthly
archives, with month/text filters. The reader preserves the original files. It caps
preview scans at 16 MB and individual displayed entries at 100,000 characters.
**Creations** discovers Markdown, text, images, audio, video, and PDF files inside the
selected companion's data folder. Images and media play inline; PDFs download.
It does not search unrelated profiles or arbitrary folders mentioned in messages.
The catalog scans at most 10,000 files and returns up to 1,500 items; the Vault remains
available for other files. Configuration, hidden files, backups, and likely secrets
are excluded. Reload the view to discover new output.

The five primary destinations are **Home**, **Journal**, **Vault**, **Photos**,
and **Settings**, with a compact navigation bar on phones. Home and Settings link
to auxiliary views such as Companions and Us. **Go to page** (Ctrl/Cmd K) finds a
page. Settings includes schedule editing, job status and native run history.

## Vault and relationships

**Vault** browses Markdown/JSON/text, follows `[[wiki links]]`, searches files,
downloads files, and exports a ZIP. Hidden files, symlinks, and likely credential
files are excluded. Exports are capped at 20,000 files / 2 GB; use the folder directly
for larger backups. Search scans up to 2,000 eligible files and returns 50 matches.

The editor writes `notes/*.md`, `dates.md`, and `care.md`. It refuses to overwrite a
file changed since it was opened. Edit identity and memory through their dedicated
screens; companion ledgers remain append-only. The UI is a vault browser with basic
Markdown headings and wiki links, not a full Obsidian replacement.

**Together** shows shared history, optional milestones, and two computed indicators.
The indicators are enabled by default; explicit opt-outs are preserved. They describe
recent state, not relationship progress. Progression visibility, pace, peer interaction,
indicator visibility, and romance preferences live only in **Preferences → Relationship**. Adult
themes require explicit adult confirmation and a compatible romantic frame; provider
rules still apply. Time away never erases earned milestones. Retirement keeps a
moment's history. These settings guide a model; they cannot guarantee every response.

Archive profiles before permanently deleting them. The external vault remains intact.
Stop the owning gateway and uninstall any dedicated service before archiving. Inspect Health after restoring a profile. Use Restart-root after changing ownership to apply shared routing changes.

## Private remote access and Android

The API requires the launch token for private routes, including images and exports.
It has explicit installation/profile addressing; there is no server-global selected
companion. This is the foundation for a later Android client. Each friend's server
has its own token and data. The beta does not implement multi-user accounts or an APK.

For private remote access use a VPN/tunnel or HTTPS reverse proxy. LAN binding is the default;
use `app --host 127.0.0.1` for host-only access. Do not expose an unencrypted token-bearing
HTTP port to the public Internet. The displayed launch link contains the access token.
The page removes it from the address bar after loading and retains it in tab storage.
Restart the app after deleting its `access-token` file to rotate it.

## Verification limits

The current workspace passed all 548 tests on Linux/Python 3.14. The preceding
beta.2 release passed all 542 tests in a clean extracted release with Python 3.11. Seven focused
content tests cover profile isolation, journal archives, credential exclusions, and
album preservation. Browser checks cover the home, photo viewer, journal search,
combined timeline, preference panels, and job filtering/schedule editor.

The Linux native contract test installed 16 jobs in a disposable Hermes 0.21.1 profile,
repaired without duplicate IDs, and updated 10 model-backed job pins. It made no model
calls and sent no messages. The native console and 54-entry provider catalog were
exercised. The browser creation flow was exercised against a contract double.

A fresh Linux managed installation completed all seven official stages and passed
version/catalog checks without modifying the existing Hermes runtime.

Native Windows launch, real-provider app chat,
and complete scheduled-day behavior still require their own acceptance runs. The
source archive is a beta for these private tests, not a claim those runs have passed.

## Chat dock and workspace names

The floating dock remembers its session and unsent draft within the browser tab.
Enter sends; Shift+Enter adds a line. Reply status remains visible while Hermes works.
Compatible Hermes runtimes now stream reply text; see [hosting and streaming notes](HOSTING.md) for verification and limits.

In Hermes settings, change Workspace display name to label any profile, including
the default root. This label does not rewrite the companion identity or profile paths.
Gateway status checks and service controls are displayed together in Hermes settings.

Closing the workspace does not stop the independently installed Hermes gateway.
Enabled jobs can continue while that gateway and its host remain running, with usable
provider credentials. Photo sessions must be configured and enabled separately.
App chat and setup operations should finish before the app process is stopped.

Hosted deployment: [HOSTING.md](HOSTING.md).

### Creator, documents, themes, and voice

The creator uses the character catalog for personality and appearance choices. “Write your own” reveals a text field; choosing a preset again excludes the custom text from submission. Choosing appearance details also enables the visual identity.

Identity includes a visual creator, saved-photo reference picker, missing-section repair, and a complete document editor. Repair appends missing sections while preserving existing writing. Add an appearance before requesting portraits; a recorded scene is also required. The document editor supports SOUL.md, profile-root Markdown documents, and memories/*.md. Vault supports editing other Markdown documents. Saves retain backups and reject stale revisions.

Use Rename beside the companion selector to change the workspace display name. Themes are saved for this browser. Hermes settings includes searchable configuration keys; Account sign-in / OAuth opens the installed Hermes provider flow for ChatGPT, Grok, and other supported accounts.

Voice studio saves native Hermes TTS configuration. Local engine installation runs in Hermes’s Python environment; model downloads may happen on the first preview. NeuTTS accepts a 1–30 second uncompressed WAV reference and its transcript, and requires espeak-ng. Speed and pitch controls appear only for engines that support them. Cloud engines require their corresponding accounts and may charge for previews. Preview files and voice references remain profile-scoped. Speech generated by Hermes uses the saved voice; restart persistent workers to reload their settings when necessary.
