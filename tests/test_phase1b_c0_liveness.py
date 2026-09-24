"""Phase 1B C0 evidence for B1: what the executor lock proves, descendants, lock
paths, and controller death. Real processes and real flock on this host.

HARNESS / PROTOTYPE (tests/phase1b_c0/liveness_proto.py). Linux only where
/proc is used. Windows job objects (O-8) and Termux (O-9) are NOT exercised
here; see Phase1B_C0_Results.md.
"""
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'phase1b_c0'))
import liveness_proto as proto  # noqa: E402

LINUX = sys.platform.startswith('linux')

# The stand-in executor: takes its lock, records identity, optionally spawns a
# descendant (in its group, or escaping it with setsid), then exits or waits.
EXECUTOR = textwrap.dedent('''
    import fcntl, json, os, subprocess, sys, time
    lock, report, child, linger = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    st = os.fstat(fd)
    pid = None
    if child != 'none':
        code = 'import os,time\\n' + ('os.setsid()\\n' if child == 'escape' else '') + 'time.sleep(30)'
        pid = subprocess.Popen([sys.executable, '-c', code], close_fds=True).pid
    with open(report, 'w') as f:
        json.dump({'pid': os.getpid(), 'pgid': os.getpgid(0), 'ident': [st.st_dev, st.st_ino], 'child': pid}, f)
    time.sleep(linger)
''')


@unittest.skipUnless(LINUX, 'uses /proc and flock; only Linux was available for C0')
class ExecutorLock(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        self.lock = self.dir / 'executors' / 'snd_x.lock'
        self.lock.parent.mkdir()
        self.script = self.dir / 'executor.py'
        self.script.write_text(EXECUTOR)
        self.children = []

    def tearDown(self):
        for pid in self.children:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def start(self, child='none', linger=0.0):
        report = self.dir / 'report.json'
        proc = subprocess.Popen([sys.executable, str(self.script), str(self.lock), str(report), child, str(linger)],
                                start_new_session=True, close_fds=True)
        deadline = time.monotonic() + 10
        while not report.exists() or not report.read_text():
            self.assertLess(time.monotonic(), deadline);time.sleep(0.02)
        time.sleep(0.05)
        info = json.loads(report.read_text())
        if info['child']:
            self.children.append(info['child'])
        return proc, info

    def test_lock_release_proves_the_executor_gone_not_its_descendants(self):
        proc, info = self.start(child='group')
        proc.wait(10)
        self.assertEqual(proto.naive_probe(self.lock), 'quiescent')          # lock free...
        self.assertIn(info['child'], proto.group_members(info['pgid']))      # ...descendant alive
        os.killpg(info['pgid'], signal.SIGKILL)
        deadline = time.monotonic() + 5
        while proto.group_members(info['pgid']) and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(proto.group_members(info['pgid']), [])

    def test_a_descendant_that_leaves_the_group_is_outside_the_boundary(self):
        proc, info = self.start(child='escape')
        proc.wait(10)
        try:
            os.killpg(info['pgid'], signal.SIGKILL)                          # the kill-tree step
        except ProcessLookupError:
            pass                                                             # nothing left in the group
        time.sleep(0.1)
        self.assertEqual(proto.group_members(info['pgid']), [])              # the group looks empty
        os.kill(info['child'], 0)                                            # but the escaped process lives

    def test_descendants_do_not_inherit_the_lock(self):
        proc, info = self.start(child='group', linger=0)
        proc.wait(10)
        self.assertEqual(proto.identity_probe(self.lock, info['ident']), 'quiescent')

    def test_a_replaced_lock_path_is_not_proof(self):
        proc, info = self.start(linger=30)
        self.children.append(proc.pid)
        self.assertEqual(proto.naive_probe(self.lock), 'live')
        os.unlink(self.lock)                                                 # routine cleanup / reset
        self.assertEqual(proto.identity_probe(self.lock, info['ident']), 'unproven')
        self.assertEqual(proto.naive_probe(self.lock), 'quiescent')          # recreated: a false proof
        self.assertEqual(proto.identity_probe(self.lock, info['ident']), 'unproven')
        proc.kill();proc.wait(10)

    def test_identity_probe_on_a_live_and_an_ended_executor(self):
        proc, info = self.start(linger=30)
        self.children.append(proc.pid)
        self.assertEqual(proto.identity_probe(self.lock, info['ident']), 'live')
        proc.kill();proc.wait(10)
        self.assertEqual(proto.identity_probe(self.lock, info['ident']), 'quiescent')

    def test_controller_death_leaves_a_posix_executor_running(self):
        controller = textwrap.dedent(f'''
            import subprocess, sys, time
            subprocess.Popen([sys.executable, {str(self.script)!r}, {str(self.lock)!r},
                              {str(self.dir / "report.json")!r}, "none", "3"],
                             start_new_session=True, close_fds=True)
            time.sleep(30)
        ''')
        ctl = subprocess.Popen([sys.executable, '-c', controller])
        deadline = time.monotonic() + 10
        while not (self.dir / 'report.json').exists() or not (self.dir / 'report.json').read_text():
            self.assertLess(time.monotonic(), deadline);time.sleep(0.02)
        info = json.loads((self.dir / 'report.json').read_text())
        self.children.append(info['pid'])
        ctl.kill();ctl.wait(10)
        self.assertEqual(proto.identity_probe(self.lock, info['ident']), 'live')   # E continues
        deadline = time.monotonic() + 10
        while proto.identity_probe(self.lock, info['ident']) == 'live' and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(proto.identity_probe(self.lock, info['ident']), 'quiescent')
