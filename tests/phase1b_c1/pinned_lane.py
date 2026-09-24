"""Locate and VERIFY the pinned Hermes for the C1 integration tests (tests only).

Configuration is read only here, and only by tests:
    TAMANITOMO_C1_HERMES_SRC      a tree exported by tools/pinned_hermes_lane.py
    TAMANITOMO_C1_HERMES_PYTHON   an interpreter with Hermes's dependencies
    TAMANITOMO_C1_REQUIRE_PINNED  '1' in the designated lane: a missing or mismatched
                                  prerequisite is a FAILURE, never a skip
    TAMANITOMO_C1_EVIDENCE        where per-test synthetic evidence is written

Verification does not trust a marker file: every file listed in the tree's
.pinned-manifest.json (written from `git ls-tree` of the pinned commit) is re-hashed
as a git blob and compared, and a file not in the listing fails verification.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import pathlib
import sys

PINNED = '0e9fc2cc152b4a4d9fd736f107412ace2a0c2555'


class PrerequisiteMissing(AssertionError):
    """Raised instead of skipping when the lane requires the pinned Hermes."""


def required():
    return os.environ.get('TAMANITOMO_C1_REQUIRE_PINNED') == '1'


def _blob(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


@functools.lru_cache(maxsize=1)
def locate():
    """((src, python), None) when verified, else (None, reason)."""
    src, python = os.environ.get('TAMANITOMO_C1_HERMES_SRC'), os.environ.get('TAMANITOMO_C1_HERMES_PYTHON')
    if not src or not python:
        return None, 'pinned Hermes not configured (TAMANITOMO_C1_HERMES_SRC / TAMANITOMO_C1_HERMES_PYTHON)'
    src = pathlib.Path(src).resolve()
    if not pathlib.Path(python).is_file():
        return None, f'interpreter {python} does not exist'
    try:
        manifest = json.loads((src / '.pinned-manifest.json').read_text())
    except (OSError, ValueError):
        return None, f'{src} has no readable .pinned-manifest.json (export it with tools/pinned_hermes_lane.py)'
    if manifest.get('commit') != PINNED:
        return None, f"{src} is {manifest.get('commit')!r}, not {PINNED}"
    files = manifest.get('files') or {}
    for rel, meta in files.items():
        path = src / rel
        if meta['mode'] in ('120000', '160000'):
            continue
        try:
            if _blob(path.read_bytes()) != meta['sha']:
                return None, f'{rel} differs from {PINNED[:10]}'
        except OSError:
            return None, f'{rel} is missing from the pinned tree'
    extra = [p for p in src.rglob('*.py') if str(p.relative_to(src)) not in files]
    if extra:
        return None, f'{len(extra)} Python file(s) in the tree are not in {PINNED[:10]}, e.g. {extra[0]}'
    return (src, python), None


def pinned_or_skip(test):
    """For setUp/setUpClass: returns (src, python), skips, or fails in the required lane."""
    pin, why = locate()
    if pin is None:
        if required():
            raise PrerequisiteMissing(why)
        test.skipTest(why)
    return pin


def evidence(name, payload):
    target = os.environ.get('TAMANITOMO_C1_EVIDENCE')
    if target:
        path = pathlib.Path(target) / f'{name}.json'
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))


def executor_env(src, home):
    return {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': str(home), 'HERMES_HOME': str(home),
            'PYTHONPATH': str(src), 'PYTHONDONTWRITEBYTECODE': '1'}


def synthetic_home(home, provider, scenario):
    """A fresh Hermes home that knows only the local mock provider (fallbacks disabled).
    The key is inline: the pinned custom provider did not read `api_key_env` (C0)."""
    (pathlib.Path(home) / 'config.yaml').write_text(provider.hermes_config(scenario).replace(
        '  api_key_env: MOCK_PROVIDER_KEY\n', f'  api_key: {provider.token}\n'))
