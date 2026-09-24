# Phase 1A results: trustworthy conversation reads and a synthetic provider

| | |
|---|---|
| Base | `7fef922`: the Phase 0 closure commit on `test/phase0-memory-correctness`. Closure CI run 35955872873 passed all 5 jobs. |
| Branch | `test/phase1-conversation-contract` |
| Scope | Phase 1A only: source inventory, owner boundary, read-only adapter, app-owned projection, snapshot/history/changes, and the mock provider. |
| Not done | Send path (1B), reflection/Hermes continuity (1C), any UI, dock, SSE/WebSocket, new channel connector |
| Released / tagged / deployed / VERSION | **No** |
| Live data | **None read or changed.** The Hermes schema was read from its source code, not from a live database. All tests and measurements use synthetic stores. |

The contract, the API and the capability table are in [`docs/CHAT_CONTRACT.md`](docs/CHAT_CONTRACT.md).

---

## Review R1 closure

Separate commit on top of the reviewed head `438312e`, answering `PHASE1A_REVIEW_R1.md`. Earlier commits are unchanged. Where this section and the original report below disagree, this section is current.

**Reproductions first.** The new regression tests were run against the reviewed revision `438312e`, in a detached worktree with only the new test and fixture files copied in:
- **8 of 9 failed**, each on the defect itself:
  - F1: workspace rows still served after revocation
  - F2: `SourceUnavailable not raised` for a renamed store; a never-created store not reported
  - F3: `rebuilt` was `None` for both anchor-preserving replacements
  - F4: the cron-mirror row admitted
  - the binding purge was not applied while the source was down
- **The reassigned-id case**, once a constant that did not exist yet was replaced, failed with `None != 'source_identity_changed'`: the reassigned id was folded in as an edit under the old message id.
- **The ordinary-edit control passed.**

The same tests pass at the closure commit.

### F1: workspace revocation is enforced

`session_kind()` admits a registered workspace session only when `binding.workspace` is true. Otherwise it excludes it as `workspace_not_trusted`, and never relabels it as terminal. Terminal trust is independent, and the existing test that withdrawing terminal trust keeps the workspace still passes.

`test_revoking_workspace_trust_removes_workspace_content`:
- workspace owner and companion rows are indexed
- trust is revoked
- snapshot, history and changes cursors all answer `resync_required`
- after the sync only the terminal row is served
- the projection file holds no workspace text
- with both kinds of trust off, nothing is served

### F2: a missing store is an outage, not empty history

- **Indexed before, missing now:** `SourceUnavailable`, which the routes return as 503 `retryable`. The transaction rolls back, so the projection, its id and `as_of` are unchanged. When the same store is renamed back, old cursors continue with no rebuild (`test_a_missing_store_after_indexing_is_unavailable_not_empty`, and a route-level twin).
- **Never existed:** `source_state: "not_created"`, 200, empty. The first messages arrive as changes (`test_a_store_that_never_existed_is_an_empty_new_conversation`). Whether a store has ever been seen survives rebuilds, so a binding purge cannot turn an outage into "not created".
- **Stale-data policy:** `snapshot` and `changes` require a successful sync. `history` is served from the projection with `as_of`, the time of the last successful sync.
- **Binding changes don't wait for the source:** an owner-binding change is committed in its own transaction before the source is read, so revocation purges even during an outage (`test_a_revoked_binding_is_purged_even_while_the_source_is_down`).

### F3: an id reused for another message never inherits an old id

Each projected row now stores `source_fp` = hash(id, session_id, role, timestamp). The projection schema is v2, so older projections rebuild themselves.

Two checks:
- **Every apply:** in both the pull and reconciliation, a fingerprint mismatch raises `IdentityChanged`. It is never treated as an edit. The projection is rebuilt in the same transaction (`source_identity_changed`).
- **Every sync:** a bounded, evenly spread sample of up to 64 indexed rows is re-checked alongside the sequence and anchor (`source_replaced`).

Tests:
- the reviewer's counterexample, with the same sequence and the anchor preserved
- the missing-anchor variant
- a reassigned id outside the sample, served stale (not aliased) until reconciliation reaches it, then rebuilt with a new id and the new provenance
- the ordinary-edit control

The limit is stated in the contract: a replacement that keeps a row's id, session, role and timestamp and changes only its content is indistinguishable from an edit. Hermes has no store-instance id.

### F4: proactive delivery is reported unsupported; the owner boundary is structural

The installed schema offers no independent evidence of delivery:
- the outbox has no platform id
- the delivery mirror row has no outbox id, no platform id and no marker; its metadata is dropped at SQLite, and `finish_reason`/`token_count` are not established as a reliable model-reply marker

So:
- The gate is reported **not passed / unsupported** (`capabilities()['proactive delivery provenance']`).
- A companion row in a trusted session is shown as recorded, with `correlation: null`. No row is presented or counted as a verified delivered outreach.
- **The text-prefix rule is removed.** A Telegram **user** row is the owner only with the `platform_message_id` that Hermes records for every inbound gateway turn. Rows without one are excluded as `unverified_sender`. That covers the cron-brief mirror whatever its text, and older rows that predate the column. Source rows are untouched.
- The outreach test is rewritten to assert exactly this, and that `CRON_MIRROR_PREFIX` no longer exists.

**Decision for the reviewer.** The `unverified_sender` rule also excludes genuine owner Telegram messages written before Hermes recorded platform ids. Their number in any real history is unknown: no live store was read. Options:
- keep them out, the current default ("unknown identities stay out")
- add an explicit owner opt-in that admits them labelled as unverified

Nothing was added for this without a decision.

### Windows diagnosis, corrected

Job 107502858190 (run 35958848173, `a4ae50f`) ended 4 failed, 158 passed. All four failures were temporary-directory cleanup `PermissionError` / WinError 32 on SQLite files still open, in:
- `test_edits_and_deletions_change_revision_not_identity`
- `test_changing_the_owner_binding_stops_serving_what_it_authorised`
- `test_a_messages_table_without_stable_ids_is_unsupported`
- `test_fifty_thousand_messages`

These were fixed by closing the test connections in `db950d9`. The same commit made the reference SSE reader stop at `[DONE]`. That change is **additional hardening**: the log shows no SSE failure. The earlier CI note below overstated it.

### Closure commands and results

```text
env PATH=/usr/local/bin:/usr/bin:/bin TAMANITOMO_REQUIRE_NODE=1 .venv/bin/python -m pytest -q -rs
-> 1445 passed, 464 subtests passed, 0 skipped, 1 warning (existing Starlette/httpx deprecation)
python -X dev -W always::ResourceWarning -m pytest tests/test_chat_projection.py tests/test_chat_routes.py
-> 0 unclosed-database warnings
```

The identity sample raised a sync with nothing new from 0.6 ms to 7.9 ms at 50,000 messages. The other numbers are in the contract. These remain desktop, projection-only measurements.

**CI for the closure commit** `5fbc33c` (run 35982558665): all 5 jobs passed. `linux (3.11)`, `linux (3.13)` and `linux (3.14)` ran the full suite with Node required. `smoke (windows-latest)` and `smoke (macos-latest)` passed too, and these include the chat projection and mock-provider tests.

Unchanged by this closure: the UI, the legacy `/api/feed` (still over-inclusive), and the send path. There was no browser, phone or live testing. The Phase 0 review document `ASTRA_PHASE0_REVIEW_R2.md` is still not available here; no compliance with its unseen contents is claimed.

---

## What was found (1A.1)

These are read from the installed Hermes source (`~/.hermes/hermes-agent` at `0e9fc2cc15`, `SCHEMA_SQL` schema_version 30). The column set used in `tests/chat_fixtures.py` was compared programmatically against it and is identical for `sessions` and `messages`.

1. **Message identity.** `messages.id` is `INTEGER PRIMARY KEY AUTOINCREMENT`, so it is usable within one database file.
   - A restored backup or replaced file has to be detected (AUTOINCREMENT sequence plus an anchor row).
   - `replace_messages()` re-inserts turns under new ids. That is projected as deletions and inserts, not merged by text.
2. **Identity fields.** Sessions carry `user_id`, `chat_id` and `chat_type` (`dm`/`group`/`channel`/`thread`). Older rows can lack `chat_type`; Telegram's private-chat rule `chat_id == user_id` covers them.
3. **Visibility markers.** Hermes has structural markers: `display_kind` (with values `hidden`, `internal_notification`, `auto_continue`, `model_switch` and `async_delegation_complete`), `_compressed_summary` and `active`/`compacted`. Reasoning lives in separate columns.
   - The legacy feed excluded only `internal_notification`. The new adapter admits only rows where `display_kind` is empty.
4. **Delivered outreach cannot be linked.**
   - `companion_outbox` records `sent` without the platform message id that `hermes send --json` returns.
   - Hermes's delivery mirror row has no outbox id: mirror metadata is dropped at the SQLite boundary.
   - So an outbox entry is never joined to a transcript row. The mirror row appears as the companion on Telegram, with `correlation: null`.
   - The fix is to record `message_id`/`mirrored` at dispatch. That changes the send path and belongs to 1B.
5. **Cron briefs look like the owner.** Hermes mirrors cron briefs into chats as `role="user"` rows, marked only by a `[Cron delivery: …]` text prefix. Such rows are shown with `speaker: unverified`, not `owner`. This is a text-based attribution guard, and it is labelled as one.
6. **Edits and reply links.** Hermes does not record Telegram edits of past messages or reply-to links.
7. **Other channels.** Discord and Signal (and every other gateway) have `platform_message_id` and origin fields, but their DM and identity semantics were not verified. They are excluded as `unverified_source:<name>`.

## Delivered

| File | What |
|---|---|
| `kit/app/chat_sources.py` | `OwnerBinding` (owner file, or a single-entry `TELEGRAM_ALLOWED_USERS`, else none); `HermesSource` (read-only, profile-scoped, structural classification); `capabilities()` |
| `kit/app/chat_projection.py` | `ChatScope`; `Projection` (the SQLite projection, sync, reconcile, snapshot/history/changes, signed scoped cursors) |
| `kit/app/chat_routes.py` | `GET /api/chat/snapshot`, `/history`, `/changes`, `/sources` |
| `kit/app/server.py`, `manage.py` | two-line registration; `_attach_media` exposed on `app.state` for reuse |
| `tests/chat_fixtures.py` | Hermes-schema store builder, with the column set pinned and verified |
| `tests/mock_provider.py` | OpenAI-compatible SSE provider on 127.0.0.1, per-run token, 11 scenarios, `hermes_config()` with no fallbacks |
| `tools/preview_fixture.py` | seeds a synthetic conversation; `--mock-provider` |
| `docs/CHAT_CONTRACT.md` | contract, API, capability table, bounds, measurements |
| `.github/workflows/test.yml` | smoke job also runs the projection and provider tests |

The existing Chat UI, `POST /api/chat`, `/api/feed` and `/api/sessions/{id}` are unchanged. A route test pins the feed's response shape.

## Acceptance gate

| Requirement | Test |
|---|---|
| Trusted workspace/terminal and authorised Telegram together | `BoundaryTests.test_trusted_workspace_terminal_and_telegram_appear_together` |
| Foreign participant, other profile, group, unverified channel, cron/subagent excluded | `test_strangers_groups_other_profiles_and_machinery_stay_out`, `test_the_same_account_is_not_trusted_by_its_display_name` |
| Internal prompts/reasoning/tools/summaries/notifications excluded | `test_internal_rows_are_not_conversation` (reasoning values never appear in the payload) |
| Identical text, distinct ids, stays distinct | `IdentityTests.test_identical_text_with_distinct_ids_stays_distinct` |
| Replay with the same source identity is one message; an old replay cannot resurrect | `test_replay_of_the_same_source_identity_is_one_message`, `test_a_replayed_old_event_does_not_resurrect_edited_or_deleted_content` |
| History ties | `OrderingTests.test_identical_timestamps_page_with_a_stable_tie_breaker` (7 equal timestamps, pages of 2) |
| Snapshot race | `test_a_message_arriving_after_the_snapshot_arrives_as_a_change` |
| Backdated arrival | `test_a_backdated_import_is_a_change_today_and_history_yesterday` |
| Edits and deletions | `test_edits_and_deletions_change_revision_not_identity` (content edit, row deleted, row deactivated); `test_reconciliation_is_bounded_per_call_and_resumes` |
| Restart | `test_ids_survive_a_restart`; `test_an_interrupted_sync_leaves_the_last_consistent_state` |
| Rebuild / source restore invalidates cursors | `ResyncTests.test_a_replaced_source_store_invalidates_old_cursors`, `test_an_older_backup_restored_is_detected_by_its_sequence` |
| Retained changes no longer cover the cursor | `test_changes_older_than_the_retained_window_require_a_resync` |
| Another companion's cursor | `test_one_companions_cursor_is_refused_for_another` (plus a forged signature); route-level cross-profile check in `test_chat_routes.py` |
| Owner-binding revocation | `test_changing_the_owner_binding_stops_serving_what_it_authorised` (projection holds no copy afterwards); route: 409 |
| Delivered outreach vs internal cron output | `test_delivered_outreach_is_distinguished_from_cron_output` |
| Source files byte-for-byte unchanged | `SourceSafetyTests.test_source_files_stay_byte_for_byte_unchanged` (state.db, outbox, session registry; no journal/WAL beside the source; projection 0600, outside the source home) |
| Source unavailable is recoverable | `test_an_unreadable_source_is_a_recoverable_error`, `test_a_messages_table_without_stable_ids_is_unsupported`; route: 503 `retryable` |
| Current Chat UI and sending tests still work | full suite below (`test_workspace`, `test_feed`, `test_reliability` incl. its chat/browser-script regressions) |
| 50,000-message payload and indexed reads | `ScaleTests.test_fifty_thousand_messages` |
| Mock provider scenarios | `tests/test_mock_provider.py` (9 tests: delayed first delta, multiple deltas, public vs non-public fields, UTF-8 split mid-character and one byte per write, completion, truncation, malformed, disconnect before/after completion, recovery, determinism, token, loopback-only, no fallbacks) |

## Measurements (50,000 synthetic messages)

Linux (CachyOS, kernel 7.2), Python 3.14.7, local SSD. Single run from the scale test's `SCALE` line:

| | |
|---|---|
| initial indexing | 1.44 s, split over 3 bounded calls (≤ 20,000 rows each) |
| snapshot, 60 messages | 0.6 ms, 26,135 bytes JSON |
| history page, 60 | 0.3 ms (query plan: `SCAN messages USING INDEX messages_history`) |
| sync with nothing new | 0.6 ms |
| full reconcile | 0.49 s (normal calls reconcile ≤ 10,000 ids, at most every 30 s) |
| projection file | 21 MB (it holds a copy of public text) |

No phone-class measurement was taken. The bounds are there for that case, but the numbers above are from a desktop.

## Commands and results

```text
# at the Phase 1A working tree (no hermes on PATH, Node required)
env PATH=/usr/local/bin:/usr/bin:/bin TAMANITOMO_REQUIRE_NODE=1 .venv/bin/python -m pytest -q -rs
-> 1436 passed, 464 subtests passed, 0 skipped, 1 warning (existing Starlette/httpx deprecation)

.venv/bin/python -m pytest -q tests/test_chat_projection.py tests/test_chat_routes.py tests/test_mock_provider.py
-> 39 passed

python tools/build_release.py --output <scratch>/p1a.zip -> built, 292 source files (not published)
```

Environment: Python 3.14.7 (repo venv), Node 26.7.0.

**CI**:
- Run 35958848173 on `a4ae50f`: Linux ×3 and macOS passed. **Windows smoke failed** in the ledgers/locks step, which now includes the chat tests. The log was not readable from here. Two Windows-only hazards were fixed in `db950d9`:
  - test SQLite connections opened with `with sqlite3.connect()` were never closed, so temp-dir cleanup cannot delete them (reproduced locally as `ResourceWarning`, now 0)
  - the reference SSE reader read past `[DONE]` into the server's abrupt close
- Run 35959348237 on `db950d9`: **all 5 jobs passed**. That is `linux (3.11)`, `linux (3.13)` and `linux (3.14)` on the full suite with Node required, plus `smoke (windows-latest)` and `smoke (macos-latest)`, which now include `test_chat_projection.py` and `test_mock_provider.py`.

## Known limits and open questions

1. **Delivered outreach is unlinked** (finding 4). It is visible only as Hermes's mirror row. A delivery whose mirror failed does not appear. Proposed for 1B: store `message_id` and `mirrored` from `hermes send --json` in the outbox `sent` update.
2. **The cron-brief attribution guard is text-based** (finding 5). It only lowers attribution to `unverified`; it never hides a row. The structural fix belongs upstream in Hermes.
3. **Transcript rewrites** (`replace_messages`) show as deletions plus inserts.
4. **The workspace session registry keeps its last 400 sessions.** An older workspace session is then classified as `terminal`, or excluded if the terminal is not trusted. Its `source_kind` is not re-labelled in place.
5. **Owner binding.** The default Telegram binding comes from a single-entry allow-list. There is no UI for the binding file yet. Should Phase 2 add one, or should the allow-list rule be dropped?
6. **The legacy `/api/feed` still includes groups and unbound accounts.** It was left unchanged on purpose. Switching the Chat UI to this contract (Phase 2) is where that tightens, explicitly.
7. **Deltas.** Hermes persists no stream deltas, so every source reports completed messages only. The mock provider is not yet wired to a Hermes run; that is the Phase 2 integration test it exists for.
8. **Verification scope.** Fixture-only: nothing was live-tested and there was no real-browser run. Node VM and HTTP tests are not a browser acceptance run. Windows/macOS coverage comes from the CI smoke jobs.
