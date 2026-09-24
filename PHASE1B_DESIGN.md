# Phase 1B design: send receipts, idempotency and interruption

Status: **design proposal only, revision 2, for review.** Nothing in this document is implemented. No sending code, UI, schema, live record or release was changed to write it.

- Branch: `test/phase1-conversation-contract`
- Revision 1: `b074ae9`. Revision 2 (this document) answers PHASE1B_REVIEW_R1 (B1–B5, U1–U9) on top of it.
- Designed against: `fc5c1e4` (code identical to `7e616d2`, accepted in PHASE1A_REVIEW_R3). Phase 1A acceptance is retained unchanged.
- Hermes inspected: installed `hermes-agent` at `0e9fc2cc15`, the same revision as the Phase 1A fixtures. Hermes line references below are to that revision and describe private code that can change; every capability taken from it is detected at run time and has a safe fallback (§8).
- Gate: Phase 1B implementation needs its own approval after this revision is reviewed.

Wording used below:
- **definite** means the app can prove the fact from durable records written by the process that knows it. **Unknown** means it cannot, and the app then says so. It does not guess.
- An **outcome** (did Hermes record the message, did it finish a reply) and **executor liveness** (can the process that ran the turn still write) are separate facts, recorded separately and never inferred from each other.

What changed from revision 1 is summarised in Appendix A, finding by finding.

---

## 0. Decisions recorded from PHASE1B_REVIEW_R1

These are the reviewer's decisions, adopted as the basis of this revision. They are not implementation authorisation.

| ID | Decision | Where this revision applies it |
|---|---|---|
| U1 | The minimal `workspace.js` correction is in 1B scope, as its own implementation commit after design approval: durable keys and receipts, honest non-acceptance / failed-generation / unknown wording, recovery of the same intent after reload. No dock, history-route migration, transport, notification or Phase 2 work. Synthetic browser checks. | §6, changeset C3 (§9), M-22 |
| U2 | A new-key send after an unknown outcome is allowed only after explicit confirmation **and** only once the old execution is proven unable to continue. Confirmation never overrides the one-active-turn rule. Status lookup, or the identical same-key retry, is always the first recovery action. | §4.5, §5.4, §6.3 |
| U3 | An explicitly unverified fallback is allowed when the bridge cannot provide source correlation, provided launch, receipt and concurrency stay safe. No session is inferred or registered from before/after history; source links stay unverified; the downgrade is disclosed. If safe process supervision itself is unavailable, the send is rejected before acceptance. This fallback does not close D5 for that turn. | §4.4.4, §4.10.6 |
| U4 | Chat text is not persisted in operation records, including `stream_text`. Bounded retention with an exact predicate. Active safety state is never pruned. The legacy response contract is kept through an authorised transient view where possible. | §5.6, §5.7 |
| U5 | Unclassified delivery errors are `unknown`. A definite pre-platform failure needs established evidence. Available ids and the uncertainty are kept; nothing is resent. | §7.5 |
| U6 | Crash tests use a subprocess harness with injected doubles, monkeypatching or a test-only subclass. No crash-trigger environment variable ships. Tests drive the production transition code. | §10 preamble |
| U7 | Proactive transcript linkage stays unsupported in 1B; delivery evidence stays in the outbox. An upstream proposal may be drafted, not filed. Mirror rows are never deduplicated by text or time. | §7.7 |
| U8 | The durable send ledger lives in the private, canonical profile home. The physical lock identity is shared across app instances and aliases and does not depend on app-local installation labels. Permissions, supported file systems, corruption/missing-file recovery and backup/restore behaviour are defined. The ledger is not a rebuildable cache. | §3, §4.1 |
| U9 | The argv-to-stdin move is a separate security task. The current exposure stays documented. No new prompt copies are introduced in error, event or operation records. | §4.4.1, §11 |

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
3. `Operations.submit()` (`runtime.py:269-310`) takes the in-memory per-installation lock `busy` (a `set` guarded by a `threading.Lock`, so it binds only the current process) and refuses if it is held. It generates its own `uuid4` identity and writes `<state>/operations/<uuid>.json` with status `running` **before** it queues the work, then runs the action on a 4-thread pool. The row keeps `progress`, `stream_text` (up to 1 MB), `result` and `error`.
   - **Correction to revision 1:** `stream_text` is **not** memory-only. `stream()` assigns it into the row; every later `report()`, `percent()` and the `finally` in `work()` call `_save(row)`, which serialises the whole row. The finalisation save always runs, so the streamed reply text reaches disk on every chat, whether or not a progress callback ran after the last delta.
   - When the action finishes, the row becomes `complete` (with `result`) or `failed` (with `error=redact(exc)`). For chat, `result` holds `response` and `messages`, and a failed chat's `error` can hold the tail of Hermes's stderr or the final text. Nothing ever prunes these files.
4. `Operations.get()` (`runtime.py:316-326`) reports a persisted `running` row that is not in memory as `interrupted`: "Inspect the current state before retrying."
5. `run()` inside `/api/chat` snapshots the session ids, then calls `rt.chat(['chat','--quiet','--oneshot','-q',message] (+ ['--resume',S]))`.
6. `Runtime.chat()` (`runtime.py:131-167`) spawns `python kit/app/hermes_stream.py …` with the message **in argv**. It reads JSON events (`delta`, `session`, `final`) through a 1024-entry queue and forwards deltas to `report.stream`. After 600 s it gives up, and `finally` kills the child (`Popen.kill()`, the child only; no process group). A non-zero exit raises, so the operation becomes `failed`.
7. When `rt.chat` cannot use the bridge (`len(command)!=1`, or no interpreter beside the binary), it falls back to `self.run(..., timeout=600)` and **no `session` event** arrives. `/api/chat` then guesses the session: the first new `cli/desktop/tui` session in the before/after diff (`manage.py:1558`).
8. Only after the turn completes does `hr.note_workspace_session(c, new)` (`runtime.py:538`) record the session in `<profile home>/.tamanitomo-sessions.json` (the newest 400 kept). The Phase 1A adapter uses that file to classify rows as `workspace` (`chat_sources.py:136`).
9. The result is `{response, session, messages: hr.messages(c, new), note}`, and it is stored in the operation JSON.
10. `ChatScope.conversation_id` is `sha256(installation label | resolved home)` (`chat_projection.py:86`). The installation part is the app-local label from the current selection, so two app states that label the same Hermes root differently derive two `conversation_id`s for one physical profile home.

### 1.3 Hermes (the owner of the turn)

- `hermes_stream.py` wraps `cli._configure_quiet_agent` (to attach `stream_delta_callback`) and `cli._run_quiet_single_query`. It emits `session` only in the wrapper's `finally` (`hermes_stream.py:37`), that is, **after** the turn. It emits `final` last.
- The session id is chosen inside Hermes: `resume or f"{%Y%m%d_%H%M%S}_{uuid6}"` (`cli.py:2825`). No flag lets the caller supply one. `_sync_cli_session_id_from_agent` (`cli.py:4051`) shows the agent can move the session id during a turn (compression starts a continuation session with `parent_session_id`).
- **Persistence seam.** Every transcript row is inserted through `SessionMessagesMixin` in `hermes_state_messages.py`: `append_message` (`:265-290`, returns the new row id), `append_messages_batch` → `_insert_message_rows` (`:293-315`, `:421-437`, which stores each row id in `msg["_row_id"]`), and `replace_messages` (`:439-470`, which deletes or soft-archives live rows and re-inserts a rewritten set). All of these run inside the Hermes process that runs the turn. Rows are written from many points in the turn loop; **I have not established** whether the owner row is on disk before the first provider request in every path (M-10, observation O-3).
- **Hermes's own turn lease.** `state.db` has `session_turn_leases` (`hermes_state_common.py:462`). `agent/turn_facade_lease.py:271` acquires one per turn when the database supports it, and appends that carry `turn_lease_holder` are refused when the lease is lost (`hermes_state_messages.py:177-231`). **Not established:** whether every writer (a terminal `--resume`, the gateway, cron) acquires it for the same key, so this revision does not rely on it for exclusion (observation O-5).
- **Exit codes.** A quiet one-shot run exits `130` after `KeyboardInterrupt` (after `_emit_interrupted_session_end`, `cli.py:4057-4063`), `1` when `run_conversation` returns `failed`, and `0` otherwise (`cli.py:4091-4100`). Exit 0 therefore means "the turn loop returned without `failed`", not "a reply row exists".
- An API call interrupted mid-stream persists the partial assistant text (`turn_api_call.py:183-191`).

### 1.4 Proactive delivery (`kit/scripts/companion_outbox.py`, `companion_dispatch.py`)

- `outbox.queue()` appends `{kind: outbox, status: queued, id: msg-<hash>}` to `<life>/outbox.jsonl`. `outbox.mark()` appends `outbox_update` rows, and `fold()` computes the current state.
- **Two lock files.** `queue()` takes `outbox.jsonl.lock` (`path.with_suffix('.jsonl.lock')`) and then calls `slf._append`, which takes `.outbox.jsonl.lock`. `mark()` takes only `.outbox.jsonl.lock`. `waiting()` and `fold()` read without any lock. `_append` already supports a `guard` callback that runs under its lock (`companion_self.py:55-67`).
- `dispatch.run()` iterates a `waiting()` snapshot and sends at most one entry per run: `verdict()`, image `review_hold()`, then `outreach.claim()` for a slot under the outreach lock (`dispatch.py:154`), then `deliver()` → `hermes_send()` (`dispatch.py:157`), then `outbox.mark(sent|failed)` (`dispatch.py:158`). Nothing prevents two dispatcher runs from holding the same snapshot entry.
- `hermes_send()` runs `hermes send --to <target> --json`. On success Hermes returns `{"success": true, "message_id": …}`. For a media send, and for a message split into chunks, only the **last** chunk's id is returned. The dispatcher treats success as a boolean and **discards `message_id`**. The adapter paths inspected return no resolved chat id. A media send that fails part-way returns an `error` after some files were delivered ("Adapter media send failed after {index}/{total} files", `send_message_tool.py:424`).
- Hermes mirrors a successful send into the target's gateway session with `mirror_to_session(platform, chat_id, text, role=…)` (`gateway/mirror.py:25`). The mirror row stores role and content only (Phase 1A contract §2).
- `companion_outreach.py send` is a second, older delivery path (used by autonomy prompts) that claims a slot and calls `hermes send` directly, not through the outbox. 1B does not change it; its no-retry rule is unchanged, and it has no outbox entry for D9 to duplicate.

### 1.5 Defects this design must close

| # | Defect | Evidence |
|---|---|---|
| D1 | There is no idempotency. A retry after a lost HTTP response, or the "you can retry" draft restored after an accepted-but-failed turn, launches a second generation and a second owner turn. | §1.1 steps 4–5, §1.2 step 1 |
| D2 | "Failed to send" is shown for accepted-but-failed, timed-out and interrupted turns. | `workspace.js:347` |
| D3 | The operation row is durable before launch, but it records neither the request nor anything that proves whether Hermes started. `interrupted` is reported for any `running` row, including one that never spawned. | `runtime.py:278`, `:323-324` |
| D4 | The busy lock is in memory and per process. A second app process (another app state, or desktop plus hosted) can run a turn on the same profile at the same time, and can run an install/update while another process chats. | `runtime.py:264-273` |
| D5 | A new session is registered as `workspace` only after completion. A crash or timeout leaves it unregistered. | `manage.py:1561`, `runtime.py:538` |
| D6 | The fallback session guess can adopt a terminal session another process created at the same moment. | `manage.py:1558` |
| D7 | A timeout or restart kills the child (not its descendants), yet a partial or complete turn may already be in `state.db`. After a hard kill of the server the child may be orphaned and still writing. | `runtime.py:163-167` |
| D8 | Operation JSON files grow without bound and keep chat text: `result.response`, `result.messages`, `stream_text` and stderr-derived `error`. | §1.2 step 3 |
| D9 | **Proactive duplicate.** A crash between `deliver()` and `outbox.mark()` leaves the entry `queued`; the next run sends it again. Two concurrent runs can also send the same entry. | `dispatch.py:154-158`, `outbox.py:103-114` |
| D10 | The platform message id Hermes returns is discarded. | `dispatch.py:115-120` |

---

## 2. Goals and non-goals

Goals:
1. One accepted workspace send launches at most one Hermes executor. Identical retries return the same receipt.
2. Acceptance is durable before any work launches. The receipt has a stable identity that survives restarts and projection rebuilds.
3. An untracked, possibly-live executor is never followed by a second writer on the same conversation (B1).
4. Every outcome is established by a named durable fact (§4.3.2). Where no such fact exists, the outcome is **unknown**, even when some content is recorded.
5. The chain request → executor → owner row → reply rows is recorded from provenance written by the executor itself, never from text or time windows.
6. Proactive dispatch claims an entry atomically, never resends an ambiguous attempt, and keeps delivery ids.
7. No chat text is persisted by the app outside Hermes's own store.

Non-goals for 1B: exactly-once execution; a new transport; the UI switch to the Phase 1A read contract (Phase 2); any external send from the workspace; new connectors; delivered-proactive transcript linkage (U7); a Hermes schema change or upstream filing; moving the prompt out of argv (U9); multi-host sharing of one profile home.

---

## 3. Identities

| Name | Made by | Form | Meaning |
|---|---|---|---|
| `client_key` | the client, once per compose-and-send intent | ULID (48-bit ms time + 80 random bits) | Idempotency key. Scoped to the **logical scope**. Its time bounds admission (§5.3). |
| logical scope | the server, captured once per request | `conversation_id` from the Phase 1A `ChatScope` (`installation label | resolved home`), plus `binding_digest` | Authorisation. Receipts are looked up only within it. |
| `home_key` | the server, at ledger open | `sha256(st_dev | st_ino | realpath)` of the profile home directory (Windows: volume serial + file index + final path) | **Physical** exclusion identity. Two labels, symlinks or app states that reach one directory get one `home_key`, one ledger file, one lease. It does not use installation labels. |
| `request_digest` | the server | `sha256` of canonical JSON `{v:1, conversation_id, destination:"workspace", session: S|null, message}` (exact UTF-8) | Binds the key to the accepted content. |
| `send_id` | the server, in the acceptance transaction | `snd_` + 26 random base32 chars | Stable receipt identity. |
| `operation_id` | the server, **reserved in the acceptance transaction** | 32 hex | Status-polling compatibility. The ledger is authoritative; the operation file is a recoverable view (§5.6). |
| `controller` | each app process at start | `ctl_` + random, plus a held OS lock `<ledger dir>/controllers/<controller>.lock` | The process that accepted a send and reads the executor's pipes. Liveness = that lock is held. |
| `claim` | the ledger | integer generation per send, plus `claim_owner` (a controller id) | The right to transition a send. Every transition is a compare-and-set on `(state, claim)`. Recovery takes ownership by incrementing it (fencing). |
| `launch_token` | the claim owner, when committing `launching` | 128-bit random | The executor's authorisation. The executor can start the turn only if its token is still the send's current token (§4.4). |
| `executor` | the executor process itself, before it enters Hermes | `{launch_token, pid, start_identity}` in `send_facts`, plus a held OS lock `<ledger dir>/executors/<send_id>.lock` | The process that runs the Hermes turn. Liveness = that lock is held (§4.5). |
| `hermes_sessions` | the executor, from Hermes's in-process state | ordered list with `created_here` flags | Sessions this executor used or created. |
| source receipts | the executor, from Hermes's insert calls | `(session_id, row_id, role, timestamp, finish_reason, write_kind)` | Causal links: rows **this executor** inserted (§4.10). |

The client owns the key because only an identifier made before sending can close the lost-response gap.

---

## 4. Server design

### 4.1 Ledger storage (U8)

**Location.** `<profile home>/.tamanitomo-sends/ledger.sqlite3`, with `controllers/`, `executors/` and `guard.lock` beside it. The directory is created `0700` and the files `0600` on POSIX; on Windows it inherits the profile home's ACL, which the app already requires to be private. A symlinked ledger, directory or lock file is refused. Every app process serving this profile home, whatever its app state or installation label, opens the same files (`home_key` is recorded in `meta` and checked at open).

**Not a cache.** The ledger is safety state. A projection rebuild never touches it. It is not re-derived from Hermes.

**Supported storage.** Local file systems on which OS advisory locks and SQLite rollback-journal locking work: ext4/btrfs/xfs/f2fs (Linux and Android internal storage), APFS/HFS+ (macOS), NTFS (Windows). At ledger open the app checks the mount type (Linux/Android `/proc/self/mountinfo`, macOS `statfs().f_fstypename`, Windows `GetVolumeInformation`). NFS, SMB/CIFS, FUSE network mounts, sdcardfs/FAT shared storage, and unrecognised types are **unsupported**: keyed sends and legacy sends are refused before acceptance with `503 send_storage_unsupported` and a plain explanation. This is the U3 rule: supervision that cannot be made safe is refused, not bypassed. Termux's private `$HOME` is internal storage and supported; confirming it on the phone host is observation O-9.

**Durability.** `journal_mode=DELETE` (not WAL), `synchronous=FULL`, `busy_timeout=5000`, `foreign_keys=ON`. Every state change is one `BEGIN IMMEDIATE` transaction. No transaction is held across a process wait, signal or network call.

**Initialisation, loss and corruption.** Two markers record that a ledger exists:
- `meta.ledger_id` (random, written at creation) and `meta.admission_floor` (a time before which keys are not admitted; creation time at first init);
- `<profile home>/.tamanitomo-sends/ledger.id`, a 0600 file holding `ledger_id`, and `<app state>/send-ledgers.json`, where each app state records the `ledger_id` it has seen per `home_key`.

At open:

| Found | Meaning | Behaviour |
|---|---|---|
| no ledger, no `ledger.id`, no app-state record for this `home_key` | first initialisation | create; `admission_floor = now` |
| ledger opens, `ledger_id` matches both markers | normal | open |
| ledger missing or unreadable, `integrity_check` fails, or `ledger_id` differs from either marker | **ledger lost** | refuse sends with `503 send_ledger_lost`. Nothing is created over it. |

Recovery from `ledger_lost` is an explicit owner action (`POST /api/chat/sends/ledger/reset`, confirmed in the UI, with the reason shown). It moves the old file aside as `ledger.lost-<time>.sqlite3` (never deletes it), creates a new ledger with a new `ledger_id` and `admission_floor = now`, and records `reset_at`. Every key minted before the floor is refused with `422 key_predates_ledger`, so a young retry of a send accepted by the lost ledger can never be accepted as new. Before a reset, the owner is shown whether any executor lock in `executors/` is still held; a held lock blocks the reset until it is released (a live executor cannot be un-tracked by a reset).

**Backup and restore.** The ledger is backed up with the profile home and is excluded from nothing. A restore of the ledger **without** its markers, or of markers without the ledger, is detected as `ledger_lost` above. A restore of the whole profile home including both markers cannot be detected by the ledger alone, because the restored state is internally consistent. Two protections remain: the app-state record (not in the profile home) usually detects it, and the documented restore procedure is "restore, then run *Reset send ledger*". The residual case (profile home and app state both restored to the same point) is stated as a limitation in `docs/CHAT_CONTRACT.md`: keys minted after the backup and within 24 h of the restore could be admitted again. Restoring a backup less than 24 h old is the only way to reach it.

### 4.2 Schema (proposed)

```sql
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
  -- schema_version=1, ledger_id, home_key, admission_floor, created_at, reset_at
CREATE TABLE sends(
  send_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,        -- logical scope
  client_key TEXT NOT NULL,
  key_time REAL NOT NULL,
  request_digest TEXT NOT NULL,
  destination TEXT NOT NULL CHECK(destination='workspace'),
  requested_session TEXT,               -- null = start a new session
  legacy INTEGER NOT NULL DEFAULT 0,    -- 1 = unkeyed POST /api/chat
  operation_id TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL,                  -- §4.3.1
  claim INTEGER NOT NULL DEFAULT 1,
  claim_owner TEXT NOT NULL,            -- controller id
  launch_token TEXT,                    -- current authorisation, null until launching
  capability TEXT NOT NULL,             -- 'full' | 'unverified_sources' (U3)
  owner_turn TEXT NOT NULL DEFAULT 'absent',  -- absent | possible | recorded | ambiguous | unknown
  reply TEXT NOT NULL DEFAULT 'none',         -- none | partial | final | unknown
  correlation TEXT NOT NULL DEFAULT 'pending',-- pending | linked | unverified | ambiguous | lost
  liveness TEXT NOT NULL DEFAULT 'none',      -- none | live | quiescent | unproven
  stop_requested_at REAL,
  deadline_at REAL,                     -- turn deadline, enforced by the executor itself
  error_code TEXT,                      -- fixed vocabulary, no free text (§5.7)
  created_at REAL NOT NULL, updated_at REAL NOT NULL,
  settled_at REAL,                      -- set once the lease is released (§5.5)
  UNIQUE(conversation_id, client_key));
CREATE INDEX sends_settled ON sends(settled_at) WHERE settled_at IS NOT NULL;
CREATE INDEX sends_open ON sends(state) WHERE settled_at IS NULL;

CREATE TABLE send_facts(               -- append-only; written by the executor or claim owner
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  send_id TEXT NOT NULL REFERENCES sends ON DELETE CASCADE,
  launch_token TEXT,                    -- executor facts carry the token that authorised them
  kind TEXT NOT NULL,                   -- §4.3.2
  data TEXT NOT NULL,                   -- JSON: ids, codes, times; never message text
  at REAL NOT NULL);
CREATE INDEX send_facts_send ON send_facts(send_id, seq);

CREATE TABLE send_events(              -- transition log (diagnostic)
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  send_id TEXT NOT NULL REFERENCES sends ON DELETE CASCADE,
  from_state TEXT, to_state TEXT NOT NULL, claim INTEGER NOT NULL,
  actor TEXT NOT NULL, at REAL NOT NULL, reason TEXT NOT NULL);  -- reason from a fixed vocabulary

CREATE TABLE lease(                    -- one row at most: one active turn per physical home
  home_key TEXT PRIMARY KEY,
  send_id TEXT NOT NULL REFERENCES sends,
  acquired_at REAL NOT NULL);
```

The ledger stores no message text, reply text, stream text, stderr or free-form error text (U4, U9).

### 4.3 States and evidence

#### 4.3.1 State machine

| State | Meaning |
|---|---|
| `accepted` | Row committed, lease held, no `launch_token` yet. No executor exists or has been authorised. |
| `launching` | A `launch_token` is committed. An executor may have been created; it cannot have entered Hermes unless an `executor_started` fact with that token exists. |
| `generating` | An `executor_started` fact exists for the current token. |
| `stopping` | Stop or timeout was requested while `generating`; the executor has been asked to interrupt. Not terminal. |
| `complete`, `failed`, `interrupted`, `not_started`, `unknown` | Outcomes; each needs the evidence in §4.3.2. |

Rejections before acceptance write no row: `409 turn_in_progress`, `409 key_conflict`, `422 key_expired`, `422 key_predates_ledger`, `503 send_storage_unsupported`, `503 send_ledger_lost`, `400` validation.

Permitted transitions. Each is a compare-and-set on `(state, claim)`, made only by the current `claim_owner`, and appends to `send_events`:

```
accepted    → launching | not_started
launching   → generating (executor_started fact) | not_started (fenced, no start fact) | unknown
generating  → stopping | complete | failed | interrupted | unknown
stopping    → complete | failed | interrupted | unknown
unknown     → complete | failed | interrupted   (only when a fact of §4.3.2 arrives late)
not_started → accepted                           (re-arm by an identical retry, §5.3)
```

`complete`, `failed`, `interrupted` and `not_started` are outcome-final (only the re-arm leaves `not_started`). `unknown` is never promoted by age or tidiness.

The **lease** is separate from the state: an outcome can be final while the lease is still held (the executor is proven to have finished its turn but its process has not exited), and an outcome can be `unknown` while the lease is released (the executor is proven dead but did not report). §4.5 defines release.

#### 4.3.2 Outcome evidence table

| Outcome | Durable fact that establishes it | Who may record the fact | Who may transition |
|---|---|---|---|
| `not_started` | (a) `spawn_failed` fact: `Popen`/`CreateProcess` raised before returning a process; or (b) the claim owner committed `launching → not_started` in a transaction that **also** replaced `launch_token` with null (fencing), and at that commit no `executor_started` fact with the old token existed. After (b), an executor holding the old token can never record `executor_started` (§4.4.3). | (a) the claim owner; (b) the claim owner's fencing transaction is itself the fact | the claim owner |
| `complete` | `executor_finished` fact with `exit=0` **and** `interrupted=false`, written by the executor after Hermes's quiet runner returned; **and** at least one assistant row in its source receipts (`reply=final`). | the executor (token-bound) | the claim owner, after ingesting it |
| `failed` | `executor_finished` with `exit≠0` and not `130`; or `exit=0` with no assistant row in a complete receipt (`error_code=no_reply_recorded`); or `executor_finished` with `timed_out=true` and no `interrupted` marker. `owner_turn` and `reply` are taken from the receipts separately. | the executor | the claim owner |
| `interrupted` | `executor_finished` with `exit=130`, or `interrupted=true` recorded by the bridge when Hermes's `KeyboardInterrupt` path ran. A stop **request** is never this fact. | the executor | the claim owner |
| `unknown` | Absence of all of the above while `executor_started` exists (or cannot be excluded), and the executor is dead or unreachable. Includes an executor killed by the kill fallback before it wrote `executor_finished`. | — (it is the absence of a fact) | the claim owner; later replaced if a finishing fact arrives |

`owner_turn`, `reply` and `correlation` are derived from source receipts only (§4.10):

| Field value | Established by |
|---|---|
| `owner_turn=recorded` | one `row_written` fact, `role=user`, `write_kind=turn`, for the send's session set |
| `owner_turn=possible` | a `row_intent` fact for a user row without its `row_written` fact (the executor died between them) |
| `owner_turn=absent` | receipts complete (`executor_finished` exists) and no user `row_written`/`row_intent` |
| `owner_turn=ambiguous` | more than one user `row_written` with `write_kind=turn` |
| `owner_turn=unknown` | receipts unavailable (`capability=unverified_sources`) or incomplete without an intent fact to bound them |
| `reply=final` / `partial` / `none` / `unknown` | assistant `row_written` facts, and whether `executor_finished` says the turn completed, was interrupted, or failed; `unknown` when receipts are incomplete or unavailable |

Recorded content without completion evidence is reported as such ("Your message and part of a reply were recorded; whether the reply finished is unknown"), never as `complete`. "Source unavailable" (state.db unreadable at read time) is a read error (Phase 1A `503 source_unavailable`), never `owner_turn=absent`.

### 4.4 Launch protocol (B1)

#### 4.4.1 Sequence

```
controller C (claim owner)                 executor E (hermes_stream.py, Hermes's interpreter)
------------------------------------------ ------------------------------------------------
T1 BEGIN IMMEDIATE: state accepted→launching,
   launch_token=K, deadline_at=now+600; COMMIT
   (on any failure here: accepted→not_started)
P  Popen(bridge, stdin=PIPE, stdout=PIPE,  E starts, imports nothing from Hermes,
   own process group / job)                   blocks reading one line from stdin
   Popen raised → T2' spawn_failed →
   not_started (definite)
J  (Windows) assign E to a job object
G  write {"go": K, "send_id", "ledger"}\n  E reads it.  EOF instead → exit 0 without
   to E's stdin                               running (C died before G)
                                           S1 acquire executors/<send_id>.lock (non-blocking;
                                              failure → exit, nothing run)
                                           S2 BEGIN IMMEDIATE: require sends.launch_token=K
                                              and state=launching; insert executor_started
                                              {pid, start_identity}; COMMIT.
                                              Token mismatch → exit without running.
                                           S3 install watchdog, persistence wrappers,
                                              session wrappers (§4.9, §4.10); enter Hermes
C  reads deltas from stdout (streaming only)  … turn …
                                           S4 insert executor_finished {exit, interrupted,
                                              timed_out}; exit (lock released by the OS)
C  on stdout EOF + exit: ingest facts, transition,
   prove quiescence (§4.5), release lease
```

The message is passed as it is today, in argv (U9: unchanged exposure, recorded in §11). No new copy of it is made in facts, events, stdin, or the operation record: the `go` line carries only the token, send id and ledger path.

#### 4.4.2 Why an untracked executor cannot run

The gap in revision 1 was "`launching` committed, `Popen` returned, controller died before recording the child". In this protocol:
- E records its own identity (S2) **before** it enters Hermes, in the same transaction that checks its authorisation. There is no instant at which E can write to `state.db` while its identity is not durable.
- If C dies before G, E sees EOF on stdin and exits without importing Hermes.
- If C dies after G, E either (i) completes S2 and is a tracked executor whose liveness is its lock (§4.5), or (ii) fails S2's token check and exits.
- Recovery never guesses which of these happened. It **fences** first (§4.4.3), then reads facts.

#### 4.4.3 Fencing

Recovery (or a stop of a `launching` send) begins with one transaction: `UPDATE sends SET claim=claim+1, claim_owner=:me, launch_token=NULL WHERE send_id=? AND claim=:seen`. After it commits, S2 of any executor holding the old token fails. Then, in a later transaction, if no `executor_started` fact with the old token exists, the send is definitely not started (`not_started`), and no executor can later start it. If one exists, it is `generating` and its liveness is checked through its lock (§4.5).

Because S2 and the fencing update both run under `BEGIN IMMEDIATE`, SQLite serialises them (one writer at a time; `BEGIN IMMEDIATE` takes the write lock at `BEGIN` [E1]). Whichever commits first wins, and the other sees its result.

#### 4.4.4 When supervision is unavailable (U3)

| Condition | Behaviour |
|---|---|
| Ledger storage unsupported (§4.1) | refuse before acceptance (`503 send_storage_unsupported`) |
| The bridge cannot run (no interpreter beside the binary, or `len(command)!=1`) | refuse before acceptance (`503 send_supervision_unavailable`). The fallback `rt.run` path cannot hold the go-gate, record its own identity or be fenced, so it cannot meet §4.4.2. This **replaces** revision 1's fallback for sends. |
| The bridge runs, but a Hermes persistence or session seam it wraps is missing | accept with `capability=unverified_sources`; the launch/lease/fencing protocol is unchanged; source links are unverified; no session is registered as `workspace`; the receipt and UI disclose it. |

The second row is a behaviour change for installations where the bridge cannot run. The Phase 1A fixture Hermes and every managed install have the interpreter; external installs with a wrapper command do not. See §12, open item O-A.

### 4.5 Executor liveness and lease release

Liveness is an OS lock, not a PID. E holds `executors/<send_id>.lock` from S1 until the process ends. The OS releases it when the process ends, however it ends (`flock` on Linux/macOS/Android; `LockFileEx` on Windows, released at process termination). The bridge child is spawned with `close_fds=True` (POSIX) and a restricted handle list (Windows, Python's default when `close_fds` is true), and Hermes's own subprocesses are spawned the same way, so descendants do not inherit the lock handle. A lock held longer than E (for example by an `os.fork` descendant) only keeps the lease longer; it can never release it early.

Proof of quiescence = the claim owner acquires `executors/<send_id>.lock` non-blocking, then releases it. Nothing else counts: a missing PID, a failed process lookup, an unsupported liveness check, a timeout or a lost heartbeat is **not** proof of death.

| Situation | Evidence | `liveness` | Lease |
|---|---|---|---|
| `accepted`, no executor authorised | no token | `none` | held (acquired at acceptance) |
| `launching`, fenced, no `executor_started` | fencing commit | `none` | **released** |
| `spawn_failed` | fact | `none` | **released** |
| executor lock acquired by the claim owner after `executor_started` | lock acquired | `quiescent` | **released** (outcome may still be `unknown`) |
| executor lock still held | lock busy | `live` | held |
| lock file cannot be opened or locked for a reason other than "busy" (I/O error, permission) | none | `unproven` | held; receipt says the app cannot confirm Hermes has stopped |
| executor lock busy after interrupt, grace and kill attempts | lock busy | `live` | held; state stays `stopping`/`unknown`; UI says a previous reply may still be running and a new message will wait |

A held lease blocks every new send on that physical home (`409 turn_in_progress`), including a confirmed new-key "Send again" (U2). There is no age-based expiry. A host reboot always resolves `live`/`unproven` for local storage, because it ends every process and lock.

**Descendants.** Hermes tools may start subprocesses. They are not the transcript writer (only the Hermes process inserts rows), so they do not gate the lease. They are still cleaned up (below) and a cleanup that cannot be confirmed is recorded as `descendants=unverified` in the receipt's diagnostic data.

**Per-OS process handling.**

| | Linux / Android (Termux) | macOS | Windows |
|---|---|---|---|
| Group | `start_new_session=True`; E is group leader | same | E assigned to a job object at step J, before G, so E cannot run before assignment; `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` set [E3] |
| Identity recorded in S2 | pid, `/proc/self/stat` field 22, boot id | pid, `sysctl kern.proc.pid` start time | pid, `GetProcessTimes` creation time |
| Signal target check before any signal | lock still busy **and** a `pidfd_open(pid)` handle whose start time matches (Python ≥ 3.9, Linux ≥ 5.3; otherwise the start-time check without a pidfd, with a residual race stated) | lock busy and start time matches; residual race between check and `killpg` stated | the job handle (no PID signalling) |
| Graceful interrupt | ledger flag read by E's watchdog → `_thread.interrupt_main()` inside E (§4.9); no signal needed | same | same |
| Kill tree | `killpg(pgid, SIGKILL)` | same | `TerminateJobObject` |
| Controller dies, executor alive | E continues; its watchdog enforces `deadline_at`; recovery supervises it through the lock and facts | same | the job handle closes with the controller and the OS kills the job's processes (kill-on-close); recovery then acquires the lock |
| Proof of death | lock acquired | lock acquired | lock acquired |

`CREATE_NEW_PROCESS_GROUP` alone is not used as a kill-tree mechanism: Python documents `send_signal(CTRL_BREAK_EVENT)` separately, and `Popen.kill()` on Windows terminates only the child [E2]. Whether the job handle lifetime and assignment behave as specified on the CI Windows runner is observation O-8; until it is observed, Windows is labelled "orphan recovery not verified on this OS".

### 4.6 Recovery ownership

Recovery runs for a send whose `claim_owner` controller lock is acquirable (the controller is dead) or on the owner's own restart. It runs eagerly once at app start for every open send in the ledger, and lazily on any `GET`/`POST` touching the conversation. There is no background poller.

1. **Claim.** `BEGIN IMMEDIATE`; re-read the row; if `claim_owner`'s controller lock is not acquirable and `claim_owner` is not this controller, stop (the owner is alive). Otherwise fence: `claim=claim+1`, `claim_owner=me`, and `launch_token=NULL` when the state is `launching`. `COMMIT`. Two competing recovery processes both try this compare-and-set on the `claim` they read; exactly one commits, the other's update matches no row and it backs off.
2. **Read facts** (a short read transaction).
3. **Probe liveness** outside any transaction (§4.5). If `live`: leave the state, record `liveness=live`, and supervise. The new owner cannot read E's stdout, so streaming for that turn ends; the facts and receipts still arrive in the ledger. E's own watchdog still enforces the deadline and stop flag.
4. **Transition** in a new `BEGIN IMMEDIATE` that re-checks `claim = my claim`. A stale observer whose claim was superseded changes nothing.
5. **Release** the lease in the same transaction as the transition when §4.5 allows.

A delayed controller that wakes after losing its claim (for example after a long suspend) finds its compare-and-set fails and only reads. Its stream-reading thread stops, and its `Popen` object is dropped without killing E; kill authority belongs to the current claim owner only.

### 4.7 Installation-wide exclusion

`Operations.busy` stays as it is (in-process). A physical guard is added beside it:

- `<Hermes installation root>/.tamanitomo-installation.lock` (an OS lock file, 0600).
- Exclusive mutations (install, update, gateway start/stop, hook approval, profile create/delete, the native console) hold it for their whole duration, and **before** starting, check every profile ledger under that root (`<root>` and `<root>/profiles/*`): any held `lease` row whose executor lock is busy, or whose state is not settled, refuses the mutation ("A chat reply is still running").
- A send's acceptance takes the installation lock briefly (non-blocking; busy → `409 installation_busy`, not accepted), then the ledger transaction, then releases it. So a mutation cannot start between a send's acceptance and its lease, and a send cannot be accepted while a mutation runs.
- Acquisition order, everywhere: installation lock → ledger transaction → (never) a lock held across a process wait. The executor never takes the installation lock.

This keeps today's rule that an update never runs under a live turn, and extends it across app processes. Today's in-process rule that one chat blocks every other action in the installation is kept for the same process. Across processes, chats on **different** profiles of one installation may run concurrently; that was already possible before 1B and is not a new exposure. App processes older than 1B do not take the installation lock; mixing them with 1B processes on one installation is unsupported and documented (§11).

### 4.8 Crash and interruption table

"Retry" means the client repeats the **same key and payload**. "Owner" is the current claim owner.

| Crash or event | Durable state | Recovery | `owner_turn` | Lease | Retry returns |
|---|---|---|---|---|---|
| Before the acceptance commit | no row | — | absent | none | fresh acceptance |
| After acceptance, before T1 | `accepted` | `not_started` | absent | released | re-arm, same `send_id` (§5.3) |
| After T1, `Popen` raised | `launching` + `spawn_failed` | `not_started` | absent | released | re-arm |
| After T1, before or after `Popen`, before G | `launching` | fence; no start fact → `not_started`; E (if any) exits on EOF | absent | released | re-arm |
| After G, before S2 commits | `launching` | fence; if S2 lost the race → `not_started`; if S2 won → `generating` path | absent / per receipts | per §4.5 | re-arm or receipt |
| After S2, before any Hermes write | `generating` | E alive → supervise; E dead without `executor_finished` → `unknown` | absent if no intent fact | released once lock acquired | `unknown` receipt |
| E between `row_intent` and `row_written` (user row) | `generating` | E dead → `unknown` | possible | released | `unknown` receipt |
| After the owner row, before any reply | `generating` | E alive → supervise; E dead → `unknown` | recorded | released once dead | `unknown` ("recorded; reply not known") |
| After partial output, E dead | `generating` | `unknown` | recorded | released | `unknown`, `reply=partial` |
| After the final reply row, before `executor_finished` | `generating` | E alive → wait for the fact; E dead → `unknown` (a reply row is not completion evidence) | recorded | per §4.5 | `unknown`, `reply=partial` |
| After `executor_finished`, before C's transition | `generating` | ingest → `complete`/`failed`/`interrupted` | per receipts | released once lock acquired | that outcome |
| After C's final transition, before the HTTP response | outcome | — | — | — | the same outcome |
| Controller dies, E alive (POSIX) | `generating` | recovery supervises; E finishes or hits its deadline and writes `executor_finished` | per receipts | released after E exits | final outcome later |
| Controller dies, E alive (Windows) | `generating` | job closes → E killed → lock acquirable → `unknown` unless `executor_finished` was written | per receipts | released | `unknown` or outcome |
| Stop pressed | `generating` → `stopping` | §4.9 | per receipts | per §4.5 | outcome from evidence |
| Deadline | `generating` → `stopping` | §4.9 | per receipts | per §4.5 | outcome from evidence |
| Provider error / truncation | `generating` | `executor_finished exit=1` → `failed` | per receipts | released | `failed` |

No path launches a second executor for one `send_id` except the re-arm of a definite `not_started`. No new send is accepted on a physical home while a possibly-live executor holds its lease.

### 4.9 Stop and timeout

- `POST /api/chat/sends/{send_id}/stop` sets `stop_requested_at` and moves `generating → stopping` (compare-and-set). On `launching` it fences instead (§4.4.3), which yields `not_started` or `generating→stopping` from evidence. It returns the receipt in its current state. It never returns `interrupted` because a stop was requested.
- E's watchdog thread (installed at S3) reads `stop_requested_at` and `deadline_at` from the ledger once a second with a read-only connection. When either applies, it records `stop_seen` and calls `_thread.interrupt_main()`, which raises `KeyboardInterrupt` in Hermes's main thread, the same path as Ctrl-C (`cli.py:4057-4063`). The same mechanism works on every OS and does not depend on the controller being alive.
- Grace: 15 s after `stop_seen`. If E's lock is still busy, the owner kills the tree (§4.5 table), records `kill_sent`, and re-probes. The outcome remains whatever the facts establish: a turn that finished before the interrupt landed is `complete`; one that raised `KeyboardInterrupt` is `interrupted`; one killed before writing `executor_finished` is `unknown`. A timeout that ends in `exit=1` is `failed` with `error_code=timeout`.
- If the kill cannot be confirmed (lock still busy), the state stays `stopping` and the lease stays held (§4.5).

### 4.10 Correlation (B2)

#### 4.10.1 Source receipts written by the executor

At S3 the bridge wraps, inside E only, `SessionMessagesMixin.append_message`, `append_messages_batch`, `_insert_message_rows` and `replace_messages` on the `SessionDB` class, and `create_session` (`hermes_state_sessions.py:362`). For each call:

- **Before** Hermes's write: a `row_intent` fact `{session_id, role, write_kind}` (no content), committed. If this ledger write fails, the wrapper raises before Hermes writes, so an unrecorded row cannot exist (fail closed; the turn fails and the receipt says why).
- **After** Hermes's write returns: a `row_written` fact `{session_id, row_id, role, timestamp, finish_reason, write_kind}` using the row id Hermes returned (`append_message`) or stored in `msg["_row_id"]` (`_insert_message_rows`).
- `write_kind` is `turn` for `append_message`/`append_messages_batch` called by the turn loop, and `rewrite` for inserts made under `replace_messages` or compression. `replace_messages` also records `session_rewritten {session_id, mode}`.
- `create_session` records `session_created {session_id, parent_session_id}`.

These facts are causal: they are written by the process that performed the insert, bound to its `launch_token`, and cover every row **this executor** wrote and no row any other process wrote. A terminal writing into the same session, even with the same text, never appears in them. No watermark, time window or text comparison selects rows, so there is no lower or upper bound to get wrong, and later turns and continuation rewrites by other processes cannot be swept in.

Whether the turn loop's user-row insert can be told apart from compression copies by these call sites alone is observation O-3/O-4. If a turn records more than one `role=user, write_kind=turn` row, `owner_turn=ambiguous` and no candidate is chosen.

#### 4.10.2 Sessions and workspace registration (D5, D6)

- A session is attributed to the send only when a `session_created` fact exists from this executor (a new session or a continuation made during the turn). The resumed `requested_session` is recorded in `hermes_sessions` with `created_here=false` and is **not** relabelled: a terminal session resumed from the workspace stays whatever it was.
- The Phase 1A classifier gains a second source of workspace sessions: `session_created` facts in the ledger (read-only), unioned with `.tamanitomo-sessions.json`. The `session_created` fact is committed in E before the session row itself is inserted (it is the `row_intent` of `create_session`), so no attributable row exists in a session that the ledger does not already attribute. This closes the crash window revision 1 left between "early event printed" and "parent recorded it".
- The post-completion `note_workspace_session` call stays (for older readers of the JSON file) but is no longer the authority.
- The before/after session diff (D6) is removed from both routes.

#### 4.10.3 Identity at read time

Links are joined into Phase 1A reads by the full identity envelope, not a row key alone. A link resolves to a projection row only when **all** of these hold for the currently authorised scope:
- the projection row's `source_session`/`source_message` equal the receipt's `(session_id, row_id)`;
- its stored fingerprint equals `fingerprint(row_id, session_id, role, timestamp)` computed from the receipt (`chat_sources.py:302`);
- its source kind and account/channel namespace are the ones this send can produce (`workspace`, no platform account);
- no known platform message id on the row conflicts with one the receipt knows (`platform_conflict`, `chat_sources.py:308`). Workspace rows normally carry none; if one appears, it is a different message by the R2 rule.

| Case | Result |
|---|---|
| Projection rebuilt (new `projection_id`), source unchanged, still authorised | the join finds the new opaque ids; `correlation.send_id` appears on them |
| Source row gone, or present with a different fingerprint, or a conflicting known platform id | `correlation=lost` for that link; the new holder of the source id never gets the old `send_id` |
| Binding changed so workspace rows are no longer authorised (Phase 1A revocation) | receipts in that scope return state and codes only; `owner_message_id`/`reply_message_ids` are omitted and no source content is returned through receipt or operation routes |
| `state.db` unreadable | the receipt's links are `unavailable` for this read; outcome fields are unaffected |

No store-replacement detection stronger than the Phase 1A read contract is claimed.

Each request captures its `ChatScope` once. A `session` supplied with a send must belong to the authorised conversation **and** be one the current binding would project (workspace or authorised terminal session); profile membership alone is not enough.

#### 4.10.4 Provisional and final bubbles

Stream frames carry `send_id`. The client's DOM ids are role- and part-specific: `snd_…:owner`, `snd_…:stream`, `snd_…:reply:<n>` (U1, §6). When a projected reply row arrives carrying `correlation.send_id` and part index, it replaces `snd_…:stream` / the matching `reply:<n>` element instead of appending a new bubble.

#### 4.10.5 Completion is separate from content

§4.3.2 governs. A public assistant row proves that content was recorded, not that the turn finished.

#### 4.10.6 Unverified fallback (U3)

When a wrapped seam is missing, E records `capability_downgrade {missing:[…]}` at S3 and the send runs with `capability=unverified_sources`: `owner_turn`/`reply` are `unknown` unless `executor_finished` says otherwise, `correlation=unverified`, no session is registered, no link is shown. The launch, fencing, lease and liveness protocol is unchanged. D5 stays open for that turn and the receipt says so.

### 4.11 Destination

`destination` is fixed to `workspace`; the request schema has no field that could change it. A badge on an earlier message is provenance only. 1B adds no external send from the workspace. The outbox, its dispatcher, `may_send`, quiet hours, approval/review and caps are unchanged except as §7 describes.

---

## 5. API

### 5.1 Routes

```
POST /api/chat/sends
  body: {client_key, conversation_id, message, session: S|null}
  202 {send: Receipt, operation: {id}}                     new acceptance
  200 {send: Receipt, operation: {id}, replay: true}        existing receipt for this key
  409 {error: "key_conflict", send_id}                     same key, different digest
  409 {error: "turn_in_progress"}                          another send holds the lease (not accepted)
  409 {error: "installation_busy"}                         an installation mutation is running
  422 {error: "key_expired" | "key_predates_ledger"}
  503 {error: "send_storage_unsupported" | "send_supervision_unavailable" | "send_ledger_lost"}
  400 invalid input, wrong conversation_id, unauthorised session

GET  /api/chat/sends/{send_id}          → Receipt (recovery runs first when needed)
GET  /api/chat/sends?key=<client_key>   → Receipt | 404
GET  /api/chat/sends?open=1             → receipts not settled, newest 20
POST /api/chat/sends/{send_id}/stop     → Receipt (§4.9)
POST /api/chat/sends/ledger/reset       → explicit ledger-loss recovery (§4.1)

Receipt = {send_id, client_key, conversation_id, state, owner_turn, reply, correlation,
           capability, liveness, settled, error: {code}|null, created_at, updated_at,
           owner_message_id|null, reply_message_ids: []}   // omitted when not authorised (§4.10.3)
```

Every route captures `ChatScope` once, then checks `conversation_id` against it. A `send_id` from another scope returns 404.

### 5.2 Order of checks for `POST /api/chat/sends`

1. Validate input and capture scope; reject a `conversation_id` that is not the captured one.
2. Open the ledger (storage, loss checks).
3. **Look up `(conversation_id, client_key)`.** If a row exists: equal digest → `200 replay` with that receipt, whatever the lease, age or state (except the `not_started` re-arm below); different digest → `409 key_conflict`. This runs **before** the busy check, so identical concurrent retries all get the one receipt, never a misleading `turn_in_progress` (M-2).
4. No row: check the key's time against the admission rules (§5.3).
5. Check supervision availability (§4.4.4).
6. Installation lock (non-blocking), then one `BEGIN IMMEDIATE`: re-run step 3 inside it (a concurrent identical request may have committed since); if the lease is held → `409 turn_in_progress`; else insert the send with `send_id`, `operation_id`, `claim=1`, `claim_owner=me`, acquire the lease, `COMMIT`. Release the installation lock.
7. Create the operation view and hand the send to the launcher (§4.4).

Same-key requests in different logical scopes are independent receipts. A wrong `conversation_id` is never permission to look in another scope.

### 5.3 Admission, replay and re-arm

| Situation | Result |
|---|---|
| Existing receipt, same digest, any state except `not_started` | `200 replay`. Nothing launches. No age limit while the receipt is retained. |
| Existing `not_started`, same digest, key time within 24 h | re-arm: `not_started → accepted` (same `send_id`, new claim), subject to the lease and installation checks of step 6, then launch |
| Existing `not_started`, same digest, key older than 24 h | `200 replay` of the `not_started` receipt with `rearm: "expired"`. Nothing launches. The client may offer a new send (a new key; no duplicate risk, because non-execution is definite). |
| Existing receipt, different digest | `409 key_conflict` |
| No receipt, key time within 24 h and ≥ `admission_floor`, not > 5 min in the future | accept |
| No receipt, key older than 24 h | `422 key_expired`. Never a fresh send. |
| No receipt, key time < `admission_floor` | `422 key_predates_ledger` |
| Key > 5 min in the future | `400` |

The server stores no request text, so it can never relaunch from a digest. The only way the original payload returns after a definite `not_started` is an identical client resubmission (step 3 compares the digest). A newer draft is a different digest and a different key.

Age never authorises a launch and never erases evidence: an expired key with an existing receipt still replays.

### 5.4 After `unknown` (U2)

The UI first calls `GET /api/chat/sends/{send_id}` (or `?key=`). "Send again" is offered only when the receipt says `liveness` is `quiescent` or `none` (lease released) and the outcome is still `unknown`. It mints a **new key** after the owner confirms "This may send your message twice." It then goes through the ordinary acceptance path, so it still gets `409 turn_in_progress` while any lease is held.

### 5.5 Ledger retention (B3)

A send is **settled** when its lease is released (`liveness` is `none` or `quiescent`) and its state is `complete`, `failed`, `interrupted`, `not_started` or `unknown`. `settled_at` is set in the releasing transaction.

Prune predicate, exactly: delete a send (its facts and events cascade) iff `settled_at IS NOT NULL AND settled_at < now − 30 days`. Unsettled sends (`accepted`, `launching`, `generating`, `stopping`, or any send with `liveness` `live`/`unproven`) are never pruned, whatever their age.

Safety after pruning: every pruned key is at least 30 days past settlement and therefore more than 24 h old, so an absent key is refused by admission (`key_expired`); no tombstone is needed for replay safety. Historical `send_id` correlation on reads is available for 30 days after settlement; after that, rows show no `correlation.send_id` and the contract says so.

Bounded work: one pass deletes at most 500 sends, chosen by `SELECT send_id FROM sends WHERE settled_at < ? ORDER BY settled_at LIMIT 500` on the partial index `sends_settled`. A pass runs after each acceptance, once at app start, and when `GET ?open=1` is served. An installation that stops sending is still pruned at its next app start; an installation that never runs the app again does not grow either. `send_events` per send is bounded by the state machine (at most 12 transitions) plus recovery attempts, which are counted in one fact rather than logged per attempt.

The 200-bytes-per-row figure in revision 1 is withdrawn. M-23 measures the real file size, including facts, events and indexes, at 10,000 settled sends with a realistic fact count per send (about 10–30 `row_intent`/`row_written` facts for a tool-using turn), and the result is reported as measured.

### 5.6 Operation records as views (B3, B5)

- `operation_id` is reserved in the acceptance transaction. `Operations.submit()` gains an `ident=` parameter so it uses the reserved id instead of generating one.
- Crash between the ledger commit and the operation file: the send is `accepted` with no executor; recovery makes it `not_started` and re-arm works; the operation view is recreated from the ledger on demand.
- `GET /api/operations/{id}`: if the id belongs to a send (`sends.operation_id`), the response is built from the ledger (status mapped as `accepted/launching/generating/stopping → running`, outcomes as themselves, `unknown` → `interrupted` with the §6.3 wording for old clients), so a missing or stale operation file never implies that a new send is needed. The file is a cache of that view.

### 5.7 What operation files may contain (U4)

New chat operation records are written through an explicit **allowlist**: `id, scope, profile, kind, label, status, progress, percent, started_at, finished_at, send_id, error_code, error, format`. For chat:
- `progress` is one of a fixed set of strings ("Starting", "Waiting for …", "Replying", "Complete", "Needs attention").
- `error` is the fixed human sentence for `error_code`, never exception text, stderr or final output. (Redacting credential-like substrings does not remove conversation text, so it is not relied on.)
- `stream_text` stays in the in-memory row only and is excluded by the allowlist at every `_save`.
- `result` in memory is `{session, send_id, note, response, messages}`; only `{session, send_id, note}` are persisted.
- `format: 2` marks records written under this allowlist.

Tests read the actual files at an intermediate progress point, at completion and at failure (M-23).

**Legacy response contract.** A client polling a chat operation still receives `result.response` and `result.messages`:
- while the row is in memory (the live process), from the in-memory result;
- otherwise, reconstructed at request time from the send's linked source rows through the Phase 1A read path under the **current** authorisation (`messages` from the linked rows; `response` from the linked final assistant row);
- otherwise (links lost, not authorised, source unavailable, or receipt pruned), `result.response = null`, `result.messages = []`, `result.content_retained = false`. A reply is never regenerated because content is missing.

**Retention of operation files.** Applies to terminal (`status` ≠ `running`) records with `format: 2` in this app state's `operations/` directory. Prune a record iff `finished_at < now − 7 days` **OR** it is not among the newest 500 terminal `format: 2` records by `finished_at`. At most 500 files are removed per pass, oldest first; a pass runs at app start and after each chat operation finishes. `running` records are never pruned by this rule (their safety state is in the ledger). Operation records without `format: 2` (pre-1B chat records and all non-chat operations) are left untouched in 1B; the app reports their count, and removing pre-1B chat records that contain text is a separate owner-approved action (§12, O-B).

### 5.8 The legacy `POST /api/chat`

Kept for old clients. Each call gets a ledger row with `client_key = legacy-<uuid>` and `legacy=1`, so it takes part in the lease, launch protocol, receipts and retention. It is **not** idempotent: two calls are two sends. The new UI never falls back to it after a network error (§6).

---

## 6. Minimal client correction (U1, changeset C3)

Scope: `workspace.js` chat submit, recovery on load, and bubble status only.

State kept in `sessionStorage` under the profile's chat key:
- `draft`: the editable compose text (as today).
- `pending`: `{client_key, conversation_id, profile, session, message, send_id?, operation_id?}`, **immutable** once created; one at a time. It is separate from `draft`, so editing or clearing the compose box never changes it, and a new draft never replaces it.

Flow:
1. Send: mint `client_key`, write `pending`, clear the compose box into a fresh draft, draw `snd_pending:owner` "sending…", `POST /api/chat/sends`.
2. `202`/`200`: store `send_id`/`operation_id` in `pending`; rename DOM ids to the `send_id` forms (§4.10.4); poll.
3. Network error or lost response: retry the **same** `pending` payload and key (bounded backoff). A `GET ?key=` 404 while the original POST may still be in flight is not permission to mint a new key; the client keeps retrying the POST with the same key, which the server resolves (§5.2).
4. On reload: if `pending` exists for this profile, resume with step 3, then poll. A `pending` from another profile is left alone and never attached to this chat.
5. Settled outcome: clear `pending`. A late completion updates only its own `send_id` bubbles; it never clears or overwrites a newer draft.

Wording (receipt facts decide it; nothing else):

| Receipt | Owner bubble | Compose box |
|---|---|---|
| pre-acceptance rejection, `not_started` | "Not sent" | the message is offered back as a draft |
| `complete` | time sent | — |
| `failed`, `owner_turn=recorded` | "Your message was recorded; the reply failed" + **Ask again** | not restored |
| `failed`, `owner_turn` absent/unknown | "The reply failed. Whether your message was recorded is unknown." | not restored |
| `interrupted` | "Stopped" (+ partial reply shown as partial) | — |
| `unknown`, acceptance confirmed | **"The app accepted your request. Whether Hermes recorded it or finished a reply is unknown."** Send again only per §5.4 | not restored |
| acceptance itself not confirmed (all retries failed) | "Not confirmed. The app will check again with the same request." | kept in `pending`, not as a draft |

"Ask again" and "Send again" are new user intents with new keys, never transport retries.

Preserved: media authorisation and `inlineMedia`, public-output filtering, per-profile draft scope, the single-action exclusion (`activeOperation`) for non-chat actions.

Synthetic browser checks (M-22): double submit, lost response, reload mid-turn, failed generation, unknown, draft edited during a turn, profile switch during a turn. This is not certification of the Phase 2 UI or phone layouts.

---

## 7. Proactive delivery (B4)

### 7.1 One lock, one claim

All outbox writes (`queue`, `mark`, and the new claim/outcome rows) take **one** lock: the `_append` lock `.outbox.jsonl.lock`. `queue()`'s extra `outbox.jsonl.lock` is kept (it serialises the capacity check with its append) and is always taken **before** the `_append` lock, never after. A dispatcher run additionally holds `<life>/.dispatch.run.lock` (non-blocking; busy → "another dispatcher is running", exit 0) for the whole run. This run lock is not the outbox data lock: `queue()` and `mark()` never take it, so holding it during the network call does not block queueing. It ensures one dispatcher per life directory; the per-entry claim below is what makes a stale snapshot harmless.

Lock order: run lock → outbox lock (released) → outreach lock (released) → outbox lock (released). No outbox or outreach lock is held during `hermes send`.

### 7.2 Attempt protocol

An attempt is identified by `attempt = <run_id>:<n>` where `run_id` is random per dispatcher run.

1. **Claim.** `_append(outbox_update{status: dispatching, attempt, run_id}, guard=…)`. The guard, under the outbox lock, re-reads the fold and refuses unless the entry's current status is exactly `queued`. Only the run whose append succeeds may continue. A dispatcher holding a stale snapshot fails here and does nothing further for that entry.
2. **Checks that do not send.** Image review and `verdict()` as today. A hold/withhold appends its outcome **with the attempt** (`withheld`, `expired`) or releases (`queued`, `release_reason`, attempt) — permitted only while the attempt is at `dispatching`.
3. **Slot.** `outreach.claim()` as today. Refused → append `queued` with `release_reason=cap` and the attempt (the entry waits; no slot was used). Granted → append `slot_reserved {attempt}`.
4. **Send marker.** Append `sending {attempt}` immediately before starting `hermes send`.
5. **Outcome.** Append exactly one of `sent`, `failed`, `unknown`, `withheld` with the attempt (§7.5), only if the entry's current status is `sending` with the same attempt (guarded).

Every guarded append validates `(attempt, expected status)`. A late update for a different or superseded attempt is refused and does not change the entry.

### 7.3 Abandoned attempts

At the start of a run (holding the run lock), any entry whose last update is from a different `run_id` and is not an outcome belongs to a dispatcher that is no longer running (only one run can hold the run lock). It is resolved from its last phase:

| Last phase | Meaning | Resolution |
|---|---|---|
| `dispatching` | no slot, no send | back to `queued` (definite non-dispatch; no slot was used) |
| `slot_reserved` | slot used, not sent | `failed` with `not_dispatched: true` (definite non-dispatch; the existing rule that a used slot is not retried) |
| `sending` | `hermes send` may have run | `unknown`, "the dispatcher stopped mid-send; delivery is not known". **Never resent.** |

A timeout is not the evidence here; the run lock is. An old dispatcher that is still running holds the run lock, so its attempts are never resolved under it.

### 7.4 Resolving `unknown` later

An `unknown` outcome may be replaced only by an outcome row carrying the **same attempt** and positive evidence (a `message_id` or an explicit platform result). 1B has no producer of such late results; the guard exists so that a future reconciler cannot overwrite an unrelated attempt or append a contradictory terminal result. Nothing sends again.

### 7.5 Outcome classification (U5)

| `hermes send` result | Outcome | Resent? |
|---|---|---|
| exit 0, `success: true`, not `skipped`, `message_id` present | `sent` + ids | no |
| exit 0, `success: true`, no `message_id` | `sent`, `message_id: null`, `id_missing: true` | no |
| `success: true, skipped: true` | `withheld` with Hermes's reason | no |
| JSON `error` whose string is on the verified pre-platform list | `failed` (definite) | no |
| any other JSON `error` (including partial media sends, `send_message_tool.py:424`), timeout, `OSError`, killed, non-JSON stdout, non-zero exit without JSON | `unknown`, with the error code and any ids kept | **no** |

The pre-platform list starts **empty**; an error string joins it only with a Hermes source reference showing it is returned before any adapter call (observation O-7). Until then every `error` is `unknown`.

### 7.6 Delivery record

A `sent` or `unknown` row stores `{attempt, platform, requested_target, recipient_resolved: <platform account/chat id> | null, message_id, id_scope: "last_chunk", mirrored: true | false | null}`. `recipient_resolved` is `null` unless the native result states it; the adapter paths inspected return no chat id, so it will usually be `null`, and the record says so rather than copying the symbolic target. `mirrored` is `null` when not reported. `id_scope: "last_chunk"` stays visible in every view: one id is never presented as the complete list for a split or media delivery.

### 7.7 What 1B still cannot certify (U7)

The app knows that and where it attempted delivery and holds the platform id Hermes gives. It still cannot link a delivery to the transcript row a viewer sees, because Hermes's mirror row holds no id. Joining by text or time is forbidden, and so is deduplicating mirror rows by text or time. Delivered-proactive provenance stays **unsupported** in the read contract. An upstream proposal (store the platform id in the mirror row) may be drafted for the owner; it is not filed, and Hermes is not modified.

### 7.8 Mixed versions

- A pre-1B dispatcher reading a 1B outbox: `fold()` keeps the last status, so `dispatching`/`slot_reserved`/`sending`/`unknown` entries are not `queued` to it and are not sent again (M-20 variant).
- A pre-1B dispatcher **already running** with a stale snapshot does not take the run lock or the claim guard, so it can still send an entry that a 1B dispatcher claimed. Running old and new dispatchers on one life directory at the same time is **unsupported**; the upgrade path is to stop the old one first. This limit is stated in the release notes when 1B ships (release work is not authorised here).

---

## 8. Observations still needed

Each is a synthetic, pinned observation against Hermes `0e9fc2cc15` (the fixture revision) with `tests/mock_provider.py`, not a live run. The design is safe whatever each one shows; the right column says what changes.

| # | Observation | How | If unknown or unsupported |
|---|---|---|---|
| O-1 | The bridge can install the go-gate before importing Hermes, and `cli` imports no Hermes module that touches `state.db` before `_run_quiet_single_query` | trace `sqlite3.connect` in the fixture | the gate still prevents the turn; a pre-turn state.db open is harmless (reads, schema checks) and noted |
| O-2 | Each wrapped seam (`append_message`, `append_messages_batch`, `_insert_message_rows`, `replace_messages`, `create_session`) exists and is the only row-insert path used by fresh, resumed, continuation and error turns | fixture turns per path with the mock provider; compare `state.db` row ids against the facts | any row not in the facts → that path is `capability=unverified_sources` |
| O-3 | When the owner user row is inserted relative to the **provider request** (not the first delta) on each path: fresh, `--resume`, compression continuation, provider error before the first byte | mock provider records request arrival; facts record the insert; compare order (M-10) | the protocol does not depend on it; the result is recorded per path, never generalised from one |
| O-4 | Whether compression copies user rows with `append_messages_batch` inside a turn (would make `write_kind=turn` ambiguous) | force compression in a fixture turn | such copies are classified `rewrite` by call path, or the owner turn becomes `ambiguous` |
| O-5 | Whether every Hermes writer path (terminal `--resume`, gateway, cron) takes `session_turn_leases` for the same key | fixtures for each | not relied on; stated in the contract |
| O-6 | `_thread.interrupt_main()` from the watchdog reaches Hermes's `KeyboardInterrupt` handler during a provider stream and during a tool call | mock `hang` and `deltas` scenarios | a missed interrupt reaches the kill fallback; outcome is from facts |
| O-7 | Which `hermes send` error strings are returned before any adapter call | read `send_message_tool.py` per string, with line refs | the list stays empty; all errors `unknown` |
| O-8 | Windows job assignment before `go`, kill-on-close on controller death, `TerminateJobObject` of descendants, lock release timing | one real (unmocked) test on the CI Windows runner | Windows is labelled "orphan recovery not verified on this OS" |
| O-9 | Termux private `$HOME` mount type and `flock` behaviour on the phone host | a synthetic check on a test profile, no live data | Android is labelled unverified; storage check refuses unknown types |

A local fake CLI is not evidence for O-2 to O-6; they need the pinned Hermes code path.

---

## 9. Affected files and changesets

Three separable changesets, each with its tests, in this order. This sequencing is a proposal; implementation needs approval.

| Changeset | Files | Contents |
|---|---|---|
| **C1** durable send and recovery | `kit/app/chat_sends.py` (new): ledger, storage checks, states, facts, fencing, lease, liveness, recovery, retention. `kit/app/hermes_stream.py`: go-gate, executor lock, S2, watchdog, persistence/session wrappers, `executor_finished`. `kit/app/runtime.py`: `Runtime.chat()` launch protocol and process group/job; `Operations.submit(ident=)`, persisted-field allowlist, operation retention; installation lock helper. `kit/app/chat_routes.py`: `/api/chat/sends*`, `correlation.send_id` join. `kit/app/manage.py`: legacy `/api/chat` through the ledger, before/after guess removed; installation lock around mutations. `kit/app/chat_sources.py`: workspace sessions from `session_created` facts; capability table. `docs/CHAT_CONTRACT.md`: "Sending" section, restore limitation. `release-files.json`. | Tests: `tests/test_chat_sends.py`, `tests/test_send_recovery_subprocess.py`, `tests/test_operations_privacy.py`; `tests/mock_provider.py` gains `hang`. |
| **C2** dispatcher safety | `kit/scripts/companion_outbox.py`: statuses, guarded claim/outcome appends, lock order. `kit/scripts/companion_dispatch.py`: run lock, attempt phases, abandoned-attempt resolution, classification, delivery record. `kit/app/chat_sources.py`: proactive capability "ids captured; transcript linkage unsupported". | `tests/test_dispatch_claim.py` |
| **C3** minimal client correction | `kit/app/static/workspace.js` (chat submit, `pending`, recovery on load, wording, DOM ids). | synthetic browser checks (M-22) |

---

## 10. Synthetic acceptance matrix

Every case uses a synthetic Hermes home, the fixture `state.db` schema (v30), the pinned Hermes revision where the case touches Hermes code, and `tests/mock_provider.py`. No real credentials, source data or messages. **Crash tests** run the app (or the executor) as a subprocess started by the test harness; the harness injects a test-only subclass or monkeypatches the production module at import (via a `sitecustomize` placed only on the test's `PYTHONPATH`), so the production transition functions run unmodified and the crash is a `SIGKILL`/`TerminateProcess` sent at a hook the double exposes. No environment variable read by shipped code triggers a crash (U6). Nothing below is a result; all are proposed.

"Provider counter" counts requests reaching the mock provider; "launch counter" counts executors that recorded `executor_started`. They are reported separately (M-11).

| # | Case | Expected |
|---|---|---|
| M-1 | Two identical `POST`s with one key, sequential | 1 launch; the second is `200 replay`, same `send_id` |
| M-1a | Same key while the first send's lease is held | `200 replay` of that receipt, not `turn_in_progress` |
| M-2 | One key, 20 concurrent requests across 2 app processes on one home | 1 launch; 19 `200 replay`; no `turn_in_progress` for the key's own receipt |
| M-2a | Two app states with different installation labels (and a symlinked home path) for one profile home | one `home_key`, one ledger, one lease; logical scopes stay separate |
| M-2b | Two recovery owners race on one dead-controller send | exactly one claim commit; the other changes nothing |
| M-2c | Two identical re-arm requests of one `not_started` send race | one re-arm, one launch |
| M-2d | Chat accepted in process A while process B starts an update on the same installation, and the reverse order | the second is refused (`installation_busy` / mutation refused); never both |
| M-3 | Same key, different text / session / conversation | `409 key_conflict`; ledger unchanged |
| M-4 | Different keys racing on one home | one accepted; the other `409 turn_in_progress` |
| M-5 | Lost HTTP response; client retries with the key | same receipt; launch counter 1 |
| M-5a | POST outcome unknown to the client; `GET ?key=` returns 404 while the POST is still in flight | client retries the same key, never mints a new one; one receipt |
| M-6 | Key older than 24 h with no row; key 10 min in the future; key before `admission_floor` | 422 / 400 / 422; nothing launched |
| M-6a | Existing receipt replayed after its key is older than 24 h | `200 replay`; nothing launched |
| M-6b | `not_started` re-arm with a key older than 24 h | replay with `rearm: "expired"`; nothing launched |
| M-6c | Ledger deleted / corrupted / `ledger_id` mismatched after sends were accepted; then a retry of a young key | `503 send_ledger_lost`; after an explicit reset, the young key is `422 key_predates_ledger` |
| M-6d | Pruning with unsettled sends older than 30 days present | unsettled sends survive; settled ones older than 30 days are removed, ≤ 500 per pass |
| M-7 | Kill at every row of §4.8 | recovered state, `owner_turn`, `reply`, lease and retry result exactly as the table says |
| M-7a | Kill the controller between `Popen` returning and `go` | executor exits on EOF without importing Hermes; recovery fences → `not_started`; provider counter 0 |
| M-7b | Kill the controller after `go`, before S2; recovery fences concurrently with S2 | exactly one of: `not_started` (S2 refused) or `generating` (S2 first); never both, never an unrecorded executor |
| M-7c | Executor lock file unlockable for a reason other than busy | `liveness=unproven`, lease held, no new send accepted |
| M-8 | Controller killed, executor alive (POSIX) | recovery supervises; executor finishes and writes `executor_finished`; outcome from it; lease released after exit; no second launch |
| M-8a | Stale callback: the old controller wakes after losing its claim | its transitions are refused by the claim check |
| M-8b | PID reuse: executor dead, its PID reused by an unrelated process | lock acquirable → quiescent; no signal sent to the unrelated process |
| M-8c | A new-key "Send again" while the old executor may still run | `409 turn_in_progress` |
| M-9 | Provider `disconnect_before_done`, `truncated`, `malformed` | `failed` with `owner_turn` from receipts; never "Not sent" |
| M-9a | Assistant row written, executor killed before `executor_finished` | `unknown`, `reply=partial`; never `complete` |
| M-9b | `state.db` unreadable at read time | links `unavailable`; `owner_turn` unchanged; never `absent` |
| M-10 | O-3 per path: fresh, resumed, continuation, provider error before first byte | records when the owner row is inserted relative to the provider request, per path, as observed |
| M-11 | `recover` scenario (drop, then complete) | launch counter 1; provider counter may be 2 (Hermes's own retry in one turn); `complete` |
| M-12 | Stop during `deltas` | `stopping` → `interrupted` from `exit=130`; partial reply linked as `partial` |
| M-12a | Stop races with normal completion | outcome from facts: `complete` if `executor_finished exit=0` came first, `interrupted` otherwise; never `interrupted` from the request alone |
| M-13 | Deadline with `hang` (timeout shortened by the test double) | interrupt, then kill if needed → outcome from facts; lock acquirable afterwards; no descendant left (checked per OS) |
| M-13a | Kill cannot be confirmed (lock stays busy, simulated by a double holding the lock) | `stopping`, lease held |
| M-14 | Projection rebuild while authorised | `correlation.send_id` resolves to the new ids |
| M-14a | Binding change revokes workspace rows | receipt and operation routes return no links and no content |
| M-15 | Source replaced / fingerprint changed / conflicting known platform id / different source namespace | `correlation=lost`; never attached to the new holder |
| M-16 | Foreign terminal writes exactly one user row in the session during the turn, with **equal text**, while the executor writes none | not linked; `owner_turn=absent` (receipts complete) |
| M-16a | Foreign rows after the turn, and a continuation rewrite by another process | never linked to the older send |
| M-16b | Two `write_kind=turn` user rows from the executor (forced) | `owner_turn=ambiguous` |
| M-18 | New session, kill after `session_created` fact, before the session row / after it | session attributed from the fact; no attributed row exists without it |
| M-18a | Resume of a pre-existing terminal session | not relabelled workspace |
| M-19 | Bridge unavailable | `503 send_supervision_unavailable`; nothing accepted |
| M-19a | A wrapped seam missing (patched out) | `capability=unverified_sources`; no session registered; launch/lease protocol unchanged |
| M-20 | Dispatcher crash after `sending`, before the outcome | next run resolves `unknown`; nothing resent |
| M-20a | Two dispatchers load the same queued entry before either claims | second fails the run lock, or, with the run lock bypassed by a double, fails the claim guard; one send |
| M-20b | Crash after `dispatching`; after `slot_reserved` | `queued` (no slot used); `failed, not_dispatched` |
| M-20c | Late same-attempt outcome after `unknown`; late outcome for a different attempt | same attempt with evidence replaces `unknown`; different attempt refused |
| M-20d | Pre-1B `fold()` reading a 1B outbox | claimed/unknown entries not `queued` |
| M-21 | `hermes send` returns id / no id / `skipped` / partial media error / other error / timeout | outcomes per §7.5; `recipient_resolved: null` when not reported; `mirrored: null` when not reported; `id_scope` present |
| M-22 | Legacy `POST /api/chat` with an old client polling `result.response`, in-process and after restart | response present while retained; `content_retained: false` when not; never regenerated |
| M-22a | New client: double submit, lost response, reload, failed generation, unknown, draft edited mid-turn, profile switch, status lookup from another app instance | behaviours of §6; the UI never falls back to the unkeyed route |
| M-23 | Size and privacy: 10,000 settled sends with realistic facts | measured ledger size and acceptance latency (desktop, labelled); prune pass bounded by the index; operation files at progress/complete/failure contain no prompt, reply, stream or stderr text |

Local full suite plus the CI matrix (Linux 3.11/3.13/3.14, Windows and macOS smoke), as in 1A. Windows and macOS each need at least one real (unmocked) executor-death and kill-tree test, or an explicit "not verified on this OS" line.

---

## 11. Compatibility

- **No Hermes schema change and no Hermes code change.** `state.db` is opened read-only by the app. The executor's wrappers run inside Hermes's process around Hermes's own calls and do not alter their arguments or results; Hermes still writes its rows.
- **Bridge protocol.** Additive: the go-gate is new stdin input. A new server with an old bridge file is impossible within one release (both ship together); a mismatched bridge refuses to start without `go` handling and the send is `not_started`.
- **Legacy `POST /api/chat`.** Works through the ledger; not idempotent (§5.8). Refused where supervision is unavailable (§4.4.4).
- **Projection schema.** Unchanged; `correlation.send_id` is computed in routes.
- **Operation records.** New chat records are allowlisted; pre-1B records are untouched and still readable.
- **Outbox.** Old entries fold unchanged. Mixed old/new dispatchers at the same time are unsupported (§7.8).
- **Mixed app versions on one installation.** A pre-1B app process does not use the ledger, lease or installation lock. Running it beside a 1B process on the same installation is unsupported and stated.
- **Prompt exposure (U9).** The message remains in the executor's argv, readable by the same OS user through `/proc/<pid>/cmdline` or process listings. 1B neither fixes nor widens this, and the metadata-only ledger does not change it.

---

## 12. Remaining open items

The reviewer's U1–U9 are decided (§0). These are the choices this revision had to make that the reviewer or owner may want to change:

| # | Item | Proposal in this revision |
|---|---|---|
| O-A | Installs where the bridge cannot run lose workspace chat (§4.4.4), where revision 1 kept them on an unverified fallback | refuse, per U3's "reject before acceptance if safe supervision is unavailable". Alternative: allow those installs only the legacy route with a visible "unsafe retry" warning. |
| O-B | Pre-1B chat operation files that contain text | report the count; delete only on an explicit owner action (a later task) |
| O-C | On Windows, controller death kills the turn (kill-on-close); on POSIX the turn continues under recovery supervision | accept the difference and document it; the alternative (no kill-on-close) leaves no way to reach the job after the controller dies |
| O-D | Whole-profile-home restores within 24 h can re-admit a key (§4.1) | document the "Reset send ledger after restore" procedure |

---

## 13. What this document does not claim

- No Phase 1B code, test or result exists. The matrix is proposed, not passing.
- When Hermes first persists the owner row is **not established** (O-3/M-10). The protocol does not depend on it.
- The Hermes seams in §4.10.1 are private code at `0e9fc2cc15`; their completeness (O-2) is not established.
- The Windows job-object behaviour and Termux storage behaviour (O-8, O-9) are not observed.
- Mirror linkage (§7.7) is unsolved; delivered-proactive provenance remains unsupported.
- Exactly-once execution is not claimed. At most one executor per key, and no second writer beside a possibly-live one, are the claims.
- `ASTRA_PHASE0_REVIEW_R2.md` and `PHASE1A_HANDOFF.md` were not on disk; this revision does not claim compliance with them. It follows PHASE1B_REVIEW_R1, PHASE1A_REVIEW_R3 and the code at `fc5c1e4`.
- Nothing was merged, tagged, released or deployed; no live record, credential or message was touched; nothing was filed upstream.

---

## Appendix A. Change summary against revision 1 (`b074ae9`)

| Finding | What changed |
|---|---|
| B1 launch ownership and orphans | Separate controller, claim (fencing generation) and executor identities (§3). Go-gated launch in which the executor records its own identity under a token check before entering Hermes (§4.4). Liveness is an OS lock held by the executor, not a PID or heartbeat; the lease is released only on proof of quiescence, and `unproven` keeps it (§4.5). Two-recoverer competition by compare-and-set (§4.6). Per-OS process table incl. Windows job object (§4.5). Physical `home_key` independent of installation labels (§3). Cross-process installation guard with fixed lock order (§4.7). Removed: the 30 s heartbeat/stale-lease rule and "interrupt orphans immediately". |
| B2 turn identity and completion | Correlation from executor-written source receipts around Hermes's insert calls, replacing the watermark/sole-candidate rule (§4.10.1). Session attribution from a `session_created` fact committed before the session row (§4.10.2). Full Phase 1A identity envelope at read time; rebuild vs revocation split (§4.10.3). Outcome evidence table: `complete` needs `executor_finished`, not a reply row (§4.3.2). Stop is `stopping` until evidence (§4.9). `unknown` wording corrected (§6). M-10 now observes the provider-request boundary per path (O-3). |
| B3 replay, retention, receipts | Existing-key lookup before the busy check (§5.2). Receipts replay after the admission window; absent expired keys refused; re-arm age rule (§5.3). `send_id`/`operation_id` reserved at acceptance; operation file is a recoverable view (§5.6). Retention only for settled sends, exact predicate, bounded indexed passes, start-up pass (§5.5). Ledger loss/corruption/restore policy with `admission_floor` and explicit reset (§4.1). Size estimate withdrawn; measured in M-23. |
| B4 dispatcher claim | One outbox lock with a guarded claim that requires `queued`; attempt ids validated on every later update; run lock identifies abandoned attempts; phase-based resolution; slot released only when no slot was used; same-attempt late resolution; resolved recipient nullable; last-chunk scope kept; mixed-version limit stated (§7). |
| B5 client and persisted text | Corrected the `stream_text` inventory (§1.2). Persisted-field allowlist; no stderr-derived text (§5.7). Operation retention predicate stated exactly, only for `format: 2` records (§5.7). Legacy `result.response`/`messages` through an authorised transient view (§5.7). Minimal client contract with an immutable `pending` send, same-key recovery, receipt-driven wording and role-specific DOM ids (§6). |
| Matrix | M-1–M-23 kept; variants added per the reviewer's table (§10). Crash harness per U6. |
