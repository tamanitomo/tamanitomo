"""Vault editor in a real browser (headless Chromium), on the NORMAL page.

The server is the app built without keyed sends (`chat_sends=None`), so the page
is the one a release serves: legacy Chat, no persistent-Chat assets. Everything
is synthetic: a temporary Hermes root, two companions and invented notes. Slow,
failed and offline requests are made with Playwright request interception, never
by touching a live service.

Coverage is desktop Chromium. Composition is exercised through the Chrome DevTools
IME protocol, which is emulation: it says nothing about a phone keyboard.

    TAMANITOMO_C3_REQUIRE_BROWSER=1 python -m pytest tests/test_vault_editor_browser.py
    TAMANITOMO_VAULT_SHOTS=<dir>  also writes screenshots
"""
import hashlib
import json
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from tests.test_phase1b_c3_browser import Browser, until, pause   # noqa: E402

SHOTS = os.environ.get('TAMANITOMO_VAULT_SHOTS')
LONG = 'notes/Long note.md'
LONG_TEXT = '# Long note\n\n' + ''.join(f'## Part {i}\n\nLine {i} with [[Other]] and **bold** text.\n\n'
                                         for i in range(1, 121))
OTHER = 'notes/Other.md'
RAW = 'notes/Raw.md'
RAW_TEXT = ('﻿---\r\ntitle: Ünïcødé ✨\r\n---\r\n# Raw\r\n\r\n::: custom {#x}\r\n%%hidden%%\r\n'
            '| a | b |\r\n|---|---|\r\nend')


class VaultEditor(Browser):
    keyed = False
    client = False

    def setUp(self):
        super().setUp()
        self.vault = self.s.companions['nova'].vault
        (self.vault / 'notes').mkdir(exist_ok=True)
        (self.vault / LONG).write_text(LONG_TEXT, encoding='utf-8')
        (self.vault / OTHER).write_text('# Other\n\nThe other note.\n', encoding='utf-8')
        (self.vault / RAW).write_bytes(RAW_TEXT.encode('utf-8'))
        (self.vault / 'soul').mkdir(exist_ok=True)
        (self.vault / 'soul/SOUL.md').write_text('# Soul\n\nWho Nova is.\n', encoding='utf-8')
        self.held = []
        # Drafts survive a reload; the page asks before closing. Tests reload deliberately.
        self.page.on('dialog', lambda d: d.accept())

    # ----- helpers -----

    def shot(self, name):
        if SHOTS:
            pathlib.Path(SHOTS).mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(pathlib.Path(SHOTS) / f'{name}.png'))

    def go(self, tab):
        self.page.evaluate(f"()=>showTab('{tab}')")
        until(lambda: self.page.evaluate(f"current==='{tab}'"), what=f'tab {tab}')

    def vault_page(self, profile='nova'):
        self.page.goto(self.s.url(profile, 'vault'))
        self.page.wait_for_selector('#vault-tree .vault-node', state='attached')

    def status(self, path=None):
        return self.page.evaluate('p=>VaultEditor.status(p)', path)

    def wait_status(self, *states, path=None, timeout=20):
        return until(lambda: self.status(path) in states, timeout=timeout, what=f'status {states} (now {self.status(path)})')

    def open(self, path, mode='edit'):
        self.page.evaluate('p=>{readNote(p)}', path)
        self.wait_status('saved', 'readonly', 'draft', 'conflict', 'offline', path=path)
        if mode and self.page.locator(f'[data-vault-mode="{mode}"]').count():
            self.page.click(f'[data-vault-mode="{mode}"]')

    def text(self, path=None):
        return self.page.evaluate('p=>VaultEditor.text(p)', path)

    def selection(self):
        return self.page.evaluate("()=>{const v=VaultEditor.view(),s=v.state.selection.main;"
                                  "return {anchor:s.anchor,head:s.head,focus:v.hasFocus}}")

    def select(self, anchor, head):
        self.page.evaluate('([a,h])=>{const v=VaultEditor.view();v.focus();'
                           'v.dispatch({selection:{anchor:a,head:h},scrollIntoView:true})}', [anchor, head])

    def disk(self, path):
        return (self.vault / path).read_bytes().decode('utf-8')

    def label(self):
        return self.page.inner_text('#vault-save-status')

    def hold(self, method, path_part='/api/vault/file'):
        """Hold matching requests (in self.held) while self.holding is set. The route stays
        installed afterwards and passes everything through: unroute() would settle the held
        requests itself, which is not what a slow network does."""
        self.holding = True
        def handler(route):
            if self.holding and route.request.method == method and path_part in route.request.url:
                self.held.append(route)
            else:
                route.continue_()
        self.page.route('**/api/vault/file**', handler)

    def release_all(self):
        self.holding = False
        while self.held:
            self.held.pop(0).continue_()

    def lose_held(self):
        """The held saves never reach the server (a connection that drops mid-request)."""
        self.holding = False
        while self.held:
            self.held.pop(0).abort('connectionreset')

    # ----- journeys -----

    def test_1_core_journey_edit_navigate_reload_recover_and_resolve_a_conflict(self):
        self.page.set_viewport_size({'width': 1280, 'height': 800})
        self.vault_page()
        self.page.wait_for_selector(f'[data-vault-file="{LONG}"]')     # 'notes' is expanded by default
        self.page.click(f'[data-vault-file="{LONG}"]')                  # the tree opens a tab
        self.wait_status('saved', path=LONG)
        self.page.click('[data-vault-mode="edit"]')
        at = LONG_TEXT.index('Line 60 with')
        self.select(at, at)
        self.page.keyboard.type('Édité ✨ 世界 ')
        self.wait_status('saved')
        self.assertIn('Line 60 with', self.disk(LONG))
        self.assertIn('Édité ✨ 世界 Line 60 with', self.disk(LONG), 'autosaved exactly')
        self.shot('01-desktop-source')

        # a selection deep in a long note survives leaving Vault and coming back
        at = self.text().index('Line 90 with')
        self.select(at, at + 7)
        pause(0.3)                                                    # CodeMirror scrolls after measuring
        scroll = self.page.evaluate('VaultEditor.view().scrollDOM.scrollTop')
        self.assertGreater(scroll, 500)
        self.go('chat')
        self.go('vault')
        until(lambda: self.page.locator('.vault-cm').count() == 1, what='editor back')
        until(lambda: self.selection()['anchor'] == at and self.selection()['head'] == at + 7, what='selection kept')
        until(lambda: abs(self.page.evaluate('VaultEditor.view().scrollDOM.scrollTop') - scroll) < 40, what='scroll kept')

        # a second tab, in Reading mode; the first keeps Source
        self.page.evaluate('p=>{readNote(p)}', OTHER)
        self.wait_status('saved', path=OTHER)
        self.page.click('[data-vault-mode="preview"]')
        self.assertEqual(self.page.locator('.vault-tab').count(), 2)

        # unsaved text across a reload: hold the save so the edit is still unsaved
        self.page.click(f'.vault-tab [data-tab-path="{LONG}"]')
        self.wait_status('saved', path=LONG)
        self.hold('PUT')
        self.select(0, 0)
        self.page.keyboard.type('Unsaved before reload. ')
        until(lambda: self.held, what='the save to be sent')
        self.assertEqual(self.status(), 'saving')
        pause(0.4)                                                    # the draft is written within 300 ms
        self.lose_held()
        self.page.reload()
        self.page.wait_for_selector('#vault-tree .vault-node', state='attached')
        until(lambda: self.page.locator('.vault-tab').count() == 2, what='tabs restored')
        self.wait_status('draft', path=LONG)
        self.assertTrue(self.text(LONG).startswith('Unsaved before reload. '))
        self.assertFalse(self.disk(LONG).startswith('Unsaved'), 'nothing was saved behind the owner')
        self.assertIn('recovered', self.page.inner_text('#vault-conflict').lower())
        self.assertEqual(self.page.get_attribute('[data-vault-mode="edit"]', 'aria-pressed'), 'true', 'mode kept')
        self.shot('02-recovered-draft')
        self.page.click('#vault-retry')                               # "Save it"
        self.wait_status('saved')
        self.assertTrue(self.disk(LONG).startswith('Unsaved before reload. '))

        # an external editor replaces the file while there are unsaved edits
        self.hold('PUT')
        self.select(0, 0)
        self.page.keyboard.type('Mine. ')
        until(lambda: self.held, what='save in flight')
        external = self.disk(LONG).replace('# Long note', '# Long note (edited elsewhere)')
        tmp = self.vault / 'notes/.swap'
        tmp.write_text(external, encoding='utf-8')
        os.replace(tmp, self.vault / LONG)                            # atomic replacement, as editors do
        self.release_all()
        self.wait_status('conflict')
        mine = self.text()
        self.assertTrue(mine.startswith('Mine. '))
        self.assertEqual(self.disk(LONG), external, 'the external version was not overwritten')
        self.page.click('#vault-compare')
        self.page.wait_for_selector('.vault-diff')
        self.assertIn('edited elsewhere', self.page.inner_text('.vault-compare'))
        self.assertIn('Mine. ', self.page.inner_text('.vault-compare'))
        self.shot('03-compare')
        self.page.click('#close-dialog')
        self.page.click('#vault-save-copy')
        self.wait_status('saved', path=LONG)
        copies = sorted((self.vault / 'notes').glob('Long note (my copy *).md'))
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].read_text(encoding='utf-8'), mine, 'my version kept as a copy')
        self.assertEqual(self.disk(LONG), external, 'and theirs kept in place')
        self.assertEqual(self.text(LONG), external)
        self.assertEqual(self.page.evaluate('VaultEditor.active()'), copies[0].relative_to(self.vault).as_posix())
        self.assertEqual(self.errors, [])

    def test_2_replace_disk_with_mine_is_explicit_and_backs_up_theirs(self):
        self.vault_page()
        self.open(OTHER)
        self.hold('PUT')
        self.select(0, 0)
        self.page.keyboard.type('Mine. ')
        until(lambda: self.held, what='save in flight')
        (self.vault / OTHER).write_text('Theirs.\n', encoding='utf-8')
        self.release_all()
        self.wait_status('conflict')
        self.page.click('#vault-keep-mine')
        self.page.click('dialog[aria-label="Replace the disk version"] [data-no]')    # cancel first
        self.assertEqual(self.status(), 'conflict')
        self.page.click('#vault-keep-mine')
        self.page.click('dialog[aria-label="Replace the disk version"] [data-yes]')
        self.wait_status('saved')
        self.assertTrue(self.disk(OTHER).startswith('Mine. '))
        backups = [p.read_bytes() for p in (self.vault / '.companion-editor-backups').rglob('*.bak')]
        self.assertIn(b'Theirs.\n', backups)

    def test_3_saves_are_serialised_and_a_slow_answer_never_overwrites_newer_text(self):
        self.vault_page()
        self.open(OTHER)
        puts = []
        self.page.on('request', lambda r: puts.append(r.post_data) if r.method == 'PUT' and '/api/vault/file' in r.url else None)
        self.hold('PUT')
        self.select(0, 0)
        self.page.keyboard.type('first ')
        until(lambda: len(self.held) == 1, what='first save held')
        self.page.keyboard.type('second ')
        pause(2.0)                                                    # past the autosave delay
        self.assertEqual(len(self.held), 1, 'no second save while one is in flight')
        self.release_all()
        self.wait_status('saved', timeout=20)
        self.assertTrue(self.disk(OTHER).startswith('first second '), 'the later text was saved after')
        self.assertTrue(self.text().startswith('first second '), 'the slow answer did not roll the buffer back')
        self.assertEqual(json.loads(puts[0])['text'][:6], 'first ')

        # a slow read of one note does not replace the note opened after it
        self.hold('GET')
        self.page.evaluate('p=>{readNote(p)}', LONG)
        until(lambda: self.held, what='read held')
        slow = self.held.pop()
        self.holding = False
        self.page.evaluate('p=>{readNote(p)}', RAW)
        self.wait_status('saved', path=RAW)
        slow.continue_()
        self.wait_status('saved', path=LONG)
        self.assertEqual(self.page.evaluate('VaultEditor.active()'), RAW, 'the later choice stays active')
        self.assertEqual(self.text(), RAW_TEXT)

    def test_4_offline_and_failed_saves_keep_the_text_and_recover(self):
        self.vault_page()
        self.open(OTHER)
        self.page.route('**/api/vault/file**', lambda r: r.abort('internetdisconnected') if r.request.method == 'PUT' else r.continue_())
        self.select(0, 0)
        self.page.keyboard.type('Offline words. ')
        self.wait_status('offline')
        self.assertIn('Offline', self.label())
        self.assertIn(OTHER, self.page.evaluate('VaultEditor.drafts()'), 'kept in this tab')
        self.shot('04-offline')
        self.page.unroute('**/api/vault/file**')
        self.page.evaluate("()=>window.dispatchEvent(new Event('online'))")
        self.wait_status('saved')
        self.assertTrue(self.disk(OTHER).startswith('Offline words. '))
        self.assertNotIn(OTHER, self.page.evaluate('VaultEditor.drafts()'), 'draft dropped once saved')

        self.page.route('**/api/vault/file**', lambda r: r.fulfill(status=500, body='{"detail":"disk full"}',
                        content_type='application/json') if r.request.method == 'PUT' else r.continue_())
        self.page.keyboard.type('Refused words. ')
        self.wait_status('failed')
        self.assertIn('disk full', self.label())
        self.assertIn('Refused words. ', self.text())
        self.page.unroute('**/api/vault/file**')
        self.page.click('#vault-retry')
        self.wait_status('saved')
        self.assertIn('Refused words. ', self.disk(OTHER))

    def test_5_protected_file_is_read_only_and_the_api_refuses_it(self):
        self.vault_page()
        self.open('soul/SOUL.md', mode=None)
        self.wait_status('readonly')
        self.assertEqual(self.page.locator('[data-vault-mode="edit"]').count(), 0, 'no Source mode')
        self.assertEqual(self.page.locator('#save-note').count(), 0)
        self.assertIn('Protected companion record', self.page.inner_text('#vault-document'))
        self.assertEqual(self.page.locator('#vault-edit-companion-btn').count(), 1, 'its dedicated editor is offered')
        status = self.page.evaluate("""async()=>{const r=await fetch(scoped('/api/vault/file'),{method:'PUT',
            headers:{'content-type':'application/json','x-tamanitomo-token':token},
            body:JSON.stringify({path:'soul/SOUL.md',text:'changed',revision:''})});return r.status}""")
        self.assertEqual(status, 400)
        self.assertEqual(self.disk('soul/SOUL.md'), '# Soul\n\nWho Nova is.\n')

    def test_6_raw_markdown_crlf_bom_and_unknown_syntax_are_not_rewritten(self):
        self.vault_page()
        self.open(RAW)
        self.assertEqual(self.text(), RAW_TEXT)
        end = self.page.evaluate('VaultEditor.view().state.doc.length')   # CRLF counts as one position
        self.select(end, end)
        self.page.keyboard.press('Enter')
        self.page.keyboard.type('added')
        self.wait_status('saved')
        self.assertEqual((self.vault / RAW).read_bytes(), (RAW_TEXT + '\r\nadded').encode('utf-8'),
                         'the new line uses CRLF like the rest; BOM, frontmatter and syntax untouched')

    def test_7_undo_redo_and_composition(self):
        self.vault_page()
        self.open(OTHER)
        self.select(0, 0)
        self.page.keyboard.type('abc')
        self.page.keyboard.press('Control+z')
        self.assertFalse(self.text().startswith('abc'))
        self.page.keyboard.press('Control+Shift+z')
        self.assertTrue(self.text().startswith('abc'))
        cdp = self.page.context.new_cdp_session(self.page)
        cdp.send('Input.imeSetComposition', {'text': 'にほ', 'selectionStart': 2, 'selectionEnd': 2})
        cdp.send('Input.imeSetComposition', {'text': 'にほん', 'selectionStart': 3, 'selectionEnd': 3})
        cdp.send('Input.insertText', {'text': '日本'})
        until(lambda: self.text().startswith('abc日本'), what='composed text committed')
        self.wait_status('saved')
        self.assertTrue(self.disk(OTHER).startswith('abc日本'))
        self.assertNotIn('にほ', self.disk(OTHER), 'no intermediate composition text was saved')

    def test_8_tabs_modes_and_drafts_are_per_profile(self):
        self.vault_page()
        self.open(OTHER, mode='preview')
        self.open(LONG, mode='split')
        self.hold('PUT')
        self.select(0, 0)
        self.page.keyboard.type('nova draft ')
        until(lambda: self.held, what='save held')
        pause(0.4)
        self.lose_held()
        (self.s.companions['rowan'].vault).mkdir(exist_ok=True)
        self.vault_page('rowan')
        self.assertEqual(self.page.locator('.vault-tab').count(), 0, "Rowan sees none of Nova's tabs")
        self.assertEqual(self.page.evaluate('VaultEditor.drafts()'), [], "nor Nova's drafts")
        self.vault_page('nova')
        until(lambda: self.page.locator('.vault-tab').count() == 2, what='nova tabs back')
        self.wait_status('draft', path=LONG)
        self.assertEqual(self.page.get_attribute('#vault-views', 'data-mode'), 'split')
        self.page.click(f'.vault-tab [data-tab-path="{OTHER}"]')
        self.assertEqual(self.page.get_attribute('#vault-views', 'data-mode'), 'preview', 'mode per note')

    def test_9_draft_storage_is_bounded_and_says_so(self):
        big = 'notes/Big.md'
        limit = None
        self.vault_page()
        limit = self.page.evaluate('VaultEditor.limits.DRAFT_BUDGET')
        (self.vault / big).write_text('# Big\n' + 'x' * (limit + 10), encoding='utf-8')
        self.open(big)
        self.hold('PUT')
        self.select(0, 0)
        self.page.keyboard.type('y')
        until(lambda: self.held, what='save held')
        pause(0.4)
        self.assertIn('too large to keep as a draft', self.label())
        self.assertNotIn(big, self.page.evaluate('VaultEditor.drafts()'))
        self.release_all()
        self.wait_status('saved', timeout=30)
        # the clear control empties what this tab kept
        self.page.click('#vault-clear-drafts')
        self.assertEqual(self.page.evaluate('VaultEditor.drafts()'), [])

    def test_10_narrow_layout_keeps_the_editing_controls_reachable(self):
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.vault_page()
        self.open(LONG)
        for sel in ('#save-note', '[data-vault-mode="preview"]', '.vault-cm .cm-content', '#vault-files-toggle'):
            box = self.page.locator(sel).first.bounding_box()
            self.assertIsNotNone(box, sel)
            self.assertLessEqual(box['x'] + min(box['width'], 40), 390, sel)
        self.assertFalse(self.page.locator('#vault-tree').is_visible(), 'the tree folds away while editing')
        self.shot('05-narrow-source')
        self.page.click('#vault-files-toggle')
        self.assertTrue(self.page.locator('#vault-tree').is_visible())
        self.shot('06-narrow-files')
        self.page.click('#vault-files-toggle')
        self.page.click('.vault-cm .cm-content')
        self.page.keyboard.type('phone ')
        self.wait_status('saved')
        self.assertIn('phone ', self.disk(LONG))
        self.assertEqual(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), True, 'no sideways scroll')

    def test_11_reading_mode_links_are_safe_and_wikilinks_open_tabs(self):
        (self.vault / 'notes/Links.md').write_text(
            '# Links\n\n[[Other]] [bad](javascript:alert(1)) [ok](https://example.org) [rel](../x)\n', encoding='utf-8')
        self.vault_page()
        self.open('notes/Links.md', mode='preview')
        anchors = self.page.eval_on_selector_all('#vault-preview a', 'a=>a.map(x=>x.getAttribute("href"))')
        self.assertEqual(anchors, ['https://example.org'])
        self.page.click('#vault-preview .wiki-link')
        until(lambda: self.page.evaluate('VaultEditor.active()') == OTHER, what='wikilink opened')
        self.shot('07-reading')

    def test_12_a_read_sent_before_a_save_cannot_roll_the_buffer_back(self):
        self.vault_page()
        self.open(OTHER)
        self.hold('GET')
        self.page.evaluate("()=>window.dispatchEvent(new Event('focus'))")    # revalidation read, held
        until(lambda: self.held, what='revalidation held')
        self.holding = False
        self.select(0, 0)
        self.page.keyboard.type('newer ')
        self.wait_status('saved')                                             # the save went through
        self.release_all()                                                    # the old read answers late
        pause(1.0)
        self.assertTrue(self.text().startswith('newer '), 'buffer kept')
        self.assertEqual(self.status(), 'saved')
        self.assertTrue(self.disk(OTHER).startswith('newer '))
        self.page.keyboard.type('again ')
        self.wait_status('saved')                                             # no stale revision, no conflict
        self.assertTrue(self.disk(OTHER).startswith('newer again '))

    def test_13_storage_follows_the_profile_boot_selects(self):
        rowan = self.s.companions['rowan'].vault
        (rowan / 'notes').mkdir(parents=True, exist_ok=True)
        (rowan / 'notes/R.md').write_text('# Rowan\n', encoding='utf-8')
        self.page.goto(self.s.base + '/')
        self.page.evaluate("()=>localStorage.setItem('last-profile-existing','rowan')")
        from tests.phase1b_c3.fixture import TOKEN
        self.page.goto(f'{self.s.base}/?installation=existing&token={TOKEN}#vault')   # no profile= in the address
        self.page.wait_for_selector('#vault-tree .vault-node', state='attached')
        self.assertEqual(self.page.evaluate('PROFILE'), 'rowan')
        self.page.evaluate("p=>{readNote(p)}", 'notes/R.md')
        self.wait_status('saved', path='notes/R.md')
        keys = self.page.evaluate('Object.keys(localStorage).filter(k=>k.startsWith("vault-ui"))')
        self.assertEqual(keys, ['vault-ui:existing|rowan'])

    # ----- V1/V2/V3 review corrections -----

    def kept(self, path):
        """The text this tab keeps for a note (sessionStorage), or None."""
        return self.page.evaluate("""p=>{for(const k of Object.keys(sessionStorage))if(k.startsWith('vault-drafts:')){
            const d=JSON.parse(sessionStorage.getItem(k))[p];if(d)return d.text;}return null}""", path)

    def record_puts(self):
        """Pass every request through, recording the text of each PUT that reaches the server."""
        bodies = []
        def handler(route):
            if route.request.method == 'PUT':
                bodies.append(json.loads(route.request.post_data)['text'])
            route.continue_()
        self.page.route('**/api/vault/file**', handler)
        return bodies

    def test_14_a_draft_recovered_while_the_disk_is_unreadable_stays_unsaved(self):
        self.vault_page()
        self.open(OTHER)
        self.hold('PUT')
        self.select(0, 0)
        self.page.keyboard.type('Kept draft. ')
        until(lambda: self.held, what='save held')
        pause(0.4)
        self.lose_held()
        # Reload with the note unreadable: the kept draft is restored with no disk snapshot.
        self.page.route('**/api/vault/file**', lambda r: r.abort('internetdisconnected'))
        self.page.reload()
        self.page.wait_for_selector('#vault-tree .vault-node', state='attached')
        self.wait_status('offline', path=OTHER)
        self.assertEqual(self.text(OTHER), 'Kept draft. # Other\n\nThe other note.\n')
        self.select(0, 0)
        self.page.keyboard.type('More. ')
        mine = 'More. Kept draft. # Other\n\nThe other note.\n'
        until(lambda: self.kept(OTHER) == mine, what='the newer text kept, not dropped')
        self.assertEqual(self.text(), mine)
        self.assertIn(self.status(), ('offline', 'dirty'))
        # Another editor changes the note; the connection returns and the note is revalidated.
        (self.vault / OTHER).write_text('External text.\n', encoding='utf-8')
        self.page.unroute('**/api/vault/file**')
        self.page.evaluate("()=>window.dispatchEvent(new Event('focus'))")
        self.wait_status('conflict')
        self.assertEqual(self.text(), mine, 'the recovered buffer was not replaced as if clean')
        self.assertEqual(self.kept(OTHER), mine)
        self.page.click('#vault-compare')
        self.page.wait_for_selector('.vault-diff')
        both = self.page.inner_text('.vault-compare')
        self.assertIn('External text.', both)
        self.assertIn('More. Kept draft.', both)
        self.page.click('#close-dialog')
        pause(5.0)                                                    # past any queued offline retry
        self.assertEqual(self.disk(OTHER), 'External text.\n', 'nothing saved over the other version')
        self.assertEqual(self.status(), 'conflict')

    def test_15_a_late_copy_receipt_keeps_newer_typing_and_the_newer_note(self):
        self.vault_page()
        self.open(OTHER)
        self.hold('PUT')
        self.select(0, 0)
        self.page.keyboard.type('Mine. ')
        until(lambda: self.held, what='save in flight')
        (self.vault / OTHER).write_text('Theirs.\n', encoding='utf-8')
        self.release_all()
        self.wait_status('conflict')

        # Typing while the copy request is held: the receipt covers only the submitted text.
        self.hold('PUT')
        self.page.click('#vault-save-copy')
        until(lambda: self.held, what='copy request held')
        submitted = json.loads(self.held[0].request.post_data)['text']
        self.assertTrue(submitted.startswith('Mine. '))
        self.select(0, 0)
        self.page.keyboard.type('Newer. ')
        newer = 'Newer. ' + submitted
        until(lambda: self.kept(OTHER) == newer, what='newer typing kept')
        self.release_all()
        until(lambda: len(list((self.vault / 'notes').glob('Other (my copy *).md'))) == 1, what='copy written')
        pause(0.5)
        first = next((self.vault / 'notes').glob('Other (my copy *).md'))
        self.assertEqual(first.read_text(encoding='utf-8'), submitted, 'the copy holds what was submitted')
        self.assertEqual(self.page.evaluate('VaultEditor.active()'), OTHER, 'still on the original')
        self.assertEqual(self.text(OTHER), newer, 'newer typing not cleared')
        self.assertEqual(self.status(OTHER), 'conflict')
        self.assertEqual(self.kept(OTHER), newer, 'and still kept in this tab')
        self.assertEqual(self.disk(OTHER), 'Theirs.\n')

        # Choosing another note while the copy request is held: the receipt does not navigate.
        pause(1.1)                                                    # copy names are stamped to the second
        self.hold('PUT')
        self.page.click('#vault-save-copy')
        until(lambda: self.held, what='second copy held')
        self.page.evaluate('p=>{readNote(p)}', LONG)
        self.wait_status('saved', path=LONG)
        self.release_all()
        until(lambda: len(list((self.vault / 'notes').glob('Other (my copy *).md'))) == 2, what='second copy written')
        pause(0.5)
        self.assertEqual(self.page.evaluate('VaultEditor.active()'), LONG, 'the newer choice stays active')
        second = [p for p in (self.vault / 'notes').glob('Other (my copy *).md') if p != first][0]
        self.assertEqual(second.read_text(encoding='utf-8'), newer)
        self.assertEqual(self.text(OTHER), 'Theirs.\n', 'unchanged original shows the disk version')
        self.assertEqual(self.status(OTHER), 'saved')
        self.assertEqual(self.errors, [])

    def test_16_a_discarded_note_sends_no_later_save(self):
        self.vault_page()
        self.open(OTHER)
        # A queued offline retry
        self.page.route('**/api/vault/file**', lambda r: r.abort('internetdisconnected') if r.request.method == 'PUT' else r.continue_())
        self.select(0, 0)
        self.page.keyboard.type('Discarded words. ')
        self.wait_status('offline')
        self.page.click(f'.vault-tab-close[data-close-path="{OTHER}"]')
        self.page.click('dialog[aria-label="Unsaved changes"] [data-discard]')
        until(lambda: self.status(OTHER) is None, what='note closed')
        self.page.unroute('**/api/vault/file**')
        puts = self.record_puts()
        self.page.evaluate("()=>window.dispatchEvent(new Event('online'))")
        pause(6.0)                                                    # past the 4 s retry
        self.assertEqual(puts, [], 'no retry for the discarded note')
        self.assertEqual(self.disk(OTHER), '# Other\n\nThe other note.\n')
        self.assertIsNone(self.kept(OTHER))

        # A request in flight at close that fails afterwards
        self.page.unroute('**/api/vault/file**')
        self.open(LONG)
        self.hold('PUT')
        self.select(0, 0)
        self.page.keyboard.type('Late failure. ')
        until(lambda: self.held, what='save held')
        self.page.click(f'.vault-tab-close[data-close-path="{LONG}"]')
        self.page.click('dialog[aria-label="Unsaved changes"] [data-discard]')
        until(lambda: self.status(LONG) is None, what='note closed')
        self.lose_held()                                              # the transport fails after close
        puts = self.record_puts()
        pause(6.0)
        self.assertEqual(puts, [], 'the late failure did not restart saving')
        self.assertEqual(self.disk(LONG), LONG_TEXT)
        self.assertIsNone(self.kept(LONG))
        self.assertEqual(self.page.evaluate('VaultEditor.drafts()'), [])


    def test_17_safe_embeds_render_images_and_note_excerpts_non_recursively(self):
        import base64
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
        (self.vault / 'notes/photo.png').write_bytes(png)
        (self.vault / 'notes/Deep.md').write_text('# Deep\nIntro.\n## Likes\nCoffee and tea.\n## Dislikes\nRain.\n', encoding='utf-8')
        (self.vault / 'notes/Inner.md').write_text('# Inner\nInner text.\n', encoding='utf-8')
        (self.vault / 'notes/Middle.md').write_text('# Middle\n![[Inner]]\n', encoding='utf-8')
        (self.vault / 'notes/Embeds.md').write_text(
            '# Embeds\n\n![[photo.png]]\n\n![[Deep#Likes]]\n\n![[Middle]]\n\n![[Nowhere]]\n', encoding='utf-8')
        self.vault_page()
        self.open('notes/Embeds.md', mode='preview')
        until(lambda: self.page.locator('#vault-preview .vault-embed-image img').count() == 1, what='image embed hydrated')
        self.assertGreater(self.page.eval_on_selector('#vault-preview .vault-embed-image img', 'i=>i.naturalWidth'), 0)

        until(lambda: self.page.locator('#vault-preview .vault-embed-note').count() == 2, what='note embeds hydrated')
        labels = self.page.eval_on_selector_all('#vault-preview .vault-embed-label', 'els=>els.map(e=>e.textContent)')
        self.assertTrue(any('Deep' in l and 'Likes' in l for l in labels))
        self.assertTrue(any('Middle' in l for l in labels))
        body_text = self.page.inner_text('#vault-preview')
        self.assertIn('Coffee and tea.', body_text)
        self.assertNotIn('Rain.', body_text, 'only the requested heading section is embedded')

        # Middle embeds Inner; that inner embed must show as an inert link, never expanded (depth-1, non-recursive).
        middle_embed = self.page.locator('#vault-preview .vault-embed-note', has_text='Middle')
        self.assertEqual(middle_embed.locator('.vault-embed-note').count(), 0, 'no nested embed card')
        self.assertEqual(middle_embed.locator('.wiki-link', has_text='Inner').count(), 1, 'nested embed shown as a plain link')
        self.assertNotIn('Inner text.', body_text, "the inner note's own body was never fetched or expanded")

        until(lambda: self.page.locator('#vault-preview .vault-embed-missing').count() == 1, what='missing embed reported')
        self.assertIn('Nowhere', self.page.inner_text('#vault-preview .vault-embed-missing'))
        self.shot('08-embeds')


if __name__ == '__main__':
    unittest.main()
