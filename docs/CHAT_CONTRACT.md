# Conversation read contract (Phase 1A)

This covers reading the owner's private conversation. Sending is unchanged (`POST /api/chat`); the Phase 1B keyed-send integration exists on the test branch but is not activated (section 8). Continuity across reflection and Hermes context is Phase 1C. No dock, push or live transport is part of this phase.

Code:
- `kit/app/chat_sources.py`: read-only adapters and the owner binding
- `kit/app/chat_projection.py`: the app-owned index and the read contract
- `kit/app/chat_routes.py`: the HTTP routes

## 1. The boundary

A private conversation is **one owner and one companion (profile) on one Hermes installation**, across sources the owner trusts. It is not "every `role='user'` row in the profile".

| Source | Included when | Identity comes from |
|---|---|---|
| workspace | a `cli`/`desktop`/`tui` session this app started, and `workspace` trusted in the binding | the app's session registry (`.tamanitomo-sessions.json`), written at send time |
| terminal | a local `cli`/`desktop`/`tui` session with no gateway `chat_id`, not started by this app, and `terminal` trusted in the binding | host provenance: only local processes write these sessions |
| telegram | `sessions.user_id` is a bound Telegram account **and** the session is a DM (`chat_type='dm'`, or `chat_type` empty with `chat_id == user_id`, which is Telegram's private-chat rule). An owner (user) row also needs the `platform_message_id` Hermes records when it receives a platform message | the owner binding, plus the platform receipt id for each owner row |

Workspace and terminal trust are independent. With workspace trust withdrawn, a registered workspace session is excluded (`workspace_not_trusted`); it is never relabelled as a terminal session. With terminal trust withdrawn, the workspace is unaffected.

Everything else is excluded and counted by reason (`/api/chat/sources`, and `excluded` in each snapshot):
- `unknown_participant`
- `group_or_channel`
- `unverified_source:<name>`: Discord, Signal and every other gateway
- `internal_session`: cron, subagent, tool, audits
- `local_source_with_gateway_chat`
- `workspace_not_trusted`
- `terminal_not_trusted`
- `unverified_sender`: a Telegram user row without a platform message id (see section 2)

A group message is excluded even when the owner wrote it. A reply to a stranger or into a group is excluded with its session. Nothing is matched by display name or message text.

**Owner binding** (`owner_binding()`), in order:
1. `<profile home>/.tamanitomo-chat-owner.json`, for example `{"workspace": true, "terminal": true, "telegram": ["123456"]}`
2. `TELEGRAM_ALLOWED_USERS`, only when it names exactly one account
3. no Telegram identity at all. Several allowed users do not say which one is the owner.

The binding's origin is reported with every snapshot.

**Scope** is captured once per request, before any read: installation, profile, resolved profile home, and binding digest (`ChatScope`). `conversation_id` = hash(installation, profile home). The projection records the binding digest. When the binding changes or is revoked, the projection is rebuilt on its next write and every read refuses old cursors (`resync_required`). Content authorised only under the old binding is not served again.

## 2. Public messages only

The adapter filters rows by Hermes's own structural markers, never by stripping text. A row is public only when all of these hold:
- `role` is `user` or `assistant`
- `display_kind` is empty (this excludes `hidden`, `internal_notification`, `auto_continue`, `model_switch` and `async_delegation_complete`)
- `_compressed_summary = 0`
- it is `active`, or is a `compacted` original
- it has non-blank `content`

Tool rows, tool-call-only assistant rows and every reasoning column are never read into the projection. A row that stops qualifying after it was shown (deleted, archived or hidden) becomes a **deletion**.

**Proactive delivery is unsupported in 1A** (review R1 F4). The requirement is that a delivered proactive message appears only through verified delivery linkage. No source this phase can read provides that linkage:
- `companion_outbox` marks an entry `sent` without the platform message id that `hermes send --json` returns. *(Phase 1B C2, not yet reviewed: the dispatcher now records that id, scoped to the last chunk of a split or media send. That alone links nothing, because the mirror row below still carries no id.)*
- Hermes's delivery mirror row (`gateway/mirror.py` → `append_message(session_id, role, content)`) has no outbox id and no platform id. It carries no marker that tells it apart from a model reply; the mirror metadata is dropped at the SQLite boundary.
- `finish_reason`/`token_count` are not a proof either. Nothing establishes that they are set on every model reply.

So the boundary is:
- Output of a cron (or any internal) session is never conversation.
- No outbox entry is projected, and none is joined to a transcript row, by text or otherwise. Queued, withheld, failed and expired entries never appear.
- A **companion** row in a trusted session is shown as that session's transcript recorded it, with `correlation: null`. No row is labelled or counted as a verified delivered outreach, whether it came from a model reply or a delivery mirror, and the gate stays **not passed**.
- An **owner** row in a Telegram session must carry the `platform_message_id` that Hermes records for every inbound gateway turn (`gateway/run_turn.py`). Without one, the sender of a user row is not established under this adapter's rule. That covers the cron-brief delivery mirror, which Hermes writes as `role="user"`, and genuine owner messages written before the column existed: a missing id does **not** prove the owner never sent the message. Such a row is excluded from the trusted conversation as `unverified_sender`; the source row is kept and the exclusion counted. A future opt-in archive view could show such rows labelled unverified, but that is a separately reviewed visibility feature: showing a row would not make it trusted owner evidence, reflection input or model context. This is structural, not a text-prefix match, and the source row is untouched.

Recording the delivery id at dispatch would make proactive delivery verifiable. That is a send-path change and belongs to Phase 1B. **(C2)** The id is now recorded; proactive delivery stays **unsupported** in the reads, because Hermes's mirror row still has no id to join on and joining by text or time is forbidden (`PHASE1B_DESIGN.md` §7.7). The capability text served by `kit/app/chat_sources.py` still describes the pre-C2 outbox and is a separate follow-up (`Phase1B_C2_Results.md` §6).

**Attachments** are resolved at read time through the existing media catalog (`_attach_media`), so review status and authorisation are unchanged. Nothing is fetched remotely.

## 3. Identity, revisions, generations

| Field | Meaning |
|---|---|
| `message_id` | Opaque: `msg_` + hash(conversation, projection generation, source key). Stable across syncs and restarts of one projection. |
| `source` | `{kind, account, channel, session, message}`. `message` is Hermes `messages.id` (AUTOINCREMENT, never reused within one file). |
| `speaker` | `owner` / `companion`. `role` is kept for compatibility. |
| `occurred_at` | Hermes `timestamp`; `occurred_at_known` is false if absent (history then sorts by first observation). |
| `observed_seq` | App-owned change sequence of the latest change to this message. |
| `revision` | 1 on insert, +1 on every edit, delete or restore. Identity never changes. |
| `status` | `public` / `edited` / `deleted` (a deleted message has `content: null`, and the projection keeps no copy of it). |
| `reply_to` | Always `null`: Hermes stores no reply link. |
| `correlation` | `{platform_message_id}` when Hermes stored one (Telegram user turns); otherwise `null`. Outgoing provisional/final correlation is reserved for 1B. |

**Source identity and generation** (review R1 F3, R2). Every projected row stores a fingerprint of what must not change for a source row to still be the same message: `(id, session_id, role, timestamp)`, plus its known `platform_message_id`. Content may change; that is an edit.

**Platform message ids** (review R2). Telegram numbers a message within its chat, so an id is compared only for the same source row, whose session fixes the account/chat. It is never matched across chats: the same bare id in two chats is two messages.
- **Known -> a different known id:** a different message. Never an edit or a replay, even with identical text (`source_identity_changed` / `source_replaced`). The new content never inherits the old correlation.
- **Missing -> known:** enrichment. The same message gains `correlation`, as a new revision (`edit`).
- **Known -> missing:** the stored id is kept, not erased, so a later different id still conflicts with it. For a Telegram owner row, losing the id also makes it `unverified_sender`, so it is projected as deleted; it is not restored under its old id if a different id appears. Hermes has no store-instance id (checked in `state_meta`), so continuity rests on these checks:
- **Every apply.** When a source id is read, in the incremental pull or in reconciliation, its fingerprint and platform id are compared with the stored ones. A mismatch means the id now names a different message. It is never folded in as an edit (`source_identity_changed`).
- **Every sync.** An evenly spread sample of up to 64 indexed rows is re-checked. So is the AUTOINCREMENT sequence (it must not go backwards) and the anchor row (it must not hold a different row or a different known platform id). Any failure means `source_replaced`. A missing row is a deletion, not a replacement, and a missing anchor is replaced by a new one.

Either result rebuilds the projection in the same transaction, with a new `projection_id` and generation. Old cursors answer `resync_required`, and no old opaque id is ever given to a different message.

A replaced row outside the sample is found when reconciliation reaches it (at most 10,000 ids per call, every 30 s). Until then the old message is served as last read: stale, never aliased.

Limit: a replacement that keeps a row's id, session, role, timestamp and platform id (or has none) and changes only its content cannot be told apart from an edit.

A Hermes `replace_messages()` (a transcript rewrite) gives surviving turns new ids. It is projected as deletions plus inserts, not as the same messages; this is a documented limit, and nothing is merged by text.

**Replays.** Records are keyed by source identity, so re-reading or re-pushing the same row is one message and no change. A push-style record may carry `source_revision`; one older than the applied revision is ignored, so a replayed old event cannot resurrect edited or deleted content.

**Edits.** Hermes has no revision column and does not record Telegram edits of past messages. An edit is observed only as changed content of the same id.

## 4. Reads

History order is `(occurred_at, message_id)`. Change order is `observed_seq`. The two are different questions: when something was said, and when the app learned it.

```
GET /api/chat/snapshot?limit=60        (1-200)
-> {conversation_id, projection_id, as_of, source_state, scope:{profile, installation, owner_binding},
    messages:[...oldest→newest...],
    history:{before: cursor|null, start_reached, start_note},
    changes:{after: cursor, high_water}, excluded:{reason:count}, sync:{...}}

GET /api/chat/history?before=<history cursor>&limit=60
-> {conversation_id, projection_id, as_of, messages, history:{before, start_reached}}

GET /api/chat/changes?after=<changes cursor>&limit=200   (1-1000)
-> {conversation_id, projection_id, as_of, changes:[{seq, kind: insert|edit|delete|restore,
    revision, message}], after: cursor, more}

GET /api/chat/sources -> capability table, binding origin, conversation_id
```

- **Snapshot** reads the page and the change high-water mark in one transaction. Every change after the mark is newer than the page, which closes the race between fetching history and starting to follow changes.
- **Changes** carry each message's current state. Clients upsert by `message_id` and keep the highest `revision`. A backdated import arrives as a change and sorts into its historical place.
- **Cursors** are signed (HMAC with a per-projection secret) and carry the conversation and projection ids.

Errors:
- **400 `invalid_cursor`:** the cursor is malformed, forged, belongs to another conversation or companion, or the limit is out of range.
- **409 `resync_required`**, with a reason:
  - `projection_rebuilt`: a rebuild, a source replacement or a binding change
  - `changes_expired`: the cursor is older than the retained window of 10,000 changes

  Load a new snapshot. This is never "no new messages".
- **503 `source_unavailable`** (`retryable: true`) from `snapshot` and `changes`: the store is locked, corrupt, of an unknown schema (including a messages table with no `id`), or **missing after it was once indexed**. Nothing is changed, and the projection is not reset (review R1 F2). When the same store comes back, old cursors continue.

**A store that never existed** is a new companion with no conversation yet. `snapshot` returns 200 with no messages and `source_state: "not_created"`, and the first messages arrive as changes. Whether a store has ever been seen survives rebuilds.

**Stale data.** `snapshot` and `changes` succeed only after a successful sync. `history` pages are served from the projection without contacting the source, and every response carries `as_of`: the time of the last successful sync. During an outage, older pages remain readable and say how old they are.

An owner-binding change is applied and committed before the source is read. A revoked binding therefore purges what it authorised even while the source is down.

**Start of history.** `start_reached: true` means the earliest message the sources still hold. A message a source has deleted is not recoverable by scrolling.

The legacy `GET /api/feed` and `GET /api/sessions/{id}` are unchanged. They still include every non-internal source, groups and unbound accounts among them. Moving the Chat UI onto this contract, which tightens that, is Phase 2 and will be explicit.

## 5. The persistent file, and its costs

**Location and contents.** One SQLite file per installation and profile, at `<app state>/chat/<installation>/<hash of profile home>.sqlite3`. The installation directory is mode 0700 and the file 0600 (POSIX); a symlinked file is refused. It holds tables `meta`, `messages` and `changes`, with a copy of public content only.

**Why it exists.** Stable ids, revisions and a change sequence need somewhere to live that is not Hermes's database. This file is not a second authority: it is rebuilt from the sources whenever its schema, scope, binding or source generation differs, and it can be deleted at any time.

**Interrupted writes.** A sync is two `BEGIN IMMEDIATE` transactions: the binding/scope check, then the source read. A crash rolls back to the last consistent state (tested).

**Indexing bounds** (for phone-class hosts):
- **Pulling new rows:** at most 20,000 source rows per request, in batches of 5,000.
- **Reconciling:** checks at most 10,000 source ids for edits and deletions per request, and only every 30 seconds. It resumes where it stopped.
- **Initial indexing:** a large history is spread over several requests (`sync.caught_up`).
- **Reads:** history pages are an index walk (`messages_history`); nothing downloads all history.

No polling runs in the background. Work happens only when `snapshot` or `changes` is requested.

Measured on 50,000 synthetic messages (Linux, Python 3.14, SSD; `tests/test_chat_projection.py::ScaleTests`):

| | |
|---|---|
| initial indexing | 1.69 s over 3 bounded calls |
| snapshot (60 messages) | 0.6 ms, 26 KB JSON |
| history page (60) | 0.3 ms |
| sync with nothing new | 7.9 ms (includes the 64-row identity sample) |
| full reconcile | 0.65 s |
| projection file | 22 MB |

These are desktop measurements of the projection alone. They are not phone results, and not route/media-enrichment or rendered-UI measurements.

## 6. Capability table

"Fixture" means tested against a Hermes-schema `state.db` built with the installed Hermes's exact sessions/messages columns (schema_version 30, hermes-agent `0e9fc2cc15`). Nothing here is live-tested.

| | workspace | terminal | telegram | discord / signal / others | proactive delivery |
|---|---|---|---|---|---|
| Schema inspected | yes | yes | yes | not in this phase | yes (`companion_outbox`, Hermes `send`/mirror) |
| Owner / DM identity | app registry + binding | local session, no gateway chat + binding | bound `user_id` + DM rule; owner rows need `platform_message_id` | **unsupported** | n/a |
| Durable ids / lifecycle | `messages.id` per store generation | same | same (+`platform_message_id` on user turns) | n/a | outbox id, no platform id |
| Edits / deletions | content change / row gone or hidden | same | same; Telegram edits are not recorded by Hermes | n/a | n/a |
| Attachments | `MEDIA:`/image refs via media catalog | same | same | n/a | n/a |
| Deltas | completed messages only (Hermes persists no deltas) | same | same | n/a | n/a |
| Delivered proactive provenance | n/a | n/a | not verifiable; companion rows shown with `correlation: null` | n/a | **unsupported** |
| Tested | fixture | fixture | fixture | excluded (fixture) | fixture |

## 7. Synthetic provider

`tests/mock_provider.py` serves the provider transport (OpenAI-compatible SSE on 127.0.0.1 with a per-run token). The scenario is the request's `model` field:
- `deltas`
- `delayed_first_delta`
- `single`
- `mixed_fields` (reasoning and tool-call deltas beside public content)
- `unicode_split` (a 4-byte character cut across writes)
- `line_split` (one byte per write)
- `truncated`
- `malformed`
- `disconnect_before_done`
- `disconnect_after_done`
- `recover` (first request drops, second completes)

`hermes_config()` writes a synthetic home's config with no fallback model, `fallback_providers: []` and `transport_fallback: deny`. `tools/preview_fixture.py --mock-provider` starts it beside the preview workspace, which now also seeds a synthetic conversation.

The source-side fixtures are `tests/chat_fixtures.py` and the push records in `tests/test_chat_projection.py`. They cover edits, deletions, backdated imports, replay, two profiles and a foreign participant.

## 8. Keyed sends (Phase 1B C1 integration): NOT ACTIVATED

This section describes code that exists on the test branches and is **off** in every shipped build (C3's browser client included, §8.6). `kit/app/chat_send_routes.py` registers its routes only when the app is built with an explicit `chat_sends=Options(...)` (`kit/app/server.py`). No entry point passes it; no UI calls it; the new modules are not in `release-files.json`. The workspace still sends through `POST /api/chat`, which is unchanged. There is no fallback between the two paths: a send accepted on the keyed path is never retried as an unkeyed `POST /api/chat`.

Design: `PHASE1B_DESIGN.md` §4–§5. Results and the exact tests: `Phase1B_C1_Results.md`; the integration closure (F1–F3) and the Linux activation evidence: `Phase1B_C1_ActivationReadiness.md`; the public-output closure after review (R1–R4): `Phase1B_C1_PublicOutputClosure.md`, which is the current status.

### 8.1 Routes

| Route | Result |
|---|---|
| `GET /api/chat/sends/bootstrap` | `{conversation_id, generation}`; creates the ledger on first use. `503 send_ledger_lost / send_storage_unsupported / send_supervision_unavailable`, `409 ledger_busy` |
| `POST /api/chat/sends` `{client_key, generation, conversation_id, message, session}` | `202` accepted (or a `not_started` send re-armed), `200` replay of the receipt for this key (`replay: true`). `409 key_conflict / generation_changed / not_bootstrapped / ledger_busy / turn_in_progress / installation_busy`, `422 key_expired`, `400` invalid input, wrong conversation, unauthorised session, `503` as above |
| `GET /api/chat/sends/{send_id}` | receipt (recovery first) |
| `GET /api/chat/sends?key=K` | receipt, or `404` (a `404` while a POST is in flight means retry the same key, never a new one). Same links as the direct receipt under the same binding |
| `GET /api/chat/sends?open=1` | unsettled receipts, newest 20. Same links as the direct receipt under the same binding |
| `POST /api/chat/sends/{send_id}/stop` | receipt. A stop never makes a send `interrupted` by itself; the outcome comes from the executor's facts |
| `POST /api/chat/sends/ledger/reset` `{"confirm": "reset send ledger"}` | new `generation`. Without the exact confirmation: `400 confirmation_required`, nothing changes. `409 executor_live` while any managed execution is not proven quiescent |
| `GET /api/operations/{id}` for a send's reserved id | a view built from the ledger; while running, an authorised public `stream` snapshot; a keyed send the ledger cannot resolve: `status: unknown` (below) |

Every route captures its scope once, before any read or side effect: installation, profile, resolved home and owner binding. A `send_id`, key or operation id from another scope is `404`. Two profile homes are two ledgers: the same key sent to both is two sends.

A receipt carries `state`, `owner_turn`, `reply`, `correlation`, `capability`, `liveness`, `coverage`, `settled`, `error {code, message}` and `operation {id}`. While the **current** binding still authorises the send's source kind, it also carries `session`, `links` (`linked | lost | pending | unavailable`), `owner_message_id` and `reply_message_ids`. These are the opaque Phase 1A message ids of the rows whose identity fingerprint (id, session, role, authored time) still equals the one the executor receipted. Otherwise the receipt holds state and codes only.

### 8.2 One active turn, replay, admission

- One lease per physical profile home. A different key while a send holds it is `409 turn_in_progress`, and nothing is accepted.
- The same key and payload always replays the one receipt, whatever the lease, age or state. The exception is a definite `not_started` within 24 h, which is re-armed under the same `send_id`.
- In one app process, a running action on the installation also refuses new keys: `installation_busy`, or `turn_in_progress` when that action is this home's own send. This is today's in-process rule. The keyed routes are exempt from the request middleware's busy refusal so that a retry can replay and a stop can reach a running turn.
- Across processes, `<Hermes root>/.tamanitomo-installation.lock` (an OS lock) is taken briefly by acceptance. It is held for their whole duration by every other installation action (`Operations.submit` for any non-chat kind, and the native console). Before such an action starts, it checks every profile ledger under the root with the send quiescence contract. A running or unproven send refuses the action ("A chat reply is still running"); a running action refuses acceptance (`installation_busy`). The application's own update (`kind: application`) is not an installation action and is unaffected.

### 8.3 Operation records (format 2)

- A chat operation's id is reserved in the acceptance transaction. `GET /api/operations/{id}` for it is built from the ledger. A missing or stale operation file never implies a new send, and nothing on this route launches one.
- Status mapping: `accepted / launching / generating / stopping` → `running`; `complete`, `failed` and `interrupted` as themselves; `not_started` → `failed` ("The reply process was not started."); `unknown` → `interrupted` with its fixed sentence.
- The file holds only `id, scope, profile, kind, label, status, progress, percent, started_at, finished_at, send_id, error_code, error, format` and `result {session, send_id, note}`. `progress` comes from a fixed set, and `error` is the fixed sentence for `error_code`, never exception text, stderr or output. Streamed text and the reply stay in memory only.
- **A keyed operation never falls back to the legacy row.** The app marks a keyed send's operation (in memory, and by `format: 2` + `send_id` in its file). When the ledger cannot resolve it — unreadable (`error_code: send_ledger_unavailable`) or no longer holding the send after a reset or retention (`send_record_unavailable`) — the answer is `status: unknown` with the fixed sentence, `send: {state: unknown, ledger}`, `result: null`, and no prompt, reply, stream or session. This never claims the send ran, failed or never existed, and the read never resets, recreates or launches anything. The same id seen from another profile or installation is `404`. An id the app knows no keyed send for is answered by the legacy operation route as before (an unknown id is still `400 Unknown operation`).
- **Stream snapshot (polling).** While the send runs, the view carries `stream: {available: true, text, truncated}` — the public text streamed so far in this process, as a snapshot (never an append log), at most the last 100 000 characters. `<think>`/`<thinking>`/`<reasoning>` blocks are removed on the server **before anything is buffered**: each attempt's deltas pass through an incremental filter that remembers, across fragments, whether a block is open (and holds at most a few characters of a possible tag), so a withheld body is never stored and dropping old text can never expose one. `stream_text` repeats `stream.text` for the current poller. It is rechecked on every read: the send's kind must be authorised by the current binding (`reason: not_authorised`) and its sources verified (`sources_unverified`). After a restart, or from another app process, the buffer does not exist: `reason: not_retained`, never regenerated. Terminal views carry `result`, not `stream`. Nothing streamed is written to the operation file. This is HTTP polling only; no browser rendering of it is certified.
- Legacy clients get `result.response` and `result.messages` under the current authorisation, on both branches. `result.response` is the authorised linked final reply row when one is linked, otherwise this process's filtered transcript, and passes through the same public-output filter either way: a terminal state never reintroduces text withheld while running. `result.messages` are the Phase 1A projected rows, as the snapshot shows them. In the live process, the in-memory reply is returned only while the send's kind is authorised and its links still resolve. Otherwise the result is reconstructed from the linked rows through the Phase 1A projection. Failing both, `response: null, messages: [], content_retained: false`. A reply is never regenerated.
- Retention applies to terminal `format: 2` files only: removed when finished more than 7 days ago or not among the newest 500, at most 500 per pass, after each chat operation. Records without `format: 2` (pre-1B chat records containing text, and every other operation) are not touched and not described as removed.

### 8.4 What changes in the reads (section 4) when keyed sends are enabled

- **Workspace sessions from receipts.** A session the executor's committed receipts show it **created** (a fresh insert) for a workspace send is a workspace session, whether or not `.tamanitomo-sessions.json` names it. A resumed terminal session, and a continuation of one, is never relabelled.
- **`correlation.send_id`.** A projected row gets `{send_id, send_part: "owner" | "reply:<n>"}` only when the send belongs to this conversation, its kind equals the row's and is authorised now, its sources were verified, its receipted fingerprint equals the row's, and no known platform id conflicts. It is computed at read time, so it survives a projection rebuild. It disappears when the send is pruned (30 days after settlement).
- **Continuation notes (O-12).** A row that an executor proved to be Hermes's own `_length_continuation_nudge` note is excluded (`excluded.internal_turn_machinery`). The proof is the dict Hermes created, matched by object identity to the committed row, and the exclusion holds only while the row's fingerprint matches. A note already projected before its proof arrived is withdrawn on the next read as a `delete` change carrying `note: "internal_turn_machinery"`. The owner typing the same words is owner speech, and nothing is matched by text or prefix. Source records are never changed.
- **Provenance outlives receipts.** Created-session and internal-row provenance is kept in the ledger's `provenance` table. It is not pruned with sends and is carried across an explicit reset. A projection rebuild re-derives the exclusion from it.
- **Disclosure.** Snapshot, history and changes carry `provenance {state, limitation, notice?}`:
  - `none`: no ledger in this profile; nothing is applied.
  - `ok`: provenance was read.
  - `incomplete`: a reset could not read the old ledger, so earlier proofs were lost. Such notes then read as the session recorded them, and every read says so.
  - `unavailable`: the ledger cannot be read now.
  - `not_applied`: an app built **without** keyed sends found a ledger in the profile.
- **Limitation, measured (open gate):** the pinned Hermes compresses a long session **in place**: it deactivates the original rows and appends active copies (history, a summary row and a copy of the owner message). The executor classifies the copies `rewrite_copy`, so the receipt's owner and reply are right. The reads follow Hermes's `active` flag, so the original owner row reads as deleted (the send's `links` become `lost`) and the copies read as new messages, the owner-text copy as uncorrelated owner speech. This is how the reads behave for any compressed session, keyed or not. See `Phase1B_C1_ActivationReadiness.md` §4.
- **Limitation, stated:** rows written outside a keyed send (terminal, Telegram, earlier app versions, history) carry no provenance. A continuation note there shows as its session recorded it. Nothing is inferred for them.

### 8.5 Restore limitation

After any known restore or rollback of the profile home or of the ledger, an explicit reset is required before sends resume. An unannounced, coherent rollback of the ledger can re-admit a request whose receipt it lost, if that key is still within the 24 h admission window and its generation still matches. This is not detected (`PHASE1B_DESIGN.md` §4.1).

### 8.6 The keyed browser client (C3): NOT ACTIVATED

`kit/app/static/chat-sends.js` is the minimal client for these routes (`PHASE1B_DESIGN.md` §6). It is served into the page only when the app is built with `chat_sends=Options(client=True)`, a second explicit opt-in beside the routes themselves; the page then carries `<meta name="tamanitomo-chat-sends" content="keyed">` and loads the script after every other one. Without that signal the page is `index.html` unchanged, the file is never referenced, it is not in `release-files.json`, and the workspace sends through `POST /api/chat` as before. The client never tries a keyed send and falls back; once an intent is keyed it never reaches `POST /api/chat` (timeout, missing route, expired sign-in and restart included).

- One pending intent per profile, in this tab's `sessionStorage` (`chat-pending-<installation>-<profile>`), beside the draft (`chat-draft-…`) and never inside it: `{v, client_key, generation, conversation_id, installation, profile, session, message, created_at, send_id?, operation_id?}`. It is written and read back before the POST; if the browser cannot store it, nothing is sent and the draft stays. Only `send_id`/`operation_id` are ever added. The compose box stays editable during a turn, and no outcome clears or replaces a newer draft.
- `client_key` is a ULID (the server's format). Every automatic retry is the identical POST with the same key (backoff 0.5–8 s, then every 30 s while the page is open, and on reload). A lost or unreadable answer is followed by `GET ?key=`; a `404` there while the POST may be in flight means retry the same POST, never a new key. A `401` stops protected polling and keeps the intent for "Check now" after signing in.
- Status polls `GET /api/operations/{id}` (the ledger view). `stream.text` replaces the reply-in-progress bubble (`<send_id>:stream`); it is never appended. The final owner/reply bubbles carry `<send_id>:owner` and `<send_id>:reply:<n>` and are filled from `result.messages` chosen by the receipt's `owner_message_id`/`reply_message_ids`. Replies render through the existing escaping and media paths.
- Wording is the §6 table: "Not sent" (a refusal that proves non-acceptance, or `not_started`; the message goes back to the box only if the box is empty), "Your message was recorded; the reply failed" + **Ask again**, "The reply failed. Whether your message was recorded is unknown.", "Stopped" with the partial reply marked partial, the `unknown` sentence with **Send again** only while the receipt says `quiescent`/`none`, "Not confirmed. The app will check again with the same request.", and the reset sentence for `409 generation_changed`. Ask again and Send again are new intents with new keys; Send again first asks "This may send your message twice." and re-reads the receipt.
- **Identity for history rows.** With the client enabled (only then), `/api/feed` rows also carry `source_message` (the Hermes row id, beside `session`), rendered as `data-source-session`/`data-source-message`. When a page returns to a pending send (reload, back to Chat), one `GET /api/chat/snapshot?limit=50` finds rows whose `correlation.send_id` is this send's; at settlement the same match is made from the settled `result.messages[].source`. A matching history row takes over the send's DOM id and the provisional bubble is removed. Nothing is matched by text or time.
- **Limitation, measured:** a send's links are recorded when it settles (C1), so between a reload and settlement the recorded owner row can show twice (history + provisional). They merge at settlement.
- Profile isolation: every request carries the scope captured with the intent; a page for another profile never reads, resumes or paints it. A pending intent from a different `conversation_id` is left untouched and blocks new sends on that tab until it is resolved or the tab is closed.
- A stored reply row that itself contains inline reasoning markup is shown as recorded (the existing read boundary above); the live stream is filtered on the server.

### 8.7 Not activated, and why

Keyed sends stay off. The gate table is `Phase1B_C1_ActivationReadiness.md` §4 (it supersedes the list that used to be here). Open on Linux: processes the pinned tool starts (every command runs in a new session, outside the managed group), the read side of real CLI compression, and escaped descendants. Not yet observed at all: supervisors on Windows, macOS and Termux.

Until then, unsupported platforms, storage or interpreters are refused before anything is created (`503`). Existing users keep `POST /api/chat`.
