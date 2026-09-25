"""Persistent Chat (first usable UI milestone): the five acceptance journeys in a real browser.

BOUNDARY: headless Chromium (Playwright) -> the actual page (index.html + workspace.js + the
keyed client and the persistent Chat store/view/controller) -> a real uvicorn server built
with chat_sends=Options(client=True) (tests/phase1b_c3/fixture.py) -> SendService -> the
fake Hermes protocol double -> a synthetic state.db. Launches and idempotency are asserted
on the ledger the server wrote. Synthetic data only: no model, platform, credential, live
profile or live dispatcher.

TAMANITOMO_C3_REQUIRE_BROWSER=1 makes a missing browser a failure, never a skip.
TAMANITOMO_CHAT_SHOTS=<dir> also saves the screenshot sequence of the main journey.
"""
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from tests.phase1b_c1.harness import LINUX                                   # noqa: E402
from tests.test_phase1b_c3_browser import Browser, WORDS, pause, until        # noqa: E402

SHOTS = os.environ.get('TAMANITOMO_CHAT_SHOTS')
NOTE = 'notes/Garden plan.md'
NOTE_TEXT = '# Garden plan\n\nTomatoes along the south fence.\nBasil in the blue pots.\n'


class Persistent(Browser):

    def setUp(self):
        super().setUp()
        vault = self.s.companions['nova'].vault
        (vault / 'notes').mkdir(exist_ok=True)
        (vault / NOTE).write_text(NOTE_TEXT, encoding='utf-8')
        self.in_flight, self.max_in_flight = 0, 0
        self.page.on('request', self._started)
        self.page.on('requestfinished', self._ended)
        self.page.on('requestfailed', self._ended)

    # operation polls in flight at once: one controller follows a send, whatever is open
    def _started(self, r):
        if '/api/operations/' in r.url:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)

    def _ended(self, r):
        if '/api/operations/' in r.url:
            self.in_flight -= 1

    def shot(self, name):
        if SHOTS:
            pathlib.Path(SHOTS).mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(pathlib.Path(SHOTS) / f'{name}.png'))

    # ----- helpers -----

    def go(self, tab):
        self.page.evaluate(f"()=>showTab('{tab}')")
        until(lambda: self.page.evaluate(f"current==='{tab}'"), what=f'tab {tab}')

    def open_note(self):
        if self.page.url == 'about:blank':
            self.page.goto(self.s.url('nova', 'vault'))
        self.go('vault')
        self.page.wait_for_selector('#vault-tree .vault-node', state='attached')   # the Vault page has drawn
        self.page.evaluate("()=>typeof showVaultView==='function'&&showVaultView('folders')")
        self.page.evaluate(f"()=>readNote({NOTE!r})")
        self.page.click('[data-vault-mode="edit"]')            # notes open in preview; edit as a person would
        self.page.wait_for_selector('#note-text')
        until(lambda: self.page.input_value('#note-text') == NOTE_TEXT, what='note loaded')

    def launcher(self):
        return self.page.inner_text('#chat-dock-launcher')

    def new_reply(self):
        return self.page.evaluate("()=>!document.querySelector('#chat-dock .chat-dock-dot').hidden")

    def dock_visible(self):
        return self.page.evaluate("()=>{const d=document.getElementById('chat-dock');return !!d&&!d.hidden}")

    def dock_open(self):
        return self.page.evaluate("()=>!document.getElementById('chat-dock-panel')?.hidden")

    def dock_text(self):
        return self.page.inner_text('#chat-dock-log')

    def dock_bubbles(self, text, owner=True):
        sel = '#chat-dock-log .bubble.user' if owner else '#chat-dock-log .bubble:not(.user):not(.typing)'
        return self.page.evaluate('([sel,text])=>[...document.querySelectorAll(sel)].filter(b=>'
                                  "(b.querySelector('.message-body')?.innerText||'').trim()===text).length",
                                  [sel, text])

    def active(self):
        return self.page.evaluate('document.activeElement?.id||document.activeElement?.tagName')

    def note_state(self):
        return self.page.evaluate("()=>{const t=document.getElementById('note-text');"
                                  "return {value:t.value,start:t.selectionStart,end:t.selectionEnd,"
                                  "marker:t.dataset.marker||null,focus:document.activeElement===t}}")


@unittest.skipUnless(LINUX, 'the C1 supervision is established on Linux only')
class Journeys(Persistent):

    # 1. core desktop journey ------------------------------------------------------------

    def test_1_send_navigate_to_vault_receive_in_dock_reply_and_maximise(self):
        self.page.set_viewport_size({'width': 1280, 'height': 800})
        self.s.gated(['The tomatoes ', 'are nearly ', 'ripe.'])
        self.open()
        self.shot('01-chat-page')
        self.type_and_send('How is the garden?')
        until(lambda: self.s.reached(1), what='reply paused after its first part')
        until(lambda: 'The tomatoes' in self.page.inner_text('#chat-log'), what='first part on the page')
        self.shot('02-streaming-on-page')

        # Vault: a note being edited, with a selection and the focus in it.
        self.open_note()
        self.page.fill('#note-text', NOTE_TEXT + 'Owner edit in progress.\n')
        self.page.evaluate("()=>{const t=document.getElementById('note-text');t.dataset.marker='same-node';"
                           "t.focus();t.setSelectionRange(2,8);}")
        before = self.note_state()
        until(self.dock_visible, what='the dock launcher on Vault')
        self.assertFalse(self.dock_open(), 'the dock is not opened for the owner')
        until(lambda: 'The tomatoes' in self.launcher(), what='live text in the collapsed launcher')
        self.shot('03-vault-with-launcher')

        self.s.release(1)
        until(lambda: 'are nearly' in self.launcher(), what='the next part in the launcher')
        self.assertEqual(self.note_state(), before, 'note buffer, selection, focus and node survive incoming text')
        self.assertFalse(self.dock_open(), 'an arriving answer never opens the dock')

        # The owner opens the dock and drafts while the reply is still arriving.
        self.page.click('#chat-dock-launcher')
        until(self.dock_open, what='dock open')
        self.assertEqual(self.active(), 'chat-dock-message', 'opening the dock focuses its composer')
        until(lambda: 'The tomatoes are nearly' in self.dock_text(), what='the stream in the dock')
        self.page.fill('#chat-dock-message', 'A newer draft in the dock')
        self.shot('04-dock-open-streaming')
        self.s.release(2)
        until(lambda: self.dock_bubbles('The tomatoes are nearly ripe.', owner=False) == 1, what='settled reply in dock')
        until(lambda: self.pending() is None, what='first send settled')
        self.assertEqual(self.page.input_value('#chat-dock-message'), 'A newer draft in the dock',
                         'completion does not clear the newer draft')
        self.assertEqual(self.storage('chat-draft-existing-nova'), 'A newer draft in the dock')
        self.assertEqual(self.page.input_value('#note-text'), NOTE_TEXT + 'Owner edit in progress.\n')

        # Reply from the dock.
        self.s.scenario(reply='Then we pick them on Saturday.')
        self.page.press('#chat-dock-message', 'Enter')
        until(lambda: self.dock_bubbles('Then we pick them on Saturday.', owner=False) == 1, what='second reply in dock')
        self.assertEqual(self.page.input_value('#chat-dock-message'), '')
        self.shot('05-replied-from-dock')

        # Maximise: the page's own unsaved-note guard is respected; staying keeps the dock.
        self.page.click('#chat-dock-maximise')
        self.page.wait_for_selector('dialog.editor-leave-dialog[open]')
        self.page.click('dialog.editor-leave-dialog [data-stay]')
        until(lambda: self.page.evaluate("current==='vault'") and self.dock_open(), what='stayed, dock kept')
        self.assertEqual(self.page.input_value('#note-text'), NOTE_TEXT + 'Owner edit in progress.\n')
        self.page.click('#chat-dock-maximise')
        self.page.click('dialog.editor-leave-dialog [data-discard]')
        self.page.wait_for_selector('#chat-log')
        until(lambda: self.page.evaluate("current==='chat'"), what='maximised into Chat')
        self.assertFalse(self.dock_visible(), 'one view at a time: no dock on the Chat page')
        self.assertEqual(self.active(), 'chat-message', 'maximise focuses the page composer')
        until(lambda: self.bubbles('The tomatoes are nearly ripe.', owner=False) == 1
              and self.bubbles('Then we pick them on Saturday.', owner=False) == 1, what='one reconciled transcript')
        self.shot('06-maximised')

        # One backend launch per intent and one presentation of each message.
        sends = self.s.sends()
        self.assertEqual([s['state'] for s in sends], ['complete', 'complete'])
        self.assertEqual([self.s.launches(s['send_id']) for s in sends], [1, 1])
        self.assertEqual(len(self.keyed_posts()), 2)
        self.assertEqual(len({p['client_key'] for p in self.keyed_posts()}), 2)
        self.assertEqual(self.s.owner_rows().count('How is the garden?'), 1)
        self.assertEqual(self.bubbles('How is the garden?'), 1)
        self.assertEqual(self.bubbles('A newer draft in the dock'), 1)
        for send in sends:
            self.assertEqual(len(self.page.query_selector_all(f'[id="{send["send_id"]}:owner"]')), 1)
            self.assertEqual(len(self.page.query_selector_all(f'[id="{send["send_id"]}:reply:0"]')), 1)
        self.assertLessEqual(self.max_in_flight, 1, 'one controller polls')
        self.assert_never_legacy()

    # 2. view lifetime and draft ---------------------------------------------------------

    def test_2_views_change_without_restarting_the_send_and_the_draft_follows(self):
        self.s.gated(['Still ', 'thinking.'])
        self.open()
        self.type_and_send('Lifetime check')
        until(lambda: self.s.reached(1), what='turn paused')
        self.page.fill('#chat-message', 'Draft kept through every view')
        self.go('vault')
        until(self.dock_visible, what='launcher')
        self.page.click('#chat-dock-launcher')
        until(lambda: self.page.input_value('#chat-dock-message') == 'Draft kept through every view',
              what='the draft follows into the dock')
        until(lambda: 'Still' in self.dock_text(), what='stream in the dock')
        self.page.press('#chat-dock-message', 'Escape')
        until(lambda: not self.dock_open(), what='minimised with Escape')
        self.assertEqual(self.active(), 'chat-dock-launcher', 'focus returns to the launcher')
        self.page.keyboard.press('Enter')
        until(self.dock_open, what='reopened from the keyboard')
        self.page.click('#chat-dock-maximise')
        self.page.wait_for_selector('#chat-message')
        until(lambda: self.page.input_value('#chat-message') == 'Draft kept through every view', what='draft on page')
        self.go('now')
        self.go('chat')
        self.page.wait_for_selector('#chat-message')
        until(lambda: 'Still' in self.page.inner_text('#chat-log'), what='stream shown again at once')
        self.assertEqual(len(self.calls('GET', '/api/chat/sends/bootstrap')), 1, 'no view restarted the send')
        self.assertEqual(len(self.keyed_posts()), 1)
        self.s.release(1)
        self.wait_reply('Still thinking.')
        until(lambda: self.pending() is None, what='settled')
        self.assertEqual(self.page.input_value('#chat-message'), 'Draft kept through every view')
        self.assertEqual(self.storage('chat-draft-existing-nova'), 'Draft kept through every view')
        send = self.one_send('Lifetime check', 'Still thinking.')
        self.assertEqual(self.s.launches(send['send_id']), 1)
        self.assertLessEqual(self.max_in_flight, 1, 'one controller polls')
        self.assert_never_legacy()

    def test_2_reload_on_another_page_keeps_following_in_the_launcher(self):
        self.s.gated(['Across ', 'a reload.'])
        self.open()
        self.type_and_send('Reload me on Vault')
        until(lambda: self.s.reached(1), what='turn paused')
        self.go('vault')
        key = self.pending()['client_key']
        self.page.reload()
        self.page.wait_for_selector('#chat-dock-launcher')
        until(self.dock_visible, what='launcher after reload')
        until(lambda: 'Across' in self.launcher() or 'Checking' in self.launcher(), what='the restored send followed')
        self.assertEqual(self.pending()['client_key'], key)
        self.s.release(1)
        until(lambda: self.pending() is None, what='settled after reload')
        until(self.new_reply, what='an in-session new-reply indicator')
        self.assertFalse(self.dock_open(), 'still not opened for the owner')
        self.page.click('#chat-dock-launcher')
        until(lambda: self.dock_bubbles('Across a reload.', owner=False) == 1, what='the reply once in the dock')
        self.assertEqual(self.page.evaluate("document.querySelectorAll('#chat-dock-log .keyed-request').length"), 0)
        self.assertFalse(self.new_reply(), 'seen once the dock shows it')
        send = self.one_send_ledger('Reload me on Vault')
        self.assertEqual(self.s.launches(send['send_id']), 1)
        self.assert_never_legacy()

    def one_send_ledger(self, text):
        sends = self.s.sends()
        self.assertEqual(len(sends), 1, sends)
        self.assertEqual(self.s.owner_rows().count(text), 1)
        self.assertEqual(len({p['client_key'] for p in self.keyed_posts()}), 1)
        return sends[0]

    # 3. isolation and recovery ----------------------------------------------------------

    def test_3_profile_switch_from_the_dock_during_a_delayed_result(self):
        self.s.gated(['Nova is ', 'answering.'])
        self.page.goto(self.s.url('rowan', 'vault'))
        self.page.wait_for_selector('#chat-dock-launcher')
        until(self.dock_visible, what='rowan launcher')
        self.page.click('#chat-dock-launcher')
        self.page.fill('#chat-dock-message', 'Rowan draft')
        self.page.goto(self.s.url('nova', 'vault'))
        self.page.wait_for_selector('#chat-dock-launcher')
        until(self.dock_visible, what='nova launcher')
        self.page.click('#chat-dock-launcher')
        self.page.fill('#chat-dock-message', 'For Nova only')
        self.page.press('#chat-dock-message', 'Enter')
        until(lambda: self.s.reached(1), what='nova paused')
        self.page.fill('#chat-dock-message', 'Nova newer draft')
        # Switch companions the way the app does (a navigation), mid-turn.
        self.page.evaluate("()=>navigateProfile('rowan','vault')")
        self.page.wait_for_url('**profile=rowan**')
        self.page.wait_for_selector('#chat-dock-launcher')
        until(self.dock_visible, what='rowan launcher again')
        self.assertIn('Rowan', self.launcher())
        mark = len(self.requests)
        self.s.release(1)
        self.s.settled(self.s.sends('nova')[0]['send_id'])
        pause(1.0)
        self.assertNotIn('Nova is', self.page.content())
        self.assertNotIn('For Nova only', self.page.content())
        self.assertFalse([r for r in self.requests[mark:] if 'profile=nova' in r[1]], 'rowan never polls nova')
        self.page.click('#chat-dock-launcher')
        self.assertEqual(self.page.input_value('#chat-dock-message'), 'Rowan draft', "rowan's draft untouched")
        self.assertEqual(self.dock_bubbles('For Nova only'), 0)
        self.assertEqual(self.s.sends('rowan'), [])
        self.page.goto(self.s.url('nova', 'chat'))
        self.page.wait_for_selector('#chat-message')
        until(lambda: self.bubbles('Nova is answering.', owner=False) == 1, what="nova's reply in nova")
        self.assertEqual(self.page.input_value('#chat-message'), 'Nova newer draft')
        self.assertEqual(self.s.launches(self.s.sends('nova')[0]['send_id']), 1)
        self.assert_never_legacy()

    def test_3_lost_response_from_the_dock_is_recovered_by_the_same_key(self):
        self.s.scenario(reply='Recovered in the dock.')
        self.page.goto(self.s.url('nova', 'vault'))
        self.page.wait_for_selector('#chat-dock-launcher')
        until(self.dock_visible, what='launcher')
        seen = []

        def lose_response(route):
            seen.append(route.request.post_data)
            if len(seen) == 1:
                route.fetch()
                route.abort()
            else:
                route.continue_()
        self.page.route('**/api/chat/sends?*', lambda r: lose_response(r) if r.request.method == 'POST'
                        else r.continue_())
        self.page.click('#chat-dock-launcher')
        self.page.fill('#chat-dock-message', 'Lost from the dock')
        self.page.press('#chat-dock-message', 'Enter')
        until(lambda: self.dock_bubbles('Recovered in the dock.', owner=False) == 1, what='recovered reply')
        self.assertEqual(self.dock_bubbles('Lost from the dock'), 1)
        self.assertEqual(len(set(seen)), 1, 'any retry was the identical request')
        send = self.one_send_ledger('Lost from the dock')
        self.assertEqual(self.s.launches(send['send_id']), 1)
        self.assert_never_legacy()

    def test_3_sign_in_expiry_stops_activity_and_hides_the_launcher_preview(self):
        self.s.gated(['Protected words ', 'after sign-in.'])
        expired = {'on': False}
        self.page.route('**/api/operations/*', lambda r: r.fulfill(status=401, content_type='application/json',
                        body='{"error":"bad or missing token"}') if expired['on'] else r.continue_())
        self.open()
        self.type_and_send('Sent before expiry')
        until(lambda: self.s.reached(1), what='paused')
        self.go('vault')
        until(lambda: 'Protected words' in self.launcher(), what='preview while signed in')
        expired['on'] = True
        until(lambda: 'Sign in again' in self.launcher(), what='signed-out launcher')
        self.assertNotIn('Protected words', self.launcher(), 'no message preview while signed out')
        count = len(self.calls('GET', '/api/operations/'))
        pause(1.5)
        self.assertEqual(len(self.calls('GET', '/api/operations/')), count, 'protected polling stopped')
        self.assertEqual(self.pending()['message'], 'Sent before expiry')
        expired['on'] = False
        self.page.click('#chat-dock-launcher')
        until(lambda: WORDS['signed_out'] in self.dock_text(), what='the status in the dock')
        self.page.click('#chat-dock-log button:has-text("Check now")')
        self.s.release(1)
        until(lambda: self.dock_bubbles('Protected words after sign-in.', owner=False) == 1, what='completed')
        self.assertEqual({p['client_key'] for p in self.keyed_posts()}.__len__(), 1)
        send = self.one_send_ledger('Sent before expiry')
        self.assertEqual(self.s.launches(send['send_id']), 1)
        self.assert_never_legacy()

    # 4. usable narrow layout ------------------------------------------------------------

    def narrow(self, width, height, theme):
        self.page.set_viewport_size({'width': width, 'height': height})
        self.page.goto(self.s.url('nova', 'vault'))
        self.page.wait_for_selector('#chat-dock-launcher')
        self.page.evaluate(f"()=>document.documentElement.dataset.theme='{theme}'")
        until(self.dock_visible, what='the pill')
        box = self.page.locator('#chat-dock-launcher').bounding_box()
        bar = self.page.locator('#tabbar').bounding_box()
        self.assertLessEqual(box['y'] + box['height'], bar['y'], 'the pill sits above the tab bar')
        self.assertGreaterEqual(box['x'], 0)
        self.assertLessEqual(box['x'] + box['width'], width, 'the pill fits the screen')
        self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth>innerWidth'), 'no sideways scroll')
        return box, bar

    def test_4_phone_width_pill_sheet_and_keyboard(self):
        self.s.scenario(reply='Hello from the sheet.')
        for width, height, theme in ((390, 844, 'midnight'), (360, 740, 'daylight')):
            with self.subTest(width=width, theme=theme):
                _, bar = self.narrow(width, height, theme)
                self.shot(f'07-pill-{width}-{theme}')
                self.page.focus('#chat-dock-launcher')
                self.page.keyboard.press('Enter')
                until(self.dock_open, what='the sheet')
                panel = self.page.locator('#chat-dock-panel').bounding_box()
                composer = self.page.locator('#chat-dock-form').bounding_box()
                self.assertLessEqual(panel['y'] + panel['height'], bar['y'] + 1, 'the tab bar stays reachable')
                self.assertGreaterEqual(panel['width'], width - 1, 'full width')
                self.assertLessEqual(composer['y'] + composer['height'], bar['y'], 'composer above the tab bar')
                self.assertEqual(self.active(), 'chat-dock-message')
                self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth>innerWidth'))
                if width == 390:
                    self.page.fill('#chat-dock-message', 'From the phone sheet')
                    self.page.press('#chat-dock-message', 'Enter')
                    until(lambda: self.dock_bubbles('Hello from the sheet.', owner=False) == 1, what='reply in sheet')
                self.shot(f'08-sheet-{width}-{theme}')
                self.page.keyboard.press('Escape')
                until(lambda: not self.dock_open(), what='minimised')
                self.assertEqual(self.active(), 'chat-dock-launcher')
                # dialogs stay above the chat layer
                self.page.evaluate("()=>{const d=document.getElementById('product-dialog');"
                                   "document.getElementById('dialog-title').textContent='Above';d.showModal();}")
                on_top = self.page.evaluate("()=>{const b=document.getElementById('chat-dock-launcher').getBoundingClientRect();"
                                            "const e=document.elementFromPoint(b.x+b.width/2,b.y+b.height/2);"
                                            "return !document.getElementById('chat-dock').contains(e)}")
                self.page.evaluate("()=>document.getElementById('product-dialog').close()")
                self.assertTrue(on_top, 'a dialog covers the chat layer')
        send = self.one_send_ledger('From the phone sheet')
        self.assertEqual(self.s.launches(send['send_id']), 1)

    def test_4_desktop_dock_fits_and_does_not_cover_the_editor(self):
        self.page.set_viewport_size({'width': 1280, 'height': 800})
        for theme in ('midnight', 'daylight'):
            with self.subTest(theme=theme):
                self.open_note()
                self.page.evaluate(f"()=>document.documentElement.dataset.theme='{theme}'")
                until(self.dock_visible, what='launcher')
                self.page.click('#chat-dock-launcher')
                until(self.dock_open, what='dock')
                panel = self.page.locator('#chat-dock-panel').bounding_box()
                self.assertLessEqual(panel['x'] + panel['width'], 1280)
                self.assertLessEqual(panel['y'] + panel['height'], 800)
                self.assertGreaterEqual(panel['y'], 0)
                self.shot(f'09-dock-{theme}')
                self.page.click('#chat-dock-minimise')
                until(lambda: not self.dock_open(), what='minimised')
                self.page.click('#note-text')
                self.assertEqual(self.active(), 'note-text', 'the editor is reachable with the dock collapsed')

    def seed_history(self, n=130):
        """Synthetic recorded history in a workspace session (the chat contract's store)."""
        sys.path.insert(0, str(ROOT / 'tests'))
        from chat_fixtures import HermesStore
        from kit.app import runtime as hr
        c = self.s.companions['nova']
        store = HermesStore(c.home)
        store.session('web-history', 'cli', started=1)
        hr.note_workspace_session(c, 'web-history')
        t = 1_780_000_000
        for i in range(n):
            store.say('web-history', 'user' if i % 2 == 0 else 'assistant', f'History line {i:03d}', t + i * 60)

    def top_of(self, text):
        return self.page.evaluate("t=>{const b=[...document.querySelectorAll('#chat-log .bubble')].find(b=>"
                                  "(b.querySelector('.message-body')?.innerText||'').trim()===t);"
                                  "return b?b.getBoundingClientRect().top:null}", text)

    def test_4_older_pages_and_incoming_text_never_move_the_reader(self):
        self.page.set_viewport_size({'width': 1280, 'height': 800})
        self.seed_history()
        self.s.gated(['A reply ', 'that grows ', 'and grows.'])
        self.open()
        self.assertIn('History line 129', self.page.inner_text('#chat-log'))
        self.assertNotIn('History line 069', self.page.inner_text('#chat-log'), 'only the newest page first')
        # Older history loads near the top and the reader keeps their place.
        self.page.evaluate("()=>{document.getElementById('chat-log').scrollTop=0}")
        at = self.top_of('History line 070')
        until(lambda: 'History line 069' in self.page.inner_text('#chat-log'), what='an older page')
        self.assertAlmostEqual(self.top_of('History line 070'), at, delta=4)
        # A reply arriving while someone reads older messages does not scroll them away.
        self.page.evaluate("()=>{const l=document.getElementById('chat-log');l.scrollTop=l.scrollHeight}")
        self.type_and_send('Grow while I read')
        until(lambda: self.s.reached(1), what='first part')
        self.page.evaluate("()=>{const l=document.getElementById('chat-log');l.scrollTop=l.scrollHeight/3}")
        pause(0.4)
        reading = self.page.evaluate("document.getElementById('chat-log').scrollTop")
        self.s.release(1)
        until(lambda: 'that grows' in self.page.inner_text('#chat-log'), what='more text')
        self.s.release(2)
        self.wait_reply('A reply that grows and grows.')
        self.assertAlmostEqual(self.page.evaluate("document.getElementById('chat-log').scrollTop"), reading, delta=4)
        self.page.wait_for_selector('.chat-new-messages')
        self.page.click('.chat-new-messages')
        until(lambda: self.page.evaluate("(()=>{const l=document.getElementById('chat-log');"
                                         "return l.scrollHeight-l.scrollTop-l.clientHeight<100})()"), what='at the foot')
        # Leaving and returning restores the place, not the foot.
        self.page.evaluate("()=>{const l=document.getElementById('chat-log');l.scrollTop=l.scrollHeight/3}")
        pause(0.3)
        mark = self.page.evaluate("[...document.querySelectorAll('#chat-log .bubble')].find(b=>b.getBoundingClientRect()"
                                  ".bottom>document.getElementById('chat-log').getBoundingClientRect().top)"
                                  ".querySelector('.message-body').innerText.trim()")
        was = self.top_of(mark)
        self.go('vault')
        self.go('chat')
        self.page.wait_for_selector('#chat-log .bubble')
        until(lambda: self.top_of(mark) is not None, what='the same message back')
        self.assertAlmostEqual(self.top_of(mark), was, delta=6)
        self.one_send('Grow while I read', 'A reply that grows and grows.')

    # 5. default compatibility ------------------------------------------------------------

    def test_5_the_new_views_never_post_to_the_legacy_route(self):
        self.s.scenario(reply='Keyed only.')
        self.page.goto(self.s.url('nova', 'vault'))
        self.page.wait_for_selector('#chat-dock-launcher')
        until(self.dock_visible, what='launcher')
        self.page.click('#chat-dock-launcher')
        self.page.fill('#chat-dock-message', 'Keyed from the dock')
        self.page.press('#chat-dock-message', 'Enter')
        until(lambda: self.dock_bubbles('Keyed only.', owner=False) == 1, what='reply')
        self.assertEqual(self.calls('POST', '/api/chat'), [])
        until(lambda: self.page.evaluate('activeOperation===null'), what='the non-chat exclusion ends at settlement')


class DefaultPage(Browser):
    """Without the explicit client build, none of the persistent Chat exists on the page."""
    keyed = False

    def test_5_default_page_has_no_dock_store_or_controller(self):
        self.open()
        self.assertFalse(self.page.evaluate('!!(window.ChatStore||window.ChatView||window.PersistentChat)'))
        self.page.evaluate("()=>showTab('vault')")
        pause(0.5)
        self.assertIsNone(self.page.query_selector('#chat-dock'))
        for name in ('chat-store.js', 'chat-view.js', 'chat-controller.js', 'chat.css'):
            self.assertNotIn(name, self.page.content())


class RoutesOnlyPage(DefaultPage):
    keyed = True
    client = False


if __name__ == '__main__':
    unittest.main()
