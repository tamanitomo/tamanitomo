# Phase 1B C3 — recovery closure (review of a8b4e52)

**Branch:** `test/phase1b-c3-recovery-closure` (local, unmerged, unpushed), child of the reviewed
`test/phase1b-c3-keyed-client`.
**Verified base:** `a8b4e52324391cae244018b5711282e9798cfad9`, tree `1caf0880c290cb718891c6f466b19db4ae62bfc2`,
clean worktree. The owner's `stash@{0}` (`9ada0ce`, WIP on main) is preserved, not applied.
**Tested implementation:** `34854bc` (tree clean before and after every run below).
**This report and `docs/phase1b_c3_recovery_evidence/`:** a later report-only commit.

Keyed sends stay OFF: `chat-sends.js` is still served only with `chat_sends=Options(client=True)`,
which no shipped entry point uses, and it is not in `release-files.json`. U1/T1 stay closed. There are
no C1, C2, backend, protocol, dispatcher, containment or compression changes, and no version bump.

## What changed (client only: `kit/app/static/chat-sends.js`)

| | Defect / gap | Change |
|---|---|---|
| R1 | A `null` from `acquire()` (sign-in pause, handled refusal) threw in `drive()`'s `finally` and left the key in `drivers`, so Check now did nothing. | `drive()` keeps an immutable `key`, releases it on every path, and assigns `p` only from a non-null result. Check now retries the same stored request after sign-in. |
| R2a | A refusal of a *replay* (e.g. `send_ledger_lost`) was treated as proof that the original was never accepted: the result was **Not sent** and the pending intent was erased. | There is a per-page `fresh` set of keys minted by an explicit Send whose every POST so far was provably refused. A 401 keeps a key in the set (auth middleware answers before any route). An unusable answer, a reload, or an unresolved outcome removes it. Only a fresh key's refusal is **Not sent**. For any other key, a refusal first looks the key up. If it finds a send, the client adopts and follows it. Otherwise the request becomes *unresolved*: the exact intent, its slot and the exclusion stay, and a manual Check now retries the same key. |
| R2b | An unreadable receipt after operation 400/404 called `settle()`. | It becomes *unresolved*. 403/404 keep the "not visible from here" wording. |
| R2c | `settled: null` (the F1 unresolved view) fell through to `finish()`. | Only `settled === true` reaches `finish()`. Anything else is *unresolved*. |
| R3 | A delayed bootstrap cleared the saved draft through a detached textarea, including a newer view's draft. | `clearSubmittedDraft()` clears only when no composer edit happened since the submit. A capture-phase `input` counter serves as the edit generation. The saved draft must also still hold the submitted text. Only the *current* composer is emptied. |
| B1 | After a reload mid-turn, history drew the recorded owner row *and* the client drew a provisional owner bubble (2 bubbles). | A restored intent that no history row is known to be yet is drawn as a separate, labelled request status (`.keyed-request`, `role=status`, "Your message, not yet in the conversation record here", with its text and actions), not as `.bubble.user`. At settlement, `adoptRow` reconciles by source ids (unchanged). If no row was adopted, the status is promoted to the ordinary owner bubble. Nothing is text-matched, and nothing in history is hidden. |
| B2 | Live/unproven confirmation guard not browser-tested. | No code change (no bypass existed). It now has a browser test. |

Wording changes: new unresolved texts say whether acceptance is **known** or **not confirmed** and
that the record is **unavailable right now**. They promise no automatic check; the only path is
Check now. The client-bug `catch` also used "The app will check again" without scheduling a check, so
it now says "Check now to ask again with the same request". The automatic-backoff wording in
`acquire()` is unchanged because that path does retry.

**Relation to the supplied candidate patch.** I inspected it and used its structure for R1 and R2 (driver key,
`unresolved()`, `settled !== true`). This implementation differs from it in four places:

1. Freshness survives a 401 pause. This keeps "fresh refusal → Not sent" after sign-in, which the
   candidate turned into unresolved.
2. A refusal of a replay looks the key up before painting unresolved. That recovers the send instead of
   leaving the owner stuck.
3. R3 uses an edit generation plus the saved-draft check, not only `box === $('chat-message')`. Under
   the candidate, navigating away and back during bootstrap with no typing re-showed the already-sent
   text in the new composer. See `test_navigation_during_bootstrap_without_typing…`.
4. The 404 wording.

The candidate did not address B1.

## Tests

Reviewer files are vendored **byte-identical** under `tests/phase1b_c3/review_a8b4e52/`
(`test_c3_recovery_unit.cjs` `34d74620…`, `c3_real_http_witness.cjs` `4337d6c2…`, `run_http_witness.py`
`3ef62c87…`). They are run by `tests/test_phase1b_c3_recovery.py`, together with the closure's own
`tests/phase1b_c3/recovery_unit.cjs` (6 cases).

`tests/test_c3_review_browser.py` is the reviewer's browser file with two recorded adaptations, both in
`test_send_again_recheck_refuses_live_or_unproven_receipt`:

1. **Harness bug.** Playwright calls a two-parameter handler as `(route, request)`. That overwrote the
   `value=liveness` default with the `Request` object (`TypeError: Object of type Request is not JSON
   serializable`). The handler is now built by a closure factory.
2. **Strengthened.** The second iteration could pass on the first iteration's leftover hint text. The
   test now clears `#chat-status` before each iteration and asserts that a new receipt read happened.

The full diff is in the packet as `reviewer_browser_adaptation.diff`. All other lines are unchanged.

`tests/test_phase1b_c3_browser.py::test_reload_mid_turn…`: the documented `1 <= count <= 2` is
replaced by the original requirement. It asserts exactly one owner bubble at four samples across the paused
interval, the presence of the labelled request status, and the status's removal after reconciliation.

`tests/test_phase1b_c3_recovery_browser.py` (new, 4) covers:

- an equal-text earlier message during reload: 2 bubbles, never 3, and none hidden
- navigation during bootstrap without typing: the sent text does not come back
- typing during bootstrap in the same view, even back to identical text: the edit is kept
- lost accepted response + synthetic ledger loss: the request stays unresolved; after the ledger is back, Check now completes with the same key, one launch and one owner/reply

## Results

The environment for every run below: Python 3.14.7, Node 26.7.0, pytest 9.1.1, Playwright 1.63.0,
Chromium 153.0.8010.12, synthetic homes, Hermes not on `PATH` (`PATH=/usr/bin:/bin`), and
`TAMANITOMO_REQUIRE_NODE=1 TAMANITOMO_C3_REQUIRE_BROWSER=1`. No skips occurred in any run.

**Against the unchanged reviewed client (a8b4e52):**

| Check | Result |
|---|---|
| Reviewer Node unit (`test_c3_recovery_unit.cjs`) | 5 failed, 3 controls passed. This reproduces the review; the failures and controls are the same. |
| Reviewer HTTP witness, lost / known | Both: pending erased. Lost → "Not sent", known → the unknown wording. 1 send, 1 launch, no ledger recreated, 1 key. This reproduces the review. |
| Supplied browser/default selection (21) | **21 passed** |
| Reviewer browser file as supplied (6) | **6 failed.** Five are real reproductions in Chromium: R1 (reply timeout after Check now), R2a (`'Not sent'`), R2b (pending None), R3 (`'' != 'New draft after navigation'`), B1 (`2 != 1`). The sixth is the harness `TypeError` above. After adaptation, that test **passed** on the base client: the guard already held. |
| Closure Node checks (6) | 5 failed, 1 control passed |
| Closure browser file (4) + supplied reload test at the restored requirement | 5 failed |

**At 34854bc:**

| Check | Collected | Result |
|---|---|---|
| C3 browser selection: supplied 21 (`test_phase1b_c3_browser.py` 16 + `test_phase1b_c3_disabled.py` 5), reviewer 6, closure 4 | 31 | **31 passed**, run twice (34.8 s, 34.5 s) |
| `tests/test_phase1b_c3_recovery.py` (reviewer unit 8/8, closure unit 6/6, HTTP witness lost+known) | 3 (+16 subtests) | **3 passed** |
| Reviewer HTTP witness, direct | 2 modes | exit 0. Lost: pending kept, "…not confirmed…unavailable right now…". Known: pending kept, "The app accepted your request…". Both: 1 send, 1 launch, no ledger recreated, 1 key. |
| Retained U1/T1/C1/C2/export selection (the reviewer's 9 files) | 96 | **96 passed, 127 subtests.** This equals the reviewer's independent count. |
| `tests/test_reliability.py` (shared static-script regressions) | 34 | **34 passed**, 17 subtests |

The collected counts overlap; they are not a unique aggregate.

**Not rerun, with the reason.** The full suite and the 27-case pinned Hermes lane were not rerun. The
change is confined to a script that only the disabled client build serves, plus tests. No backend,
shared static file or lane module changed (`git diff --stat a8b4e52 34854bc`). The lane and negative
manifest tests are untouched, and the prior results at effc80c stand for them. Neither the C2 live
dispatcher nor a real Hermes/profile was used.

## Remaining limitations (not added to this task)

- An unresolved intent holds this tab's one-pending slot and the action exclusion until Check now
  finds evidence. The same holds if the ledger stays missing, or if a replay of a more than 24-hour-old
  key is refused with `key_expired` and the key lookup finds nothing. The only other ways out are
  closing the tab (the slot is in `sessionStorage`) or the reviewed reset flow. This is the
  conservative choice the review asked for. A dedicated "give up on this request" flow would be new
  UX and was not designed here.
- The request status also appears after a same-page return to Chat (not only after a reload), because
  the Chat view is rebuilt and has no link to the history row either.
- Still tracked, unchanged: containment, compression-read identity, native/unsupported platforms, the
  Kelvin-sign/ASCII tag-policy consistency, and the different-conversation pending-tab UX.

## Evidence

`docs/phase1b_c3_recovery_evidence/` was exported by `tools/evidence_export.py --kind executed`: 26 files,
all re-parsed and validated, with home, job and host paths redacted. `runs/` holds the 34854bc runs and
`baseline_a8b4e52/` holds the runs against the reviewed client. Earlier evidence directories and
`Phase1B_C3_Results.md` are unchanged.
