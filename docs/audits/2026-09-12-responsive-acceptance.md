# Responsive layout acceptance

Tested the current source in a disposable local workspace using real browser frames at phone widths. The harness exposed only DOM layout measurements and page selection; it did not alter production companion data. These checks establish CSS viewport behavior, not native iOS/Android keyboard, microphone, or touch-device acceptance.

## Findings and fixes

| Check | Before | After |
| --- | --- | --- |
| Conversation at 320×380 | Send occupied y=449–491, below the 380 px viewport and clipped by the conversation card. | Composer and Send occupy y=303–347, both within the viewport. Send is 44 px tall. |
| Journal at 320 px | The horizontal entry list expanded the page to roughly 23,008 px wide. | Page width equals available client width (305 px with the browser’s vertical scrollbar). |
| Longer recorded mood at 320 px | Mood text displaced New chat beyond the header’s bounds. | Text is constrained and ellipsized; header controls remain inside the viewport. |
| Photos, Together, Jobs & health at 320 px | Checked for document overflow. | Each fits the available client width. |

The compact-height chat layout places the composer and Send alongside each other, allows remaining chat space to shrink, and retains scrolling as a fallback. The missing screen-reader-only label style is now defined. Navigation and voice controls receive larger phone tap targets.

## Journal interaction

The phone journal starts with a collapsed “Browse entries” picker, leaving the selected entry visible. Opening the picker uses a bounded vertical list rather than a long horizontal strip. Choosing an entry on a narrow screen closes the picker and brings the reader into view. Desktop retains the open entry list by default.

Browser interaction checks at 1280 px selected the October 1, 2022 fixture entry and loaded the next page, progressing from 100 to 200 of 1,006 entries while retaining the selection. The 320 px frame verified the collapsed initial picker and absence of horizontal document overflow. The fixture also contains a 120,018-character entry, which remains fully readable.

## Voice lifecycle

Refreshing Conversation now stops capture before replacing its controls. Starting a new conversation also cancels the previous voice state. A JavaScript regression uses recorder, microphone-track, and playback doubles to verify cancellation and stopping happen before the refreshed chat handler replaces controls. Existing failure/recovery tests continue to pass. No physical microphone was used in this pass.

## Remaining acceptance

Test real mobile keyboards, safe-area insets, screen readers, microphone permission transitions, and touch interactions on iOS and Android. Windows/cloud installation and actual service-administration flows remain separate acceptance areas. The app is not claimed to have passed a full device or host matrix.
