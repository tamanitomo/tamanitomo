#!/usr/bin/env python3
"""Packaged-entry smoke for the Vault editor. Synthetic data only; development tool.

    python tools/vault_packaged_smoke.py <release ZIP> <report.json>

Extracts the ZIP to a temporary directory and starts the package's own entry point
(`python -m kit.app.hosted`, as the systemd unit does) against a throwaway Hermes
root with one synthetic companion, a fake Hermes that echoes chat, and a random
token. It then drives headless Chromium: the local editor bundle is served, a note is
edited and autosaved, an unsaved edit survives a reload and is saved from the recovered
draft, and a legacy Chat round-trip does not disturb the note. It reports which Chat
implementation the page runs. Nothing reads ~/.hermes or a real vault.
"""
import json, os, pathlib, shutil, socket, subprocess, sys, tempfile, time, urllib.request, zipfile

ZIP, REPORT = pathlib.Path(sys.argv[1]).resolve(), pathlib.Path(sys.argv[2])
tmp = pathlib.Path(tempfile.mkdtemp(prefix='vault-smoke-'))
with zipfile.ZipFile(ZIP) as z:
    z.extractall(tmp)
PKG = tmp / 'tamanitomo'
sys.path[:0] = [str(PKG), str(PKG / 'kit/scripts')]
import companion_config as cc                                    # from the package
from playwright.sync_api import sync_playwright

assert pathlib.Path(cc.__file__).resolve().is_relative_to(PKG)
TOKEN = 'vault-smoke-' + os.urandom(6).hex()
checks = []
PAGE = []      # waiting must pump Playwright (route callbacks run inside its calls)


def check(name, ok, detail=''):
    checks.append({'check': name, 'ok': bool(ok), 'detail': str(detail)[:300]})
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f' — {detail}'), flush=True)


def until(fn, what, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        PAGE[0].wait_for_timeout(100) if PAGE else time.sleep(0.1)
    raise AssertionError('timed out: ' + what)


root, vault = tmp / 'hermes', tmp / 'vault'
root.mkdir(); vault.mkdir(); (vault / 'notes').mkdir()
c = cc.Companion(agent='Nova', human='Alex', profile='nova', hermes_root=root, vault=vault, soul_in_vault=False,
                 context_mode='fixed')
c.home.mkdir(parents=True); c.save()
NOTE = 'notes/Smoke.md'
(vault / NOTE).write_text('# Smoke\n\n' + ''.join(f'Line {i}\n' for i in range(200)), encoding='utf-8')
fake = tmp / 'fake_hermes_chat.py'
fake.write_text("import sys,runpy\na=sys.argv[1:]\nif a[:1]==['chat'] and '-q' in a:\n"
                "    print('Echo from synthetic Hermes: '+a[a.index('-q')+1]);sys.exit(0)\n"
                f"sys.argv=[{str(PKG / 'tests/fake_hermes.py')!r},*a];runpy.run_path(sys.argv[0],run_name='__main__')\n")
s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
env = {k: v for k, v in os.environ.items() if not k.startswith(('TAMANITOMO_', 'COMPANION_', 'HERMES_'))}
env.update(PATH='/usr/bin:/bin', HERMES_HOME=str(root), TAMANITOMO_APP_STATE=str(tmp / 'state'), TAMANITOMO_TOKEN=TOKEN,
           COMPANION_BIND='127.0.0.1', COMPANION_PORT=str(port), COMPANION_HERMES_COMMAND=json.dumps([sys.executable, str(fake)]))
log = open(tmp / 'server.log', 'w')
proc = subprocess.Popen([sys.executable, '-m', 'kit.app.hosted'], cwd=PKG, env=env, stdout=log, stderr=subprocess.STDOUT)
base = f'http://127.0.0.1:{port}'
url = lambda tab: f'{base}/?installation=existing&profile=nova&token={TOKEN}#{tab}'


def get(path):
    req = urllib.request.Request(base + path, headers={'X-Tamanitomo-Token': TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


try:
    until(lambda: get('/api/instance')[0] == 200, 'server up', 30)
    check('packaged entry point kit.app.hosted serves', proc.poll() is None)
    s1, html = get('/'); html = html.decode()
    check('page loads the local editor bundle and script', '/static/vault-editor.bundle.js?v=' in html
          and '/static/vault-editor.js?v=' in html)
    manifest = json.loads((PKG / 'SHA256SUMS.json').read_text())
    for name in ('kit/app/static/vault-editor.bundle.js', 'kit/app/static/vault-editor.LICENSES.txt', 'kit/app/static/vault-editor.js'):
        st, body = get('/static/' + name.rsplit('/', 1)[1])
        import hashlib
        check(f'{name} shipped, served and matches the manifest', st == 200 and hashlib.sha256(body).hexdigest() == manifest.get(name))
    check('no persistent-Chat assets in the page (normal build)', 'chat-controller.js' not in html and 'tamanitomo-chat-sends' not in html)
    check('no build tooling shipped', not (PKG / 'tools/editor').exists() and not any(PKG.rglob('node_modules')))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(); page = browser.new_page(viewport={'width': 1280, 'height': 800}); PAGE.append(page)
        errors, remote = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: remote.append(r.url) if not r.url.startswith(base) and not r.url.startswith('data:') else None)
        page.on('dialog', lambda d: d.accept())
        page.goto(url('vault')); page.wait_for_selector('#vault-tree .vault-node', state='attached')
        check('the bundle defined the editor API', page.evaluate("typeof TamanitomoCodeMirror==='object'&&typeof VaultEditor==='object'"))
        chat_impl = 'persistent (keyed)' if page.evaluate("typeof window.KeyedChat!=='undefined'") else 'legacy (POST /api/chat)'
        check('Chat implementation on this page is the legacy one', chat_impl.startswith('legacy'), chat_impl)
        page.evaluate(f"()=>readNote({NOTE!r})")
        until(lambda: page.evaluate('VaultEditor.status()') == 'saved', 'note open')
        page.click('[data-vault-mode="edit"]'); page.wait_for_selector('.vault-cm .cm-content')
        page.evaluate("()=>{const v=VaultEditor.view();v.focus();v.dispatch({selection:{anchor:9}})}")
        page.keyboard.type('Packaged edit ✨ ')
        until(lambda: page.evaluate('VaultEditor.status()') == 'saved', 'autosave')
        check('edit autosaved through the revision contract', (vault / NOTE).read_text(encoding='utf-8').startswith('# Smoke\n\nPackaged edit ✨ '))

        # recovery: the save never reaches the server, then the page reloads
        held = []
        page.route('**/api/vault/file**', lambda r: held.append(r) if r.request.method == 'PUT' else r.continue_())
        page.keyboard.type('Unsaved. ')
        until(lambda: held, 'save sent'); page.wait_for_timeout(400)
        for r in held: r.abort('connectionreset')
        page.unroute('**/api/vault/file**')
        page.reload(); page.wait_for_selector('#vault-tree .vault-node', state='attached')
        until(lambda: page.evaluate('VaultEditor.status()') == 'draft', 'draft recovered')
        check('unsaved text recovered after reload, not saved behind the owner',
              'Unsaved. ' in page.evaluate('VaultEditor.text()') and 'Unsaved. ' not in (vault / NOTE).read_text(encoding='utf-8'))
        page.click('#vault-retry')
        until(lambda: page.evaluate('VaultEditor.status()') == 'saved', 'saved from draft')
        check('recovered draft saved on request', 'Unsaved. ' in (vault / NOTE).read_text(encoding='utf-8'))

        # a legacy Chat round-trip, then back to the note: selection and text intact
        page.click('[data-vault-mode="edit"]')
        page.evaluate("()=>{const v=VaultEditor.view();v.focus();v.dispatch({selection:{anchor:20,head:30}})}")
        page.evaluate("()=>showTab('chat')"); page.wait_for_selector('#chat-message')
        page.wait_for_function("!document.querySelector('.chat-loading')", timeout=20000)
        page.fill('#chat-message', 'hello from the vault smoke'); page.click('#send-message')
        until(lambda: 'Echo from synthetic Hermes: hello from the vault smoke' in page.inner_text('#chat'), 'legacy reply', 30)
        page.evaluate("()=>showTab('vault')")
        until(lambda: page.locator('.vault-cm').count() == 1, 'editor back')
        sel = page.evaluate("()=>{const s=VaultEditor.view().state.selection.main;return [s.anchor,s.head]}")
        check('after a legacy Chat round-trip the note keeps its selection', sel == [20, 30], sel)
        check('no page errors', errors == [], errors)
        check('no request left the local server (no CDN)', remote == [], remote[:3])
        page.screenshot(path=str(REPORT.with_suffix('.png')))
        browser.close()
finally:
    proc.terminate()
    try:proc.wait(15)
    except subprocess.TimeoutExpired:proc.kill()
    log.close()
    REPORT.write_text(json.dumps({'zip_sha256': __import__('hashlib').sha256(ZIP.read_bytes()).hexdigest(),
                                  'checks': checks, 'passed': sum(c['ok'] for c in checks),
                                  'failed': sum(not c['ok'] for c in checks)}, indent=2))
    shutil.rmtree(tmp, ignore_errors=True)
print(json.dumps({'passed': sum(c['ok'] for c in checks), 'failed': sum(not c['ok'] for c in checks)}))
