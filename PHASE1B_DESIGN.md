# Phase 1B design: send receipts, idempotency and interruption

Status: **design proposal only, for review.** Nothing in this document is implemented. No sending code, UI, schema, live record or release was changed to write it.

- Branch: `test/phase1-conversation-contract`
- Designed against: `fc5c1e4` (code identical to `7e616d2`, accepted in PHASE1A_REVIEW_R3)
- Hermes inspected: installed `hermes-agent` at `0e9fc2cc15`, the same revision as the Phase 1A fixtures
- Gate: PHASE1A_REVIEW_R3 "Proposed next task" and TAMANITOMO_BUILD_PLAN_R2 §1.4. Phase 1B implementation needs its own approval after this review.

Wording used below: **definite** means the app can prove the fact from its own durable records. **Unknown** means it cannot, and the app then says so. It does not guess.

---

## 1. The current send path

### 1.1 Client (`kit/app/static/workspace.js`)

1. `chat-form.onsubmit` (`workspace.js:292`) saves the draft to `sessionStorage`, draws a temporary bubble `turn-<Date.now()>` marked "sending…", then calls `action('/chat', {message, session: chatSession}, onDone)`.
2. `action()` (`workspace.js:118`) refuses to start while `activeOperation` is set, or while an operation id is still in `sessionStorage`. Otherwise it `POST`s and hands the returned operation row to `followOperation()`.
3. `followOperation()` (`workspace.js:55`) stores the operation id in `sessionStorage` and polls `GET /api/operations/{id}` every 350 ms for chat. While polling it paints `row.stream_text` into a `#chat-stream` bubble. When the status becomes `complete` it calls `onDone`, which marks the temporary bubble sent, clears the draft, and appends the reply from `result.messages` (or `result.response`).
4. Any other outcome throws. The `catch` block (`workspace.js:339-353`) marks the bubble **"Failed to send"**, puts the message back in the compose box and says "you can retry". The UI draws no distinction between a request that was never accepted, a generation that failed, a timeout and a restart.
5. After a page reload, a leftover operation id is followed again (`workspace.js:197-198`). `onDone` was an in-memory callback, so it is gone, and a completed chat just re-renders the page. The draft survives in `sessionStorage` because only `onDone` clears it.

### 1.2 Server (`kit/app/manage.py`, `kit/app/runtime.py`)

1. `POST /api/chat` (`manage.py:1542-1566`) validates `message` (1–30,000 characters). When `session` is given it checks that the session belongs to this profile (`hr.messages`). It then calls `op('Chat with …', run)`.
2. `op()` (`manage.py:245-249`) refuses while a native Hermes console is open, then calls `Operations.submit()`.
3. `Operations.submit()` (`runtime.py:269-310`) takes the in-memory per-installation lock `busy` and refuses with a 400 if it is held. It writes `<state>/operations/<uuid>.json` with status `running` **before** it queues the work (`runtime.py:278`), then runs the action on a 4-thread pool. The row keeps `progress`, `stream_text` (up to 1 MB, in memory only), `result` and `error`. When the action finishes, the row becomes `complete` or `failed`. Nothing ever prunes these files.
4. `Operations.get()` (`runtime.py:316-326`) reports a persisted `running` row that is not in memory as `interrupted`: "Inspect the current state before retrying."
5. `run()` inside `/api/chat` snapshots the session ids, then calls `rt.chat(['chat','--quiet','--oneshot','-q',message] (+ ['--resume',S]))`.
6. `Runtime.chat()` (`runtime.py:131-167`) spawns `python kit/app/hermes_stream.py …` with the message **in argv**. It reads JSON events (`delta`, `session`, `final`) through a 1024-entry queue and forwards deltas to `report.stream`. After 600 s it gives up, and `finally` kills the child. A non-zero exit raises, so the operation becomes `failed`.
7. When `rt.chat` cannot use the bridge (`len(command)!=1`, or no interpreter beside the binary), it falls back to `self.run(..., timeout=600)` and **no `session` event** arrives. `/api/chat` then guesses the session: the first new `cli/desktop/tui` session in the before/after diff (`manage.py:1558`).
8. Only after the turn completes does `hr.note_workspace_session(c, new)` (`runtime.py:538`) record the session in `<profile home>/.tamanitomo-sessions.json`. The Phase 1A adapter uses that file to classify rows as `workspace` (`chat_sources.py:241-247`).
9. The result is `{response, session, messages: hr.messages(c, new), note}`, and it is stored in the operation JSON.

### 1.3 Hermes (the owner of the turn)

- `hermes_stream.py` wraps `cli._configure_quiet_agent` (to attach `stream_delta_callback`) and `cli._run_quiet_single_query`. It emits `session` only in the wrapper's `finally` (`hermes_stream.py:37`), that is, **after** the turn. It emits `final` last.
- The session id is chosen inside Hermes: `resume or f"{%Y%m%d_%H%M%S}_{uuid6}"` (`cli.py:2825`). No flag lets the caller supply one. `_sync_cli_session_id_from_agent` shows that the agent can move the session id during a turn (context compression starts a continuation session with `parent_session_id`).
- Hermes writes messages to `state.db` from many points in the turn loop (`agent._persist_session` in `turn_api_call.py`, `turn_response_intake.py`, `turn_truncation.py`, … and `_flush_messages_to_session_db` in `turn_final_response.py`). **I have not established** whether the owner row is on disk before the first provider byte in every path. The design treats "owner turn recorded" as something to observe, never to assume (§4.6, matrix M-10).
- Interruption: a quiet one-shot run catches `KeyboardInterrupt`, emits an interrupted session end, and prints `session_id` to stderr (`cli.py:4057-4062`). An API call interrupted mid-stream persists the partial assistant text (`turn_api_call.py:183-191`).

### 1.4 Proactive delivery (`kit/scripts/companion_outbox.py`, `companion_dispatch.py`)

- `outbox.queue()` appends `{kind: outbox, status: queued, id: msg-<hash>}` to `<life>/outbox.jsonl`. `outbox.mark()` appends `outbox_update` rows, and `fold()` computes the current state.
- `dispatch.run()` sends at most one entry per run: it runs `verdict()`, then `outreach.claim()` for a slot (`dispatch.py:154`), then `deliver()` → `hermes_send()` (`dispatch.py:157`), then `outbox.mark(sent|failed)` (`dispatch.py:158`).
- `hermes_send()` runs `hermes send --to <target> --json`. On success Hermes returns `{"success": true, "message_id": …}` (`tools/send_message_tool.py:472`). For a media send, and for a message split into chunks, only the **last** chunk's id is returned (`send_message_tool.py:427`). The dispatcher treats success as a boolean and **discards `message_id`**.
- Hermes mirrors a successful send into the target's gateway session with `mirror_to_session(platform, chat_id, text, role=…)` (`gateway/mirror.py:25`), and the result carries `mirrored: true`. The mirror row stores role and content only. It has no outbox id and no platform id (Phase 1A contract §2).

### 1.5 Defects this design must close

| # | Defect | Evidence |
|---|---|---|
| D1 | There is no idempotency. A retry after a lost HTTP response, or the "you can retry" draft restored after an accepted-but-failed turn, launches a second generation and a second owner turn. | §1.1 steps 4–5, §1.2 step 1 |
| D2 | "Failed to send" is shown for accepted-but-failed, timed-out and interrupted turns. The build plan forbids this. | `workspace.js:347` |
| D3 | The operation row is durable before launch, but it records neither the request nor anything that proves whether Hermes started. `interrupted` is reported for any `running` row, including one that never spawned. | `runtime.py:278`, `:323-324` |
| D4 | The busy lock is in memory and scoped per process. A second app process (another `TAMANITOMO_APP_STATE`, or desktop plus hosted) or a terminal `hermes --resume S` can run a turn on the same session at the same time. | `runtime.py:264-273` |
| D5 | A new session is registered as `workspace` only after completion. A crash or timeout leaves it unregistered, so its rows are classified `terminal` (or excluded when terminal trust is off), never `workspace`. | `manage.py:1561`, `runtime.py:538` |
| D6 | The fallback session guess can adopt a terminal session that another process created at the same moment, and register it as `workspace`. | `manage.py:1558` |
| D7 | A timeout or restart kills the child, yet a partial or complete turn may already be in `state.db`. It is reported as `failed`/`interrupted` with no statement about what was recorded. After a hard kill of the server, the child's fate is unknown: it may be orphaned and still writing. | `runtime.py:163-167` |
| D8 | Operation JSON files grow without bound and keep full reply text (`result.response`, `result.messages`). | `runtime.py:299-310` |
| D9 | **Proactive duplicate.** A crash between `deliver()` and `outbox.mark()` leaves the entry `queued`, so the next run claims another slot and sends it again. That breaks the module's own "never retried" rule. | `dispatch.py:154-158`, `outbox.py:103-114` |
| D10 | The platform message id Hermes returns is discarded, so a delivered proactive message can never be verified (Phase 1A F4). | `dispatch.py:115-120` |

---

## 2. Goals and non-goals

Goals:
1. One accepted workspace send launches at most one Hermes turn. Identical retries return the same receipt.
2. Acceptance is durable before any work launches. The receipt has a stable identity that survives restarts and projection rebuilds.
3. Every outcome is honest: definite non-execution, accepted-but-failed, interrupted, and **unknown**.
4. The chain request → owner turn → operation → provisional bubble → final reply is recorded from provenance, never from text.
5. Proactive dispatch stops double-sending (D9) and captures delivery identifiers durably (D10).

Non-goals for 1B: exactly-once execution; a new transport (SSE/WebSocket); the UI switch to the Phase 1A read contract (Phase 2); any external send from the workspace; new channel connectors; certifying delivered proactive provenance (§6.4 explains why this still depends on a mirror-linkage decision); changing Hermes's schema.

---

## 3. Identifiers

| Name | Made by | Form | Scope and meaning |
|---|---|---|---|
| `client_key` | the client, once per compose-and-send intent | ULID (48-bit ms time + 80 random bits), Crockford base32 | Scoped to `(installation, profile home, conversation_id)`. The embedded time bounds how old a key may be (§5.3). |
| `request_digest` | the server | `sha256` of canonical JSON `{v:1, conversation_id, destination:"workspace", session: S\|null, message}` (message as exact UTF-8, no normalisation) | Binds the key to the accepted content and destination. |
| `send_id` | the server, at acceptance | `snd_` + 26-char random | The stable receipt identity. It is also the provisional bubble id. |
| `operation_id` | the existing `Operations` | 32 hex | Kept for status polling and compatibility. Linked 1:1 to `send_id`. |
| `worker` | the server, at launch | `{instance, pid, pid_start, boot_id}` | Ties a `generating` row to a live process. `instance` is a random token per app process start. `pid_start` is `/proc/<pid>/stat` field 22 or the platform equivalent. |
| `hermes_sessions` | Hermes, reported by the bridge | ordered list | The initial session, plus any continuation session made during the turn. |
| `owner_source` / `reply_sources` | the ledger, after reconciliation | Phase 1A source keys plus fingerprints `(id, session_id, role, timestamp)` | Authoritative links into Hermes. **Not** projection `message_id`s (§4.7). |

Why the key belongs to the client: a client that never saw a response can only retry with an identifier it made before sending. A key generated by the server cannot close the lost-response gap.

---

## 4. Server design

### 4.1 Where records live

A new SQLite file, the **send ledger**, at `<profile home>/.tamanitomo-sends.sqlite3` (0600 on POSIX, a symlinked file refused, the same checks as the projection).

Why in the profile home and not the app state directory:
- Every app process serving this profile, whatever its `TAMANITOMO_APP_STATE`, sees the same ledger and the same lease (closes D4 for app processes). The app already keeps `.tamanitomo-sessions.json` and `.tamanitomo-chat-owner.json` there.
- It is **not** rebuildable, so it must not share the Phase 1A projection's life cycle (that file "can be deleted at any time"). A projection rebuild never touches the ledger.
- Installation scope comes for free: a profile home belongs to exactly one installation.

The ledger never stores message text or reply text. It stores digests, identifiers and states. This leaves the privacy footprint below today's operation JSON (D8).

### 4.2 Schema (proposed)

```sql
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);   -- schema_version=1, created_at
CREATE TABLE sends(
  send_id TEXT PRIMARY KEY,
  scope_digest TEXT NOT NULL,          -- sha256(installation|profile home|conversation_id)
  client_key TEXT NOT NULL,
  key_time REAL NOT NULL,              -- decoded from the ULID
  request_digest TEXT NOT NULL,
  destination TEXT NOT NULL CHECK(destination='workspace'),
  requested_session TEXT,              -- null = start a new session
  state TEXT NOT NULL,                 -- §4.3
  execution TEXT NOT NULL,             -- none | started | unknown
  owner_turn TEXT NOT NULL,            -- absent | recorded | unknown | ambiguous
  reply TEXT NOT NULL,                 -- none | partial | final | unknown
  error_code TEXT, error_detail TEXT,  -- redacted, <= 600 chars
  operation_id TEXT,
  worker TEXT,                         -- JSON, §3
  heartbeat_at REAL,
  source_watermark INTEGER,            -- max(messages.id) in state.db, read just before spawn
  hermes_sessions TEXT,                -- JSON list
  owner_source TEXT, reply_sources TEXT,  -- JSON, §4.6
  correlation TEXT NOT NULL DEFAULT 'pending',  -- pending | linked | unverified | ambiguous | lost
  created_at REAL NOT NULL, updated_at REAL NOT NULL, finished_at REAL,
  UNIQUE(scope_digest, client_key));
CREATE TABLE send_events(              -- append-only transition log
  seq INTEGER PRIMARY KEY AUTOINCREMENT, send_id TEXT NOT NULL,
  from_state TEXT, to_state TEXT NOT NULL, at REAL NOT NULL, reason TEXT NOT NULL);
CREATE TABLE lease(                    -- at most one active turn per conversation
  scope_digest TEXT PRIMARY KEY, send_id TEXT NOT NULL,
  worker TEXT NOT NULL, heartbeat_at REAL NOT NULL);
```

Every state change is one `BEGIN IMMEDIATE` transaction that updates `sends`, appends to `send_events` and, where it applies, writes `lease`. It uses the same journal mode as the projection. WAL is avoided on file systems where it is unsafe (Termux shared storage); this needs checking on the phone host before 1B lands.

### 4.3 State machine

Client-only states (never stored on the server): `draft` → `submitting`.

| State | Meaning | `execution` |
|---|---|---|
| `accepted` | The ledger row is committed and the lease is held. No process exists and none has been attempted. | `none` |
| `launching` | The intent to spawn is committed. `Popen` may or may not have run. | `unknown` |
| `generating` | The child is running. `worker.pid`/`pid_start` are recorded and the heartbeat is live. | `started` |
| `complete` | The child exited 0 and reconciliation found the reply. | `started` |
| `failed` | The child ran and ended in error (provider error, truncation, non-zero exit, timeout). **The owner message may be recorded.** | `started` |
| `interrupted` | The owner asked to stop, and Hermes handled the interrupt (§4.5). | `started` |
| `not_started` | **Definite** non-execution: spawn raised, or recovery found a row still in `accepted`. | `none` |
| `unknown` | The app lost track of a turn that was in `launching`/`generating` (crash, kill, lost heartbeat), and reconciliation has not yet found an outcome. | `unknown` |

Rejections that happen **before** acceptance write no row and are not states: `409 turn_in_progress`, `409 key_conflict`, `422 key_expired`, `400` validation. The client shows them as "Not sent", which is true.

Permitted transitions (anything else is a bug and raises):

```
accepted   → launching | not_started
launching  → generating | not_started (Popen raised, definite) | unknown (recovery)
generating → complete | failed | interrupted | unknown (recovery)
unknown    → complete | failed | interrupted     (only by source reconciliation, §4.6)
not_started→ accepted  (only by an identical retry of the same key, §5.2)
```

`complete`, `failed` and `interrupted` are terminal. `unknown` stays `unknown` when reconciliation cannot decide, and the UI says so. It is never auto-promoted to `failed` to look tidy.

Each terminal state carries `owner_turn` and `reply` separately, so the UI can say "Your message was recorded; the reply failed." That replaces "Failed to send" (D2).

### 4.4 Concurrency and locking

- **Lease.** Acceptance and lease acquisition happen in one transaction. When a live lease exists for the conversation, the request is refused with `409 turn_in_progress` (definite non-acceptance). This keeps today's one-turn-at-a-time behaviour and extends it across processes.
- **Liveness.** The worker's heartbeat updates `heartbeat_at` every 5 s. A lease is stale only when the heartbeat is older than 30 s **and** the recorded worker is not alive (`pid` exists with the same `pid_start` and `boot_id`). A long provider stall with a live heartbeat is never treated as dead.
- **Recovery on start and on demand.** A process that finds a stale lease runs recovery for that send under `BEGIN IMMEDIATE` (§4.5) and then releases the lease. Recovery runs lazily on the next `POST`/`GET` for the conversation and eagerly once at app start. There is no background polling.
- **Orphaned children.** The child is started in its own process group (`start_new_session=True` on POSIX, `CREATE_NEW_PROCESS_GROUP` on Windows). When recovery finds the recorded child still alive (same pid, `pid_start` and `boot_id`), it can never report through the dead pipe, so recovery sends it an interrupt, waits up to 10 s, kills the group if needed, then reconciles from the source. It never waits for the orphan to finish, and it never starts a second turn next to it.
- **Terminal `--resume`.** A person resuming the same session from a real terminal is outside the app's lease. Reconciliation detects the effect (more than one owner row after the watermark) and marks the correlation `ambiguous` instead of picking one (§4.6).
- `Operations.busy` stays in place for the installation-wide mutations (install, update, gateway). A chat send still takes it, as it does today, so an update cannot run under a live turn.

### 4.5 Crash and interruption table

"Retry" means the client repeats the **same key and payload**.

| Crash point | Durable state found | Recovery sets | Owner turn | Can a retry duplicate the turn? | Retry returns |
|---|---|---|---|---|---|
| Before the acceptance commit | no row | — | absent (definite) | no | a fresh acceptance (the first never existed) |
| After acceptance, before the `launching` commit | `accepted` | `not_started` | absent (definite) | no | re-arms the same `send_id` → `accepted` → launch (definite non-execution makes this safe) |
| After the `launching` commit, before or during `Popen` | `launching` | `unknown`, then reconcile: rows in the watermark window → `failed`/`complete`, none → **stays `unknown`** | unknown until reconciled | **no**: never relaunched automatically | the `unknown` receipt |
| Child started, before Hermes persisted anything | `generating` | orphan killed, `unknown`, reconcile finds nothing | unknown (cannot prove Hermes would not have written the row later) | no | the `unknown` receipt, with "Send again" offered as a **new key** only after the owner explicitly confirms (§5.4) |
| After the owner row persisted, before any reply | `generating` | reconcile → `failed` (`owner_turn=recorded`, `reply=none`) | recorded | no | the `failed` receipt ("recorded; no reply") |
| After partial output | `generating` | reconcile → `failed` (`reply=partial`) or `interrupted` when Hermes wrote its interrupted marker | recorded | no | that receipt |
| After the final reply persisted, before exit | `generating` | reconcile → `complete` | recorded | no | `complete` |
| After exit 0, before the `complete` commit | `generating` | reconcile → `complete` | recorded | no | `complete` |
| After the `complete` commit, before the client got the response | `complete` | — | recorded | no | `complete` with the correlation |
| Owner presses Stop | `generating` | interrupt → Hermes's `KeyboardInterrupt` path → `interrupted` | recorded or absent, per reconciliation | no | `interrupted` |
| 600 s timeout | `generating` | interrupt first, then kill, then reconcile → `failed` (`error_code=timeout`) | per reconciliation | no | `failed` |
| Provider disconnect or truncation (Hermes exits non-zero) | `generating` | `failed` (`error_code=provider`) | per reconciliation | no | `failed` |

No path in this table launches a second Hermes turn for one `send_id`, except the `accepted → not_started → accepted` re-arm, which is only reachable when the app can prove that nothing ran.

This design does **not** claim exactly-once execution. It claims at most one launch per key, plus a truthful account when the outcome is unknown.

### 4.6 Correlation

**Session.** A bridge change (§7) emits `session` as soon as the agent is configured, again whenever the id changes, and in `finally` as today. The server appends every id to `hermes_sessions` and calls `note_workspace_session` **at the first sighting** (closes D5). The before/after guess (D6) is removed. When the bridge is unavailable (fallback `rt.run`), a new session cannot be correlated: the send is allowed only with `requested_session` set, or it completes with `correlation='unverified'` and the new session is **not** registered as `workspace`. This choice goes to the owner (§10, U3).

**Owner turn.** `W` is `max(messages.id)` from `state.db`, read in the `launching` transaction before spawn. The owner row is the single row with `session_id ∈ hermes_sessions`, `id > W`, `role='user'` and public by the Phase 1A rule.
- exactly one → `owner_turn=recorded`, `correlation=linked`
- none → `owner_turn=absent` once the child has exited, `unknown` otherwise
- more than one → `owner_turn=ambiguous`, `correlation=ambiguous`. No candidate is chosen.

The request digest is compared with that row's content as a **consistency check only**. A mismatch (for example, if Hermes rewrote the text) gives `correlation='unverified'`. Text never selects between candidates and never creates a link.

**Reply.** Assistant rows in `hermes_sessions` with `id > owner id`, public, written before the child exited (or found by reconciliation after an unknown exit). `reply=final` when the child exited 0; `partial` for a failed or interrupted turn that left assistant text.

**Provisional → final bubble.** Stream frames are tagged with `send_id`, and the provisional bubble's DOM id is `send_id`. Phase 1A's read contract gains `correlation.send_id` on the owner row and the reply rows. `chat_routes` computes it at read time by joining ledger `owner_source`/`reply_sources` on the projection's source key. A client that receives the projected reply replaces the provisional bubble with the same `send_id` instead of appending a duplicate.

**Surviving a projection rebuild.** The ledger stores **source keys and fingerprints**, never projection `message_id`s as authority. After a rebuild (new `projection_id`), the join finds the new opaque ids through the same source keys. When the fingerprint no longer matches (Hermes replaced its store: `source_replaced`), the join yields nothing, and the send reports `correlation='lost'` instead of attaching to whatever now holds that source id. This follows the Phase 1A R2 rule that no old identity is given to a different message.

**Destination.** `destination` is fixed to `workspace`, and the request schema has no field that could change it. A web reply stays a web reply. A Telegram (or other) badge on an earlier message is provenance only and does not change where the next reply goes. 1B adds no external send from the workspace. The outbox, its dispatcher, `may_send` permissions and image pre-delivery review are unchanged except as §6 describes.

---

## 5. API

### 5.1 New routes (added beside the old ones; `POST /api/chat` stays)

```
POST /api/chat/sends
  body: {client_key, conversation_id, message, session: S|null}
  202 {send: Receipt, operation: {id}}                 new acceptance
  200 {send: Receipt, operation: {id}|null, replay: true} identical retry
  409 {error: "key_conflict", send_id}                 same key, different digest
  409 {error: "turn_in_progress", send_id}             another turn holds the lease (not accepted)
  422 {error: "key_expired"}                           key time outside the window (§5.3)
  400 invalid input / wrong conversation_id (the Phase 1A scope capture applies)

GET  /api/chat/sends/{send_id}          → Receipt (recovery runs first when the lease is stale)
GET  /api/chat/sends?key=<client_key>   → Receipt | 404 (a client that lost send_id)
GET  /api/chat/sends?open=1             → receipts not in a terminal state, newest 20
POST /api/chat/sends/{send_id}/stop     → Receipt (generating → interrupted, §4.5)

Receipt = {send_id, client_key, conversation_id, state, execution, owner_turn, reply,
           correlation, error: {code, detail}|null, created_at, finished_at,
           owner_message_id|null, reply_message_ids: [] }   // resolved through the projection at read time
```

- Scope: `conversation_id` must equal the Phase 1A `ChatScope.conversation_id` captured for the request. A key from another profile or installation is not visible (404), because its `scope_digest` differs (profile isolation).
- Streaming stays on the existing operation poll (`stream_text`), with `send_id` added to the operation row. 1B adds no new transport.

### 5.2 Idempotency rules

| Situation | Result |
|---|---|
| New key in the window | accept (202) |
| Same key, same digest, any non-`not_started` state | 200 with the existing receipt. **Nothing launches.** |
| Same key, same digest, `not_started` | re-arm the same `send_id` → `accepted` → launch (definite non-execution) |
| Same key, different digest (text, session or conversation) | 409 `key_conflict`. Nothing changes. |
| Same key, other scope | treated as a new key in that scope. Keys are never looked up across scopes. |
| Key older than the window, or no row found for an old key | 422 `key_expired`. It is **never** accepted as a fresh send. |

### 5.3 Retention and bounds

- **Key window: 24 h.** A key whose embedded time is more than 24 h old, or more than 5 min in the future, is refused (`key_expired` / `400`).
- **Receipts are kept 30 days**, well beyond the window. So any key the server would accept still has its receipt when replayed. The 22+ day gap is deliberate headroom for clock skew and restored devices.
- **Pruning** runs once per acceptance and removes at most 500 rows past 30 days. `send_events` follows its sends. Ledger size is bounded by messages per 30 days; at about 200 bytes a row, 10,000 sends a month is about 2 MB.
- **Operation JSON** (D8): 1B stops writing reply text into chat operation rows (the receipt and the projection carry it). Operation files older than 7 days, beyond the newest 500, are pruned. This changes an existing behaviour and needs the owner's approval (§10, U4).

### 5.4 Client contract (for the later UI change; not implemented in 1B unless §10 U1 says so)

- The client mints the key when the owner presses Send and keeps `{client_key, send_id?, digest}` in `sessionStorage` beside the draft until the receipt is terminal.
- A lost response or reload means the client retries the same key, or calls `GET ?key=`.
- `failed` with `owner_turn=recorded` reads "Your message was sent; the reply failed", offers **Ask again**, and does **not** restore the text as an unsent draft.
- `unknown` reads "Sent. It is not known whether a reply was generated." **Send again** mints a **new key** after explicit confirmation that a duplicate is possible.
- `not_started` and pre-acceptance rejections read "Not sent", and the draft is restored.

---

## 6. Proactive delivery

### 6.1 Dispatch intent before delivery (closes D9)

The outbox stays append-only JSONL, and the dispatcher remains the only sender.
1. Before `deliver()`, append `{kind: outbox_update, status: dispatching, attempt: <uuid>, at}` under the outbox file lock.
2. `fold()` treats `dispatching` as not waiting. `waiting()` never returns it, so a crash after this point cannot resend.
3. After `hermes_send()`, append exactly one outcome: `sent`, `failed` or `unknown`, with the same `attempt`.
4. On its next run, the dispatcher finds `dispatching` with no outcome older than the send timeout (120 s) plus a margin, and appends `unknown` ("the dispatcher stopped mid-send; delivery is not known"). It **never** re-sends that entry.

`STATUSES` gains `dispatching` and `unknown`. Old ledgers stay valid: an entry with no `dispatching` row folds as it does today.

### 6.2 Outcome classification

| `hermes send` result | Outcome | Retried? |
|---|---|---|
| exit 0, `success: true`, not `skipped`, `message_id` present | `sent` + ids | no |
| exit 0, `success: true`, no `message_id` | `sent`, `message_id: null`, `id_missing: true` | no |
| `success: true, skipped: true` (e.g. `cron_auto_delivery_duplicate_target`) | `withheld` with Hermes's reason | no |
| JSON `error` from a check made before any platform call (unknown platform, no credentials, target not found) | `failed` (definite) | no (unchanged rule) |
| timeout, `OSError`, killed, non-JSON stdout, non-zero exit with no JSON | `unknown` | **no** |

The "before any platform call" list must be fixed from the Hermes source per error string, not guessed. Until that is done, every `error` counts as `unknown`, not `failed`. This errs toward saying "not known" rather than "not delivered". (§10, U5.)

### 6.3 Captured delivery record

A `sent` row stores `{attempt, platform, target, message_id, id_scope: "last_chunk", mirrored: bool}`. `id_scope` is honest about Hermes returning only the last chunk's id (§1.4). No text is compared, and the outbox body is not copied again.

### 6.4 What 1B still cannot certify

With §6.1–6.3, the app knows *that* and *where* a proactive message was delivered and holds the platform id. It still cannot link that delivery to the **transcript row** a viewer sees, because Hermes's mirror row holds no id. Joining by text is forbidden. Projecting outbox `sent` entries as their own messages would duplicate the mirror row, since dedupe by text is equally forbidden. The options, for the owner and reviewer:
- **(a)** Keep delivered-proactive **unsupported** in the read contract. Delivery status appears only in the outbox views (recommended for 1B).
- **(b)** Propose upstream that `mirror_to_session` store the platform message id in `messages.platform_message_id`. The adapter could then link rows by id. This is a Hermes change and is not ours to make.
- **(c)** Project outbox deliveries as a separate, labelled source, and exclude Telegram-session companion rows written within the dispatch window. This is rejected because it is a time-and-text heuristic in disguise.

Until (b) or an equivalent exists, the Phase 1A capability table keeps "delivered proactive provenance: unsupported".

---

## 7. Affected files

| File | Change |
|---|---|
| `kit/app/chat_sends.py` (new) | ledger, state machine, lease, recovery, reconciliation against `state.db` (read-only, through `runtime.session_db`) |
| `kit/app/chat_routes.py` | the `/api/chat/sends` routes; `correlation.send_id` join on reads |
| `kit/app/runtime.py` | `Runtime.chat()`: process group, early session callback, `interrupt()`; chat operation rows without reply text; operation pruning |
| `kit/app/hermes_stream.py` | emit `session` at configure time and on change (additive; the `final` protocol is unchanged) |
| `kit/app/manage.py` | legacy `/api/chat` keeps its behaviour, but gains early registration (D5) and drops the before/after guess (D6). Chat routes move into `chat_routes` (plan §1.6) |
| `kit/scripts/companion_outbox.py`, `companion_dispatch.py` | `dispatching`/`unknown`, attempt ids, captured `message_id` |
| `kit/app/chat_sources.py` | capability table: proactive "ids captured; transcript linkage unsupported" |
| `docs/CHAT_CONTRACT.md` | a new "Sending" section |
| `release-files.json` | the new module and test files |
| `tests/test_chat_sends.py`, `tests/test_dispatch_intent.py` (new); `tests/mock_provider.py` (a `hang` scenario, and `kill_after_first_delta` if needed) | §8 |

`workspace.js` is **not** changed in 1B unless §10 U1 decides otherwise.

---

## 8. Synthetic acceptance matrix

Every case uses a synthetic Hermes home, the fixture `state.db` schema (v30), and `tests/mock_provider.py`. No real credentials, source data or messages are used. "Crash" means a subprocess test harness that SIGKILLs the app worker at a named hook (`CHAT_SENDS_TEST_CRASH_AT=<point>`, honoured only when a test-only env var is set and never read in release builds; the design of that seam is a review item, U6).

| # | Case | Expected |
|---|---|---|
| M-1 | Two identical `POST`s with the same key, sequential | 1 Hermes spawn, 1 owner row; the second returns 200 `replay` with the same `send_id` |
| M-2 | Same key, 20 concurrent requests across 2 app processes on one profile home | 1 spawn; 19 replays or `turn_in_progress`, never a second acceptance |
| M-3 | Same key, different text / session / conversation | 409 `key_conflict`; the ledger is unchanged |
| M-4 | Different keys racing on one conversation | 1 accepted; the other gets 409 `turn_in_progress` (not accepted, draft kept) |
| M-5 | Lost HTTP response (the client drops the 202 and retries with the key) | the same receipt; the mock provider's request counter stays at 1 |
| M-6 | Key older than 24 h; key 10 min in the future; old key whose row was pruned | 422 / 400 / 422; nothing launched |
| M-7 | Crash at each point in §4.5 | the recovered state, `execution`, `owner_turn` and retry result exactly as the table says; the provider counter never exceeds 1 per key |
| M-8 | Orphaned child alive after the app is killed | recovery interrupts it, then reconciles; no second spawn |
| M-9 | Provider scenarios `disconnect_before_done`, `truncated`, `malformed` | `failed`, with `owner_turn` from reconciliation; never "not sent" |
| M-10 | `delayed_first_delta` + crash before the first delta | records **as observed** whether Hermes persisted the owner row; the test states what it proved and closes the §1.3 open point |
| M-11 | `recover` scenario (drop, then complete) | Hermes's own retry inside one turn → one `send_id`, `complete` |
| M-12 | Stop during `deltas` | `interrupted`; the partial reply is linked, `reply=partial` |
| M-13 | Timeout (a `hang` scenario, with the timeout shortened for the test) | interrupt, then kill → `failed/timeout`; no orphan left |
| M-14 | Projection rebuild (binding change) between send and read | `correlation.send_id` resolves to the new generation's ids |
| M-15 | Source replacement (`source_replaced`) after the send | `correlation='lost'`; never attached to the new holder of the source id |
| M-16 | A terminal `--resume` of the same session during the turn (a fixture row inserted after the watermark) | `owner_turn=ambiguous`; nothing chosen by text |
| M-17 | Two profiles, the same `client_key` | independent receipts; neither can read the other's (404) |
| M-18 | New session, crash before completion | the session is registered `workspace` at first sighting and projected as workspace (D5) |
| M-19 | Bridge unavailable (fallback path) + a concurrent terminal session created | the terminal session is **not** registered as workspace (D6) |
| M-20 | Dispatcher crash after `deliver()` before the outcome | the entry folds `unknown`; the next run sends nothing (D9) |
| M-21 | `hermes send` returns `message_id` / no id / `skipped` / error / timeout | outcomes per §6.2; the id is stored with `id_scope` |
| M-22 | Legacy `POST /api/chat` still works | the existing tests stay green; D5/D6 fixes apply |
| M-23 | Scale | 10,000 receipts: acceptance < 20 ms, pruning bounded at 500 rows per call (desktop measurement only, labelled as such) |

Local full suite plus the CI matrix (Linux 3.11/3.13/3.14, Windows and macOS smoke), as in 1A. Process-group and `pid_start` behaviour are platform-specific. Windows and macOS need at least one real (not mocked) orphan-recovery test each, or an explicit "not tested on this OS" line.

---

## 9. Compatibility

- **No Hermes schema change.** The ledger is app-owned. `state.db` is still opened read-only (`mode=ro`, `query_only`).
- **The bridge protocol is additive.** Old servers ignore early `session` events. A new server with an old bridge (no early event) falls back to the post-turn `session` event, and D5 then stays open for that turn only.
- **The legacy `POST /api/chat` and the current UI keep working.** Legacy sends get no key, so they are not idempotent, as today. They do get a ledger row with `client_key=legacy-<uuid>`, so the lease covers them too (D4).
- **The projection schema does not change.** `correlation.send_id` is computed in routes, so no rebuild is forced.
- **Outbox:** old entries fold unchanged. A dispatcher from before 1B that reads a new ledger would treat `dispatching` as an unknown status. `fold()` already keeps the last known status, so the entry would not return to `queued`. This must be tested (M-20 variant).
- **Release:** the new modules go in `release-files.json`. There is no data migration. The ledger file is created on first send.

---

## 10. Unresolved decisions for the owner or reviewer

| # | Decision | Recommendation |
|---|---|---|
| U1 | Does 1B include the minimal `workspace.js` change (use `/api/chat/sends`, stop showing "Failed to send" for accepted sends), or leave the UI entirely to Phase 2? | Include the minimal change. D1/D2 are user-visible duplicates today. It would be reviewed as its own commit. |
| U2 | Should an `unknown` receipt offer "Send again"? | Yes, as a new key behind an explicit confirmation that a duplicate is possible. |
| U3 | When the bridge is unavailable and a new session is requested: refuse, or complete as `unverified` and leave the session unregistered? | Complete as `unverified` and do not register it. Refusing would break chat on setups that already work. |
| U4 | Stop storing reply text in chat operation JSON, and prune operation files (7 days / 500)? | Yes. |
| U5 | Before the error list is verified, classify every `hermes send` `error` as `unknown` rather than `failed`? | Yes (conservative). |
| U6 | The crash-injection seam: an env var read by production code vs. a test-only subclass or monkeypatch in a subprocess harness | A subprocess harness with monkeypatching; no seam in shipped code if achievable. |
| U7 | Proactive transcript linkage: option (a) now, and open an upstream Hermes proposal for (b)? | (a) now; (b) as an upstream proposal the owner decides whether to file. |
| U8 | Ledger location in the profile home (§4.1) vs. the app state directory | The profile home, for the cross-process lease. |
| U9 | Should the message stay in argv (visible in `/proc/<pid>/cmdline` to the same user) or move to stdin? | Out of 1B scope; note it for a security pass. |

---

## 11. What this document does not claim

- No Phase 1B code, test or result exists. Every behaviour above is proposed.
- When Hermes first persists the owner row is **not established** (§1.3, M-10).
- The mirror linkage (§6.4) is unsolved. Delivered proactive provenance remains unsupported.
- Exactly-once execution is not claimed.
- `ASTRA_PHASE0_REVIEW_R2.md` and `PHASE1A_HANDOFF.md` were not on disk. This design follows PHASE1A_REVIEW_R3, TAMANITOMO_BUILD_PLAN_R2 §1.4–1.6, and the code at `fc5c1e4`.
- Nothing was merged, tagged, released or deployed, and no live record was touched.
