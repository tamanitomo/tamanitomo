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
| workspace | a `cli`/`desktop`/`tui` session this app started | the app's session registry (`.tamanitomo-sessions.json`), written at send time |
| terminal | a local `cli`/`desktop`/`tui` session with no gateway `chat_id`, and `terminal` trusted in the binding | host provenance: only local processes write these sessions |
| telegram | `sessions.user_id` is a bound Telegram account **and** the session is a DM (`chat_type='dm'`, or `chat_type` empty with `chat_id == user_id`, which is Telegram's private-chat rule) | the owner binding |

Everything else is excluded and counted by reason (`/api/chat/sources`, and `excluded` in each snapshot):
- `unknown_participant`
- `group_or_channel`
- `unverified_source:<name>`: Discord, Signal and every other gateway
- `internal_session`: cron, subagent, tool, audits
- `local_source_with_gateway_chat`
- `terminal_not_trusted`

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

**Proactive messages.** Output of a cron session is never conversation. A proactive message that Hermes delivered **and mirrored into the owner's DM session** appears as the companion speaking on Telegram, because that row is in the owner's conversation.

The outbox cannot be joined to it:
- `companion_outbox` marks an entry `sent` without the platform message id.
- The Hermes mirror row (`gateway/mirror.py`) carries no outbox id.

So `correlation` is `null`, and no outbox entry is projected by itself. Queued, withheld, failed and expired entries never appear. Nothing is joined by text.

Hermes also mirrors **cron briefs** into a chat as `role="user"` rows. They carry only a `[Cron delivery: <job>]` text prefix; the structured marker is dropped at the SQLite boundary. Such a row keeps its place, but its `speaker` is `unverified` with a note, never `owner`. This is a sender-attribution guard. It is not the public/private boundary.

**Attachments** are resolved at read time through the existing media catalog (`_attach_media`), so review status and authorisation are unchanged. Nothing is fetched remotely.

## 3. Identity, revisions, generations

| Field | Meaning |
|---|---|
| `message_id` | Opaque: `msg_` + hash(conversation, projection generation, source key). Stable across syncs and restarts of one projection. |
| `source` | `{kind, account, channel, session, message}`. `message` is Hermes `messages.id` (AUTOINCREMENT, never reused within one file). |
| `speaker` | `owner` / `companion` / `unverified`. `role` is kept for compatibility (`unverified` maps to `user`). |
| `occurred_at` | Hermes `timestamp`; `occurred_at_known` is false if absent (history then sorts by first observation). |
| `observed_seq` | App-owned change sequence of the latest change to this message. |
| `revision` | 1 on insert, +1 on every edit, delete or restore. Identity never changes. |
| `status` | `public` / `edited` / `deleted` (a deleted message has `content: null`, and the projection keeps no copy of it). |
| `reply_to` | Always `null`: Hermes stores no reply link. |
| `correlation` | `{platform_message_id}` when Hermes stored one (Telegram user turns); otherwise `null`. Outgoing provisional/final correlation is reserved for 1B. |

**Source generation.** The projection stores the source's AUTOINCREMENT sequence and a fingerprint of one anchor row. Either of these counts as a **replaced store**:
- the sequence goes backwards (an older backup was restored)
- the anchor id now holds a different row (a different file)

A replaced store rebuilds the projection with a new `projection_id` and generation. Old cursors answer `resync_required`, and old ids are never aliased to new rows.

A Hermes `replace_messages()` (a transcript rewrite) gives surviving turns new ids. It is projected as deletions plus inserts, not as the same messages; this is a documented limit, and nothing is merged by text.

**Replays.** Records are keyed by source identity, so re-reading or re-pushing the same row is one message and no change. A push-style record may carry `source_revision`; one older than the applied revision is ignored, so a replayed old event cannot resurrect edited or deleted content.

**Edits.** Hermes has no revision column and does not record Telegram edits of past messages. An edit is observed only as changed content of the same id.

## 4. Reads

History order is `(occurred_at, message_id)`. Change order is `observed_seq`. The two are different questions: when something was said, and when the app learned it.

```
GET /api/chat/snapshot?limit=60        (1-200)
-> {conversation_id, projection_id, scope:{profile, installation, owner_binding},
    messages:[...oldest→newest...],
    history:{before: cursor|null, start_reached, start_note},
    changes:{after: cursor, high_water}, excluded:{reason:count}, sync:{...}}

GET /api/chat/history?before=<history cursor>&limit=60
-> {conversation_id, projection_id, messages, history:{before, start_reached}}

GET /api/chat/changes?after=<changes cursor>&limit=200   (1-1000)
-> {conversation_id, projection_id, changes:[{seq, kind: insert|edit|delete|restore,
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
- **503 `source_unavailable`** (`retryable: true`): the store is missing, locked, corrupt or of an unknown schema, including a messages table with no `id`. Nothing is changed.

**Start of history.** `start_reached: true` means the earliest message the sources still hold. A message a source has deleted is not recoverable by scrolling.

The legacy `GET /api/feed` and `GET /api/sessions/{id}` are unchanged. They still include every non-internal source, groups and unbound accounts among them. Moving the Chat UI onto this contract, which tightens that, is Phase 2 and will be explicit.

## 5. The persistent file, and its costs

**Location and contents.** One SQLite file per installation and profile, at `<app state>/chat/<installation>/<hash of profile home>.sqlite3`. The installation directory is mode 0700 and the file 0600 (POSIX); a symlinked file is refused. It holds tables `meta`, `messages` and `changes`, with a copy of public content only.

**Why it exists.** Stable ids, revisions and a change sequence need somewhere to live that is not Hermes's database. This file is not a second authority: it is rebuilt from the sources whenever its schema, scope, binding or source generation differs, and it can be deleted at any time.

**Interrupted writes.** Every sync is one `BEGIN IMMEDIATE` transaction, so a crash rolls back to the last consistent state (tested).

**Indexing bounds** (for phone-class hosts):
- **Pulling new rows:** at most 20,000 source rows per request, in batches of 5,000.
- **Reconciling:** checks at most 10,000 source ids for edits and deletions per request, and only every 30 seconds. It resumes where it stopped.
- **Initial indexing:** a large history is spread over several requests (`sync.caught_up`).
- **Reads:** history pages are an index walk (`messages_history`); nothing downloads all history.

No polling runs in the background. Work happens only when `snapshot` or `changes` is requested.

Measured on 50,000 synthetic messages (Linux, Python 3.14, SSD; `tests/test_chat_projection.py::ScaleTests`):

| | |
|---|---|
| initial indexing | 1.44 s over 3 bounded calls |
| snapshot (60 messages) | 0.6 ms, 26 KB JSON |
| history page (60) | 0.3 ms |
| sync with nothing new | 0.6 ms |
| full reconcile | 0.49 s |
| projection file | 21 MB |

## 6. Capability table

"Fixture" means tested against a Hermes-schema `state.db` built with the installed Hermes's exact sessions/messages columns (schema_version 30, hermes-agent `0e9fc2cc15`). Nothing here is live-tested.

| | workspace | terminal | telegram | discord / signal / others | outbox delivery |
|---|---|---|---|---|---|
| Schema inspected | yes | yes | yes | not in this phase | yes (`companion_outbox`, Hermes `send`/mirror) |
| Owner / DM identity | app registry | local session, no gateway chat | bound `user_id` + DM rule | **unsupported** | n/a |
| Durable ids / lifecycle | `messages.id` per store generation | same | same (+`platform_message_id` on user turns) | n/a | outbox id, no platform id |
| Edits / deletions | content change / row gone or hidden | same | same; Telegram edits are not recorded by Hermes | n/a | n/a |
| Attachments | `MEDIA:`/image refs via media catalog | same | same | n/a | n/a |
| Deltas | completed messages only (Hermes persists no deltas) | same | same | n/a | n/a |
| Delivered proactive provenance | n/a | n/a | mirror row appears, no linkage | n/a | **linkage unavailable** |
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
