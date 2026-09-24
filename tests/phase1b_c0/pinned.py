"""C0 HARNESS: locate the pinned Hermes and run harness scripts under its interpreter.

Test-only configuration (read by tests, never by shipped code):
    TAMANITOMO_C0_HERMES_SRC     a tree of hermes-agent at exactly PINNED, containing
                                 `.c0-revision` with the full hash (see Phase1B_C0_Results.md)
    TAMANITOMO_C0_HERMES_PYTHON  an interpreter with Hermes's dependencies installed

When either is missing the Hermes-backed C0 tests SKIP with that reason; they
never fall back to an installed or live Hermes.
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
PINNED = '0e9fc2cc152b4a4d9fd736f107412ace2a0c2555'


def hermes():
    """(src, python) or (None, reason)."""
    src, python = os.environ.get('TAMANITOMO_C0_HERMES_SRC'), os.environ.get('TAMANITOMO_C0_HERMES_PYTHON')
    if not src or not python:
        return None, 'pinned Hermes not configured (TAMANITOMO_C0_HERMES_SRC / TAMANITOMO_C0_HERMES_PYTHON)'
    marker = pathlib.Path(src) / '.c0-revision'
    if not marker.exists() or marker.read_text().strip() != PINNED:
        return None, f'{src} is not marked as Hermes {PINNED[:10]}'
    return (pathlib.Path(src), python), None


def env(src, home=None):
    out = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONPATH': str(src), 'PYTHONDONTWRITEBYTECODE': '1'}
    if home:
        out.update({'HOME': str(home), 'HERMES_HOME': str(home)})
    return out


def seam(pin, mode, scenario):
    src, python = pin
    with tempfile.TemporaryDirectory(prefix='c0-seam-') as work:
        proc = subprocess.run([python, str(HERE / 'seam_scenarios.py'), mode, scenario, work],
                              env=env(src, work), capture_output=True, text=True, timeout=120)
        if proc.returncode:
            raise AssertionError(f'seam driver failed: {proc.stderr[-2000:]}')
        return json.loads(proc.stdout.strip().splitlines()[-1])


def synthetic_home(root, provider, scenario):
    home = pathlib.Path(root) / 'home'
    home.mkdir()
    # Inline synthetic key: the pinned custom provider did not read `api_key_env` from the
    # model section (observed: HTTP 401 from the mock). The key is random per run.
    (home / 'config.yaml').write_text(provider.hermes_config(scenario).replace(
        '  api_key_env: MOCK_PROVIDER_KEY\n', f'  api_key: {provider.token}\n'))
    return home


def turn(pin, home, receipts, report, message='A synthetic owner message', resume=None,
         interrupt_after=None, recorder='commit', timeout=180):
    src, python = pin
    argv = ['chat', '--quiet', '--oneshot', '-q', message] + (['--resume', resume] if resume else [])
    opts = [str(report), str(receipts), '--recorder', recorder]
    if interrupt_after:
        opts += ['--interrupt-after-deltas', str(interrupt_after)]
    started = __import__('time').time()
    proc = subprocess.run([python, str(HERE / 'turn_driver.py'), *opts, '--', *argv],
                          env=env(src, home), cwd=str(home), capture_output=True, text=True, timeout=timeout)
    out = json.loads(pathlib.Path(report).read_text()) if pathlib.Path(report).exists() else {}
    out['process_exit'] = proc.returncode
    out['launched_at'] = started
    return out


def rows(home):
    con = sqlite3.connect(str(pathlib.Path(home) / 'state.db'))
    try:
        return [{'row_id': r[0], 'session_id': r[1], 'role': r[2], 'active': r[3], 'finish_reason': r[4],
                 'tool_calls': bool(r[5])}
                for r in con.execute('SELECT id, session_id, role, active, finish_reason, tool_calls '
                                     'FROM messages ORDER BY id')]
    finally:
        con.close()


def session_ids(home):
    con = sqlite3.connect(str(pathlib.Path(home) / 'state.db'))
    try:
        return [r[0] for r in con.execute('SELECT id FROM sessions ORDER BY started_at')]
    finally:
        con.close()


def facts(receipts):
    sys.path.insert(0, str(HERE))
    import receipt_probe
    return receipt_probe.read_facts(receipts)
