"""C0 HARNESS / PROTOTYPE of the section 7 attempt protocol -- not production code.

Uses the REAL outbox file format (companion_outbox + companion_self._append with a
guard) and the REAL daily-slot ledger (companion_outreach.claim), so slot
accounting is measured with production code. The attempt protocol itself is the
prototype: production companion_dispatch.py is unchanged.

Two recovery rules are implemented so a test can compare them:

* `rev2`    -- PHASE1B_DESIGN.md revision 2, section 7.3: an abandoned
               `dispatching` entry goes back to `queued` ("no slot was used").
* `amended` -- a `reserving_slot` phase is appended BEFORE outreach.claim, and the
               charge row carries the attempt id (in `reason`, which the pinned
               outreach ledger already stores). Recovery resolves `reserving_slot`
               by looking for that attempt's charge row under the outreach lock:
               found -> `failed, not_dispatched` (slot consumed, no refund);
               absent with a readable ledger -> `queued` (definitely not charged);
               ledger unreadable -> `reservation_unresolved` (not dispatched, slot
               consumption unknown; no requeue, no refund).

`Crash` is raised at a named boundary to stand in for process death. The run
lock is a real flock and is released when the run's `with` block unwinds, as the
OS would release it.
"""
from __future__ import annotations

import contextlib
import json
import pathlib
import secrets

import companion_outbox as outbox
import companion_outreach as outreach
import companion_self as slf
from companion_platform import file_lock

BOUNDARIES = ('after_claim', 'after_reservation_intent', 'after_charge', 'after_slot_marker', 'after_sending_marker')
OUTCOMES = {'sent', 'failed', 'unknown', 'withheld', 'expired'}


class Crash(BaseException):
    pass


class RunLockBusy(Exception):
    pass


def _rows(c):
    return list(slf._read(outbox.path_for(c)))


def _last(c, ident):
    last = None
    for row in _rows(c):
        if row.get('id') == ident and row.get('kind') == 'outbox_update':
            last = row
    return last


def _status(c, ident):
    return next(e['status'] for e in outbox.fold(c) if e['id'] == ident)


def _update(c, ident, status, attempt, run_id, expect, **extra):
    """Guarded append: refused unless the entry's current status is `expect`
    (and, for a later phase, the current attempt is this one)."""
    def guard():
        current = _status(c, ident)
        last = _last(c, ident)
        if current != expect:
            return {'written': False, 'refused': f'status {current}'}
        if expect != 'queued' and (last or {}).get('attempt') != attempt:
            return {'written': False, 'refused': 'different attempt'}
        return None
    row = {'id': ident, 'kind': 'outbox_update', 'status': status, 'attempt': attempt, 'run_id': run_id,
           'detail': '', 'at': '2026-09-10T14:00:00+00:00', **extra}
    return slf._append(outbox.path_for(c), row, dedupe_id=False, guard=guard)


def charges_for(c, attempt):
    """Rows in the outreach ledger that carry this attempt. Raises if unreadable."""
    marker = f'attempt={attempt}'
    found = 0
    with outreach.path(c).open(encoding='utf-8') as f:
        for line in f:
            if line.strip():
                row = json.loads(line)                  # a torn line is unreadable, not absent
                if marker in row.get('reason', ''):
                    found += 1
    return found


@contextlib.contextmanager
def run_lock(c):
    import fcntl
    path = pathlib.Path(c.life) / '.dispatch.run.lock'
    with path.open('a+b') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RunLockBusy('another dispatcher is running')
        yield


def recover(c, rule, run_id):
    """Resolve attempts abandoned by a dispatcher that no longer holds the run lock."""
    resolved = []
    for entry in outbox.fold(c):
        status = entry['status']
        last = _last(c, entry['id'])
        if not last or last.get('run_id') == run_id or status in OUTCOMES or status == 'queued':
            continue
        attempt = last.get('attempt')
        if status == 'dispatching':
            _update(c, entry['id'], 'queued', attempt, run_id, 'dispatching', release_reason='abandoned')
            resolved.append((entry['id'], 'queued'))
        elif status == 'reserving_slot':
            try:
                with file_lock(outreach.path(c).with_suffix('.jsonl.lock')):
                    n = charges_for(c, attempt) if outreach.path(c).exists() else 0
            except (OSError, ValueError):
                _update(c, entry['id'], 'reservation_unresolved', attempt, run_id, 'reserving_slot')
                resolved.append((entry['id'], 'reservation_unresolved'))
                continue
            if n:
                _update(c, entry['id'], 'failed', attempt, run_id, 'reserving_slot', not_dispatched=True)
                resolved.append((entry['id'], 'failed_not_dispatched'))
            else:
                _update(c, entry['id'], 'queued', attempt, run_id, 'reserving_slot', release_reason='abandoned')
                resolved.append((entry['id'], 'queued'))
        elif status == 'slot_reserved':
            _update(c, entry['id'], 'failed', attempt, run_id, 'slot_reserved', not_dispatched=True)
            resolved.append((entry['id'], 'failed_not_dispatched'))
        elif status == 'sending':
            _update(c, entry['id'], 'unknown', attempt, run_id, 'sending')
            resolved.append((entry['id'], 'unknown'))
    return resolved


def run(c, now, deliver, rule='amended', crash_at=None, snapshot=None):
    """One dispatcher run. `deliver(entry) -> (ok, detail)` is the send double.
    `snapshot` lets a test hand in a stale `waiting()` list."""
    run_id = secrets.token_hex(4)
    with run_lock(c):
        recovered = recover(c, rule, run_id)
        entries = snapshot if snapshot is not None else outbox.waiting(c, now)
        for n, entry in enumerate(entries):
            attempt = f'{run_id}:{n}'
            claimed = _update(c, entry['id'], 'dispatching', attempt, run_id, 'queued')
            if claimed.get('refused'):
                return {'recovered': recovered, 'result': 'claim_refused', 'why': claimed['refused']}
            if crash_at == 'after_claim':
                raise Crash
            expect = 'dispatching'
            if rule == 'amended':
                _update(c, entry['id'], 'reserving_slot', attempt, run_id, 'dispatching')
                expect = 'reserving_slot'
                if crash_at == 'after_reservation_intent':
                    raise Crash
            slot = outreach.claim(c, f'outbox attempt={attempt}', now=now)
            if not slot['allowed']:
                _update(c, entry['id'], 'queued', attempt, run_id, expect, release_reason='cap')
                return {'recovered': recovered, 'result': 'cap'}
            if crash_at == 'after_charge':
                raise Crash
            _update(c, entry['id'], 'slot_reserved', attempt, run_id, expect)
            if crash_at == 'after_slot_marker':
                raise Crash
            _update(c, entry['id'], 'sending', attempt, run_id, 'slot_reserved')
            if crash_at == 'after_sending_marker':
                raise Crash
            ok, detail = deliver(entry)
            _update(c, entry['id'], 'sent' if ok else 'unknown', attempt, run_id, 'sending')
            return {'recovered': recovered, 'result': 'sent' if ok else 'unknown'}
        return {'recovered': recovered, 'result': 'idle'}
