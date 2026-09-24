# Phase 1B design: send receipts, idempotency and interruption

Status: **design, revision 3 with the focused corrections requested by PHASE1B_REVIEW_R3, marked (R4).** C0 was accepted as verification work. The **C1 core** now exists as isolated, callable components (`kit/app/chat_sends.py`, `send_executor.py`, `send_protocol.py`, `send_quiescence.py`) exercised by synthetic tests only; **no route, UI, release file or real profile uses it**, and the current workspace send path is unchanged. Evidence: [`Phase1B_C0_Results.md`](Phase1B_C0_Results.md), [`Phase1B_C1_Results.md`](Phase1B_C1_Results.md).

- Branch: `test/phase1-conversation-contract`
- Revision 1: `b074ae9`. Revision 2: `7907066` (answered PHASE1B_REVIEW_R1). Revision 3 (this document) answers PHASE1B_REVIEW_R2 with focused corrections; the structure and numbering of revision 2 are kept. Every passage changed by revision 3 is marked **(R3)**; Appendix B lists them.
- Designed against: `fc5c1e4` (code identical to `7e616d2`, accepted in PHASE1A_REVIEW_R3). Phase 1A acceptance is retained unchanged.
- Hermes inspected: `hermes-agent` at `0e9fc2cc15` (full hash `0e9fc2cc152b4a4d9fd736f107412ace2a0c2555`), the same revision as the Phase 1A fixtures. Hermes line references below are to that revision and describe private code that can change; every capability taken from it is detected at run time and has a safe fallback (§8). **(R3)** C0 ran real pinned-Hermes code against synthetic homes; where a statement below rests on a C0 observation it cites the case (`C0:` + test name).
- Gate: **(R4)** PHASE1B_REVIEW_R3 authorised the isolated C1 core and its synthetic tests on an unmerged branch (`test/phase1b-c1-core`). Routing normal sends through it (C1 activation), C2 and C3 remain separate, later changesets, each with its own review.

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

**(R3) Decisions recorded from PHASE1B_REVIEW_R2.** Again not implementation authorisation.

| ID | Decision | Where applied |
|---|---|---|
| O-A | Where safe supervision is unavailable (the bridge cannot run, or the platform's supervision is not established), workspace sends are **refused** before acceptance, on the keyed and the legacy route alike. No "unsafe legacy" escape hatch. Missing source-correlation seams alone may still run as explicitly unverified. | §4.4.4, §4.5 |
| O-B | Pre-1B chat operation files that contain text: report their count, leave them untouched. Deleting them needs a separate owner decision. Their text is not described as removed. | §5.7 |
| O-C | Windows kill-on-close on controller death versus POSIX continuation is a **proposed** platform policy. It is not enabled on any platform until that platform's supervision evidence exists (O-8, O-9, O-11). | §4.5 |
| O-D | Restore: an explicit **Reset send ledger** is mandatory before sends resume after any known ledger rollback or profile restore. An undetected coherent rollback can replay a missing, still-admissible request; this is disclosed, not claimed to be detected. | §4.1 |

**(R4) Decisions recorded from PHASE1B_REVIEW_R3.** Implementation of the isolated C1 core is authorised; activation is not.

| ID | Decision | Where applied |
|---|---|---|
| O-E | **Hold migration and rollout, not engineering.** The current user-facing route stays unchanged while the C1 core is developed, so no platform loses chat because its supervisor is untested. The **new** path refuses activation on an unsupported or unverified supervisor, and a send that has entered the new protocol never falls back to the unkeyed old path. Windows/macOS need real supervisor tests on CI hosts, and Termux needs synthetic device evidence, before their activation is proposed. | §4.4.4, §4.5 |
| O-F | **Gap latching without re-failing a committed source write.** A receipt gap is latched, later unreceipted work is refused before it starts, and no clean completion is claimed. Shown with the real exception, interruption and cleanup paths and in-process concurrency; reporting failure never blocks quiescence recovery. | §4.10.1; C1 results §3 |
| O-G | **Coverage and containment are activation gates.** Before the new path is activated for ordinary tool-capable chat: a real tool-using turn, interruption during a tool, full CLI compression continuation, and the declared descendant boundary must be exercised. A process that might still write is not made safe by labelling its correlation unverified. | §4.5, §8, §12 |
| O-H | **Structured attempt identity in C2.** Charge records gain an explicit `attempt` field; substring matching of `reason` is never production identity. Additive; quota calculation unchanged. C2 remains separate. | §7.2 |

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
- **Persistence seam (R3, corrected).** Revision 2 named five methods. That list was incomplete and its commit boundary was wrong:
  - **The only commit point is `SessionDB._execute_write`** (`hermes_state.py:773-858`). It runs a callback inside `BEGIN IMMEDIATE`, commits, and returns the callback's result. On a `locked`/`busy` error raised inside the callback it rolls back and **re-runs the whole callback** (`:840-842`). If the commit step itself raises after the callback ran, settlement is unknown and the error propagates (`:786-790`).
  - `_insert_message_rows` (`hermes_state_messages.py:421-437`) inserts **in the caller's transaction** and sets `msg["_row_id"]` before any commit. `append_messages_batch` (`:293-315`) and `replace_messages` (`:439-470`) do more SQL after it returns. A row id seen there is a candidate, not a committed row. SQLite may hand a rolled-back id out again, AUTOINCREMENT included [S]. C0 reproduced all three failure traces on the pinned code: a rolled-back batch, a retried callback that yields the same ids twice, and a rolled-back id that is reused by a foreign writer (C0: `RevisionTwoDefects`).
  - More row-insert paths exist, all of them inside `_execute_write` callbacks: `archive_and_compact` (`:510-565`), the pure-SQL tail clone `_clone_message_rows` (`:498-506`, a multi-row `INSERT … SELECT` with no per-row id), `rewind_to_message`'s replacement row (`:1071`), `publish_compression_child` (`hermes_state_compression.py:181-245`, which inserts the child **session row directly**, not through `create_session`, then clones rows), and session import (`hermes_state_portability.py:469`).
  - `create_session` and `ensure_session` are **upserts** (`hermes_state_sessions.py:362-370`). A call does not show that the session was absent.
  - Every write above runs inside the Hermes process that runs the turn. C0 observed that, before the turn begins, the quiet CLI also commits several maintenance writes in that process (`prune_empty_ghost_sessions`, `prune_sessions`, `sweep_orphaned_sessions`, `update_system_prompt` and others). It did so after `import cli` returned; nothing opened `state.db` during the import (C0: `test_state_db_is_written_before_the_turn_but_not_during_import`).
  - Owner-row timing (O-3): in the five fresh-session paths and the resume path C0 ran, the owner row was committed **before** the first provider request, 80–150 ms earlier. The paths were normal, provider error before the first byte, disconnect, truncation, and hang/interrupt (C0: `RealTurns`). The protocol does not depend on this order. It is recorded per path and not generalised.
- **Hermes's own turn lease.** `state.db` has `session_turn_leases` (`hermes_state_common.py:462`). `agent/turn_facade_lease.py:271` acquires one per turn when the database supports it, and appends that carry `turn_lease_holder` are refused when the lease is lost (`hermes_state_messages.py:177-231`). **Not established:** whether every writer (a terminal `--resume`, the gateway, cron) acquires it for the same key, so this revision does not rely on it for exclusion (observation O-5).
- **Exit codes.** A quiet one-shot run exits `130` after `KeyboardInterrupt` (after `_emit_interrupted_session_end`, `cli.py:4057-4063`), `1` when `run_conversation` returns `failed`, and `0` otherwise (`cli.py:4091-4100`). Exit 0 therefore means "the turn loop returned without `failed`", not "a reply row exists". **(R3)** It does not mean "the reply finished" either. With the mock `truncated` and `disconnect_before_done` scenarios, the pinned CLI exited 0 and stored an ordinary text assistant row with `finish_reason='length'`, after 4 stream requests inside one executor (C0: `test_truncated_and_disconnected_replies_exit_zero`).
- **(R3, corrected.)** Revision 2 said an API call interrupted mid-stream persists the partial assistant text (`turn_api_call.py:183-191`). C0 did not observe that on the path it ran. `_thread.interrupt_main()` after two stream deltas from the mock `hang` scenario ended the turn with exit 130, and **no** assistant row was stored (C0: `test_interrupt_main_reaches_the_turn_during_a_stream`). Other interrupt points, a tool call among them, were not observed. The design allows for both results.

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
7. **(R3, wording corrected.)** No **new** durable chat text in the send ledger or in new-format (`format: 2`) operation records. This does not cover the retained Phase 1A content projection, client `sessionStorage`, or pre-1B operation files, which are deliberately left as they are (O-B). It is not a claim that the app keeps no chat text outside Hermes.

Non-goals for 1B: exactly-once execution; a new transport; the UI switch to the Phase 1A read contract (Phase 2); any external send from the workspace; new connectors; delivered-proactive transcript linkage (U7); a Hermes schema change or upstream filing; moving the prompt out of argv (U9); multi-host sharing of one profile home.

---

## 3. Identities

| Name | Made by | Form | Meaning |
|---|---|---|---|
| `generation` **(R3)** | the server, when a ledger is created or explicitly reset; returned by bootstrap (§5.1) | 128-bit random, opaque | The reset fence. The client freezes it with the key and resubmits it unchanged. A request carrying a generation that is not the ledger's current one is never accepted as new (§5.3). It is not a rollback detector (§4.1). |
| `client_key` | the client, once per compose-and-send intent | ULID (48-bit ms time + 80 random bits) | Idempotency key. Scoped to the **logical scope**. Its time bounds freshness only (§5.3), never the reset fence. |
| logical scope | the server, captured once per request | `conversation_id` from the Phase 1A `ChatScope` (`installation label | resolved home`), plus `binding_digest` | Authorisation. Receipts are looked up only within it. |
| `home_key` | the server, at ledger open | `sha256(st_dev | st_ino | realpath)` of the profile home directory (Windows: volume serial + file index + final path) | **Physical** exclusion identity. Two labels, symlinks or app states that reach one directory get one `home_key`, one ledger file, one lease. It does not use installation labels. |
| `request_digest` | the server | `sha256` of canonical JSON `{v:1, conversation_id, destination:"workspace", session: S|null, message}` (exact UTF-8) | Binds the key to the accepted content. |
| `send_id` | the server, in the acceptance transaction | `snd_` + 26 random base32 chars | Stable receipt identity. |
| `operation_id` | the server, **reserved in the acceptance transaction** | 32 hex | Status-polling compatibility. The ledger is authoritative; the operation file is a recoverable view (§5.6). |
| `controller` | each app process at start | `ctl_` + random, plus a held OS lock `<ledger dir>/controllers/<controller>.lock` | The process that accepted a send and reads the executor's pipes. Liveness = that lock is held. |
| `claim` | the ledger | integer generation per send, plus `claim_owner` (a controller id) | The right to transition a send. Every transition is a compare-and-set on `(state, claim)`. Recovery takes ownership by incrementing it (fencing). |
| `launch_token` | the claim owner, when committing `launching` | 128-bit random | The executor's **revocable** authorisation. The executor can start the turn only if its token is still the send's current token (§4.4). Fencing (recovery, reset) clears it; clearing it says nothing about the past. |
| `attempt_id` **(R5)** | the claim owner, in the same T1 transaction | 128-bit random, not secret | The **immutable** identity of one launch attempt. S2 requires it; `executor_started` records it; start evidence is looked up by it, never by the token; the executor lock is per attempt (`executors/<send_id>.<attempt_id>.lock`). A re-arm (same `send_id`) starts a new attempt. |
| `executor` | the executor process itself, before it enters Hermes | `{launch_token, pid, start_identity, pgid, lock_identity}` in `send_facts`, plus a held OS lock `<ledger dir>/executors/<send_id>.lock` | The process that runs the Hermes turn. **(R3)** Liveness of the executor = that lock, checked against the recorded `lock_identity` (§4.5). Quiescence of the managed execution also needs its process group or job to be empty (§4.5). |
| `hermes_sessions` | the executor, from its committed write receipts | ordered list with `created_here` flags | Sessions this executor used or created. **(R3)** `created_here=true` only from a committed session insert that C0's recorder saw as **fresh** (absent before, present after, in the same transaction). An upsert, an ensure or a failed create never sets it (§4.10.2). |
| source receipts **(R3)** | the executor, at Hermes's commit boundary | one `write_committed` fact per committed `_execute_write`: `{wid, method, attempts, rows:[(session_id, row_id, role, class)], sessions:[(session_id, fresh)], unidentified}` | Causal links: rows **this executor committed** (§4.10.1). Candidates seen inside a callback that rolled back, was retried or never finished are never published. |

The client owns the key because only an identifier made before sending can close the lost-response gap.

---

## 4. Server design

### 4.1 Ledger storage (U8)

**Location.** `<profile home>/.tamanitomo-sends/ledger.sqlite3`, with `controllers/`, `executors/` and `guard.lock` beside it. The directory is created `0700` and the files `0600` on POSIX; on Windows it inherits the profile home's ACL, which the app already requires to be private. A symlinked ledger, directory or lock file is refused. Every app process serving this profile home, whatever its app state or installation label, opens the same files (`home_key` is recorded in `meta` and checked at open).

**Not a cache.** The ledger is safety state. A projection rebuild never touches it. It is not re-derived from Hermes.

**Supported storage.** Local file systems on which OS advisory locks and SQLite rollback-journal locking work: ext4/btrfs/xfs/f2fs (Linux and Android internal storage), APFS/HFS+ (macOS), NTFS (Windows). At ledger open the app checks the mount type (Linux/Android `/proc/self/mountinfo`, macOS `statfs().f_fstypename`, Windows `GetVolumeInformation`). NFS, SMB/CIFS, FUSE network mounts, sdcardfs/FAT shared storage, and unrecognised types are **unsupported**: keyed sends and legacy sends are refused before acceptance with `503 send_storage_unsupported` and a plain explanation. This is the U3 rule: supervision that cannot be made safe is refused, not bypassed. Termux's private `$HOME` is internal storage and supported; confirming it on the phone host is observation O-9.

**Durability.** `journal_mode=DELETE` (not WAL), `synchronous=FULL`, `busy_timeout=5000`, `foreign_keys=ON`. Every state change is one `BEGIN IMMEDIATE` transaction. No transaction is held across a process wait, signal or network call.

**Initialisation, loss and corruption (R3).** Revision 2's `admission_floor` compared a server time with a client-minted key time. It failed twice. The first ordinary send could predate a floor its own POST created. A client clock up to five minutes ahead let an old key pass the floor of a reset ledger. C0 reproduced both (C0: `test_revision_two_rejects_the_first_ordinary_send`, `test_revision_two_readmits_an_accepted_key_after_reset`). Both uses of the floor are replaced:

- **First-use bootstrap.** `GET /api/chat/sends/bootstrap` (§5.1) creates the ledger if it does not exist, under the ownership guard below, and returns `{conversation_id, generation}`. The client calls it **before** it mints a key and freezes its pending send (§6). `POST /api/chat/sends` never creates a ledger. On a profile home with no ledger it answers `409 not_bootstrapped` and accepts nothing. So the first ordinary send is ordered after initialisation, with no dependence on clocks (C0: `test_bootstrap_before_minting_admits_the_first_send`).
- **Generation fence.** `meta.generation` is random at creation and at every explicit reset. The client stores it in `pending` with the key and resubmits both unchanged. With no receipt for the key, a request whose generation is not the current one is refused with `409 generation_changed` and is **never** accepted as new. Changing the key after an ambiguous POST does not change this (§6). Key-time freshness (§5.3) is a separate check and never acts as the fence (C0: `test_generation_fence_refuses_a_prior_generation_request`, `test_freshness_is_separate_from_the_fence`).
- Loss markers are kept for **detecting a missing or mismatched file**, not rollback: `meta.ledger_id`, `<profile home>/.tamanitomo-sends/ledger.id`, and `<app state>/send-ledgers.json`.

At open:

| Found | Meaning | Behaviour |
|---|---|---|
| no ledger, no `ledger.id`, no app-state record for this `home_key` | never initialised | bootstrap creates it; a POST is `409 not_bootstrapped` |
| ledger opens, `ledger_id` matches both markers | normal | open |
| ledger missing or unreadable, `integrity_check` fails, or `ledger_id` differs from either marker | **ledger lost** | refuse sends with `503 send_ledger_lost`. Nothing is created over it, not even by bootstrap. |

**Explicit reset (R3, serialised).** Recovery from `ledger_lost`, and the mandatory step after a known restore, is an owner action: `POST /api/chat/sends/ledger/reset`, confirmed in the UI with the reason shown. It uses the same ownership protocol as acceptance and launch, not a separate path:

1. Take `<ledger dir>/guard.lock` **exclusively**. Acceptance (§5.2 step 6), bootstrap and executor registration (S2, §4.4.1) hold it **shared** for the length of their transaction, so none of them can interleave with a reset. A reset that finds it busy answers `409 ledger_busy` and changes nothing (C0: `test_reset_cannot_interleave_with_executor_registration`).
2. If the old ledger is readable, fence it in one transaction: every send with a `launch_token` gets `launch_token=NULL, claim=claim+1`. An executor that has not yet run S2 can then never register (C0: `test_reset_fences_launch_tokens_before_replacing_the_ledger`).
3. Check quiescence for every executor recorded by an unsettled send, using **(R4) the one quiescence contract of §4.5** (identity-checked lock **and** a demonstrably empty group), the same function used for lease release, retention and installation mutations. Any `live` or `unproven` result refuses the reset (`409 executor_live`) and nothing is moved. A lock file with no recorded executor is probed for "busy" (its executor never entered Hermes). If the old ledger is unreadable, the executor's identity that it wrote **into its lock file** at S1 (pid, pgid, lock identity) is the record, checked by the same contract; an empty acquirable lock file belongs to an executor that died before S2. **(R4)** The C0 admission prototype's reset opened locks with `open('a+b')` (creating them) and checked only "busy"; that is not the contract and is not used. A lock file is never deleted to unblock a reset.
4. Move the old file aside as `ledger.lost-<time>.sqlite3` (never delete it). Create the new ledger with a new `ledger_id` and a new `generation`. Record `reset_at`.

After a reset, a retry of a key accepted under the old ledger carries the old generation, so it is `409 generation_changed`, and the client says that whether it was sent before is unknown (§6).

**Backup and restore (R3, corrected).** Revision 2 overstated what the markers detect, in three ways.
- A constant `ledger_id` does **not** detect a rollback within the same ledger. Suppose the ledger is backed up while its id is A, key K is then accepted and executed in ledger A, and only the older ledger file is restored. All three markers still read A, K's receipt is missing, and K can be accepted as new while it is still admissible.
- The app-state record does not help, because nothing requires it to be restored.
- The window is not tied to the backup's age. What matters is the missing key's own admission age: 24 h under §5.3.

The generation does not detect this either, because the restored file carries the same generation (C0: `test_a_database_only_rollback_replays_a_missing_key_under_either_rule`). The design therefore claims only this:
- Loss of the file or of a marker, corruption, and a replaced ledger whose `ledger_id` differs are detected (`ledger_lost`).
- **After any known restore or rollback of the profile home or of the ledger, *Reset send ledger* is mandatory before sends resume.** It puts every earlier request in an old generation (C0: `test_explicit_reset_after_a_known_restore_closes_it`).
- **Stated limitation:** an unannounced, coherent rollback of the ledger (with or without its markers) can re-admit a request whose receipt it lost, if that request's key is still within the admission window and its generation still matches. Detecting it automatically would need an external non-rollback checkpoint. That is not designed in 1B and is not promised. `docs/CHAT_CONTRACT.md` will state this with the reset procedure.

### 4.2 Schema (proposed)

```sql
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
  -- schema_version=1, ledger_id, home_key, generation (R3; replaces admission_floor), created_at, reset_at
CREATE TABLE sends(
  send_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,        -- logical scope
  client_key TEXT NOT NULL,
  key_time REAL NOT NULL,
  request_digest TEXT NOT NULL,
  destination TEXT NOT NULL CHECK(destination='workspace'),
  requested_session TEXT,               -- null = start a new session
  source_kind TEXT NOT NULL,            -- (R3) 'workspace' | 'terminal': the permitted kind for this send (§4.10.3)
  source_namespace TEXT,                -- (R3) account/channel namespace for that kind, null for workspace
  generation TEXT NOT NULL,             -- (R3) the ledger generation the request carried
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

Rejections before acceptance write no row: `409 turn_in_progress`, `409 key_conflict`, `409 generation_changed` (R3), `409 not_bootstrapped` (R3), `409 ledger_busy` (R3, a reset is in progress), `422 key_expired`, `503 send_storage_unsupported`, `503 send_supervision_unavailable`, `503 send_ledger_lost`, `400` validation. (`422 key_predates_ledger` is withdrawn with the admission floor.)

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
| `complete` | **(R3)** `executor_finished` with `exit=0`, `interrupted=false` **and `receipts_complete=true`**, written by the executor after Hermes's quiet runner returned; **and** in its committed receipts, exactly one `user_turn` row and at least one **`public_output`** row for the send's session set, the last of which has `finish_reason='stop'` (`reply=final`). An arbitrary assistant insert does not qualify. Neither does a tool-call-only or text-less row, a display/summary/observed row, or any row copied by a rewrite, compaction, clone or compression (`class ≠ public_output`, §4.10.1). | the executor (token-bound) | the claim owner, after ingesting it |
| `failed` | `executor_finished` with `exit≠0` and not `130`; or **(R3)** `exit=0` with complete receipts in which the last `public_output` row does not have `finish_reason='stop'` (`error_code=reply_incomplete`, `reply=partial`; C0 observed exit 0 with `finish_reason='length'` for truncation and disconnect); or `exit=0` with complete receipts and no `public_output` row (`error_code=no_reply_recorded`); or `executor_finished` with `timed_out=true` and no `interrupted` marker. `owner_turn` and `reply` are taken from the receipts separately. | the executor | the claim owner |
| `interrupted` | `executor_finished` with `exit=130`, or `interrupted=true` recorded by the bridge when Hermes's `KeyboardInterrupt` path ran. A stop **request** is never this fact. | the executor | the claim owner |
| `unknown` | Absence of all of the above while `executor_started` exists (or cannot be excluded), and the executor is dead or unreachable. Includes an executor killed by the kill fallback before it wrote `executor_finished`. | — (it is the absence of a fact) | the claim owner; later replaced if a finishing fact arrives |

`owner_turn`, `reply` and `correlation` are derived from source receipts only (§4.10).

**(R3, corrected R4) Receipt coverage** is one of these, and it is decided before any field value below. The same restrictions apply **whether or not `executor_finished` exists** (review R3 5.2: revision 3's *bounded* definition omitted unidentified rows, contradicting the field table):
- **complete**: `executor_finished` exists and says `receipts_complete=true`, **and** every restriction below holds.
- **bounded**: no `executor_finished`, **and** every restriction below holds.
- Restrictions: every `write_intent` has its outcome fact; there is no `write_unsettled` and no `receipt_gap`; **no committed write carries unidentified rows** (`unidentified=0` everywhere, including a session insert whose effect could not be observed); and no `user_turn`/`public_output` row lies outside the send's session set.
- **incomplete**: anything else. Incomplete coverage never establishes an absence: a clone that produced unidentified rows followed by executor death is `owner_turn=unknown`, `reply=unknown`, never `absent`/`none` (tested on the derived receipt, not only the recorder's counter).
- **unavailable**: `capability=unverified_sources`.

`unverified_sources` and `incomplete` never mean "no row was written". The only thing that means that is complete or bounded coverage together with an absent row.

| Field value | Established by |
|---|---|
| `owner_turn=recorded` | exactly one committed `user_turn` row for the send's session set |
| `owner_turn=absent` | coverage **complete or bounded**, and no committed `user_turn` row. This includes "no `write_intent` after S2 at all": `write_intent` is committed before Hermes's callback and fails closed, so the absence of any intent proves no write was attempted. |
| `owner_turn=possible` | a transcript `write_intent` with no outcome fact (the executor died inside the write), or a `write_unsettled` fact (the commit raised after the callback), with no `receipt_gap` and no unidentified rows, and no committed `user_turn` row. Either way the owner row may or may not be on disk. |
| `owner_turn=ambiguous` | more than one committed `user_turn` row |
| `owner_turn=unknown` | coverage **incomplete** because of a `receipt_gap`, unidentified rows, turn rows outside the session set, or a finish fact without `receipts_complete`; or coverage **unavailable** |
| `reply=final` / `partial` / `none` / `unknown` | `final`: the `complete` rule above. `partial`: at least one committed `public_output` row without `final`. `none`: coverage complete or bounded, and no `public_output` row. `unknown`: coverage incomplete or unavailable. |

These are four different observations, and they are never merged: the executor did not run (`not_started`); no committed owner row (`absent`); an unresolved intent (`possible`); receipt coverage unavailable (`unknown`).

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
                                           S1 open/create executors/<send_id>.<attempt_id>.lock (R5), lock it
                                              (non-blocking; failure → exit, nothing run);
                                              record its (st_dev, st_ino)
                                           S2 guard.lock shared; BEGIN IMMEDIATE: require
                                              sends.launch_token=K and state=launching; insert
                                              executor_started {pid, start_identity, pgid,
                                              lock_identity}; COMMIT; release guard.
                                              Token mismatch → exit without running.
                                           S3 install watchdog and the commit-boundary
                                              recorder (§4.9, §4.10.1); then import cli and
                                              enter Hermes
C  reads deltas from stdout (streaming only)  … turn …
                                           S4 insert executor_finished {exit, interrupted,
                                              timed_out, receipts_complete}; exit (lock
                                              released by the OS)
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

Recovery (or a stop of a `launching` send) begins with one transaction: `UPDATE sends SET claim=claim+1, claim_owner=:me, launch_token=NULL WHERE send_id=? AND claim=:seen`. After it commits, S2 of any executor holding the old token fails. Then, if no `executor_started` fact **for the send's current `attempt_id`** exists, the send is definitely not started (`not_started`), and no executor can later start it. If one exists, it is `generating` and its liveness is checked through its lock (§4.5).

**(R5) Revocation is not history.** PHASE1B_REVIEW_R4 (C1-R4-1) showed the R4 core deciding "not started" from the token: a refused reset nulled the token of a send whose executor had already committed S2 (the controller had not yet promoted it to `generating`), and a later recovery settled it `not_started`, released the lease and allowed a same-key re-arm while the executor ran. The token now only authorises future starts. Start evidence is read by `attempt_id`, which fencing, a refused reset, a change of claim owner and settlement never alter. Every launcher and finaliser callback is bound to its own attempt (or, before T1, its own claim) and leaves any other attempt untouched.

Because S2 and the fencing update both run under `BEGIN IMMEDIATE`, SQLite serialises them (one writer at a time; `BEGIN IMMEDIATE` takes the write lock at `BEGIN` [E1]). Whichever commits first wins, and the other sees its result.

#### 4.4.4 When supervision is unavailable (U3)

| Condition | Behaviour |
|---|---|
| Ledger storage unsupported (§4.1) | refuse before acceptance (`503 send_storage_unsupported`) |
| The bridge cannot run (no interpreter beside the binary, or `len(command)!=1`) | refuse before acceptance (`503 send_supervision_unavailable`). The fallback `rt.run` path cannot hold the go-gate, record its own identity or be fenced, so it cannot meet §4.4.2. This **replaces** revision 1's fallback for sends. |
| **(R3)** The platform's supervision is not established (§4.5 "Platform enablement") | refuse before acceptance (`503 send_supervision_unavailable`), with the platform named. An "unverified" label is not enough to enable it. |
| The bridge runs, but the commit-boundary seam (`SessionDB._execute_write` with the pinned calling convention) is missing or changed | accept with `capability=unverified_sources`; the launch/lease/fencing protocol is unchanged; source links are unverified; no session is registered as `workspace`; the receipt and UI disclose it. |

**(R3) O-A decided:** the first two rows apply to the keyed route **and** the legacy `POST /api/chat` (§5.8). There is no unsafe legacy escape hatch. The third row is the only degraded mode, and it degrades correlation only, never supervision. This is a behaviour change for installs where the bridge cannot run (external installs with a wrapper command) and, until their evidence exists, for the platforms listed as not enabled in §4.5.

### 4.5 Executor liveness and lease release

Liveness is an OS lock, not a PID. E holds `executors/<send_id>.lock` from S1 until the process ends. The OS releases it when the process ends, however it ends (`flock` on Linux/macOS/Android; `LockFileEx` on Windows, released at process termination). The bridge child is spawned with `close_fds=True` (POSIX) and a restricted handle list (Windows, Python's default when `close_fds` is true), so a descendant does not inherit the lock handle unless it is forked without exec. A lock held longer than E (for example by an `os.fork` descendant) only keeps the lease longer; it can never release it early.

**(R3) What the lock proves, and what it does not.** Acquiring E's lock proves **E** has ended. It does not prove every descendant has ended. C0 showed this directly: after E exited, its lock was free while a child in E's process group was still running (C0: `test_lock_release_proves_the_executor_gone_not_its_descendants`). Revision 2 dismissed descendants as "not the transcript writer". That was an assumption about Hermes's tool paths, not something the lock protocol establishes. Revision 3 scopes the claim explicitly:

- **Managed execution** = E plus every process in E's process group (POSIX: E is a session and group leader, `start_new_session=True`) or E's job (Windows).
- **Quiescence** = both of:
  - (a) E's lock is acquired by the identity probe below;
  - (b) the managed execution is **demonstrably** empty. On Linux/Android, no non-zombie process has E's `pgid` (enumerating `/proc/<pid>/stat`). On macOS, `sysctl KERN_PROC_PGRP` returns none. On Windows, `JOBOBJECT_BASIC_ACCOUNTING_INFORMATION.ActiveProcesses = 0`.
  - **(R4) An incomplete observation is not an empty group.** Only a process that is demonstrably gone (`ENOENT`/`ESRCH` on its entry) is skipped. A permission, I/O or parse failure on any entry, an unreadable `/proc`, a `/proc` mounted with `hidepid`, or a platform without supported enumeration makes (b) **unproven**, and the lease, reset refusal and installation exclusion stay in force. The C0 prototype caught every `OSError` and returned an empty list; the reviewer's probe showed one unreadable process read as "no members". C1: `send_quiescence.group_members` returns `complete=false` for all of these.

  Only when both hold is the lease released. If (a) holds and (b) does not, `liveness=live`; the owner kills the group or job (§4.9) and probes again.
- **Outside the boundary:**
  - A process that deliberately leaves the group or job: `setsid`/`setpgid` on POSIX (C0: `test_a_descendant_that_leaves_the_group_is_outside_the_boundary`), or a job breakaway on Windows. The design does not claim to contain it or detect it. Whether any Hermes tool path does this at `0e9fc2cc15` is new observation **O-10**.
  - Unrelated external writers, such as a terminal the owner runs.

  The claim is exactly: **no second managed writer while any managed process may still run.** It is not extended to an arbitrary process tree.
- Transcript rows written by any process other than E are never receipted, so they can never be linked to the send (§4.10.1). A write by an escaped descendant can therefore not corrupt correlation. It can only be an unreceipted row, like a terminal's.
- The installation-wide exclusion (§4.7) uses the same quiescence test. An update is refused while any managed process of any profile's open send remains, not only while E does.

**(R3) Lock files are safety objects.** Their lifetime and handling:
- S1 opens or creates the lock and records its `(st_dev, st_ino)` in `executor_started`.
- A lock file is **never unlinked, truncated or replaced** while any send that recorded it is unsettled. Retention (§5.5) removes it only together with its settled send. A reset never removes one (§4.1). Nothing deletes a busy lock to unblock the UI.
- **Identity probe:** open the path **without `O_CREAT`**, lock it non-blocking, then require `fstat(fd)` = recorded identity = `stat(path)`.
  - Busy → `live`.
  - Acquired and identical → condition (a) holds.
  - Missing path, a different identity, or a path replaced between open and stat → **`unproven`**, and the lease stays held.

  Revision 2's probe opened with create. C0 showed that it reports a recreated file as proof that the executor ended while the executor still held the unlinked original (C0: `test_a_replaced_lock_path_is_not_proof`, `test_identity_probe_on_a_live_and_an_ended_executor`).

Proof of quiescence = the identity probe acquires E's lock **and** the managed execution is empty. Nothing else counts: a missing PID, a failed process lookup, an unsupported liveness check, a timeout or a lost heartbeat is **not** proof of death.

**(R3) Platform enablement.** A platform's keyed and legacy sends are enabled only when its supervision behaviour has been observed, not inferred (O-A, O-C):

| Platform | Needs | C0 status | Sends |
|---|---|---|---|
| Linux (desktop/server) | flock semantics, group enumeration, `killpg`, controller death leaves E running | observed on this host (C0: `test_phase1b_c0_liveness.py`, 6 cases) | proposed **enabled** |
| Windows | O-8: job assignment before `go`, `ActiveProcesses`, last-handle kill-on-close, `TerminateJobObject` reaching descendants, breakaway behaviour, lock release timing | **unavailable** (no Windows host; CI runner not used in C0) | **refused** until O-8 passes |
| macOS | O-11 (new): `KERN_PROC_PGRP` enumeration, `killpg`, flock on APFS | **unavailable** | **refused** until O-11 passes |
| Android / Termux | O-9: private `$HOME` mount type, flock, `/proc` group enumeration under the app's SELinux domain | **unavailable** (no device test in C0) | **refused** until O-9 passes |

This is the named consequence of the missing evidence. It is a regression for the platforms marked refused, which today can chat without these guarantees. It is §12 item O-E for the owner.

| Situation | Evidence | `liveness` | Lease |
|---|---|---|---|
| `accepted`, no executor authorised | no token | `none` | held (acquired at acceptance) |
| `launching`, fenced, no `executor_started` | fencing commit | `none` | **released** |
| `spawn_failed` | fact | `none` | **released** |
| identity probe acquires the executor lock **and** the managed group/job is empty (R3) | lock acquired, group empty | `quiescent` | **released** (outcome may still be `unknown`) |
| executor lock still held, **or** acquired while a managed process remains (R3) | lock busy / group not empty | `live` | held |
| lock file missing, replaced (identity mismatch), or not openable/lockable for a reason other than "busy" (R3) | none | `unproven` | held; receipt says the app cannot confirm Hermes has stopped |
| executor lock busy after interrupt, grace and kill attempts | lock busy | `live` | held; state stays `stopping`/`unknown`; UI says a previous reply may still be running and a new message will wait |

A held lease blocks every new send on that physical home (`409 turn_in_progress`), including a confirmed new-key "Send again" (U2). There is no age-based expiry. A host reboot always resolves `live`/`unproven` for local storage, because it ends every process and lock.

**Descendants (R3, replaced).** Revision 2's rule ("descendants do not gate the lease") is withdrawn. Descendants inside the managed group or job gate the lease through quiescence condition (b) above. Descendants that leave it are outside the stated boundary (O-10).

**Per-OS process handling.**

| | Linux / Android (Termux) | macOS | Windows |
|---|---|---|---|
| Group | `start_new_session=True`; E is group leader | same | E assigned to a job object at step J, before G, so E cannot run before assignment; `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` set [E3] |
| Identity recorded in S2 | pid, `/proc/self/stat` field 22, boot id | pid, `sysctl kern.proc.pid` start time | pid, `GetProcessTimes` creation time |
| Signal target check before any signal | lock still busy **and** a `pidfd_open(pid)` handle whose start time matches (Python ≥ 3.9, Linux ≥ 5.3; otherwise the start-time check without a pidfd, with a residual race stated) | lock busy and start time matches; residual race between check and `killpg` stated | the job handle (no PID signalling) |
| Graceful interrupt | ledger flag read by E's watchdog → `_thread.interrupt_main()` inside E (§4.9); no signal needed | same | same |
| Kill tree | `killpg(pgid, SIGKILL)` | same | `TerminateJobObject` |
| Controller dies, executor alive | E continues; its watchdog enforces `deadline_at`; recovery supervises it through the lock and facts (C0 observed on Linux: `test_controller_death_leaves_a_posix_executor_running`) | same (not observed) | **proposed** (O-C): kill-on-close ends the job only when the **last** handle to the job closes [W]. The controller must hold the only job handle, and no process in the job may hold one; child association depends on the creation and breakaway flags. None of this is observed yet (O-8). |
| Proof of quiescence | identity probe acquires the lock **and** no process in E's group | identity probe **and** `KERN_PROC_PGRP` empty | identity probe **and** `ActiveProcesses = 0` |

`CREATE_NEW_PROCESS_GROUP` alone is not used as a kill-tree mechanism: Python documents `send_signal(CTRL_BREAK_EVENT)` separately, and `Popen.kill()` on Windows terminates only the child [E2]. **(R3)** Windows sends are refused until O-8 is observed on a real Windows host. A test-status label such as "orphan recovery unverified" does not enable a send path whose safety prerequisites are not established.

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
| After S2, before any Hermes write | `generating` | E alive → supervise; E dead without `executor_finished` → `unknown` | **(R3)** `absent` (bounded coverage: no `write_intent` at all, and intents fail closed) | released once quiescent | `unknown` receipt |
| **(R3)** E between a transcript `write_intent` and its outcome fact (inside Hermes's callback or commit) | `generating` | E dead → `unknown` | `possible` | released once quiescent | `unknown` receipt |
| **(R3)** Hermes's commit raised after the callback ran (`write_unsettled`) | `generating` | per E; the turn usually fails | `possible` (if it was the owner-row write) | per §4.5 | outcome from `executor_finished`, `owner_turn=possible` |
| **(R3)** Hermes committed; the receipt write failed (`receipt_gap`) | `generating` | E refuses every later write (fail closed), so Hermes aborts the turn; `executor_finished.receipts_complete=false` | `unknown` | per §4.5 | `failed` or `unknown`; never `complete` |
| After the owner row, before any reply | `generating` | E alive → supervise; E dead → `unknown` | recorded | released once dead | `unknown` ("recorded; reply not known") |
| After partial output, E dead | `generating` | `unknown` | recorded | released | `unknown`, `reply=partial` if a `public_output` row was committed, else `none` (bounded) |
| After the final reply row, before `executor_finished` | `generating` | E alive → wait for the fact; E dead → `unknown` (a reply row is not completion evidence) | recorded | per §4.5 | `unknown`, `reply=partial` |
| **(R3)** `executor_finished exit=0`, last public row `finish_reason≠'stop'` | `generating` | ingest → `failed`, `reply_incomplete` | recorded | released once quiescent | `failed`, `reply=partial` |
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
- E's watchdog thread (installed at S3) reads `stop_requested_at` and `deadline_at` from the ledger once a second with a read-only connection. When either applies, it records `stop_seen` and calls `_thread.interrupt_main()`, which raises `KeyboardInterrupt` in Hermes's main thread, the same path as Ctrl-C (`cli.py:4057-4063`). The same mechanism is expected on every OS and does not depend on the controller being alive. **(R3)** C0 observed it on Linux during a provider stream only: exit 130, 1.84 s from the interrupt to the end of the turn, and no assistant row stored (C0: `test_interrupt_main_reaches_the_turn_during_a_stream`). The tool-call path and other OSes are not observed (O-6 remains open for those).
- Grace: 15 s after `stop_seen`. If the managed execution is not quiescent (R3: E's lock busy **or** a process left in its group/job), the owner kills the group/job (§4.5 table), records `kill_sent`, and re-probes. The outcome remains whatever the facts establish: a turn that finished before the interrupt landed is `complete`; one that raised `KeyboardInterrupt` is `interrupted`; one killed before writing `executor_finished` is `unknown`. A timeout that ends in `exit=1` is `failed` with `error_code=timeout`.
- If the kill cannot be confirmed (lock still busy), the state stays `stopping` and the lease stays held (§4.5).

### 4.10 Correlation (B2)

#### 4.10.1 Source receipts written by the executor

**(R3, replaced.)** Revision 2 wrapped five methods and wrote `row_written` when each returned. On the pinned code that published rolled-back rows, published the same ids twice on a retried callback, claimed a foreign writer's reuse of a rolled-back id, missed the compression child session and its cloned rows, and raised into Hermes after Hermes had committed (C0: `RevisionTwoDefects`, 6 cases). The replacement records at the commit boundary instead.

At S3, inside E only, the bridge wraps **`SessionDB._execute_write`**, the one place where the pinned `SessionDB` commits (§1.3):

1. **Write intent.** At the outermost `_execute_write`, before Hermes's callback runs, E commits `write_intent {wid, method}`. `wid` is a per-executor counter; `method` is the calling SessionDB method's name, for diagnostics only. If this ledger write fails, the wrapper raises **before** Hermes's callback, so no write happens without an intent (fail closed).
2. **Candidates per attempt.** The callback receives a connection proxy. For each `INSERT INTO messages` the proxy records `(session_id, row_id, role, class-inputs)`, read back from the row inside the same transaction, with no content. For each `INSERT INTO sessions` it records whether the id existed just before the statement and exists just after (`fresh`). A multi-row `INSERT … SELECT` (the tail clone) has no per-row id; its row count, from `changes()`, which excludes FTS trigger rows, is recorded as `unidentified`. **When Hermes retries the callback, the previous attempt's candidates are discarded.**
3. **Publish only after commit.** Only when the outermost `_execute_write` **returns** (Hermes has committed) does E commit `write_committed {wid, method, attempts, rows, sessions, unidentified}`. Nested `_execute_write` calls publish nothing of their own; their observations belong to the enclosing scope.
4. **Failure outcomes.** If `_execute_write` raises and the callback never returned: `write_rolled_back {wid, attempts, candidates}`, and no rows are published. If the callback returned but the commit step raised: `write_unsettled {wid}`, meaning settlement is unknown.
5. **Cross-store gap.** Hermes committed but the `write_committed` fact could not be written: E records `receipt_gap {wid}` if it still can, and **never raises into Hermes for that write**, because it succeeded. From then on every `write_intent` fails closed, so no later row, and in particular no owner row in a session the ledger never attributed, can land. `executor_finished` carries `receipts_complete=false`. The gap is never filled later by matching text or by taking whatever row now holds a candidate id.

**(R5) Continuation-note provenance (O-12).** Hermes creates its mid-stream continuation note as a `role=user` dict tagged `_length_continuation_nudge` (`agent/turn_truncation.py`); the SessionDB projection drops the tag and Hermes pops it from the live dict when the continued reply finishes, so the stored row has no marker. Inside E only, the executor keeps a reference to each dict Hermes created **with** that tag (wrapping the module-level `append_message` of `agent.turn_truncation`) and, at `agent.session_persistence._db_flush_write(agent, batch_rows, batch_msgs)` after the commit, matches them **by object identity** to the rows whose committed ids Hermes copies back. It writes `row_provenance {rows: [{session_id, row_id, kind: length_continuation_nudge}]}`. Receipt derivation treats a row as internal only when that provenance names a row committed in this attempt's own receipts; any other entry changes nothing. Text is never read, and an owner message with the identical words stays owner speech. A missing seam, a copied dict or a failed provenance write leaves the conservative result (`ambiguous`, never complete). Seen on the pinned code only; no Hermes change.

Row classes, computed at publish time:

| Class | Rows | May support |
|---|---|---|
| `user_turn` | `role=user`, written by `append_message`/`append_messages_batch`, **and (R4) publicly eligible by Phase 1A's structural rule**: no `display_kind`, not `_compressed_summary`, not `observed`, active (or a compacted original), text present, no tool calls | `owner_turn` |
| `user_internal` **(R4)** | a `role=user` turn-method row that fails that eligibility (hidden, display-only, summary, observed, empty) | nothing. Thread/call provenance alone is not message eligibility (review R3 5.2). |
| `public_output` | `role=assistant`, text present, no tool calls, no `display_kind`, not `_compressed_summary`, not `observed`, written by `append_message`/`append_messages_batch` | `reply` (with `finish_reason`, §4.3.2) |
| `assistant_internal` | assistant rows with tool calls, no text, a display kind, or summary/observed flags | nothing |
| `internal` | tool/system rows | nothing |
| `rewrite_copy` | every row inserted by any other method (`replace_messages`, `archive_and_compact`, `publish_compression_child`, rewind replacement, import) | nothing. A copy of historical output is never turn output. |

C0 checked this rule on the pinned code (C0: `CommitAwareReceipts`, 12 cases):
- rollback after the inner helper → nothing published;
- a retried callback → one receipt with `attempts=2`;
- a foreign row reusing a rolled-back id → never claimed;
- a chunked batch → one receipt per committed chunk;
- rewrite/compaction rows → `rewrite_copy`, and the clone is counted `unidentified`;
- tool-call, tool and public rows → correctly separated;
- a commit failure → `write_unsettled`;
- a receipt-write failure after the source commit → `receipt_gap`, then fail closed.

For the real CLI turns run, the committed receipts covered exactly the rows in `state.db`: fresh session, resume, provider error, truncation, disconnect, interrupt (C0: `RealTurns`). **Limits:** this is a harness recorder, not production. The CLI compression-continuation path, tool-using turns, gateway and cron were not run. A second concurrent Hermes writer in E's own process was not exercised.

These facts are causal. They are written by the process that performed the commit, bound to its `launch_token`, and cover rows **this executor committed** and no row any other process wrote. A terminal writing into the same session, even with the same text, never appears in them. No watermark, time window or text comparison selects rows.

If a send's committed receipts hold more than one `user_turn` row, `owner_turn=ambiguous` and no candidate is chosen.

#### 4.10.2 Sessions and workspace registration (D5, D6)

- **(R4) How freshness is observed.** Inside the write transaction the recorder reads `max(rowid)` of `sessions` before an `INSERT INTO sessions` and the ids with a higher rowid after it. A new row always receives a rowid above the previous maximum, so this names exactly the sessions the statement created and does not depend on the statement's text. (Mapping the `id` column to a positional parameter failed on the pinned upsert, whose `VALUES` list contains a literal `NULL`.) If the rowid cannot be read, the insert is recorded with `fresh=null` and counts as unidentified.
- **(R3)** A session is attributed to the send as *created here* only when a `write_committed` fact from this executor lists it with `fresh=true`. That covers a new session and a continuation created during the turn, including `publish_compression_child`, which inserts the session row without `create_session`. A `create_session`/`ensure_session` call on an existing id is an upsert and gives `fresh=false`. A failed insert gives `write_rolled_back` with no session. Neither ever labels the session as created by the workspace (C0: `test_only_a_fresh_insert_is_a_created_session`, `test_compression_child_and_clone_are_seen_and_the_clone_is_unidentified`). The resumed `requested_session` is recorded in `hermes_sessions` with `created_here=false` and is **not** relabelled.
- The Phase 1A classifier gains a second source of workspace sessions: fresh-session receipts in the ledger (read-only), unioned with `.tamanitomo-sessions.json`.
- **(R3) Early registration without an upsert-as-proof.** Revision 2 made the *pre-call* intent of `create_session` the attribution. That treated an upsert attempt as proof of creation. Instead:
  - The fresh-session receipt is committed as soon as Hermes's session-insert transaction returns, and before control goes back to Hermes.
  - On the pinned CLI path the session row and the owner row are separate `_execute_write` calls, and C0 observed the session row committed first in every fresh turn run.
  - If that receipt cannot be committed, E is in `receipt_gap` and refuses every later write, so the owner row cannot land in an unattributed session. The turn fails and `owner_turn=unknown` is reported, never `absent`.
  - If Hermes ever inserted a fresh session and a transcript row in **one** transaction, both would arrive in the same `write_committed` fact, which still precedes any later write.
  - So no attributable transcript row exists in a session the ledger does not attribute.
- The post-completion `note_workspace_session` call stays (for older readers of the JSON file) but is no longer the authority.
- The before/after session diff (D6) is removed from both routes.

#### 4.10.3 Identity at read time

Links are joined into Phase 1A reads by the full identity envelope, not a row key alone. A link resolves to a projection row only when **all** of these hold for the currently authorised scope:
- the projection row's `source_session`/`source_message` equal the receipt's `(session_id, row_id)`;
- its stored fingerprint equals `fingerprint(row_id, session_id, role, timestamp)` computed from the receipt (`chat_sources.py:302`);
- **(R3)** its source kind and account/channel namespace equal the send's recorded `source_kind`/`source_namespace` (§4.2), **and** that kind and namespace are still authorised by the current binding. At acceptance the server records the permitted kind: `workspace` for a new session or a workspace session; `terminal` (with its namespace) for an authorised terminal session resumed from the workspace. Revision 2 accepted only `workspace` here, which contradicted its own rule that a resumed terminal session stays terminal. The terminal's history is never relabelled to make the join succeed. Authorisation is never widened because the executor wrote a row: if the binding later stops authorising terminal rows, those links resolve to nothing, exactly as a Phase 1A revocation;
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

When the commit-boundary seam is missing or its calling convention changed (R3: `SessionDB._execute_write(self, fn, patience_s=None)`), E records `capability_downgrade {missing:[…]}` at S3 and the send runs with `capability=unverified_sources`. Then `owner_turn` and `reply` are `unknown` (coverage unavailable, §4.3.2), `correlation=unverified`, no session is registered, and no link is shown. `executor_finished` can still establish `failed` or `interrupted`; `complete` needs complete receipts, so an unverified send whose executor reports `exit=0` ends in state `unknown` with `error_code=sources_unverified`, worded "Hermes finished the turn; the app could not verify what it recorded". It is never `complete`. The launch, fencing, lease and liveness protocol is unchanged. D5 stays open for that turn and the receipt says so.

### 4.11 Destination

`destination` is fixed to `workspace`; the request schema has no field that could change it. A badge on an earlier message is provenance only. 1B adds no external send from the workspace. The outbox, its dispatcher, `may_send`, quiet hours, approval/review and caps are unchanged except as §7 describes.

---

## 5. API

### 5.1 Routes

```
GET  /api/chat/sends/bootstrap          (R3) → {conversation_id, generation}; creates the ledger on
                                        first use (§4.1); 503 send_ledger_lost / send_storage_unsupported /
                                        send_supervision_unavailable; 409 ledger_busy during a reset

POST /api/chat/sends
  body: {client_key, generation, conversation_id, message, session: S|null}
  202 {send: Receipt, operation: {id}}                     new acceptance
  200 {send: Receipt, operation: {id}, replay: true}        existing receipt for this key
  409 {error: "key_conflict", send_id}                     same key, different digest
  409 {error: "generation_changed"}                        (R3) no receipt, and the request's generation is not current
  409 {error: "not_bootstrapped"}                          (R3) no ledger exists; call bootstrap first
  409 {error: "ledger_busy"}                               (R3) an explicit reset is in progress
  409 {error: "turn_in_progress"}                          another send holds the lease (not accepted)
  409 {error: "installation_busy"}                         an installation mutation is running
  422 {error: "key_expired"}
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
2. Open the ledger (storage, loss checks). **(R3)** No ledger → `409 not_bootstrapped`; the POST never creates one.
3. **Look up `(conversation_id, client_key)`.** If a row exists: equal digest → `200 replay` with that receipt, whatever the lease, age, state **or generation** (except the `not_started` re-arm below); different digest → `409 key_conflict`. This runs **before** the busy check, so identical concurrent retries all get the one receipt, never a misleading `turn_in_progress` (M-2).
4. No row: **(R3)** the request's `generation` must equal the ledger's current one (else `409 generation_changed`); then the key's time is checked for freshness (§5.3).
5. Check supervision availability (§4.4.4), including platform enablement (§4.5).
6. Installation lock (non-blocking), then `guard.lock` **shared** (R3; busy with a reset → `409 ledger_busy`), then one `BEGIN IMMEDIATE`: re-run steps 3–4 inside it (a concurrent identical request, or a reset, may have committed since); if the lease is held → `409 turn_in_progress`; else insert the send with `send_id`, `operation_id`, `generation`, `source_kind`/`source_namespace`, `claim=1`, `claim_owner=me`, acquire the lease, `COMMIT`. Release the guard, then the installation lock.
7. Create the operation view and hand the send to the launcher (§4.4).

Same-key requests in different logical scopes are independent receipts. A wrong `conversation_id` is never permission to look in another scope.

### 5.3 Admission, replay and re-arm

| Situation | Result |
|---|---|
| Existing receipt, same digest, any state except `not_started` | `200 replay`. Nothing launches. No age limit while the receipt is retained. |
| Existing `not_started`, same digest, key time within 24 h | re-arm: `not_started → accepted` (same `send_id`, new claim), subject to the lease and installation checks of step 6, then launch |
| Existing `not_started`, same digest, key older than 24 h | `200 replay` of the `not_started` receipt with `rearm: "expired"`. Nothing launches. The client may offer a new send (a new key; no duplicate risk, because non-execution is definite). |
| Existing receipt, different digest | `409 key_conflict` |
| No receipt, `generation` current, key time within 24 h and not > 5 min in the future | accept |
| **(R3)** No receipt, `generation` not current (an earlier ledger, or a request frozen before a reset) | `409 generation_changed`. Never a fresh send, whatever the key's time. |
| No receipt, key older than 24 h | `422 key_expired`. Never a fresh send. |
| Key > 5 min in the future | `400` |

**(R3)** The generation is the reset fence and the key time is only freshness. A client clock that runs ahead or behind changes only freshness results; it can never make a request from an earlier generation fresh (C0: `test_generation_fence_refuses_a_prior_generation_request`, `test_freshness_is_separate_from_the_fence`). `key_predates_ledger` and `admission_floor` are withdrawn.

The server stores no request text, so it can never relaunch from a digest. The only way the original payload returns after a definite `not_started` is an identical client resubmission (step 3 compares the digest). A newer draft is a different digest and a different key.

Age never authorises a launch and never erases evidence: an expired key with an existing receipt still replays.

### 5.4 After `unknown` (U2)

The UI first calls `GET /api/chat/sends/{send_id}` (or `?key=`). "Send again" is offered only when the receipt says `liveness` is `quiescent` or `none` (lease released) and the outcome is still `unknown`. It mints a **new key** after the owner confirms "This may send your message twice." It then goes through the ordinary acceptance path, so it still gets `409 turn_in_progress` while any lease is held.

### 5.5 Ledger retention (B3)

A send is **settled** when its lease is released (`liveness` is `none` or `quiescent`) and its state is `complete`, `failed`, `interrupted`, `not_started` or `unknown`. `settled_at` is set in the releasing transaction.

Prune predicate, exactly: delete a send (its facts and events cascade) iff `settled_at IS NOT NULL AND settled_at < now − 30 days`. **(R3)** Its `executors/<send_id>.lock` is removed in the same pass, only after the row is deleted, and only if the identity probe finds it acquirable. It is never removed while its send is unsettled (§4.5). Unsettled sends (`accepted`, `launching`, `generating`, `stopping`, or any send with `liveness` `live`/`unproven`) are never pruned, whatever their age.

Safety after pruning: every pruned key is at least 30 days past settlement and therefore more than 24 h old, so an absent key is refused by admission (`key_expired`); no tombstone is needed for replay safety. Historical `send_id` correlation on reads is available for 30 days after settlement; after that, rows show no `correlation.send_id` and the contract says so.

Bounded work: one pass deletes at most 500 sends, chosen by `SELECT send_id FROM sends WHERE settled_at < ? ORDER BY settled_at LIMIT 500` on the partial index `sends_settled`. A pass runs after each acceptance, once at app start, and when `GET ?open=1` is served. An installation that stops sending is still pruned at its next app start; an installation that never runs the app again does not grow either. `send_events` per send is bounded by the state machine (at most 12 transitions) plus recovery attempts, which are counted in one fact rather than logged per attempt.

The 200-bytes-per-row figure in revision 1 is withdrawn. M-23 measures the real file size, including facts, events and indexes, at 10,000 settled sends with a realistic fact count per send (R3: a `write_intent` plus an outcome fact per committed Hermes write; C0 counted 17 committed writes, so about 34 facts, for a plain one-reply turn with no tools, and more for tool-using turns), and the result is reported as measured.

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
- while the row is in memory (the live process), from the in-memory result, **(R3) but only after the same current-authorisation check as reconstruction**. The request's `ChatScope` is captured, the send's scope and linked sources must still be authorised, and otherwise the in-memory `response`/`messages` are withheld exactly as below. A revocation cannot leak content through the "still in memory" branch (M-14a covers both branches);
- otherwise, reconstructed at request time from the send's linked source rows through the Phase 1A read path under the **current** authorisation (`messages` from the linked rows; `response` from the linked final assistant row);
- otherwise (links lost, not authorised, source unavailable, or receipt pruned), `result.response = null`, `result.messages = []`, `result.content_retained = false`. A reply is never regenerated because content is missing.

**Retention of operation files.** Applies to terminal (`status` ≠ `running`) records with `format: 2` in this app state's `operations/` directory. Prune a record iff `finished_at < now − 7 days` **OR** it is not among the newest 500 terminal `format: 2` records by `finished_at`. At most 500 files are removed per pass, oldest first; a pass runs at app start and after each chat operation finishes. `running` records are never pruned by this rule (their safety state is in the ledger). Operation records without `format: 2` (pre-1B chat records and all non-chat operations) are left untouched in 1B; the app reports their count, and removing pre-1B chat records that contain text is a separate owner-approved action (O-B, decided: count only). **(R3)** Their text is still on disk; no document or UI says it was removed.

### 5.8 The legacy `POST /api/chat`

Kept for old clients. Each call gets a ledger row with `client_key = legacy-<uuid>` and `legacy=1`, so it takes part in the lease, launch protocol, receipts and retention. It is **not** idempotent: two calls are two sends. The new UI never falls back to it after a network error (§6). **(R3)** The server bootstraps implicitly for it, carrying the current generation, because a legacy call has no retry identity to fence. It is refused on exactly the conditions that refuse the keyed route (§4.4.4, O-A).

---

## 6. Minimal client correction (U1, changeset C3)

Scope: `workspace.js` chat submit, recovery on load, and bubble status only.

State kept in `sessionStorage` under the profile's chat key:
- `draft`: the editable compose text (as today).
- `pending`: `{client_key, generation, conversation_id, profile, session, message, send_id?, operation_id?}`, **immutable** once created; one at a time. It is separate from `draft`, so editing or clearing the compose box never changes it, and a new draft never replaces it.

Flow:
0. **(R3)** Before the first send of a page load (and after any `generation_changed`), `GET /api/chat/sends/bootstrap` to get the current `generation`. A failure here means nothing is sent and the compose box keeps the text as a draft.
1. Send: mint `client_key`, write `pending` with the bootstrapped `generation`, clear the compose box into a fresh draft, draw `snd_pending:owner` "sending…", `POST /api/chat/sends`.
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
| **(R3)** `409 generation_changed` for a `pending` send | "The app's send records were reset. Whether this message was sent before the reset is unknown." **Send again** is a new intent (new key, new generation), after the confirmation of §5.4 | not restored; `pending` cleared |
| **(R3)** `409 not_bootstrapped` | treated as a failed bootstrap (step 0): "Not sent" | offered back as a draft |

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
3. **Slot (R3, split in two).** The daily-slot charge (`outreach.jsonl`) and the outbox marker are separate durable writes. A file lock does not make them one transaction.
   - **3a. Reservation intent.** Append `reserving_slot {attempt}` (guarded: the current status must be `dispatching` with this attempt) **before** any charge.
   - **3b. Charge by attempt identity.** `outreach.claim()` appends its charge row with the attempt id. C2 adds an explicit `attempt` field. The pinned outreach row already stores `reason` (≤ 200 characters), and the C0 prototype carries `attempt=<id>` there without changing production code. Refused → append `queued` with `release_reason=cap` and the attempt. That is definite: `claim()` appends nothing when it refuses.
   - **3c.** Granted → append `slot_reserved {attempt}`.
4. **Send marker.** Append `sending {attempt}` immediately before starting `hermes send`.
5. **Outcome.** Append exactly one of `sent`, `failed`, `unknown`, `withheld` with the attempt (§7.5), only if the entry's current status is `sending` with the same attempt (guarded).

Every guarded append validates `(attempt, expected status)`. A late update for a different or superseded attempt is refused and does not change the entry.

### 7.3 Abandoned attempts

At the start of a run (holding the run lock), any entry whose last update is from a different `run_id` and is not an outcome belongs to a dispatcher that is no longer running (only one run can hold the run lock). It is resolved from its last phase:

**(R3)** Revision 2 resolved `dispatching` as "no slot was used". That did not follow from the durable state. A crash after `claim()` committed its charge but before `slot_reserved` was appended left `dispatching`. The next run requeued the entry and charged a second slot for one message. C0 reproduced this with the real outreach ledger: one delivery, two slots (C0: `test_revision_two_charges_twice_after_a_charge_before_marker_crash`). This is a quota-accounting and classification defect; no `sending` marker was reached, so it is not a duplicate delivery. The rule for each boundary:

| Crash boundary | Last phase | What is durable | Resolution |
|---|---|---|---|
| before the reservation intent | `dispatching` | no intent, so no charge can exist for this attempt (the charge follows the intent) | back to `queued` (definite non-dispatch, no slot used) |
| after the intent, before the charge | `reserving_slot` | intent; charge row for this attempt absent | resolved under the outreach lock by looking up the attempt's charge row: **absent and the ledger readable** → back to `queued` (definitely not charged) |
| after the charge, before its marker | `reserving_slot` | intent and a charge row for this attempt | **present** → `failed`, `not_dispatched: true`; the slot stays consumed, with no refund and no requeue |
| any `reserving_slot` whose charge cannot be established | `reserving_slot` | outreach ledger unreadable/corrupt | `reservation_unresolved`: "definitely not dispatched; slot consumption unknown". No automatic requeue and no refund; the owner sees it. |
| after the slot marker | `slot_reserved` | slot used, not sent | `failed`, `not_dispatched: true` (the existing rule that a used slot is not retried) |
| after the `sending` marker | `sending` | `hermes send` may have run | `unknown`, "the dispatcher stopped mid-send; delivery is not known". **Never resent.** |

The charge-row lookup is sound only because the run lock proves the earlier dispatcher is no longer running, and its charge append (one line, `fsync`ed under the outreach lock) is either wholly present or makes the ledger unreadable (a torn line). C0 asserted, at every boundary, the status after the next run, the delivery-call count and `outreach.sent_today`: `(sent,1,1)`, `(sent,1,1)`, `(failed,0,1)`, `(failed,0,1)`, `(unknown,0,1)`, plus `reservation_unresolved` for a torn ledger (C0: `test_amended_rule_at_every_boundary`, `test_an_unreadable_slot_ledger_leaves_the_reservation_unresolved`). These results come from the prototype attempt protocol over the production outbox format and the production `claim()`; they are not an integrated C2 result.

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

- A pre-1B dispatcher reading a 1B outbox: `fold()` keeps the last status, so `dispatching`/`reserving_slot`/`reservation_unresolved`/`slot_reserved`/`sending`/`unknown` entries are not `queued` to it and are not sent again (M-20d; C0: `test_pre_1b_fold_does_not_requeue_new_phases`, with the unchanged production `fold()`/`waiting()`).
- A pre-1B dispatcher **already running** with a stale snapshot does not take the run lock or the claim guard, so it can still send an entry that a 1B dispatcher claimed. Running old and new dispatchers on one life directory at the same time is **unsupported**; the upgrade path is to stop the old one first. This limit is stated in the release notes when 1B ships (release work is not authorised here).

---

## 8. Observations still needed

Each is a synthetic, pinned observation against Hermes `0e9fc2cc15` (the fixture revision) with `tests/mock_provider.py`, not a live run. The design is safe whatever each one shows; the right column says what changes.

**(R3) C0 status.** The full results, commands and platform limits are in `Phase1B_C0_Results.md`. In summary:

| # | C0 status | Consequence recorded in this revision |
|---|---|---|
| O-1 | **Observed (Linux, pinned code).** No `state.db` open during `import cli`. Several committed maintenance writes happen after import and before `_run_quiet_single_query`. | The go-gate and S2 precede `import cli` (§4.4.1). Those writes are executor writes, receipted with no transcript rows; they are not "harmless reads" as revision 2 said. |
| O-2 | **Partly observed.** The five named seams were **not** the complete insert surface (§1.3). The commit-boundary recorder covered every row in 6 real CLI paths and 13 SessionDB scenarios. | §4.10.1 replaced. CLI compression continuation, tool-using turns, gateway and cron remain unobserved; a path that yields `unidentified` rows makes coverage incomplete (`owner_turn=unknown`), never assumed. |
| O-3 | **Observed for 6 paths:** owner row committed before the first provider request each time. | Recorded, not relied on. |
| O-4 | **Observed at the SessionDB level:** compaction/compression/rewrite rows are inserted by non-turn methods and are classified `rewrite_copy`; the tail clone has no per-row id. The CLI-triggered compression path is not observed. | Rewrites can never supply `user_turn` or `public_output`. |
| O-5 | **Not observed.** Source reading only: `agent/turn_facade_lease.py` claims coverage of resume, gateway and background delivery. | Still not relied on. |
| O-6 | **Observed for the provider-stream path on Linux:** exit 130, no partial row. The tool-call path is not observed. | §4.9 unchanged; the kill fallback still covers a missed interrupt. |
| O-7 | Not run; the pre-platform error list stays **empty** (safe fallback: every `error` is `unknown`). | none |
| O-8 | **Unavailable** (no Windows host). | Windows sends refused (§4.5). |
| O-9 | **Unavailable** (no device test). | Android/Termux sends refused (§4.5). |
| O-10 (new) | Whether any Hermes tool path at `0e9fc2cc15` starts a process that leaves E's group or job. **Not observed.** | Outside the stated boundary until observed (§4.5). |
| O-11 (new) | macOS process-group enumeration, `killpg`, flock on APFS. **Unavailable.** | macOS sends refused (§4.5). |
| O-12 **(R4, new, observed in C1)** | When the main reply stream drops mid-reply, the pinned Hermes stores the partial reply (`finish_reason='length'`), then a **`role=user` continuation note with no structural marker** (no `display_kind`, not `observed`, not a summary, active), then the retried reply. | Structure cannot distinguish it from an owner message and text is never read, so the receipt is `owner_turn=ambiguous`, outcome `unknown`, never `complete` (C1: `test_a_dropped_main_stream_adds_an_unmarked_user_row`). The same row would pass Phase 1A's structural rule as an owner message; that is reported for the reviewer, not changed here. |

The table of revision 2 follows unchanged for reference.

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
| **C0** verification (R3; **this changeset**, test/harness only) | `tests/phase1b_c0/` (`receipt_probe.py`, `seam_scenarios.py`, `turn_driver.py`, `pinned.py`, `admission_proto.py`, `dispatch_proto.py`, `liveness_proto.py`); `tests/test_phase1b_c0_{receipts,admission,dispatch,liveness}.py`; `tests/mock_provider.py` gains `hang`, `error_before_first_byte` and `request_times` | Observations and prototypes only. No production module is changed. Results: `Phase1B_C0_Results.md`. |
| **C1 core (R4, implemented, not activated)** | `kit/app/chat_sends.py`, `kit/app/send_executor.py`, `kit/app/send_protocol.py`, `kit/app/send_quiescence.py` (all new, not in `release-files.json`); `tools/pinned_hermes_lane.py`; tests `tests/test_phase1b_c1_core.py`, `tests/test_phase1b_c1_pinned.py`, `tests/phase1b_c1/`; additive `recover_stream` mock scenario | The ledger, states, bootstrap/generation, acceptance and launch ownership, supervised executor, commit-boundary receipts, recovery/quiescence, reset and retention as callable components. The executor is a new file beside `hermes_stream.py`, which is unchanged. See `Phase1B_C1_Results.md`. |
| **C1 activation** (later, separate review) | `kit/app/chat_sends.py` (new): ledger, storage checks, states, facts, fencing, lease, liveness, recovery, retention. `kit/app/hermes_stream.py`: go-gate, executor lock with recorded identity, S2 under the shared guard, watchdog, the commit-boundary recorder (§4.10.1), `executor_finished` with `receipts_complete`. `kit/app/runtime.py`: `Runtime.chat()` launch protocol and process group/job; `Operations.submit(ident=)`, persisted-field allowlist, operation retention; installation lock helper. `kit/app/chat_routes.py`: `/api/chat/sends*`, `correlation.send_id` join. `kit/app/manage.py`: legacy `/api/chat` through the ledger, before/after guess removed; installation lock around mutations. `kit/app/chat_sources.py`: workspace sessions from fresh-session receipts (R3); capability table. `docs/CHAT_CONTRACT.md`: "Sending" section, restore limitation. `release-files.json`. | Tests: `tests/test_chat_sends.py`, `tests/test_send_recovery_subprocess.py`, `tests/test_operations_privacy.py`. (`tests/mock_provider.py` already gained `hang` in C0.) |
| **C2** dispatcher safety | `kit/scripts/companion_outbox.py`: statuses (incl. `reserving_slot`, `reservation_unresolved`), guarded claim/outcome appends, lock order. `kit/scripts/companion_outreach.py`: an `attempt` field on charge rows and a lookup by attempt (R3). `kit/scripts/companion_dispatch.py`: run lock, attempt phases, abandoned-attempt resolution per §7.3, classification, delivery record. `kit/app/chat_sources.py`: proactive capability "ids captured; transcript linkage unsupported". | `tests/test_dispatch_claim.py` |
| **C3** minimal client correction | `kit/app/static/workspace.js` (chat submit, `pending`, recovery on load, wording, DOM ids). | synthetic browser checks (M-22) |

---

## 10. Synthetic acceptance matrix

Every case uses a synthetic Hermes home, the fixture `state.db` schema (v30), the pinned Hermes revision where the case touches Hermes code, and `tests/mock_provider.py`. No real credentials, source data or messages. **Crash tests** run the app (or the executor) as a subprocess started by the test harness; the harness injects a test-only subclass or monkeypatches the production module at import (via a `sitecustomize` placed only on the test's `PYTHONPATH`), so the production transition functions run unmodified and the crash is a `SIGKILL`/`TerminateProcess` sent at a hook the double exposes. No environment variable read by shipped code triggers a crash (U6). Nothing below is a result; all are proposed. **(R3)** Where a row says "C0 …: passed", that is a **harness or prototype** result from `Phase1B_C0_Results.md`, run against the pinned Hermes or the production file formats. It is not an integrated production result. The case stays proposed for C1/C2.

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
| M-6 | **(R3)** Key older than 24 h with no row; key 10 min in the future; request with a non-current generation | 422 / 400 / `409 generation_changed`; nothing launched |
| M-6e (R3) | First send on an empty ledger: POST without bootstrap; bootstrap, then mint, then POST | `409 not_bootstrapped` and no ledger created; then accepted (C0 prototype: passed) |
| M-6f (R3) | Client clock 4 min ahead and 1 h behind; accept, explicit reset, retry the old key with its frozen generation | ahead/behind change only freshness; the retry is `409 generation_changed`, never a second launch (C0 prototype: passed; the revision 2 rule re-admitted it) |
| M-6g (R3) | Reset attempted during S2 registration and during acceptance; reset with a live executor lock; reset then an old launch token's S2 | `409 ledger_busy`; `409 executor_live`; S2 refused (C0 prototype: passed) |
| M-6h (R3) | Database-only rollback to a backup taken before key K was accepted (same `ledger_id`, same generation); then explicit reset | K is re-admitted before the reset (the **stated limitation**, demonstrated); `generation_changed` after it (C0 prototype: passed) |
| M-6a | Existing receipt replayed after its key is older than 24 h | `200 replay`; nothing launched |
| M-6b | `not_started` re-arm with a key older than 24 h | replay with `rearm: "expired"`; nothing launched |
| M-6c | Ledger deleted / corrupted / `ledger_id` mismatched after sends were accepted; then a retry of a young key | `503 send_ledger_lost`; after an explicit reset, the young key is **(R3)** `409 generation_changed` |
| M-6d | Pruning with unsettled sends older than 30 days present | unsettled sends survive; settled ones older than 30 days are removed, ≤ 500 per pass |
| M-7 | Kill at every row of §4.8 | recovered state, `owner_turn`, `reply`, lease and retry result exactly as the table says |
| M-7a | Kill the controller between `Popen` returning and `go` | executor exits on EOF without importing Hermes; recovery fences → `not_started`; provider counter 0 |
| M-7b | Kill the controller after `go`, before S2; recovery fences concurrently with S2 | exactly one of: `not_started` (S2 refused) or `generating` (S2 first); never both, never an unrecorded executor |
| M-7c | Executor lock file unlockable for a reason other than busy | `liveness=unproven`, lease held, no new send accepted |
| M-7d (R3) | Executor lock path unlinked and recreated (cleanup/reset race) while E holds the original; lock path missing | identity probe `unproven`, lease held; the create-on-open probe of revision 2 would report `quiescent` (C0 prototype: both observed) |
| M-7e (R3) | E exits while a child in its group runs; a child that calls `setsid` | lease held until the group is empty (then kill → quiescent); the escaped child is outside the boundary and is reported as such (C0 prototype: both observed on Linux) |
| M-8 | Controller killed, executor alive (POSIX) | recovery supervises; executor finishes and writes `executor_finished`; outcome from it; lease released after exit; no second launch |
| M-8a | Stale callback: the old controller wakes after losing its claim | its transitions are refused by the claim check |
| M-8b | PID reuse: executor dead, its PID reused by an unrelated process | lock acquirable → quiescent; no signal sent to the unrelated process |
| M-8c | A new-key "Send again" while the old executor may still run | `409 turn_in_progress` |
| M-9 | Provider `disconnect_before_done`, `truncated`, `malformed` | `failed` with `owner_turn` from receipts; never "Not sent". **(R3)** For the first two the pinned CLI exits 0 with a `finish_reason='length'` row, so the expected outcome is `failed`, `reply_incomplete`, `reply=partial` (C0: exit 0 and `length` observed) |
| M-9c (R3) | Commit-boundary receipts: rollback after the inner helper; retried callback; foreign reuse of a rolled-back id; nested chunked batch; rewrite/compaction/compression copies; public vs tool-call/internal rows; commit raised after callback; receipt write failed after source commit | no false receipt, no duplicate receipt, copies never `user_turn`/`public_output`, `write_unsettled` → `possible`, `receipt_gap` → later writes refused and `owner_turn=unknown` (C0 on pinned SessionDB: passed; revision 2's recorder failed each of the first five as the review predicted) |
| M-9a | Assistant row written, executor killed before `executor_finished` | `unknown`, `reply=partial`; never `complete` |
| M-9b | `state.db` unreadable at read time | links `unavailable`; `owner_turn` unchanged; never `absent` |
| M-10 | O-3 per path: fresh, resumed, continuation, provider error before first byte | records when the owner row is inserted relative to the provider request, per path, as observed |
| M-11 | `recover` scenario (drop, then complete) | launch counter 1; provider counter may be 2 (Hermes's own retry in one turn); `complete` |
| M-12 | Stop during `deltas` | `stopping` → `interrupted` from `exit=130`; partial reply linked as `partial` |
| M-12a | Stop races with normal completion | outcome from facts: `complete` if `executor_finished exit=0` came first, `interrupted` otherwise; never `interrupted` from the request alone |
| M-13 | Deadline with `hang` (timeout shortened by the test double) | interrupt, then kill if needed → outcome from facts; lock acquirable afterwards; no descendant left (checked per OS) |
| M-13a | Kill cannot be confirmed (lock stays busy, simulated by a double holding the lock) | `stopping`, lease held |
| M-14 | Projection rebuild while authorised | `correlation.send_id` resolves to the new ids |
| M-14a | Binding change revokes workspace rows | receipt and operation routes return no links and no content. **(R3)** Checked on both branches: the live in-memory result and the reconstruction after restart |
| M-15 | Source replaced / fingerprint changed / conflicting known platform id / different source namespace | `correlation=lost`; never attached to the new holder |
| M-16 | Foreign terminal writes exactly one user row in the session during the turn, with **equal text**, while the executor writes none | not linked; `owner_turn=absent` (receipts complete) |
| M-16a | Foreign rows after the turn, and a continuation rewrite by another process | never linked to the older send |
| M-16b | Two `user_turn` rows committed by the executor (forced) | `owner_turn=ambiguous` |
| M-17 (R3, restored) | Two **independent** profile homes, each with its own ledger, the **same** `client_key` and the same text sent to both | two receipts, two launches (one per profile); no receipt, link, content or lease of one profile is visible or effective in the other; a `send_id` of one returns 404 in the other. The aliasing test (M-2a) and a UI profile switch (M-22a) do not replace this. |
| M-18 | **(R3)** New session: kill E after Hermes commits the session row but before the fresh-session receipt; kill after the receipt; receipt write fails | no receipt → the session is not attributed, and no owner row can exist in it (fail closed); with the receipt → attributed; never attributed from a pre-call intent |
| M-18a | Resume of a pre-existing terminal session | not relabelled workspace. **(R3)** Its rows link with `source_kind=terminal` while the binding authorises terminal rows, and resolve to nothing after revocation |
| M-18b (R3) | `create_session` on an existing id, `ensure_session` on an existing id, a failed create, a compression child created by direct INSERT | only the genuinely fresh inserts are `created_here` (C0 on pinned SessionDB: passed) |
| M-19 | Bridge unavailable; **(R3)** platform not enabled (§4.5); both on the keyed and the legacy route | `503 send_supervision_unavailable`; nothing accepted |
| M-19a | A wrapped seam missing (patched out) | `capability=unverified_sources`; no session registered; launch/lease protocol unchanged |
| M-20 | Dispatcher crash after `sending`, before the outcome | next run resolves `unknown`; nothing resent |
| M-20a | Two dispatchers load the same queued entry before either claims | second fails the run lock, or, with the run lock bypassed by a double, fails the claim guard; one send |
| M-20b | **(R3)** Crash at each boundary of §7.3: before the intent; after the intent, before the charge; **after the charge, before its marker**; after `slot_reserved`; after `sending`; plus an unreadable outreach ledger | status, delivery calls and `sent_today` per §7.3: `(sent,1,1)`, `(sent,1,1)`, `(failed,0,1)`, `(failed,0,1)`, `(unknown,0,1)`, `reservation_unresolved` (C0 prototype: passed; revision 2's rule gave 2 slots for 1 delivery at the charge-before-marker boundary) |
| M-20c | Late same-attempt outcome after `unknown`; late outcome for a different attempt | same attempt with evidence replaces `unknown`; different attempt refused |
| M-20d | Pre-1B `fold()` reading a 1B outbox | claimed/unknown entries not `queued` |
| M-21 | `hermes send` returns id / no id / `skipped` / partial media error / other error / timeout | outcomes per §7.5; `recipient_resolved: null` when not reported; `mirrored: null` when not reported; `id_scope` present |
| M-22 | Legacy `POST /api/chat` with an old client polling `result.response`, in-process and after restart | response present while retained; `content_retained: false` when not; never regenerated |
| M-22a | New client: double submit, lost response, reload, failed generation, unknown, draft edited mid-turn, profile switch, status lookup from another app instance | behaviours of §6; the UI never falls back to the unkeyed route |
| M-23 | Size and privacy: 10,000 settled sends with realistic facts | measured ledger size and acceptance latency (desktop, labelled); prune pass bounded by the index; operation files at progress/complete/failure contain no prompt, reply, stream or stderr text |

Local full suite plus the CI matrix (Linux 3.11/3.13/3.14, Windows and macOS smoke), as in 1A. **(R3)** Windows and macOS each need their real (unmocked) supervision observations (O-8, O-11) before sends are enabled there. Without them the platform is **refused** (§4.5); a "not verified on this OS" line documents the refusal and does not replace the evidence.

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

The reviewer's U1–U9 and O-A–O-D are decided (§0). **(R3)** These remain for the reviewer or owner:

| # | Item | Proposal in this revision |
|---|---|---|
| O-E | **Decided (R4):** hold migration/rollout pending platform evidence, not engineering. The current route stays; the new path refuses unverified supervisors and never falls back to the unkeyed path once a send has entered it. | Real Windows/macOS supervisor tests on CI hosts and synthetic Termux device evidence before their activation is proposed. |
| O-F | **Decided (R4):** gap latching without re-failing a committed source write. | Shown in C1 with the real CLI exception path, the real SessionDB, an in-process multi-thread case and interrupt-safe fact writes (C1 results §3). |
| O-G | **Decided (R4):** explicit coverage and containment activation gates. | Still open before activation for tool-capable chat: a real tool-using turn, interruption during a tool, full CLI compression continuation, descendant containment for tool processes (O-10), foreign writers (O-5). |
| O-H | **Decided (R4):** structured `attempt` identity on charge records in C2. | C2, later. |
| O-I | **Decided (R5, PHASE1B_REVIEW_R4 §6):** the continuation note is internal machinery, not owner speech. The source row is preserved; nothing is excluded by text or prefix; no historical row is reclassified. | For C1-controlled turns the executor records causal provenance (§4.10.1 R5), receipts list the row as internal, and the owner turn is the real owner row. **Still an activation gate:** the Phase 1A read adapter must exclude that exact row by this provenance (bound to the committed source identity) while keeping an equal-text owner control; rows written outside a C1 executor (terminal, legacy, history) have no such provenance, so that trusted-read path stays marked incomplete and its activation blocked. |

---

## 13. What this document does not claim

- **(R4)** The C1 core exists but is **not activated**: no route, UI, release manifest or real profile uses it, and no normal send goes through it. Its results are integrated synthetic results on Linux only (`Phase1B_C1_Results.md`); they are not a production-send certification, and C1 activation, C2 and C3 remain proposed.
- When Hermes first persists the owner row was observed for 6 paths only (O-3/M-10). The protocol does not depend on it.
- The commit-boundary seam in §4.10.1 is private code at `0e9fc2cc15`. Its coverage was observed for the paths listed in §8 and is not established for the rest (O-2, O-G).
- The Windows job-object behaviour, macOS process groups and Termux storage (O-8, O-11, O-9) are not observed; those platforms are refused, not labelled.
- Automatic detection of a coherent ledger rollback is **not** claimed (§4.1).
- Containment of a process that leaves E's group or job is **not** claimed (§4.5).
- Mirror linkage (§7.7) is unsolved; delivered-proactive provenance remains unsupported.
- Exactly-once execution is not claimed. At most one executor per key, and no second writer beside a possibly-live one, are the claims.
- `ASTRA_PHASE0_REVIEW_R2.md` and `PHASE1A_HANDOFF.md` were not on disk; this revision does not claim compliance with them. It follows PHASE1B_REVIEW_R2, PHASE1B_REVIEW_R1, PHASE1A_REVIEW_R3 and the code at `fc5c1e4`.
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

## Appendix B. Change summary against revision 2 (`7907066`), answering PHASE1B_REVIEW_R2

| Review item | What changed |
|---|---|
| §1 O-A–O-D | Decisions recorded (§0). O-A: refusal applies to legacy and keyed routes, and to platforms without supervision evidence (§4.4.4, §4.5). O-B: count-only; the text is not described as removed (§5.7). O-C: proposed policy, not enabled until O-8 (§4.5). O-D: mandatory reset after known restores, limitation corrected (§4.1). |
| B2.1 commit receipts | The recorder moved to `SessionDB._execute_write`, the only commit point. It publishes candidates only after the outermost call returns, discards retried attempts, and records `write_rolled_back` / `write_unsettled` / `receipt_gap`, failing closed after a gap (§4.10.1). §1.3 corrected: more insert paths, callback retry, maintenance writes before the turn. |
| B2.2 creation vs upsert | `created_here` only from a fresh insert observed inside the transaction. Upsert, ensure and failure never count; the compression child is covered. Early registration without treating an intent as proof (§3, §4.10.2). |
| B2.3 terminal resume | `source_kind`/`source_namespace` recorded per send and validated under current authorisation. No relabelling, no widened authorisation (§4.2, §4.10.3). |
| B2.4 completeness | Receipt coverage (complete / bounded / incomplete / unavailable) decided first. `complete` needs complete receipts and a `public_output` row with `finish_reason='stop'`; new `reply_incomplete`. The crash table and the evidence table reconciled (§4.3.2, §4.8). |
| B3.1 first use | Bootstrap before the client mints; a POST never initialises (§4.1, §5.1, §6). |
| B3.2 reset fence | Server-made `generation` frozen with the key; `admission_floor`/`key_predates_ledger` withdrawn; reset serialised by the shared/exclusive `guard.lock`, fencing tokens and checking quiescence before replacement (§4.1, §5.2, §5.3). |
| B3.3 rollback | The detection claim was withdrawn. The same-generation rollback limitation is stated, and the reset is mandatory after known restores (§4.1). |
| B4 slot boundary | A `reserving_slot` phase and a charge row identified by attempt. Per-boundary recovery with `reservation_unresolved`, and no requeue or refund when consumption is unknown (§7.2, §7.3). |
| B1 executor lock | Quiescence = identity-checked lock **and** an empty process group/job. The escape boundary is stated (O-10). Lock files are safety objects: never unlinked while referenced, probed without create, missing/replaced → `unproven`. Platform enablement table; unverified platforms refused (§4.5). |
| B5 | In-memory legacy results pass the current-authorisation check (§5.7); goal 7 wording (§2); M-17 restored (§10). |
| §7 C0 | C0 changeset (§9); status per observation (§8); matrix rows marked with harness/prototype results (§10); open items O-E–O-H (§12). |

## Appendix C. (R4) Corrections made alongside the C1 core, answering PHASE1B_REVIEW_R3

| Review item | What changed |
|---|---|
| §4 O-E–O-H | Decisions recorded (§0, §12). |
| §5.1 incomplete observation | §4.5 (b): permission/I/O/parse/unsupported/hidepid = unproven; §4.1 step 3 uses the one contract; the create-on-open reset probe is not used. |
| §5.2 coverage precedence | §4.3.2: the bounded definition carries the same restrictions as complete (no unidentified rows); the field table matches. |
| §5.2 owner eligibility | §4.10.1: `user_turn` requires Phase 1A's public/trusted structural eligibility; new class `user_internal`. |
| C1 findings | §4.10.2 freshness by rowid; O-12 continuation note (§8, §12 O-I); §9 C1 split into core (done) and activation (later). |
| Implementation details found in C1 | The executor moves the controller's pipes off fds 0/1 before Hermes runs, so a Hermes descendant cannot hold the stream open after the executor exits (the controller also never blocks closing a pipe a descendant holds). `tmpfs` is added to the supported local file systems (flock and rollback-journal locking work there). A ledger on tmpfs disappears at reboot: if the app-state marker survives on persistent storage this is `ledger_lost`; if the whole profile home and app state are on tmpfs it is indistinguishable from a new profile, which is stated, not detected.. |

## Appendix D. (R5) Corrections answering PHASE1B_REVIEW_R4

| Review item | What changed |
|---|---|
| C1-R4-1 refused reset erased start identity | `attempt_id` (immutable) separated from `launch_token` (revocable); start evidence read by attempt in fencing, recovery, promotion and derivation; cleanup callbacks bound to their attempt/claim (§3, §4.4.3). |
| C1-R4-2 stale executor rewrote a newer attempt's lock | one lock file per attempt; S2 also requires the attempt; the nonce check is unchanged (§3, §4.4.1). |
| §5 lane completeness | explicit required-case manifest; any missing, skipped, duplicated, failed or errored case fails the verdict. |
| §6 O-12 | decision recorded (§12 O-I); causal provenance for C1 turns (§4.10.1 R5); read-boundary change remains an activation gate. |
| §8 CI annotations | only test id, file and exception class are published; details stay in the job log. |
