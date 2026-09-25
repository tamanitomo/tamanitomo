# Vault editor / safe-save: first slice, results

Branch `test/vault-editor-safe-save`, local only (not pushed). It is kept out of the release
candidate: `release/chat-journal-rc` contains none of these commits.

## 1. Identities

| | SHA |
|---|---|
| Base | `c3d6bee6ec910019232001ed7363c64ba3e44b7a`: the published release-candidate head (tested code `754d9d6` + register). Branched in its own worktree. The owner's checkout, other branches and `stash@{0}` are untouched. |
| Bundle and build | `1343248` |
| Backend safe-save | `2afa642` |
| Editor UI and tests (**tested code**) | `11ce49a6a993fb63084c923a57f9edbc1e8b576a` |
| Report only | the commit adding this file, `docs/vault_editor_evidence/` and `tools/vault_packaged_smoke.py` (a development tool; not in `release-files.json`) |

Artifacts (hashes also in `docs/vault_editor_evidence/hashes.txt`):

| File | sha256 |
|---|---|
| Release ZIP built from `11ce49a` (`build/tamanitomo-vault-11ce49a.zip`, 301 files + manifest; two builds identical) | `31bd14329cfc4df56d2697736096acd63c743d6aa8dd00ceb79b5e2705ce8771` |
| `kit/app/static/vault-editor.bundle.js` (322,098 bytes) | `d218422caf7ec65565f9a004f16272122e979d1c1620d60991a5c18a38c30ab5` |
| `kit/app/static/vault-editor.LICENSES.txt` | `b41b8ebb94a209aacf81b1a04988cff13120278d8b7428ba0fd60ddc4559e15a` |
| `kit/app/static/vault-editor.js` | `282abc9fad4d5bc1a30f06edce76ae628edc9c6c5b8173533162c064f36eb95b` |
| `tools/editor/package-lock.json` | `dc251d683ad4eb7e064897a6a4e784cc3f003ceab4e636a055c800c6a4fc460c` |

## 2. What was built (and what was reused)

**Reused, not duplicated:** the existing `/api/vault` routes, path resolution, the hidden, credential
and protected classifications (`vault.resolve`, `peer.is_secret`, `vault.protected/editable`), the
sha256 revision tokens and their 409, the file lock, trash/restore, download/export, the tree, search,
new note/folder, the dedicated Identity destination (`companion-edit`) and the Vault Reading renderer.
There is no second file service and no new permission policy. There are no new routes. "Save a copy" is
the existing create-only write (`revision: ''`).

- **Bundle** (`tools/editor`): CodeMirror 6 and Lezer, pinned exactly with a lockfile and built by
  esbuild into one local IIFE. Markdown comes from `@lezer/markdown` directly, so no HTML/CSS/JS
  language packs are included. The header records the lockfile hash, and `vault-editor.LICENSES.txt`
  carries every bundled licence (`THIRD-PARTY-NOTICES.md` updated). `node build.mjs --check` fails on
  drift. A clean `npm ci` rebuild matched byte for byte. `test.yml` gains that check on one Linux job.
  No runtime CDN, and end users need no Node.
- **Backend** (`kit/app/vault.py`): backups keep the replaced **bytes** exactly (the old
  `read_text()` turned CRLF into LF), one folder per note, newest 20 kept. Autosave bursts share one
  backup, **but only when the bytes being replaced are this editor's own last write**; anything
  written by another program is always backed up before it is replaced. A linked backup folder is
  refused before anything is written.
- **Editor** (`kit/app/static/vault-editor.js`, loaded after `studios.js`):
  - Note tabs. Per-note Reading/Source/Split mode, tree expansion, selection and scroll, per
    installation and profile (localStorage, bounded to 12 tabs and 50 remembered notes).
  - One long-lived CodeMirror view. Each note keeps its own `EditorState` (undo history, selection),
    so a Chat update, leaving Vault or switching tabs never rebuilds or loses it.
  - Autosave through the revision token, with one save in flight per note; later edits are saved
    after it against the returned revision. A read that started before a save is discarded, and an
    answer never replaces newer text.
  - States: Saving, Saved, Unsaved changes, Offline (kept in this tab, retried with backoff and on
    `online`), Not saved (server refusal, with the reason and Try again), Changed outside the app
    (conflict), Recovered draft.
  - No reserialisation. CodeMirror keeps the note's own line separator (CRLF stays CRLF), and a BOM,
    frontmatter and unknown syntax are left as typed.
  - Drafts live in `sessionStorage` per installation and profile, bounded to 1.5 M characters across
    20 notes, and **disclosed** under the editor. They are cleared on save, discard, "Clear kept
    drafts", or when the tab closes (the app has no sign-out; drafts share the sign-in token's
    lifetime). The page warns before closing with unsaved text.
  - Conflict: both versions kept. Compare (line diff plus both texts), Save mine as a copy, Use the
    disk version (an undoable change), or Replace disk with mine (explicit confirmation; theirs is
    backed up). Never silent last-write-wins.
  - Protected files are read-only with no Source mode, and the dedicated editor is offered. The API
    refusal is tested directly.
  - Narrow widths: the tree folds away while a note is open (☰ toggles it), and the header controls
    wrap.
- **Fixes found on the way** (in `studios.js`): Reading-mode Markdown links became anchors for any
  target, `javascript:` included. They are now http(s)/mailto only, as the app's `richText()` allows.
  Also, a default-expanded folder showed "Empty folder" because only the root listing was read; the
  editor now reads remembered expanded folders when it mounts.

## 3. Results (this executor; synthetic fixtures only)

Python 3.14.7, Node v26.7.0, headless Chromium. `TMPDIR` was job-local, and `hermes` was off `PATH`.

| Run | Tree | Result |
|---|---|---|
| Full suite, as `test.yml`/`release.yml` run it (`TAMANITOMO_REQUIRE_NODE=1`), then `node tests/test_updates_ui.js` | `11ce49a` | **1861 passed, 52 skipped (all "pinned Hermes not configured"), 0 failed, 640 subtests**. Node OK |
| Vault browser journeys `tests/test_vault_editor_browser.py` (`TAMANITOMO_C3_REQUIRE_BROWSER=1`) | `11ce49a` | **13 passed, 0 skipped** |
| Affected suites after the review correction: Vault browser + persistent-Chat browser + `test_vault_editor_api/bundle`, `test_workspace`, `test_studios`, `test_reliability` | `11ce49a` working tree | **125 passed, 20 subtests** |
| `node build.mjs --check` after a clean `npm ci` in a separate copy | `1343248` | matches |
| **Packaged smoke** (`tools/vault_packaged_smoke.py` on the ZIP above) | `11ce49a` ZIP | **15/15**: see §4 |

The first full run (before the review correction) had one failure. The appended Vault CSS had landed
inside the slice `tests/test_us_ui.js` checks for `:hover`. The block was moved beside the existing
Vault rules; the assertion was not changed.

**Browser journeys** (all on the normal page: app built without keyed sends, legacy Chat):

1. Core journey: open a long note from the tree and type Unicode at line 60, which autosaves exactly.
   Select deep in the note, go to Chat and back, and the selection and scroll are kept. Open a second
   tab in Reading mode. Hold a save, reload, and the tabs and modes are restored, the draft is
   recovered, and the disk is untouched until "Save it". Then an external atomic replacement during a
   save gives a conflict; Compare shows both, and Save mine as a copy leaves theirs in place and mine
   as a copy.
2. Replace disk with mine: cancel first (nothing changes), then confirm. Theirs is in the backups.
3. Saves are serialised: a second save never starts while one is held, the later text is saved after,
   and the slow answer does not roll the buffer back. A slow read of note A does not displace note B,
   opened after it.
4. Offline (connection aborted): the text is kept in the tab, and saving resumes on `online`. A
   server 500: "Not saved: disk full", text kept, Try again saves.
5. Protected `soul/SOUL.md`: no Source mode, no Save, the dedicated editor offered. A direct `fetch`
   PUT returns 400 and the disk is unchanged.
6. Raw file with BOM, CRLF, frontmatter, `:::`, `%%`, a table and no final newline: a new line is
   written as CRLF, and the bytes are otherwise identical.
7. Undo/redo (Ctrl+Z / Ctrl+Shift+Z). IME composition through Chrome DevTools `Input.imeSetComposition`
   / `insertText`: only the committed text is saved.
8. Tabs, modes and drafts per profile: Rowan sees none of Nova's tabs or drafts. Nova's come back
   with the draft and per-note modes.
9. Storage bound: a note larger than the draft budget is not kept and the label says so. "Clear kept
   drafts" empties the tab's store.
10. 390 px: Save, the mode switch, the editor and the files toggle are all on screen; the tree folds
    and toggles; typing saves; no sideways scroll.
11. Reading mode: `javascript:` and relative links stay text, https becomes a link, and a wikilink
    opens a tab.
12. A read sent before a save cannot roll back the buffer or leave a stale revision.
13. With no `profile=` in the address, storage follows the profile `boot()` selects.

**Persistent-Chat coexistence (development harness, reported separately).**
`tests/test_persistent_chat_browser.py` builds the app with keyed sends through the synthetic
C1/C3 fixture. **This is not packaged persistent Chat, and not evidence for C.** It passed 12/12
with 4 subtests. That includes a reply streaming into the dock while a note in Vault keeps its
buffer, selection, focus and the same editor node. Its helpers moved from the textarea to
CodeMirror. One expectation changed: maximising the dock from Vault no longer shows a discard
prompt, because the note is autosaved and its buffer kept (the test asserts the text is on disk
first).

## 4. Packaged entry point

`tools/vault_packaged_smoke.py` extracts the ZIP and starts **the package's own**
`python -m kit.app.hosted` (as the systemd unit does) with a synthetic Hermes root, a fake echoing
Hermes and a random token. Results in `docs/vault_editor_evidence/packaged-smoke-11ce49a.json`:
- The bundle, licences and editor script are shipped, served, and match `SHA256SUMS.json`.
- No build tooling or `node_modules` ships.
- The page defines the editor.
- An edit autosaves.
- An unsaved edit whose save never arrived is recovered after a reload, and only saved on request.
- After a Chat round-trip the note keeps its selection.
- No page errors, and no request left the local server.

**The Chat on that page is the legacy implementation (`POST /api/chat`)**; there is no `KeyedChat`
and no persistent-Chat asset in the page.

## 5. Known limitations (not claimed)

- Desktop Chromium only. Composition is DevTools emulation; no phone keyboard, Firefox or Safari was
  tested.
- Syntax highlighting is not live preview. Backlinks, indexing, graph, properties, split panes,
  link-aware rename and plugins are later assignments.
- Drafts do not survive closing the tab (disclosed; the page warns). Two browser tabs editing one
  note resolve through the conflict state, not by merging.
- External changes are noticed on focus, tab switch and save. There is no file watching. A clean
  buffer takes the disk version (undoable, with a notice). The revision check detects other editors;
  it cannot make them cooperate, and an external program can still overwrite a file after the app's
  save.
- Editor backups have no browsing UI yet (the separate vault git history is unchanged). Legacy flat
  backups from earlier versions are left as they are.
- A line separator is chosen per note: in a CRLF note, a lone `\n` is kept but shown as a special
  character.
- Reading mode uses the Vault's own renderer (it escapes HTML first; its link schemes are now
  restricted), not `product.js` `richText()`, which has no wikilinks or outline anchors.
- On narrow screens the toolbar labels wrap (e.g. "[[ ]]" splits); cosmetic, seen in
  `05-narrow-source.png`, not fixed in the tested code.
- Two copies saved in the same second would collide (the second gets a 409 message).

Nothing was pushed from this branch, installed, activated, merged, tagged or published. No live
profile, vault, model, service or job was touched.
