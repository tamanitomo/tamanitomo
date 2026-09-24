# Phase 0 results: memory correctness and a testable baseline

Report for review of **Phase 0** of `TAMANITOMO_BUILD_PLAN.md` ("persistent Chat, a simpler Life archive, and an Obsidian-style Vault").

| | |
|---|---|
| Base | `e28197ce1849922d463052643ca617a80ad6e58e` (3.0.24, equal to `origin/main` at start) |
| Implementation commit | `103eee5` on `test/phase0-memory-correctness` |
| Scope | Phase 0 only, plus the R2 closure patch (next section). Phase 1A is on the child branch `test/phase1-conversation-contract`. |
| Released / tagged / deployed | **No.** There is no version bump or CHANGELOG entry, and nothing was installed on any live host. |
| Live data touched | **None.** No live ledger was read, migrated or edited. All verification used temporary directories and synthetic profiles. |

Plan sections are referred to by their numbers (0.2 to 0.6). File paths are relative to the repository root.

---

## Closure patch (revision 2 of the plan)

Separate commit on top of `fa04f08`, addressing R2 sections 0.2 to 0.6. The reviewed commits are unchanged. No live data, merge, version bump or release. Where this section and the original report below disagree, this section is current.

### 0.2 Canonical matching: NFC and whitespace only

`canonical_statement()` (Python) and `usFactKey()` (JS) now do exactly two things: NFC composition, and trimming/collapsing a named set of ordinary whitespace (space, tab, LF, CR, FF, VT, no-break space; named rather than `\s` so both languages agree). First-letter lowercasing, final `.`/`!` removal, curly-quote folding and space-before-mark removal are gone. There is no list of exceptions.

- `Robin wrote 5!` / `Robin wrote 5` and `Polish is familiar to Robin.` / `polish is familiar to Robin.` are now `different` cases (plus `May visits…` / `may visits…`).
- The seven old `same` pairs that relied on the removed folds are moved to an explicit `revised` list in `tests/canonical_statement_cases.json` and asserted as different in both Python and JS, at the function and at write time.
- `same` now holds 5 pairs (whitespace runs, tab, newline, no-break space, decomposed accent).

### 0.3 Held-fact decisions: a recoverable protocol

`decide_held()` in `companion_self.py`:

- **Serialized** per human store by `.facts-held.decide.lock`. Lock order: decide lock → `facts.jsonl` lock → `facts-held.jsonl` lock; nothing takes them in another order.
- **Intent first.** An `held_fact_intent` row with a stable `op_id` (hash of held ID + decision) is appended before any effect. It fixes which decision wins.
- **Effect.** `accept` calls `record_fact` with a deterministic ID, so a retry finds the row it wrote. If an equal fact is already active the decision records `duplicate_of` and writes nothing.
- **Decision.** `held_fact_decision` records `decision`, `op_id`, `origin`, and `fact_id` or `duplicate_of`.
- **Recovery.** A crash at any boundary leaves an intent; `held_facts()` shows it as `pending_decision` (read-only, no recovery on read). Deciding the same way again resumes with the same `op_id`.
- **Conflicts.** The opposite decision after an intent or a decision raises `HeldDecisionConflict` before any effect (HTTP 409).
- **Idempotence.** Repeating a finished decision returns it unchanged (`already_decided`), including after the fact was retracted. It is not re-recorded, and nothing else is retracted to compensate.
- **Override, not verification.** An accepted fact carries `held_decision: {held_id, op_id, origin, note}`; the note says it is an owner override. The held row, reasons and evidence are never rewritten.

Tests (`HeldDecisionProtocolTests`, 8): override marking and byte-identical held row; idempotent repeat; opposite decision conflicts with the file unchanged; retry after retraction; `duplicate_of` with an unrelated equal fact left active; **every interruption boundary** (before intent, after intent/before fact, after fact/before decision) × both decisions, including an opposite decision while pending; 8 threads behind a barrier; 6 concurrent OS processes. Plus API tests in `tests/test_app.py`.

### 0.4 Transcript-wrapper facts are held

`PLAN_CONTRACT` is now 3. Under contract 3, a fact whose statement has the `X said: …` shape is a `held` diagnostic with reason `transcript_wrapper`; `apply_plan` puts it in `facts-held.jsonl` exactly as written, and its siblings are applied. It is not re-worded and no second request is made. Untrusted or bad evidence is still fatal. A contract-2 plan keeps the wrapper fatal on resume, as it was when it was saved.

**Stable diagnostics.** A resumed plan is now applied with the diagnostics saved beside it, not recomputed ones, so a retry commits the same subset even if the rules change. The plan is still re-validated for fatal errors. Contract-1 plans (no saved diagnostics) recompute as before. A run with omissions, warnings or holds reports `clean: false`.

### 0.5 Bounded retries and the Needs review queue

- **The whole attempt counts.** The count is written to `<budget>.attempts.json` *before* the request. Connection errors, truncation, JSON decode errors and validation failures are recorded against the attempt, and a process killed mid-generation has still spent it.
- **Backoff.** After a failure, the next attempt waits 15 minutes, then 1 hour. Until then `reflect()` returns `status: waiting` with `retry_after`.
- **Budget identity.** A daily/weekly/monthly budget is its period. A **check-in's budget belongs to the evidence after its watermark** (`last_reflected` + `last_reflected_id`), so a new conversation, which changes the batch key, no longer gets fresh attempts. The watermark and `pending` are unchanged while held.
- **Audited reset.** `reset_attempts()` / `--reset-attempts <budget> --reason "…"` requires a reason and keeps the spent count and errors under `resets`.
- **Needs review UI.** Us → "Remembered about you" shows `Needs review (N)` only when N > 0. It opens the existing memory library in a review mode, which shows the candidate, the exact quote, the source and the reasons, with Accept and Dismiss. There is no new navigation destination, notification, auto-accept or chat send. A failed load says "Could not load memories that need review", never an empty queue. Viewing does not accept. Routes: `GET /api/facts/held`, `POST /api/facts/held/{id}/decide`.

### 0.6 Similarity tokens and bounded groups

- `usFactWords` keeps a `+`/`#` suffix on its word, so C, C++ and C# are never grouped as similar.
- A similar group renders 3 rows. Further rows come 3 at a time from a "Show N more" button, so later evidence is not in the initial markup.

Restored CI is unchanged. Smoke jobs remain smoke jobs: no browser, mobile, light theme, keyboard or touch claim is made here.

### Closure commands and results

```text
env PATH=/usr/local/bin:/usr/bin:/bin TAMANITOMO_REQUIRE_NODE=1 .venv/bin/python -m pytest -q -rs
-> 1396 passed, 464 subtests passed, 0 skipped, 1 warning (existing Starlette/httpx deprecation)
node tests/test_us_ui.js -> passed
```

Environment: Linux (CachyOS, kernel 7.2), Python 3.14 (repo venv), Node 26.7.0.

**CI for the closure commit** `7fef922` (run 35955872873, GitHub-hosted, Node 22): all 5 jobs passed. `linux (3.11)`, `linux (3.13)` and `linux (3.14)` ran the full suite with Node required. `smoke (windows-latest)` and `smoke (macos-latest)` ran on Python 3.13, including the thread and OS-process held-decision races on `msvcrt` and `flock`.

Phase 1A was branched from `7fef922` as `test/phase1-conversation-contract`; see its `Phase1AResults.md`.

Not re-verified in a browser for the closure. The Needs review UI is covered by the Node VM test only.

---

## 0.1 Preserved

Everything 0.1 lists is kept:

- configured pronouns in Us
- the bounded `existing_facts` context
- versioned resumption of saved plans (`PLAN_CONTRACT`)
- exact source quotes
- the report-only `duplicate-facts`
- the Node/pytest harness
- the 3.0.23 Us behaviour

No historical ledger is rewritten. Where old data needed different handling (see "Additional defect" below), it is read around.

## 0.2 Canonical matching is conservative

`kit/scripts/companion_self.py` `canonical_statement()` now ignores **formatting only**. Its docstring states the policy in full:

- **Folded (treated as equal):** Unicode NFC composition, curly vs straight quote marks, runs of whitespace, whitespace before `, ; : . ! ?`, one final run of `.` or `!`, and the case of the **first letter only**.
- **Kept (treated as different):**
  - signs: -5 / +5 / 5
  - `%`, currency and unit symbols
  - `C++` / `C#` / `C`
  - operators, apostrophes, commas, quotation marks themselves
  - word order and negation
  - case after the first letter: `US`/`us`, `Polish`/`polish`
  - compatibility forms: NFKC is no longer used, because it turns `x²` into `x2` and full-width `５` into `5`

The rule is defined by a shared data file, `tests/canonical_statement_cases.json`: 9 "same" and 19 "different" pairs, including every example in 0.2. The Python ledger and the JS preview key (`usFactKey` in `kit/app/static/us.js`) are both tested against that file.

The looser old normalization survives only as `_loose()`, which feeds the **report-only** `duplicate_facts()`.

**Defect found by the new cases:** fact IDs hashed `statement.lower()`. Two statements that now differ (by case) but share evidence therefore collided, and the second write **raised** "Entry ID already exists with different content". IDs now hash the exact statement.

**Compatibility:**
- A retry that spans the upgrade of a fact written under the old ID is answered by the canonical duplicate guard (`written: false`). It is not appended twice.
- A manual `supersedes` retry that spans the upgrade is refused rather than duplicated.

**Supersedes and locking.** Validation of the `supersedes` target now happens inside the ledger lock, in the same guard as the duplicate check.

**The coffee/tea correction.** A valid explicit correction is never cancelled by an equal active fact. It is written, keeps its `supersedes`, and reports the equal fact under `equal_to` with a note. Nothing is merged.

Tests (`tests/test_local_reflection.py`, `FactLedgerTests`):

- `test_a_correction_is_not_cancelled_by_an_equal_fact`: the exact A/B/correction case from 0.2.
- `test_a_correction_target_is_checked_inside_the_lock`: deterministic. A rival correction is injected between entry and append, and the second is refused.
- `test_concurrent_corrections_of_one_fact_leave_one_winner`: 8 threads behind a barrier. Exactly 1 is written and 7 raise.
- `test_retrying_a_correction_is_idempotent`. This was **previously broken**: the retry found the target inactive and raised.
- `test_a_retry_written_by_a_newer_release_is_the_same_row`: new metadata fields do not make a retry look like a conflicting row.
- `test_only_formatting_is_folded`: both the pure function and the write-time behaviour, across all 28 pairs.

## 0.3 Word-bag deduplication no longer hides anything

`usMemoryPreview()` in `us.js` behaves as follows:

- **Same text** (by `usFactKey`, the ledger's rule) shows once in the preview. The library keeps both records.
- **Word-set likeness** (`usLikelySameFact`, unchanged) is now only a reason to **group**. The later item appears under the first as an expandable **"Similar memory (N)"**. There it has its own statement, category, evidence and "Mark incorrect" action, and it does not take a preview slot.
- The preview returns copies. It does not mutate the fact objects the library uses.
- Nothing here writes to the durable store.

`tests/test_us_ui.js` covers the following:

- "Robin introduced Alice to Kit" and "Robin introduced Kit to Alice": both remain reachable.
- The 1050 Ti pair takes one slot and the other stays readable, with its own "Mark incorrect" button.
- All previous "distinct" pairs each get their own slot.
- The library count equals the number of active records.

Browser check on the synthetic profile: 9 facts gave 5 preview rows plus 3 grouped, with "View all 9 memories" (screenshot below).

## 0.4 Question perspective is guidance, not a blacklist

`_about_the_human()` is replaced by `question_concern()` in `companion_local_reflection.py`:

- **Omit, with a diagnostic:** literal machine wording (`the human`, `the user`) or a bare question ID.
- **Warn and keep:** the configured name used in the third person, matched **with its case** and ignoring vocative position ("Robin, …" / "…, Robin?"), in a question that never says you/your.
- No other rejection by name. "What will you do tomorrow?" is fine for someone named Will, and "May I ask about your trip?" for May.

The direct-address instruction in the generation prompt is unchanged.

**Fatal vs nonfatal.** `validate()` still raises on structural or evidence violations. It now **returns** `{'omitted': [...], 'warnings': [...]}` for question-quality issues:

- `reflect()` applies the plan minus omitted questions (`usable()`), keeping every validated sibling entry.
- The saved plan stays exactly as authored, with `diagnostics` alongside it.
- The result reports `clean: false`, plus `omitted`, `warnings` and `held_facts`. A run with omissions is never reported as clean.
- Resuming the same saved plan recomputes the same diagnostics, so commit and retry stay idempotent.

**Bounded retries.** A freshly requested plan that fails validation is saved as `<id>.rejected-N.json`, and the failure is counted in `<id>.attempts.json`. After `MAX_ATTEMPTS = 3` for one period, the model is not asked again and `reflect()` returns `status: held` with the errors. Previously, each cron fire for that period would ask the model again with no limit.

Tests: `test_questions_are_addressed_to_the_human` (rewritten), `test_a_poorly_worded_question_does_not_cost_the_reflection`, `test_a_clean_run_says_so`, `test_refused_plans_are_retried_a_bounded_number_of_times`.

## 0.5 The evidence guarantee, stated correctly

What is established: the evidence is an exact human quote selected by a trusted `quote_id`. That proves the **origin** of the quote. It does **not** prove that the model-authored `statement` is supported by it.

1. **Metadata.** Facts written from a reflection statement carry `statement_origin: "model_paraphrase"` and `statement_check`. That field is a plain sentence saying what was screened and that the statement "is not otherwise verified against its quote". Their `provenance` says the statement was written by the companion and the evidence is exact. `fact_statements()` passes `origin` into the next reflection's `existing_facts`. The Us page adds "Summed up from what you said; the quote below is exact." This wording uses no pronoun for the companion.
2. **Screen, not proof.** `paraphrase_concerns()` in `companion_self.py` flags obvious unsupported transformations that the quote does not contain:
   - a new number or position
   - a flipped polarity (negation)
   - certainty added to a hedged quote
   - a new proper name
   - a new time word
   - a quote whose subject is someone else ("my sister …", "she …", but not "my sister and I")
3. **Held, not promoted.** A statement that fails the screen goes to `facts-held.jsonl`, outside the active ledger. It is not returned by `facts()` or offered as known. `companion_self.py held-facts` lists them. `decide-held --id ID --decision accept|dismiss` settles one; accepting records it as an ordinary paraphrase fact.
4. **Evaluation cases** (`ParaphraseScreenTests`):
   - 13 faithful paraphrases that must pass (dislikes/don't like, "three"/3, "second"/2nd, "No, I work as a nurse", $1,200/$1200, …)
   - 19 cases that must be caught, covering changed quantities, negation, names, dates and times, uncertainty and misattribution
   - **4 documented misses** asserted as not caught (a substituted object with no new name, a contradicted detail, tense or habit changes, exaggeration), so the limitation is explicit and a future improvement has to move a case deliberately

   One case that was drafted as a miss turned out to be caught ("My friend thinks I should quit." → "Robin wants to quit."), so it was moved.
5. **Wording.** The reflection module docstring said "evidence-backed writes"; it now says quote-backed and describes the screen. `docs/LOCAL_STACK.md` now has an explicit "what is and is not checked about a fact" paragraph.

No word-overlap test is presented as proof, and no ledger is rewritten.

**Deliberately unchanged:** a fact statement in the "X said: …" transcript form is still a fatal plan error, as before. The retry cap now bounds it. The plan relaxed only question quality. Whether such statements should be held instead is a question for the reviewer.

## 0.6 Test and release discipline

- **CI restored:** `.github/workflows/test.yml` runs on push and PR.
  - Linux runs the full suite on Python 3.11, 3.13 and 3.14, plus installer syntax checks.
  - Windows and macOS (Python 3.13) run a smoke job: ledger/lock/file tests and all browser-script regressions.
  - It **does not gate a release**; `release.yml` keeps its own Linux gate.
  - This reverses the owner's 2026-09-20 removal of the matrix, which was removed because runner-only failures blocked releases. The separation is the mitigation. The first run is this push.
- **No silent skips in CI.** All JS regressions moved into `tests/test_reliability.py::BrowserScriptRegressionTests` through one helper, `node_or_skip()`. Locally a missing Node skips visibly; with `TAMANITOMO_REQUIRE_NODE=1` (set in CI) it fails. `test_every_script_regression_is_run_here` fails if any `tests/test_*.js` is not wired. All three modes were checked: present runs, absent+required fails, absent skips visibly.
- **Documented runner:** `docs/TESTING.md`.
- **Synthetic preview:** `tools/preview_fixture.py` does the following:
  - serves the workspace from a temp dir with an invented companion (Nova) and human (Robin), seeded facts (including paraphrased, similar and held ones), a random per-run token and `tests/fake_hermes.py`
  - removes the data on exit, including after SIGTERM
  - is covered by `tests/test_preview_fixture.py`
- **Not done here:** the **mock streaming provider**. Nothing in Phase 0 streams, so it is deferred to Phase 1/2, where chat tests first need it.

## Additional defect (outside the plan's list, same area)

`POST /api/facts/{id}/forget` ("Mark incorrect") superseded the fact with a new **active** row whose statement was `"(retired by <name>)"`. That row appeared in Us and was sent back to reflection as a known fact. The existing test compared a value with itself (`assertEqual(x, [] if not x else x)`), so it could not fail.

- **Fix:** the route now records a real `human_fact_retraction` and adds no replacement row.
- **Existing data:** placeholders already in ledgers are recognised by the exact fields the app wrote (`source == 'app'`, `evidence == 'retired in the app'`, `id == supersedes + '-retired'`) and skipped at read time. They are never rewritten.
- **Tests:** `tests/test_app.py` has the corrected test, plus `test_a_placeholder_left_by_an_earlier_forget_is_not_a_memory`, which checks the file bytes are unchanged.

## Exit gate

| Gate item | Status |
|---|---|
| Regression examples in 0.2 to 0.5 covered | Yes. Every example in the plan text is a test case. |
| Original history byte-for-byte unchanged during read/report | Yes. `ReadOnlyTests` snapshots every file under a synthetic profile (facts, a correction, a similar pair, a held fact, a `state.db`), runs `facts`, `fact_statements`, `duplicate_facts`, `held_facts`, `messages` and `context`, and compares bytes. The legacy placeholder test does the same for the API. |
| Concurrent / retried corrections tested | Yes. Deterministic interleaving, 8-thread race, retry idempotence, cross-release retry. |
| Exact commands, passes, skips, environment | Below. |

## Commands and results

```text
# baseline at e28197c, before any change
env PATH=/opt/rocm/bin:/usr/local/bin:/usr/bin:/bin .venv/bin/python -m pytest -q
-> 1361 passed, 459 subtests passed, 0 skipped

# at 103eee5 (no hermes on PATH, Node required)
env PATH=/opt/rocm/bin:/usr/local/bin:/usr/bin:/bin TAMANITOMO_REQUIRE_NODE=1 .venv/bin/python -m pytest -q -rs
-> 1380 passed, 459 subtests passed, 0 skipped, 1 warning (existing Starlette/httpx deprecation)

node tests/test_us_ui.js                      -> passed
python tools/build_release.py --output <tmp>  -> built, 284 source files + integrity manifest (not published)
```

Environment: Linux (CachyOS, kernel 7.2), Python 3.14 in the repo venv, Node 26.7.0.

**CI, first run of the restored workflow** (commit `8996bb4`, GitHub-hosted runners, Node 22): all 5 jobs passed.

- `linux (3.11)`, `linux (3.13)` and `linux (3.14)` ran the full suite with Node required.
- `smoke (windows-latest)` and `smoke (macos-latest)` ran on Python 3.13.

This covers the lock and ledger tests (including the 8-thread correction race) on Windows `msvcrt` and macOS `flock`.

## Browser verification

- Chrome (via Claude in Chrome), desktop width about 1568 px, dark theme, synthetic profile from `tools/preview_fixture.py`.
- Checked through the DOM: the Us preview had 5 rows, 3 "Similar memory" groups (C/C++, the two introductions, the 1050 Ti pair) and "View all 9 memories". 5 paraphrase notes were rendered.
- Screenshot: [`docs/audits/phase0/us-similar-desktop.jpg`](docs/audits/phase0/us-similar-desktop.jpg). It is synthetic data only.
- **Not verified:** phone widths (360/390/768; the window resize did not take effect), light theme, keyboard/touch, screen reader. **No native device testing.**

## Known limitations and open questions for the reviewer

1. **C and C++ are grouped as "similar"** in the preview, because the word-bag tokenizer drops `+`. Both remain visible and the ledger keeps them separate. Should the grouping tokenizer keep symbol suffixes?
2. **Case policy.** Folding only the first letter means "robin ENJOYS tea" and "Robin enjoys tea" are two memories, not one. This was chosen on "prefer a duplicate over discarded information". Confirm, or specify a domain rule.
3. **The screen will hold some faithful facts:**
   - "I love it, no joke" reads as a negation.
   - A hedge like "if" in the quote with none in the statement reads as added certainty.
   - An acronym absent from the quote reads as a new name.

   Held facts are recoverable with `decide-held`, but there is **no UI for held facts yet**, only the CLI. Is a Us/library affordance wanted in Phase 0, or later?
4. **Transcript-wrapper fact statements remain fatal** (now retry-capped). Should they be held or omitted like questions instead?
5. **Retry cap of 3** per period is a constant. Should it be configurable?
6. **CI reversal** of the owner's earlier decision: the owner should confirm. The first run was green on every job.
7. **Mock streaming provider** deferred (see 0.6).

## Files changed

```text
kit/scripts/companion_self.py              canonical policy, exact-statement IDs, supersedes in lock,
                                           correction bypass, paraphrase screen, held facts, tombstone read
kit/scripts/companion_local_reflection.py  question_concern, diagnostics, usable(), retry cap, screened facts
kit/app/server.py                          forget -> retract_fact
kit/app/static/us.js, product.css          usFactKey, Similar memory grouping, origin note
tests/canonical_statement_cases.json       shared Python/JS cases
tests/test_local_reflection.py             ledger, correction, question, screen, held, read-only tests
tests/test_us_ui.js, tests/test_app.py     preview grouping, forget/tombstone
tests/test_reliability.py                  BrowserScriptRegressionTests, node_or_skip, wiring guard
tests/test_preview_fixture.py, tools/preview_fixture.py
.github/workflows/test.yml, docs/TESTING.md, docs/LOCAL_STACK.md, release-files.json
Phase0Results.md, docs/audits/phase0/us-similar-desktop.jpg   (this report; not in release-files.json)
```
