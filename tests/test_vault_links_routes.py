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

    def resolve(self, source, target, kind='wiki'):
        return self.client.get('/api/vault/links/resolve',
                               params={'profile': 'nova', 'source': source, 'target': target, 'kind': kind},
                               headers=self.h)

    def embed_note(self, source, target, heading=''):
        return self.client.get('/api/vault/links/embed-note',
                               params={'profile': 'nova', 'source': source, 'target': target, 'heading': heading},
                               headers=self.h)

    def embed_image(self, source, target):
        return self.client.get('/api/vault/links/embed-image',
                               params={'profile': 'nova', 'source': source, 'target': target}, headers=self.h)

    def test_resolve_unique_ambiguous_and_unresolved(self):
        self.write('robin.md', '# Robin')
        self.write('dup/robin.md', '# Robin too')
        self.write('c.md', '# C')
        self.assertEqual(self.resolve('a.md', 'c').json()['candidates'], ['c.md'])
        self.assertEqual(set(self.resolve('a.md', 'robin').json()['candidates']), {'robin.md', 'dup/robin.md'})
        self.assertEqual(self.resolve('a.md', 'nope').json()['candidates'], [])

    def test_resolve_refuses_an_unauthorized_source(self):
        r = self.resolve('../outside.md', 'x')
        self.assertEqual(r.status_code, 400, r.text)

    def test_embed_note_returns_bounded_text(self):
        self.write('target.md', '# Target\nSome body text.')
        body = self.embed_note('a.md', 'target').json()
        self.assertTrue(body['resolved'])
        self.assertIn('Some body text.', body['text'])
        self.assertFalse(body['truncated'])

    def test_embed_note_slices_by_heading(self):
        self.write('target.md', '# Title\n## Keep\nkept\n## Drop\ndropped\n')
        body = self.embed_note('a.md', 'target', heading='Keep').json()
        self.assertIn('kept', body['text'])
        self.assertNotIn('dropped', body['text'])

    def test_embed_note_ambiguous_target_is_not_resolved(self):
        self.write('x.md', '# X'); self.write('dup/x.md', '# X too')
        body = self.embed_note('a.md', 'x').json()
        self.assertFalse(body['resolved'])
        self.assertEqual(len(body['candidates']), 2)

    def test_embed_note_never_recurses_into_the_targets_own_embed(self):
        self.write('leaf.md', '# Leaf\nplain text')
        self.write('mid.md', '![[leaf]]')
        body = self.embed_note('a.md', 'mid').json()
        self.assertIn('[[leaf]]', body['text'])   # left as literal, not expanded

    def test_embed_image_serves_inline_with_the_right_content_type(self):
        (self.vault / 'photo.png').write_bytes(b'\x89PNG\r\n\x1a\nFAKE')
        r = self.embed_image('a.md', 'photo.png')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers['content-type'], 'image/png')
        self.assertIn('inline', r.headers.get('content-disposition', ''))
        self.assertEqual(r.content, b'\x89PNG\r\n\x1a\nFAKE')

    def test_embed_image_refuses_a_non_image_target(self):
        self.write('notes.md', '# not an image')
        r = self.embed_image('a.md', 'notes')
        self.assertEqual(r.status_code, 400)

    def test_embed_image_refuses_an_unresolved_target(self):
        r = self.embed_image('a.md', 'nope.png')
        self.assertEqual(r.status_code, 404)

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
