"""Phase 1B C3 recovery closure (review of a8b4e52): the client's recovery rules, run in Node.

Runs the reviewer's actual source-executed checks (tests/phase1b_c3/review_a8b4e52/, byte-
identical to the review packet), this closure's additional checks
(tests/phase1b_c3/recovery_unit.cjs), and the reviewer's real-HTTP/ledger witness: the actual
server, send ledger and fake Hermes, with the client executed in Node (no DOM, no browser). The
witness moves only a synthetic ledger, after settlement and an idle worker.

Node is required with TAMANITOMO_REQUIRE_NODE=1 (as in CI); otherwise a missing Node skips.
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from tests.test_reliability import node_or_skip     # noqa: E402

HERE = ROOT / 'tests/phase1b_c3'


class RecoveryNode(unittest.TestCase):
    def run_cases(self, script):
        node = node_or_skip(self, 'Node is needed for the C3 recovery checks')
        done = subprocess.run([node, str(script), str(ROOT)], capture_output=True, text=True, timeout=120)
        self.assertTrue(done.stdout.strip(), done.stderr)
        result = json.loads(done.stdout)
        for case in result['cases']:
            with self.subTest(case['name']):
                self.assertEqual(case['status'], 'pass', case.get('assertion'))
        self.assertEqual(done.returncode, 0, done.stderr)
        return result

    def test_reviewer_unit_checks(self):
        self.assertEqual(self.run_cases(HERE / 'review_a8b4e52/test_c3_recovery_unit.cjs')['passed'], 8)

    def test_closure_unit_checks(self):
        self.assertEqual(self.run_cases(HERE / 'recovery_unit.cjs')['passed'], 6)

    def test_real_http_ledger_witness(self):
        node_or_skip(self, 'Node is needed for the C3 HTTP witness')
        with tempfile.TemporaryDirectory(prefix='c3w-') as tmp:
            out = pathlib.Path(tmp) / 'out'
            env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
            done = subprocess.run([sys.executable, str(HERE / 'review_a8b4e52/run_http_witness.py'), str(ROOT),
                                   '--out', str(out), '--tmpdir', str(pathlib.Path(tmp) / 'synthetic')],
                                  capture_output=True, text=True, timeout=300, env=env)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            for mode in ('lost', 'known'):
                data = json.loads((out / f'http_witness_source_{mode}.json').read_text())
                with self.subTest(mode):
                    self.assertTrue(data['pending_preserved'])
                    self.assertNotEqual(data['status'], 'Not sent')
                    self.assertEqual((data['durable_send_count'], data['durable_launch_count']), (1, 1))
                    self.assertFalse(data['new_ledger_created'])
                    self.assertEqual(len(data['keys_sent']), 1)


if __name__ == '__main__':
    unittest.main()
