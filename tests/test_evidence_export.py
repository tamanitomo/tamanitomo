"""tools/evidence_export.py: format-aware redaction keeps every export machine-readable (review of
b94caf2, R4). The defect it answers: a text substitution wrote hostname="<host>" into junit.xml."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools' / 'evidence_export.py'
JUNIT = ('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" tests="3" '
         'hostname="{host}"><testcase classname="t.A" name="test_one" time="0.1"/>'
         '<testcase classname="t.A" name="test_two"><skipped message="x"/></testcase>'
         '<testcase classname="t.B" name="test_three"><failure message="at /home/someone/x">'
         'trace /home/someone/x</failure></testcase></testsuite></testsuites>')


class EvidenceExport(unittest.TestCase):

    def run_tool(self, *args):
        return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=60)

    def test_placeholders_are_escaped_and_cases_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            src = tmp / 'in'
            src.mkdir()
            (src / 'junit.xml').write_text(JUNIT.format(host='realhost'))
            (src / 'lane.json').write_text(json.dumps({'host': 'realhost', 'path': '/home/someone/x', 'n': 3}))
            r = self.run_tool('--out', str(tmp / 'out'), '--kind', 'executed', '--source-note', 'unit',
                              '--sub', f'{tmp}=<tmp>', '--sub', '/home/someone=~', '--sub', 'realhost=<host>',
                              '--forbid', '/home/', str(src))
            self.assertEqual(r.returncode, 0, r.stderr)
            root = ET.parse(tmp / 'out' / 'in' / 'junit.xml').getroot()          # parses
            suite = root.find('testsuite')
            self.assertEqual(suite.get('hostname'), '<host>')                      # escaped on disk
            self.assertIn('&lt;host&gt;', (tmp / 'out' / 'in' / 'junit.xml').read_text())
            self.assertEqual(suite.get('tests'), '3')                              # counts untouched
            manifest = json.loads((tmp / 'out' / 'MANIFEST.json').read_text())
            record = manifest['files']['in/junit.xml']
            self.assertEqual((record['junit_cases'], record['junit_status_counts']),
                             (3, {'failure': 1, 'passed': 1, 'skipped': 1}))
            self.assertEqual(json.loads((tmp / 'out' / 'in' / 'lane.json').read_text())['path'], '~/x')

    def test_an_earlier_raw_placeholder_is_repaired_as_a_derivative(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            bad = tmp / 'junit.xml'
            bad.write_text(JUNIT.format(host='<host>'))
            with self.assertRaises(ET.ParseError):
                ET.parse(bad)
            r = self.run_tool('--out', str(tmp / 'out'), '--kind', 'derivative', '--source-note', 'unit', str(bad))
            self.assertEqual(r.returncode, 0, r.stderr)
            ET.parse(tmp / 'out' / 'junit.xml')
            manifest = json.loads((tmp / 'out' / 'MANIFEST.json').read_text())
            self.assertEqual(manifest['files']['junit.xml']['repaired'], ['<host>'])
            self.assertIn('NOT a test rerun', manifest['note'])

    def test_other_malformation_and_leaks_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            (tmp / 'broken.xml').write_text('<a><b></a>')
            self.assertNotEqual(self.run_tool('--out', str(tmp / 'o1'), '--kind', 'derivative', '--source-note', 'u',
                                              str(tmp / 'broken.xml')).returncode, 0)
            (tmp / 'leak.txt').write_text('at /home/someone')
            r = self.run_tool('--out', str(tmp / 'o2'), '--kind', 'executed', '--source-note', 'u',
                              '--forbid', '/home/', str(tmp / 'leak.txt'))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('forbidden', r.stderr)


if __name__ == '__main__':
    unittest.main()
