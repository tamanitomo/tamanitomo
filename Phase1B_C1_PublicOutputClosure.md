# Phase 1B C1 public-output closure (review of `b94caf2`: R1–R4)

Prepared 2026-09-24 for `TAMANITOMO_C1_REVIEW_AND_HANDOFF_b94caf2.md`, section 7. **Keyed-send production activation remains OFF.** Stop for review: no push, merge, release, version bump, tag, deployment or live-data change.

## 1. State and commits

| | |
|---|---|
| Verified base | local `test/phase1b-c1-integration-closure` at `b94caf2df48671b0572b01ef4e269afa1d32fed4`. HEAD matched it, clean, no later owner commits. The older stash `stash@{0}` (`WIP on main: e5b7e02`) is untouched. `origin/test/phase1b-c1-core` was not used as a base |
| Child branch | `test/phase1b-c1-public-output-closure` (local, unmerged, **not pushed**) |
| Changeset A — R1/R2 output | `d9ee878` — `kit/app/chat_send_routes.py` (the **only** production file changed in this task) + tests |
| Changeset B — R3 fixtures | `1142d25` — tests and the test-only fake double; no production change. **Tested code SHA** for the final runs |
| Changeset C — R4 evidence + docs | the commit adding this report: `tools/evidence_export.py` (new), `tests/test_evidence_export.py` (new), evidence directories, contract/design/readiness status lines |

Kept unchanged: the F1 keyed-origin marker and restricted `unknown` view, and F3's authorisation propagation through `lookup`/`open_receipts` (no edit to either). `runtime.py` needed no change: the fix sits before `report.stream`, so `Operations`' raw buffer is untouched and simply never receives withheld text.

## 2. The reviewer's regressions: availability

The review's companion ZIP, including `test_phase1b_c1_review_r1.py` and its logs, was **not available on this host**; only the handoff markdown was. `tests/test_phase1b_c1_review_r1.py` is therefore a **reconstruction** from the review's descriptions. It keeps the class `StreamPrivacyReview` and the three named regressions and adds one ordinary-public-output control. It uses the existing fake Hermes double with a deliberately clean durable reply row. Its bytes are not the reviewer's, and the reviewer's own raw logs are **MISSING** here.

## 3. R1/R2 — reproduction, fix, results

Baseline: a detached worktree at `b94caf2`. `kit/` was unchanged; only the new test file and the fake double's `at<i>` acknowledgement were copied in.

```
TMPDIR=<tmp> PATH=/usr/bin:/bin <repo>/.venv/bin/python -X dev -W always::ResourceWarning -m pytest -q -rA \
    --tb=short -p no:cacheprovider tests/test_phase1b_c1_review_r1.py
```

| Run | Code | Result | Log (`docs/phase1b_c1_public_output_evidence/runs/`) |
|---|---|---|---|
| Reviewer regressions (the 4-test file) | `b94caf2` kit | **3 failed, 1 passed** (3.01 s). All three fail on the hidden marker; the public-output control passes | `review_r1_baseline.txt/.xml` |
| Full file, adding the coverage and unit classes written for this task | `b94caf2` kit | 7 functions failed, 5 passed. 4 are product failures on the hidden marker (the 3 regressions + interruption). 3 are `ImportError` for `PublicFilter`, a symbol that does not exist on the base, so not a product result. Revocation, ledger loss, restart and source-unavailable already withheld on the base. Pytest's aggregate line reads "78 failed, 5 passed" because each failing subtest counts | `review_r1_fullfile_baseline.txt/.xml` |
| Same file, fixed | `1142d25` | all pass (inside the 167 below) | `xdev_c1.txt/.xml` |

A first draft of the rollover test failed on its later "public tail" wait rather than on the marker. It was reordered so its first failing assertion is the defect itself (the marker visible during the pause), and the baseline row above is from the reordered test.

### Fix (`d9ee878`, `kit/app/chat_send_routes.py`)

- **R1:** `PublicFilter` is an incremental, bounded filter, one per attempt, created in `launch_action` and fed from the single supervising thread. It tracks whether the stream is inside a `<think>`/`<thinking>`/`<reasoning>` block (case-insensitive) and holds at most 11 characters of a possible tag split across fragments. It never stores a withheld body.
  - Only its output reaches `report.stream`, so the operation's in-memory buffer holds public text only, and a raw-buffer rollover can no longer drop an opening tag.
  - At the end of the attempt, a partial that never became a tag is emitted as ordinary text; an unclosed block stays withheld.
  - A re-armed attempt gets a new operation and therefore a new filter. A provider retry inside one executor is the same stream.
- **R2:** `legacy_result` prefers the authorised linked final reply row and uses the (already filtered) transcript only when no reply row is linked. Both go through `public_text()`. The F1 fail-closed view, revocation, ledger-loss and source-link checks are unchanged. Nothing is regenerated.
- **Stated boundary:** `result.messages` are the Phase 1A projected rows, as the snapshot shows them. A reply row that Hermes itself stored with inline reasoning markup is shown as recorded; that is a read-contract matter, not changed here. Hermes history is never rewritten.

### Coverage now (`tests/test_phase1b_c1_review_r1.py`, `tests/test_phase1b_c1_closure.py`)

| Concern | Tests |
|---|---|
| Running snapshot across a rollover | `StreamPrivacyReview::test_running_hidden_block_stays_hidden_after_raw_buffer_rollover`: `<think>`, 1,000,050 filler characters, the marker, a pause before `</think>`. The fixture acknowledges the pause; the test polls for 1.5 s, then requires the later public tail (the ordered pipe proves the marker delta was already processed), then the terminal payload. None contains the marker or the filler. One launch |
| Terminal success / failure | `…completed…`, `…failed…`: the whole payload, the operation file, one launch |
| Interruption | `StreamPrivacyCoverage::test_interrupted_keeps_only_public_partial_text`: stop mid-stream; the response is the filtered public partial |
| Restart / reconstruction | `…restart_reconstruction_uses_the_clean_row` (response and messages) |
| Revocation | `…revocation_withholds_everything` |
| Ledger loss | `…ledger_loss_is_the_restricted_view` (F1 view, no content) |
| Source unavailable | `…source_unavailable_withholds_content` (`links: unavailable`, no content) |
| Unknown state | **not separately covered**: no deterministic fixture yields `unknown` after hidden deltas. The terminal path is the same `legacy_result` |
| Filter unit | `PublicFilterUnit`: every two-way split and char-by-char feeding; bounded state across 3,000,000 characters inside a block; `a < b`, `<b>`, trailing `<thi`, unclosed block, orphan closer |
| F1 no-extra-launch gaps (documented in the previous packet) | the corrupt, readable-reset (both), pruning and persisted-after-restart reads now assert unchanged deterministic counters: operation rows, executor lock files, Hermes rows |

## 4. R3 — fixtures (`1142d25`, test-only)

| Fixture | Change |
|---|---|
| F3 `open=1` | A **test-owned barrier** wraps `_kill` on the app's own `SendService` instance. `_kill` is reached only after `_finalize` has resolved the outcome and recorded the links, and before descendant cleanup and settlement. Reads cannot reach `_kill` meanwhile, because `recover` returns early for an actively supervised send. All five paths (direct, key, open, operation, replay) are compared under the current binding, then again after revocation, while the **same** send is still unsettled. The barrier is released in `finally`; settlement, one launch and an empty open list follow |
| Swallowed interrupt | The double writes `hang_ready_file` from **inside** its interrupt-swallowing loop. Only then is a stop requested, and `stop_seen` + `kill_sent` + one `executor_started` are asserted. A deadline cannot be ordered after that acknowledgement, because its clock starts before the double loads, so this leg now uses stop; the kill-fallback path it reaches is the same |
| Escaped child | The **child** writes `child_ack_file` after `os.setsid()`, and the double waits for it. The test checks the ack equals the pid and `os.getsid(child) == child` |
| Stale-attempt injection | `injection_prerequisite()` probes whether the executor interpreter actually loads `inject_delay/sitecustomize.py` (`os.open` is `gated_open`). If it doesn't, the test fails with "TEST PREREQUISITE MISSING", never a timeout or skip. `test_a_shadowed_injection_is_reported_as_a_missing_prerequisite` proves the probe catches a shadowing `sitecustomize` |

Stale-attempt, nonce, fencing, no-extra-launch and lease assertions are unchanged.

**Determinism under load** (`runs/stress_new.txt`, `stress_baseline.txt`): the five R3 tests, 4 concurrent workers × 10 rounds.
- New fixtures (`1142d25`): **200/200 passed**.
- Old fixtures on the baseline (`b94caf2`): **also 200/200 passed**. The reviewer's three timing failures **did not reproduce on this host**.

The fixture corrections rest on the review's source-level explanation and remove the timing dependency by construction. They are not a response to an observed local failure.

## 5. R4 — evidence export

- **Defect reproduced:** `docs/phase1b_c1_activation_evidence/lane/junit.xml` fails to parse at line 1, column 212 (`hostname="<host>"`). **The same defect is in the earlier `docs/phase1b_c1_evidence/junit.xml` and `docs/phase1b_c1_integration_evidence/junit.xml`** (column 211), produced by the same text sanitiser. All 28 JSON files in the b94caf2 evidence parse.
- **Fix:** `tools/evidence_export.py` parses XML and JSON, redacts parsed values, and re-serialises with the format's own writer, so placeholders are escaped. It then re-parses each output and checks that JUnit case identities and statuses are equal before and after. It fails on any other malformation and on forbidden strings in outputs or in its own manifest, and writes `MANIFEST.json` (bytes, SHA-256, source, source SHA-256, repairs) for the exact bytes. Tests: `tests/test_evidence_export.py` (3 passed).
- **Derivatives (format-only, NOT reruns):** `docs/phase1b_c1_evidence_derivatives/` holds repaired copies of the three historical `junit.xml` files. Cases are preserved: 15/15, 19/19 and 27/27 passed. `repaired: ["<host>"]`. Originals are unchanged (no diff to any earlier evidence directory). The JUnit header `tests="29"` for 27 cases is kept as pytest wrote it (subtests counted); counts were not edited.
- **New executed evidence:** `docs/phase1b_c1_public_output_evidence/` holds 46 files through the same tool, including the new lane's `junit.xml`, which parses with `hostname="&lt;host&gt;"`. Both manifests were validated after export: every listed file matches bytes and hash, nothing is unlisted, and every XML/JSON file parses. A leak scan finds no home path, host name or job path.

## 6. Verification (all run for this task; no earlier count reused)

Host: Linux 7.2 x86_64, glibc 2.44; app Python 3.14.7, pytest 9.1.1, FastAPI 0.141.1, Starlette 1.6.0, httpx 0.28.1, `pyte` installed, Node v26.7.0. Synthetic homes on btrfs (a supported type; `TMPDIR` on the home file system because `/tmp` is full). No live `hermes` on PATH (`run_context.txt`: `hermes=none`).

| Run | Code | Result | Evidence |
|---|---|---|---|
| `-X dev -W always::ResourceWarning` integration + core + closure + review_r1 | `1142d25`, clean | **167 passed, 0 skipped**, 115 subtests, 0 ResourceWarnings | `runs/xdev_c1.*` |
| same, earlier attempt | `1142d25`, but an untracked `tools/evidence_export.py` was briefly present | 167 passed, 0 skipped (kept for transparency; superseded by the clean run) | `runs/xdev_c1_overlapped.*` |
| Full suite, unconfigured, `TAMANITOMO_REQUIRE_NODE=1` | `1142d25`, clean | **1642 passed, 51 skipped**, 591 subtests. All 51 skips are unconfigured pinned lanes: 24 × C0, 27 × C1 | `runs/full_unconfigured.*` |
| **Pinned lane** | `1142d25`, `app_dirty: false` | verdict **pass, 27/27 required cases**, 188.8 s. Hermes `0e9fc2cc152b4a4d9fd736f107412ace2a0c2555`, tree `a6b86d2a…`, blob-verified export, all imports from the verified tree | `lane/lane.json`, `lane/junit.xml`, `runs/lane_console.txt` |
| Full suite, C0 + C1 pinned configured (documented setup, `TAMANITOMO_C1_REQUIRE_PINNED=1`) | `1142d25`, clean | **1693 passed, 0 skipped, 0 failed**, 595 subtests | `runs/full_configured.*` |
| Full suite, unconfigured, over the Changeset C tree before this report and before the evidence re-export that added this log (tree `d7112e4a…`; the only later differences are documentation and evidence files) | pre-commit C | 1645 passed, 51 skipped (1642 + the 3 export-tool tests) | `runs/full_unconfigured_changeset_c_tree.txt` |
| Fixture stress | `1142d25` / `b94caf2` | 200/200 and 200/200 | `runs/stress_*.txt` |

The lane manifest is unchanged at **27 required cases**. `test_a_subset_with_one_passing_case_fails` and `test_the_previous_manifest_alone_no_longer_passes` still pass (inside the core runs).

**CI: not run.** The branch is not pushed.

### Failure/skip classification

| Kind | Here |
|---|---|
| Product failures | R1 and R2, reproduced at `b94caf2` (4 tests, above); none remain at `1142d25` |
| Fixture failures | The review's three timing races: **not reproduced here** (200/200 under load); corrected by construction |
| Missing dependencies | none here (`pyte` present). The review environment lacked `pyte` |
| Unavailable test injection | none here (the probe confirms `gated_open` loads). The review environment's own `sitecustomize` shadowed it; that now fails explicitly as a prerequisite |
| Host permissions | none; the permission-denial case ran here (it was skipped in the privileged review environment) |
| Unavailable environments | CI; Windows, macOS, Termux native supervision; any browser. The reviewer's original test file and logs |

### Reviewer-environment discrepancies

The review ran Python 3.13.5, pytest 9.0.2, FastAPI 0.128.2, Starlette 0.50.0 and httpx 0.28.1 on tmpfs, without `pyte`, with a shadowing `sitecustomize`, and with privileges that bypass file permissions. Here: Python 3.14.7, pytest 9.1.1, FastAPI 0.141.1, Starlette 1.6.0, httpx 0.28.1, on btrfs, with `pyte`, without a shadowing `sitecustomize`, unprivileged. Python 3.13 was not run here.

## 7. Activation gates (unchanged)

| Gate | Status |
|---|---|
| Tool processes outside the managed group (executor hard-kill) | **OPEN**: failed requirement (`tool_executor_killed_turn.json`) |
| Read side of real CLI compression | **OPEN**: failed requirement (`real_compression_turn.json`) |
| Escaped descendants | **OPEN**: demonstrated limitation, O-10 (`tool_descendants_turn.json`) |
| Windows / macOS / Termux | **not observed** in this task; still refused |
| F2 public stream (HTTP polling) | R1/R2 closed by behavioural tests at `1142d25`, pending review. No browser test |

The passing `PinnedActivation` observation tests still record unsafe outcomes. They keep those gates open; they are not satisfied requirements. Nothing in this task changes containment, compression identity, C2, C3, Phase 1C or UI.
