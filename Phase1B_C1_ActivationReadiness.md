# Phase 1B C1 activation readiness: integration closure (F1–F3) and Linux activation evidence

Prepared 2026-09-24 for the continuation handoff of the same date (sections 4–7). **Keyed sends remain NOT ACTIVATED.** Stop for review: no merge, release, version bump, tag, deployment, push or live-data change was made.

## 1. Commits, files, what stays disabled

| | |
|---|---|
| Reviewed base | `test/phase1b-c1-core` at `dd7d61483a198418200c73f51744c240d23c4ee2` (verified: local HEAD = `origin/test/phase1b-c1-core` = the handoff's hash, clean worktree, no later owner commits) |
| Child branch | `test/phase1b-c1-integration-closure` (local, unmerged, **not pushed**) |
| Changeset A (code + tests) | `f4aed6c` — F1–F3 closure |
| Changeset B (tests + manifest only) | `fc1e16b` — eight new required pinned cases; **tested head for the lane** (`lane.json`: `app_commit fc1e16b…`, `app_dirty: false`) |
| Changeset C (docs + evidence) | the commit adding this report |

Changed files:

- **Production (A):** `kit/app/chat_send_routes.py` (restricted `unknown` view, `Hidden`, stream snapshot, `public_stream`, lookup/open authorisation), `kit/app/chat_sends.py` (`lookup`/`open_receipts` take `authorized_kinds`), `kit/app/runtime.py` (`Operations.submit(send_id=)`, `Operations.keyed()`), `kit/app/manage.py` (a keyed operation outside scope is `404`, never the legacy branch).
- **Tests (A, B):** `tests/test_phase1b_c1_closure.py` (new), `tests/test_phase1b_c1_pinned.py` (`PinnedActivation`), `tests/test_phase1b_c1_core.py` (a negative manifest test), `tests/mock_provider.py` (tool-call and overflow scenarios; request bodies kept in memory), `tests/phase1b_c1/fake_hermes/hermes_cli/main.py` (test-only `stream_steps` pause), `tests/phase1b_c1/seed_history.py` (new), `tools/pinned_hermes_lane.py` (manifest 19 → 27).
- **Docs (C):** this report; `docs/CHAT_CONTRACT.md` §8 (current behaviour); `PHASE1B_DESIGN.md` (current-status line, old one labelled superseded; Appendix F); `Phase1B_C1_Results.md` (pointer only; history untouched); evidence in `docs/phase1b_c1_activation_evidence/` (new directory; R4/R5 evidence untouched).

**Still disabled:** routes register only through an explicit `build(chat_sends=Options(...))`; no entry point passes it (`Disabled::test_no_entry_point_enables_it_and_shipped_files_stand_alone` passes); no UI calls the keyed routes; the new modules are not in `release-files.json`; `POST /api/chat` and `hermes_stream.py` are unchanged; no accepted keyed request is ever routed to `/api/chat`. `workspace.js` is unchanged (C3 not started).

## 2. F1–F3: reproduction, fix, result

Reproduction: `tests/test_phase1b_c1_closure.py` was written first, then run against **unchanged `kit/`** in a separate detached worktree of `dd7d614`. Only the new test file and the test-only fake-Hermes `stream_steps` knob were copied in.

```
TMPDIR=<tmp> python -X dev -W always::ResourceWarning -m pytest -q -rA --tb=line tests/test_phase1b_c1_closure.py
```

Baseline (`dd7d614`): **18 failed, 4 passed, 7 subtests passed** (pytest counts failed subtests as failures). By test function: 13 failed outright; 2 "passed" as functions but with failing subtests; 2 controls genuinely passed. Full output: `docs/phase1b_c1_activation_evidence/runs/f1_f3_baseline_dd7d614.txt`.

After the fix (`f4aed6c`, same command): **18 passed, 12 subtests passed** (the 17 above plus `PublicStreamUnit`, a unit test of the new server-side filter that cannot exist on the baseline). `runs/f1_f3_postfix.txt`.

### F1 — keyed operation falling back to the raw legacy row: **reproduced, closed**

| Test | Baseline `dd7d614` | After |
|---|---|---|
| `test_unreadable_ledger_authorised_and_revoked` (ledger-id file unreadable → `lost`) | both subtests FAIL: reply text returned via `stream_text` and `result.response`, **with the binding unchanged and with it revoked** | pass: `status: unknown`, `send_ledger_unavailable`, no content; state.db rows, executor locks and ledger files unchanged |
| `test_corrupt_ledger` | FAIL (reply text leaked, revoked binding) | pass; ledger bytes untouched, no `ledger.lost-*` created by the read |
| `test_persisted_format_two_after_restart` | FAIL: the metadata-only file was served as a legacy row, **leaking the Hermes session id under a revoked binding** | pass: `unknown`, no session id |
| `test_readable_reset` / `_authorised_is_restricted_too` | FAIL both (reply text returned after a confirmed reset) | pass: `send_record_unavailable`; the read changes no generation |
| `test_receipt_pruning` | FAIL (reply text after retention pruned the send) | pass: `send_record_unavailable` |
| `test_other_profile_is_404_even_with_the_ledger_lost` (control) | pass | pass |
| `test_genuine_legacy_operation_and_unknown_id` (control) | pass: legacy chat row keeps its full result; unknown id `400 Unknown operation` | pass (unchanged legacy behaviour kept, including the `400`) |

Fix: the operation is marked as a keyed send's when it is submitted (in memory: `row['send_id']`; on disk: the existing `format: 2` + `send_id`). `Integration.operation_view` returns `None` (the legacy branch) **only** for an id the app knows no keyed send for. A keyed id that the ledger cannot resolve gets the restricted view below; a keyed id from another installation or profile raises `Hidden`, which is a `404`.

The restricted view is metadata only: `status: unknown`, fixed `error`, `send {state: unknown, ledger: unavailable | no_record}`, `result: null`. It distinguishes an unavailable ledger from a missing record, and neither from an unknown id. Reads never create, reset or recover a ledger and never launch. `status: unknown` is terminal for today's poller, so it stops rather than spinning.

### F2 — no live public stream in the keyed polling contract: **reproduced, closed (HTTP polling only)**

Baseline: all six `F2PublicStream` tests FAIL: a running keyed view never carries any stream text (`stream never reached …`). After: pass.

- `test_snapshot_grows_and_is_not_append_only`: a paused synthetic turn shows `A`, then `A+B`. Repeated polls return the same snapshot, not appended text. `stream` disappears at completion and `result.response` is the full reply. The operation file is read mid-turn and at success: no owner, reply or stream text.
- `test_failure_file_holds_no_text`: the operation file for a turn that fails after streaming holds no text.
- `test_revocation_withholds_the_next_read`: the next read after revocation is `{available: false, reason: not_authorised}`.
- `test_other_profile_and_lost_ledger`: another profile gets `404` and no text; a lost ledger mid-turn gives the F1 `unknown` view and no stream.
- `test_reasoning_markup_never_leaves_the_server`: a closed `<think>` block, an unclosed `<reasoning>` block and a partial tag are all removed on the server.
- `test_after_restart_a_partial_stream_is_not_fabricated`: a second app over the same state shows `running`, `reason: not_retained`, no text, one launch.

Limits, stated. This is HTTP polling. No browser was driven, so browser streaming is **not certified**. The server filter handles inline reasoning *markup*. Hermes's `stream_delta_callback` carries content deltas only (the mock's `reasoning_content`/`tool_calls` fields never reach it), so tool internals are not in the stream. That is a property of the pinned callback, observed in C0 and not re-derived here.

### F3 — lookup/open receipts omitting authorised links: **reproduced, closed**

Baseline: `test_completed_turn_all_paths_agree_then_all_withhold`: the `lookup` path with the current binding FAILS (no `session`/`links`/owner/reply ids). Direct, replay and operation-embedded receipts already agreed, and all four already withheld consistently after revocation, as the handoff expected. `test_open_receipts_for_a_paused_unsettled_turn` FAILS. `test_two_profiles_same_key_and_lost_response_retry` FAILS in both profiles. After: all pass. All five paths agree on `session`, `links`, `owner_message_id` and `reply_message_ids`; all omit them together after revocation; no cross-profile visibility; one executor per send after lost-response recovery.

One correction to the handoff's test plan. A deterministically *paused generating* turn has **no** links, by design: links are recorded when the controller resolves an outcome (`_resolve` → `_record_links`), not mid-generation. The unsettled turn *with* links is a finished turn whose process group still has a live member (fake `child='group'`), and that is what the `open=1` test uses. No code was changed to create mid-generation links.

Fix: `SendService.lookup()`/`open_receipts()` take `authorized_kinds`, and the routes pass the captured binding's kinds. Omitted still means no links (deny by default).

## 3. Results actually run (this host)

Host: Linux 7.2 (x86_64), glibc 2.44; synthetic homes and app state on **btrfs** (`TMPDIR` under the home file system, because this host's `/tmp` tmpfs was 100 % full). App interpreter: Python 3.14.7; Node v26.7.0 (`TAMANITOMO_REQUIRE_NODE=1`). The live `hermes` executable was removed from `PATH` for every final run (`PATH=/usr/bin:/bin` or `/usr/local/bin:/usr/bin:/bin`; `command -v hermes` → none).

| Command | Result |
|---|---|
| `python tools/pinned_hermes_lane.py --checkout <hermes-agent> --python <hermes venv python> --work <empty dir>` at `fc1e16b` | verdict **pass**: **27/27 required cases** (the previous 19 + 8 new), 0 skipped, 0 failed, 188.8 s. Pinned `0e9fc2cc152b4a4d9fd736f107412ace2a0c2555`, tree `a6b86d2a…`, 12 298 blob-verified files, every Hermes import from the verified tree; Hermes interpreter Python 3.11.15, SQLite 3.53.1. Evidence: `docs/phase1b_c1_activation_evidence/lane/` |
| full suite, unconfigured: `TAMANITOMO_REQUIRE_NODE=1 pytest -q -rs` | **1629 passed, 51 skipped**, 510 subtests. All 51 skips are unconfigured pinned lanes: 24 × C0 (`TAMANITOMO_C0_HERMES_*` unset), 27 × C1 (`TAMANITOMO_C1_HERMES_*` unset). `runs/full_suite_unconfigured.txt` |
| full suite, C0 and C1 pinned configured (the documented setup: C1 → the lane's verified export; C0 → a separate copy of it with `.c0-revision`; `TAMANITOMO_C1_REQUIRE_PINNED=1`) | **1680 passed, 0 skipped, 0 failed**, 514 subtests, 1 warning (the existing Starlette/httpx deprecation). `runs/full_suite_pinned_configured.txt` |
| `python -X dev -W always::ResourceWarning -m pytest -q -rs tests/test_phase1b_c1_integration.py tests/test_phase1b_c1_core.py tests/test_phase1b_c1_closure.py` | **154 passed**, 34 subtests, **0 ResourceWarnings**. `runs/xdev_resourcewarning.txt` |
| baseline sanity before any change: same `-X dev` command, integration + core only, at `dd7d614` | 135 passed, 22 subtests, 0 skipped |

The earlier reports' counts (for example "1,653 passed, zero skipped" at `38d6b79`) were **not** copied; every number above was run here.

**CI: pending / not run.** The branch has not been pushed: remote writes need the owner's explicit authorisation, which this task did not include. Linux 3.11/3.13/3.14 and the Windows/macOS smoke jobs have therefore not run on `fc1e16b` or later. Locally only Python 3.14 (app) and 3.11 (Hermes) were exercised. The workflow does not configure the pinned lane, so CI would not replace it anyway.

A negative test still proves a selected subset cannot pass the full-lane gate (`test_a_subset_with_one_passing_case_fails`). A new one shows the previous 19-case set alone now **fails** the verdict with 8 missing cases (`test_the_previous_manifest_alone_no_longer_passes`). `test_the_manifest_is_exactly_the_pinned_test_module` keeps the manifest and the module equal.

## 4. Gate table

Legend: **closed** = demonstrated against pinned code with the guarantee holding; **open** = measured failure or missing guarantee; **not observed** = no environment here. A passing test that *pins* an observed limitation is listed as **open**.

| Gate | Status | Evidence (pinned lane unless stated) |
|---|---|---|
| Tool-using turn | **closed (Linux)** | `test_tool_turn_completes_with_tool_rows_excluded`: the real quiet CLI calls the pinned `terminal` tool (writes and reads a file in the synthetic home), then replies. Rows: owner `user_turn`; `assistant` (tool_calls) `assistant_internal`; `tool` `internal`; final `public_output`. The receipt links only the owner and final reply rows. One launch; 2 main stream requests + 1 auxiliary; same-key replay, no relaunch |
| Stop during a tool | **closed for this path (Linux)** | `test_stop_during_a_tool`: the tool (`sleep`) is alive in **its own session** (pgid ≠ executor pgid). After the stop *request*: lease still held, not settled. Outcome `interrupted`/`stopped`/`quiescent`; the tool process is gone, because **Hermes's own interrupt cleanup killed it**, not Tamanitomo containment. No provider request after the stop; same-key retry `200`, one launch |
| Deadline during a tool | **closed for this path (Linux)** | `test_deadline_during_a_tool`: `interrupted`/`timeout`/`quiescent`; the tool is gone (Hermes cleanup); retry replays; one launch |
| Controller death during a tool | **closed (Linux)** | `test_controller_death_during_a_tool`: the controller is SIGKILLed while the tool runs; mid-point `generating`, lease 1, tool alive; a new controller supervises to `complete`/`quiescent`; one launch |
| Executor killed during a tool (the supervisor's kill after the stop grace, or any hard kill) | **OPEN** | `test_executor_killed_during_a_tool_leaves_the_tool_running`: after SIGKILL of the executor's process group, the send settles `quiescent`, **lease 0, while the tool process is still alive**. Cause, from source: the pinned local terminal backend starts every command with `start_new_session=True` (`tools/environments/local.py`), so tool processes are never in the managed group, and quiescence cannot see them. The lease can be released while a tool the turn started is still running |
| Real CLI compression, receipt side | **closed (Linux)** | `test_real_cli_compression_continuation`: a 40-exchange synthetic history seeded through the pinned SessionDB is resumed; the provider refuses the first main request with a structured `context_length_exceeded`; **the real CLI reactive compression ran** (4 requests: title, overflow, compression, retry). Observed: **in place, same session, no child session**. Hermes appended copies of history, a summary row, and a **verbatim copy of the owner message**. The executor classified every copy `rewrite_copy`; the receipt owner = the real owner row, reply = the final row; one launch |
| Real CLI compression, read side (snapshot/history/changes/rebuild) | **OPEN** | Same test, pinned as observed. Hermes deactivates the originals; the Phase 1A reads follow `active`. So the **real owner row reads as deleted** (the send's `links` = `lost`, and the legacy `result` is not retained). The **copies read as new public messages** in snapshot, history, changes and after a projection rebuild. The owner-text copy reads as **uncorrelated owner speech**. Only the summary row stays hidden. This affects any compressed session, keyed or not (a Phase 1A read-contract gap). A preflight (turn-start) compression was **not** triggered. In a diagnostic probe (not a lane case) the same history without the overflow went through uncompressed as one ~657k-character request: with no provider-reported usage, the pinned preflight defers on its rough estimate |
| Ordinary descendants | **closed at fixture level only** | In-group children keep the group non-empty, so the send stays unsettled until they end (`test_phase1b_c1_core.py` M-7e group leg, fake Hermes; re-run in the suites above). Through the pinned tool **no child is ever in the group** (next row) |
| Escaped descendants | **OPEN** (stated boundary O-10, now measured on real Hermes) | `test_tool_descendants_escape_the_managed_group`: a Hermes-managed background process (`background: true`) and a child a fixture script detaches with `os.setsid()` are both alive after the send settled `complete`/`quiescent`, each in its own session; the executor's group is empty; neither was detected. Fixture leg: core M-7e setsid. Also observed: in single-query mode the pinned tool refuses a foreground `&` and `nohup`/`disown`/`setsid` wrappers, and blocks `sh -c` as dangerous (no user to approve). Those are Hermes guards, not a containment guarantee |
| Foreign writers | **partly closed (Linux): attribution holds; coordination is upstream's, and partial** | `test_foreign_writers_are_never_attributed`. While the keyed send runs, a second pinned CLI resuming **the same session** is refused by **Hermes's own session-owner lease** (`hermes-refusal-reason: SESSION_NOT_OWNED`). Tamanitomo's lease plays no part, and the foreign process never waits on it. An unrelated fresh-session turn in the same profile runs freely (control). After settlement, a same-session foreign turn with **identical owner text** is accepted by Hermes; its rows are never receipted or linked, and the receipt's links are unchanged. Not established: older Hermes versions, gateways, or direct SQL writers honouring anything. Tamanitomo's installation lock is not claimed to bind them |
| Linux supervision | **evidence gathered; activation still blocked** by the three open rows above | this report |
| Windows | **not observed** | supervisors still refused (`send_supervision_unavailable`); CI smoke not run on this branch |
| macOS | **not observed** | as Windows |
| Android/Termux | **not observed** | needs synthetic device evidence; desktop Linux is not a substitute |

No production change was made in Changeset B. None of the measured failures has a narrow fix inside the existing protocol (see §6).

## 5. Privacy, authentication, preserved behaviour

- **Operation files:** read mid-turn, at success and at failure (`F2PublicStream`, `OperationViews`): no owner, reply or stream text. The allowlist (`PERSISTED`) is unchanged. The in-memory marker added for F1 is a `send_id`, which is already in the allowlist.
- **Content withholding on every read path:** receipt, key lookup, open receipts, replay, operation view, stream snapshot and legacy result. All follow the current binding and are rechecked per request. A keyed operation can no longer reach the unrestricted legacy branch.
- **Ledger directory (real turn):** `test_fresh_turn_completes_and_the_same_key_replays` still finds no owner or reply text anywhere in it.
- **Phase 1A / O-12 preserved:** `PinnedHttp` (dropped-stream note excluded from snapshot/history/changes, equal-text owner control, note without provenance read as recorded) and every `ReadBoundary`/`Scopes`/`Disabled` test pass, unchanged.
- **Evidence sanitisation:** paths rewritten to `~`, `<repo>`, `<work>`, `<tmp>`, `<job>`, `<hermes-checkout>`, the host name to `<host>`; a scan finds no residual home path, host name, token or key string. Mock-provider tokens are per-run random and are not in the evidence. All content is synthetic.
- **Nothing live was touched:** synthetic homes only, local mock provider only, no model request, no message sent. The Hermes checkout under `~/.hermes` was read only through `git ls-tree`/`cat-file`/`archive`; its untracked files are excluded by the export.

## 6. Recommendation for the next separately reviewed task

Do **not** activate. The three Linux gates above are open, and three platforms are unobserved. Recommended next task, as its own design and review, in this order:

1. **Tool-process supervision (the executor-kill gap).** Narrow proposal: an executor seam around the pinned local backend's spawn (like the existing provenance seam) records each tool process's session/pgid as a fact *before* it runs. The quiescence contract then treats every recorded tool group like the executor's group: live, or proven empty. The supervisor's kill path extends to those groups. This keeps immutable attempt identity, claim fencing and the one quiescence contract. The Hermes-managed background registry (`process_registry`) needs the same recording, or such tools stay refused.
2. **Escaped-descendant containment** is a platform change. On Linux: a delegated cgroup-v2 scope per attempt (Hermes already reasons about `systemd-run --scope`), with quiescence = an empty cgroup, so `setsid` cannot leave it. Where no delegated cgroup is available, report `unproven` rather than `quiescent`. This needs its own design; activation stays off until then.
3. **In-place compression read contract (Phase 1A).** Decide what is canonical after an in-place rewrite. The executor already classifies `rewrite_copy` rows; it can record copy → original provenance, bound to fingerprints. The reads can then keep the original's message id and hide copies, including the owner-text copy, as they do for continuation notes. Sessions compressed outside a keyed send have no such provenance; they need an explicitly stated trusted-read limitation.

C2 (dispatcher safety) can proceed in parallel as separately reviewed engineering, since it does not depend on these gates. C3 client work can build against the unactivated fixture path, now that F2 gives it a polling stream and F3 gives it consistent recovery links. Production cutover stays gated on the above and on Windows/macOS/Termux evidence.
