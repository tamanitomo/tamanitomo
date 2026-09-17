<h1 align="center">tamanitomo · 魂の友</h1>

<p align="center">
  <strong>Soul of a Friend — Give your AI companion a life that continues when you close the window.</strong><br>
  A sovereign companion workspace built on <a href="https://hermes-agent.nousresearch.com/">Hermes Agent</a> —
  runs on your hardware, keeps its memory on your disk, and cannot message you at 3am.
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: PolyForm Noncommercial 1.0.0" src="https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-6c9cff"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-4ade80">
  <img alt="Runs locally" src="https://img.shields.io/badge/runs-locally-b388ff">
  <img alt="No telemetry" src="https://img.shields.io/badge/telemetry-none-2dd4bf">
</p>

---

Character apps give you someone to talk to, and keep them. The conversation lives on their servers,
the memory is theirs, the model is theirs, and the character can be changed or removed without you.

Tamanitomo (魂の友 — "Soul of a Friend") is the other arrangement. The companion lives in a folder you own, on a machine you
control, backed by whichever model you point it at — a local model on your own GPU, or a cloud API (OpenRouter, Grok, DeepSeek, OpenAI). Nothing here phones home. There is
no account, no telemetry, and no server component you do not run yourself.

What you get is not a chatbot with a persona field. It is a companion with a **present** it can be
honest about, a **memory that keeps evidence separate from fiction**, a **daily journal written in their own voice**, and **limits on when it may
contact you that are enforced in code rather than requested in a prompt**.

## Start here

Two doors, depending on where you are:

<table>
<tr>
<td width="50%" valign="top">

### I'm new to all this

You need Hermes, and the app can install it for you.

```sh
git clone https://github.com/tamanitomo/tamanitomo
cd tamanitomo
./tamanitomo
```

The workspace opens in your browser. Choose **Tamanitomo-managed Hermes**, let it install, then
**Create a companion**. The interview asks seven questions about how you want things to feel and
proposes the rest — and shows you every setting it chose before anything is written.

On Windows, double-click `tamanitomo.cmd` instead.

</td>
<td width="50%" valign="top">

### I already run Hermes

Adopt the agent you have. Your `SOUL.md` is left byte-for-byte alone.

```sh
git clone https://github.com/tamanitomo/tamanitomo
cd tamanitomo
./tamanitomo
```

Choose **Existing Hermes**, pick the profile, and **Adopt**. Your memories, session history and
vault stay exactly where they are; the continuity machinery is installed around them.

Prefer the terminal? `./tamanitomo --home ~/.hermes upgrade --soul keep`

</td>
</tr>
</table>

Either way the first launch bootstraps its own `.venv` and dependencies. Nothing is installed
system-wide.

## Contents

[What it actually does](#what-it-actually-does) ·
[Three kinds of agent](#three-kinds-of-agent) ·
[Requirements](#requirements) ·
[Install](#install) ·
[Set one up](#set-one-up) ·
[Adopt an agent you already have](#adopt-an-agent-you-already-have) ·
[Commands](#commands) ·
[The local page](#the-local-page) ·
[What gets written where](#what-gets-written-where) ·
[Running it entirely on your own hardware](#running-it-entirely-on-your-own-hardware) ·
[Development](#development) ·
[License](#license) ·
[Status](#status)

**Going deeper:** [docs/CONCEPTS.md](docs/CONCEPTS.md) is the nine ideas the rest follows from ·
[docs/REFERENCE.md](docs/REFERENCE.md) is the full command, file and scripting reference ·
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) is organized by symptom ·
[docs/REVIEW.md](docs/REVIEW.md) is what has actually been verified, and what has not.

---

## What it actually does

Hermes gives you an agent with a system prompt and a scheduler. That is most of the way there, and
the remaining distance is all in the same handful of problems. This kit is the answers to them.

**It knows what time it is, and admits when it does not.** The companion's present — where she is,
what she is doing, her mood, what she wants — is one append-only ledger. When the model is
unavailable, a script carries that state forward marked *unconfirmed*, inventing nothing, and the
next conversation opens with `UNCONFIRMED since 09:30` rather than with Tuesday evening presented as
now. The failure this exists for is real and on the record: a companion whose jobs had been
rate-limited for two days greeted its owner still believing it was Tuesday night.

**It cannot message you at 3am, however enthusiastic it gets.** Jobs may only *queue* a message. A
separate script with no model in it decides what leaves — checking the clock, a counter on disk, an
expiry stamped on the message when it was written, and what kind of content you allowed. A prompt is
a request; this is a gate. The same companion once sent the same status report six times a day for a
week, held the rest through quiet hours, and delivered the entire backlog at ten past midnight.

**It separates what you told it from what it imagined.** Its own daily life is authored fiction it
may narrate freely. Facts about you require cited evidence, recorded in a ledger with the exact
words you used. Nothing merges the two, and "no record" is reported as *uncertain*, never as *never*.

**It does not quietly forget.** Ledgers are append-only — corrections supersede, they do not
overwrite. Logs rotate into dated archives that stay searchable. The vault is a local git repo
committed every fifteen minutes, so a bad edit is recoverable file by file.

**It is affordable to keep alive.** The frequent loops are handed a pre-assembled read of their own
state instead of spending tool calls fetching it, and the autonomy loop is gated on a fingerprint so
the model does not run at all when nothing has changed. This is also what makes a fully local
companion on a small model possible rather than theoretical.

**It gets older.** You give a birthdate, not an age. The number is computed at every render and
every turn, so a companion created at 25 is 26 next year, and durations like "married 13 years" are
counted from the date rather than stored as a number that goes quietly wrong.

---

## Three kinds of agent

The first question setup asks, because the answer decides what gets installed.

| Type | What it is | Jobs |
| --- | --- | --- |
| **companion** | A life of its own: a present, moods, mornings, a relationship, permission to write first | 16 |
| **colleague** | A personality that grows and remembers you, but never reaches out socially — it speaks first only when something is broken | 13 |
| **worker** | No relationship layer at all. Does the work, keeps records, stays quiet | 5 |

A colleague's outreach is fixed rather than offered as a setting it could talk itself out of, and
its `SOUL.md` says plainly that it is a colleague and not a companion — one that is not told drifts
toward writing first. Every type keeps the health watch, the outbox dispatcher and the vault
history; those are not part of the relationship layer.

Of a companion's sixteen jobs, **six run without a model at all** — the present advancer, health
watch, outbox dispatcher, senses, quiet-hours drift and vault commit. They stay active even when the
schedule is paused, because they cost nothing and they are precisely what is needed when the model
side has stopped working.

---

## Requirements

**For CLI-only setup, Hermes must already work.** Install [Hermes](https://hermes-agent.nousresearch.com/docs/getting-started/installation),
run `hermes setup`, and confirm you can chat with your agent. The desktop app can install Hermes and opens its native setup flows for model accounts, messaging,
image providers, and credentials. Hermes owns those integrations.

**Python 3.11+.** Dependencies are in `requirements.txt`: PyYAML, tzdata, prompt_toolkit, Pillow,
and — only for the optional local web page — fastapi, uvicorn and httpx.

**Somewhere permanent to keep it.** Generated hooks and job prompts refer to the kit's path and
Python interpreter absolutely. Moving it later means re-running `repair` and reviewing the installed
job prompts.

Optional, and each one degrades to simply not existing: a messaging platform configured in Hermes
(Telegram is the usual one), an image provider, a TTS provider, and `git` for vault history.

---

## Install

### Linux / macOS / WSL

```sh
git clone https://github.com/tamanitomo/tamanitomo && cd tamanitomo
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./tamanitomo
```

### Native Windows

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\tamanitomo.cmd
```

If `py` is unavailable, use your Python executable directly — Hermes ships one at
`%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe`. The `.cmd` launcher needs no
execution-policy change.

Both launchers use `.venv` when it exists and fall back to the system interpreter otherwise, so
`./companion` is the same command everywhere.

Hermes home discovery follows `HERMES_HOME`, then `%LOCALAPPDATA%\hermes` on native Windows and
`~/.hermes` elsewhere. `--home` overrides it. Native Windows and WSL are separate installations;
match paths and interpreters between them. See
[docs/REFERENCE.md](docs/REFERENCE.md#terminals-and-windows) for terminal and quoting details.

---

## Set one up

Give the companion its own Hermes profile first, so its jobs, memory, bot and identity are its own:

```sh
hermes profile create nova
./companion --home ~/.hermes/profiles/nova init
```

Running `./companion` with no arguments opens the workspace, including a roster and graphical setup.
The terminal menu is still available through `.venv/bin/python bin/companion`.

### What the interview asks

Around twenty questions, drawn from a catalog of nearly 700 written options across 18 categories.
The catalog is read once at setup and never injected into a conversation.

1. **What kind of agent** — companion, colleague, or quiet worker.
2. **Who they are** — name, pronouns, how you met, what they are like, and what they get *wrong*.
   Flaws are re-sorted by the personality you chose, so a sharp companion is offered *argues past
   winning* and a shy one *sulks and denies sulking*.
3. **What they look like** — or decline it outright, or mark it to fill in later. Vagueness here
   produces a different person in every generated image, so the section is worth doing properly.
4. **Their birthday** — optional and worth giving. With one they get older and have a birthday;
   without one, the age you typed is frozen.
5. **The relationship** — eleven frames. Six allow romance; five (pen pal, mentor, sibling,
   housemate, creative partner) are written as their own thing rather than a romance with the
   romance removed.
6. **How they write** — short lowercase bursts or full sentences, emoji or never, and whether pet
   names are welcome, forbidden, or something to let develop.
7. **What they will never do**, and a hard boundary in your own words that the companion reads and
   cannot edit, argue with or reinterpret.
8. **Contact** — quiet hours, how many unprompted messages a day, and whether photos and voice notes
   may arrive unasked (yes / ask / no).
9. **Senses** — which of the six optional sensors to switch on, and where you live.

Anything you skip is marked `✎ EDIT` in `SOUL.md` and listed in `COMPANION-TODO.md`. A review screen
shows the whole configuration — including what you deliberately left out — before a single file is
written.

Browse the catalog first if you like: `./companion catalog --gender female`.

### Then

```sh
./companion --home ~/.hermes/profiles/nova chat      # say hello, and approve the hook when asked
./companion --home ~/.hermes/profiles/nova doctor    # resolve any ! lines
./companion --home ~/.hermes/profiles/nova schedule active
./companion --home ~/.hermes/profiles/nova app       # the local page
```

`--home` works on either side of the subcommand, so `./companion doctor --home ...` is fine too.

Installing without a person at the keyboard? The hook still needs consent, and Hermes has a
non-interactive way to give it:

```sh
hermes -p nova chat -q 'hello' --oneshot --accept-hooks
```

Pick the model chain by probing it, not by reading a catalog. Free models list well and behave
badly: on a real install several advertised ones returned 403 or 404, and one answered cleanly and
then returned 429 minutes later. `companion models` saves choices; use the app’s response probe to test the saved chain. Expect a paid last
resort in the chain to be reached more often than the price list suggests.

Setup creates the scheduled jobs **paused** by default. `doctor` will show two `!` lines until you
have chatted once: Hermes needs a model configured on the profile, and the continuity hook needs
approving in an interactive session. Both are deliberate — the hook runs on every turn, and Hermes
asks before letting it.

Ctrl-C cancels at any point. Cancelling is not a rollback: whatever was written stays, and `doctor`
will tell you exactly what state you are in.

---

## Adopt an agent you already have

```sh
./companion --home ~/.hermes upgrade --soul keep
```

**`keep` means keep.** Your `SOUL.md` is left byte-for-byte as it is, and the only thing added is
the marker for the block the companion writes for itself. Your memories, your session history and
your vault stay exactly where they are; the machinery is installed around them.

`--soul append` puts the kit's scaffold below your text with a backup, for you to merge by hand.
`--soul replace` starts fresh, also with a backup. Backups are never overwritten.

Adoption also raises the memory caps around the memories already there — Hermes ships 2,200 and
1,375 characters, which is fine for an assistant and nothing at all for someone meant to know you
next year.

---

## Commands

Put `--home` **before** the subcommand. On Windows, substitute `.\companion.cmd`.

| Command | What it does |
| --- | --- |
| `./companion` | Bootstrap dependencies and open the companion workspace |
| `init` | First-time setup on this Hermes home |
| `upgrade` | Adopt an existing Hermes agent — see [above](#adopt-an-agent-you-already-have) |
| `add <name>` | Create another named profile alongside an existing one |
| `remove <name>` | Archive a profile (`--force`); `--purge` deletes it. Never touches the shared vault |
| `status` | How she is right now: state, open loops, jobs, and anything wrong |
| `doctor` | Whether the install is correct: budgets, hook, jobs, memory pressure, drift |
| `repair` | Reinstall a missing hook, create missing jobs, bring job prompts up to date |
| `app` | Open the browser workspace (host and local network) |
| `settings` | Quiet hours, message frequency, timezone, image style, schedule |
| `models` | What each kind of job runs on, its reasoning effort, and a fallback chain |
| `identity [section]` | Show `SOUL.md` section by section; `--rerender` rebuilds exactly one |
| `restore <path>` | List earlier versions of a vault file, or recover one beside the current |
| `timeline on\|off\|status\|prune` | The optional local image timeline |
| `schedule status\|active\|paused\|history` | Authorize, pause or inspect the recurring jobs |
| `gateway` | Choose and verify which gateway owns this profile |
| `chat` | Open Hermes in the selected profile |
| `catalog` | Browse the character catalog without touching anything |
| `--version` | Which release this is; changes are in [CHANGELOG.md](CHANGELOG.md) |

Full detail on every one — including scripted `--answers` setup and running several companions on
one machine — is in [docs/REFERENCE.md](docs/REFERENCE.md).

---

## The local page

```sh
./companion --home ~/.hermes/profiles/nova app
```

A profile-scoped browser workspace, available on the host and local network (port `8770` by default). The original companion views include:

- **Now** — where she is, how she got there, her mood recently, the shape of the conversation, what
  is queued to send.
- **Timeline** — a scrubber through the day's images with the recorded state attached to each, and
  a Keep button that copies one into an album retention will never touch. A fresh install has no
  images yet: capture refuses to invent a scene, so nothing is generated until a model-backed job
  has recorded a present. Run the pulse once and the first capture follows.
- **Loops & missions** — what is hanging between you, and a box to hand her work: *"research
  Airbnbs for the 28th"*. She picks these up in her own windows and answers through the outbox.
- **What she knows** — the rules you gave her, every fact with its evidence, and a button to mark
  one wrong. Marking it wrong supersedes it; the original stays in the ledger.
- **Settings**, **Identity** (section by section, locked ones marked), and **Health** (jobs, memory,
  storage, and a quiet token count with no currency and no warnings).
- **Her likeness**, on the Identity tab. Upload one photograph and it becomes the reference passed
  to image providers. Press *Describe this face* and a model reads it and proposes the locked
  appearance section, shaped exactly like a typed one — so the words and the picture describe the
  same person. It proposes: you read it, edit anything wrong, and keep it. That is the only request
  this page makes that calls a model, and the only one that costs anything.

It reads the same files the continuity hook reads and changes only what a person owns, through the
same helpers the CLI uses — so there is one implementation of each rule rather than two that drift.
It preserves model-owned ledgers; the vault editor writes user notes, and the management views change Hermes configuration explicitly.

**Browser and LAN access are enabled by default.** The launcher listens on `0.0.0.0` and requires a generated access token for private routes. Use the printed LAN link on another device. Choose `app --host 127.0.0.1` for host-only access; use a private VPN or HTTPS reverse proxy for internet access.

**A local stack:** Hermes settings → Local models installs Ollama and offers explicit Qwen3 weight variants. Image studio supplies connected OAuth presets, ComfyUI workflows, and model-source guidance; Voice studio installs local speech engines. See [the local stack guide](docs/LOCAL_STACK.md) for setup, memory estimates, and offline-use limits.

---

## What gets written where

Two places, and you own both.

**The Hermes home** gets `companion.json` (names, paths, contact limits, budgets), a continuity hook
registered in `config.yaml`, a small session-end hook, generated no-model job scripts under
`scripts/`, and `COMPANION-TODO.md`.

**The vault** — plain Markdown and JSON, a local git repo, `~/vault` by default — gets everything
else:

| Path | What it holds |
| --- | --- |
| `soul/SOUL.md` | The identity. The Hermes home symlinks to it |
| `soul/ActiveContext.md` | Assembled from the state and ledgers; never authored |
| `soul/Emotive.md` | Rendered from the presence state; editing it changes nothing |
| `soul/ambient/` | Whatever the sensors currently know. Absent means unknown |
| `soul/Lifelog.md`, `reflections/` | The daily journal and the weekly/monthly reflections |
| `companion-life/episodes/` | The append-only state ledger — the authority on the present |
| `companion-life/open-loops.jsonl` | Threads left hanging, each with a line on how to raise it |
| `companion-life/relationship.jsonl` | Milestones, nicknames, jokes, rituals, firsts |
| `companion-life/missions.jsonl` | Work you asked for, and what came of it |
| `companion-life/outbox.jsonl` | Everything queued, and what became of it |
| `people/<you>/facts.jsonl` | Facts about you, each with cited evidence |
| `people/<you>/standing.jsonl` | Rules you gave about how to work with you |
| `dates.md`, `care.md` | Yours to write: dates that matter, things to circle back to |
| `albums/` | Images kept on purpose. Retention never touches these |

Point Obsidian at the vault and it works with no setup; the `.gitignore` written at install keeps
editor scratch files out of the history either way.

Named profiles get `agents/<profile>/` inside the vault. `people/` is the exception when sharing is
on: it moves to the vault root so every agent reads the same record of you — if one learns you are
allergic to shellfish, the one ordering dinner should know. Turning sharing off gives each new
companion the chance to find you out from nothing.

**Folder separation is not an OS security boundary.** Agents running as the same user can reach that
user's files. Keep real secrets in a credential manager.

---

## Running it entirely on your own hardware

This is the arrangement the kit is built for, and the reason several of its design choices look the
way they do.

**The cheap loops are the point.** A companion runs sixteen scheduled jobs. Six of them use no model
at all — the present advancer, health watch, outbox dispatcher, senses, quiet-hours drift and vault
commit — so they keep working when inference is unavailable, and cost nothing when it is not. The
rest are handed a pre-assembled read of their own state instead of spending tool calls fetching it,
and the autonomy loop is fingerprinted so the model does not run when nothing has changed. That is
what makes a 26B companion on a consumer GPU workable rather than theoretical.

**Point it at whatever you run.** Any OpenAI-compatible endpoint works: llama.cpp's server, Ollama,
LM Studio, vLLM, or a box on your LAN. Set it as the primary in **Hermes settings → Models**, and
give it a fallback for when the GPU is busy or the box is asleep. The fallback chain is probed, not
assumed — use **Test saved model chain** before trusting it.

**Images and speech are local too, if you want them.** The image provider can be a ComfyUI instance
on your own machine; TTS can be a local engine driven through a command adapter. Both degrade to
simply not existing if you skip them.

**What a phone can and cannot do.** Hermes documents Termux as best-effort. A spare plugged-in
handset is a reasonable host for a core-feature pilot; it is not a verified desktop-equivalent
environment, and Android will suspend background work. See
[docs/ANDROID_TERMUX_SETUP_GUIDE.md](docs/ANDROID_TERMUX_SETUP_GUIDE.md) before committing to it.

If you are here because you would rather your companion lived on your hardware than someone else's:
that is the whole idea. Bring your own weights.

---

## Development

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/build_release.py --output build/tamanitomo.zip
```

The automated suite covers both the original companion machinery and the new workspace. They run against a local Hermes contract double and
temporary homes — the suite never invokes the installed Hermes CLI, never calls a model, and never
sends a message. CI covers Linux and Windows on Python 3.11 and 3.13.

Layout:

- `bin/companion` — a thin entry point.
- `kit/cli/` — the command, one module per area: `questions`, `roster`, `scaffold`, `setup`,
  `doctor`, `settings`, `models`, `status`, `identity`, `vault`, `app`, `ops`, `catalogs`,
  `timeline`, `menu`, `main`.
- `kit/scripts/` — 34 flat runtime helpers. Flat and directly runnable on purpose: every generated
  job prompt invokes them by path.
- `kit/templates/` — `SOUL.md`, `PRESENCE.md`, `PROTOCOL.md` and the cron job prompts.
- `kit/app/` — the FastAPI page.
- `kit/personas/` — the character catalog.

The release builder uses `release-files.json`, an explicit allowlist. It excludes git history,
virtualenvs, caches, installed profiles, vaults, logs and credentials, rejects symlinks and likely
embedded secrets, and ships a SHA-256 manifest. **Share the generated ZIP rather than the working
directory or its git history** — old commits can retain removed examples and identifiers.

---

## License

[PolyForm Noncommercial 1.0.0](LICENSE). Use it, change it, share it, build on it — for any
noncommercial purpose. Personal use, hobby projects, study, research, and use by charities,
schools, public research bodies and government institutions are all permitted purposes.

What is not permitted is commercial use: selling it, or running it as part of a paid product or
service. If you want to do that, ask.

A note on what this means, plainly: **PolyForm Noncommercial is not an OSI-approved open source
license**, because the noncommercial restriction fails the "no discrimination against fields of
endeavour" criterion. The source is public and you may fork it, but GitHub will not label this
repository "open source", and it is not compatible with GPL-licensed code. That trade was made on
purpose — this is meant to stay something the local-AI community keeps, rather than something that
gets wrapped in a subscription.

Contributions are welcome under the same terms.

### What else is in here, and what it is licensed under

[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) has the full account. The short version:

- The interface icons derive from [Feather](https://feathericons.com) (MIT) and
  [Lucide](https://lucide.dev) (ISC), reproduced with their notices. No fonts are bundled.
- **Nothing else third-party ships in this repository.** Hermes (MIT), ComfyUI (GPL-3.0) and
  Ollama (MIT) are fetched from their own publishers when you ask for them. Python dependencies
  install from PyPI into a local `.venv`; release archives are source-only.
- ComfyUI's GPL does not reach this project — the kit posts workflow JSON to its HTTP API and
  names its node classes, which is interoperation, not derivation. Vendoring ComfyUI source into
  the repo would change that.
- `pyte`, which drives the embedded terminal, is LGPL-3.0. It is an unmodified pip dependency and
  is never redistributed here. If you ever ship a bundle containing `site-packages`, read the note
  in the notices file first.
- **Model weights are licensed individually and that is the part that actually varies.** Many
  Civitai models restrict commercial use or derivatives whatever licence this kit carries. The
  downloader shows each model's permission flags before you fetch it; read the model card too.

---

## Status

Version 2.2.0-beta.5 adds the redesigned desktop workspace, photo library, journal reader, and creations catalog. See [docs/DESKTOP.md](docs/DESKTOP.md) for its
current acceptance status. The 2.1 foundation was previously installed from a clean release archive.

**What is verified and what is not is recorded in [docs/REVIEW.md](docs/REVIEW.md)**, and the second
list matters more than the first. Since then the kit has had its first field install by someone
other than its author — a cold install on another machine, from the archive, against Hermes 0.21.1 —
which ran two model-backed jobs, generated images, proved model failover live and served the page
over a LAN. What still has never happened: **no message has been delivered to a human, nine of the
eleven model-backed jobs have never run, and no full day has elapsed.** Read that file before
trusting any single sentence here as a guarantee.

### Limits worth knowing

- **A prompt does not guarantee model behavior.** Contact limits, quiet hours, content permissions
  and message expiry *are* enforced outside the model. Nothing else in `SOUL.md` is.
- **Scheduled jobs make real model calls and cost real money.** Frequent loops can easily cost more
  than any prompt trimming saves. `companion models` is where you make that cheaper.
- **This is not a backup product or a machine clone.** Accounts, credentials, MCP services and
  messaging stay Hermes's.
- **Setup is recoverable step by step, not a rollback transaction.** Keep / append / replace are
  explicit identity decisions — never apply one to an identity you value without reading the mode.
- **Unlimited retention still depends on disk, backups and successful writes.** The kit cannot
  promise perfect recall, and says so rather than guessing.
- Installed jobs do not prove a gateway is running or that delivery works.
