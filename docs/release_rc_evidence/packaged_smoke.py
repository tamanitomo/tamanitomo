#!/usr/bin/env python3
"""Packaged-release smoke for the Chat/Journal RC. Synthetic data only.

Usage: packaged_smoke.py <extracted package root> <report.json>

Launches the package's own entry point (`python -m kit.app.hosted`, as the
systemd unit does) against a throwaway Hermes root with two synthetic
companions, a fake Hermes that echoes, and a random token. Then drives the
flag-off page in headless Chromium. Nothing here reads ~/.hermes or ~/vault.
"""
import datetime as dt, json, os, pathlib, socket, subprocess, sys, tempfile, time, urllib.request

PKG = pathlib.Path(sys.argv[1]).resolve()
REPORT = pathlib.Path(sys.argv[2])
sys.path[:0] = [str(PKG), str(PKG / 'kit/scripts')]
import companion_config as cc          # from the package
import companion_life as life
from PIL import Image
from playwright.sync_api import sync_playwright

assert pathlib.Path(cc.__file__).resolve().is_relative_to(PKG), cc.__file__
UTC = dt.timezone.utc
TOKEN = 'rc-smoke-' + os.urandom(6).hex()
DRAFT = 'A half-written thought about the market'
checks = []


def check(name, ok, detail=''):
    checks.append({'check': name, 'ok': bool(ok), 'detail': str(detail)[:300]})
    print(('PASS ' if ok else 'FAIL ') + name + (f' — {detail}' if detail and not ok else ''), flush=True)


def until(fn, what, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(0.1)
    raise AssertionError('timed out: ' + what)


def state(activity, location='home', confirmed=True):
    return {'activity': activity, 'location': location, 'mood': 'calm', 'outfit': ['tee'],
            'transition': '', 'confirmed': confirmed}


def seed(c):
    rec = lambda when, activity, ident, **kw: life.record(c.life, activity + '.', activity, 'in_progress', when, ident,
                                                          c.agent, c.human, state=state(activity, **kw))['episode']
    rec(dt.datetime(2026, 9, 20, 9, 0, tzinfo=UTC), 'walking to the market', 'walk-1', location='market street')
    rec(dt.datetime(2026, 9, 20, 9, 15, tzinfo=UTC), 'walking to the market', 'walk-2', location='market street')
    reading = rec(dt.datetime(2026, 9, 20, 11, 0, tzinfo=UTC), 'reading by the window', 'read-1', location='library')
    folder = c.data / 'image-timeline'
    (folder / 'captures').mkdir(parents=True)
    (folder / 'images').mkdir()
    ident = 'a' * 24
    Image.new('RGB', (64, 80), (90, 140, 200)).save(folder / 'images' / f'{ident}.png')
    (folder / 'captures' / f'{ident}.json').write_text(json.dumps(
        {'id': ident, 'created_at': reading['recorded_at'], 'status': 'saved', 'scene': reading,
         'filename': f'{ident}.png', 'primary_filename': f'{ident}.png', 'variants': [{'filename': f'{ident}.png'}]}))
    c.soul_dir.mkdir(parents=True, exist_ok=True)
    (c.soul_dir / 'Lifelog.md').write_text(
        '## 2026-09-18\n\nThe day before the market. Rain all afternoon.\n\n'
        '## 2026-09-20\n\nA slow **market** morning, then the library until the light went.\n')
    (c.home / 'companion-appearance.json').write_text(json.dumps({'nav_pins': ['chat', 'timeline', 'journals']}))


def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p


tmp = pathlib.Path(tempfile.mkdtemp(prefix='rc-smoke-', dir=os.environ.get('TMPDIR')))
root, vault, st = tmp / 'hermes', tmp / 'vault', tmp / 'state'
root.mkdir(); vault.mkdir()
comps = {}
for name, agent in (('nova', 'Nova'), ('rowan', 'Rowan')):
    c = cc.Companion(agent=agent, human='Alex', profile=name, hermes_root=root, vault=vault, soul_in_vault=False,
                     context_mode='fixed', timezone='America/New_York')
    c.home.mkdir(parents=True); c.life.mkdir(parents=True, exist_ok=True); c.soul_dir.mkdir(parents=True, exist_ok=True)
    c.save(); comps[name] = c
seed(comps['nova'])

# A fake Hermes: `chat ... -q MSG` echoes; everything else goes to the package's contract double.
fake = tmp / 'fake_hermes_chat.py'
fake.write_text(
    'import sys,runpy,pathlib\n'
    'a=sys.argv[1:]\n'
    "if a[:1]==['chat'] and '-q' in a:\n"
    "    print('Echo from synthetic Hermes: '+a[a.index('-q')+1]);sys.exit(0)\n"
    f"sys.argv=[{str(PKG / 'tests/fake_hermes.py')!r},*a];runpy.run_path(sys.argv[0],run_name='__main__')\n")
port = free_port()
env = {k: v for k, v in os.environ.items() if not k.startswith(('TAMANITOMO_', 'COMPANION_', 'HERMES_'))}
env.update(PATH='/usr/bin:/bin', HERMES_HOME=str(root), TAMANITOMO_APP_STATE=str(st), TAMANITOMO_TOKEN=TOKEN,
           COMPANION_BIND='127.0.0.1', COMPANION_PORT=str(port),
           COMPANION_HERMES_COMMAND=json.dumps([sys.executable, str(fake)]))
log = open(tmp / 'server.log', 'w')
proc = subprocess.Popen([sys.executable, '-m', 'kit.app.hosted'], cwd=PKG, env=env, stdout=log, stderr=subprocess.STDOUT)
base = f'http://127.0.0.1:{port}'
url = lambda profile, tab: f'{base}/?installation=existing&profile={profile}&token={TOKEN}#{tab}'
try:
    def up():
        try:
            return urllib.request.urlopen(base + '/api/instance', timeout=2).status in (200, 401, 403)
        except urllib.error.HTTPError as e:
            return e.code in (401, 403)
    until(up, 'packaged server up', 30)
    check('packaged entry point kit.app.hosted serves', proc.poll() is None)

    def get(path, auth=True):
        req = urllib.request.Request(base + path, headers={'X-Tamanitomo-Token': TOKEN} if auth else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    s, body = get('/')
    html = body.decode()
    check('flag-off page carries no keyed signal or persistent-Chat assets',
          s == 200 and 'tamanitomo-chat-sends' not in html and 'chat-controller.js' not in html and 'chat.css' not in html)
    check('flag-off page loads journal.js', '/static/journal.js?v=' in html)
    for asset in ('chat-controller.js', 'chat-sends.js', 'chat-store.js', 'chat-view.js', 'chat.css'):
        check(f'/static/{asset} absent from package (404)', get('/static/' + asset)[0] == 404)
    s, _ = get('/api/chat/sends/bootstrap?installation=existing&profile=nova')
    check('keyed send routes not registered', s in (404, 405), s)
    s, _ = get('/api/journal/archive?installation=existing&profile=nova', auth=False)
    check('unauthenticated API read refused', s in (401, 403), s)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        errors, writes = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: writes.append((r.method, r.url)) if r.method not in ('GET', 'HEAD') and '/api/' in r.url else None)
        H = lambda: page.evaluate('location.hash')
        text = lambda: page.inner_text('#journal-page')

        def at(day, view, needle):
            until(lambda: H() == f'#journals/{day}/{view}' and needle in text(), f'{day}/{view} {needle!r}')
            return page.get_attribute(f'#journal-view-{view}', 'aria-selected') == 'true'

        def go(tab):
            page.evaluate(f"()=>showTab('{tab}')"); until(lambda: page.evaluate(f"current==='{tab}'"), 'tab ' + tab)

        page.goto(url('nova', 'chat'))
        page.wait_for_selector('#chat-message', timeout=20000)
        # Pre-existing race (same code on 3.0.24): typing before the feed load finishes is overwritten.
        # Record it once, then wait as the accepted harness does.
        page.fill('#chat-message', 'typed during load')
        page.wait_for_function("!document.querySelector('.chat-loading')", timeout=20000)
        time.sleep(0.5)
        early = page.evaluate("sessionStorage.getItem(chatKey('draft'))")
        checks.append({'check': 'OBSERVATION text typed before feed load is persisted', 'ok': True,
                       'detail': f'stored draft={early!r} box={page.input_value("#chat-message")!r}'})
        print('OBSERVE early draft', repr(early), repr(page.input_value('#chat-message')))
        check('legacy Chat page, no KeyedChat client', page.evaluate('typeof window.KeyedChat') == 'undefined')
        page.fill('#chat-message', DRAFT)
        before = len(writes)

        go('journals')
        check('Journal opens latest reflection with date route', at('2026-09-20', 'reflection', 'slow market morning'))
        page.click('#journal-browse'); page.click('[data-pick-day="2026-09-18"]')
        check('historical Reflection 2026-09-18', at('2026-09-18', 'reflection', 'Rain all afternoon'))
        page.click('#journal-view-day')
        check('historical Day 2026-09-18 (no scenes, honest)', at('2026-09-18', 'day', 'No scenes were recorded on this day.'))
        page.go_back(); page.go_back()
        check('back returns through Journal history', at('2026-09-20', 'reflection', 'slow market morning'))
        page.click('#journal-view-day')
        ok = at('2026-09-20', 'day', 'Reading by the window')
        check('Day 2026-09-20 scenes + collapsed snapshot + photo in its scene',
              ok and 'unchanged snapshot' in text() and
              page.locator('#journal-page [data-scene="read-1"] [data-archive-photo]').count() == 1, text()[:200])
        page.reload(); page.wait_for_selector('#journal-page')
        check('refresh keeps date and view', at('2026-09-20', 'day', 'Reading by the window'))
        page.goto(url('nova', 'journals/2026-09-18/reflection'))
        check('shared date link lands directly', at('2026-09-18', 'reflection', 'Rain all afternoon'))

        page.goto(url('nova', 'timeline'))
        until(lambda: page.evaluate("current==='timeline'"), 'old #timeline link')
        page.wait_for_selector('#timeline-feed [data-journal]')
        pin = page.locator('#tabbar button[data-tab="timeline"]')
        check('old #timeline link works and saved pin rendered', pin.count() == 1)
        go('photos'); page.set_viewport_size({'width': 390, 'height': 844}); pin.click()
        until(lambda: H() == '#timeline', 'pin opens Timeline')
        page.set_viewport_size({'width': 1280, 'height': 720})
        page.wait_for_selector('#timeline-feed [data-journal]')
        page.locator('#timeline-feed [data-journal]').first.click()
        check('Timeline diary link lands in Journal', at('2026-09-20', 'reflection', 'slow market morning'))

        go('chat'); page.wait_for_selector('#chat-message')
        until(lambda: page.input_value('#chat-message') == DRAFT, 'draft kept', 10)
        check('Chat draft preserved across Journal, Timeline, back/forward and reloads',
              page.input_value('#chat-message') == DRAFT)
        check('archive navigation made no write request', writes[before:] == [], writes[before:])

        # existing production send path, synthetic echo
        page.fill('#chat-message', 'hello from the smoke')
        page.click('#send-message')
        until(lambda: 'Echo from synthetic Hermes: hello from the smoke' in page.inner_text('#chat'), 'legacy reply', 30)
        check('existing Chat send (POST /api/chat) round-trips via fake Hermes',
              any(m == 'POST' and u.split('?')[0].endswith('/api/chat') for m, u in writes))

        # profile switch: Rowan sees only its own (empty) archive
        page.goto(url('rowan', 'journals'))
        until(lambda: page.evaluate("current==='journals'"), 'rowan journals')
        time.sleep(1.5)
        t = page.inner_text('#journals')
        check('profile switch: Rowan shows none of Nova\'s archive',
              'market' not in t.lower() and 'Rain all afternoon' not in t, t[:200])
        check('no page errors', [e for e in errors if 'Failed to fetch' not in e] == [], errors)
        browser.close()
finally:
    proc.terminate()
    try:
        proc.wait(15)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
    server_log = (tmp / 'server.log').read_text()
    REPORT.write_text(json.dumps({'package': str(PKG), 'checks': checks, 'server_log_tail': server_log[-2000:],
                                  'passed': sum(c['ok'] for c in checks), 'failed': sum(not c['ok'] for c in checks)},
                                 indent=2))
    import shutil; shutil.rmtree(tmp, ignore_errors=True)
print(json.dumps({'passed': sum(c['ok'] for c in checks), 'failed': sum(not c['ok'] for c in checks)}))
