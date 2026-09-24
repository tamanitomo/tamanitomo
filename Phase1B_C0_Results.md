# Phase 1B C0 results: verification harness and evidence

| | |
|---|---|
| Answers | `PHASE1B_REVIEW_R2.md` (review of `PHASE1B_DESIGN.md` at `7907066`) |
| Branch | `test/phase1-conversation-contract`, on top of `7907066` |
| Scope | **C0 only**: test-harness and prototype code under `tests/`, plus the focused design amendment (revision 3 of `PHASE1B_DESIGN.md`). |
| Production code changed | **None.** `kit/` is untouched. No sending code, no UI, no migration. |
| Hermes | `hermes-agent` `0e9fc2cc152b4a4d9fd736f107412ace2a0c2555`, exported with `git archive` into a scratch tree (untracked files in the source checkout were therefore excluded). `cli`, `hermes_state` and `hermes_cli.main` were confirmed to import from that tree. |
| Provider | `tests/mock_provider.py` only (127.0.0.1, random per-run token). No real provider, no fallback provider (`fallback_providers: []`, `transport_fallback: deny`). |
| Data | Synthetic homes only (`HOME`/`HERMES_HOME` set to a fresh temp directory per turn, `PATH=/usr/bin:/bin`). No live credentials, transcripts, profiles or messages were read or written. |
| Released / tagged / deployed / merged / upstream | **No** |

**What a pass means here.** The Hermes-backed tests exercise the real pinned `SessionDB` and real quiet one-shot CLI turns. The rules they check (the commit-boundary recorder, the generation fence, the slot-reservation phases, the identity-checked liveness probe) are **harness/prototype** implementations in `tests/phase1b_c0/`. A pass shows how the pinned Hermes behaves at these boundaries and that the prototype rule holds there. It is not an integrated production result: C1–C3 do not exist.

---

## 1. Commands, platform and counts

Platform: Linux 7.2.0 (CachyOS), x86_64. App test interpreter Python 3.14.7. Hermes interpreter Python 3.11.15 (the dependencies of an installed hermes-agent 0.21.1 venv; the pinned source tree is first on `PYTHONPATH`). SQLite 3.53.1 (Hermes interpreter) and 3.53.4 (system). Windows, macOS and Android were **not available**.

Pinned-tree setup (the paths are placeholders):

```text
git -C <hermes-agent checkout> archive 0e9fc2cc15 | tar -x -C <pinned>
echo 0e9fc2cc152b4a4d9fd736f107412ace2a0c2555 > <pinned>/.c0-revision
export TAMANITOMO_C0_HERMES_SRC=<pinned> TAMANITOMO_C0_HERMES_PYTHON=<python with Hermes deps>
```

These two variables are read only by `tests/phase1b_c0/pinned.py`. If they are unset, or the marker does not match, the 24 Hermes-backed tests **skip** with that reason. They never fall back to an installed Hermes.

| Command | Result |
|---|---|
| `pytest -q tests/test_phase1b_c0_receipts.py tests/test_phase1b_c0_admission.py tests/test_phase1b_c0_dispatch.py tests/test_phase1b_c0_liveness.py` (pinned configured) | **48 passed**, 14 subtests passed, 0 failed, 0 skipped |
| `env PATH=/usr/local/bin:/usr/bin:/bin TAMANITOMO_REQUIRE_NODE=1 pytest -q -rs` (pinned configured) | **1499 passed**, 478 subtests passed, 0 skipped, 1 warning (the existing Starlette/httpx deprecation) |
| the same, pinned **not** configured (as in CI) | **1475 passed, 24 skipped** (all 24 are the Hermes-backed C0 tests, reason printed), 476 subtests passed, 1 warning |
| `python -X dev -W always::ResourceWarning -m pytest tests/test_phase1b_c0_*.py` | 0 ResourceWarnings |

Per file: `test_phase1b_c0_receipts.py` has 24 tests (6 reproductions of revision 2 defects, 12 commit-aware seam cases, 6 real CLI turns). `test_phase1b_c0_admission.py` has 12, `test_phase1b_c0_dispatch.py` 6 and `test_phase1b_c0_liveness.py` 6. The admission, dispatch and liveness tests are POSIX-only and skip on Windows with a stated reason. The liveness tests need Linux `/proc`.

Two harness mistakes were fixed during C0 and are recorded here so they are not mistaken for Hermes behaviour:
- In a first draft, faults were injected into Hermes **staticmethods** as plain functions. That produced `TypeError`s, not the intended fault.
- Clone rows were counted with `total_changes`, which includes FTS trigger rows (13 instead of 1). The harness now uses `changes()`.

Both were fixed before the counts above.

---

## 2. Reproductions of the review's counterexamples

Each was reproduced first, then the amended rule was checked on the same input.

| Review item | Reproduction (revision 2 rule) | Amended rule |
|---|---|---|
| B2.1 rollback after the inner helper | Pinned `append_messages_batch`, with a fault injected after `_insert_message_rows` returned: `row_written` for ids 1 and 2; `state.db` empty | `write_intent` then `write_rolled_back`; no receipt |
| B2.1 retried callback | A `database is locked` error inside the callback: Hermes re-ran it (`attempts=2`) and committed ids 1 and 2; revision 2 published `row_written` for **1,1,2,2** | one `write_committed` with `attempts=2` and rows 1 and 2 |
| B2.1 id reuse (SQLite AUTOINCREMENT) | The executor's batch rolled back, then a foreign connection committed a row: it received **id 1**, the id revision 2 had already published as the executor's | no receipt; the foreign row is never claimed |
| B2.2 upsert | `create_session` on an existing id: revision 2 wrote `session_created` | `fresh=false`; only genuinely new ids are `fresh=true`; a failed create gives `write_rolled_back` |
| B2 (found in C0) | `publish_compression_child` inserts the child session row directly (not through `create_session`) and clones a tail row with `INSERT … SELECT`: revision 2 saw neither | child `fresh=true`; clone counted `unidentified=1`, so coverage is incomplete (stated, not guessed) |
| B2 (found in C0) | A receipt failure after Hermes committed: revision 2's fail-closed wrapper raised `OperationalError` **into Hermes after its commit** | `receipt_gap`; that write is not failed; every later write is refused (the row it would have written never landed) |
| B3.1 first use | The client mints at T, the POST at T+0.2 s initialises the floor, and the send is rejected `key_predates_ledger` | bootstrap before minting; accepted. A POST without bootstrap is `not_bootstrapped` and creates nothing |
| B3.2 clock skew | The reviewer's 12:00/12:04/12:01/12:02 trace: the old key was **accepted again** after the reset | `generation_changed` |
| B3.3 same-ID rollback | A database-only restore of a pre-K backup: K accepted again | **the same** under the generation rule. The limitation is real; after the mandatory explicit reset, `generation_changed` |
| B4 charge before marker | Real `outreach.claim` + crash before `slot_reserved`: next run requeued and charged again, so **2 slots for 1 delivery** | `(failed, 0 deliveries, 1 slot)` |
| B1 descendants | A child in E's group was still running after E's lock became acquirable | lease held until the group is empty |
| B1 lock path | Lock unlinked and recreated while E held the original: the create-on-open probe reported **quiescent** | identity probe: `unproven` |

---

## 3. Observations O-1 to O-9 (and new O-10, O-11)

"Observed" means the stated behaviour was seen on the stated path and platform, and nowhere else.

### O-1 the go-gate precedes Hermes; state.db before the turn: **observed (Linux)**
- A `sqlite3.connect` tracer installed before `import cli` recorded **no** `state.db` open during `import cli`, on all 6 CLI paths.
- After import and before `_run_quiet_single_query`, the pinned CLI opened `state.db` 3 times on a fresh home and committed maintenance writes. Recorded caller names include `prune_empty_ghost_sessions`, `prune_sessions`, `sweep_orphaned_sessions`, `update_system_prompt` and `_write_sql`/`_write_rowcount`. None inserted a transcript row.
- **Consequence:** revision 2's "a pre-turn state.db open is harmless (reads, schema checks)" was wrong. These are writes by the executor, possibly to other sessions (pruning). They happen after S2 in the proposed order, so they are tracked executor writes, and the recorder receipts them (with no transcript rows).

### O-2 insert-path completeness: **partly observed**
- The five methods named in revision 2 are **not** the whole surface. Found by source reading and confirmed by execution: `archive_and_compact`, `_clone_message_rows` (multi-row `INSERT … SELECT`), `rewind_to_message`'s replacement, `publish_compression_child` (a direct session `INSERT`), and import. All run inside `_execute_write`, the one commit point. It re-runs the whole callback on locked/busy (`hermes_state.py:840-842`).
- With the commit-boundary recorder, committed receipts equalled the `state.db` rows exactly in all 6 real CLI turns: fresh, resume, error before the first byte, truncated, disconnect before done, interrupted. SessionDB-level scenarios covered batch, chunked batch, replace, compaction, compression child, rewind, sessions and fault cases.
- **Not observed:** CLI-triggered compression continuation, tool-using turns, gateway and cron writers, a second Hermes thread writing concurrently inside E.
- **Consequence:** the recorder moves to `_execute_write` (design §4.10.1). A path that yields unidentified rows makes coverage incomplete, so `owner_turn=unknown`. Paths not observed remain O-G.

### O-3 owner row vs provider request: **observed for 6 paths**
Times are from launch. The owner row was committed before the first provider request each time:

| Path | Exit | Owner row committed | First provider request | Provider requests (stream) | Rows |
|---|---|---|---|---|---|
| fresh, `deltas` | 0 | 1.159 s | 1.240 s | 2 (1) | user; assistant `stop` |
| resume, `deltas` | 0 | 0.798 s | 0.945 s | 1 (1) | + user; assistant `stop` |
| provider 500 before first byte | 1 | 1.332 s | 1.412 s | 6 (3) | user only |
| `truncated` | **0** | 1.175 s | 1.260 s | 5 (4) | user; assistant **`length`** |
| `disconnect_before_done` | **0** | 1.159 s | 1.243 s | 5 (4) | user; assistant **`length`** |
| `hang` + interrupt after 2 deltas | 130 | 1.141 s | 1.224 s | 2 (1) | user only |

**Consequence:** recorded, not relied on. Two more findings from this table:
- **Exit 0 with a `length` row** for truncation and disconnect. `complete` now also needs `finish_reason='stop'` on the last public row; otherwise the send is `failed`, `reply_incomplete` (design §4.3.2).
- **One executor, several provider requests**, from Hermes's own retries and a non-stream auxiliary request. At most one executor is not the same as one provider request (M-11).

### O-4 compression copies: **observed at SessionDB level only**
Rows inserted by `replace_messages`, `archive_and_compact` and `publish_compression_child` are attributed to those methods and classified `rewrite_copy`. A tail clone has no per-row id. **Consequence:** rewrite rows can never supply `user_turn` or `public_output`. The CLI-triggered compression path was not run.

### O-5 turn leases: **not observed**
Source reading only (`agent/turn_facade_lease.py`). The design still does not rely on it.

### O-6 interrupt: **observed on the provider-stream path (Linux)**
`_thread.interrupt_main()` after the second delta: exit 130 in 1.84 s, and no assistant row stored. That contradicts revision 2's claim that partial text is persisted on this path. The tool-call path and other OSes are **not observed**.

### O-7 pre-platform error strings: **not run**
The list stays empty. Safe fallback: every `error` is `unknown`.

### O-8 Windows job objects: **unavailable**
There is no Windows host. The CI Windows runner was not used for an unmocked test in C0. **Consequence:** Windows sends are refused until observed (design §4.5, open item O-E).

### O-9 Termux: **unavailable**
There was no device test. **Consequence:** Android/Termux sends are refused until observed.

### O-10 (new) descendant escape: **not observed for Hermes**
The mechanism itself was demonstrated on Linux: a `setsid` child survives the group kill and is invisible to group enumeration. Whether any Hermes tool path does this is unobserved. It is outside the stated boundary (design §4.5).

### O-11 (new) macOS process groups and flock: **unavailable**
macOS sends are refused until observed.

Linux supervision behaviours observed (`test_phase1b_c0_liveness.py`):
- a descendant does not inherit the lock;
- lock release ≠ group empty;
- `killpg` empties the group;
- identity probe `live` → `quiescent` across executor death;
- a replaced path is `unproven`;
- the controller's death leaves a POSIX executor running, which then releases its lock.

---

## 4. The design amendment

`PHASE1B_DESIGN.md` is revision 3. Revision 2's structure and numbering are kept; 91 passages carry an **(R3)** marker, and Appendix B maps each review item to its change. In summary:

- **B2.** Commit-boundary receipts at `_execute_write`. Fresh-insert-only `created_here`. The terminal-resume `source_kind`. Receipt-coverage classes (complete / bounded / incomplete / unavailable) and a reconciled crash table. `public_output` versus copies and internal rows, and the `finish_reason` rule.
- **B3.** Bootstrap before minting. A server generation as the reset fence (the admission floor withdrawn). Reset serialised through `guard.lock` with fencing and quiescence. The corrected rollback limitation and the mandatory reset procedure.
- **B4.** A `reserving_slot` phase. Charge rows identified by attempt. A per-boundary recovery table with `reservation_unresolved`.
- **B1.** Quiescence = identity-checked lock plus an empty group/job. Lock-file lifetime rules. A platform enablement table: Linux proposed enabled; Windows, macOS and Android refused pending evidence.
- **B5.** The in-memory legacy result passes the authorisation check. Goal 7 wording. M-17 restored.
- **O-A to O-D** recorded as decided. New open items **O-E to O-H** for the owner/reviewer. O-E, the platform refusals, is the one with user-visible cost.

---

## 5. Files in this changeset

| File | Kind |
|---|---|
| `tests/phase1b_c0/receipt_probe.py` | prototype recorders (`rev2` reproduction, `commit` amended rule), run inside the Hermes interpreter |
| `tests/phase1b_c0/seam_scenarios.py` | SessionDB scenario driver (pinned Hermes interpreter) |
| `tests/phase1b_c0/turn_driver.py` | real quiet one-shot turn driver: connect tracer, recorder, interrupt watchdog |
| `tests/phase1b_c0/pinned.py` | pinned-Hermes locator and subprocess helpers (skip if not configured) |
| `tests/phase1b_c0/admission_proto.py` | B3 prototype over a real SQLite ledger and flock |
| `tests/phase1b_c0/dispatch_proto.py` | B4 prototype over the production outbox format and `outreach.claim` |
| `tests/phase1b_c0/liveness_proto.py` | B1 probes (naive vs identity) and `/proc` group enumeration |
| `tests/test_phase1b_c0_{receipts,admission,dispatch,liveness}.py` | the 48 C0 tests |
| `tests/mock_provider.py` | additive: `hang` and `error_before_first_byte` scenarios; `request_times` |
| `PHASE1B_DESIGN.md` | revision 3 |
| `Phase1B_C0_Results.md` | this report |

The C0 files are **not** added to `release-files.json`; they are verification harness, not shipped. The new mock scenarios are additive, and the existing mock-provider tests pass unchanged.

## 6. Not done

- No C1, C2 or C3 production code, no UI, no live migration.
- No Windows, macOS or Android evidence.
- No tool-using, compression-continuation, gateway or cron turn.
- No real provider, credentials or messages.
- No merge, tag, release, deploy or upstream filing.
- No deletion of historical operation files.
