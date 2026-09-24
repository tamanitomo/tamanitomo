# Phase 1B C1 results: core, closure and integration

## I. C1 integration for PHASE1B_REVIEW_R5 (read this first)

| | |
|---|---|
| Answers | `PHASE1B_REVIEW_R5.md`: R4 closed and the C1 core accepted; the remaining C1 integration was requested |
| Branch | `test/phase1b-c1-core`, unmerged. Earlier reviewed commits are preserved and not rewritten |
| Commits | `d7885b1` integration code and tests; `f76c14f` docs (`docs/CHAT_CONTRACT.md` §8, `PHASE1B_DESIGN.md` Appendix E); `38d6b79` a **test-only** fix: the cross-process tests' `spawn()` helper now closes subprocess pipes and reaps its helper processes (it had raised `ResourceWarning`). No production module changed in `38d6b79`. |
| **Tested code head** | **`38d6b79e0b6cef0b5c1ed3b2e0fb27b1044a478d`**. Every local result below ran there on a clean tree. This report and the evidence are committed after it. |
| Activated | **No.** The keyed routes exist only in an app built with `build(chat_sends=Options(...))`, and no entry point passes that option. No UI uses them. Nothing was added to `release-files.json`. `POST /api/chat`, `Runtime.chat()` and `hermes_stream.py` are unchanged, and there is no fallback between the two paths. The executor and quiescence modules are byte-identical to `1e161c3`. |
| Not done | C2 and C3; the optional adapter that would route the legacy `POST /api/chat` through the ledger. Nothing was merged, tagged, released or deployed, and no live profile, credential, model or platform message was touched. |

### I.1 Implemented and tested (synthetic, Linux, this host)

The brief's items, each with where it is tested. `tests/test_phase1b_c1_integration.py` drives the app over HTTP (TestClient) with the fake Hermes double. That double is **protocol evidence only**. `PinnedHttp` in `tests/test_phase1b_c1_pinned.py` runs the same app path against the pinned Hermes `0e9fc2cc15` and `tests/mock_provider.py`.

| Item | Implementation | Tests |
|---|---|---|
| 1. Routes | `kit/app/chat_send_routes.py`: bootstrap, keyed POST, receipt, `?key=`, `?open=1`, stop, reset (needs `{"confirm": "reset send ledger"}`). Scope is captured once, first. When this process's installation slot is taken, `accept(admit=False)` still replays and refuses new keys. The keyed routes are exempt from the middleware's busy refusal, so a retry can replay and a stop can reach a running turn. | `HttpLifecycle` (connected path and replay; POST before bootstrap; lost-response recovery by key; `key_conflict`, `generation_changed`, `key_expired`, wrong conversation, unauthorised session; resume authorised by the current binding; one active attempt with same-key replay while running; stop; open receipts; confirmed reset and the generation fence; reset refused while a turn runs). `PinnedHttp.test_http_fresh_turn_links_reads_and_replays` |
| 2. Operation ids and views | The operation id is reserved at acceptance and used through `Operations.submit(ident=, claimed=, persist=)`. `GET /api/operations/{id}` for a send is built from the ledger. Files are allowlisted, `format: 2`, and never hold prompt, reply, stream or exception text. The legacy `result` is in memory or reconstructed, in both cases only under the **current** authorisation. Retention removes terminal `format: 2` files only. | `OperationViews` (file at completion, failure and mid-turn has no text; after a restart with the file deleted, the view comes from the ledger and nothing relaunches; revocation withholds links and content on the in-memory and reconstructed branches; a replaced source row is `lost`; the join survives a projection rebuild; retention leaves a pre-1B record untouched) |
| 3. Read boundary | Workspace sessions come from fresh-session receipts. O-12 notes are excluded by the receipted identity fingerprint, not by text. A note projected before its proof arrived is withdrawn on the next read as a `delete` with `note: internal_turn_machinery`. `correlation.send_id` is added at read time. Provenance is kept in the ledger's `provenance` table: not pruned with sends, and carried across a reset whose old ledger is readable. | `ReadBoundary` (receipt-derived workspace session; no ledger gives an unchanged read; note excluded from snapshot, history and changes; equal-text owner control; late proof withdraws the projected row; rebuild, pruning and readable reset keep the exclusion; unreadable-ledger reset **discloses** the loss; unreadable ledger disclosed). `PinnedHttp`: the real dropped-stream note is excluded from all three reads; owner text equal to the note stays owner speech; a failed provenance write hides nothing and the receipt is `unknown`/`ambiguous` |
| 4. Installation guard | `chat_sends.hold_installation(root)` takes an exclusive OS lock and applies the one quiescence contract. It is held by every non-chat `Operations.submit` for its whole run and by the native console for its lifetime; acceptance takes it briefly. The application's own update is not an installation action. | `InstallationGuard`, each case with a **second OS process** (`tests/phase1b_c1/mutation_proc.py`): a mutation in the other process refuses acceptance, then admits it; an open send refuses the other process's mutation; an app mutation is refused while the other process runs a send; an app mutation refuses the other process's send for its whole duration; the console holds the guard until it ends |
| 5. Contract | `docs/CHAT_CONTRACT.md` §8; `PHASE1B_DESIGN.md` Appendix E | `Scopes` (M-17 over HTTP: two profiles, same key); `Disabled` (routes absent without the option; Phase 1A output unchanged; a leftover ledger is disclosed `not_applied`; the shipped files import stand-alone; the two fingerprint functions agree) |

**A loss of provenance is disclosed, not preserved.** The read model reports `incomplete` in two cases: a reset could not read the old ledger, or an app built without keyed sends found a ledger (`not_applied`). In both, earlier notes read as their session recorded them and each read says the guarantee is gone. That is a disclosure; the exclusion is not maintained. It is maintained only across a projection rebuild, receipt pruning, and a reset of a **readable** ledger.

### I.2 Commands and results at `38d6b79` (environment-specific)

Temporary files went to a dedicated directory on `/home`. This host's `/tmp` tmpfs had about 216 MB free, and an unrelated space check fails there. No check was blocked by space.

| Command | Result |
|---|---|
| `TMPDIR=<task dir> python -X dev -W always::ResourceWarning -m pytest -q tests/test_phase1b_c1_integration.py` | **35 passed**, 2 subtests, 0 skipped, exit 0; **0 ResourceWarnings** (the only warning is the existing Starlette/httpx deprecation) |
| `python tools/pinned_hermes_lane.py --checkout <hermes-agent> --python <hermes venv python> --work <task dir>/lane` | verdict **pass**: **19/19 required cases**, 0 skipped, 0 failed, 71.9 s; `lane.json`: `app_commit` `38d6b79`, `app_dirty: false`. Evidence: [`docs/phase1b_c1_integration_evidence/`](docs/phase1b_c1_integration_evidence/) (paths sanitised to `~`, `<work>`, `<tmp>`; host name to `<host>`) |
| full suite, C0 and C1 pinned configured (`PATH=/usr/local/bin:/usr/bin:/bin TAMANITOMO_REQUIRE_NODE=1 TAMANITOMO_C0_HERMES_*` on a separate copy of the verified export with `.c0-revision`, `TAMANITOMO_C1_HERMES_*`, `TAMANITOMO_C1_REQUIRE_PINNED=1`, `pytest -q -rs`) | **1653 passed, 0 skipped, 0 failed**, 502 subtests, 1 warning (the same deprecation), exit 0 |
| unconfigured full suite | not rerun locally at this head; ordinary CI provides it (§I.4) |

The lane manifest is now 19 cases: the 15 from R4 plus `PinnedHttp` ×4. `LaneVerdict` still checks it against the test module. The R4 evidence in `docs/phase1b_c1_evidence/` is unchanged.

Earlier runs on intermediate code during development are not the results of record. For reference only, a diagnostic lane subset (`-- -k http`) at `f76c14f` returned verdict fail, exit 1, as intended.

### I.3 Remaining activation gates (unchanged in kind; nothing here closes them)

- **Tool-capable turns and interruption during a tool:** not run (O-G).
- **Real CLI compression continuation:** only SessionDB-level seam evidence exists (O-G).
- **Managed-descendant containment** for tool processes (O-10); **foreign writers** (O-5).
- **Real-platform supervisor observations** on Windows, macOS and Termux (O-8, O-11, O-9). Those platforms are refused, and CI smoke refusals are not those observations. Rollout is held (O-E); existing users keep `POST /api/chat`.
- **Non-C1 provenance:** rows written outside a keyed send (terminal, Telegram, earlier app versions, history) carry no provenance, and a continuation note there still reads as owner speech. This is documented, not resolved.
- **Provenance is applied only in apps built with keyed sends.** Activation must keep it on wherever a ledger exists; a build without it only discloses `not_applied`.
- **Not built:** the legacy `/api/chat` adapter (optional in the brief), C2 dispatcher safety, C3 client migration.
- **Other properties:** the send route's executor environment is refreshed per request. Eager recovery runs when the app is built. Every non-chat installation action is treated as a mutation (conservative; mirrors the in-process rule).

### I.4 CI

Recorded after the push below.

The sections that follow are the R4-round report, kept as written.

## 0. Closure for PHASE1B_REVIEW_R4

| | |
|---|---|
| Answers | `PHASE1B_REVIEW_R4.md` (C1 retained; two attempt-lifecycle defects; lane completeness; O-12 decision; annotation hygiene) |
| Branch | `test/phase1b-c1-core`, reviewed commits preserved; closure code commit `1e161c3` |
| Activated | **No.** No route, UI, release entry, real profile, C2 or C3. The current send path is unchanged. |

**C1-R4-1 (refused reset erased start identity) and C1-R4-2 (stale executor rewrote a newer attempt's lock).** Integrated reproductions were added to `tests/test_phase1b_c1_core.py::AttemptLifecycle` and run against the reviewed code (`428bef7` modules plus two no-op test hooks, `started_event` and `before_finalize`) before any fix:

| Case | Reviewed code | After `1e161c3` |
|---|---|---|
| S2 committed, controller paused before `generating`; reset refused while E runs; controller killed; another controller recovers | **FAILED**: settled `not_started`, lease released, executor running | pass: `generating`, `liveness=live`, lease held, new key `turn_in_progress`, same key replays (no re-arm); after the executor is killed it settles `unknown`, never `not_started` |
| same, controller survives; the refused reset repeated twice | **FAILED**: receipt `not_started` although the turn completed | pass: `complete/recorded/final`, quiescent |
| reset wins before S2 (before `go`) | pass | pass: executor refused, Hermes never ran |
| stale E1 held **after `go`, before S1** (test-only S1 gate), fence + re-arm, E2 completes, E1 released before E2's settlement | **FAILED** (`test_stale_executor_released_after_the_newer_attempt_finished`) | pass: E2 `complete`, quiescent; one lock file per attempt |
| same, E1 paused before `go` | **FAILED**: E2 `unproven`/`lock_replaced`, lease stuck | pass |
| E1 released while E2 holds its own lock (both gate positions) | pass | pass |
| stale launcher losing T1 | pass | pass (cleanup is now also bound to its claim/attempt) |

Fix: `attempt_id` is the **immutable** identity of a launch attempt, separate from the **revocable** `launch_token` and from the recovery claim. S2 requires both; `executor_started` records the attempt; start evidence is read by attempt in fencing, recovery, promotion to `generating` and receipt derivation; a refused reset still revokes tokens but can no longer erase history. Executor locks are per attempt (`executors/<send_id>.<attempt_id>.lock`), so a stale executor can only open its own; the nonce check is unchanged. Every launcher/finaliser callback carries its attempt (or, before T1, its claim) and returns without acting on any other.

**Lane completeness.** `tools/pinned_hermes_lane.py` now has an explicit 15-case `REQUIRED_CASES` manifest; the verdict fails on a missing, skipped, duplicated, failed or errored case, or any other failure. `LaneVerdict` tests the reviewer's one-case subset (now `fail`), each failure mode, and that the manifest equals the pinned test module. A real lane run with `-k fresh` returned verdict **fail** ("required case did not run: …", exit 1).

**O-12 decision recorded and followed up.** Design §12 O-I records the decision. Investigation of the pinned code: Hermes creates the note in `agent/turn_truncation.py` as a `role=user` dict tagged `_length_continuation_nudge`; the SessionDB projection drops the tag, and `agent/turn_final_response.py` pops it from the live dict when the continued reply finishes, so a flush-time check sees nothing (probed: no tag at `_db_flush_collect`). The executor therefore keeps references to the dicts Hermes created **with** the tag and, at `_db_flush_write` after the commit, matches them **by identity** to the rows whose committed ids Hermes copies back, recording `row_provenance`. Derivation treats only a row committed in this attempt's own receipts and named by that provenance as internal (`internal_rows` in the receipt). Pinned results: the dropped-stream turn is now `complete` with the real owner row and the note listed as internal; an owner message with the note's exact words stays owner speech; with the provenance write forced to fail the receipt stays `ambiguous`/`unknown`; a same-key retry replays the same receipt. No text matching, no Hermes change, no historical reclassification. The Phase 1A read-boundary change (excluding that exact row by provenance) and non-C1 rows remain an activation gate.

**CI annotations.** Only test id, file and exception class are published; the step tolerates a missing `junit.xml`.

**Counts at `1e161c3`** (environment-specific):

| Command | Result |
|---|---|
| lane (`tools/pinned_hermes_lane.py …`), run twice | **pass** both: 15/15 required cases, 0 skipped, 59 s each; evidence in `docs/phase1b_c1_evidence/` |
| lane with `-k fresh` (diagnostic subset) | verdict **fail**, exit 1 (14 required cases did not run) |
| `pytest tests/test_phase1b_c1_core.py` | **100 passed**, 20 subtests; 11 clean runs, 8 of them four-way concurrent; 0 unclosed resources under `-X dev` |
| full suite, pinned not configured, this host | **1575 passed, 39 skipped** (24 C0 + 15 C1 pinned, reasons printed), 496 subtests, 1 warning |
| full suite, C0 and C1 pinned configured | **1614 passed, 0 skipped**, 500 subtests, 1 warning |
| CI | run `36023175886` at `5557208`: all 5 jobs passed (§9) |

The lane interpreter is an existing, inventoried dependency environment (the local hermes-agent venv; `environment.json` lists its 134 distributions), not a clean dependency install; every Hermes import resolved inside the verified export; no profile data was read.

The sections below are the R3-round report, kept as written except where marked; where they differ from §0, §0 is current.

---

| | |
|---|---|
| Answers | `PHASE1B_REVIEW_R3.md` (acceptance of C0 at `8735557`; authorisation of the isolated C1 core) |
| Branch | `test/phase1b-c1-core` (new, unmerged), on top of `8735557` |
| Base / code head | base `87355573c75a2237d54002bed579fde73843c003`; code head `97bb3a1` (the evidence below was produced there); this report is committed on top |
| Scope | **C1 core only**: callable components and their synthetic integration tests. |
| Activated | **No.** No route, UI, `release-files.json` entry or real profile uses these modules. `POST /api/chat`, `Runtime.chat()` and `kit/app/hermes_stream.py` are unchanged, so no platform's current chat changes. C2 and C3 were not started. |
| Hermes | `hermes-agent` `0e9fc2cc152b4a4d9fd736f107412ace2a0c2555`, exported blob by blob and verified by `tools/pinned_hermes_lane.py` (12,298 files, tree `a6b86d2a`). |
| Provider / data | `tests/mock_provider.py` only (127.0.0.1, per-run token, fallbacks disabled). Synthetic `HOME`/`HERMES_HOME` per turn, `PATH=/usr/bin:/bin`. No live profile, credential, model or platform message. |
| Merged / tagged / released / deployed / upstream | **No** |

**What a pass means here.** The lane cases run the production C1 modules end to end against the real pinned Hermes CLI and SessionDB. They are integrated **synthetic** results on **one Linux host**. They are not a production-send certification, not evidence for Windows, macOS or Android, and not evidence for the paths listed in §7 as activation gates.

---

## 1. What was built

| Component | File | Design |
|---|---|---|
| Ledger location, schema, connection rules, ownership guard, row classes | `kit/app/send_protocol.py` (standard library only; imported by the app **and** by the executor under Hermes's interpreter) | §3, §4.1, §4.2, §4.10.1 |
| One quiescence contract | `kit/app/send_quiescence.py` | §4.5 (R4) |
| Durable send service | `kit/app/chat_sends.py`: bootstrap, loss markers, admission and replay, generation fence, freshness, re-arm, launch ownership (T1, spawn in a new session, `go`), stop, settlement, recovery, reset, retention, receipt derivation, installation-mutation check | §4.1–§4.9, §5.1–§5.5 |
| Supervised executor | `kit/app/send_executor.py`: go-gate, S1 lock with recorded identity, S2 under the shared guard, watchdog, commit-boundary recorder, `executor_finished` | §4.4, §4.9, §4.10.1 |
| Designated pinned lane | `tools/pinned_hermes_lane.py` | review R3 5.3 |

Not built (activation work, a later changeset): the `/api/chat/sends*` routes, the legacy `/api/chat` through the ledger, `Operations.submit(ident=)` and the operation-record allowlist/retention (§5.6–§5.8), the Phase 1A classifier reading fresh-session receipts, the `correlation.send_id` projection join, the installation lock around real mutations in `manage.py`, and `docs/CHAT_CONTRACT.md`. The core exposes what those need (`receipt()` with source links gated by the current binding's kinds, `installation_quiescence()`), but nothing calls it.

The send path the review asked to prioritise runs end to end:

```text
bootstrap → immutable pending intent (client key + generation) → durable acceptance (lease)
→ T1 token → spawn (own session/group) → go → S2 registration → pinned Hermes turn (mock provider)
→ commit-boundary receipts → executor_finished → quiescence (lock + empty group) → settlement
→ same-key replay (200, nothing launched, provider not called again)
```

---

## 2. Commands, platform and counts (environment-specific)

Platform: Linux 7.2.0 (CachyOS), x86_64. App interpreter Python 3.14.7. Hermes interpreter Python 3.11.15 with SQLite 3.53.1: the dependency environment of the locally installed hermes-agent venv (134 distributions, listed in `environment.json`). Only its interpreter and packages were used; every Hermes import resolved inside the verified exported tree, and its profile data was never read. Windows, macOS and Android hosts were **not available**.

| Command | Result |
|---|---|
| `python tools/pinned_hermes_lane.py --checkout <hermes-agent> --python <hermes venv python> --work <empty dir>` at `97bb3a1`, run twice | **pass** both times: 13/13 passed, 0 skipped, 0 failed (52 s, 53 s). Evidence: [`docs/phase1b_c1_evidence/`](docs/phase1b_c1_evidence/) (paths sanitised to `~`, `<work>`, `<tmp>`) |
| `pytest -q tests/test_phase1b_c1_core.py` | **86 passed**, 14 subtests; 11 clean repeats, 8 of them as four concurrent copies (load); `-X dev -W always::ResourceWarning`: 0 unclosed resources |
| full suite, pinned **not** configured, **on this host** (`PATH=/usr/local/bin:/usr/bin:/bin TAMANITOMO_REQUIRE_NODE=1 pytest -q -rs`) | **1561 passed, 37 skipped**, 490 subtests, 1 warning (the existing Starlette/httpx deprecation). The 37 skips are the 24 Hermes-backed C0 cases and the 13 C1 pinned cases, each with the reason printed. (CI will differ: it also lacks `uv`, which skips one installer test.) |
| full suite with C0 **and** C1 pinned configured (`TAMANITOMO_C0_HERMES_*`, `TAMANITOMO_C1_HERMES_*`, `TAMANITOMO_C1_REQUIRE_PINNED=1`) | **1598 passed, 0 skipped**, 494 subtests, 1 warning |
| CI (`test.yml`) | recorded after the push in §9; the Windows/macOS smoke jobs now include `tests/test_phase1b_c1_core.py`, where the Linux-only cases skip and the refusal, derivation and recorder cases run. That is refusal evidence, **not** O-8/O-11 supervision evidence. |

The lane exists because ordinary runs skip the 13 pinned cases. In the lane:
- the tree is exported from `git ls-tree`/`git cat-file` (raw blobs; `git archive` applies `.gitattributes` eol conversion, which made 5 `.ps1` files differ on the first attempt), and **every file's git blob hash is re-verified** against the commit's listing, with missing and extra files failing; the test-side locator re-verifies the same manifest before any case runs, so a handwritten marker is not provenance;
- interpreter, SQLite version, installed distributions and the import origin of `hermes_state`, `cli`, `hermes_cli.main`, `hermes_state_messages` and `run_agent` are recorded; an import outside the verified tree fails the lane;
- `TAMANITOMO_C1_REQUIRE_PINNED=1` turns a missing or mismatched prerequisite into a **failure**; the lane verdict is `fail` on any skip, failure or error, or if no required case ran. Checked: required-but-unconfigured → 13 failed; not required → 13 skipped with the reason; one byte appended to `hermes_state.py` → `PrerequisiteMissing: hermes_state.py differs from 0e9fc2cc15`.
- It also caught a real harness regression during this work (the receipt-gap injector stopped firing after ledger opens moved to `file:` URIs), failing the case instead of passing it vacuously (`2e72c4d`).

---

## 3. Review R3 items and where they are answered

| R3 item | Implementation | Evidence |
|---|---|---|
| **5.1** incomplete process observation is not an empty group | `send_quiescence.group_members` returns `complete=false` for permission, I/O (EISDIR), parse failure, an unreadable `/proc`, `hidepid`, or an unsupported platform; only ENOENT/ESRCH ("gone") is skipped. `observe()` → `unproven`. | `Quiescence.*` (real `PermissionError` via `chmod 000`, real EISDIR, a vanished entry, an unparseable entry, `hidepid=2`); `ResetAndQuiescence.test_unreadable_process_data_is_unproven` (lease held, reset refused, new send `turn_in_progress`) |
| 5.1 one hardened contract for release, reset and installation mutations | `sq.observe` is the only liveness decision in lease release, `reset()`, `prune()` lock removal and `installation_quiescence()`. Reset probes without creating, checks identity and group; with an unreadable ledger it uses the identity the executor wrote into its lock file. | combined cases below |
| 5.1 combined cases | executor gone, managed descendant remains; missing lock; replaced lock; unreadable process data; registration racing reset; reset racing acceptance; two recovering controllers | `ResetAndQuiescence.test_executor_gone_but_managed_descendant_remains`, `…missing_or_replaced_lock_is_unproven`, `…unreadable_process_data_is_unproven`, `…registration_racing_reset`, `…reset_racing_acceptance`, `…reset_with_an_unreadable_ledger_uses_the_identity_in_the_lock_file`; `Recovery.test_two_recovering_controllers_one_claim` |
| **5.2** coverage precedence | `derive()` decides coverage first; unidentified rows, an unobservable session insert, a gap, turn rows outside the session set, or a finish fact without `receipts_complete` make coverage incomplete **with or without** `executor_finished`; incomplete never yields `absent`/`none`. Design §4.3.2 corrected. | `Derivation.test_unidentified_clone_rows_then_death_never_become_absence` (derived receipt, not the counter); pinned `PinnedSeams.test_compression_clone_then_death_is_unknown_not_absent` (real `publish_compression_child`, production recorder) |
| 5.2 owner eligibility | `send_protocol.classify`: `user_turn` requires Phase 1A's structural public eligibility; otherwise `user_internal`. Design §4.10.1 corrected. | `OwnerEligibility.test_negative_controls`; `Launch.test_ineligible_owner_rows_do_not_establish_the_owner_turn` (through the executor); pinned `PinnedSeams.test_hidden_and_summary_owner_rows_are_not_owner_evidence` |
| **5.3** designated pinned lane | `tools/pinned_hermes_lane.py`, `tests/phase1b_c1/pinned_lane.py` | §2 |
| **O-E** hold rollout, not engineering | nothing activated; the new path refuses an unproven supervisor (non-Linux platform, missing interpreter, unsupported storage, unreadable or `hidepid` `/proc`) before creating anything; a send inside the protocol has no fallback to the unkeyed path (the service has none) | `SupervisionRefusal.*` (runs on every CI platform) |
| **O-F** gap latching | the committed write is not failed back into Hermes; later writes are refused before they start; `receipts_complete=false`; never `complete`; settlement still happens | pinned `test_receipt_gap_in_a_real_turn` (real CLI, real exception path: Hermes exited **0** after its reply write was refused, and the receipt is `unknown`/`receipts_incomplete`); pinned `test_receipt_gap_after_a_real_commit`; `RecorderConcurrency.test_concurrent_writers_with_a_receipt_failure` (3 threads; every committed write receipted or recorded as the gap); interrupt cases (below); `Launch.test_receipt_gap_…` (settled) |
| O-F interruption paths | every fact write carries a per-executor `fid`; an interrupt around the write is settled exactly once before it is re-raised; an interrupt escaping Hermes after the callback returned is `write_unsettled`; the watchdog delivers at most one interrupt and the window is closed before `executor_finished` | `RecorderConcurrency.test_an_interrupt_after_the_fact_commit_does_not_duplicate_it`, `…before_the_fact_commit_still_records_it_once`, `…inside_hermes_after_commit_is_unsettled_not_published`; pinned stop and deadline turns |
| **O-G** coverage/containment gates | recorded as activation gates (§7); nothing claims them | — |
| **O-H** structured attempt identity | recorded for C2; nothing implemented | — |
| CI counts | `Phase1B_C0_Results.md` §1 now separates this host's count from CI run `35999880594` (`1474 passed, 25 skipped`) and states the smoke jobs did not run C0 | — |

---

## 4. Matrix coverage (PHASE1B_DESIGN.md §10)

"fake" = the local fake Hermes double (a protocol double, **not** Hermes evidence; used where a crash must land at an exact boundary). "pinned" = the real pinned CLI/SessionDB in the lane.

| Case | Where | Result |
|---|---|---|
| M-1, M-1a, M-5 same key, sequential and while the lease is held | fake + pinned | `200 replay`, same `send_id`, one `executor_started`, no further provider request |
| M-2 20 concurrent identical requests over 2 controllers | fake | 1×202, 19×200. First run found a real race (two threads creating the controller lock); fixed |
| M-2a aliases (second app state, symlinked home) | fake | one ledger, one lease; `turn_in_progress` through the alias |
| M-2b two recoverers | fake (subprocess controller) | exactly one `recovery` fact |
| M-2d acceptance vs installation mutation | fake | `installation_busy` (acceptance leg; wiring mutations is activation work) |
| M-3, M-4 | fake | `key_conflict` with the ledger unchanged; `turn_in_progress` |
| M-6, M-6e, M-6f, M-6a, M-6b, M-6c, M-6d | fake | generation, freshness, POST-never-creates, replay after expiry, expired re-arm, lost/corrupt ledger (`send_ledger_lost`, nothing recreated), bounded pruning with unsettled sends kept |
| M-7 kill at each §4.8 row (controller) | fake, subprocess controller SIGKILLed by a test-only subclass hook | after acceptance → `not_started` then re-arm with the same `send_id`; after T1 → `not_started`; M-7a between spawn and `go` → executor exits on EOF, **Hermes never ran** (no `state.db`); M-7b after `go` → exactly one of `not_started`/started |
| M-7 kill of the executor at turn boundaries | fake | before owner row: `unknown/absent/none/bounded`; inside the owner write: `unknown/possible`; after owner row: `unknown/recorded/none`; after reply: `unknown/recorded/partial`; all `executor_lost`, quiescent, settled |
| M-7c/M-7d lock missing, replaced (including inode reuse), symlinked | fake | `unproven`, lease held, reset refused, new send refused |
| M-7e descendant in the group; `setsid` descendant | fake | lease held until the owner kills the group; the escaped child stays alive and is outside the boundary |
| M-8 controller dies mid-turn | fake + pinned | executor continues; recovery supervises through lock and facts; `complete`; one launch |
| M-8a stale owner | fake | its launch and compare-and-set are refused |
| M-8c new key while a send runs | fake | `turn_in_progress` |
| M-9 truncated / disconnect before done | pinned | exit 0 with `length` → `failed`, `reply_incomplete`, `reply=partial` |
| M-9c commit-boundary receipts | pinned seams + fake + recorder unit tests | clone unidentified; gap; eligibility |
| M-11 provider retry in one executor | pinned | launch counter 1, provider counter 3; see O-12 below |
| M-12 stop during the stream | pinned | `interrupted`, `stopped`, no assistant row (`reply=none`), quiescent |
| M-13 deadline; kill fallback | pinned (deadline) + fake (interrupt swallowed → group killed → `unknown/executor_lost`) | as expected |
| M-14a links withheld when the binding no longer authorises the kind | fake | receipt has no `source_links` (receipt leg; the in-memory legacy branch is activation work) |
| M-16b two owner rows | fake + pinned (O-12) | `ambiguous`, no candidate chosen |
| M-17 independent homes, same key and text | fake | two receipts; a `send_id` of one is `NotFound` in the other |
| M-18a resumed session | pinned | `created_here=false`; its rows link |
| M-18b fresh vs upsert | pinned | only rowid-new sessions are fresh (see §5) |
| M-19 bridge / platform unavailable | all platforms | `503 send_supervision_unavailable`, nothing created |
| M-23 privacy | fake + pinned | no owner, reply or stream text in any file under the send-ledger directory; executor stderr is discarded |

Not covered (activation work or C2/C3): M-10, M-14, M-15, M-16, M-16a, M-18 (kill between session commit and receipt), M-19a, M-20*, M-21, M-22*, M-23 size/latency.

---

## 5. Findings made while building C1

1. **O-12 (new): an unmarked `role=user` continuation note.** When the main reply stream drops mid-reply, the pinned Hermes stores the partial reply (`finish_reason='length'`), then a `role=user` row beginning `[System: The previous response was cut off by a network error mid-stream…` with no `display_kind`, not `observed`, not a summary, `active=1`, then the retried reply. Structure cannot tell it from an owner message, and C1 never reads text, so the receipt is `owner_turn=ambiguous`, `reply=partial`, outcome `unknown`, never `complete`. Made deterministic with an additive mock scenario (`recover_stream`: the drop counts streaming requests only). **The same row passes Phase 1A's structural rule as an owner message.** That is reported for the reviewer (design §12 O-I), not changed.
2. **Exit 0 after a refused write.** In the real receipt-gap turn, Hermes caught the refused reply write and still exited 0. Exit 0 is again not evidence of a persisted reply; the receipt says `unknown`/`receipts_incomplete`.
3. **Session freshness by rowid.** The pinned upsert's `VALUES` list contains a literal `NULL`, so mapping `id` to a positional parameter failed (the first real turn came out `receipts_incomplete`). The recorder now reads the ids whose rowid exceeds the pre-statement maximum; see design §4.10.2 (R4).
4. **Descendants holding the controller's pipe.** A Hermes descendant inherited the executor's stdout, so the controller's reader, and a `close()` of the pipe, waited until the descendant exited (60 s in the test). The executor now keeps its wire on a private non-inheritable fd and gives Hermes `/dev/null` on fds 0 and 1; the controller never closes a pipe its reader is blocked on.
5. **A lock's `(st_dev, st_ino)` is not an identity over time.** The first CI run failed `test_missing_and_replaced_lock_paths_are_unproven`: on the runner's ext4, a lock file unlinked and recreated got the **same inode number**, so the identity probe (the design's and C0's) accepted a replaced file. The executor now writes a random nonce into its lock at S1 and records it in `executor_started`; the probe requires device, inode **and** nonce. With an unreadable ledger, a lock file without a readable identity is `unproven` (a replaced path is indistinguishable from an executor that died before writing it). New deterministic test: same inode, different nonce → `lock_replaced`.
6. **Stop and deadline silently degrade when SIGINT is ignored.** `_thread.interrupt_main()` does nothing when SIGINT is `SIG_IGN`, which a process started with `&` from a non-interactive shell (or under `nohup`) inherits and Python keeps. Under a loaded local run started that way, stop and deadline reached only the kill fallback (`unknown`/`executor_lost`). The executor now installs Python's default SIGINT handler before Hermes runs; `test_stop_works_when_the_app_was_started_with_sigint_ignored` fails without the fix (kill after the grace) and passes with it.
7. **Implementation defects found by the tests and fixed:** a controller-lock race between threads (M-2); a plain `sqlite3.connect` would have created an empty file over a missing ledger (all opens are now `mode=rw`, only creation uses `rwc`); concurrent first bootstraps could both create (creation is now exclusive under `create.lock`); a reset through one app state made other app states see `ledger_lost` (the new ledger lists previous ledger ids); a connection leaked when a PRAGMA failed on a corrupt file; `reply=final` was reported for an ambiguous owner turn.

---

## 6. Platform outcomes

| Platform | Outcome |
|---|---|
| Linux (this host) | all C1 core and pinned cases pass as reported above |
| Windows, macOS | not available here. On CI they run the C1 core file: refusal of the unverified supervisor, derivation, owner eligibility and the recorder; supervision cases skip (O-8, O-11 not observed) |
| Android / Termux | not run (O-9) |

---

## 7. Remaining activation gates

Before normal sends go through C1 (C1 activation):
1. Routes (`/api/chat/sends*`), the legacy route through the ledger, operation views and allowlist (§5.6–§5.8), the Phase 1A fresh-session source, the `correlation.send_id` join, the installation lock around real mutations, and `docs/CHAT_CONTRACT.md` — each with its matrix cases (M-10, M-14, M-15, M-16, M-16a, M-18, M-19a, M-22, M-23 size).
2. **O-G** for tool-capable chat: a real tool-using turn, interruption during a tool, full CLI compression continuation, and the descendant boundary for tool processes (O-10). Foreign writers (O-5) against the receipt boundary.
3. **O-12 / O-I**: the reviewer's decision on the unmarked continuation row (C1 is safe as is; Phase 1A shows it as an owner message).
4. **O-E**: Windows (O-8) and macOS (O-11) supervisor tests on real CI hosts, and Termux device evidence (O-9), before any of those is proposed for activation. Until then the new path refuses them.
5. Release: the four modules are deliberately **not** in `release-files.json`.

Then C2 (dispatcher, with the structured `attempt` field, O-H) and C3 (the minimal receipt-aware client), each with its own review.

---

## 8. Files

| File | Kind |
|---|---|
| `kit/app/chat_sends.py`, `send_executor.py`, `send_protocol.py`, `send_quiescence.py` | new production modules, not activated, not shipped |
| `tools/pinned_hermes_lane.py` | the designated lane |
| `tests/test_phase1b_c1_core.py` | 86 tests (derivation, eligibility, quiescence, refusal, admission, launch, crash recovery, reset/quiescence, retention, recorder) |
| `tests/test_phase1b_c1_pinned.py` | 13 pinned cases (lane) |
| `tests/phase1b_c1/` | harness, fake Hermes double, subprocess controller, pinned locator, pinned seam driver, test-only fault injector (`inject/sitecustomize.py`, placed on the executor's `PYTHONPATH` by one test) |
| `tests/mock_provider.py` | additive `recover_stream` scenario |
| `docs/phase1b_c1_evidence/` | sanitised lane evidence at `97bb3a1` (paths → `~`/`<work>`/`<tmp>`, host name → `<host>`) |
| `.github/workflows/test.yml` | the C1 core file added to the Windows/macOS smoke list |
| `PHASE1B_DESIGN.md` | R4 corrections, Appendix C |
| `Phase1B_C0_Results.md` | post-review note; environment-specific CI counts |

---

## 9. CI

| Run | Head | Result |
|---|---|---|
| `36010308868` | `2f11faf` | Windows and macOS smoke **passed** (now including the C1 core file). Linux 3.11/3.13/3.14 **failed**: finding 5 (inode reuse) and a test that did not wait for a killed executor's lock release. Job logs need a signed-in viewer, so `6b4b2a4` added a failure-only step that publishes failed tests as check-run annotations. |
| `36012008668` | `6b4b2a4` | same failures, now readable as annotations; fixed in `97bb3a1` |
| `36015884514` | `84cc9d0` (code `97bb3a1`; not a separate full-suite run at `428bef7`) | **all 5 jobs passed**: Linux 3.11, 3.13, 3.14 (the 13 C1 pinned and 24 C0 pinned cases skip there with the reason printed; the lane is where they run), Windows and macOS smoke (C1 core: refusal, derivation, eligibility and recorder cases run; supervision cases skip). Detailed per-job pass/skip counts were not read: job logs need a signed-in viewer. |
| `36023175886` | `5557208` (closure code `1e161c3`) | **all 5 jobs passed** (Linux 3.11/3.13/3.14; Windows and macOS smoke). As before, the 15 C1 pinned and 24 C0 pinned cases skip on Linux CI (the lane runs them) and supervision cases skip on Windows/macOS; per-job counts not read (logs need a signed-in viewer). |

---

## 10. Not done, not claimed

- No activation: no route, UI, release entry or real-profile use; normal sending is unchanged. No C2, no C3.
- No Windows, macOS or Android supervision evidence; no tool-using, compression-continuation, gateway or cron turn.
- No real provider, credentials or messages; no live profile read or written.
- No merge, tag, release, deployment, upstream filing, or deletion of historical operation files.
- The lane's Hermes interpreter is the dependency environment of a locally installed hermes-agent venv; the lane records it and verifies import origins, but it is not a clean dependency install.
