"""Vault file actions: new folder, duplicate, rename/move (LINK-05 first slice).

One service (kit/app/vault.py), the same authorization/collision/reserved-name/symlink
policy regardless of caller. Link-aware rewriting of what pointed at a moved NOTE
(LINK-06) is exercised in tests/test_vault_link_aware_move.py, not here -- these tests
use non-.md files or single files with no other notes in the vault, so LINK-06's rewrite
pass finds nothing to do and every result here still looks exactly like a "dumb" move.
Synthetic vaults only.
"""
import hashlib, os, sys, tempfile, unittest
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


class MkdirTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.c = companion(Path(self.tmp.name))

    def test_creates_a_folder(self):
        vault.mkdir(self.c, 'notes/sub')
        self.assertTrue((self.c.vault / 'notes/sub').is_dir())

    def test_refuses_an_existing_path(self):
        (self.c.vault / 'notes').mkdir()
        with self.assertRaises(FileExistsError):
            vault.mkdir(self.c, 'notes')

    def test_refuses_a_reserved_name(self):
        for bad in ('CON', 'con.md', 'nul', 'COM1'):
            with self.assertRaises(ValueError, msg=bad):
                vault.mkdir(self.c, bad)

    def test_refuses_a_trailing_dot_or_space(self):
        with self.assertRaises(ValueError):vault.mkdir(self.c, 'notes.')
        with self.assertRaises(ValueError):vault.mkdir(self.c, 'notes ')

    def test_refuses_forbidden_characters(self):
        for bad in ('a<b', 'a>b', 'a:b', 'a"b', 'a|b', 'a?b', 'a*b'):
            with self.assertRaises(ValueError, msg=bad):
                vault.mkdir(self.c, bad)

    def test_refuses_traversal(self):
        with self.assertRaises(ValueError):vault.mkdir(self.c, '../escape')
        with self.assertRaises(ValueError):vault.mkdir(self.c, 'a/../../escape')

    def test_refuses_through_a_symlink(self):
        real = Path(self.tmp.name) / 'outside'; real.mkdir()
        link = self.c.vault / 'linked'
        os.symlink(real, link)
        with self.assertRaises(ValueError):
            vault.mkdir(self.c, 'linked/newdir')


class DuplicateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.c = companion(Path(self.tmp.name))
        (self.c.vault / 'notes').mkdir()
        (self.c.vault / 'notes/a.md').write_text('# A\ncontent', encoding='utf-8')

    def rev(self, rel):
        return hashlib.sha256((self.c.vault / rel).read_bytes()).hexdigest()

    def test_duplicate_creates_a_copy_with_the_same_content(self):
        result = vault.duplicate(self.c, 'notes/a.md', self.rev('notes/a.md'))
        self.assertEqual(result['duplicated'], 'notes/a copy.md')
        self.assertEqual((self.c.vault / 'notes/a copy.md').read_text(encoding='utf-8'), '# A\ncontent')
        self.assertEqual((self.c.vault / 'notes/a.md').read_text(encoding='utf-8'), '# A\ncontent')  # original untouched

    def test_repeated_duplicate_increments_the_suffix(self):
        vault.duplicate(self.c, 'notes/a.md', self.rev('notes/a.md'))
        r2 = vault.duplicate(self.c, 'notes/a.md', self.rev('notes/a.md'))
        self.assertEqual(r2['duplicated'], 'notes/a copy 2.md')

    def test_stale_revision_is_refused(self):
        with self.assertRaises(FileExistsError):
            vault.duplicate(self.c, 'notes/a.md', 'not-the-real-hash')

    def test_protected_file_cannot_be_duplicated(self):
        (self.c.home / 'config.yaml').write_text('x: 1', encoding='utf-8')
        # protected() checks vault-relative critical names; use one that matches.
        (self.c.vault / 'SOUL.md').write_text('secret', encoding='utf-8')
        rev = hashlib.sha256((self.c.vault / 'SOUL.md').read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            vault.duplicate(self.c, 'SOUL.md', rev)

    def test_binary_file_is_duplicated_byte_exact_not_through_text_mode(self):
        raw = bytes(range(256))  # includes bytes that are not valid UTF-8 alone
        (self.c.vault / 'notes/pic.png').write_bytes(raw)
        rev = hashlib.sha256(raw).hexdigest()
        result = vault.duplicate(self.c, 'notes/pic.png', rev)
        self.assertEqual((self.c.vault / result['duplicated']).read_bytes(), raw)

    def test_crlf_text_is_duplicated_byte_exact(self):
        raw = b'---\r\ntitle: x\r\n---\r\n# A\r\n\r\nbody\r\n'
        (self.c.vault / 'notes/raw.md').write_bytes(raw)
        rev = hashlib.sha256(raw).hexdigest()
        result = vault.duplicate(self.c, 'notes/raw.md', rev)
        self.assertEqual((self.c.vault / result['duplicated']).read_bytes(), raw)


class MoveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.c = companion(Path(self.tmp.name))
        (self.c.vault / 'notes').mkdir()
        (self.c.vault / 'notes/a.md').write_text('# A', encoding='utf-8')

    def rev(self, rel):
        return hashlib.sha256((self.c.vault / rel).read_bytes()).hexdigest()

    def test_rename_moves_the_file_and_keeps_content(self):
        vault.move(self.c, 'notes/a.md', 'notes/b.md', self.rev('notes/a.md'))
        self.assertFalse((self.c.vault / 'notes/a.md').exists())
        self.assertEqual((self.c.vault / 'notes/b.md').read_text(encoding='utf-8'), '# A')

    def test_move_to_a_new_folder_creates_it(self):
        vault.move(self.c, 'notes/a.md', 'archive/2026/a.md', self.rev('notes/a.md'))
        self.assertEqual((self.c.vault / 'archive/2026/a.md').read_text(encoding='utf-8'), '# A')

    def test_a_file_requires_a_revision(self):
        with self.assertRaises(ValueError):
            vault.move(self.c, 'notes/a.md', 'notes/b.md', None)

    def test_stale_revision_is_refused(self):
        with self.assertRaises(FileExistsError):
            vault.move(self.c, 'notes/a.md', 'notes/b.md', 'wrong-hash')
        self.assertTrue((self.c.vault / 'notes/a.md').exists())  # nothing moved

    def test_refuses_to_overwrite_an_existing_destination(self):
        (self.c.vault / 'notes/b.md').write_text('# B', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            vault.move(self.c, 'notes/a.md', 'notes/b.md', self.rev('notes/a.md'))
        self.assertEqual((self.c.vault / 'notes/b.md').read_text(encoding='utf-8'), '# B')  # untouched

    def test_case_only_rename_actually_changes_the_case(self):
        rev = self.rev('notes/a.md')
        vault.move(self.c, 'notes/a.md', 'notes/A.md', rev)
        names = {p.name for p in (self.c.vault / 'notes').iterdir()}
        self.assertIn('A.md', names)
        self.assertEqual((self.c.vault / 'notes/A.md').read_text(encoding='utf-8'), '# A')

    def test_folder_move_needs_no_revision(self):
        (self.c.vault / 'notes/sub').mkdir()
        (self.c.vault / 'notes/sub/x.md').write_text('x', encoding='utf-8')
        vault.move(self.c, 'notes/sub', 'archive/sub', None)
        self.assertEqual((self.c.vault / 'archive/sub/x.md').read_text(encoding='utf-8'), 'x')

    def test_protected_destination_is_refused(self):
        with self.assertRaises(ValueError):
            vault.move(self.c, 'notes/a.md', 'SOUL.md', self.rev('notes/a.md'))
        self.assertTrue((self.c.vault / 'notes/a.md').exists())

    def test_backup_history_follows_the_rename(self):
        rev1 = self.rev('notes/a.md')
        vault.write(self.c, 'notes/a.md', '# A changed', rev1)  # creates a backup of the original
        backups_before = list((self.c.vault / vault.BACKUPS).glob('*'))
        self.assertTrue(backups_before)
        vault.move(self.c, 'notes/a.md', 'notes/b.md', self.rev('notes/a.md'))
        b_folder = vault.backup_folder(self.c, 'notes/b.md')
        self.assertTrue(list(b_folder.glob('*.bak')), 'backups moved with the rename')

    def test_refuses_a_reserved_destination_name(self):
        with self.assertRaises(ValueError):
            vault.move(self.c, 'notes/a.md', 'notes/CON.md', self.rev('notes/a.md'))

    def test_refuses_through_a_symlink(self):
        real = Path(self.tmp.name) / 'outside'; real.mkdir()
        link = self.c.vault / 'linked'
        os.symlink(real, link)
        with self.assertRaises(ValueError):
            vault.move(self.c, 'notes/a.md', 'linked/a.md', self.rev('notes/a.md'))


if __name__ == '__main__':
    unittest.main()
