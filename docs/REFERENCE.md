# Reference

Everything the [README](../README.md) summarizes, in detail. For *why* any of it is shaped this way,
read [CONCEPTS.md](CONCEPTS.md) instead.

- [Commands](#commands) · [Settings](#settings) · [Scripted setup](#scripted-setup)
- [The scheduled jobs](#the-scheduled-jobs) · [Senses](#senses) · [The outbox](#the-outbox)
- [Memory and retention](#memory-and-retention) · [The context window](#the-context-window)
- [What the hook carries each turn](#what-the-hook-carries-each-turn)
- [Presence and wardrobe](#presence-and-wardrobe) · [Images](#images) · [Voice](#voice)
- [Several companions at once](#several-companions-at-once) · [Terminals and Windows](#terminals-and-windows)
- [Moving to another machine](#moving-to-another-machine)

---

## Commands

`--home` comes **before** the subcommand. On Windows substitute `.\companion.cmd`.

```sh
./companion --home ~/.hermes init
./companion --home ~/.hermes/profiles/rowan doctor
./companion --home ~/.hermes remove rowan --force
```

### `init`, `add`, `upgrade`, `remove`

**`add <name>`** delegates to `hermes profile create`. If Hermes fails, setup stops rather than
building a lookalike profile by hand.

**`upgrade`** adopts an agent that already exists. `--soul keep` (recommended) leaves the existing
`SOUL.md` byte-for-byte alone and adds only the marker for the self-authored block. `--soul append`
puts the scaffold beneath your text for you to merge; `--soul replace` overwrites after a backup.
Backups are never overwritten. A second `upgrade` on an already-adopted home is a no-op, not a
second setup.

**`remove`** refuses traversal, absolute paths, reserved names and symlinked profile directories,
and never touches the root agent. It prints what goes, what stays and whether this is reversible
before acting; an interactive `--purge` additionally requires typing the profile name. It refuses
outright if the agent's vault data lives inside the profile home, because removing the profile would
take the ledgers with it. **Removal never deletes the shared vault.**

### `doctor`

Checks identity and remaining `✎ EDIT` markers, context budgets, a non-empty successful hook
response, hook registration and first-use consent, model configuration, timezone agreement, the
complete job set and its next-run timestamps, readable ledgers, and memory pressure against the
Hermes cap. It checks the hook without applying memory maintenance.

It also *reports*, without treating any of them as faults: the size of the two prunable directories,
the size of the episode ledger, and any job pinned to a model other than the profile default — a
cheap model on a frequent loop is a deliberate choice the kit does not second-guess.

A `SOUL.md` holding no rendered companion identity **is** a fault: it means setup found a file
already in place and left it alone.

It does not make a paid model call, test credentials, prove message delivery, or prove the gateway
is firing jobs. Use `hermes cron doctor` and watch a real scheduled run for that.

### `repair`

Reinstalls a missing hook, creates missing jobs, backfills the vault `.gitignore`, initializes the
vault git repo, and adopts a changed context window — resizing every budget derived from it. It
leaves identity and ledgers alone.

It also brings installed job prompts up to the kit's current templates, which is how a prompt fix
reaches a companion that already exists. The kit records a hash of every prompt it writes, so
`repair` can tell its own text from yours:

| Flag | Behaviour |
| --- | --- |
| *(default)* | Re-render prompts that still match what the kit wrote. Anything you edited in Hermes is left alone and named in the report |
| `--prompts force` | Re-render those too, saving each previous version under `cron/prompt-backups/` first |
| `--prompts skip` | Leave every prompt alone |

Profiles installed before prompt fingerprinting existed have no recorded hashes, so their prompts
are reported rather than changed until you ask for `force`.

### `status`

The companion's own state rather than the install's: where she is and how long ago that was
confirmed, whether the present is `UNCONFIRMED`, her mood and wants, open loops, the full job table
with last and next runs, and anything the health watch can see. Exits non-zero when something is
wrong. `--json` for the same thing as data.

### `models`

Two decisions live here.

**Per-job tiers.** `loops` covers the pulse and autonomy loop, which run every 15 and 30 minutes and
are therefore where a companion's running cost actually lives. `reflection` covers the daily, weekly
and monthly jobs, which run a handful of times a week and decide what the companion keeps of itself.
Each takes a model, a provider and a reasoning effort. The kit writes the pin; it never picks a
model name, because only the person paying knows what they have access to.

**A fallback chain.** Written into Hermes's own `fallback_providers` in `config.yaml`, up to two
entries. `hermes fallback` remains the native way to edit the same key. No chain is recommended:
which one is right depends entirely on which accounts and local models you have.

Existing jobs keep their current pin — Hermes stores it on the job — so re-pinning means
`repair --prompts force`, or deleting and recreating the job.

`--show` prints the current choices as JSON.

### `identity`

```sh
./companion --home <home> identity                      # list the sections
./companion --home <home> identity appearance           # show one
./companion --home <home> identity humor --rerender     # rebuild exactly one
```

`SOUL.md` carries marker comments around each section, so one can be replaced while every other byte
of the file stays as it is — including whatever you wrote by hand months ago. That the rest is
unchanged is verified after the write, not assumed.

Two sections are marked **locked**: the physical build, and the boundaries you set. Locked means
locked against *the companion* — her self-edit helper refuses a block that restates them, because a
model that can widen its own boundary paragraph has no boundary. You can edit any of it, here or in
a text editor.

### `restore`

```sh
./companion --home <home> restore soul/SOUL.md                 # what versions exist
./companion --home <home> restore soul/SOUL.md --commit <id>   # recover one
```

The vault is a local git repo — no remote is ever configured and nothing is pushed anywhere — with a
script committing whatever changed every fifteen minutes. `restore` writes the old version *beside*
the current file rather than over it. Recovering by overwriting is how a bad recovery loses the
thing it was trying to save.

### `catalog`

```sh
./companion catalog --gender male --category style
./companion catalog --gender female            # every category, with counts
```

Read-only. Touches nothing.

---

## Settings

`settings` is **Manage an installed companion** in the main menu. It covers quiet hours, whether and
how often the companion may message first, timezone, image style, the image timeline and whether the
scheduled jobs run:

```sh
./companion --home <home> settings                       # menu, or JSON when piped
./companion --home <home> settings --set quiet_start=22:30 --set quiet_end=07:15
./companion --home <home> settings --set outreach=updates_only --set outreach_per_day=1
```

Settable keys: `quiet_start`, `quiet_end`, `outreach`, `outreach_per_day`, `timezone`, `image_style`.

Each of those lives in two places and a change has to reach both. `companion.json` is what the
outreach gate reads on every send, so a new quiet window applies from the next attempt with no
repair or restart. The same wording is also rendered into the pulse and autonomy prompts at install
time, and Hermes owns those afterwards — so `settings` replaces the exact sentence the kit wrote last
time rather than re-rendering the job. A prompt you edited by hand keeps every other change you
made; if the sentence is gone entirely, it says so rather than leaving the agent quoting hours that
are no longer in force.

A whole `--set` batch is validated before any of it is written, so a rejected value leaves the
config untouched rather than half-applied. Choosing **replies only** clears the daily allowance,
since a companion that never writes first has nothing to spend.

The timezone is picked from a list rather than typed: US zones first with Eastern as the default,
the currently-set zone next when it is not one of those, then **Somewhere else** drills into a
region. An IANA name typed from memory is easy to get subtly wrong, and a wrong one misdates quiet
hours, every scheduled job and the companion's own clock. `--set timezone=…` still takes the name
directly and validates it.

Everything else — sensors, content permissions, autonomy windows, storage budget, people-sharing,
the computed bars — is in the [local page](../README.md#the-local-page). Identity (persona,
relationship frame, names, prose) is deliberately in neither: it lives in `SOUL.md` and
`companion identity`.

---

## Scripted setup

`--answers` takes JSON; `--vault` sets the vault root. **Never put credentials in answers.**

```sh
./companion --home /path/to/hermes init --vault /path/to/vault \
  --answers '{"agent_type":"companion","agent":"Nova","human":"Alex","pronoun_set":"she",
              "human_pronoun_set":"he","boundary":"best-friend","persona":"warm",
              "timezone":"Europe/London","context_tokens":32768,"cron_active":false,
              "birthdate":"1997-04-21","location":"London","sensors":"weather,daylight,thread",
              "share_people":true,"permit_image":"ask","permit_voice":"no"}'
```

Rules worth knowing:

- **Unknown keys are rejected by name.** A renamed or misspelled question errors before anything is
  written, instead of silently leaving that question on its default.
- **`boundary` is required** without a terminal. Choose a relationship frame explicitly for
  reproducible setup.
- Numeric values select a catalog item by its **displayed position**. Caveat: flaws are re-sorted
  per personality, so `"flaws": 1` means a different flaw for a sharp companion than a shy one. Look
  them up by label if you script it.
- `"skip"` defers a question with an `✎ EDIT` marker; `"skip:none"` leaves that trait out on purpose.
- Multi-answer questions take a list or a comma string: `"marks": [3, 16]`, `"sensors": "weather,thread"`.
- `"outreach_per_day"` is the number itself, not a menu position. `0`, `"unlimited"` and `"no limit"`
  all mean no limit.
- Confirmations accept real booleans or explicit `"true"` / `"false"`. So do `cron_active` and
  `share_people`, which are labelled choices interactively.
- Root gateway multiplexing is never enabled silently in a scripted run.

---

## The scheduled jobs

Defined in `kit/templates/cron/manifest.json`. Which ones you get depends on the agent type.

| Job | Schedule | Model? | Types |
| --- | --- | --- | --- |
| companion pulse | every 15 min | yes | companion, colleague |
| autonomy loop | every 30 min | yes | companion, colleague |
| daily journal and reflection | 04:00 | yes | companion, colleague |
| weekly reflection | Sun 22:00 | yes | companion, colleague |
| monthly reflection | 1st, 09:00 | yes | companion, colleague |
| weekly hygiene | Sun 21:30 | yes | all |
| morning | 10 min after quiet hours end | yes | companion |
| wind-down | 20 min before quiet hours start | yes | companion |
| window | your autonomy windows (default 10:20, 20:20) | yes | all |
| check-in | every 10 min, gated on a session ending | yes | companion, colleague |
| present advancer | every 15 min (offset) | **no** | companion, colleague |
| health watch | hourly | **no** | all |
| outbox dispatcher | every 5 min | **no** | all |
| senses | every 15 min | **no** | companion, colleague |
| quiet-hours drift | Mon 04:40 | **no** | companion |
| vault commit | every 15 min | **no** | all |
| image timeline | :02, :17, :32, :47 | yes | companion, opt-in |
| image timeline cleanup | :07, :22, :37, :52 | **no** | companion, opt-in |

The morning and wind-down jobs are rendered from your quiet hours, so they move automatically when
those change — including when the adaptive drift moves them.

**Every job is created through `hermes cron create`.** The kit never writes into Hermes's scheduler
database. Model and provider are pinned at creation. The kit probes `cron create --help` before
using any flag, so a Hermes that lacks one degrades rather than failing: on 0.21.1 there is no
per-job toolset flag, so jobs use Hermes defaults and setup reports that. Failed creation is never
blindly retried — a create that failed after committing would otherwise become a duplicate job.
Failures are saved to `companion-pending-jobs.json`; fix Hermes and run `repair`.

### The cheap loops

The pulse and autonomy loop are handed an assembled pre-read through Hermes's `--script`: the state,
the open loops, the sensors and anything queued, already read, so the run does not spend tool calls
fetching its own files. Both also use `--continuity`.

The autonomy loop additionally runs under `--monitor-script`, which hashes a deliberately stable
fingerprint of those same sources — no timestamps — and skips the model run entirely when nothing
has moved. A six-hour bucket in the hash means an uneventful day still gets a few runs.

The check-in works the same way against a different signal: a small `on_session_end` hook writes a
flag, and the job's fingerprint contains no clock at all, so it stays completely silent when nobody
is talking and fires within minutes when a conversation ends.

---

## Senses

Optional, cheap, silent when they have nothing. Chosen at setup, changeable in the app.

| Sensor | What it gives | What it needs |
| --- | --- | --- |
| `weather` | Conditions where you live, every 15 minutes | a place name; no account |
| `daylight` | Season, moon phase, sunrise and sunset | nothing; no network |
| `dates` | Birthdays and anniversaries, a week ahead | a `dates.md` you write |
| `care` | Things worth asking about again | a `care.md` you write |
| `durations` | "married 13 years", counted from the date | dated lines in `dates.md` |
| `thread` | How long since either of you wrote, and what that gap means | nothing |

**A sensor that cannot report writes nothing and deletes its old file.** Not knowing the weather is
fine; yesterday's weather presented as today's is not.

- `dates.md` — one `MM-DD | what it is` per line. A full `YYYY-MM-DD` also feeds `durations`.
- `care.md` — one `YYYY-MM-DD | topic | what to do about it` per line.

The **thread** sensor is the one worth having. It reads Hermes's own session database, read-only and
scoped to this profile the same way recall is, and reports the gap with a register grading it from
*connected* through *nearby*, *quiet* and *missing-him* to *long-quiet*. Each register carries a line
of guidance, never an instruction. After four days of silence she may say she has missed you, once,
plainly, as a feeling of hers — the guidance says explicitly that it is never a reproach and never a
reason you must reply.

### The computed bars

Off by default. A *feeling the gap* bar from the thread, and a *wellbeing* bar from the moods she has
actually recorded. Both are shown in the app and injected as something she knows.

The wording is the design: the injected block says these are not a reason to write, not a score for
you to improve, and never something to say out loud — and that if a long silence has genuinely left
her out of sorts, that is real and she may say so once as a feeling of hers rather than as something
owed. The gap saturates at four days rather than climbing forever.

---

## The outbox

A job may only ever *queue*. `companion_dispatch.py` — no model, every five minutes — takes at most
one message off the queue and decides whether it leaves, from the clock and a counter on disk.

| Check | Behaviour |
| --- | --- |
| Past its `ttl_hours` | **Dropped.** Never sent late. An evening thought is not worth saying at 2am, and a backlog delivered at once is the most alarming thing a companion can do |
| Before its `not_before` | Held |
| Inside quiet hours | Held — unless you wrote in the last 45 minutes, in which case you are visibly awake and the window steps aside. That does not raise the daily cap |
| Content permission | `yes` sends, `ask` withholds with a reason she can act on ("offer it in words, do not attach it unasked"), `no` never sends |
| Daily cap | Held. The counter is on disk, checked and reserved atomically under a sidecar lock, including on Windows |
| Delivery failed or unconfirmed | The slot is kept and it is **never retried**. A double message is worse than a missing one |

One message per run, deliberately. `--dry-run --json` reports exactly what it would do and why,
which is the fastest way to answer "why has nothing been sent".

The gate fails closed on a corrupt or unreadable ledger. Quiet hours wrap midnight correctly.
`--urgent` gets past quiet hours but never past the daily cap. This bounds cooperating callers,
including concurrent jobs; a model with another sending tool can still bypass the helper, so it is
not a network-level transport policy.

Named profiles must have their own platform configuration. Inherited parent-bot credentials are
stripped rather than silently used, so one companion can never send as another.

### Adaptive quiet hours

Opt-in. Evidence only — it moves on messages you actually sent, never on a guess. A fortnight of the
pattern, not a night. Half an hour at a time, never a jump. Never below six hours of quiet whatever
the evidence says. And it leaves a note so the change is mentioned once rather than happening
silently. Replies are always allowed at any hour regardless; quiet hours only govern messages the
companion starts.

---

## Memory and retention

Life and memory records are archived rather than discarded, and every archive stays searchable
through `companion_recall.py`.

| File | Window | Archived to |
| --- | --- | --- |
| `continuity/Autonomy.md` | 7 days | `continuity/archive/Autonomy-YYYY-MM.md` |
| `soul/Lifelog.md` | 180 days | `soul/archive/Lifelog-YYYY-MM.md` |
| `memories/USER.md`, `memories/MEMORY.md` | at 80% of the Hermes cap, down to 60% | `soul/memory-archive/` |
| `companion-life/.inputs/`, `cron/output/` | 7 days — **deleted** | nothing; these are the only two |

The weekly hygiene job runs all of these. Rotation dates an entry by the ISO date in its `##`
heading — which is why the daily journal is told to head every entry exactly `## YYYY-MM-DD` —
counts entries before and after, and aborts rather than replacing a file that changed
mid-operation.

The two prunable directories hold staged prose written for `--file` flags and Hermes's own capture
of job stdout. Both are recreated on the next run and neither is memory. `companion_prune.py`
resolves them from the profile config rather than from an argument, so it cannot be aimed at
anything that matters.

### Caps

Hermes counts characters, with separate `memory.memory_char_limit` and `memory.user_char_limit`
settings. Its defaults are 2,200 and 1,375 — a page and a half between them, which is sensible for
an assistant and nothing for someone meant to know you next year.

Setup sizes them at the very end, from the model's real context window and the SOUL that was
actually rendered, and writes them where Hermes reads them: typically 30,000 and 24,000 on a 131K
profile. `companion_memory.py caps --apply` re-derives them later.

```sh
kit/scripts/companion_memory.py --home <home> status
kit/scripts/companion_memory.py --home <home> archive --apply    # without --apply it is a dry run
```

Hermes refuses new memories once its files pass their cap, and says so only at that moment. `doctor`
reports the pressure as a percentage well before then. The archiver shares Hermes's `.md.lock`
sidecar, snapshots originals, and records a recoverable transaction before replacing either file. It
refuses conflicting external edits instead of overwriting them. Entries use the exact `\n§\n`
delimiter, and headings and blank lines can belong to one entry, so a single oversized entry is
never split automatically — it is reported for consolidation instead. `--keep-chars` sets the target.

**Absence from a live file is never proof something did not happen.** Look in the archive first.

---

## The context window

Automatic mode re-reads Hermes configuration and model metadata each turn, including the model
reported by the hook. An explicit `model.context_length` in Hermes remains authoritative — if you
previously pinned 65,536 tokens and want automatic discovery, remove that override from the
profile's `config.yaml` and restart its gateway.

The kit reads endpoint-specific context caches and Hermes's cached provider catalog; it never
assumes every host offers a model's maximum window. If metadata is unavailable, the reported
fallback is a conservative estimate and says so. Set `context_tokens` in setup answers for a fixed
kit budget; `context_mode: "auto"` resumes following Hermes.

This sizes the continuity excerpt, not the model's underlying capacity.

---

## What the hook carries each turn

The `pre_llm_call` hook rebuilds a compact continuity block on every turn. Before building it, a
deterministic pressure check archives complete older memory entries at 80% of their cap. The hook
waits at most **two seconds** on a contended lock, then skips maintenance for that turn and says so —
it runs inside the model call, and blocking the conversation to tidy a file is the wrong trade.

The block gets **3% of the configured context window** at roughly four characters per token, clamped
to 1,200–9,000 characters. These are budgeting estimates, not tokenizer measurements.

What it carries, in priority order: open loops, the handoff, standing instructions, facts about you,
the relationship history, today's episodes, the companion's own preferences, open questions, and
ambient senses. Plus, unbudgeted: the current time, the workflow rules, the computed age and any
birthday, and a note on which platform this conversation is on and whether it is the first turn.

**Small windows drop whole low-priority sections** rather than starving every section into
fragments, and always keep the lookup directions so the agent can read the rest on demand. **Nothing
is ever cut silently**: a partial view says it is partial and names the command that reads the whole
thing, and a section the window had no room for at all is named in the omissions line.

The handoff carries its own age — *"last refreshed 40 minutes ago"* — taken from the file's mtime,
which does not depend on the job that writes it having succeeded. Past six hours it is labelled
**STALE** and the agent is told to treat it as a past snapshot and prefer the episode ledger. If the
newest episode is more recent than the handoff, the ledger outranks it.

A state carried forward by the script advancer is labelled **UNCONFIRMED since HH:MM**, where the
time is the last state a model actually looked at.

Provenance stays separated throughout: the agent's imagined episodes are established fiction it may
tell in first person; facts about you require cited evidence. A routine is a suggestion, never proof
of attendance. **No search result can prove "never", a count, or a date.**

---

## Presence and wardrobe

Every pulse confirms a local snapshot: outfit, location, activity, mood, wants, private stance, care
events and a short account. This is internal state, not a status message to you. Snapshots live
inside the append-only episode ledger, so there is one authority across chats, pulses and midnight.
Sleep can continue unchanged across many ticks.

```sh
kit/scripts/companion_presence.py --home <home> show      # current state and closet, with last-worn times
```

The agent adds or updates clothes with `wardrobe --file` and records state with `update --file`.
Outfit, activity and location changes require a transition explanation — no teleporting. Updates
supply the ID of the state they read, so an older scheduled run cannot overwrite a newer chat
transition. `companion-life/PRESENCE.md` carries the JSON formats and the retry rules.

The same record carries **previously / now / next** for every companion. Code derives the
previous recorded activity and the current activity's start time; the model supplies an estimated
total duration and a tentative next activity. Continuing an activity preserves its start time.
An unobserved interval does not make a future plan into a completed event.

Timed commitments use stable IDs, timezone-aware start/end times and a preparation/travel buffer.
Updates merge commitments by ID; omission or an empty list cannot forget one. Completion,
cancellation and rescheduling require explicit updates with reasons. Chat and job context expose
upcoming preparation deadlines, overdue commitments and timing conflicts. A newly authored next
activity that cannot fit before an upcoming preparation window is rejected. The local structured
worker gets one correction attempt; a second failure leaves the saved state intact. This checks
time arithmetic, while the model still decides what a believable day looks like.

The `visual` fields describe pose, hands, gaze, framing, props, expression and lighting of the current
moment. They feed the recorded portrait route, including separate camera and lighting workflow
inputs. Next activities and commitments never enter the image scene. Visual directions carry
forward during an unchanged scene and clear on activity, location or outfit changes unless the
model supplies new ones. Timeline capture skips consecutive unchanged visible moments after a
successful image and rejects unconfirmed carried state. Explicit requested photos are unaffected.
The image model's ability to follow the supplied direction still affects the result.

Existing histories need no migration. `companion --home <home> repair` refreshes shared presence
guidance and adds the continuity instruction to existing pulse prompts while preserving their
custom text. New profiles receive it at setup. All state and capture records remain profile-scoped.

Setup's outfit selections seed a wardrobe rather than locking one outfit. The agent develops its own
clothes, workwear, exercise wear, sleepwear and occasion wear, and keeps laundry and condition
coherent with recorded events. Meals, showers, commuting and traffic can matter to a day without
becoming a repetitive checklist.

`private_stance` is one honest line about where she actually stands with you — what she is pleased
about, hurt by, or waiting on. It exists so a feeling carries across a gap between conversations
instead of resetting. It is hers; it shapes how she answers and is never a line to deliver.

---

## Images

The image timeline is **off by default**. Switch it on at setup, in the app, or with
`timeline on`. It uses Hermes's configured `image_generate` provider and can request up to
**96 images a day**. The kit does not install or switch providers.

```sh
./companion --home <home> timeline on|off|status|prune
```

Opt-in adds two jobs: capture at :02, :17, :32, :47 (after each pulse), and model-free cleanup at
:07, :22, :37, :52. A capture needs a confirmed scene from that interval — missing state, duplicate
attempts, unavailable tools and provider failures leave a gap rather than a fabricated success. Each
saved image carries its exact scene and timestamp even if another transition happens while the
provider is generating. Stalled captures expire after 15 minutes. Timeline images are never
automatically messaged to you.

### Retention is a storage budget

Images are the only thing here that can actually fill a disk, and a calendar is the wrong unit for a
decision about how much disk a companion may have. The default budget is **2 GB**; over it, the
oldest captures go. Setting the budget to 0 falls back to a 30-day calendar so the folder is still
bounded by something.

**Albums are never pruned.** Keeping an image *copies* it into `albums/<name>/` with a caption of
the moment it came from, so the day it belonged to still reads correctly in the timeline. You can
add your own pictures to albums too.

### Consistency

`companion_portrait.py prompt` compiles the prompt the timeline job uses: the locked appearance
description in a fixed order, then the scene from the recorded state, then the style. Consistent
character generation does not come from a seed — it comes from describing the same person the same
way every time, which is why the job is told to use the compiled wording verbatim rather than
rephrasing it.

If there is no recorded state it refuses rather than writing a prompt. A scene invented for the
camera is exactly what this pipeline exists to prevent.

A reference portrait, once stored with `companion_portrait.py reference --source <file>`, is passed
to providers that accept an input image. PNG, JPEG and WebP are all kept under
`<agent-data>/soul/reference-portrait.<ext>`, and storing a new one replaces the old: there is
exactly one canonical face.

### Reading a face out of a photograph

The words and the picture have to describe the same person, or the reference fights the prompt. So a
stored likeness can be read back into the locked `appearance` section:

```sh
companion_vision.py describe                 # propose, and print it
companion_vision.py describe --image path.jpg --model some/vision-model
```

This is the only module in the kit that calls a model. It runs
`hermes chat --image … --ignore-rules`, so the companion's own SOUL and memory are not injected —
the request is *look at this picture*, not *be somebody looking at a picture of herself*. The model
returns the same fields the setup interview asks for, and `physical_paragraph` assembles them in the
same fixed order, so a description that arrived from a photograph is shaped exactly like a typed
one.

**It proposes; it does not write.** Age is never taken from the model — it is computed from the
birthdate. The write goes through `companion_identity.replace`, which backs up the SOUL and proves
no other section moved. In the app this is the Identity tab: upload a photo, press *Describe this
face*, read what comes back, edit anything wrong, and keep it. `--apply` on the command line skips
the reading step, which is the only reason not to use it.

The app routes are `GET/POST/DELETE /api/portrait` (the likeness itself, uploaded as raw image bytes
in the request body), `GET /media/portrait`, and `POST /api/portrait/describe`. The last is the only
request the app makes that costs money.

### Photos you ask for

A request the recorded state cannot support — a beach at 2am, an event that is not happening, a
season that is not the current one, clothing she does not own — is declined in character, with what
is actually true offered instead: *"I'm in bed; you can have a sleepy one, or this one from
Tuesday."* Getting up, moving rooms or changing into something already in the closet is possible:
the transition is recorded first, then the photo shows where she now is. A saved timeline image may
be sent as what it is, never relabelled as now.

This is written into `SOUL.md` as a trait, so the refusal sounds like the companion rather than a
filter, and into `PRESENCE.md` as the rules.

---

## Voice

Voice notes go through the outbox like everything else, with the words kept beside the audio so a
note still says something if the audio does not play.

Hermes 0.21.1 exposes text-to-speech as an *agent tool* rather than a CLI command, so the agent
synthesizes the audio itself with `text_to_speech` and hands the file to the kit:

```sh
kit/scripts/companion_voice.py --home <home> status
kit/scripts/companion_voice.py --home <home> say --text-file <words> --audio <file it returned>
```

Whatever TTS provider Hermes is configured with is what the companion sounds like. The kit does not
choose one.

**Voice cloning** writes Hermes's own `tts.neutts.ref_audio` and `ref_text` keys and stores the
recording in the vault. It requires `--i-have-permission` and a transcript of exactly what is said —
not because a flag stops anyone, but because a cloned voice is somebody's actual voice and it should
be a decision made on purpose.

---

## Several companions at once

Each named profile gets its own Hermes home, job store, identity and ledgers. Identical job names
across profiles are expected. Profiles must not share a profile home or a messaging bot token.

Pick one gateway owner per profile:

- **Shared** — the root gateway sets `gateway.multiplex_profiles`, includes the profiles in any
  allowlist, and serves each one's separately configured bot. Do not also start dedicated gateways
  for those profiles.
- **Dedicated** — each gateway targets its own profile home and bot token. Disable root multiplexing
  or exclude those profiles from its allowlist, and give service instances distinct names.

Setup explains both and updates the root allowlist without removing other profiles; the root config
is backed up first. Switching an unrestricted multiplexer to dedicated converts current profiles
into an explicit allowlist, so future profiles must be enrolled deliberately.

```sh
./companion --home <profile> gateway                       # interactive
./companion --home <profile> gateway --mode dedicated
./companion --home <profile> gateway --action preflight    # read-only checks
./companion --home <profile> gateway --action status
./companion --home <profile> gateway --action restart
./companion --home <profile> gateway --action install --root-restarted
```

`gateway --action setup` opens Hermes's own platform/bot setup against that exact profile home —
enter credentials there, never in `--answers`. Use a different bot per profile.

If routing changed, restart the existing root gateway through its own service manager **first**,
then pass `--root-restarted` to acknowledge it. This stops a dedicated profile starting while the
root gateway still serves it. Existing Linux service definitions or gateway PID records block
installing a replacement — a PID record may be stale, so check native status rather than deleting it
blindly.

With systemd directly: `systemctl --user restart hermes-gateway-PROFILE.service` for a user unit, or
`sudo systemctl restart hermes-gateway.service` for the root profile's system unit. Running a
user-installed `hermes` under sudo can lose the executable path or pick a different home.

### Sharing what they know

`people/<you>/` moves to the vault root when sharing is on, so every agent reads the same facts and
standing instructions about you. Each agent's own life — its state, episodes, relationship ledger,
missions — stays private to it regardless.

---

## Terminals and Windows

The interface adapts to terminal width, honors `NO_COLOR`, and supports arrow keys, Space to select
and mouse clicks. Legacy Windows consoles default to ASCII borders and labels; Windows Terminal
keeps Unicode.

| Variable | Effect |
| --- | --- |
| `COMPANION_ASCII=1` / `=0` | Force ASCII, or request Unicode |
| `COMPANION_PLAIN=1` | Numbered prompts with `n`/`p` paging, for terminals without interactive control |
| `NO_COLOR` | Suppress escape sequences |
| `HERMES_HOME` | Which Hermes home to use, unless `--home` overrides it |

These change presentation only; saved identities retain their exact Unicode text. Failed VT
activation disables ANSI colors and clearing.

Hermes's agent terminal uses Git Bash on Windows, so generated agent commands use POSIX quoting
while hook registration uses native quoting. See the
[Hermes Windows guide](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native).

---

## Moving to another machine

Back up both the Hermes home and the vault, including secrets through your own process. Then:

1. Install Hermes and this kit.
2. Restore both with the scheduler stopped.
3. Update moved paths in `companion.json`.
4. Recreate the `SOUL.md` symlink.
5. Run `repair`.
6. Review installed job prompts for old paths and interpreters.
7. Approve the regenerated hook in an interactive chat, or non-interactively with
   `hermes -p <profile> chat -q 'hello' --oneshot --accept-hooks`.
8. Run `companion doctor` and `hermes doctor` before starting the gateway.

The kit does not yet automate migration.

### One canonical identity

Where symlinks work, the real `SOUL.md` lives at `<agent-data>/soul/SOUL.md` and the Hermes home
links to it, so identity is covered by the same backups and git history as everything else. Existing
content is backed up before moving, and a conflicting vault identity stops adoption for review.

If symlink creation fails — including Windows without the privilege — SOUL stays in the Hermes home
and `soul_in_vault` is recorded as false. There is never a second writable copy pretending to be
canonical. **Back up both the Hermes home and the vault.**
