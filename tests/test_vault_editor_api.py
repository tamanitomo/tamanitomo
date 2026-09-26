"""Vault editor safe-save contract, through the real app routes (synthetic vault).

The editor (kit/app/static/vault-editor.js) relies on exactly these server rules:
revision tokens decide every write, text round-trips byte for byte, protected and
private files are refused by the API itself (not just by disabled buttons), and
editor backups are exact, per note, bounded and coalesced without ever losing a
version someone else wrote."""
import hashlib, json, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]
from fastapi.testclient import TestClient
import companion_config as cc
from kit.app import vault
from kit.app.server import build

TOKEN = 'vault-editor-token'


class VaultEditorApi(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); self.root = base / 'hermes'; self.vault = base / 'vault'
        self.root.mkdir(); self.vault.mkdir(); (self.vault / 'notes').mkdir()
        self.c = cc.Companion(agent='Nova', human='Alex', profile='nova', hermes_root=self.root, vault=self.vault,
                              soul_in_vault=False, context_mode='fixed')
        self.c.home.mkdir(parents=True); self.c.save()
        self.rowan = cc.Companion(agent='Rowan', profile='rowan', hermes_root=self.root, vault=base / 'vault-rowan',
                                  context_mode='fixed')
        self.rowan.vault.mkdir(); self.rowan.home.mkdir(parents=True); self.rowan.save()
        self.client = TestClient(build(self.root, token=TOKEN, state_dir=base / 'state'))
        self.h = {'x-tamanitomo-token': TOKEN}

    def get(self, path, profile='nova'):
        return self.client.get('/api/vault/file', params={'profile': profile, 'path': path}, headers=self.h)

    def put(self, path, text, revision, profile='nova'):
        return self.client.put('/api/vault/file', params={'profile': profile}, headers=self.h,
                               json={'path': path, 'text': text, 'revision': revision})

    def backups(self, rel):
        folder = self.vault / vault.BACKUPS / hashlib.sha256(rel.encode()).hexdigest()[:24]
        return sorted(folder.glob('*.bak')) if folder.exists() else []

    # --- raw text -------------------------------------------------------------------

    def test_bom_crlf_frontmatter_and_unknown_syntax_round_trip_byte_for_byte(self):
        raw = ('﻿---\r\ntitle: Ünïcødé ✨\r\ntags: [a, b]\r\n---\r\n# Heading\r\n\r\n'
               '::: custom-block {#id .cls}\r\n%%comment%%\r\n[^1]: foot\r\n\ttab nbsp  \r\nlast line no newline')
        note = self.vault / 'notes/raw.md'; note.write_bytes(raw.encode('utf-8'))
        body = self.get('notes/raw.md').json()
        self.assertEqual(body['text'], raw)
        self.assertEqual(body['revision'], hashlib.sha256(raw.encode()).hexdigest())
        edited = raw.replace('last line', 'last line, edited')
        r = self.put('notes/raw.md', edited, body['revision'])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(note.read_bytes(), edited.encode('utf-8'), 'no BOM, CRLF or syntax was rewritten')
        self.assertEqual(r.json()['revision'], hashlib.sha256(edited.encode()).hexdigest())
        self.assertEqual(self.backups('notes/raw.md')[0].read_bytes(), raw.encode('utf-8'), 'backup is exact bytes')

    # --- revisions and conflicts ----------------------------------------------------

    def test_external_atomic_replacement_is_a_conflict_and_both_versions_survive(self):
        note = self.vault / 'notes/a.md'; note.write_text('mine to start\n')
        rev = self.get('notes/a.md').json()['revision']
        tmp = self.vault / 'notes/.a.md.tmp'; tmp.write_text('written by another editor\n')
        os.replace(tmp, note)                                    # how editors and sync tools save
        r = self.put('notes/a.md', 'my unsaved buffer\n', rev)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(note.read_text(), 'written by another editor\n', 'nothing overwritten')
        # "Save mine as a copy": a new path with the empty revision (create only).
        copy = self.put('notes/a (my copy).md', 'my unsaved buffer\n', '')
        self.assertEqual(copy.status_code, 200, copy.text)
        self.assertEqual(self.put('notes/a (my copy).md', 'again', '').status_code, 409, 'create never overwrites')
        # "Replace disk with mine" (explicit): against the new revision; the external text is backed up.
        now = self.get('notes/a.md').json()
        self.assertEqual(self.put('notes/a.md', 'my unsaved buffer\n', now['revision']).status_code, 200)
        self.assertIn(b'written by another editor\n', [b.read_bytes() for b in self.backups('notes/a.md')])

    def test_a_stale_revision_after_our_own_save_is_refused(self):
        (self.vault / 'notes/s.md').write_text('one')
        rev1 = self.get('notes/s.md').json()['revision']
        self.assertEqual(self.put('notes/s.md', 'two', rev1).status_code, 200)
        self.assertEqual(self.put('notes/s.md', 'three', rev1).status_code, 409, 'an older response cannot win')
        self.assertEqual((self.vault / 'notes/s.md').read_text(), 'two')

    # --- backups --------------------------------------------------------------------

    def test_autosave_backups_coalesce_but_external_versions_are_always_kept(self):
        rel = 'notes/b.md'; note = self.vault / rel; note.write_text('v0')
        rev = self.get(rel).json()['revision']
        for i in range(1, 8):                                     # a typing session: many saves
            rev = self.put(rel, f'v{i}', rev).json()['revision']
        self.assertEqual([b.read_bytes() for b in self.backups(rel)], [b'v0'], 'one backup for the session')
        note.write_text('external')                               # someone else writes
        rev = self.get(rel).json()['revision']
        rev = self.put(rel, 'v8', rev).json()['revision']
        self.assertEqual([b.read_bytes() for b in self.backups(rel)], [b'v0', b'external'])

    def test_backups_are_bounded_per_note(self):
        rel = 'notes/c.md'; data = b'x'
        start = time.time()
        for i in range(vault.BACKUP_KEEP + 7):
            vault.backup(self.c, rel, data + str(i).encode(), now=start + i * (vault.BACKUP_WINDOW + 1))
        kept = self.backups(rel)
        self.assertEqual(len(kept), vault.BACKUP_KEEP)
        self.assertEqual(kept[-1].read_bytes(), data + str(vault.BACKUP_KEEP + 6).encode(), 'newest kept')

    def test_backups_folder_is_hidden_from_the_vault_browser(self):
        rel = 'notes/d.md'; (self.vault / rel).write_text('one')
        self.put(rel, 'two', self.get(rel).json()['revision'])
        names = [e['name'] for e in self.client.get('/api/vault', params={'profile': 'nova'}, headers=self.h).json()['entries']]
        self.assertNotIn(vault.BACKUPS, names)
        self.assertEqual(self.get(vault.BACKUPS + '/x.bak').status_code, 400)

    def test_a_linked_backup_folder_is_refused(self):
        outside = self.vault.parent / 'outside'; outside.mkdir()
        try:(self.vault / vault.BACKUPS).symlink_to(outside, target_is_directory=True)
        except OSError:self.skipTest('symlinks unavailable')
        rel = 'notes/e.md'; (self.vault / rel).write_text('one')
        r = self.put(rel, 'two', self.get(rel).json()['revision'])
        self.assertEqual(r.status_code, 400)
        self.assertEqual((self.vault / rel).read_text(), 'one')
        self.assertEqual(self.put('notes/new-note.md', 'fresh', '').status_code, 400, 'a new note too')
        self.assertFalse((self.vault / 'notes/new-note.md').exists())
        self.assertEqual(list(outside.iterdir()), [], 'nothing written through the link')

    # --- direct API enforcement (not just disabled buttons) ----------------------------

    def test_protected_private_and_hidden_files_are_refused_by_the_api(self):
        (self.vault / 'soul').mkdir(); (self.vault / 'soul/SOUL.md').write_text('identity')
        (self.vault / 'companion-life').mkdir(); (self.vault / 'companion-life/day.md').write_text('life')
        (self.vault / 'notes/tool.py').write_text('print(1)')
        (self.vault / 'notes/plain.txt').write_text('plain')
        (self.vault / 'notes/.env').write_text('SECRET=1')
        (self.vault / 'notes/api_key.md').write_text('k')
        soul = self.get('soul/SOUL.md').json()
        self.assertTrue(soul['protected']); self.assertFalse(soul['editable'])
        for rel, rev in (('soul/SOUL.md', soul['revision']), ('companion-life/day.md', None), ('notes/tool.py', None),
                         ('notes/plain.txt', None), ('SOUL.md', ''), ('notes/new.py', '')):
            if rev is None: rev = hashlib.sha256((self.vault / rel).read_bytes()).hexdigest()
            self.assertEqual(self.put(rel, 'overwrite', rev).status_code, 400, rel)
        self.assertEqual((self.vault / 'soul/SOUL.md').read_text(), 'identity')
        for rel in ('notes/.env', 'notes/api_key.md', '.companion-editor.lock', '../hermes/nova/config.yaml',
                    '/etc/passwd', 'notes/../../x.md'):
            self.assertEqual(self.get(rel).status_code, 400, rel)
            self.assertEqual(self.put(rel, 'x', '').status_code, 400, rel)
        self.assertEqual(self.client.put('/api/vault/file', params={'profile': 'nova'}, json={
            'path': 'notes/x.md', 'text': 'x', 'revision': ''}).status_code, 401, 'no token, no write')

    def test_profiles_edit_their_own_vault_only(self):
        (self.vault / 'notes/mine.md').write_text('nova only')
        self.assertEqual(self.get('notes/mine.md', profile='rowan').status_code, 400)
        r = self.put('notes/mine.md', 'rowan wrote', '', profile='rowan')
        self.assertEqual(r.status_code, 200)
        self.assertEqual((self.vault / 'notes/mine.md').read_text(), 'nova only')
        self.assertEqual((self.rowan.vault / 'notes/mine.md').read_text(), 'rowan wrote')

    def test_size_limit_is_enforced(self):
        big = 'x' * (vault.MAX_TEXT + 1)
        self.assertEqual(self.put('notes/big.md', big, '').status_code, 400)
        self.assertFalse((self.vault / 'notes/big.md').exists())


class VaultFileActionsApi(unittest.TestCase):
    """mkdir, duplicate and move, through the real app routes (LINK-05). These move bytes
    only -- they never rewrite another note's links to the old path (that's LINK-06)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); self.root = base / 'hermes'; self.vault = base / 'vault'
        self.root.mkdir(); self.vault.mkdir(); (self.vault / 'notes').mkdir()
        self.c = cc.Companion(agent='Nova', human='Alex', profile='nova', hermes_root=self.root, vault=self.vault,
                              soul_in_vault=False, context_mode='fixed')
        self.c.home.mkdir(parents=True); self.c.save()
        self.client = TestClient(build(self.root, token=TOKEN, state_dir=base / 'state'))
        self.h = {'x-tamanitomo-token': TOKEN}

    def mkdir(self, path):
        return self.client.post('/api/vault/mkdir', params={'profile': 'nova'}, headers=self.h, json={'path': path})

    def duplicate(self, path):
        return self.client.post('/api/vault/duplicate', params={'profile': 'nova'}, headers=self.h, json={'path': path})

    def move(self, path, target):
        return self.client.post('/api/vault/move', params={'profile': 'nova'}, headers=self.h, json={'path': path, 'target': target})

    def listing(self, path=''):
        return self.client.get('/api/vault', params={'profile': 'nova', 'path': path}, headers=self.h).json()['entries']

    # --- mkdir ------------------------------------------------------------------------

    def test_mkdir_creates_an_empty_folder_visible_in_the_listing(self):
        r = self.mkdir('notes/research')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue((self.vault / 'notes/research').is_dir())
        self.assertIn('research', [e['name'] for e in self.listing('notes')])

    def test_mkdir_refuses_a_collision(self):
        (self.vault / 'notes/taken').mkdir()
        self.assertEqual(self.mkdir('notes/taken').status_code, 409)

    def test_mkdir_refuses_a_hidden_or_traversal_path(self):
        self.assertEqual(self.mkdir('.hidden').status_code, 400)
        self.assertEqual(self.mkdir('../outside').status_code, 400)

    # --- duplicate --------------------------------------------------------------------

    def test_duplicate_copies_bytes_exactly_with_an_auto_named_copy(self):
        raw = '﻿---\r\ntitle: X\r\n---\r\nBody\r\n'
        (self.vault / 'notes/a.md').write_bytes(raw.encode('utf-8'))
        r = self.duplicate('notes/a.md')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['duplicated'], 'notes/a copy.md')
        self.assertEqual((self.vault / 'notes/a copy.md').read_bytes(), raw.encode('utf-8'))
        self.assertEqual((self.vault / 'notes/a.md').read_bytes(), raw.encode('utf-8'), 'original untouched')

    def test_duplicate_increments_the_name_on_repeat(self):
        (self.vault / 'notes/a.md').write_text('one')
        self.assertEqual(self.duplicate('notes/a.md').json()['duplicated'], 'notes/a copy.md')
        self.assertEqual(self.duplicate('notes/a.md').json()['duplicated'], 'notes/a copy 2.md')
        self.assertEqual(self.duplicate('notes/a.md').json()['duplicated'], 'notes/a copy 3.md')

    def test_duplicate_refuses_a_protected_file(self):
        (self.vault / 'soul').mkdir(); (self.vault / 'soul/SOUL.md').write_text('identity')
        self.assertEqual(self.duplicate('soul/SOUL.md').status_code, 400)

    # --- move -------------------------------------------------------------------------

    def test_move_renames_a_file(self):
        (self.vault / 'notes/a.md').write_text('content')
        r = self.move('notes/a.md', 'notes/b.md')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse((self.vault / 'notes/a.md').exists())
        self.assertEqual((self.vault / 'notes/b.md').read_text(), 'content')

    def test_move_refuses_a_collision(self):
        (self.vault / 'notes/a.md').write_text('a'); (self.vault / 'notes/b.md').write_text('b')
        self.assertEqual(self.move('notes/a.md', 'notes/b.md').status_code, 409)
        self.assertEqual((self.vault / 'notes/b.md').read_text(), 'b', 'destination untouched')

    def test_move_refuses_a_protected_source_or_destination(self):
        (self.vault / 'soul').mkdir(); (self.vault / 'soul/SOUL.md').write_text('identity')
        (self.vault / 'notes/a.md').write_text('a')
        self.assertEqual(self.move('soul/SOUL.md', 'notes/x.md').status_code, 400)
        self.assertEqual(self.move('notes/a.md', 'soul/SOUL.md').status_code, 400)

    def test_move_a_folder_relocates_every_file_inside_it(self):
        (self.vault / 'notes/project').mkdir()
        (self.vault / 'notes/project/a.md').write_text('a')
        (self.vault / 'notes/project/sub').mkdir()
        (self.vault / 'notes/project/sub/b.md').write_text('b')
        r = self.move('notes/project', 'notes/renamed')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse((self.vault / 'notes/project').exists())
        self.assertEqual((self.vault / 'notes/renamed/a.md').read_text(), 'a')
        self.assertEqual((self.vault / 'notes/renamed/sub/b.md').read_text(), 'b')

    def test_move_a_folder_into_itself_is_refused(self):
        (self.vault / 'notes/project').mkdir()
        (self.vault / 'notes/project/a.md').write_text('a')
        self.assertEqual(self.move('notes/project', 'notes/project/inner').status_code, 400)

    def test_move_to_a_different_folder_with_the_same_basename_touches_nothing(self):
        (self.vault / 'notes/Robin.md').write_text('# Robin\n', encoding='utf-8')
        (self.vault / 'notes/Journal.md').write_text('Saw [[Robin]] and [[Robin#Likes]] today.\n', encoding='utf-8')
        r = self.move('notes/Robin.md', 'people/Robin.md')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['relinked'], [], 'a bare wikilink by basename already reads correctly')
        self.assertEqual((self.vault / 'notes/Journal.md').read_text(),
                          'Saw [[Robin]] and [[Robin#Likes]] today.\n', 'basename unchanged, so text unchanged too')

    def test_move_rewrites_unambiguous_inbound_wikilinks_on_rename(self):
        (self.vault / 'notes/Robin.md').write_text('# Robin\n', encoding='utf-8')
        (self.vault / 'notes/Journal.md').write_text('Saw [[Robin]] and [[Robin#Likes]] today.\n', encoding='utf-8')
        r = self.move('notes/Robin.md', 'notes/Robert.md')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['relinked'], ['notes/Journal.md'])
        self.assertEqual((self.vault / 'notes/Journal.md').read_text(), 'Saw [[Robert]] and [[Robert#Likes]] today.\n')

    def test_move_rewrites_a_path_style_link_to_the_new_path(self):
        (self.vault / 'notes/Robin.md').write_text('# Robin\n', encoding='utf-8')
        (self.vault / 'notes/Journal.md').write_text('See [[notes/Robin.md]].\n', encoding='utf-8')
        r = self.move('notes/Robin.md', 'people/Robin.md')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((self.vault / 'notes/Journal.md').read_text(), 'See [[people/Robin.md]].\n')

    def test_move_rewrite_keeps_basename_when_it_actually_changes(self):
        (self.vault / 'notes/Robin.md').write_text('# Robin\n', encoding='utf-8')
        (self.vault / 'notes/Journal.md').write_text('Saw [[Robin]] today.\n', encoding='utf-8')
        self.move('notes/Robin.md', 'notes/Rob.md')
        self.assertEqual((self.vault / 'notes/Journal.md').read_text(), 'Saw [[Rob]] today.\n')

    def test_move_does_not_rewrite_an_ambiguous_referrer(self):
        (self.vault / 'notes/a.md').write_text('# A', encoding='utf-8')
        (self.vault / 'notes/dup').mkdir(); (self.vault / 'notes/dup/a.md').write_text('# A dup', encoding='utf-8')
        (self.vault / 'notes/linker.md').write_text('[[a]]', encoding='utf-8')
        self.move('notes/a.md', 'notes/renamed.md')
        self.assertEqual((self.vault / 'notes/linker.md').read_text(), '[[a]]')

    def test_move_relink_backs_up_the_rewritten_note(self):
        (self.vault / 'notes/Robin.md').write_text('# Robin\n', encoding='utf-8')
        (self.vault / 'notes/Journal.md').write_text('[[Robin]]\n', encoding='utf-8')
        self.move('notes/Robin.md', 'notes/Rob.md')
        backups = self.vault / vault.BACKUPS / hashlib.sha256('notes/Journal.md'.encode()).hexdigest()[:24]
        self.assertEqual([p.read_bytes() for p in backups.glob('*.bak')], [b'[[Robin]]\n'])

    def test_move_does_not_touch_a_note_that_never_referenced_it(self):
        (self.vault / 'notes/Robin.md').write_text('# Robin\n', encoding='utf-8')
        (self.vault / 'notes/Unrelated.md').write_text('Nothing relevant here.\n', encoding='utf-8')
        self.move('notes/Robin.md', 'notes/Rob.md')
        self.assertEqual((self.vault / 'notes/Unrelated.md').read_text(), 'Nothing relevant here.\n')

    def test_move_migrates_the_notes_backup_history(self):
        rel = 'notes/a.md'; note = self.vault / rel; note.write_text('v0')
        rev = self.client.get('/api/vault/file', params={'profile': 'nova', 'path': rel}, headers=self.h).json()['revision']
        self.client.put('/api/vault/file', params={'profile': 'nova'}, headers=self.h, json={'path': rel, 'text': 'v1', 'revision': rev})
        old_backups = self.vault / vault.BACKUPS / hashlib.sha256(rel.encode()).hexdigest()[:24]
        self.assertTrue(list(old_backups.glob('*.bak')), 'a backup exists before the move')
        self.assertEqual(self.move(rel, 'notes/b.md').status_code, 200)
        new_backups = self.vault / vault.BACKUPS / hashlib.sha256('notes/b.md'.encode()).hexdigest()[:24]
        self.assertEqual([p.read_bytes() for p in new_backups.glob('*.bak')], [b'v0'])
        self.assertFalse(old_backups.exists(), 'old backup folder migrated, not left behind')


if __name__ == '__main__':
    unittest.main()
