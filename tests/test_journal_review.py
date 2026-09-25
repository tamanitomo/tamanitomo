"""Focused Journal review regressions: instant order and initial-load selection.

Backend cases exercise the actual synthetic writers and FastAPI route. Route
cases execute the actual journal.js in Node with a minimal DOM/deferred API;
they are deliberately NOT described as browser or end-to-end executions.
Copy this file and observe_initial_route.js together into tests/.
"""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from tests.test_journal_archive import Fixture, ROOT, tree


class JournalReviewChronology(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)

    def record(self, instant, activity, ident):
        return self.f.scene(self.f.nova, dt.datetime.fromisoformat(instant), activity, ident)

    def day(self):
        response = self.f.get('/api/journal/archive/2025-11-02')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['scenes']

    def test_fall_back_distinct_scenes_follow_instants_not_wall_clock(self):
        self.record('2025-11-02T05:50:00+00:00', 'first hour scene', 'first')
        self.record('2025-11-02T06:10:00+00:00', 'second hour scene', 'second')
        self.record('2025-11-02T07:00:00+00:00', 'after rollback', 'after')
        before = tree(self.f.nova.life)
        rows = self.day()
        self.assertEqual([r['id'] for r in rows], ['first', 'second', 'after'])
        self.assertEqual(rows[0]['at'], '2025-11-02T01:50:00-04:00')
        self.assertEqual(rows[1]['at'], '2025-11-02T01:10:00-05:00')
        for row in rows:
            if row['until']:
                self.assertLessEqual(dt.datetime.fromisoformat(row['at']),
                                     dt.datetime.fromisoformat(row['until']))
        self.assertEqual(tree(self.f.nova.life), before)

    def test_fall_back_collapsed_snapshots_keep_chronological_endpoints(self):
        self.record('2025-11-02T05:50:00+00:00', 'reading', 'first')
        self.record('2025-11-02T06:10:00+00:00', 'reading', 'second')
        before = tree(self.f.nova.life)
        row, = self.day()
        self.assertEqual(row['ids'], ['first', 'second'])
        self.assertEqual(row['snapshots'], 2)
        self.assertEqual(row['at'], '2025-11-02T01:50:00-04:00')
        self.assertEqual(row['last_at'], '2025-11-02T01:10:00-05:00')
        self.assertEqual(tree(self.f.nova.life), before)


class JournalReviewInitialRoute(unittest.TestCase):
    def observe(self, *, deferred_list=False, navigate=True):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is required for the actual Journal module regression')
        script = Path(__file__).with_name('observe_initial_route.js')
        self.assertTrue(script.is_file(), 'Keep the original JS observer alongside this file')
        result = subprocess.run(
            [node, str(script), str(ROOT / 'kit/app/static/journal.js')],
            text=True, capture_output=True, timeout=15,
            env={**os.environ, 'DEFER_LIST': '1' if deferred_list else '0',
                 'NAVIGATE': '1' if navigate else '0', 'ASSERT_LATEST': '0'},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def assert_latest(self, result):
        self.assertEqual(result['before']['day'], '2026-09-20')
        self.assertEqual(result['after']['day'], '2026-09-20',
                         'initial data arrival must not replace the newer date')
        self.assertEqual(result['hash'], '#journals/2026-09-20/day')
        self.assertIn('data-day="2026-09-20"', result['html'])
        self.assertNotIn('data-day="2026-09-18"', result['html'])

    def test_pending_archive_index_does_not_restore_old_route(self):
        self.assert_latest(self.observe())

    def test_pending_reflection_list_does_not_restore_old_route(self):
        self.assert_latest(self.observe(deferred_list=True))

    def test_initial_shared_route_still_opens_without_new_selection(self):
        result = self.observe(navigate=False)
        self.assertEqual(result['after']['day'], '2026-09-18')
        self.assertEqual(result['hash'], '#journals/2026-09-18/day')
        self.assertIn('data-day="2026-09-18"', result['html'])


if __name__ == '__main__':
    unittest.main()
