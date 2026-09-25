"""Vault link-index routes, through the real app (LINK-01/LINK-02 first slice, backlinks
half of LINK-04). Synthetic vault only."""
import sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from fastapi.testclient import TestClient
import companion_config as cc
from kit.app.server import build

TOKEN = 'vault-links-token'


class VaultLinksRoutes(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); self.root = base / 'hermes'; self.vault = base / 'vault'
        self.root.mkdir(); self.vault.mkdir()
        self.c = cc.Companion(agent='Nova', profile='nova', hermes_root=self.root, vault=self.vault,
                              soul_in_vault=False, context_mode='fixed')
        self.c.home.mkdir(parents=True); self.c.save()
        self.client = TestClient(build(self.root, token=TOKEN, state_dir=base / 'state'))
        self.h = {'x-tamanitomo-token': TOKEN}

    def write(self, rel, text):
        path = self.vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def health(self):
        return self.client.get('/api/vault/links/health', params={'profile': 'nova'}, headers=self.h)

    def backlinks(self, path):
        return self.client.get('/api/vault/links/backlinks', params={'profile': 'nova', 'path': path}, headers=self.h)

    def test_health_reflects_the_real_vault(self):
        self.write('a.md', '[[missing]]')
        self.write('b.md', '# B')
        body = self.health().json()
        self.assertEqual(body['notes'], 2)
        self.assertEqual(body['unresolved'], 1)
        self.assertFalse(body['incomplete'])

    def test_backlinks_for_a_real_note(self):
        self.write('robin.md', '# Robin')
        self.write('journal.md', 'Saw [[Robin]] today.')
        body = self.backlinks('robin.md').json()
        self.assertEqual([row['path'] for row in body['linked']], ['journal.md'])
        self.assertIn('unlinked_mentions', body)
        self.assertIn('ambiguous', body)

    def test_a_path_outside_the_vault_is_refused_not_500(self):
        r = self.backlinks('../outside.md')
        self.assertEqual(r.status_code, 400, r.text)

    def test_a_hidden_or_protected_path_is_refused(self):
        r = self.backlinks('.hidden/secret.md')
        self.assertEqual(r.status_code, 400, r.text)

    def test_wrong_token_is_refused(self):
        r = self.client.get('/api/vault/links/health', params={'profile': 'nova'}, headers={'x-tamanitomo-token': 'nope'})
        self.assertEqual(r.status_code, 401)

    def test_another_profiles_vault_is_isolated(self):
        rowan = cc.Companion(agent='Rowan', profile='rowan', hermes_root=self.root, vault=self.vault.parent / 'vault-rowan',
                             context_mode='fixed')
        rowan.vault.mkdir(); rowan.home.mkdir(parents=True); rowan.save()
        (rowan.vault / 'private.md').write_text('# Rowan only', encoding='utf-8')
        self.write('a.md', '# Nova only')
        nova_health = self.client.get('/api/vault/links/health', params={'profile': 'nova'}, headers=self.h).json()
        rowan_health = self.client.get('/api/vault/links/health', params={'profile': 'rowan'}, headers=self.h).json()
        self.assertEqual(nova_health['notes'], 1)
        self.assertEqual(rowan_health['notes'], 1)


if __name__ == '__main__':
    unittest.main()
