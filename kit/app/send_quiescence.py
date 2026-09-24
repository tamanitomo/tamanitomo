"""One quiescence contract for the Phase 1B managed execution (C1 core).

NOT ACTIVATED. Used by kit/app/chat_sends.py for lease release, explicit reset,
retention and the installation-mutation check -- the same function everywhere
(review R3 5.1). Standard library only.

A managed execution is QUIESCENT only when BOTH hold (PHASE1B_DESIGN.md 4.5):
  (a) the executor's lock is acquired through the identity probe: opened without
      creating it, locked non-blocking, fstat(fd) == the recorded identity ==
      stat(path), AND the file still holds the random nonce the executor wrote into
      it at S1. (st_dev, st_ino) alone is not an identity over time: ext4 reused
      the inode number of an unlinked lock file for its recreation on CI;
  (b) the executor's process group is demonstrably empty.

Anything short of that is `live` (the lock is busy, or a process is still in the
group) or `unproven`. In particular an INCOMPLETE observation is never an empty
group: a process whose /proc entry cannot be read for any reason other than "it
is gone" (permission, I/O, a parse failure), an unreadable /proc, a /proc
mounted with hidepid, or a platform with no supported enumeration all make (b)
unproven. Only a process that is demonstrably gone (ENOENT/ESRCH) is skipped.
(The C0 prototype caught every OSError and returned [] -- the reviewer's probe
showed one unreadable process read as an empty group.)

Stated boundary: a process that leaves the group (setsid/setpgid) is outside it
and is neither contained nor detected (O-10). Supported platform: Linux only.
"""
from __future__ import annotations

import dataclasses
import errno
import json
import os
import signal
import sys
from pathlib import Path

from . import send_protocol as sp

PROC = '/proc'          # module attribute so a test can point it at a synthetic tree
GONE = (errno.ENOENT, errno.ESRCH)


@dataclasses.dataclass(frozen=True)
class Observation:
    state: str                      # 'quiescent' | 'live' | 'unproven'
    reason: str
    members: tuple = ()

    @property
    def quiescent(self):
        return self.state == 'quiescent'


def platform_supported():
    """(True, '') when this host has the supervision this module can observe."""
    if not sys.platform.startswith('linux'):
        return False, f'process supervision is not established on {sys.platform}'
    if sp.fcntl is None:
        return False, 'advisory file locks are unavailable'
    hidden = proc_hidepid()
    if hidden is None:
        return False, f'{PROC} cannot be inspected'
    if hidden:
        return False, f'{PROC} is mounted with hidepid; process groups cannot be fully observed'
    return True, ''


def proc_hidepid():
    """True when /proc hides processes, False when not, None when that cannot be read."""
    try:
        text = Path(PROC, 'self', 'mountinfo').read_text()
    except OSError:
        return None
    for line in text.splitlines():
        parts = line.split(' - ')
        if len(parts) != 2:
            continue
        left, right = parts[0].split(), parts[1].split()
        if len(left) >= 5 and left[4] == '/proc' and right and right[0] == 'proc':
            options = right[2].split(',') if len(right) > 2 else []
            return any(o.startswith('hidepid=') and o not in ('hidepid=0', 'hidepid=off') for o in options)
    return False


def probe_lock(path, recorded, nonce=None):
    """(state, reason) for the executor lock alone: 'acquired' | 'live' | 'unproven'.
    `nonce` is the executor's recorded lock nonce; None skips that check (tools only)."""
    if sp.fcntl is None:
        return 'unproven', 'lock_unsupported'
    try:
        fd = sp.open_lock_file(path, create=False)          # never O_CREAT
    except OSError as exc:
        return 'unproven', 'lock_missing' if exc.errno == errno.ENOENT else 'lock_unopenable'
    try:
        try:
            sp.fcntl.flock(fd, sp.fcntl.LOCK_EX | sp.fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                return 'live', 'executor_lock_held'
            return 'unproven', 'lock_unlockable'
        held = os.fstat(fd)
        try:
            now = os.stat(path, follow_symlinks=False)
        except OSError:
            return 'unproven', 'lock_replaced'
        if recorded is None:
            return 'unproven', 'lock_identity_unknown'
        ident = (held.st_dev, held.st_ino)
        if ident != tuple(recorded) or (now.st_dev, now.st_ino) != tuple(recorded):
            return 'unproven', 'lock_replaced'
        if nonce is not None:
            try:
                content = json.loads(os.pread(fd, 65536, 0) or b'null')
            except (OSError, ValueError):
                content = None
            if not isinstance(content, dict) or content.get('lock_nonce') != nonce or not nonce:
                return 'unproven', 'lock_replaced'
        return 'acquired', 'executor_lock_acquired'
    finally:
        os.close(fd)


def group_members(pgid):
    """(members, complete, reason). `complete` is False whenever any process could not
    be inspected; a caller must then treat the group as unproven, never as empty."""
    ok, why = platform_supported()
    if not ok:
        return (), False, 'group_enumeration_unsupported'
    try:
        entries = os.listdir(PROC)
    except OSError:
        return (), False, 'proc_unreadable'
    members, complete, reason = [], True, 'group_enumerated'
    for name in entries:
        if not name.isdigit():
            continue
        try:
            with open(os.path.join(PROC, name, 'stat'), 'rb') as handle:
                stat = handle.read().decode('ascii', 'replace')
        except OSError as exc:
            if exc.errno in GONE:
                continue                                   # demonstrably gone
            complete, reason = False, 'process_uninspectable'
            continue
        try:
            fields = stat[stat.rindex(')') + 2:].split()
            state, group = fields[0], int(fields[2])
        except (ValueError, IndexError):
            complete, reason = False, 'process_unparseable'
            continue
        if state not in ('Z', 'X') and group == pgid:
            members.append(int(name))
    return tuple(sorted(members)), complete, reason


def observe(lock_path, recorded_ident, pgid, nonce):
    """The contract. Used for lease release, reset, retention and installation mutations."""
    lock, why = probe_lock(lock_path, recorded_ident, nonce)
    if lock == 'live':
        return Observation('live', why)
    if lock != 'acquired':
        return Observation('unproven', why)
    if not isinstance(pgid, int) or pgid <= 1:
        return Observation('unproven', 'group_unknown')
    members, complete, reason = group_members(pgid)
    if members:
        return Observation('live', 'group_not_empty', members)
    if not complete:
        return Observation('unproven', reason)
    return Observation('quiescent', 'lock_acquired_group_empty')


def kill_group(pgid, executor_pid=None, executor_start=None):
    """SIGKILL the managed group. When the executor is still the group's leader and
    alive, its start time must match the recorded one first (PID reuse). Returns a
    fixed reason code. Residual race between the check and killpg is stated."""
    if not isinstance(pgid, int) or pgid <= 1:
        return 'kill_refused_no_group'
    if executor_pid and executor_start is not None:
        current = sp.start_time(executor_pid, PROC)
        if current is not None and current != executor_start:
            return 'kill_refused_identity_mismatch'
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return 'kill_no_such_group'
    except PermissionError:
        return 'kill_not_permitted'
    return 'kill_sent'
