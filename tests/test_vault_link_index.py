"""Vault link index: parser, resolver and backlinks (LINK-01/LINK-02 first slice).

NOT ACTIVATED: no route serves this yet (see kit/app/vault_link_index.py). Pure-function
tests for the parser/resolver/backlinks, plus a real-filesystem test of the incremental
build through kit/app/vault.files() (the same authorization boundary the editor uses).
"""
import sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

import companion_config as cc
from kit.app import vault_link_index as vli


def companion(root, **kw):
    c = cc.Companion(agent='Nova', profile='nova', hermes_root=root / 'hermes', vault=root / 'vault',
                     soul_in_vault=False, context_mode='fixed', **kw)
    c.vault.mkdir(parents=True, exist_ok=True)
    c.home.mkdir(parents=True, exist_ok=True)
    c.save()
    return c


class ParseNoteTests(unittest.TestCase):
    def test_frontmatter_title_aliases_and_list_tags(self):
        text = '---\ntitle: The Real Title\naliases: [Nick, "Second Name"]\ntags: [project, review]\n---\nBody text.\n'
        parsed = vli.parse_note(text)
        self.assertEqual(parsed['title'], 'The Real Title')
        self.assertEqual(parsed['aliases'], ['Nick', 'Second Name'])
        self.assertEqual(parsed['tags'], ['project', 'review'])

    def test_malformed_frontmatter_does_not_fail_closed(self):
        text = '---\ntitle: [unterminated\n---\n# Fallback Title\nSome #inline-tag text.\n'
        parsed = vli.parse_note(text)
        self.assertTrue(parsed['properties'].get('_malformed'))
        self.assertEqual(parsed['title'], 'Fallback Title')
        self.assertIn('inline-tag', parsed['tags'])

    def test_headings_and_block_ids(self):
        text = '# Top\n## Sub heading\nSome text. ^my-block\n### Deep\n'
        parsed = vli.parse_note(text)
        self.assertEqual([h['text'] for h in parsed['headings']], ['Top', 'Sub heading', 'Deep'])
        self.assertEqual([h['level'] for h in parsed['headings']], [1, 2, 3])
        self.assertEqual(parsed['block_ids'], ['my-block'])

    def test_wikilinks_with_heading_block_and_label(self):
        text = '[[Plain Note]] and [[Other#Heading]] and [[Third^blk]] and [[Fourth|Label Text]]'
        parsed = vli.parse_note(text)
        targets = {(o['target'], o['heading'], o['block'], o['label']) for o in parsed['outbound']}
        self.assertIn(('Plain Note', None, None, None), targets)
        self.assertIn(('Other', 'Heading', None, None), targets)
        self.assertIn(('Third', None, 'blk', None), targets)
        self.assertIn(('Fourth', None, None, 'Label Text'), targets)

    def test_embed_wikilink_is_flagged(self):
        parsed = vli.parse_note('![[image.png]] and [[Not An Embed]]')
        by_target = {o['target']: o['embed'] for o in parsed['outbound']}
        self.assertTrue(by_target['image.png'])
        self.assertFalse(by_target['Not An Embed'])

    def test_relative_markdown_link_captured_external_link_skipped(self):
        parsed = vli.parse_note('[note](../folder/Other%20Note.md) and [site](https://example.com) and [mail](mailto:a@b.c)')
        targets = [o['target'] for o in parsed['outbound'] if o['kind'] == 'md']
        self.assertEqual(targets, ['../folder/Other%20Note.md'])

    def test_links_and_tags_inside_code_fences_and_spans_are_ignored(self):
        text = ('Prose #real-tag [[Real Link]]\n'
                '```\n#not-a-tag [[Not A Link]]\n```\n'
                'Back to prose with `#also-not-a-tag [[Also Not A Link]]` inline.\n')
        parsed = vli.parse_note(text)
        self.assertEqual(parsed['tags'], ['real-tag'])
        self.assertEqual([o['target'] for o in parsed['outbound']], ['Real Link'])

    def test_a_lone_title_heading_is_not_duplicated_as_a_tag_or_link(self):
        parsed = vli.parse_note('# Just A Title\nNothing else notable.')
        self.assertEqual(parsed['title'], 'Just A Title')
        self.assertEqual(parsed['outbound'], [])


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.entries = {
            'a.md': vli.parse_note('# A'),
            'folder/b.md': vli.parse_note('---\naliases: [Bee]\n---\n# B'),
            'c.md': vli.parse_note('# C'),
            'dup/a.md': vli.parse_note('# A dup'),
        }
        self.lookup = vli.build_lookup(self.entries)

    def test_basename_resolution(self):
        self.assertEqual(vli.resolve_wiki('c', self.lookup), ['c.md'])

    def test_alias_resolution(self):
        self.assertEqual(vli.resolve_wiki('Bee', self.lookup), ['folder/b.md'])

    def test_ambiguous_basename_returns_every_candidate_not_a_guess(self):
        candidates = set(vli.resolve_wiki('a', self.lookup))
        self.assertEqual(candidates, {'a.md', 'dup/a.md'})

    def test_explicit_path_target_resolves_from_vault_root(self):
        self.assertEqual(vli.resolve_wiki('folder/b', self.lookup), ['folder/b.md'])

    def test_unresolved_target_is_empty_not_a_guess(self):
        self.assertEqual(vli.resolve_wiki('Nonexistent', self.lookup), [])

    def test_relative_markdown_link_resolves_from_the_source_notes_directory(self):
        link = {'kind': 'md', 'target': '../c.md'}
        self.assertEqual(vli.resolve_md('../c.md', 'folder/b.md', self.lookup), ['c.md'])
        self.assertEqual(vli.resolve(link, 'folder/b.md', self.lookup), ['c.md'])

    def test_relative_markdown_link_is_url_decoded(self):
        self.entries['my note.md'] = vli.parse_note('# space')
        lookup = vli.build_lookup(self.entries)
        self.assertEqual(vli.resolve_md('my%20note.md', 'a.md', lookup), ['my note.md'])


class BacklinksTests(unittest.TestCase):
    def test_linked_backlink_is_found_and_ambiguous_is_kept_separate(self):
        entries = {
            'target.md': vli.parse_note('# Target'),
            'dup/target.md': vli.parse_note('# Target too'),
            'linker.md': vli.parse_note('See [[Target]] for detail.'),  # ambiguous: two "target" basenames
            'a.md': vli.parse_note('# A'),
            'exact.md': vli.parse_note('See [target.md](target.md).'),
        }
        result = vli.backlinks(entries, 'target.md')
        self.assertEqual([row['path'] for row in result['linked']], ['exact.md'])
        self.assertEqual([row['path'] for row in result['ambiguous']], ['linker.md'])

    def test_embed_is_flagged_in_the_backlink_row(self):
        entries = {'pic-holder.md': vli.parse_note('![[photo.png]]'), 'photo.png': {'outbound': [], 'aliases': []}}
        result = vli.backlinks(entries, 'photo.png')
        self.assertTrue(result['linked'][0]['embed'])

    def test_a_note_does_not_backlink_itself(self):
        entries = {'self.md': vli.parse_note('[[self]] refers to itself')}
        result = vli.backlinks(entries, 'self.md')
        self.assertEqual(result['linked'], [])

    def test_unlinked_mentions_finds_plain_text_name_without_a_link(self):
        entries = {
            'robin.md': vli.parse_note('---\naliases: [Bob]\n---\n# Robin'),
            'diary.md': vli.parse_note('Had lunch with Robin today, no link written.'),
            'other.md': vli.parse_note('Nothing relevant here.'),
            'linked.md': vli.parse_note('[[Robin]] came by.'),
        }
        mentions = {row['path'] for row in vli.unlinked_mentions(entries, 'robin.md')}
        self.assertEqual(mentions, {'diary.md'})  # linked.md is excluded: it has a real link

    def test_unresolved_links_are_reported(self):
        entries = {'a.md': vli.parse_note('[[Nowhere]] and [missing](missing.md)')}
        rows = vli.unresolved(entries)
        targets = {(r['path'], r['target']) for r in rows}
        self.assertEqual(targets, {('a.md', 'Nowhere'), ('a.md', 'missing.md')})


class SearchTests(unittest.TestCase):
    def test_search_matches_title_path_and_body_case_insensitively(self):
        entries = {
            'notes/Weekend Plans.md': vli.parse_note('# Weekend Plans\nGoing hiking.'),
            'other.md': vli.parse_note('# Other\nNothing related.'),
        }
        self.assertEqual({m['path'] for m in vli.search(entries, 'hiking')}, {'notes/Weekend Plans.md'})
        self.assertEqual({m['path'] for m in vli.search(entries, 'WEEKEND')}, {'notes/Weekend Plans.md'})

    def test_empty_query_returns_nothing(self):
        self.assertEqual(vli.search({'a.md': vli.parse_note('# A')}, ''), [])


class BuildIntegrationTests(unittest.TestCase):
    """Through the real filesystem and kit/app/vault.files()'s authorization boundary."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.c = companion(Path(self.tmp.name))

    def write(self, rel, text):
        path = self.c.vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def test_build_indexes_notes_and_is_incremental(self):
        self.write('a.md', '[[b]]')
        self.write('b.md', '# B')
        entries, incomplete = vli.build(self.c)
        self.assertFalse(incomplete)
        self.assertEqual(set(entries), {'a.md', 'b.md'})
        cached_sig = entries['b.md']['sig']
        # Rebuilding without touching b.md must not re-parse it (same cached signature).
        entries2, _ = vli.build(self.c)
        self.assertEqual(entries2['b.md']['sig'], cached_sig)

    def test_a_removed_note_drops_out_of_the_index(self):
        path = self.write('gone.md', '# Gone')
        vli.build(self.c)
        path.unlink()
        entries, _ = vli.build(self.c)
        self.assertNotIn('gone.md', entries)

    def test_an_edited_note_is_reparsed(self):
        path = self.write('edit.md', '# Before')
        vli.build(self.c)
        import time; time.sleep(0.01)
        path.write_text('# After', encoding='utf-8')
        entries, _ = vli.build(self.c)
        self.assertEqual(entries['edit.md']['title'], 'After')

    def test_hidden_and_excluded_paths_never_reach_the_index(self):
        self.write('.hidden/secret.md', '# Should not be indexed')
        self.write('config.yaml', 'not markdown')  # non-.md, also protected -- irrelevant either way
        entries, _ = vli.build(self.c)
        self.assertEqual(set(entries), set())

    def test_backlinks_end_to_end_through_a_real_build(self):
        self.write('robin.md', '# Robin')
        self.write('journal.md', 'Talked to [[Robin]] today.')
        entries, _ = vli.build(self.c)
        result = vli.backlinks(entries, 'robin.md')
        self.assertEqual([row['path'] for row in result['linked']], ['journal.md'])

    def test_health_reports_counts(self):
        self.write('a.md', '[[missing]]')
        report = vli.health(self.c)
        self.assertEqual(report['notes'], 1)
        self.assertEqual(report['unresolved'], 1)
        self.assertFalse(report['incomplete'])


if __name__ == '__main__':
    unittest.main()
