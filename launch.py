#!/usr/bin/env python3
"""Dependency bootstrap. Only the Python standard library is required to start."""
from __future__ import annotations
import hashlib
import contextlib
import os
from pathlib import Path
import subprocess
import sys
import venv
import time

ROOT=Path(__file__).resolve().parent

@contextlib.contextmanager
def setup_lock():
    """Serialize first launches so two windows cannot install into one venv."""
    with (ROOT/'.bootstrap.lock').open('a+b') as handle:
        handle.write(b'0');handle.flush();handle.seek(0)
        deadline=time.monotonic()+600
        while True:
            try:
                if os.name=='nt':
                    import msvcrt
                    handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>=deadline:raise OSError('Another launcher is still preparing dependencies. Try again after it finishes.')
                time.sleep(.2)
        try:yield
        finally:
            if os.name=='nt':
                handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)

def bootstrap(args):
    if sys.version_info<(3,11):
        raise SystemExit('Tamanitomo needs Python 3.11+. Use the tamanitomo launcher to provision Python automatically.')
    from update_release import apply_pending
    with setup_lock():apply_pending(ROOT)
    directory=ROOT/'.venv'
    python=directory/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    with setup_lock():
        if not python.exists():
            print('Preparing the tamanitomo environment…',flush=True)
            venv.EnvBuilder(with_pip=True).create(directory)
        fingerprint=hashlib.sha256((ROOT/'requirements.txt').read_bytes()).hexdigest()
        stamp=directory/'.tamanitomo-requirements'
        old_stamp=directory/'.companion-requirements'
        if not stamp.exists() and old_stamp.exists():
            try:old_stamp.replace(stamp)
            except OSError:stamp=old_stamp
        if not stamp.exists() or stamp.read_text().strip()!=fingerprint:
            print('Installing tamanitomo dependencies…',flush=True)
            subprocess.run([str(python),'-m','pip','install','-r',str(ROOT/'requirements.txt')],check=True)
            stamp.write_text(fingerprint+'\n')
    command=[str(python),str(ROOT/'bin/tamanitomo'),*(args or ['app'])]
    # subprocess preserves Windows Ctrl-C handling; POSIX exec avoids an extra process.
    if os.name=='nt':return subprocess.call(command)
    os.execv(str(python),command)

if __name__=='__main__':
    try:sys.exit(bootstrap(sys.argv[1:]))
    except (OSError,subprocess.CalledProcessError) as exc:
        print(f'Setup could not finish: {exc}\nRun the launcher again to retry.',file=sys.stderr);sys.exit(1)
