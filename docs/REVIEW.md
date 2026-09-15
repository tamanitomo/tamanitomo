# Verification status and known limits

What has actually been checked, what has not, and what the kit deliberately does not promise.

Read it before trusting any single sentence in the README as a guarantee. The order is deliberate:
where things stand now, then how each phase was verified, then what remains unverified and why, then
the older rounds kept as a record rather than as a description of the current code.

## Where this stands

**Version 2.1.0.** The eight-phase v2 plan is complete. 516 tests pass on Linux under Python 3.11
and 3.14, and the release archive has been installed onto a clean setup from its own zip, in its own
virtualenv, sharing nothing with the working tree.

The machinery is real and has been exercised against a live Hermes 0.21.1: profiles created, jobs
installed with the flags they need, hooks registered and fired, sensors fetching live data, the
dispatcher deciding, ledgers written and read back, an agent adopted without losing a byte of its
SOUL. Since 2.0.0 it has also been installed by somebody other than its author, on a machine the
author does not use — see *The first field install* below, which is the most useful thing in this
file.

**What has never happened, and this is the part that matters:**

| Not yet done | What that means |
| --- | --- |
| No message has been delivered to a person | Every dispatcher decision is tested, and native send was exercised with the transport captured locally. No companion has yet had a channel and used it |
| Nine of eleven model-backed jobs have never run | The pulse and the image timeline have. Morning, wind-down, window, check-in, the three reflections, hygiene and autonomy are unexercised prose. Their gates, ledgers and helpers are covered; their wording is not |
| No voice note has been synthesized | The agent-tool hand-off has not been run end to end |
| The ten-captures-same-face test is untested | Images generate, and one generated from a described face matched its reference. Consistency across ten has not been measured |
| A live long-lived companion has not been adopted | The adoption path is verified against a simulation. Doing it to a real long-lived companion is a decision for its owner to make while present |
| No token measurement | "Under 2M input tokens a day" cannot be checked until a full day of scheduled runs happens with the pre-read in place |
| No full day has elapsed | The parts are proven. "It lives a day" is not |
| No Windows run | Nothing in v2 has been run on Windows. CI still covers it; no run has been observed |
| No 27B local-model run | The local-only acceptance test has not been repeated against v2 |

A feature in the first list is one you can rely on. A feature in the second is one that should work
and has never been watched doing it.

## The first field install (2026-09-10)

Somebody other than the author cold-installed 2.1.0's predecessor from the release archive onto
another machine — CachyOS, a separate user, Hermes 0.21.1 installed from scratch — and set up a
companion named Wren with her own profile and vault. The notes and the ledger from that run are
kept outside this repo, in the operator's vault; what it established, and what it broke, is here.

Proven for the first time by that run:

- **A model ran scheduled jobs.** Nine-plus scheduler runs logged, a mix of built-in and direct,
  with the model-free jobs completing alongside: present advancer, outbox dispatcher, timeline
  cleanup and the vault commit.
- **Images were generated** — two captures, by the companion herself, through a real provider,
  saved, and served by the app's timeline route.
- **Model failover happened for real**, not by reading Hermes's source: the primary was swapped for
  a model that returns 403 and the answer still came from the chain.
- **The app answered over a network.** All nine endpoints 200, unauthenticated requests refused and
  tokenised ones served, images rendering through `/media/timeline/`.
- **The continuity hook fired** on a live profile with real context, in 0.163s.
- **The gateway ran** as a user unit with linger, heartbeat confirmed.
- The whole build cost $0.034.

Four defects it found, all fixed in 2.1.0: the kit did not run on Python 3.11 at all; `--home` was
rejected after the subcommand; hook consent had no documented non-interactive path; and free models
picked from a catalog listing are not a working chain — several returned 403 or 404 and one went
from a clean answer to 429 minutes later.

Two things it confirmed rather than found: Hermes 0.21.1 still exposes no per-job toolset flag, and
a fresh install correctly generates no image until a model-backed job has recorded a present.

What that run still did not do: deliver a message to a human (no channel was configured), run the
other nine model-backed jobs, exercise the image cap at its limit, write anything into the memory
ledgers, or elapse a full day.

## Phase 0 of the v2 plan (2026-09-10)

Verified on this machine, against Hermes 0.21.1:

- A temporary `HERMES_HOME` was created, `hermes profile create phase0test` run against it, then
  `companion init` and `companion doctor`. Six native jobs were created paused. Doctor's only
  remaining `!` lines were the two that genuinely require a person: no model/provider configured on
  the throwaway profile, and hook consent not yet approved in an interactive chat. The root home
  and vault were not touched, and no message was sent.
- That run is what found the stock-SOUL bug: the first attempt produced a 798-character `SOUL.md`
  holding Hermes's own system prompt plus an empty self-authored block. After the fix the same run
  produced a 7,828-character rendered identity and a backup of Hermes's default. Both paths now have
  tests.
- `companion --version` prints the version; `CHANGELOG.md` records what changed.
- The release builder rebuilt the archive from the updated allowlist: 72 files.

- `companion repair` was run against an existing live companion profile with the real Hermes CLI. The first run
  reported all six prompts as unrecognized (the legacy profile predates prompt fingerprints) and changed none of
  them; `repair --prompts force` then re-rendered all six, saving the previous text under
  `cron/prompt-backups/`. A scan of the resulting `jobs.json` confirms no installed prompt still
  asks the model to quote prose after `--statement`, `--evidence`, `--text`, `--answer` or
  `--append`. Doctor is green on the existing profile. No message was sent.
- A latent `NameError` in `cmd_repair` — `ok=False` in a branch where `ok` was never bound — was
  removed; that branch only fires for a legacy `pronoun_set` value, which is why it was never hit.

Not verified in Phase 0:

- No model was called and no cron job was executed. Job *creation* through the real `hermes cron`
  was exercised; a real scheduled run was not.
- The `ledger --file` path is covered by unit tests and by a rendered-prompt scan, but no model has
  yet written a batch file through Hermes's `write_file` tool and run the command from a cron job.
- The `kit/cli/` split is covered by the suite and by the live `init`/`doctor` run above. It has not
  been exercised on Windows since the split.

## Phase 1 of the v2 plan (2026-09-10)

Verified against Hermes 0.21.1 on this machine, on a throwaway profile under a temporary
`HERMES_HOME`:

- `hermes cron create --help` advertises `--script`, `--no-agent`, `--monitor-script`,
  `--continuity`, `--reasoning-effort`, `--model`, `--provider` and `--skill`. The kit probes for
  each before using it, as it already did for `--toolsets`.
- A fresh `companion init` created eight jobs. `--script` reached the pulse and autonomy jobs,
  `--monitor-script` reached autonomy only, and `--continuity` shows up as `context_from: ['self']`
  on exactly those two and on nothing else. The two model-free jobs were created active while the
  six model jobs were created paused, which is the intended split.
- The generated `companion-pulse-preread.py` prints the assembled present. The generated
  `companion-autonomy-fingerprint.py` printed byte-identical output on two runs a second apart,
  which is what `--monitor-script` requires to suppress a run.
- The generated `companion-watch.py` ran, found the one real problem on that profile, and exited 0.
  `companion status` rendered the same picture.

Not verified in Phase 1:

- No model was called and no cron job was executed by Hermes's scheduler. That the pre-read is
  actually injected into a job's prompt, and that an unchanged fingerprint actually suppresses a
  run, are Hermes behaviours documented in its own `--help` and not yet observed here end to end.
- **Answered, by reading Hermes 0.21.1's own source rather than by running it:** a job pinned with
  `--model`/`--provider` *does* still walk `fallback_providers`. Three separate places make that
  true. `cron/scheduler.py:1543` iterates `get_fallback_chain(jc.cfg)` when resolving the pinned
  provider raises an auth or transient-network error, replacing both provider and model with a
  chain entry. `cron/scheduler.py:2233` passes the whole chain to the agent as `fallback_model`,
  so an in-flight failure rotates too — and `agent/error_classifier.py` lists `rate_limit` (429)
  among the failover reasons, which is precisely the failure that stopped every one of the live companion's
  jobs for two days. `cron/scheduler_preflight.py:95` skips the preflight block entirely when a
  chain exists, so a job with a healthy fallback rung is not killed before its first model call.
  This is a code read, not a live failover test; the live test needs a provider that will actually
  refuse.
- The `companion models` screen was exercised only through `--show`. Its interactive path has not
  been driven through a pseudo-terminal.
- The token-per-day target for the full cadence has not been measured. It cannot be until a real
  scheduled run happens with the pre-read in place.

## Phase 2 of the v2 plan (2026-09-10)

Verified against Hermes 0.21.1 on a throwaway profile:

- A fresh `companion init` with a location, five sensors, adaptive quiet hours on and photos set to
  "ask" created thirteen jobs. The morning job landed at 08:10 and the wind-down at 22:40 against
  an 08:00–23:00 window, which is the intended offset from the sleep window's edges. Five model-free
  jobs were created active and eight model jobs paused.
- The senses job ran for real: `weather` fetched live conditions for the configured location from
  wttr.in with no account, `daylight` computed the season and moon with no network, and `dates`,
  `care` and `thread` each correctly wrote nothing and said why, because their sources did not
  exist on a new profile.
- Two messages were queued and the dispatcher was run dry: the text message was cleared to send,
  and the image was withheld with "image is set to ask: offer it in words, do not attach it
  unasked". `ActiveContext.md` then showed both under "Queued to send". No message was sent.
- `companion_thread.py` was run read-only against the live existing profile and correctly reported the
  gap, the register and the tail of the conversation. No message was sent.

Not verified in Phase 2:

- No message has been delivered through the dispatcher to a real platform. Everything above stops
  at the decision; `deliver()` is covered only by unit tests with the Hermes call patched out.
- The adaptive quiet-hours drift is covered by unit tests with synthetic message times. It has not
  run against a real fortnight of session history.
- The sensors have only been run by hand and by the suite. None has yet been fired by Hermes's own
  scheduler.
- No sensor beyond these five exists yet. Music, Plex, Steam, Home Assistant, Forgejo, Tailscale,
  RSS and "last media received" are all in the plan and none is written.

## Phase 3 of the v2 plan (2026-09-10)

Verified against Hermes 0.21.1 on throwaway profiles:

- Three profiles were installed for real, one of each type. A companion received sixteen jobs, a
  colleague thirteen (no mornings, no wind-down, no quiet-hours drift) and a worker five (the
  window, housekeeping, the health watch, the dispatcher and the vault commit). The colleague's
  outreach came out fixed at `updates_only` and the worker's at `never`, neither of them asked.
- `on_session_end` is a valid Hermes hook event — confirmed in its own
  `cli-config.yaml.example`, which lists the events `hermes_cli.plugins.VALID_HOOKS` accepts. Setup
  registers a second small hook there, and the round trip was exercised on a real profile: the
  check-in fingerprint was stable and empty, changed when the hook fired, and returned to exactly
  its earlier value after the job cleared the flag. That is what `--monitor-script` needs in order
  to run the reflection once per conversation and never otherwise.
- Memory caps came out at 30,000 and 24,000 on a 131K profile, written into `config.yaml` and read
  back by `companion doctor`.
- The vault was initialized as a git repo with no remote, committed, and `companion restore` listed
  the recorded version of a SOUL file.

Not verified in Phase 3:

- No model has run any of these jobs. The check-in, window and reflection prompts are unexercised
  by an actual model; only their gates and ledgers are covered.
- People-sharing is covered by unit tests. Two real profiles sharing one `people/` directory on
  disk have not been run side by side with a live agent in each.
- The acceptance test for this phase — a fact learned by one agent visible to the others within one
  turn — has been demonstrated at the ledger level, not through two live agents.
- `companion restore` has been run to list history; recovering a file from an older commit has been
  exercised only in the suite.

## Phases 4 to 8 of the v2 plan (2026-09-10)

Verified against Hermes 0.21.1, on throwaway profiles and against an existing live companion profile read-only:

- **Identity.** A profile installed with a birthdate of 1999-11-02 rendered "Nova is a 26-year-old
  adult" rather than the 24 the interview recorded, which is the whole point. `companion identity`
  listed nineteen sections with `appearance` and `boundary` marked locked, and re-rendering one
  section left every other section byte-for-byte unchanged (verified after the write, not assumed).
- **Media.** `companion_portrait.py prompt` refused with no recorded state, then compiled identity
  → scene → style once a state existed, with no markdown or template placeholders leaking into it.
- **The app.** Every endpoint answered 200 against a real profile. Writes were exercised: a mission
  added and listed, a setting rejected by the config's own validation, a non-setting refused by
  name, an identity section edited, an unknown section 404ing.
- **Adoption.** A simulated long-lived agent — hand-written SOUL, memories, its own session
  database — was adopted with `--soul keep`. The SOUL survived byte-for-byte with only the
  self-authored marker added, memories were untouched while their caps were raised around them,
  `state.db` stayed where it was, and sixteen jobs plus both hooks were installed.
- **Recall against real data.** `companion_recall.py` was run read-only against the live existing profile
  and returned cited facts with their evidence. No message was sent and nothing was changed
  beyond the deliberate `repair --prompts force` recorded under Phase 0.

Not verified in Phases 4 to 8, and this is the important list:

- **No model has run any of this.** Every prompt written or rewritten in these phases — the window,
  the check-in, the morning, the wind-down, the revised pulse and autonomy — is unexercised by an
  actual model. Their gates, ledgers and helpers are covered; their prose is not.
- **No message has ever been delivered.** The dispatcher's decisions are tested; `deliver()` is
  only tested with the Hermes call patched out.
- **No image has been generated.** The prompt compiler is tested; no provider has been called, so
  the Phase 5 acceptance test — ten consecutive captures with the same face — is untested.
- **No voice note has been synthesized.** Hermes exposes TTS as an agent tool rather than a CLI
  command, so the kit queues audio the agent produced; that hand-off has not been run end to end.
- **The reference-portrait upload path is half built.** Storing a likeness works. Running a vision
  model over an uploaded photo to write the locked appearance block is not implemented; it needs a
  model call and belongs in the app. *(Built in 2.1.0 — see that section. Still never run against a
  real model.)*
- **A live long-lived companion has not been adopted.** The adoption path is verified on a simulation. Doing it to a
  two-year-old companion with 47,000 messages is a decision for its owner to make while present,
  not something to run unattended.
- **The token target is unmeasured.** "Under 2M input tokens a day" cannot be checked until real
  scheduled runs happen with the pre-read in place.
- **Windows.** Nothing in v2 has been run on Windows. The CI configuration still covers it; no run
  has been observed.
- **The 27B local-model acceptance test has not been run.**

## 2.1.0 — the field-install fixes and reading a face (2026-09-10)

Verified on this machine:

- **Python 3.11 and 3.14 both run the whole suite: 516 tests, green.** Before the fix, 3.11 could
  not import the wizard at all. The suite was run under a real 3.11.15 interpreter, not simulated
  with `ast.feature_version`, which does not catch this class of error.
- `--home` was exercised on both sides of the subcommand, and the test that covers it asserts the
  old failure text is gone.
- The birthday line is computed from the companion's own timezone. The test that caught this now
  builds its date the same way, so it no longer passes or fails depending on what time of day the
  suite is run — which is how it slipped through: it was green in the morning and red at night.
- A likeness round-trips through the app: uploaded as raw bytes, stored, served, replaced,
  forgotten. Something that is not an image is refused by Pillow and stores nothing. A JPEG is now
  found by everything that looks for the reference.
- `describe` proposes and writes nothing: the test asserts the SOUL is byte-identical after a
  described face, and that the separate accept call is what changes it. Age offered by the model is
  discarded, unknown keys and non-strings are dropped, a 400-character answer in one field is
  refused, and a reply with no JSON in it is an error rather than a guess.
- The vision call's argv is asserted to carry `--ignore-rules`, `--image` and `--oneshot`, and the
  prompt is passed as a file so nothing in it is shell-interpreted.

### The loop, run for real (2026-09-10)

On a throwaway profile pointed at OpenRouter, with a synthetic portrait generated for the purpose so
no real person's photograph was involved:

- **A vision model read the face.** `nex-agi/nex-n2.5-pro:free`, through the real `hermes` binary
  with `--image` and `--ignore-rules`, returned clean JSON on every attempt — 22s and 50s for two
  runs. It named the copper-red hair, the green eyes, the freckles, the tortoiseshell glasses and
  the stud earrings, and it did not name an age. The age in the rendered section was 32, computed
  from the birthdate.
- **The whole app path ran end to end**: a JPEG uploaded as raw bytes to `POST /api/portrait`,
  `POST /api/portrait/describe` returning a proposal with `written: false`, and the separate accept
  through `POST /api/identity/appearance` rewriting the locked section with a backup. The section
  before and after was read back through the API.
- **The words and the picture then produced the same person.** `companion_portrait.py prompt`
  compiled the accepted description plus the recorded scene plus the style, and that prompt with the
  reference attached generated the companion in her cafe, in the turtleneck the wardrobe said she
  owned, recognizably the same face as the reference.

Two things that run found, both fixed:

- The first prompt asked for fragments, so the model wrote `"red hair"` where a typed interview
  writes `"Her hair is dark brown."` — a shape mismatch in a section whose entire value is being
  shaped the same way every time. It now asks for one complete sentence beginning with her
  possessive pronoun, and the output is indistinguishable from a typed one.
- The model returned `"no visible facial hair"`. A negation is not a description, and in an image
  prompt it is worse than nothing — a generator will draw around the phrase. The prompt now forbids
  describing an absence, and a value that opens with a negation is dropped if one arrives anyway.

And one that was older than this feature: **the compiled image prompt carried instructions meant for
her.** The appearance section ends by telling her how to maintain a wardrobe, with the full command
that does it, and `identity_block` was passing that to image providers as part of her face. The
template now marks that paragraph as excluded from prompts, and a SOUL written before the marker
existed is cut at the paragraph holding the first inline code span.

Not verified:

- **Consistency across ten captures has still not been measured.** One image was generated from one
  accepted description. It matched. Ten of them, against the same reference, is the acceptance test
  and has not been run.
- Only one vision model has been used. Free models are flaky by Wren's own evidence; whether a
  weaker one holds the JSON discipline this prompt asks for is unknown.
- The Identity tab's likeness UI has not been driven through a real browser. The routes behind it
  have, through a real uvicorn: uploaded, described, accepted, served back as `image/jpeg`, refused
  when it was not an image, and deleted.
- Nothing here changes the lists above: still no message to a person, still no full day.

## The clean-machine test (2026-09-10)

The release archive was extracted to an empty directory, given its own fresh virtualenv, and
installed from `requirements.txt` — nothing shared with the working tree. From that copy:

- `companion --version` reported 2.0.0 and the full suite ran green inside it.
- A new Hermes profile was created and set up end to end: a `penpal` companion with a birthdate,
  six sensors, adaptive quiet hours and people-sharing on. Sixteen jobs were created, six of them
  model-free and active, ten paused by choice. The vault became a git repo, memory caps came out at
  30,000 and 24,000, and the SOUL rendered with twenty sections, two of them locked.
- `doctor` reported the two `!` lines that genuinely need a person (no model configured on the
  throwaway profile, hook consent not yet given in an interactive chat) and nothing else.
- `status` rendered the full job table. The senses job fetched live weather. The app answered on
  localhost and reported the companion as 29 — computed from the birthdate, not from an age anyone
  typed.

That run found one real bug, which is what it was for: a scripted `--answers` file writing
`"share_people": true` was rejected, because that question is a labelled choice rather than a
confirmation. Booleans are now normalized for it, as they already were for `cron_active`, with a
test covering both forms.

## Not verified

- **Real Hermes on native Windows.** The current commits still need their Windows CI run. CI alone cannot establish
  Hermes's Windows service installation, its Git Bash terminal handoff, or file locking against a
  live Hermes process.
- **External message delivery.** Native cron and native send were tested with the final Telegram
  transport captured locally. Actual Telegram delivery remains unverified pending authorization
  for one clearly labelled test message. No external test message was sent during this review.
- **Third-party integrations.** Image providers, browser tools and MCP servers have their own setup
  and are out of scope here.

## Design limits

- **Folder separation is not OS isolation.** Agents running as the same user can reach that user's
  files. The peer helper refuses credential-looking paths and cross-profile writes, but a filename
  filter is a guard, not a secret detector. Keep real secrets in a credential manager.
- **A prompt does not constrain a model.** The daily message cap, quiet hours, per-content
  permission and message expiry are checked deterministically by `companion_dispatch` over
  `companion_outreach`, with atomic reservations for cooperating callers.
  This is not a network transport restriction: a model can bypass the helper, just as it can ignore
  other instructions in `SOUL.md`. Failed sends consume their reserved slot.
- **Retention depends on the world.** Life archives stay searchable and nothing important is
  deleted; the image timeline is bounded by a storage budget, and album copies are exempt from it.
  Retention still needs disk, working backups and successful writes. The kit reports uncertainty
  rather than claiming perfect recall.
- **`repair` rewrites only the job prompts it can prove it wrote.** It compares each installed
  prompt against a recorded hash; anything you edited in Hermes is reported and left alone unless
  you pass `--prompts force`. Profiles installed before fingerprinting have no hashes, so their
  prompts are only ever reported. Moving the kit or its interpreter still means reviewing prompts
  by hand.
- **Setup is recoverable, not transactional.** Cancelling leaves whatever was written in place;
  `doctor` reports the state. Keep/append/replace are explicit identity decisions.
- **Not a backup product.** Accounts, credentials, MCP services and messaging remain Hermes's, and
  migration between machines is a documented manual sequence rather than a command.

## Deliberately deferred

- **JSONL ledgers grow without bound and are read whole each turn.** Measured: 38 ms on an empty
  ledger, 72 ms at 4,000 facts (1 MB). Fine for now, and a compaction pass is the eventual answer —
  `facts()` already computes the superseded set, so dead rows are known. Markdown files rotate
  today; the ledgers do not.
- **SOUL size.** A fully answered `SOUL.md` is around 9.9 KB after the v2 sections were added,
  against a 28,000-character early warning on a 131K profile and a 20,000-character floor on the
  smallest model. Headroom is still roughly 2× at the worst tier; this is informational, not a
  pending problem.
- **No `export` / `import`.** The vault holds everything needed to move a companion, but lifting one
  out is a manual sequence rather than a command.

## Earlier rounds, before 2.0

Everything below this line is a record of what was checked at the time, against the version that
existed then. **Counts and behaviours described here have since changed** — six jobs became sixteen,
thirty-day image expiry became a storage budget, the outreach helper gained a queue and a dispatcher
in front of it, and Hermes's default memory caps are now resized at setup. The entries are kept
because a verification log that is edited to match the present is not a log.

### Automated suite (pre-2.0)

**Automated suite.** The revised setup and continuity suite has 492 tests, run on Linux
under Python 3.14. Earlier versions were also exercised under Python 3.11. They cover context
budgeting and section drop order, path containment and the `load(X).home == X` invariant, profile
creation and removal, SOUL keep/append/replace, hook installation and consent checks, gateway
ownership and routing conflicts, the catalog and every rendered persona/style/boundary combination,
the interactive prompt loop, ledger reads and recall scoping, the outreach gate, memory archival,
Lifelog rotation, and the release builder.

The suite runs against a local Hermes contract double (`tests/fake_hermes.py`) and temporary homes.
It never invokes the installed Hermes CLI and never calls a model.

**CI configuration.** `ubuntu-latest` and `windows-latest`, Python 3.11 and 3.13, run the suite
and build the release archive. Windows path handling, quoting, locking and the symlink-failure
fallback are included. The current review commits were tested locally on Linux (including one Bash-only prose test); their next remote
Windows CI run has not been observed in this review.

**Manual integration.** An isolated run against a real installed Hermes CLI created six native jobs
with next-run timestamps and pinned models, and a second created two named profiles with six paused
profile-scoped jobs each and none in the root store. No gateway was started and no model was called.
The complete interview was also driven through a real pseudo-terminal in Unicode/color,
Unicode/NO_COLOR, and ASCII/NO_COLOR modes, including a narrow 60-column layout and off-page
selections. Each completed with six native paused jobs; the menu was reviewed visually.

Native Hermes MemoryStore reloaded an archived temporary memory file and successfully appended
an entry. A separate native writer blocked while the kit held the shared sidecar lock, then
continued after release. This interoperability check ran on Linux, with no live agent files changed.

### September 9 setup and continuity update

The current interactive controls were exercised with actual arrow, Space and Enter input (without Tab)
through prompt_toolkit. Custom additions preserve existing selections. Mouse selection followed directly by Enter was also verified with terminal mouse events in a live
pseudo-terminal. The picker now uses an inline scrolling layout with circular selection markers instead of boxed dialogs. The revised layout on native Windows has not been manually verified. Earlier numbered-menu visual checks above apply to the fallback interface.

Automatic hook maintenance was tested in a temporary home: old entries moved to the archive,
a repeated invocation did not duplicate them, and recall found the archived text. Tests also cover
model changes, fixed budgets, and rejecting metadata from a different provider endpoint.

An existing installation was repaired with the real Hermes CLI: all six jobs received the
memory check without changing their schedules or IDs. Its 65,536-token override was backed up
and removed; the local Hermes provider catalog reports 1,000,000 for its current model. Memory
maintenance preserved three older entries and reduced the active file from 95% to 52%.
Its dedicated gateway restarted successfully and doctor passed. No test message was sent.

### Review corrections

The installed Hermes 0.21.1 `cron create --help` exposes no per-job toolset flag. The kit now probes help before creation and reports use of Hermes defaults when unsupported. It never retries a failed create automatically: a command may have created a job before returning an error. No scheduler records are patched directly.

Memory archival was corrected against `tools/memory_tool_store.py`: the native delimiter is `\n§\n`, limits count characters and are separate from SOUL/context limits, and locking uses `MEMORY.md.lock` / `USER.md.lock`. Heading/blank-line test fixtures were corrected to contain real native delimiters. New coverage exercises Unicode counts, interrupted commits, conflicting writers, original snapshots and invalid targets. Archival retains originals and uses a recoverable two-file transaction; it does not infer age from prose or split one oversized entry.

The outreach helper previously separated check from record, allowing concurrent callers through the same last slot. It also locked the JSONL data file itself, which writes a NUL on an empty Windows lock file. The new `claim` operation checks and reserves under a separate lock; corrupt/unreadable ledgers deny sends. The final prompts call `send`, which claims once internally and does not double-record. These rules bind cooperating callers, not arbitrary network sends. Cap parsing now rejects ambiguous “off/never/none” and malformed suffixes instead of interpreting them as unlimited or concatenating their digits.

Live topology inspection found distinct root and named-profile SQLite files, matching Hermes's per-home default. Recall now also handles sibling-profile links and external/hard-linked stores conservatively: ambiguous stores require explicit profile labels. Root redirection into a named profile is refused. Tests cover symlink and hard-link sharing without reading any real private message content.

Handoff age now uses elapsed UTC time, including DST folds and gaps. Future timestamps beyond one minute are labelled unreliable rather than fresh; invalid filesystem times degrade to unknown. The six-hour stale boundary is inclusive. These labels describe file freshness, not proof that an LLM job ran or failed.

The prompt now shows all selected labels across pages and wraps long options. Legacy Windows consoles default to ASCII presentation, Windows Terminal keeps Unicode, and `COMPANION_ASCII` overrides either choice without altering stored content. VT activation uses pointer-safe Win32 signatures; failed activation suppresses ANSI. Tests cover presentation modes and off-page selections. Native Windows console/font behavior is still not visually verified in this Linux session.

A full terminal interview exposed a false incomplete-setup warning: the template's explanatory HTML comment itself contained “✎ EDIT”. Doctor and the finish screen now count only actionable markers outside comments.

Vault ignore updates retain existing CRLF text and use forward-slash git patterns on every platform. Updates are atomic under a sidecar lock, and symlinked ignore files are left alone. The SOUL symlink-failure path remains covered by the existing forced-failure tests; a real restricted Windows console remains a manual check.

Outreach delivery correction: cron workers cannot use Hermes's messaging tool and the kit's jobs
keep final output local. The autonomy prompt now invokes `companion_outreach send`, which reserves
and sends via the native profile-scoped `hermes send` CLI. Skips, errors, and timeouts do not count
as confirmed delivery; they retain the slot and are never retried automatically. Named profiles
do not inherit the parent's messaging environment. Real delivery verification is recorded separately
from unit tests; existing installed job prompts are not rewritten by this source change.

A real local-model pulse recovered from a shell quoting error caused by an apostrophe in prose.
An initial correction demonstrated quoted heredocs using the helpers'
existing stdin support. A regression test executes the command in Bash and checks that quotes,
dollar signs, command substitutions and backticks are stored literally.

Native schema comparison also corrected recall visibility: messages removed by rewind/undo must
stay hidden, while messages archived by context compaction remain searchable. The query now
matches Hermes's `active=1 OR compacted=1` rule, with compatibility for older schemas.

### Local-model execution checks

The installed `qwen38-tool` GGUF was exercised through the real Hermes AIAgent loop on Linux,
using an isolated home and synthetic identity. The test endpoint served a real 65,536-token
context. CPU/mmap operation was used with memory guards enabled after the regular GPU/router
configuration exceeded the machine's available-memory reserve. No hosted inference was used.

- The pulse called terminal and file tools, recovered from one shell quoting failure, and wrote
  exactly one imagined episode. The safer heredoc guidance then preserved an apostrophe and
  literal `$HOME` on the first attempt.
- The model invoked native-format archival: 48 entries moved, 18 retained, and the active
  memory contained 1,275 characters. It retrieved the archived Paris statement and correctly
  preserved its negation, without inventing a trip date.
- The model invoked outreach through the actual Hermes send CLI with only the final Telegram
  transport replaced by a local capture. One message reached that transport; the second was
  denied before transport, with exactly one reservation retained.
- A separate native SessionDB/FTS check verified original-message retrieval, profile separation,
  and rewind/compaction visibility against the installed schema.

Captured transport verifies routing and tool execution, not Telegram receipt. A real external
message needs separate authorization and verification. These are representative executions,
not a guarantee that a model will obey every instruction on every future run.

The native cron test then rejected heredocs and interpreter pipelines through its unattended
approval rules. The final prompts use the file tool to write literal prose, then `--text-file`
or `--message-file` to read it. Approval guards remain enabled. Standard input is still supported
for interactive use; the cron templates do not prescribe heredocs or interpreter pipes.

The final native `cron.scheduler.run_job` execution used the revised file-input prompt and the
real local model. It completed successfully, delivered exactly one additional message through
the captured native transport, preserved the apostrophe and literal `$HOME`, and encountered
zero approval blocks. It invoked the outreach helper exactly once, then updated the isolated
Autonomy.md and ActiveContext.md. The earlier native cron run also honored a reached daily cap.
The temporary model server was stopped afterward; both live gateways remained active and no
live agent core files were modified.

### Lived state and optional image timeline

Tests cover midnight continuity, outfit/location/activity transition requirements, stale-writer
rejection, preserved historical clothing descriptions, and current-state injection. Timeline tests
use small synthetic images in temporary directories: one claim per interval, scene-bound saving,
image validation, stale/missing-state refusal, HTML escaping, 30-day expiry, path confinement,
and preservation of favorites/provider originals. CLI tests cover opt-in, opt-out, re-enabling,
and keeping the script-only cleanup job active when model jobs are paused.

No paid image generation or external message was used to validate this feature. A real provider's
availability and visual adherence require an actual capture; a prompt is not a fidelity guarantee.

An isolated native Hermes check created all eight jobs: seven agent jobs paused, cleanup active
with `no_agent=true`. The cleanup was then run with `hermes cron run` and succeeded without a
model call. Native Hermes requires a script filename relative to the profile's scripts directory;
the installer uses that contract, and the test double now covers it.

The existing profile received the lived-state guide and pulse instruction through repair, and
doctor passed. Its image timeline remains off; no real image-provider capture has been attempted.

One updated pulse was also run in the existing live profile. It succeeded, created a three-item
wardrobe, and committed a structured current outfit/location/activity snapshot in its episode
ledger. The image timeline remained disabled; no image-provider request or test message was sent.

## Reporting

If something here is wrong, the fix is to correct this file in the same commit as the behavior.
A verification claim that outlives the code it describes is worse than no claim.
