#!/usr/bin/env python3
"""Serve the workspace against a synthetic companion, for looking at changes in
a real browser without touching anyone's data.

Everything lives in a temporary directory that is removed on exit: a Hermes
root, a vault, one companion ("Nova") and one human ("Robin"), and ledgers
seeded with invented memories. The access token is random per run and is
printed once. Hermes is replaced by tests/fake_hermes.py, so nothing reaches a
model or a messaging platform.

    python tools/preview_fixture.py [--port 38500] [--keep]

With --persistent-chat the app is built with keyed sends and their client
(chat_sends=Options(client=True), NOT activated in any shipped entry point), so
the persistent Chat page, desktop dock and mobile pill can be tried. Sends go
to the Phase 1B protocol double (tests/phase1b_c1/fake_hermes) and replies
stream in a few timed steps; a second companion ("Rowan") and a few ordinary
vault notes are added for the profile-switch and Vault parts of the journey.

    python tools/preview_fixture.py --persistent-chat [--port 38500]

Screenshots taken from this are safe to share: no live names, transcripts,
portraits or vault content exist in it.
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, secrets, shutil, signal, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

import companion_config as cc  # noqa: E402
import companion_render as cr  # noqa: E402
import companion_self as slf  # noqa: E402

UTC = dt.timezone.utc
# (category, statement, quote, written from a reflection?)
FACTS = [
    ('likes', 'Robin enjoys playing Fire Emblem.', 'I play Fire Emblem all the time.', True),
    ('people', "Robin's sister is Bee.", 'My sister is Bee.', True),
    ('people', 'Robin introduced Alice to Kit.', 'I introduced Alice to Kit at the party.', True),
    ('people', 'Robin introduced Kit to Alice.', 'Then I introduced Kit to Alice properly.', True),
    ('logistics', 'Robin has an older 4 GB GTX 1050 Ti available to install in a spare PC.', 'I have an old 4 GB 1050 Ti for the spare PC.', False),
    ('other', 'Robin has an older 4 GB GTX 1050 Ti available for the spare PC.', 'That 1050 Ti is going in the spare PC.', False),
    ('likes', 'Robin writes C++.', 'Most of my work is C++.', True),
    ('likes', 'Robin writes C.', 'I also write plain C for the firmware.', True),
    ('places', 'Robin is from the US.', "I'm from the US originally.", False),
]


def seed(tmp: Path) -> tuple[Path, cc.Companion]:
    root = tmp / 'hermes'; vault = tmp / 'vault'
    root.mkdir(); vault.mkdir()
    c = cc.Companion(agent='Nova', human='Robin', profile='nova', hermes_root=root, vault=vault,
                     soul_in_vault=False, context_mode='fixed', timezone='UTC')
    c.home.mkdir(parents=True); c.life.mkdir(parents=True)
    c.save(); c.soul.write_text(cr.render_template('SOUL.md.tmpl', cr.mapping_for(c, 'warm', 'none')))
    start = dt.datetime(2026, 9, 1, 12, tzinfo=UTC)
    for i, (category, statement, quote, written) in enumerate(FACTS):
        when = start + dt.timedelta(days=i)
        slf.record_fact(c.human_dir, statement, f'{when.isoformat()}: {quote}', when, category, 'stated',
                        f'fixture message:{i}', human=c.human,
                        statement_origin='model_paraphrase' if written else 'recorded')
    slf.hold_fact(c.human_dir, 'Robin loves hiking.', f'{start.isoformat()}: My sister loves hiking.', start,
                  'likes', 'fixture message:99', ['the quote is about someone else'], c.human)
    seed_conversation(c, start)
    return root, c


def seed_conversation(c, start):
    """A Hermes-schema state.db for the chat contract: the owner on the
    workspace, a terminal and Telegram; a stranger, a group and a cron run
    that must stay out; an edit and a deletion to reconcile."""
    sys.path.insert(0, str(ROOT / 'tests'))
    from chat_fixtures import HermesStore, OWNER_TELEGRAM, standard_sessions
    from kit.app import runtime as hr
    store = HermesStore(c.home); standard_sessions(store)
    hr.note_workspace_session(c, 'web')
    (c.home / '.tamanitomo-chat-owner.json').write_text(json.dumps({'telegram': [OWNER_TELEGRAM]}))
    t = start.timestamp()
    store.say('tg', 'user', 'Morning! On the train again.', t + 60, platform_message_id='101')
    store.say('tg', 'assistant', 'Safe travels. Did you bring the book?', t + 90)
    store.say('web', 'user', 'Back at my desk now.', t + 3600)
    store.say('web', 'assistant', 'Welcome back. Tea first?', t + 3620)
    store.say('term', 'user', 'quick question from the terminal', t + 7200)
    store.say('stranger', 'user', 'a stranger writes (must not appear)', t + 7300)
    store.say('group', 'user', 'group chatter (must not appear)', t + 7400)
    store.say('job', 'assistant', 'nightly cron output (must not appear)', t + 7500)
    for i in range(3):store.say('tg', 'user', 'hi', t + 8000)   # identical text and time, three messages





NOTES = {
    'notes/Garden plan.md': '# Garden plan\n\nTomatoes along the south fence.\nBasil in the blue pots.\n\n'
                            'See [[Reading list]] for the seed catalogue.\n',
    'notes/Reading list.md': '# Reading list\n\n- The seed catalogue\n- A book about bridges\n',
    'notes/Weekend.md': '# Weekend\n\nSaturday: market, then the long walk.\nSunday: nothing planned.\n',
}
# Streamed replies for the persistent Chat preview, one per send, in rotation.
REPLIES = [
    ['Oh, that is a lovely thing to hear. ', 'I was just thinking about the garden, ', 'actually: ',
     'the tomatoes by the south fence ', 'should be ready by the weekend. ', 'Shall we plan the market trip?'],
    ['Mm, give me a second to think. ', 'I would start with the reading list, ', 'then the walk. ',
     'The bridge book can wait for a rainy day.'],
    ['Yes! ', 'Saturday it is. ', 'I will remember the blue pots ', 'and remind you about the basil.'],
]


def seed_persistent_chat(root: Path, c) -> cc.Companion:
    """A second synthetic companion and a few ordinary, editable vault notes."""
    rowan = cc.Companion(agent='Rowan', human='Robin', profile='rowan', hermes_root=root, vault=c.vault,
                         soul_in_vault=False, context_mode='fixed', timezone='UTC')
    rowan.home.mkdir(parents=True); rowan.life.mkdir(parents=True, exist_ok=True)
    rowan.save(); rowan.soul.write_text(cr.render_template('SOUL.md.tmpl', cr.mapping_for(rowan, 'warm', 'none')))
    for relative, text in NOTES.items():
        path = c.vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    # No favourable newest session is seeded: the seeded conversation's newest 'cli' session is
    # a gateway chat (gw-cli) that keyed sends refuse, and the persistent Chat continues the
    # most recent ELIGIBLE session the server names (GET /api/chat/continuation) instead.
    return rowan


def stream_replies(homes, stop):
    """Each send streams the next reply in REPLIES, one step every ~1.2 s: the protocol
    double waits at <pause>/at<i> for go<i>; this writes go<i>, then clears both files so
    the next turn pauses again. It also rotates the scenario for the next send."""
    import threading, time
    turns = {h: 0 for h in homes}

    def scenario(home):
        steps = REPLIES[turns[home] % len(REPLIES)]
        (home / 'fake_scenario.json').write_text(json.dumps(
            {'stream_steps': steps, 'stream_pause_dir': str(home / 'preview-pause')}))

    for home in homes:
        (home / 'preview-pause').mkdir(exist_ok=True)
        scenario(home)

    def run():
        while not stop.is_set():
            for home in homes:
                pause = home / 'preview-pause'
                for at in sorted(pause.glob('at*')):
                    i = at.name[2:]
                    if i == '1':                  # a new turn has read its scenario: rotate
                        turns[home] += 1
                        scenario(home)
                    time.sleep(1.2)
                    go = pause / f'go{i}'
                    go.write_text('')
                    time.sleep(0.3)
                    go.unlink(missing_ok=True); at.unlink(missing_ok=True)
            time.sleep(0.05)
    threading.Thread(target=run, daemon=True).start()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=38500)
    p.add_argument('--keep', action='store_true', help='leave the temporary directory behind')
    p.add_argument('--persistent-chat', action='store_true',
                   help='build with keyed sends and the persistent Chat UI (synthetic; not activated anywhere else)')
    p.add_argument('--mock-provider', action='store_true',
                   help='also serve tests/mock_provider.py and point the synthetic Hermes home at it (no fallbacks)')
    a = p.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix='tamanitomo-preview-'))
    # A plain kill must still remove the synthetic data.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        root, c = seed(tmp)
        if a.mock_provider:
            sys.path.insert(0, str(ROOT / 'tests'))
            from mock_provider import MockProvider
            provider = MockProvider().__enter__()
            (c.home / 'config.yaml').write_text(provider.hermes_config())
            (c.home / '.env').write_text(f'MOCK_PROVIDER_KEY={provider.token}\n')
            print(f'Mock provider: {provider.url} (scenario = model name)', flush=True)
        os.environ['COMPANION_HERMES_COMMAND'] = json.dumps([sys.executable, str(ROOT / 'tests/fake_hermes.py')])
        from kit.app.server import build
        import uvicorn
        token = secrets.token_urlsafe(18)
        options = None
        if a.persistent_chat:
            import threading
            from kit.app import chat_send_routes as csr
            from tests.phase1b_c1 import harness as h
            rowan = seed_persistent_chat(root, c)
            stream_replies([c.home, rowan.home], threading.Event())
            options = csr.Options(executor=lambda rt, home: h.fake_executor(home), client=True)
        app = build(root, token=token, state_dir=tmp / 'state', chat_sends=options)
        print(f'Synthetic workspace: http://127.0.0.1:{a.port}/  token: {token}', flush=True)
        if a.persistent_chat:
            print(f'Persistent Chat: http://127.0.0.1:{a.port}/?installation=existing&profile=nova&token={token}#chat'
                  '  (keyed sends ON for this synthetic server only; Ctrl-C stops it)', flush=True)
        print(f'Data: {tmp} ({"kept" if a.keep else "removed on exit"})', flush=True)
        uvicorn.run(app, host='127.0.0.1', port=a.port, log_level='warning')
    finally:
        if not a.keep: shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
