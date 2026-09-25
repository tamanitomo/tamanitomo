# Phase 1B C2 results: dispatcher safety

Prepared 2026-09-24. Implements `PHASE1B_DESIGN.md` §7 (changeset C2, matrix M-20, M-20a–d, M-21) on the accepted design; no second protocol. **Keyed-send activation remains OFF** (C2 does not touch it). Stop for review: no push, merge, release, version bump, deployment or live-data change.

## 1. State and commits

| | |
|---|---|
| Base | `test/phase1b-c1-public-output-closure` at `3d78c57594df100ff7ae170d7aa501a8ad59a6df` (verified: HEAD, clean, no later owner commits; the owner's `stash@{0}` untouched; the public-output branch and its packet are unchanged) |
| Branch | `test/phase1b-c2-dispatcher-safety` (local, unmerged, **not pushed**) |
| Code + tests | `46060d4` — **tested code SHA** |
| Results | the commit adding this file (documentation and evidence only) |

**Unlike C1, C2 is not behind an activation flag.** It changes the shipped dispatcher scripts (`kit/scripts/companion_{outbox,outreach,dispatch}.py`, all in `release-files.json`). On this unmerged branch nothing is live. **Corrected after the combined review of 02f2285:** it is not only merge/release that brings it into effect — running the dispatcher directly from a development checkout of this branch executes the new C2 code. Such execution must stay synthetic (fixture life directories and delivery doubles); running it on a live profile is not authorised, nor is merging or releasing it.

## 2. What was built (and where it follows or departs from §7)

| §7 | Production code | Note |
|---|---|---|
| 7.1 one run per life directory | `companion_dispatch.run()` takes `<life>/.dispatch.run.lock` with `file_lock(timeout=0)` (flock on POSIX, msvcrt on Windows); busy → `{'busy': True}`, nothing done, silent exit 0 | lock order as designed; no outbox/outreach lock held during `hermes send` |
| 7.2 attempts and guarded phases | `companion_outbox.transition()`: the append is written only if, under the outbox lock, the folded status equals the expected one and (from any phase) the entry's current attempt is the caller's. `run()` goes claim `dispatching` → `reserving_slot` → `outreach.claim(attempt=…)` → `slot_reserved` → `sending` → `hermes send` → one outcome. A refused step stops the attempt; the send is never reached without the `sending` marker | **Departure, stated:** `verdict()` (read-only) runs before the claim, so holds (quiet hours, `not_before`, cap-by-verdict) write nothing, as before, instead of claim + release rows every tick. Expiry and withhold are single transitions guarded on `queued`. The image review runs after the claim (step 2) |
| 7.2 step 3 reservation | intent row before any charge; the charge row carries a structured `attempt`; a refusal appends nothing and releases the entry to `queued` (`release_reason: cap` or `ledger_unreadable`) | |
| 7.3 recovery | `companion_dispatch.recover()` under the run lock: `dispatching` → `queued`; `reserving_slot` → `outreach.charges_for(attempt)`: 0 → `queued`, ≥1 → `failed` + `not_dispatched`, unreadable → `reservation_unresolved`; `slot_reserved` → `failed` + `not_dispatched`; `sending` → `unknown`, never resent | the lookup raises on any unreadable/invalid line; `OSError` is treated the same |
| 7.4 late results | `companion_outbox.resolve_unknown()`: same attempt + evidence (`message_id` or `platform_result`) only; one late result at most | no producer exists (as designed) |
| 7.5 classification | `companion_dispatch.classify()`; `PRE_PLATFORM_ERRORS = ()` (empty until O-7 evidence) | a `deliver()` refusal before Hermes is called (file gone, image review) is a definite `failed`, `not_dispatched` |
| 7.6 delivery record | `{platform, requested_target, recipient_resolved, message_id, id_scope: "last_chunk", mirrored, id_missing}` on the outcome row; `recipient_resolved`/`mirrored` only when Hermes states them, else `null` | |
| 7.8 mixed versions | stated in the module docstring, `docs/REFERENCE.md`, and pinned by a test (§4 item 5) | |

Other changes: `companion_outbox.mark()` (hand `drop`, older callers) is now guarded to `queued` entries; `fold()` exposes `attempt`, `run_id`, `delivery`, `not_dispatched`, `release_reason`, `error_code` (never carried across attempts). `hermes_send()` keeps its `(ok, detail)` shape for `companion_watch`. `_hook(name)` is a no-op crash seam; `_invoke()` is the only platform call. The one changed existing test: `tests/test_outbox.py::test_a_failed_send_keeps_its_slot_and_is_not_retried` now expects `unknown` for an **unconfirmed** send (§7.5); its guarantee — slot kept, never retried — is unchanged.

## 3. Tests

`tests/test_dispatch_claim.py` (28 tests, the design's named file) runs the production modules. Doubles: the delivery call `_invoke` only; for crash cases `tests/phase1b_c2/dispatch_proc.py` runs `companion_dispatch.run()` in a subprocess and SIGKILLs it at the named `_hook` (process death: the OS releases the run lock). Pre-1B behaviour is the actual pre-C2 module source at the base (`3d78c57`; these three files last changed in `c0cdbf3`, before Phase 1B). As first submitted it was loaded with `git show`, which failed in checkouts or archives without that commit (review finding T1); it is now loaded from the byte-identical, hash-verified fixtures in `tests/fixtures/phase1b_pre_c2/` (manifest records commit, tree, paths, SHA-256).

All runs at **`46060d4`** (clean before and after, `run_context.txt`), Linux 7.2 x86_64, app Python 3.14.7, Node v26.7.0 required, no `hermes` on PATH, synthetic homes on btrfs (`TMPDIR` on the home file system). Evidence: `docs/phase1b_c2_evidence/` (exported with `tools/evidence_export.py`; every XML/JSON re-parsed, manifest validated).

| Command | Result | Evidence |
|---|---|---|
| `python -X dev -W always::ResourceWarning -m pytest -q -rs tests/test_dispatch_claim.py tests/test_outbox.py tests/test_phase1b_c0_dispatch.py` | **51 passed, 0 skipped**, 34 subtests, **0 ResourceWarnings** | `runs/c2_only_xdev.txt` |
| same flags + `tests/test_audit_2026_09_23.py tests/test_runtime.py` | 172 passed, 0 skipped, 64 subtests; 2 warnings: the existing Starlette/httpx deprecation, and one `ResourceWarning: unclosed database` attributed to `test_runtime.py`. **Pre-existing:** the same warning appears on the unchanged base `3d78c57` with the same files (attributed to a different `test_runtime` test by GC timing); the C2 modules use no database | `runs/c2_xdev.*` |
| `tests/test_dispatch_claim.py`, 4 concurrent workers × 10 rounds | **1120/1120 passed** (28 × 40) | `runs/c2_stress.txt` |
| full suite, unconfigured, `TAMANITOMO_REQUIRE_NODE=1 pytest -q -rs` | **1673 passed, 51 skipped**, 617 subtests. All skips are unconfigured pinned lanes: 24 × C0, 27 × C1 | `runs/full_unconfigured.*` |
| pinned lane (`tools/pinned_hermes_lane.py`, Hermes `0e9fc2cc15`) | verdict **pass, 27/27 required cases**, `app_commit 46060d4`, `app_dirty: false` (C2 does not touch the lane; run to show its manifest and negative tests are intact) | `lane/`, `runs/lane_console.txt` |
| full suite, C0 + C1 pinned configured (documented setup, `TAMANITOMO_C1_REQUIRE_PINNED=1`) | **1724 passed, 0 skipped, 0 failed**, 621 subtests | `runs/full_configured.*` |

Not run: CI (branch not pushed), Windows, macOS, Python 3.11/3.13 for the app, any real Hermes send or platform (by design: delivery doubles only).

## 4. Acceptance checklist

| # | Requirement | Result | Evidence |
|---|---|---|---|
| 1 | Concurrent dispatchers cannot both claim and deliver one entry | **met** | `OneRunOneClaim`: a second run is refused by the run lock while the first is mid-send (1 delivery, 1 slot); with the run lock removed by a double and both runs holding the same snapshot, exactly one claim is written (`sent` + `skipped`, 1 delivery, 1 slot); 8 real processes × 3 rounds over 3 entries: one `dispatching` row per entry ever, 3 deliveries, 3 slots |
| 2 | Each crash boundary gives its outcome without a duplicate delivery or charge | **met** | `CrashBoundaries::test_every_boundary` (SIGKILL): `after_claim` (sent,1,1) · `after_reservation_intent` (sent,1,1) · `after_charge` (failed,0,1) · `after_slot_marker` (failed,0,1) · `after_sending_marker` (unknown,0,1) · `after_delivery` (unknown,1,1); a further run changes nothing. `failed` carries `not_dispatched` |
| 3 | An unreadable charge ledger stays unresolved | **met** | torn outreach line → `reservation_unresolved`, 0 deliveries, not requeued (two runs); a lookup `OSError` → `reservation_unresolved`; `charges_for` raises on a torn line and is 0 only for a missing ledger |
| 4 | Stale or different-attempt updates cannot overwrite the current attempt; classification per §7.5 | **met** | `AttemptOwnership` (different attempt refused; stale expected phase refused; a late `sent` after recovery refused; `unknown` replaced only by the same attempt with evidence, once; a requeued entry belongs to its new attempt; `mark()` refused on an owned or decided entry); `Classification::test_the_table` (id, no id, skipped, partial media error, other error, error with exit 0, timeout, OS error, non-JSON, non-zero exit without JSON, success with non-zero exit) and the record fields; `OutcomesThroughTheDispatcher` |
| 5 | Existing entries readable; old/new simultaneous limitation stated, not solved | **met (limitation stated and pinned)** | a pre-1B outbox (no attempt fields) folds unchanged and its queued entry is dispatched; the pre-C2 `fold()`/`waiting()` (from the verified base source) sees no phase or new outcome as `queued` (M-20d); `test_a_running_pre_1b_dispatcher_is_not_excluded` pins the stated limitation: an old dispatcher with a pre-claim snapshot sends again (2 deliveries, 2 slots) |

## 5. Remaining limitations (not solved here)

- **Old and new dispatchers at the same time** on one life directory: unsupported (§7.8), demonstrated above. Upgrade path: stop the old dispatcher first; to be stated in release notes when released.
- **Windows:** the run lock uses the existing msvcrt `file_lock`, but no Windows run happened; the crash and concurrency tests are POSIX-only (skipped on Windows). No CI ran.
- **Transcript linkage** stays unsupported (§7.7): ids are recorded, the Hermes mirror row still has none; nothing is joined by text or time.
- **`PRE_PLATFORM_ERRORS` is empty**, so every Hermes-reported error is `unknown` (conservative; owner-visible) until O-7 evidence exists.
- **`unknown` and `reservation_unresolved` need the owner:** nothing resolves them automatically; `resolve_unknown()` has no producer.
- **Torn outbox lines** are skipped by the existing `_read` (unchanged); an attempt row lost that way would read as the previous phase. Not changed in C2.

## 6. Separately recorded (not changed; outside the authorised scope)

- `kit/app/chat_sources.py` capability text for "proactive delivery provenance" still says the outbox records no platform id. The design's C2 row lists a capability update; the task scope named only the three scripts, and the status stays `unsupported` either way. Follow-up: update the reason text.
- `companion_outreach.send()` still exists as a direct `hermes send` path with no caller in the repository (its CLI `send` queues). Unchanged; it bypasses the outbox if anything calls it.
- `companion_watch.py` sends its alerts through `hermes_send()` outside the outbox, by design; C2's guarantees do not cover it.
- If C2 is released, `release-files.json` needs `tests/test_dispatch_claim.py` and `tests/phase1b_c2/` (release work, not done).
