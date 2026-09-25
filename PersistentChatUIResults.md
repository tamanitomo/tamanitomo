# Persistent Chat — first usable UI milestone: results

**Branch:** `test/persistent-chat-ui` (local, unmerged, unpushed). It is a child of the accepted
`test/phase1b-c3-recovery-closure`.
**Verified base:** `27c6ab4eaf0e0f41ff3c33ddd45168adbdd1f0bc`, tree `5c3c7de3…`. The worktree was clean,
and no later owner commits existed. `stash@{0}` (WIP on main) was preserved and not applied.
**Tested implementation:** `cf7b56f` (tree `b5f913b7…`). The worktree was clean before and after the
evidence runs.
**This report and `docs/persistent_chat_evidence/`:** a later report-only commit.

Keyed activation stays **OFF**. Everything below is served only by
`chat_sends=Options(client=True)`, which no shipped entry point sets. None of the new files is in
`release-files.json`. There is no version bump and no push, merge, release or deployment. No live
profile, credential, model, platform or C2 dispatcher was used. No reflection, prompt, Hermes context,
backend route or protocol changed; the only server change is which assets the opted-in page loads.

## What works

**The journey:** start a chat → go to a Vault note → the reply keeps arriving → open the dock and
draft or reply there → maximise into Chat. It is one conversation with one active send.

- **One controller, state outside the page.** `chat-store.js` keeps each installation/profile
  scope's history rows, source-identity links, send presentation (status, stream snapshot, replies),
  hints and scroll anchors. The draft stays in its existing sessionStorage key.
  - `chat-sends.js` is the accepted C3 state machine. Its send, retry, recovery and wording logic is
    unchanged; only its painting now publishes to the store.
  - Its send client is attached **once per page load**, not per Chat view. A send therefore
    continues, and after a reload resumes, whichever page is open.
- **One renderer, two views.** `chat-view.js` renders the same store into the Chat page and the
  dock.
  - Rendering is keyed and incremental. An element is created once, and only its changed children
    are replaced. A growing reply is one element from its first snapshot to its settled text; the
    snapshots replace each other and are never appended.
  - Incoming text never touches anything outside the log. It never moves focus and never scrolls a
    reader away from older messages; a **New messages** control appears instead.
  - Older pages load near the top with the reader's place kept.
  - Exactly one view (and one composer) is mounted at a time.
- **Chat page.** The shell and composer render at once. Nothing waits for history, feelings or
  portraits. The header shows the name, the avatar, the actual send state (sending, checking,
  replying, sign-in needed) or the recorded mood. The relationship percentage is gone.
- **Desktop dock.** A bottom-right launcher shows who, what is happening now, a short live preview,
  and an in-session **New reply** marker.
  - The owner opens the mini chat. It has minimise (also Esc), which returns focus to the launcher,
    and maximise.
  - It never opens itself and never takes focus when an answer arrives.
  - Maximise respects the page's unsaved-note guard. Choosing "Stay" keeps the dock as it was.
- **Mobile (≤900 px).** The same launcher becomes a pill above the tab bar. It opens a full-height
  sheet that stops at the tab bar, so navigation stays reachable, and respects the safe-area insets.
  Dialogs and viewers stay above it, and it hides while the navigation drawer is open.
- **One presentation per message.** History rows and send parts are matched only by source identity
  (session + Hermes row id), as C3 did.
  - A pending send whose row may already be in newly read history is shown as the labelled C3
    request status.
  - A settled send's own presentation is retired only by a history read that **started after** it
    settled.
  - Equal-text history is never hidden.
- **Privacy on expiry.** A 401 stops protected polling, exactly as in C3. The collapsed launcher then
  shows "Sign in again" and **no message preview**.
  - A `pin_required` 401 on the new history reads raises the app's existing PIN dialog, as `api()`
    does.
  - Page and dock content otherwise behave as the app already does (the page is not blanked).
- **Voice, media and exclusion are reused unchanged:** `mountBrowserVoice`, `richText`,
  `inlineMedia`, authorised media URLs, and the `activeOperation` exclusion for non-chat actions.

## Working preview

```sh
cd ~/projects/tamanitomo
.venv/bin/python tools/preview_fixture.py --persistent-chat --port 38500
# prints:  Persistent Chat: http://127.0.0.1:38500/?installation=existing&profile=nova&token=<random>#chat
```

- **Server and data.** It binds to 127.0.0.1 only and uses a random per-run token. All data lives in a
  temporary directory under `$TMPDIR` (printed as `Data:`) and is removed on exit. `--keep` leaves it
  behind.
  - The data: companions Nova and Rowan, a synthetic multi-channel history, and three ordinary
    editable notes (`notes/Garden plan.md` and two others).
  - Replies come from the Phase 1B protocol double (`tests/phase1b_c1/fake_hermes`). They stream in
    ~1.2 s steps and rotate between three synthetic replies.
- **Stop it** with Ctrl-C, or `kill <pid>`; SIGTERM also removes the data.
- **Owner data is never used.** The Hermes root is always the generated one; the owner's Hermes home
  and credentials are never selected.
- **Host note:** this host's `/tmp` is currently 100% full (other sessions' files). If Chromium or
  the preview fails with `ERR_INSUFFICIENT_RESOURCES` or ENOSPC, set `TMPDIR` to a directory with
  room.

## Acceptance checklist

| # | Check | Evidence (real Chromium → uvicorn → SendService → fake Hermes; ledger assertions) | Result |
|---|---|---|---|
| 1 | Core desktop journey | `test_1_send_navigate_to_vault_receive_in_dock_reply_and_maximise`. Live text reaches the collapsed launcher while a Vault note is edited: its value, selection (2–8), focus and DOM node are unchanged. The dock is opened by the owner, a newer dock draft survives the completion, the reply is sent from the dock, and maximise with "Stay" keeps the dock (the second attempt discards). Result: 2 sends, 1 launch each, 2 distinct keys, one bubble per message, one element per `send:owner` and `send:reply:0`, at most one operation poll in flight, no `POST /api/chat`. | pass |
| 2 | View lifetime and draft | `test_2_views_change_…`: page → Vault → dock → Esc → keyboard reopen → maximise → Home → Chat mid-reply. Bootstrap ran once, 1 POST, 1 launch, at most one poll in flight, and the draft followed every view and survived completion. `test_2_reload_on_another_page…`: reload on Vault mid-turn keeps the same key; the launcher follows and shows New reply; one reply, no request status left. The C3 reload/recovery tests (31) pass against the refactored controller. | pass |
| 3 | Isolation and recovery | `test_3_profile_switch_from_the_dock…`: nova's result arrives while the tab is on rowan. Nothing of nova is painted, no nova-scoped request is made, and rowan's draft is untouched; back on nova, the reply and nova's newer draft are there. `test_3_lost_response_from_the_dock…`: same-key recovery. `test_3_sign_in_expiry…`: polling stops, there is no launcher preview, and Check now completes with the same key. Plus the C3 lost-response, ledger-loss, same-key, sign-in and reset tests. | pass |
| 4 | Narrow layout | `test_4_phone_width_pill_sheet_and_keyboard` at 390×844 (midnight) and 360×740 (daylight): the pill sits above the tab bar, there is no sideways scroll, the sheet is full width and stops at the tab bar, the composer is visible, Enter/Esc work with focus return, a send from the sheet works, and a dialog sits above the chat layer. `test_4_desktop_dock_fits…` checks both themes. `test_4_older_pages_and_incoming_text…` covers paging and not moving the reader. | pass (emulated) |
| 5 | Default compatibility | The default and routes-only builds serve `index.html` byte-for-byte, with no dock, store or controller, no new file names, and the legacy `POST /api/chat` (`test_phase1b_c3_disabled.py`, `DisabledClient`, `DefaultPage`, `RoutesOnlyPage`). None of the new files is shipped. The preview test shows synthetic temporary-only data. Disabling is removing the option: no migration, same storage keys. | pass |

**Native devices:** not run. Mobile was checked in desktop Chromium emulation only. The phone
keyboard, the visual viewport and iOS safe-area behaviour are not certified.

## Commands, counts, skips

Environment for every run: Python 3.14.7, Node v26.7.0, Playwright 1.63.0, Chromium 153.0.8010.12,
`PATH=/usr/bin:/bin` (Hermes not on PATH), `TAMANITOMO_REQUIRE_NODE=1 TAMANITOMO_C3_REQUIRE_BROWSER=1`,
and `TMPDIR` set to job scratch.

| Run at cf7b56f | Result |
|---|---|
| `pytest tests/test_persistent_chat_browser.py` (new, TAMANITOMO_CHAT_SHOTS set) | **12 passed**, 4 subtests |
| `pytest` C3 browser 16 + disabled 5 + reviewer 6 + closure 4 + `test_phase1b_c3_recovery.py` (reviewer Node 8/8, closure Node 6/6, HTTP witness) + `test_preview_fixture.py` + `test_reliability.py` | **71 passed**, 33 subtests |
| Ordinary full suite `pytest tests/` (once, on this tree) | **1732 passed, 51 skipped, 0 failed**, 637 subtests |

The 51 skips are all pinned-Hermes-only:

- 24 in `test_phase1b_c0_receipts.py` ("pinned Hermes not configured", `TAMANITOMO_C0_HERMES_*`)
- 27 in `test_phase1b_c1_pinned.py` (`TAMANITOMO_C1_HERMES_*`)

The real-Hermes lane was not rerun: no backend, protocol or lane module changed.

**Test changes.** `test_phase1b_c3_disabled.py`'s enabled-page assertion expected exactly one
injected script. The assertion is replaced, not dropped: it now requires the signal, `chat.css` after
`product.css`, and the four scripts in load order, and it still requires the page to equal
`index.html` once those are removed. The "not shipped", "not in index.html" and "inert / no path to
`POST /api/chat`" checks were extended to the new files. No other existing assertion changed.

## Screenshot sequence (`docs/persistent_chat_evidence/screens/`, synthetic)

1. `01-chat-page.png`: the Chat page.
2. `02-streaming-on-page.png`: a reply streaming on the page.
3. `03-vault-with-launcher.png`: a Vault note being edited, the launcher previewing the live reply.
4. `04-dock-open-streaming.png`: the dock opened by the owner, the reply growing, a draft being typed.
5. `05-replied-from-dock.png`: a reply sent from the dock.
6. `06-maximised.png`: maximised into Chat, one transcript.
7. `07-pill-390-midnight.png` / `07-pill-360-daylight.png`: the phone pill.
8. `08-sheet-*.png`: the phone sheet.
9. `09-dock-*.png`: the desktop dock in both themes.

The daylight shots switch the theme by attribute after load, so some app chrome keeps its earlier
styling; this is a test artifact.

## Known limitations and separately tracked items (not added to this milestone)

**Found here, pre-existing, and relevant to activation (not fixed: it would change which session a
send resumes).**

- The Chat page takes `session` from the legacy `/api/feed`'s `latest_session`. That value can be a
  `cli`-labelled session that is really a gateway chat (the chat fixtures' `gw-cli`).
- Keyed sends correctly refuse such a session with `400 unauthorised_session`, which the page shows as
  **Not sent**.
- The C3 page had the same behaviour. The preview seeds a newer genuine workspace session so the
  journey is representative.
- Before activation, keyed sends should resume only a session the keyed binding authorises.

**Milestone limits (by design).**

- Transport is the existing operation polling (Phase 3.1).
- New messages arriving on other channels appear when the Chat page opens with nothing pending. They
  are not pushed to the dock.
- New reply is in-session only: no persistent unread count and no read receipts.
- The dock shows the latest 40 rows; maximise for older history.
- A settled failure status (Ask again / Send again) is retired by the next Chat-page history read,
  exactly as the C3 page lost it on a return to Chat. The C3 limitation "request status after a
  same-page return" no longer occurs, because state persists across views.
- If C1 did not link a settled send's rows, an equal-text duplicate could show until the next page
  read. Nothing is text-matched to hide it.

**Polish backlog.**

- The open desktop dock (380 px) covers the right edge of a wide editor while open.
- The operation toast can sit over the collapsed launcher.
- `.chat-hint` is hidden at ≤700 px on the page, so page hints show only in the dock's status line on
  phones (pre-existing).

**Pre-existing, outside this task.**

- The Vault tree shows "Empty folder" for a remembered expanded folder until it is re-opened.
- The legacy `/api/feed` in the synthetic preview includes the fixture's stranger/group rows, which
  the Phase 1A snapshot excludes.

**Still tracked, unchanged:** Phase 1C shared context, containment, compression identity, the
tag vocabulary, the abandon-request flow, SSE/Web Push, Journal, the Vault redesign and native
platforms.

This UI does not establish cross-channel model awareness; it only displays one conversation.

## Evidence

`docs/persistent_chat_evidence/runs/` was exported by `tools/evidence_export.py --kind executed`: 9
files, re-parsed and validated, with home and job paths redacted, plus `MANIFEST.json`. The screenshots
are copied unmodified, because the exporter is text/XML/JSON only. They show synthetic data only; no
token or path is visible.
