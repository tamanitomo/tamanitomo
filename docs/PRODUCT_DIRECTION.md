# Product direction

Agreed with the product owner on September 12, 2026.

## The everyday experience

Companionship and continuity lead. A user should be able to chat casually every day, then ask the same companion to investigate a practical problem, such as a Plex server failure, using Hermes's tools and configured access. A companion hosted in the cloud must clearly distinguish its host from the user's home systems.

The workspace should welcome ordinary users while rewarding power users with advanced configuration, image workflows, and voice cloning. Good defaults and guided setup should reduce the knowledge needed to begin. Advanced capabilities remain available.

Hermes administration is equally important and belongs in this workspace. Simplifying navigation must not bury maintenance, account configuration, gateway controls, diagnostics, or recovery. The goal is one understandable place to manage the whole experience.

## Memory

Eventually, facts about the human—possessions, education, preferences, and life events—should be shareable across companions, while relationship-specific history stays with the relevant companion.

A new classification or sharing scheme is deferred until other polish is complete. In the meantime, settings changes must not make existing records disappear. Conflicting ledgers must be preserved and surfaced for resolution, never silently merged or overwritten.

## Mood and continuity

The owner wants a richer visible present: current mood, recent emotional history, additional status, and indicators that meaningfully influence conversation. These should be part of the companion's character and continuity, rather than decorative meters.

The distinction between two hours, an ordinary overnight absence, and two days matters. The mood pass should account for sleep, daily rhythm, relationship context, and personality rather than applying the same elapsed-time response to everyone. The owner welcomes affectionate or lightly reproachful greetings appropriate to that context.

The expanded direction includes visible game-like feelings that influence chat. Repeated relationship experiences should matter: repair or forgiveness must not erase the history of an earlier rupture. Absence alone is not evidence that a particular relationship event occurred. Known sleep and regular commitments should explain awayness without inventing the human's current activities. Contact quiet hours are delivery restrictions, not proof that the human is asleep.

Daily interaction should resemble a messaging app; Journal should prioritize browsing and reading entries; Photos should prioritize browsing the collection. Keep Hermes administration directly accessible as these views become simpler. Advanced image workflows and voice cloning belong behind understandable defaults, with clear routes into their controls.

Keep operational facts separate from authored emotional state: an actual server failure, a pending tool request, and a fictional mood must never be confused. Tool success still needs evidence.

## Work sequence

1. Dependability: fix the confirmed audit issues in contact controls, media privacy, URL handling, record preservation, edit protection, operation recovery/ownership, and settings consistency.
2. Intuitive daily use: streamline create/adopt, connect, chat, inspect status, and recover from a problem. Keep Hermes administration directly reachable. Preserve access to specialist studios.
3. Real acceptance: exercise required host/provider combinations, interruption and recovery, and a scheduled overnight run using disposable profiles and deliberate delivery destinations.
4. Richer mood/status behavior and, later, finer-grained memory sharing.

## Reliability pass implementation

The first pass adds explicit unlimited-contact controls; shared photo validation and human-record preservation; consistent job synchronization from both settings editors; profile-owned operation results and recoverable polling; concealed chat/activity images; separate raw and HTML-escaped media URLs; and unsaved-edit guards for notes, companion documents, profile settings, and Preferences.

Page asset URLs are content-versioned to prevent an update from mixing cached controllers with newer helpers. This pass does not redesign the mood model, add infrastructure credentials, change real companion memories, or deploy the workspace.

Verification: 683 automated tests passed on the local Python environment, including the new API and JavaScript regressions. Browser checks verified daily-cap validation, the unsaved-work indicator, Stay/Discard navigation, saving a note, and concealed chat images with deliberate reveal. The source release built with 196 files, and every packaged hash was checked. Real microphone/provider playback, Windows acceptance, and overnight operation remain separate acceptance work.

## Mood audit follow-up

At the start of the mood audit, the indicators were a 96-hour elapsed-gap calculation and a keyword average of recorded moods, without expected absences or personality-weighted relationship history. Presence already recorded mood, wants and private stance and carried them into chat context; this was the foundation to extend, rather than creating a competing emotional truth.

The follow-up fixes whole-word mood scoring ("unhappy" previously matched "happy"), suppresses locally negated words, and removes both Markdown and JSON snapshots when indicators are disabled or no longer have evidence. The scorer remains a limited heuristic, not a semantic interpretation of arbitrary prose. These fixes are not the full requested emotional model.

Follow-up verification: 685 automated tests passed, including the added scoring and stale-snapshot regressions; `git diff --check` passed. Existing dependency deprecation and SQLite resource warnings remain. These follow-up changes are local and have not been deployed or rebuilt into the earlier release archive.

## Daily interface pass

Conversation is first in the everyday navigation; Hermes settings and Jobs & health remain direct destinations. Secondary pages move into More, and provider terminology now finds Hermes settings in the page finder. Chat uses the remaining viewport height, formats saved messages, separates dates, preserves manual scroll position while replies stream, and rejects outdated history responses after switching conversations.

Photos groups the collection by date with compact thumbnails and sequential lightbox navigation. Capture diagnostics are collapsed initially. Photo and journal filters survive navigation within the app; Journal retains its selected entry and uses a sticky list on wider screens. These are incremental improvements, not completion of the requested product redesign.

Verification: 44 relevant Python tests passed, together with JavaScript tests for escaped formatting, grouped photo indices, reversed chat-response ordering, and the earlier reliability checks. In the disposable browser fixture, the chat composer fit the 798×732 viewport, saved Markdown rendered correctly, six images appeared under three date groups, lightbox navigation worked, a filtered journal entry survived a visit to chat, and searching "providers" returned Hermes settings. No real provider calls or companion data changes were made. Broader device acceptance, deeper archive browsing, and the contextual emotional model remain unfinished.

## Contextual feelings implementation

The next pass adds `companion_feelings.py` and the Together controls described in `docs/FEELINGS.md`. The shared calculation includes weekly/overnight expected absences, temperament sensitivity and recovery, evidence-backed connection/rupture/repair experiences, repeated-topic history, and corrections that preserve the audit trail. It enters both live chat and scheduled context, while authored mood and private stance remain authoritative. Home and Together display the same indicators, and chat links to them.

Verification: the full suite passed 697 tests. Dedicated tests cover routines, DST, overlap, repeat rupture after repair, persistent trust, correction, retry and revision behavior, profile isolation, incoming-message return context, and chat/scheduled injection. Browser checks saved temperament and sleep, recorded a rupture, recorded repair, corrected the original entry back to baseline, and retained all three records. JavaScript regressions and syntax checks passed. The only data changed during browser testing belonged to the disposable fixture.

Remaining acceptance is material: real providers must demonstrate appropriate tone and successful experience recording, richer archive browsing still needs work, and the wider device/host matrix is not proven. The full goal remains active. These changes are local; no cloud companion has been deployed or modified.

## Chat archive browsing

The conversation picker and message view now offer earlier pages. Cursor ordering includes a tie-breaker, so identical timestamps and newly appended messages do not cause older pages to repeat or skip records. Profile scoping and message visibility filters remain enforced. Returning to a saved conversation outside the newest 100 no longer silently creates a new chat.

Browser verification used 116 disposable conversations and a 427-message thread. The picker reached the old thread; message pages progressed from 200 to 400 to all 427, marked the beginning, and the same thread remained selected after visiting Together. API regressions cover timestamp ties, concurrent appends, invalid cursors/page sizes, hidden records, and isolation. Gallery/journal archive depth and real-provider acceptance remain separate outstanding work.

## Journal archive reading

Journal now pages through entries beyond the old 1,000-entry cap, searches the scanned archive, and loads long entries fully in the reader. Existing file-size and aggregate scan limits remain explicit. The list and paging button share one sticky container; browser testing caught and fixed the list covering that button.

Verification used 1,006 disposable entries, including a 120,018-character entry. The reader reached its final sentence, search found the oldest entry outside the loaded pages, and the paging button loaded the next 100 entries with its click target unobstructed. API regressions cover paging beyond 1,000, full-text search beyond the preview, full-entry retrieval, profile isolation, and invalid parameters.

Hermes is installed locally (0.21.1) with an OpenAI Codex provider configured, but no real-model calls were made. Usage reached 42% remaining during this pass, so further implementation and provider calls are deferred to preserve the owner's 40% reserve. Gallery scan depth, real-model behavior/experience-recording acceptance, and wider device/host verification remain unproven; the full goal is not complete.

Final verification for this journal pass: 704 tests passed in 73.7 seconds, along with the JavaScript regressions and `git diff --check`. Existing dependency deprecation and SQLite resource warnings remain. The source-only daily-polish review archive includes the current changes; no deployment was performed.

## Gallery archive and initial model acceptance

The owner extended the usage reserve to 30% remaining. Photos now loads 120 images at a time, reaches beyond the previous 1,500-item cap, and applies search, day, and collection filters before paging. Duplicate copies retain album membership and the strictest concealment setting. The separate 10,000-file scan boundary remains explicit. Rating an image outside the first catalog page now finds its duplicate copies before updating their ratings.

Browser checks reached all 266 unique fixture photos over three pages, found the oldest photo through search, and showed that same image in Favorites. They caught a false scan-limit warning, now fixed. Automated regression coverage reaches 1,505 unique images, checks timestamp ties, search before paging, duplicate ratings outside the first page, collection privacy, and invalid filters.

The configured Hermes model also completed three synthetic tone checks and one supported-experience recording check. The recording check verified the resulting temporary ledger, rather than trusting the final response. See `docs/audits/2026-09-12-model-acceptance.md` for samples and limitations. These checks used disposable homes and did not modify a real companion. Installed-hook end-to-end acceptance and the wider device/host matrix remain outstanding.

A further generated-hook test succeeded: a real Hermes turn referred to a rupture stored only in its temporary ledger and continued offering Plex troubleshooting. Tools were disabled, so it requested diagnostic output and did not claim to have inspected a real server. This closes the initial generated-hook acceptance gap, but not browser-to-provider or real service-administration acceptance.

The continuity review also found that repair/correction targets stopped at the latest 30 experiences. Together now pages through the older ledger and adds loaded records to those selectors. A disposable browser check loaded 36 records, selected the oldest promise, and saved a repair, producing 37 records. API tests verify timestamp ties, complete paging, profile isolation, invalid cursors/limits, and repairing an older record. Loading history preserves an unfinished form's selected target and topic.

Final verification for this resumed pass: 708 tests passed, JavaScript regressions and syntax checks passed, and `git diff --check` passed. The source-only review ZIP contains 202 source files plus an integrity manifest. Existing dependency deprecation and SQLite resource warnings remain. No deployment was performed.


## Browser chat and administration acceptance

The owner extended the reserve to 24% remaining. The full local browser-to-provider path now has initial acceptance evidence: generated-hook approval, three saved exchanges in one conversation, refresh/resume, contextual recall, and real streaming callback output. Details and boundaries are in `docs/audits/2026-09-12-model-acceptance.md`.

The live test exposed a chat completion notification covering the Send button. Successful chat operations now keep that redundant notice hidden while Conversation is open; failures and completions on other pages remain visible. The welcome card is removed on the first send.

Gateway navigation also had a stale heading comparison that made its tab empty. Management cards now use explicit group identifiers. Jobs & health → Gateway settings opens the Gateway & routine tab and expands its controls above the dashboard. Hermes settings also has a direct Gateway & routine shortcut. Browser verification found the intended tab selected, the disclosure open, and the controls visible near the top.

Chat media lookup now resolves explicit references before gallery paging, including album-copy paths while retaining strict duplicate concealment. Text-only history avoids scanning the gallery. Regression coverage uses an older image behind 1,501 newer images and a stricter-rated duplicate; the referenced album image remains attached and concealed. The existing 10,000-file catalog scan bound still applies.

All live-provider data belonged to a temporary companion. No real companion memories, background gateway, or deployment was changed. The wider phone/device and Windows/cloud host matrix remains unverified.

Final verification for this pass: 710 tests passed, JavaScript syntax and regression checks passed, and `git diff --check` passed. The disposable provider home was removed after testing. The updated source-only archive retains 202 source files plus its integrity manifest; no deployment was performed.

## Narrow layouts and voice refresh

The owner extended the usage reserve to 15% remaining. Real 320 px browser frames exposed a clipped chat composer, a journal entry list expanding the document to roughly 23,008 px, and a longer mood displacing New chat. The fixes constrain intrinsic widths, provide a compact-height composer layout, and keep mood text inside the header. The screen-reader-only label class now has its missing CSS definition, and key navigation/voice tap targets are larger.

The journal now uses a collapsible entry picker on narrow screens, with a vertical list and automatic return to the reader after selection. Desktop retains the open list. Browser checks retained the selected entry while paging from 100 to 200 entries, and the narrow frame starts with the picker collapsed without document overflow.

Refreshing Conversation or starting a new chat now stops the prior microphone/voice state. A JavaScript regression verifies cancellation, recorder/track stopping, and playback stopping before chat controls are replaced. See `docs/audits/2026-09-12-responsive-acceptance.md` for measurements and limits. Native mobile keyboard/microphone behavior and the Windows/cloud host matrix remain unverified.

Final verification for the responsive pass: 710 tests passed, JavaScript syntax and regression checks passed, and `git diff --check` passed. Browser layout checks covered narrow chat, journal, photos, Together, and health views. No deployment was performed.
