# Journal Day | Reflection archive: results

## Base and changesets

- Declared base: `1b8a50c3daf04e1fa5f8a6d0f412b876c4953864` (accepted Phase 1C R1 documentation head; descendant of accepted tested code `62c223b`). Worktree and index were clean before starting. The owner stash `stash@{0}` was left untouched.
- Branch: `test/journal-day-archive`, a child of the base. Unpushed, unmerged, no version bump.
- **Tested code commit: `c3c31df`** (Journal archive: Day | Reflection over one selected date). Implementation and focused tests.
- Report commit: this file, `docs/JOURNAL_ARCHIVE.md` and `docs/journal_archive_evidence/`. Report-only; no suite was re-run for it.

## What was delivered

- **Backend adapter** `kit/app/journal_archive.py` (read-only): `GET /api/journal/archive` (the dates on record) and `GET /api/journal/archive/<date>` (one day). Registered next to the content routes in `server.py`.
- **Journal page** `kit/app/static/journal.js` replaces the Journal handler that lived in `product.js`. It adds:
  - a Day | Reflection tab pair;
  - date navigation: Older/Newer, a panel with a date input, a calendar, Today, Latest reflection, and search;
  - the `#journals/<date>/<view>` address, with back/forward and refresh.
  The Reflection view keeps the old reader's markup, `richText` rendering, source file name and "pictures from this day" strip.
- **Day view** reuses the Timeline scene-rail markup and CSS (`tl-rail`/`tl-scene`/`tl-card`/`tl-shot`). It shows:
  - scenes, with adjacent identical snapshots collapsed for display;
  - planned, skipped and carried-forward labels;
  - photos attached by capture scene id, opening in the existing photo viewer;
  - the reflection excerpt, with a link to the Reflection view;
  - the day's plan, labelled as a plan;
  - "You two" only from a moment explicitly dated that day;
  - an honest empty or unavailable sentence for each source.
- **Routing:**
  - `showTab` keeps a page's own sub-route;
  - `boot` reads the tab from the first path segment;
  - a `popstate` handler replays Journal history.
- **Unchanged:** Timeline, its routes, navigation entries and pins; Home and Us; Photos; Plans; persistent Chat.

Contract, date rules, association rules, states and the remaining Timeline parity gaps are in `docs/JOURNAL_ARCHIVE.md`.

## Implementation choices

- **One-day endpoint.** Journal gets its own endpoint instead of stitching `/api/life` together in the browser. `/api/life` returns only the latest 100 collapsed events across all days, so it cannot answer "what happened on 12 March". Placing rows by instant also needs the profile timezone on the server.
- **Photos through the catalog.** Photo rows come from `content.catalog(reference_paths=…)`, so blur/rating, etags and the existing media checks all apply. Association uses the capture's recorded scene id and nothing else. This is stricter than Timeline, which places photos by time adjacency.
- **Default view.** Bare `#journals` defaults to Reflection on the latest entry, which is exactly the old landing. A profile with no reflections opens today's Day view.
- **Old handler removed.** The old Journal handler was removed from `product.js`, not left as dead code. `selectedJournal` is still declared there because Home and Timeline set it.
- **Test harness fix.** `showTab` reads `String(location.hash||'')`. In a browser this is the same value; the change only stops `tests/test_us_ui.js`, whose stub `location` has no `hash`, from failing. No test was edited to pass.

## No model calls, no source mutation: evidence

- `tests/test_journal_archive.py::HistoricalDay::test_reading_writes_nothing_and_calls_no_model` hashes every file under the Hermes root and the vault, with sha256 and mtime_ns. It then makes five archive/journal requests with `subprocess.run`, `subprocess.Popen` and `os.system` patched to raise. The trees are identical afterwards and nothing was started.
- `tests/test_journal_archive_browser.py::test_archive_journey_…` asserts that the whole browser journey makes no non-GET `/api` request. The journey covers opening Journal, calendar selection, view switches, back/forward, photo viewer, refresh, shared link and Timeline round trip.
- By construction, `journal_archive.py` calls only readers: `read_events`, `timeline.records`, `catalog`, `journals`, `notes.moments` and `companion_plan.read_for`. It has no write, schedule, operation or Hermes call. `/api/schedule`'s `expected_day` is deliberately not used, because it would present a weekday routine as if it were a record for a past date.

## Verification (all at `c3c31df`, clean tree, synthetic fixtures only)

| Run | Command | Result |
|---|---|---|
| New + affected unit/JS suites | `.venv/bin/python -m pytest -q -p no:warnings -p no:cacheprovider tests/test_journal_archive.py tests/test_content.py tests/test_journal.py tests/test_hardening.py tests/test_image_identity.py tests/test_reliability.py tests/test_workspace.py tests/test_updates.py tests/test_phase1b_c1_integration.py tests/test_phase1b_c3_disabled.py tests/test_schedule_and_face.py tests/test_runtime.py tests/test_local_reflection.py tests/test_cli.py tests/test_vault_index.py tests/test_chat_projection.py` | **535 passed, 33 subtests passed, 0 failed, 0 skipped** |
| Journal browser journeys | `TAMANITOMO_C3_REQUIRE_BROWSER=1 TAMANITOMO_JOURNAL_SHOTS=<dir> .venv/bin/python -m pytest -v tests/test_journal_archive_browser.py` | **5 passed, 0 skipped** |
| Chat browser suites (routing changed under them) | `TAMANITOMO_C3_REQUIRE_BROWSER=1 .venv/bin/python -m pytest -q tests/test_persistent_chat_browser.py tests/test_phase1b_c3_browser.py tests/test_c3_review_browser.py tests/test_phase1b_c3_recovery_browser.py` | **38 passed, 4 subtests passed, 0 skipped** |

The browser was headless Chromium 153.0.8010.12 (Playwright), driving a real uvicorn fixture (`tests/phase1b_c3/fixture.py`) with the fake Hermes. Raw outputs and JUnit files are in `docs/journal_archive_evidence/runs/`; `MANIFEST.json` records source and exported hashes and JUnit counts. Private paths and hostname were replaced with placeholders; outcomes are unchanged.

The "affected" set was chosen by grep: every test file that mentions journal, `showTab`, `location.hash`, `product.js` or `release-files.json`, plus the JS regressions `test_reliability.py` runs. That includes the new `test_journal_archive_ui.js`, which the repo's own check requires to be wired there. No full suite, pinned-Hermes lane, legacy-send audit or R1 selection was run; none of their dependencies changed.

Coverage against the assignment's list:

1. **Historical date.**
   - `HistoricalDay`: scenes, a collapsed walk carrying both ids, a photo per scene joined by capture id, and the reflection with its `Lifelog.md` source.
   - The Day and Reflection routes return the same date, and stored history is untouched.
   - The browser journey repeats this through the UI and opens the photo in the viewer.
2. **Truthful states** (`TruthfulStates`):
   - new/empty profile;
   - scenes without a reflection;
   - unreadable scene file;
   - unreadable journal is reported as unavailable, not as absent;
   - corrupt capture record;
   - deleted photo counted as missing, not relinked;
   - neighbouring file does not make an empty day look recorded;
   - scan-limited library is partial, not missing;
   - planned, skipped and carried-forward rows;
   - **negative case:** a same-day creation image and a capture for a scene not in the record are not attached, and the companion's text "coffee with Alex" produces no "You two";
   - "You two" appears only from an exact `happened_on` date.
3. **Dates** (`Dates` and the Node helpers under `TZ=America/New_York`):
   - UTC-written row placed on the prior New York date across midnight;
   - spring-forward and fall-back days, including both 01:30s in order;
   - date-only, naive and garbage timestamps get no time and do not wander from neighbouring files;
   - invalid dates are refused;
   - client day stepping across both DST changes and a full year.
4. **Routing, compatibility, isolation, stale answers.**
   - Browser: shared link, refresh, back/forward, back from another tab, tab-switch memory, the old `#timeline` link, the saved Timeline pin (phone bottom bar), and Timeline's diary link into Journal. The Chat draft survives all of it.
   - A held stale response for an older date is released after a newer date is drawn and does not replace it.
   - Profile `rowan` sees only its own empty archive.
   - Server: profile isolation, token required, and a linked episode file is not followed.

**Widths.** Phone 390×844, tablet 820×1180 and desktop 1366×900: no horizontal page scroll, and the view tabs, date button and Older button are on screen. The arrow-key tab switch works. Screenshots are in `docs/journal_archive_evidence/screens/`. This is desktop Chromium emulation, not native-device coverage.

## Known limitations (documented, not gates)

- Each Day request walks the content catalog to resolve photo rows, at the same cost as the existing Reflection "pictures from this day" strip. The archive index reads up to 1,500 episode files and every journal page when Journal opens.
- `companion_life.read_events` silently skips malformed JSON lines, so a partly corrupt day file shows its readable rows without a warning. Only an unreadable or linked file is reported as unavailable.
- The Reflection view's "pictures from this day" strip is the existing date-based behaviour, kept for compatibility. It is labelled as pictures from the day, not as attached to the reflection.
- Only plans in `plans/<date>.json` are shown. Legacy `tomorrow.json` and weekday routines are not date records and are not presented as history.
- "You two" depends on moments having an ISO `happened_on`. Free-text dates are not interpreted, so real shared moments recorded that way do not appear on a day.
- Tab switches still replace history, as before. Only Journal date/view choices add history entries.
- Full-page screenshots show the phone's fixed bottom bar mid-page; that is how full-page capture renders a fixed element.
- Timeline parity gaps are listed in `docs/JOURNAL_ARCHIVE.md`. Timeline is not retired and its preferences are not migrated.

Keyed activation and the Phase 1C continuity options remain OFF. No live profile, model, platform or dispatcher was used. Nothing was pushed, merged, released or deployed.
