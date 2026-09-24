"""C0 HARNESS / PROTOTYPE of executor liveness probes (POSIX) -- not production code.

* `naive_probe`     -- revision 2, section 4.5: quiescent iff the executor lock at
                       the path can be acquired.
* `identity_probe`  -- amended: the executor records the lock file's (st_dev,
                       st_ino) in executor_started; the probe opens the path WITHOUT
                       creating it, acquires, and requires fstat(fd) == the recorded
                       identity == stat(path). Missing or replaced path -> `unproven`.
* `group_members`   -- amended quiescence also requires that no process remains in
                       the executor's process group (Linux: /proc/<pid>/stat field 5).
                       A process that left the group (setsid) is outside this
                       boundary; that is stated, not hidden.
"""
from __future__ import annotations

import fcntl
import os
import pathlib


def naive_probe(path):
    with open(path, 'a+b') as handle:                    # creates the file if it is missing
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'live'
        return 'quiescent'


def identity_probe(path, recorded):
    try:
        fd = os.open(path, os.O_RDWR)                   # never O_CREAT
    except FileNotFoundError:
        return 'unproven'
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'live'
        held = os.fstat(fd)
        try:
            now = os.stat(path)
        except FileNotFoundError:
            return 'unproven'
        if (held.st_dev, held.st_ino) != tuple(recorded) or (now.st_dev, now.st_ino) != tuple(recorded):
            return 'unproven'
        return 'quiescent'
    finally:
        os.close(fd)


def group_members(pgid):
    """Live, non-zombie processes whose process group is `pgid` (Linux /proc)."""
    out = []
    for entry in pathlib.Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / 'stat').read_text()
        except OSError:
            continue
        fields = stat[stat.rindex(')') + 2:].split()
        if fields[0] != 'Z' and int(fields[2]) == pgid:
            out.append(int(entry.name))
    return out
