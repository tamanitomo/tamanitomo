"""Vault file-action routes (LINK-05 first slice), through the real app."""
import hashlib, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from fastapi.testclient import TestClient
import companion_config as cc
from kit.app.server import build

TOKEN = 'vault-actions-token'


class VaultFileActionsRoutes(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); self.root = base / 'hermes'; self.vault = base / 'vault'
        self.root.mkdir(); self.vault.mkdir(); (self.vault / 'notes').mkdir()
        self.c = cc.Companion(agent='Nova', profile='nova', hermes_root=self.root, vault=self.vault,
                              soul_in_vault=False, context_mode='fixed')
        self.c.home.mkdir(parents=True); self.c.save()
        self.client = TestClient(build(self.root, token=TOKEN, state_dir=base / 'state'))
        self.h = {'x-tamanitomo-token': TOKEN}
        (self.vault / 'notes/a.md').write_text('# A', encoding='utf-8')

    def rev(self, rel):
        return hashlib.sha256((self.vault / rel).read_bytes()).hexdigest()

    def mkdir(self, path):
        return self.client.post('/api/vault/mkdir', params={'profile': 'nova'}, headers=self.h, json={'path': path})

    def duplicate(self, path, revision):
        return self.client.post('/api/vault/duplicate', params={'profile': 'nova'}, headers=self.h,
                                json={'path': path, 'revision': revision})

    def move(self, path, dest, revision=None):
        return self.client.post('/api/vault/move', params={'profile': 'nova'}, headers=self.h,
                                json={'path': path, 'dest': dest, 'revision': revision})

    def test_mkdir_creates_and_is_idempotent_refused(self):
        r = self.mkdir('notes/sub')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue((self.vault / 'notes/sub').is_dir())
        r2 = self.mkdir('notes/sub')
        self.assertEqual(r2.status_code, 409, r2.text)

    def test_mkdir_refuses_unauthorized_or_reserved_paths(self):
        self.assertEqual(self.mkdir('../outside').status_code, 400)
        self.assertEqual(self.mkdir('CON').status_code, 400)

    def test_duplicate_end_to_end(self):
        r = self.duplicate('notes/a.md', self.rev('notes/a.md'))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['duplicated'], 'notes/a copy.md')
        self.assertEqual((self.vault / 'notes/a copy.md').read_text(encoding='utf-8'), '# A')

    def test_duplicate_stale_revision_is_409(self):
        r = self.duplicate('notes/a.md', 'stale')
        self.assertEqual(r.status_code, 409, r.text)

    def test_move_end_to_end_and_read_at_the_new_path(self):
        r = self.move('notes/a.md', 'notes/b.md', self.rev('notes/a.md'))
        self.assertEqual(r.status_code, 200, r.text)
        got = self.client.get('/api/vault/file', params={'profile': 'nova', 'path': 'notes/b.md'}, headers=self.h)
        self.assertEqual(got.json()['text'], '# A')
        missing = self.client.get('/api/vault/file', params={'profile': 'nova', 'path': 'notes/a.md'}, headers=self.h)
        self.assertEqual(missing.status_code, 400)

    def test_move_collision_is_409_and_nothing_changes(self):
        (self.vault / 'notes/b.md').write_text('# B', encoding='utf-8')
        r = self.move('notes/a.md', 'notes/b.md', self.rev('notes/a.md'))
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual((self.vault / 'notes/b.md').read_text(encoding='utf-8'), '# B')
        self.assertTrue((self.vault / 'notes/a.md').exists())

    def test_move_without_a_revision_is_refused_for_a_file(self):
        r = self.move('notes/a.md', 'notes/b.md', None)
        self.assertEqual(r.status_code, 400, r.text)

    def test_another_profiles_vault_is_isolated(self):
        rowan = cc.Companion(agent='Rowan', profile='rowan', hermes_root=self.root, vault=self.vault.parent / 'vault-rowan',
                             context_mode='fixed')
        rowan.vault.mkdir(); rowan.home.mkdir(parents=True); rowan.save()
        r = self.client.post('/api/vault/mkdir', params={'profile': 'rowan'}, headers=self.h, json={'path': 'x'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse((self.vault / 'x').exists())
        self.assertTrue((rowan.vault / 'x').exists())

    def test_wrong_token_is_refused(self):
        r = self.client.post('/api/vault/mkdir', params={'profile': 'nova'},
                             headers={'x-tamanitomo-token': 'nope'}, json={'path': 'x'})
        self.assertEqual(r.status_code, 401)


if __name__ == '__main__':
    unittest.main()
