# Phase 1B — U1/T1 corrections (combined review of 02f2285) and C3 keyed client: results

Prepared 2026-09-24. Answers `CLAUDE_NEXT_TASK.md` of `TAMANITOMO_COMBINED_REVIEW_02f2285`. **Keyed-send activation remains OFF**: the C3 client is served only on an app explicitly built with `chat_sends=Options(client=True)`, which no entry point does. Synthetic data only. The C2 dispatcher was run only by the test suite (fixture life directories, delivery doubles), never on a live profile. No push, merge, release, deployment or version bump. **Stop for review.**

## 1. Starting point and branches

Verified before any change: `test/phase1b-c2-dispatcher-safety` at `02f22856fb60e71f5e8d1283e620e216c5eab798`, clean worktree. The owner's stash (`stash@{0}: WIP on main: e5b7e02 …`) is untouched. No later owner commits existed. Nothing earlier was rewritten.

| Branch (local, unpushed) | Parent | Commit | Contents | Tree |
|---|---|---|---|---|
| `test/phase1b-02f2285-corrections` | `02f2285` | `b69e7c0` | **U1**: candidate patch 01 applied unchanged + the reviewer's actual test files + 4 implementer edge checks | `3a5b00ac` |
| same | | `b14477d` | **T1**: candidate patch 02 applied unchanged + the `Phase1B_C2_Results.md` wording correction | `dfe9ddcf` |
| `test/phase1b-c3-keyed-client` | `b14477d` | `effc80c` | **C3** code, tests, `CHAT_CONTRACT.md` §8.6, `PHASE1B_DESIGN.md` C3 row + Appendix G (**tested SHA**) | `3023de25` |
| same | | this report's commit | this report + `docs/phase1b_02f2285_corrections_evidence/` + `docs/phase1b_c3_evidence/` (documentation only; no code after `effc80c`) | |

Environment for every run: Linux 7.2 x86_64, repository `.venv` Python 3.14.7, pytest 9.1.1, Node v26.7.0 required (`TAMANITOMO_REQUIRE_NODE=1`), `PATH` without `~/.local/bin` (no `hermes` on PATH), `TMPDIR` on the home btrfs file system, synthetic homes only. Browser: headless Chromium 153.0.8010.12 via Playwright 1.63.0. The counts below are this implementer's executions. The reviewer's counts are not repeated as mine.

## 2. Corrections

### U1: Unicode-safe comparison offsets (`b69e7c0`)

- **Patch inspection:** the candidate changes only the comparison string in `PublicFilter.feed()` (`s.translate(_ASCII_LOWER)`) plus its constant and comment. It applied cleanly to `02f2285`. The only other `.lower()` in the module (`public_stream`, line 113) lowercases a slice for a `startswith` test and reuses no index from it, so it is not the same defect. No normalisation, raw-buffer, authorisation or history-policy change.
- **Reviewer tests, actual files:** `tests/test_phase1b_review_02f2285.py` is byte-identical to `reviewer_tests/test_review_unicode_and_c2.py` (SHA-256 `bbe116d6…a342`, as in the packet manifest). `tests/test_phase1b_review_b94caf2_original.py` is byte-identical to `reviewer_tests/test_original_public_output_b94caf2.py` (`ba181b09…18c6`). Nothing was reconstructed.
- **Baseline at `02f2285`** (reviewer file added, code unchanged): **3 failed, 1 passed**. The three failures are `test_lowercase_expansion_preserves_public_characters` (`'İstanbul <ublic answer.'`), `test_fragmentation_does_not_change_hidden_block_exclusion`, and the HTTP `test_interruption_does_not_publish_hidden_unicode_prefixed_delta` (the marker was present in the interrupted `result.response`). The pass is the dispatcher withdrawal control. `runs/u1_baseline.*`
- **After:** the reviewer's 4 new + 4 original tests: **8 passed**. `runs/u1_after_review.*` Supplied C1 closure + R1 + export + original four: **37 passed**, 93 subtests. `runs/u1_c1_focused.*`
- **Implementer edge checks** (`tests/test_phase1b_u1_unicode_offsets.py`, clearly separate from the reviewer's file): uppercase/mixed-case tags after expanding characters at fragment sizes 1/2/3/5/whole; split tags and an unclosed block; non-ASCII text returned unchanged; bounded partial state. **4 failed at `02f2285`** (separate worktree) and **4 passed** with U1.

### T1: self-contained pre-C2 fixtures (`b14477d`)

- **Provenance verified against the real objects:** this repository has `3d78c57` (tree `3b7844f8…`, as in the manifest). `git show 3d78c57:kit/scripts/companion_{outbox,dispatch}.py` is byte-identical (`cmp`) to the fixture files, and their SHA-256 values equal the manifest's. The loader checks the commit and the bytes before compiling. No assertion was weakened, no test skipped, no Git object created.
- **Baseline** (a git-free export of `b69e7c0`, no `.git`, `git rev-parse` → not a repository): **49 passed, 2 failed**. Both are `CalledProcessError` in the `git show` loader. `runs/t1_baseline_source_only.*`
- **After:** checkout, the supplied 51-test C2 selection + the reviewer's 4: **55 passed**, 34 subtests (`runs/t1_c2_checkout.*`). In a git-free export of `b14477d` (`runs/t1_source_only_git_check.txt`): compatibility class **3 passed**, 6 subtests; full C2 selection **51 passed**, 34 subtests (`runs/t1_source_only_{compat,c2}.*`). Tampering one fixture byte in that export fails with `pre-C2 fixture checksum mismatch` (`runs/t1_tamper_check.txt`). The withdrawal-between-precheck-and-claim control stays passing (zero charges, zero deliveries).
- **Report wording:** `Phase1B_C2_Results.md` no longer says C2 takes effect only if merged and released. Running the dispatcher from a development checkout executes C2, so it stays synthetic-only. The "loaded from git" description was corrected.

### Checks at `b14477d` (clean)

| Command | Result | Evidence |
|---|---|---|
| `python -X dev -W always::ResourceWarning -m pytest` on C1 closure, C1 review R1, export, C2 claim/outbox/C0-dispatch, the reviewer's two files, U1 edge checks | **96 passed**, 127 subtests, 0 ResourceWarnings (the reviewer's 92-case selection + 4 implementer checks) | `runs/corr_focused.*` |
| the six affected R3 cases (as named in the review) | **6 passed**, 10 subtests | `runs/corr_r3_affected.*` |
| full suite, unconfigured | **1685 passed, 51 skipped**, 617 subtests. The skips are the unconfigured pinned lanes (24 × C0, 27 × C1) | `runs/corr_full_unconfigured.*` |
| pinned lane (`tools/pinned_hermes_lane.py`, Hermes `0e9fc2cc15`, mock provider) | **verdict pass, 27/27** required cases, `app_commit b14477d`, `app_dirty: false`. Manifest and negative tests unchanged | `lane/`, `runs/corr_lane_console.txt` |

All evidence for this section is in `docs/phase1b_02f2285_corrections_evidence/`.

## 3. C3: minimal keyed-send client (`effc80c`)

### What was built

- **`kit/app/static/chat-sends.js`** (new; not in `release-files.json`). It does nothing unless the page carries `<meta name="tamanitomo-chat-sends" content="keyed">`, and then defines `window.KeyedChat`.
- **Enablement, two explicit opt-ins:** `build(chat_sends=Options(..., client=True))`. Only then does `index()` add the signal meta and the script tag (after every other script), and `/api/feed` rows carry `source_message` (the Hermes row id). An app with the keyed routes but without `client=True`, like the default app, serves the ordinary page and feed unchanged. The mode is never discovered by trying a send.
- **`workspace.js`:** three hooks, inert without `window.KeyedChat`: the submit handler delegates, the chat page calls `attach()` after it renders, and history bubbles get `data-source-*` attributes when a row carries `source_message`.
- **Pending intent** `{v, client_key, generation, conversation_id, installation, profile, session, message, created_at, send_id?, operation_id?}` in `sessionStorage` under `chat-pending-<installation>-<profile>`, beside `chat-draft-…`. It is written and read back before the POST; if storage fails, nothing is sent and the draft stays. Only `send_id`/`operation_id` are ever added. `client_key` is a ULID (the server's format). The scope is captured before any await, and every request carries it explicitly.
- **Sending and recovery:** bootstrap before every new intent. On a lost or unreadable answer, a missing route or a gateway error: `GET ?key=`, then the identical POST with bounded backoff (0.5, 1, 2, 4, 8 s, then every 30 s with "Not confirmed…"). A lookup `404` never mints a new key. `401` stops protected polling and keeps the intent ("Check now" resumes it). Refusals that prove non-acceptance give "Not sent". A reload or a return to Chat resumes only this scope's pending intent.
- **Status:** polls `GET /api/operations/{id}` (the ledger view, 350 ms). `stream.text` replaces the `<send_id>:stream` bubble. At the outcome it reads the receipt until `settled` and fills `<send_id>:owner` / `<send_id>:reply:<n>` from `result.messages` chosen by the receipt's ids. Replies render through the existing `richText`, `extractMediaFromContent` and `inlineMedia` (media URLs are still authorised by the server).
- **Wording:** exactly the §6 table (see `docs/CHAT_CONTRACT.md` §8.6). Ask again and Send again are new intents. Send again appears only while the receipt says `quiescent`/`none`, asks "This may send your message twice.", and re-reads the receipt before minting a key. `generation_changed` clears the intent, shows the reset sentence and offers Send again as a new intent. It is never silently re-generationed.
- **Draft:** the compose box stays editable during a turn (`readOnly` is not set by the keyed path). A definitely-not-accepted message returns to the box only if the box is empty. No outcome clears or replaces a newer draft. The send button is disabled while an intent is pending, and `activeOperation` is set, so the existing non-chat exclusion still refuses other actions.
- **Reconciliation read, documented:** after a reload or a return to Chat with a pending send, one `GET /api/chat/snapshot?limit=50` (Phase 1A). Rows whose `correlation.send_id` is this send's are matched to history bubbles by `(session, source row id)`. At settlement the same match is made from `result.messages[].source`. A matching history row takes over the DOM id, and the provisional bubble is removed. Nothing is matched by text or time.

### Acceptance checklist

| # | Requirement | Result | Evidence (`tests/test_phase1b_c3_browser.py`) |
|---|---|---|---|
| 1 | Double submit, lost response, in-flight lookup 404 and reload recover the same intent: one launch, one owner/reply presentation | **met, with one stated interim limitation** | `test_submit_and_double_submit_launch_once`: 2× `requestSubmit` + Enter + click → 1 POST, 1 send, `executor_started` × 1, 1 Hermes owner row, 1 owner + 1 reply bubble. `test_lost_response_is_recovered_by_the_same_key`: the server accepts, the browser loses the answer, then a lookup by key and one send/launch. `test_lookup_404_while_the_post_is_in_flight_never_mints_a_new_key`: the first POST is held and the lookup sees 404. The original then arrives late (202) before the retry, which replays. One key in every POST, one send, one launch. `test_reload_mid_turn_…`: same key after reload, one launch; **after settlement** one owner + one reply. **Between the reload and settlement the recorded owner row can show twice** (history + provisional), because C1 records a send's links only at settlement; the two merge by id when it settles. |
| 2 | Draft edits survive completion, error, navigation and late callbacks; pending is immutable; storage failure never sends | **met** | `test_draft_edited_during_a_turn_…`: a newer draft typed mid-turn survives Home→Chat navigation and completion (box and `chat-draft-…`); `pending.message` is unchanged; `action('/maintenance/doctor')` is refused mid-turn. `test_storage_failure_never_sends_…`: `setItem` throws for `chat-pending-*`, so 0 POSTs, 0 sends and the draft is kept. Error paths leave the box alone (`test_failed_…`, `test_unknown_…`: box stays empty, not restored). |
| 3 | Receipt-based wording; retries never mint a key or call the legacy route; explicit new sends after unknown need confirmation + quiescence | **met** | `test_failed_generation_…` (exit 1): "Your message was recorded; the reply failed" + Ask again → new key, `failed` + `complete`. `test_stopped_turn_…` (exit 130): "Stopped", partial reply marked "Partial reply". `test_unknown_outcome_…` (executor killed after the owner row): the unknown sentence + Send again; Cancel sends nothing; confirm → receipt re-read → new key. `test_ledger_reset_…`: POSTs blocked, ledger reset, then `409 generation_changed` → reset sentence, 0 sends, one key, pending cleared. `test_refused_while_another_turn_runs_…`: `409 turn_in_progress` → "Not sent", message back in the empty box. Ten of the fourteen keyed tests assert **no `POST /api/chat`** (`assert_never_legacy`; the draft, profile-switch, stopped-turn and withheld-reasoning tests do not check it), and `test_phase1b_c3_disabled.py` checks that the client source has no `/chat` send path. |
| 4 | Profile switch, stale responses and auth expiry keep isolation; non-chat exclusion and media/public-output protections intact | **met** | `test_profile_switch_and_late_results_…`: nova's pending turn and rowan's page. Rowan's draft is intact, no nova bubbles or pending, the send button is enabled, and after nova's turn completes the rowan page makes no request with `profile=nova`. Back on nova: one send, one owner, one reply; rowan has 0 sends. `test_authentication_expiry_…`: operation polls return 401 → wording, polling stops (no further requests over 1.5 s), intent kept, no legacy call; Check now → one send. `test_withheld_reasoning_never_reaches_the_page`: a `<think>` marker streamed and paused mid-block never appears in the page. The reply `Hello <b>there</b>` renders escaped. |
| 5 | The default client is unchanged; the keyed path runs in an actual browser against synthetic fixtures | **met** | `DisabledClient` (default build) and `RoutesWithoutClient` (keyed routes, no client opt-in): no signal, no `KeyedChat`, no script. Submit goes to `POST /api/chat` with the existing "Failed to send" wording, and no keyed request is made. `tests/test_phase1b_c3_disabled.py`: the served page is `index.html` byte-for-byte except version stamps (both builds); the client build adds only the meta and the script; feed rows are identical to the default except `source_message`, which only the client build has; `release-files.json` ships no `chat-sends.js`; no `.py` sets `client=True`. |

### Results at `effc80c` (clean before and after, `runs/run_context.txt`)

| Command | Result | Evidence |
|---|---|---|
| `TAMANITOMO_C3_REQUIRE_BROWSER=1 python -X dev -W always::ResourceWarning -m pytest -q tests/test_phase1b_c3_browser.py tests/test_phase1b_c3_disabled.py` | **21 passed, 0 skipped**, 0 ResourceWarnings | `runs/c3_browser.*` |
| browser file, 5 sequential rounds, then 3 concurrent rounds | **16/16 in each of the 8 rounds** | `runs/c3_stress.txt`, `runs/c3_parallel_*.txt` |
| focused (the corrections selection + `test_phase1b_c1_integration.py`), `-X dev -W always::ResourceWarning` | **131 passed**, 129 subtests, 0 ResourceWarnings | `runs/focused.*` |
| full suite, unconfigured, `TAMANITOMO_C3_REQUIRE_BROWSER=1` | **1706 passed, 51 skipped**, 617 subtests (skips = unconfigured pinned lanes) | `runs/full_unconfigured.*` |
| full suite, C0 + C1 pinned configured (the documented setup: C1 → the lane's verified export; C0 → a separate copy with `.c0-revision`; `TAMANITOMO_C1_REQUIRE_PINNED=1`), `TAMANITOMO_C3_REQUIRE_BROWSER=1` | **1757 passed, 0 skipped, 0 failed**, 621 subtests | `runs/full_configured.*` |
| pinned lane | **verdict pass, 27/27**, `app_commit effc80c`, `app_dirty: false` | `lane/`, `runs/lane_console.txt` |

The single warning in each run is the existing Starlette/httpx deprecation. Evidence: `docs/phase1b_c3_evidence/`, exported with `tools/evidence_export.py` (every XML/JSON re-parsed; manifest hashes; paths and host name substituted).

Development note: while the browser tests were being written, a test harness defect (sleeping outside Playwright blocks its route handlers) and a test race (history loading the stored reply a poll before settlement) were fixed in the tests before `effc80c`. The code defects found the same way were a storage-failure hint overwritten by the composer reset, and the box being made read-only by the shared voice helper. Both were fixed in `chat-sends.js` before `effc80c`. No failing run is presented as passing.

## 4. Remaining limitations (not solved here)

- **Interim double owner row after a reload mid-turn** (item 1 above). It needs links before settlement, which is C1 behaviour and was not reopened.
- A pending intent whose `conversation_id` no longer matches this scope's (the owner binding changed) is left untouched, and it blocks new keyed sends in that tab until the tab is closed. There is no "forget" control.
- No Stop control was added (not in scope). Interrupted wording was exercised with an exit-130 turn.
- The "Send again refused while an execution is still live/unproven" branch is implemented (the button needs `quiescent`/`none`, and the receipt is re-read on confirm), but the fake double cannot produce `unknown` with a live execution, so that branch has no browser test.
- A stored reply row that itself contains inline reasoning markup is shown as recorded (the existing Phase 1A read boundary). The browser test pins the stream boundary with a clean stored reply, as the reviewer's HTTP tests do.
- Desktop headless Chromium only: no Firefox/WebKit, phone keyboard, push, or native Windows/macOS/Termux evidence. No CI (nothing pushed).
- The C1 activation gates stay open: tool processes outside the managed group, escaped descendants, compression read identity, native-platform supervision. C2's outbox protocol still does not cover the notifier/direct-delivery paths or mixed old/new dispatchers.

## 5. Unrelated observations (recorded, not acted on)

- `public_stream()` (the snapshot regex, `re.I`) applies Unicode case folding, so `<thinK>` (KELVIN SIGN) counts as a tag and is removed. `PublicFilter` recognises ASCII tags only and emits it as text. A block written with that character is therefore hidden in the running snapshot but present in a terminal `result.response`. This needs a deliberate choice of one tag definition; it was not changed here.
- The legacy `workspace.js` stream strip (`/<(think|reasoning)>…/`) omits `<thinking>`. It applies only to the unkeyed path's raw `stream_text`.
- `voiceControlsBusy()` sets the compose box read-only. That is why the legacy path blocks draft edits mid-turn; the keyed path does not call it.
