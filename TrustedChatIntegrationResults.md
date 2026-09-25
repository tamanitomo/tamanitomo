# Trusted Chat integration: results

**Branch:** `test/chat-trusted-read-integration`, local only (not merged or pushed). It is a child of the accepted
`test/persistent-chat-ui`.
**Verified base:** `40b8608a97ed209dbebfcb529ea30c93d4d1b738`. The worktree was clean and the index empty. There were no
later owner commits. `stash@{0}` (WIP on main) was preserved and not applied. `~/projects/companion-kit` is a
symlink to the same repository.
**Tested implementation:** `c7b09c2` (tree `c5590ae1…`). The worktree was clean before and after the evidence runs.
**This report and `docs/trusted_chat_evidence/`:** a later report-only commit.

Keyed activation stays **OFF**. Everything here is served only by `chat_sends=Options(client=True)`, and no shipped
entry point sets that. Nothing is added to `release-files.json`. There is no version bump and no push, merge, release
or deployment. No live profile, credential, model, platform or dispatcher was used.

## What changed

**A. Trusted reads in the enabled client** (`chat-controller.js`, `chat-store.js`, `chat-view.js`)
- **Where rows come from.** Newest and older pages come from `GET /api/chat/snapshot` and `GET /api/chat/history`,
  not `/api/feed`. A small adapter (`PersistentChat.adapt`) maps each projected message to the row shape the renderer
  already draws. The channel comes from `source.kind`.
- **Identity.** Row identity is `m:<message_id>`. Equal text is never merged. A send's parts are reconciled only by
  source identity (session + Hermes row id), or by the read's own `correlation.send_id`.
- **Paging.** The existing bounded 60-row paging and scroll anchors are unchanged.
- **Failures.**
  - A `503` is shown as unavailable, with earlier rows kept and marked "read earlier". It is never shown as an empty
    conversation.
  - `409 resync_required` or `400 invalid_cursor` on an older page causes **one** fresh snapshot.
  - A changed `projection_id` replaces the rows.
  - The draft and the pending intent are not touched by any read path.
- **Compatibility.** `/api/feed` and the ordinary client are unchanged.

**B. Continuation eligibility on the server** (`chat_send_routes.py`, `chat-sends.js`)
- **Shared predicate.** `Integration.eligible_kind` is now used by both `authorize_session` (keyed acceptance) and a
  new read-only `GET /api/chat/continuation[?session=]`. That route is registered with the keyed routes only.
  - It returns `current {session, eligible, kind?}` and `suggestion`: the most recently active eligible workspace or
    terminal session. "Most recently active" means the latest message timestamp, otherwise `started_at`; ties go to
    the higher session id. At most 200 local-source sessions are scanned.
  - It creates no ledger, starts no turn, writes no source row and returns no content.
  - The contract is in `docs/CHAT_CONTRACT.md` §8.8 and the §8.1 table.
- **Client policy.** It runs before an intent exists (`continuation()` in `chat-sends.js`, called from
  `startIntent`):
  1. A saved, still-eligible session is kept. A completed send's `result.session` becomes the saved session.
  2. With nothing saved, the suggestion is used and saved.
  3. With no suggestion, the send uses `session: null` and the page says "Your first message starts a new session."
  4. A saved session that is no longer eligible is **not replaced**. Nothing is posted and the draft stays. The log
     offers **Start a new session**, or **Continue the most recent conversation** when a suggestion exists.
  5. `400 unauthorised_session` at acceptance (authorisation changed after the check) shows "Not sent", puts the
     message back in the box and shows the choice.
  6. A stored intent never changes. There is no fallback to `POST /api/chat`.
- **Scope.** The selection is stored per installation/profile in `sessionStorage` (`chat-continuation-…`). The global
  `chatSession` is no longer the source of an intent's session. It is still written for compatibility, and a bare
  script harness without the store still uses it.
- **Route path.** The route is deliberately **not** under `/api/chat/sends/`. The accepted reviewer browser test
  `test_receipt_outage_does_not_forget_an_accepted_intent` fails every `/api/chat/sends/*` read except bootstrap,
  treating them as send-id reads. A first placement at `/api/chat/sends/continuation` broke that test, so it was moved.
  No reviewer file was changed.

**Preview.** `tools/preview_fixture.py --persistent-chat` no longer seeds the favourable `web-evening` session. On
the unmodified mixed fixture, the legacy feed still picks `gw-cli`, and the preview sends into `term` (the eligible
terminal session).

**Unchanged:** the ledger, the execution protocol, quiescence/containment, the dispatcher, reflection, prompts, the
Hermes schema, `/api/feed` and the default page.

## Acceptance checklist

| # | Check | Evidence | Result |
|---|---|---|---|
| 1 | Mixed-history reads | `test_chat_trusted_browser::MixedHistory::test_1_…`: the page and the dock show the trusted workspace, terminal and Telegram rows. Stranger, group and cron markers are absent through the newest page and every older page (70 extra rows; start reached). Three `hi` bubbles have three distinct `m:msg_…` keys. No `GET /api/feed`. The `state.db` sha256 is unchanged and there are no sends. HTTP: `test_chat_trusted_integration::Mixed::test_trusted_reads_…` pages in 3-row steps with the same assertions, plus the source digest | pass |
| 2 | Continuation without the favourable seed | Browser: the `gw-cli` fixture sends via `term` (1 send, 1 launch, POST session `term`). An ineligible saved `gw-cli` gets no POST and no intent, and the draft stays in the box and in storage. Then **Start a new session** gives POST session `null`, 1 launch, and the created session becomes current. **Continue the most recent** gives `term`. A race (binding withdrawn between check and POST) gives 1 POST, `400`, nothing accepted, the message back and the choice shown. A new profile states the new-session state, then continues its created session (`[null, created]`, 1 launch each). HTTP: the legacy feed still picks `gw-cli` and acceptance refuses it. Continuation refuses `gw-cli`, `job`, `sub`, `stranger`, `group`, `dc`, `tg`, `tg-old`, `rowan-tg` and unknown ids even when they are newest. It is read-only (no ledger, same source digest, not busy). Workspace-trust withdrawal and the POST race are refused. An unreadable store gives `503`. Profiles are isolated. It is `404` without keyed sends | pass |
| 3 | Core UI stays useful | `MixedJourneys` reruns the 10 accepted journeys (`test_persistent_chat_browser.Journeys`) unchanged on the mixed `gw-cli` fixture: send → Vault → dock → reply → maximise; view changes; reload; profile switch; lost response; sign-in expiry; narrow layout; paging/anchors; no legacy POST. The original `Journeys` on empty profiles also pass | pass (emulated mobile) |
| 4 | Recovery and isolation | New: nova's selection is never used for rowan. A snapshot `503` mid-turn keeps rows, the pending key and the newer draft, then completes with 1 launch. A history `409 resync_required` mid-turn causes exactly one fresh snapshot and keeps key, draft and one presentation. Existing: C3 browser (16), C3 recovery browser, reviewer browser (6), C3 Node recovery checks (reviewer 8/8, closure 6/6) and the HTTP witness | pass |
| 5 | Default compatibility and preview | `test_phase1b_c3_disabled.py` (default and routes-only pages byte-identical to `index.html`, new files not shipped), `DefaultPage`/`RoutesOnlyPage`, `test_preview_fixture.py` (no workaround; the legacy feed picks `gw-cli`; a keyed send via the suggestion completes into `term`). The actual preview entry point was driven in Chromium: trusted rows shown, excluded rows absent, POST session `term`, no "Not sent", no `/api/feed` read, data directory removed on SIGTERM | pass |

## Commands, counts, skips

Environment: Python 3.14.7, Node v26.7.0, Playwright 1.63.0, Chromium 153.0.8010.12 (`environment.json`). `PATH=/usr/bin:/bin` (Hermes not on PATH),
`TAMANITOMO_REQUIRE_NODE=1 TAMANITOMO_C3_REQUIRE_BROWSER=1`, and `TMPDIR` set to job scratch, because this host's
`/tmp` is 100% full.

| Run at c7b09c2 (my executions) | Result |
|---|---|
| `pytest tests/test_chat_trusted_integration.py tests/test_phase1b_c1_integration.py tests/test_chat_routes.py tests/test_preview_fixture.py` (`trusted_http`) | **56 passed**, 2 subtests |
| `pytest tests/test_chat_trusted_browser.py tests/test_persistent_chat_browser.py tests/test_phase1b_c3_browser.py tests/test_phase1b_c3_recovery_browser.py tests/test_c3_review_browser.py` (`browser`: new 19 = 9 MixedHistory + 10 MixedJourneys; accepted 12 + 16 + 4 + 6 unchanged) | **57 passed**, 8 subtests, 0 skipped |
| `pytest tests/test_phase1b_c3_recovery.py tests/test_phase1b_c3_disabled.py tests/test_reliability.py` (`c3_and_default`: reviewer Node 8/8, closure Node 6/6, HTTP witness, default/routes-only pages) | **42 passed**, 33 subtests |
| Ordinary full suite `pytest tests/` (once, final tree) | **1764 passed, 51 skipped, 0 failed**, 641 subtests (was 1732; +32 new) |
| Actual preview entry point driven in Chromium (`preview_run.json`) | POST session `term`; no Not sent; no `/api/feed`; data removed on SIGTERM |

The 51 skips are all pinned-Hermes-only (`pinned_skips.txt`): 24 in `test_phase1b_c0_receipts.py`, 27 in
`test_phase1b_c1_pinned.py` ("pinned Hermes not configured").

The real-Hermes pinned lane was **not** rerun. Its path (executor, protocol, receipts, ledger) is unchanged. The only
backend change is the `authorize_session` refactor onto the shared predicate, which the C1 integration tests cover
(`test_admission_refusals_change_nothing`, `test_a_resumed_workspace_session_is_authorised_by_the_current_binding`).

**Test changes.** New: `tests/test_chat_trusted_integration.py` and `tests/test_chat_trusted_browser.py`.
`tests/test_preview_fixture.py` now expects the legacy feed's `gw-cli` rather than the removed `web-evening` seed,
and proves a keyed send through the suggestion. No other existing test changed.

## Reviewer results vs mine

Everything above is my own execution at `c7b09c2`. The reviewer's earlier results (45 tests with 33 subtests; the
preview entry point served and cleaned up; the browser journeys inspected but not rerun because Chromium was blocked)
refer to `40b8608` and are not restated as results for this commit.

## Known limitations and separately tracked items

- **The suggestion may be a terminal session.** On the mixed fixture the most recently active eligible session is the
  terminal `term`, so the preview's first send continues there. After a reload, that history row is badged
  **Terminal**, which is true of where it was sent.
  - Preferring workspace sessions over terminal ones is a policy question. It is not decided here; the handoff asks
    for "workspace or trusted terminal" by recency.
- **Choice after a refused POST.** After an acceptance refusal, the choice first shows only **Start a new session**.
  The suggestion appears on the next continuation check (the next send attempt or Chat open).
- **Stale older rows.** Rows in already-loaded older pages that are later deleted stay until a full reload or resync.
  There is no changes feed, by design (no event transport in this task).
- **Missing timestamps.** `occurred_at: null` draws as the epoch day. The legacy feed had the same behaviour with a
  missing timestamp.
- **Earlier limitations still apply:** duplicate owner row between reload and settlement (C1 link timing), native
  phones not tested, and daylight screenshots switched by attribute.
- **Not in scope:** Phase 1C context, cross-channel model awareness, event/notification transport, Journal/Vault
  redesign, containment, compression identity, production activation.

## Evidence

`docs/trusted_chat_evidence/` was exported by `tools/evidence_export.py --kind executed`: 13 files, all validated,
with home paths, job paths and the host name redacted (`--forbid` checked), plus `MANIFEST.json`. The JUnit XML is re-parsed by the
exporter (56 / 57 / 42 cases, all passed). `screens/` holds two synthetic preview screenshots, copied unmodified:
the ineligible-session choice with the draft kept, and a send into the eligible session. Neither shows a token or a
path.
