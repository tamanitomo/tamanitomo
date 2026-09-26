"""Vault link-index routes, through the real app (LINK-01 through LINK-03: index/resolver,
backlinks half of LINK-04, and safe embeds). Synthetic vault only."""
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

    def embed(self, path, target):
        return self.client.get('/api/vault/links/embed', params={'profile': 'nova', 'path': path, 'target': target}, headers=self.h)

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

    def test_backlinks_includes_the_notes_own_properties(self):
        self.write('robin.md', '---\ntitle: Robin\naliases: [Bob]\n---\n# Robin')
        body = self.backlinks('robin.md').json()
        self.assertEqual(body['properties'], {'title': 'Robin', 'aliases': ['Bob']})

    def test_backlinks_properties_empty_for_a_note_without_frontmatter(self):
        self.write('plain.md', '# Plain')
        body = self.backlinks('plain.md').json()
        self.assertEqual(body['properties'], {})

    def test_a_path_outside_the_vault_is_refused_not_500(self):
        r = self.backlinks('../outside.md')
        self.assertEqual(r.status_code, 400, r.text)

    def test_a_hidden_or_protected_path_is_refused(self):
        r = self.backlinks('.hidden/secret.md')
        self.assertEqual(r.status_code, 400, r.text)

    def test_wrong_token_is_refused(self):
        r = self.client.get('/api/vault/links/health', params={'profile': 'nova'}, headers={'x-tamanitomo-token': 'nope'})
        self.assertEqual(r.status_code, 401)

    def test_embed_resolves_a_note_excerpt(self):
        self.write('journal.md', '# Journal')
        self.write('robin.md', '# Robin\nDetails.')
        body = self.embed('journal.md', 'Robin').json()
        self.assertEqual(body['kind'], 'note')
        self.assertEqual(body['path'], 'robin.md')

    def test_embed_resolves_an_image(self):
        self.write('journal.md', '# Journal')
        (self.vault / 'photo.png').write_bytes(b'fake-bytes')
        body = self.embed('journal.md', 'photo.png').json()
        self.assertEqual(body, {'kind': 'image', 'path': 'photo.png'})

    def test_embed_missing_target_reported_not_500(self):
        self.write('journal.md', '# Journal')
        body = self.embed('journal.md', 'Nowhere').json()
        self.assertEqual(body['kind'], 'missing')

    def test_embed_source_outside_the_vault_is_refused_not_500(self):
        r = self.embed('../outside.md', 'Robin')
        self.assertEqual(r.status_code, 400, r.text)

    def test_embed_hidden_target_path_is_refused_not_500(self):
        self.write('journal.md', '# Journal')
        r = self.embed('journal.md', '.hidden/secret.md')
        self.assertEqual(r.status_code, 400, r.text)

    def test_embed_wrong_token_is_refused(self):
        r = self.client.get('/api/vault/links/embed', params={'profile': 'nova', 'path': 'journal.md', 'target': 'Robin'},
                             headers={'x-tamanitomo-token': 'nope'})
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
