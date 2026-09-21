"""Circling back on the thing you said you would check on.

This was switched on, wired up and completely inert: the sensor read one
hand-written file and nothing else, and nobody had ever been told to create it.
So a companion appeared to be tracking follow-ups and was tracking none, for
everyone, silently. It now reads the store she already writes to by herself.
"""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

import companion_config as cc
import companion_loops as loops
import companion_sensors as sensors


class CareFollowUpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex', profile='nova',
                              hermes_root=base / 'hermes', vault=base / 'vault',
                              timezone='UTC', context_mode='fixed')
        self.c.home.mkdir(parents=True)
        self.c.soul_dir.mkdir(parents=True)
        self.c.life.mkdir(parents=True, exist_ok=True)
        self.c.save()
        self.now = dt.datetime(2026, 9, 21, 12, tzinfo=ZoneInfo('UTC'))

    def loop(self, title, follow_up, gentle='raise it once, lightly', status='open'):
        loops.add(self.c, {'title': title, 'detail': 'something that happened',
                           'gentle_use': gentle, 'follow_up_at': follow_up,
                           'category': 'care'}, self.now)
        if status != 'open':
            rows = [r for r in loops.loops(self.c) if r.get('title') == title]
            loops.update(self.c, {'id': rows[-1]['id'], 'status': status}, self.now)

    def care(self, when=None):
        return sensors.care(self.c, when or self.now)

    def test_it_works_with_nothing_set_up_at_all(self):
        """The old behaviour: a file nobody knew to write, so nothing ever."""
        text, extra = self.care()
        self.assertIsNone(text)
        self.assertEqual(extra, 'nothing due')

    def test_a_follow_up_that_has_come_due_is_surfaced(self):
        self.loop('how the interview went', '2026-09-20T09:00:00+00:00',
                  gentle='ask once, lightly')
        text, extra = self.care()
        self.assertIn('how the interview went', text)
        self.assertIn('ask once, lightly', text, 'the gentle_use line is the whole point')
        self.assertEqual(extra['count'], 1)

    def test_one_that_is_not_due_yet_waits(self):
        self.loop('the exam on Friday', '2026-09-25T09:00:00+00:00')
        self.assertIsNone(self.care()[0])

    def test_a_closed_loop_stops_being_raised(self):
        self.loop('the dentist', '2026-09-20T09:00:00+00:00', status='closed')
        self.assertIsNone(self.care()[0])

    def test_a_loop_with_no_date_is_not_a_follow_up(self):
        """An open thread is not the same as something due to be asked about."""
        self.loop('a book lent out', '')
        self.assertIsNone(self.care()[0])

    def test_a_person_can_still_add_their_own_by_hand(self):
        (self.c.data / 'care.md').write_text(
            '# mine\n2026-09-19 | his mother | ask how she is settling in\n', encoding='utf-8')
        text, extra = self.care()
        self.assertIn('his mother', text)
        self.assertEqual(extra['count'], 1)

    def test_both_sources_appear_together(self):
        self.loop('how the interview went', '2026-09-20T09:00:00+00:00')
        (self.c.data / 'care.md').write_text(
            '2026-09-19 | his mother | ask how she is settling in\n', encoding='utf-8')
        text, extra = self.care()
        self.assertEqual(extra['count'], 2)
        self.assertIn('interview', text)
        self.assertIn('mother', text)

    def test_it_is_never_presented_as_a_list_to_read_out(self):
        self.loop('how the interview went', '2026-09-20T09:00:00+00:00')
        self.assertIn('not a list to read out', self.care()[0])

    def test_an_unreadable_loop_store_does_not_lose_the_handwritten_file(self):
        (self.c.data / 'care.md').write_text(
            '2026-09-19 | his mother | ask how she is settling in\n', encoding='utf-8')
        path = loops.path_for(self.c) if hasattr(loops, 'path_for') else None
        if path:
            pathlib.Path(path).write_text('{ not json at all\n', encoding='utf-8')
        self.assertIn('mother', self.care()[0])


if __name__ == '__main__':
    unittest.main()


class ArchiveIndexTests(unittest.TestCase):
    """Archived memories went into the vault and stayed findable only by reading it.

    Sixty-seven thousand characters of prose with a date comment every so often
    is most of the promise kept and the useful half missing: nothing could say
    what had been archived, or when, without opening the whole file.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex', hermes_root=base / 'h',
                              vault=base / 'v', timezone='UTC', context_tokens=8192)
        import companion_memory as memory
        self.memory = memory
        memory.memory_dir(self.c).mkdir(parents=True)
        (self.c.home / 'config.yaml').write_text(
            'memory:\n  memory_char_limit: 2200\n  user_char_limit: 1375\n', encoding='utf-8')

    def fill(self, n, word='Fact'):
        import companion_memory as memory
        (memory.memory_dir(self.c) / 'MEMORY.md').write_text(
            memory.ENTRY_DELIMITER.join(f'- {word} {i} about an ordinary day.' for i in range(n)),
            encoding='utf-8')

    def test_every_archived_entry_is_indexed_as_it_moves(self):
        self.fill(200)
        result = self.memory.archive(self.c, 'MEMORY.md', apply=True)
        self.assertGreater(result['moved'], 0)
        self.assertEqual(result['indexed'], result['moved'])
        self.assertEqual(len(self.memory.index(self.c)), result['moved'])

    def test_an_index_row_says_what_it_was_without_opening_the_archive(self):
        self.fill(200)
        self.memory.archive(self.c, 'MEMORY.md', apply=True)
        row = self.memory.index(self.c)[0]
        for field in ('id', 'file', 'archived_at', 'chars', 'sha256', 'preview'):
            self.assertIn(field, row)
        self.assertIn('about an ordinary day', row['preview'])
        self.assertEqual(row['file'], 'MEMORY.md')

    def test_the_index_is_newest_first(self):
        self.fill(200, 'Older')
        self.memory.archive(self.c, 'MEMORY.md', apply=True)
        self.fill(200, 'Newer')
        self.memory.archive(self.c, 'MEMORY.md', apply=True)
        self.assertIn('Newer', self.memory.index(self.c)[0]['preview'])

    def test_a_version_is_snapshotted_once_and_can_be_found_by_its_day(self):
        self.fill(200)
        self.memory.archive(self.c, 'MEMORY.md', apply=True)
        snaps = sorted((self.memory.archive_dir(self.c) / 'snapshots').iterdir())
        self.assertEqual(len(snaps), 1)
        self.assertTrue(snaps[0].name.startswith('MEMORY-'))
        self.assertIn(dt.date.today().isoformat(), snaps[0].name)

    def test_the_same_content_is_never_snapshotted_twice(self):
        self.fill(200)
        text = (self.memory.memory_dir(self.c) / 'MEMORY.md').read_text(encoding='utf-8')
        first = self.memory.snapshot(self.c, 'MEMORY.md', text)
        second = self.memory.snapshot(self.c, 'MEMORY.md', text)
        self.assertTrue(first['written'])
        self.assertFalse(second['written'], 'an unchanged file was stored twice')
        self.assertEqual(len(list((self.memory.archive_dir(self.c) / 'snapshots').iterdir())), 1)

    def test_a_dry_run_writes_no_index_and_no_snapshot(self):
        self.fill(200)
        self.memory.archive(self.c, 'MEMORY.md', apply=False)
        self.assertEqual(self.memory.index(self.c), [])
        self.assertFalse((self.memory.archive_dir(self.c) / 'snapshots').exists())

    def test_a_corrupt_index_line_does_not_hide_the_rest(self):
        self.fill(200)
        self.memory.archive(self.c, 'MEMORY.md', apply=True)
        path = self.memory.index_path(self.c)
        path.write_text('{ not json\n' + path.read_text(encoding='utf-8'), encoding='utf-8')
        self.assertGreater(len(self.memory.index(self.c)), 0)

    def test_what_was_archived_before_there_was_an_index_is_indexed_too(self):
        """Otherwise the index is only ever true about the future."""
        archive = self.memory.archive_for(self.c, 'MEMORY.md')
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text(
            '\n<!-- archived 2026-08-01 from memories/MEMORY.md -->\n'
            + self.memory.ENTRY_DELIMITER.join(['- He is allergic to shellfish.',
                                                '- His sister is called Bea.'])
            + '\n<!-- archived 2026-09-01 from memories/MEMORY.md -->\n'
            + '- They do the crossword on Sundays.\n', encoding='utf-8')
        dry = self.memory.backfill_index(self.c)
        self.assertEqual(dry['found'], 3)
        self.assertFalse(dry['applied'])
        self.assertEqual(self.memory.index(self.c), [], 'a dry run must write nothing')

        self.memory.backfill_index(self.c, apply=True)
        rows = {r['preview']: r for r in self.memory.index(self.c)}
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows['He is allergic to shellfish.']['archived_at'], '2026-08-01')
        self.assertEqual(rows['They do the crossword on Sundays.']['archived_at'], '2026-09-01')

    def test_running_the_backfill_twice_does_not_duplicate_anything(self):
        archive = self.memory.archive_for(self.c, 'MEMORY.md')
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text('- He is allergic to shellfish.\n', encoding='utf-8')
        self.memory.backfill_index(self.c, apply=True)
        again = self.memory.backfill_index(self.c, apply=True)
        self.assertEqual(again['found'], 0)
        self.assertEqual(len(self.memory.index(self.c)), 1)

    def test_entries_archived_before_batches_were_dated_are_still_indexed(self):
        archive = self.memory.archive_for(self.c, 'MEMORY.md')
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text('- An entry from before the markers existed.\n', encoding='utf-8')
        result = self.memory.backfill_index(self.c, apply=True)
        self.assertEqual(result['found'], 1)
        self.assertEqual(result['undated'], 1)
        self.assertEqual(self.memory.index(self.c)[0]['archived_at'], 'unknown')
