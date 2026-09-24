#!/usr/bin/env python3
"""Serve the workspace against a synthetic companion, for looking at changes in
a real browser without touching anyone's data.

Everything lives in a temporary directory that is removed on exit: a Hermes
root, a vault, one companion ("Nova") and one human ("Robin"), and ledgers
seeded with invented memories. The access token is random per run and is
printed once. Hermes is replaced by tests/fake_hermes.py, so nothing reaches a
model or a messaging platform.

    python tools/preview_fixture.py [--port 38500] [--keep]

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
    return root, c


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=38500)
    p.add_argument('--keep', action='store_true', help='leave the temporary directory behind')
    a = p.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix='tamanitomo-preview-'))
    # A plain kill must still remove the synthetic data.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        root, _ = seed(tmp)
        os.environ['COMPANION_HERMES_COMMAND'] = json.dumps([sys.executable, str(ROOT / 'tests/fake_hermes.py')])
        from kit.app.server import build
        import uvicorn
        token = secrets.token_urlsafe(18)
        app = build(root, token=token, state_dir=tmp / 'state')
        print(f'Synthetic workspace: http://127.0.0.1:{a.port}/  token: {token}', flush=True)
        print(f'Data: {tmp} ({"kept" if a.keep else "removed on exit"})', flush=True)
        uvicorn.run(app, host='127.0.0.1', port=a.port, log_level='warning')
    finally:
        if not a.keep: shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
