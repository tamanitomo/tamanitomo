#!/usr/bin/env python3
"""The designated pinned-Hermes verification lane for Phase 1B C1 (review R3 5.3).

    python tools/pinned_hermes_lane.py --checkout <hermes-agent git checkout> \
        --python <interpreter with Hermes's dependencies> --work <empty scratch dir>

What it does, and why each step exists:
  1. Exports exactly PINNED's committed blobs from the checkout (`git ls-tree` + `git
     cat-file`; untracked or modified files in the checkout are therefore excluded).
  2. VERIFIES the export instead of trusting a marker: every exported file's git blob
     hash must equal the blob `git ls-tree -r PINNED` lists for it, and no file may be
     missing or extra. The per-file list is written to <src>/.pinned-manifest.json so the
     tests re-verify the same tree before relying on it.
  3. Records the interpreter (path, version, SQLite), its installed distributions and
     versions, and the import origin of every Hermes module the executor uses. An import
     that resolves outside the verified tree fails the lane.
  4. Runs the C1 pinned tests with TAMANITOMO_C1_REQUIRE_PINNED=1: a missing or
     mismatched prerequisite FAILS instead of skipping, and the lane then fails if any
     test was skipped, failed or errored, or if a required test id did not run.
  5. Leaves inspectable synthetic evidence in <work>/evidence/ (lane.json, environment.json,
     junit.xml, per-test JSON). Homes are synthetic; the provider is tests/mock_provider.py.

Never reads a live profile or credential: every Hermes process gets a fresh HOME and
HERMES_HOME, PATH=/usr/bin:/bin, a local mock provider with fallbacks disabled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
PINNED = '0e9fc2cc152b4a4d9fd736f107412ace2a0c2555'
TESTS = ['tests/test_phase1b_c1_pinned.py']
REQUIRED_PREFIX = 'tests.test_phase1b_c1_pinned'


def blob_sha(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def git(checkout, *args, binary=False):
    out = subprocess.run(['git', '-C', str(checkout), *args], check=True, capture_output=True)
    return out.stdout if binary else out.stdout.decode()


def export(checkout, src):
    """Write every blob of PINNED's tree to `src`, byte for byte. (`git archive` applies
    .gitattributes eol conversion, so its output is not the committed blobs.)"""
    listing = git(checkout, 'ls-tree', '-r', '-z', '--full-tree', PINNED, binary=True).split(b'\0')
    files = {}
    for entry in filter(None, listing):
        meta, path = entry.split(b'\t', 1)
        mode, kind, sha = meta.decode().split()
        if kind == 'blob':
            files[path.decode()] = {'mode': mode, 'sha': sha}
    names = list(files)
    batch = subprocess.run(['git', '-C', str(checkout), 'cat-file', '--batch'],
                           input=''.join(files[n]['sha'] + '\n' for n in names).encode(),
                           capture_output=True, check=True).stdout
    view = memoryview(batch)
    offset = 0
    for name in names:
        header_end = batch.index(b'\n', offset)
        sha, kind, size = batch[offset:header_end].decode().split()
        assert sha == files[name]['sha'] and kind == 'blob', (name, sha, kind)
        data = bytes(view[header_end + 1:header_end + 1 + int(size)])
        offset = header_end + 1 + int(size) + 1
        target = src / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if files[name]['mode'] == '120000':
            os.symlink(data.decode(), target)
        else:
            target.write_bytes(data)
            if files[name]['mode'] == '100755':
                target.chmod(0o755)
    return files, git(checkout, 'rev-parse', PINNED + '^{tree}').strip()


def verify_tree(src, files):
    """[] when the tree on disk is exactly `files`; otherwise the discrepancies."""
    problems = []
    for rel, meta in files.items():
        path = src / rel
        if meta['mode'] == '120000':
            if not path.is_symlink() or blob_sha(os.readlink(path).encode()) != meta['sha']:
                problems.append(('symlink', rel))
            continue
        if meta['mode'] == '160000':
            continue                     # submodule: not part of the archive
        try:
            if blob_sha(path.read_bytes()) != meta['sha']:
                problems.append(('content', rel))
        except OSError:
            problems.append(('missing', rel))
    on_disk = {str(p.relative_to(src)) for p in src.rglob('*') if (p.is_file() or p.is_symlink())}
    extra = on_disk - set(files) - {'.pinned-manifest.json'}
    problems += [('extra', rel) for rel in sorted(extra)]
    return problems


def environment(python, src):
    probe = r'''
import json, sqlite3, sys, importlib.metadata as md
out = {"executable": sys.executable, "version": sys.version, "sqlite": sqlite3.sqlite_version,
       "prefix": sys.prefix, "distributions": sorted({(d.metadata["Name"] or "?") + "==" + d.version
                                                      for d in md.distributions()})}
origins = {}
for name in ("hermes_state", "cli", "hermes_cli.main", "hermes_state_messages", "run_agent"):
    try:
        mod = __import__(name, fromlist=["x"])
        origins[name] = getattr(mod, "__file__", None)
    except Exception as exc:
        origins[name] = "IMPORT FAILED: " + type(exc).__name__
out["import_origins"] = origins
print(json.dumps(out))
'''
    with tempfile.TemporaryDirectory(prefix='lane-home-') as home:
        env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': home, 'HERMES_HOME': home,
               'PYTHONPATH': str(src), 'PYTHONDONTWRITEBYTECODE': '1'}
        proc = subprocess.run([python, '-c', probe], env=env, cwd=home, capture_output=True, text=True, timeout=300)
    if proc.returncode:
        raise SystemExit('interpreter probe failed:\n' + proc.stderr[-3000:])
    return json.loads(proc.stdout.strip().splitlines()[-1])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--checkout', required=True)
    ap.add_argument('--python', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('pytest_args', nargs='*')
    args = ap.parse_args(argv)
    work = pathlib.Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    if any(work.iterdir()):
        raise SystemExit(f'{work} is not empty')
    src, evidence = work / 'hermes-src', work / 'evidence'
    src.mkdir()
    evidence.mkdir()
    lane = {'pinned': PINNED, 'started': time.time(), 'host': platform.platform(),
            'app_commit': subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True,
                                         text=True).stdout.strip(),
            'app_dirty': bool(subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--', 'kit', 'tests',
                                              'tools'], capture_output=True, text=True).stdout.strip()),
            'app_python': sys.version}
    files, tree = export(args.checkout, src)
    problems = verify_tree(src, files)
    lane.update(tree=tree, files=len(files), tree_problems=problems[:50])
    if problems:
        (evidence / 'lane.json').write_text(json.dumps(lane, indent=2))
        raise SystemExit(f'exported tree does not match {PINNED}: {problems[:5]}')
    (src / '.pinned-manifest.json').write_text(json.dumps({'commit': PINNED, 'tree': tree, 'files': files}))
    env_info = environment(args.python, src)
    (evidence / 'environment.json').write_text(json.dumps(env_info, indent=2))
    outside = {k: v for k, v in env_info['import_origins'].items()
               if not (isinstance(v, str) and pathlib.Path(v).resolve().is_relative_to(src))}
    lane['import_origins_outside_tree'] = outside
    if outside:
        (evidence / 'lane.json').write_text(json.dumps(lane, indent=2))
        raise SystemExit(f'Hermes modules imported from outside the verified tree: {outside}')
    env = dict(os.environ, TAMANITOMO_C1_HERMES_SRC=str(src), TAMANITOMO_C1_HERMES_PYTHON=args.python,
               TAMANITOMO_C1_REQUIRE_PINNED='1', TAMANITOMO_C1_EVIDENCE=str(evidence))
    junit = evidence / 'junit.xml'
    cmd = [sys.executable, '-m', 'pytest', '-q', '-rs', f'--junitxml={junit}', *TESTS, *args.pytest_args]
    lane['command'] = cmd
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env)
    cases = []
    if junit.exists():
        for case in ET.parse(junit).getroot().iter('testcase'):
            status = 'passed'
            for tag in ('failure', 'error', 'skipped'):
                if case.find(tag) is not None:
                    status = tag
            cases.append({'id': f"{case.get('classname')}::{case.get('name')}", 'status': status,
                          'seconds': float(case.get('time') or 0)})
    lane.update(pytest_exit=proc.returncode, cases=cases, finished=time.time())
    bad = [c for c in cases if c['status'] != 'passed']
    required = [c for c in cases if c['id'].startswith(REQUIRED_PREFIX)]
    lane['verdict'] = 'pass' if proc.returncode == 0 and cases and not bad and required else 'fail'
    (evidence / 'lane.json').write_text(json.dumps(lane, indent=2))
    print(json.dumps({'verdict': lane['verdict'], 'cases': len(cases), 'not_passed': bad,
                      'evidence': str(evidence)}, indent=2))
    return 0 if lane['verdict'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
