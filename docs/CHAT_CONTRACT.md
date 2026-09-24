# Conversation read contract (Phase 1A)

This covers reading the owner's private conversation. Sending is unchanged (`POST /api/chat`); send receipts, idempotency and recovery are Phase 1B. Continuity across reflection and Hermes context is Phase 1C. No dock, push or live transport is part of this phase.

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
- `companion_outbox` marks an entry `sent` without the platform message id that `hermes send --json` returns.
- Hermes's delivery mirror row (`gateway/mirror.py` → `append_message(session_id, role, content)`) has no outbox id and no platform id. It carries no marker that tells it apart from a model reply; the mirror metadata is dropped at the SQLite boundary.
- `finish_reason`/`token_count` are not a proof either. Nothing establishes that they are set on every model reply.

So the boundary is:
- Output of a cron (or any internal) session is never conversation.
- No outbox entry is projected, and none is joined to a transcript row, by text or otherwise. Queued, withheld, failed and expired entries never appear.
- A **companion** row in a trusted session is shown as that session's transcript recorded it, with `correlation: null`. No row is labelled or counted as a verified delivered outreach, whether it came from a model reply or a delivery mirror, and the gate stays **not passed**.
- An **owner** row in a Telegram session must carry the `platform_message_id` that Hermes records for every inbound gateway turn (`gateway/run_turn.py`). Without one, the sender of a user row is not established under this adapter's rule. That covers the cron-brief delivery mirror, which Hermes writes as `role="user"`, and genuine owner messages written before the column existed: a missing id does **not** prove the owner never sent the message. Such a row is excluded from the trusted conversation as `unverified_sender`; the source row is kept and the exclusion counted. A future opt-in archive view could show such rows labelled unverified, but that is a separately reviewed visibility feature: showing a row would not make it trusted owner evidence, reflection input or model context. This is structural, not a text-prefix match, and the source row is untouched.

Recording the delivery id at dispatch would make proactive delivery verifiable. That is a send-path change and belongs to Phase 1B.

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
