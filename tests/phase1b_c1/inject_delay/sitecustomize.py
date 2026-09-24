"""TEST-ONLY: hold an executor between `go` and S1 (tests only; never shipped).

Placed on ONE executor's PYTHONPATH by tests/test_phase1b_c1_core.py. The first os.open of
a path under executors/ (S1, the executor's own lock) writes <dir>/reached and then blocks
until <dir>/release exists. The directory comes from C1_TEST_S1_GATE, read only here.
"""
import os
import time

_gate = os.environ.get('C1_TEST_S1_GATE')
_open = os.open
_done = []


def gated_open(path, *args, **kwargs):
    if _gate and not _done and '/executors/' in str(path):
        _done.append(1)
        with open(os.path.join(_gate, 'reached'), 'w'):
            pass
        while not os.path.exists(os.path.join(_gate, 'release')):
            time.sleep(0.02)
    return _open(path, *args, **kwargs)


os.open = gated_open
