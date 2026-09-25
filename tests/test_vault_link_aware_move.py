"""Link-aware rename/move through the real vault.move() (LINK-06): the rewrite passes
in kit/app/vault_link_index.py, wired into kit/app/vault.py, exercised end to end
against real files on disk -- link resolution, physical move, and the write-back that
rewrites other notes' links to the new name/path. Synthetic vaults only.
"""
import hashlib, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

import companion_config as cc
from kit.app import vault


def companion(root, **kw):
    c = cc.Companion(agent='Nova', profile='nova', hermes_root=root / 'hermes', vault=root / 'vault',
                     soul_in_vault=False, context_mode='fixed', **kw)
    c.vault.mkdir(parents=True, exist_ok=True)
    c.home.mkdir(parents=True, exist_ok=True)
    c.save()
    return c


class LinkAwareMoveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.c = companion(Path(self.tmp.name))
        (self.c.vault / 'notes').mkdir()

    def write(self, rel, text):
        (self.c.vault / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.c.vault / rel).write_text(text, encoding='utf-8')

    def rev(self, rel):
        return hashlib.sha256((self.c.vault / rel).read_bytes()).hexdigest()

    def read(self, rel):
        return (self.c.vault / rel).read_text(encoding='utf-8')

    def test_rename_rewrites_a_wikilink_elsewhere(self):
        self.write('notes/Target.md', '# Target')
        self.write('notes/Citing.md', 'See [[Target]] for details.')
        result = vault.move(self.c, 'notes/Target.md', 'notes/Renamed.md', self.rev('notes/Target.md'))
        self.assertEqual(result['links']['updated'], [{'path': 'notes/Citing.md', 'links': 1}])
        self.assertEqual(self.read('notes/Citing.md'), 'See [[Renamed]] for details.')

    def test_move_to_a_new_folder_rewrites_a_relative_mdlink(self):
        self.write('notes/Target.md', '# Target')
        self.write('notes/Citing.md', 'See [it](Target.md) here.')
        result = vault.move(self.c, 'notes/Target.md', 'archive/Target.md', self.rev('notes/Target.md'))
        self.assertEqual(result['links']['updated'], [{'path': 'notes/Citing.md', 'links': 1}])
        self.assertEqual(self.read('notes/Citing.md'), 'See [it](../archive/Target.md) here.')

    def test_the_moved_notes_own_relative_link_is_recomputed(self):
        self.write('notes/Target.md', 'See [other](Other.md).')
        self.write('notes/Other.md', '# Other')
        result = vault.move(self.c, 'notes/Target.md', 'archive/Target.md', self.rev('notes/Target.md'))
        self.assertEqual(result['links']['own_links_updated'], 1)
        self.assertEqual(self.read('archive/Target.md'), 'See [other](../notes/Other.md).')

    def test_multiple_citing_notes_all_get_rewritten(self):
        self.write('notes/Target.md', '# Target')
        self.write('notes/A.md', '[[Target]]')
        self.write('notes/B.md', '[[Target|see this]]')
        result = vault.move(self.c, 'notes/Target.md', 'notes/Renamed.md', self.rev('notes/Target.md'))
        paths = {row['path'] for row in result['links']['updated']}
        self.assertEqual(paths, {'notes/A.md', 'notes/B.md'})
        self.assertEqual(self.read('notes/A.md'), '[[Renamed]]')
        self.assertEqual(self.read('notes/B.md'), '[[Renamed|see this]]')

    def test_ambiguous_name_is_reported_not_guessed(self):
        self.write('a/Note.md', '# A')
        self.write('b/Note.md', '# B')
        self.write('citing.md', '[[Note]]')
        result = vault.move(self.c, 'a/Note.md', 'a/Renamed.md', self.rev('a/Note.md'))
        self.assertEqual(result['links']['updated'], [])
        self.assertEqual(self.read('citing.md'), '[[Note]]')  # untouched
        self.assertEqual(len(result['links']['ambiguous']), 1)
        self.assertEqual(result['links']['ambiguous'][0]['path'], 'citing.md')

    def test_a_non_md_file_move_does_not_attempt_link_rewriting(self):
        self.write('notes/Target.md', '# Target')
        (self.c.vault / 'notes/pic.png').write_bytes(b'\x89PNG fake')
        result = vault.move(self.c, 'notes/pic.png', 'notes/pic2.png', self.rev('notes/pic.png'))
        self.assertNotIn('links', result)

    def test_link_rewrite_reuses_the_ordinary_backup_mechanism(self):
        self.write('notes/Target.md', '# Target')
        self.write('notes/Citing.md', '[[Target]]')
        vault.move(self.c, 'notes/Target.md', 'notes/Renamed.md', self.rev('notes/Target.md'))
        b_folder = vault.backup_folder(self.c, 'notes/Citing.md')
        backups = list(b_folder.glob('*.bak'))
        self.assertTrue(backups, 'the pre-rewrite content of Citing.md was backed up like any other edit')
        self.assertEqual(backups[0].read_bytes().decode('utf-8'), '[[Target]]')

    def test_a_link_with_no_matching_note_leaves_that_note_alone(self):
        self.write('notes/Target.md', '# Target')
        self.write('notes/Unrelated.md', '[[SomethingElse]]')
        result = vault.move(self.c, 'notes/Target.md', 'notes/Renamed.md', self.rev('notes/Target.md'))
        self.assertEqual(result['links']['updated'], [])
        self.assertEqual(self.read('notes/Unrelated.md'), '[[SomethingElse]]')

    def test_pure_rename_in_place_updates_only_the_wikilink_text(self):
        self.write('notes/Target.md', '# Target')
        self.write('notes/Citing.md', 'a [[Target]] and a [relative](Target.md) link')
        result = vault.move(self.c, 'notes/Target.md', 'notes/Renamed.md', self.rev('notes/Target.md'))
        self.assertEqual(self.read('notes/Citing.md'), 'a [[Renamed]] and a [relative](Renamed.md) link')
        self.assertEqual(result['links']['updated'], [{'path': 'notes/Citing.md', 'links': 2}])


if __name__ == '__main__':
    unittest.main()
