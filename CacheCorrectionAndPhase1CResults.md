# Cache-authorisation correction (review 5027108) and Phase 1C continuity: results

Keyed activation stays **OFF**. Every new path is behind a development option that nothing shipped sets. There is no
version bump, no `release-files.json` change, and no push, merge, release or deployment. No live profile, credential,
model, platform or dispatcher was used. All data is synthetic.

**Verified start:** `test/chat-trusted-read-integration` at `5027108839ef…`. The worktree was clean and the index empty.
There were no later owner commits. `stash@{0}` (WIP on main, e5b7e02) was preserved and not applied. The review
archive's 19 manifest hashes matched. The review's archive SHA `d5755c03…` is the earlier 5027108 packet.

| Branch (local, unpushed) | Commit | What |
|---|---|---|
| `test/chat-trusted-cache-correction` (from 5027108) | `b7b57ec` | Correction code, the reviewer's candidate patch **unchanged**, and the reviewer tests vendored byte-identical |
| | `8d48dd2` | Docs only: CHAT_CONTRACT §8.8 failure rule |
| `test/phase1c-continuity` (child of 8d48dd2) | `c0c4f5f` | Phase 1C code and tests. **Tested SHA**, tree `75923112…` |
| | (this commit) | Docs only: CHAT_CONTRACT §9, this report, `docs/phase1c_evidence/` |

## A. Cache-authorisation correction (finding C1)

**Patch inspection before applying.** `Projection.sync` commits a binding reset in its own transaction before it reads
the source, so a failure after a revocation really does follow a purge. The route change returns only
`projection_id`, read through the existing scoped `projection.snapshot(1)`. It returns `null` if that read fails, and
it re-raises for a disabled build, so that build's contract is unchanged. The store fields the patch touches
(`settled`, `stream`, `replies`, `request`) all exist. `invalidateHistory` drops rows, links and cursor. It retires
settled intents and turns unsettled ones into request status. The draft is kept. `401` now also invalidates, which
fails closed. It was applied with `git apply` as supplied.

| Check | Result |
|---|---|
| Reviewer witness `run_cache_witness.py` on 5027108 (unmodified) | **2 passed / 2 failed**, reproduced: `revocation_success` and `outage_only` pass; `invalidated_outage` and `revocation_outage` keep the revoked marker |
| Same witness after the patch (and again at c0c4f5f) | **4 passed / 0 failed**. The draft and pending intent are kept in all four, source bytes are unchanged, and 0 sends were made |
| Reviewer browser file `test_trusted_cache_browser_review.py` (3 tests), on unfixed code | **2 failed** (both revocation paths keep the marker), 1 passed (the same-generation control). So the tests really do test the gap |
| Same, after the patch | **3 passed** |
| Adjusted existing ordinary-outage browser test | Passes. Its history-retention assertion is kept; only the mocked 503 body gained the real `projection_id` |
| Focused API/recovery selection (the reviewer's 7 files) | **98 passed**, 35 subtests. `pyte` is installed here, so the native-console test the reviewer had to deselect also ran. The reviewer's figure was 96 + 1 skip + 1 deselected |
| All browser journeys (the new file + trusted, persistent, C3, C3 recovery, C3 review), with Chromium required | **60 passed**, 8 subtests |

## B. Phase 1C continuity (`c0c4f5f`)

**One reader** (`kit/app/chat_sources.py`, `owner_evidence` / `EvidenceView`). It uses the projection's own
`HermesSource.read` connection and `classify()` predicate, so membership has a single definition: the owner binding,
the workspace registry, Telegram DMs with a recorded platform id, and send-provenance exclusions. There is no new
database, identity policy, model call or framework. It adds:
- `forward` reads in `(timestamp, id)` order. That is exactly the keyset reflection's watermark already used, so
  existing watermarks keep their meaning.
- A bounded `recent` read, and session lineage.
- Evidence-only omissions: `not_public`, and `compression_carryover`. The second covers rows Hermes copies into a
  compression child. I checked the pinned `publish_compression_child`: copies get new ids but keep their original
  timestamps. A row counts as carryover when it is not newer than its child session.
- An unreadable send ledger, and (after review edfee06 R1, `62c223b`) a ledger with **known lost provenance** (`incomplete`), **fail closed** (`EvidenceUnavailable`). Limits are stated in `view.limits`.

**Reflection** (`companion_local_reflection.py --trusted-sources`, i.e. `reflect(trusted=True)`). It returns the same
return shape and uses the same batch bounds, keys, retry budget, plan contract 3 and `<messages.id>:<n>` quote ids.
Rows gain `channel`, and a saved plan without it still applies. Only owner rows are quotable; companion rows are
context. A `--human-user-id` outside the binding is refused. An unreadable store raises **before** an attempt is
counted, so no model call is made and the watermark does not move. The default Telegram-only query is unchanged.

**Handoff** (`companion_context.py`, `TAMANITOMO_DEV_CROSS_CHANNEL_HANDOFF=1`). It sits inside the existing
continuity fence at priority 6, with its own cap and omission line. The full rules are in CHAT_CONTRACT §9.3:
- Destination is the hook payload's top-level `session_id`.
- Non-owner sessions get nothing.
- An unknown session or an unreadable store gets a one-line diagnostic.
- Selection is deterministic: the last 24 hours, excluding the destination and its compression lineage, at most 6
  items, 280 characters each, and `min(1800, cap/6)` characters **of quoted lines**. The header and omission line
  are extra (N1 below).
- Items are labelled with time, channel and speaker, and the header says they are quoted data, not instructions.
- Fence markers inside quoted text are defused.

### The five checks

| # | Check | Evidence |
|---|---|---|
| 1 | Shared reader includes owner workspace, terminal and Telegram rows. Stranger, group, cron, gateway-`cli`, a mirrored Telegram row with no id, and another profile's row are excluded and counted. Revocation, withdrawn workspace/terminal trust, and profile isolation hold | `SharedReaderTests` (7) |
| 2 | Quotes resolve to real owner rows across channels, and a fact's `source` names the session/message. Companion or foreign rows cannot be selected. Forced small batches process every trusted row once, in order. An outage spends no attempt; an unreadable ledger fails closed; source bytes are unchanged; a saved plan in the old shape applies without a new model call. Existing reflection, held-fact and decision tests pass | `ReflectionTests` (7) + `tests/test_local_reflection.py` |
| 3 | **Pinned Hermes 0e9fc2cc15 at the real request boundary.** The tree was re-exported and verified against the manifest. A `hermes chat --resume <term session>` turn ran with the hook registered and the mock provider's request body inspected. The current user message starts with the raw owner text. Inside the fence are the two labelled Telegram lines ("Robin" / "Nova (you)"). The stranger row is absent. The session's own first message appears once, as native history, and not in the handoff. There is one handoff per request, and it is not stored as a message. Row delta is exactly 4 over 2 turns. With the flag off, the control has no handoff | `test_phase1c_pinned_hook.py` (required-pinned run), `phase1c_pinned_handoff.json` |
| 4 | Diagnostics instead of guesses: a missing or unknown session, and an unreadable store. A small window names "recent messages from other channels" in the omission notice. Item/character caps and an older-messages line hold. Nothing is added when nothing is recent. The hook subprocess (real stdin payload shape) writes no source bytes. The pinned run shows the same model request count with and without the handoff (1 = 1) | `HookHandoffTests` (9) + `QuietHandoffTests` (5) |
| 5 | Page → Vault → dock, immutable pending recovery, continuation choice, and default-disabled behaviour | The 60 browser tests and 98 focused tests above, at c0c4f5f |

**Counts at `c0c4f5f`** (exported to `docs/phase1c_evidence/`; 15 files, manifest validated, host, home and job paths redacted):
- Cache witness: 4/0.
- Focused selection: 98 passed.
- Browser (Chromium required): 60 passed.
- Phase 1C + pinned hook + reflection (pinned required): 79 passed.
- **Full ordinary suite, once: 1795 passed, 52 skipped.** All skips are the optional pinned lanes: 24 C0 and 28 C1,
  including the new pinned hook test, because they were not configured in that run. That suite ran on the
  c0c4f5f tree before the docs-only 8d48dd2 edit; no test reads CHAT_CONTRACT.
- The full C1 pinned lane was not rerun. Only the new hook test ran pinned.

## Limits and what is NOT claimed

- A request containing context does not prove the model will use, recall or report it. Visible unified history and
  context in an outgoing request are separate claims.
- **Compression.** A handoff row written without its original time looks like a new message. Native-history dedupe
  is by session lineage, not content. A copy outside compression lineage would be quoted. Continuation notes outside
  keyed sends have no provenance (this is inherited). In-place compression reads remain an open gate.
- **Default reflection unchanged, gaps included.** The Telegram-only query still reads a group chat under the owner's
  user id, and another profile's rows in a shared store. The trusted reader fixes both, but only when opted in.
- **Scheduling.** Nothing schedules `--trusted-sources`. Any existing reflection job is unchanged.
- **Per-turn cost.** The hook reads at most 400 source rows per turn while enabled.
- **Still open (unchanged):** activation gates, tool/descendant containment, native platforms, physical phone. The
  review's follow-ups (plain-recency suggestion, timestamp display, deletion lag) were not touched. On the reviewer's
  prose note: restored requests show as request status cards (accepted C3 behaviour). An earlier report called this
  duplicate owner presentation, which it is not.

## R1 correction after review edfee06 (known lost provenance)

**Verified start:** `test/phase1c-continuity` at `edfee06132729460ac08c879c3d0a973e69e96a2`. The worktree was clean and
the index empty. There were no later owner commits, and `stash@{0}` was preserved. The review packet
`TAMANITOMO_R1_REVIEW_PACKET_edfee06.zip` (SHA-256 `9f73362b…`) was extracted outside the repository. Its `REVIEW.md`
and `CLAUDE_NEXT_TASK.md` are byte-identical to the Markdown copies supplied earlier.

| Branch (local, unpushed) | Commit | What |
|---|---|---|
| `test/phase1c-provenance-guard` (child of edfee06) | `62c223b` | **Tested SHA**, tree `5c985db1…`. The reviewer's candidate guard, applied unchanged with `git apply` (3 added lines in `owner_evidence`), plus `tests/test_phase1c_provenance_review.py` vendored byte-identical |
| | (this commit) | Docs only: CHAT_CONTRACT §9.1/§9.2/§9.3, this addendum, `docs/phase1c_r1_evidence/` |

**Patch inspection.** `incomplete` is the existing `ReadModel` state set when a reset recorded `provenance_lost_at`.
The guard raises the existing `EvidenceUnavailable` before the source is opened, exactly as `unavailable` already did.
Its callers already handle that exception:
- `trusted_messages` turns it into a `ValueError` before `reflect()` counts an attempt. No planner call is made and the
  watermark does not move.
- `cross_channel_handoff` turns it into its "could not be checked this turn" diagnostic.

`ok` and `none` are untouched. The Chat projection does not call `owner_evidence` and keeps its disclosed degraded
display.

| Check (my execution, synthetic fixtures, `TMPDIR` on a disposable tmpfs directory) | Result |
|---|---|
| The 4 reviewer regressions on edfee06, before the patch | **1 passed / 3 failed**. That reproduces the finding: the readable-provenance equal-text control passes; lost provenance was quotable, reflection proceeded, and the handoff quoted the note as Robin |
| The handoff's focused selection at `62c223b`: `test_phase1c_provenance_review`, `test_phase1c_continuity`, `test_local_reflection`, `test_local_context` | **85 passed, 5 subtests** |
| Reviewer `observe_phase1c_edges.py`, unmodified, on a throwaway edfee06 clone | N1 section 1,911 characters at a cap of 1,800 (5 quoted lines). N2: 0 eligible results, `complete: false`, older authorised row present. R1 state reproduced pre-fix |
| Same observer at `62c223b` | Its third section stops at the new `ValueError` from `trusted_messages`. The guard is refusing the state that section assumes. It was not modified to work around this |

No full suite, browser or pinned run was repeated for this guard, as the handoff allows. The earlier counts in this
report are unchanged and still belong to `c0c4f5f`.

**Accepted known issues (documentation only, no code change):**
- **N1.** The 1,800-character handoff cap counts quoted lines only. The header and omission line are added on top.
- **N2.** When the 400-row recent scan is used up before it reaches an eligible row from another channel, the handoff
  is left out silently. There is no omission notice, although the scan was incomplete.
