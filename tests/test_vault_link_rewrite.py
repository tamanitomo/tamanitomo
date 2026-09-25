"""Pure link-rewrite functions for LINK-06 (link-aware rename/move). No disk I/O --
these operate directly on strings, same pattern as parse_note's own tests."""
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from kit.app import vault_link_index as vli


def lookup_for(*rels, aliases=None):
    entries = {rel: {'aliases': (aliases or {}).get(rel, [])} for rel in rels}
    return vli.build_lookup(entries)


class InboundRewriteTests(unittest.TestCase):
    def test_wikilink_and_mdlink_both_rewritten(self):
        lookup = lookup_for('notes/Old Name.md')
        text = '[[Old Name]] and a link [see](Old%20Name.md) here.\n'
        new_text, count = vli.rewrite_inbound_links(text, 'notes/Old Name.md', 'notes/New Name.md', 'notes/Other.md', lookup)
        self.assertEqual(new_text, '[[New Name]] and a link [see](New%20Name.md) here.\n')
        self.assertEqual(count, 2)

    def test_relative_mdlink_from_a_subfolder(self):
        lookup = lookup_for('notes/Old Name.md', 'notes/sub/Deep.md')
        text = 'see [here](../Old%20Name.md)\n'
        new_text, count = vli.rewrite_inbound_links(text, 'notes/Old Name.md', 'notes/New Name.md', 'notes/sub/Deep.md', lookup)
        self.assertEqual(new_text, 'see [here](../New%20Name.md)\n')
        self.assertEqual(count, 1)

    def test_ambiguous_name_is_never_rewritten(self):
        lookup = lookup_for('a/Note.md', 'b/Note.md')
        text = '[[Note]]\n'
        new_text, count = vli.rewrite_inbound_links(text, 'a/Note.md', 'a/Renamed.md', 'src.md', lookup)
        self.assertEqual(new_text, text)
        self.assertEqual(count, 0)

    def test_embed_marker_heading_block_and_label_survive(self):
        lookup = lookup_for('notes/Pic Note.md')
        text = '![[Pic Note]] and ![[Pic Note#Section^blk|Label Text]]\n'
        new_text, count = vli.rewrite_inbound_links(text, 'notes/Pic Note.md', 'notes/New Pic.md', 'src.md', lookup)
        self.assertEqual(new_text, '![[New Pic]] and ![[New Pic#Section^blk|Label Text]]\n')
        self.assertEqual(count, 2)

    def test_crlf_is_preserved(self):
        lookup = lookup_for('notes/Pic Note.md')
        text = '[[Pic Note]]\r\n[[Pic Note]]\r\n'
        new_text, count = vli.rewrite_inbound_links(text, 'notes/Pic Note.md', 'notes/New Pic.md', 'src.md', lookup)
        self.assertEqual(new_text, '[[New Pic]]\r\n[[New Pic]]\r\n')
        self.assertEqual(count, 2)

    def test_path_style_wikilink_keeps_its_own_md_suffix_convention(self):
        lookup = lookup_for('folder/Target.md')
        text = '[[folder/Target.md]] and [[folder/Target]]\n'
        new_text, count = vli.rewrite_inbound_links(text, 'folder/Target.md', 'moved/Target2.md', 'src.md', lookup)
        self.assertEqual(new_text, '[[moved/Target2.md]] and [[moved/Target2]]\n')
        self.assertEqual(count, 2)

    def test_fenced_code_and_inline_code_spans_are_never_touched(self):
        lookup = lookup_for('notes/Old Name.md')
        text = '```\n[[Old Name]]\n```\nprose `[[Old Name]]` end [[Old Name]] real\n'
        new_text, count = vli.rewrite_inbound_links(text, 'notes/Old Name.md', 'notes/New Name.md', 'src.md', lookup)
        self.assertEqual(new_text, '```\n[[Old Name]]\n```\nprose `[[Old Name]]` end [[New Name]] real\n')
        self.assertEqual(count, 1)

    def test_unrelated_links_are_left_alone(self):
        lookup = lookup_for('notes/Old Name.md', 'notes/Other.md')
        text = '[[Other]] stays put.\n'
        new_text, count = vli.rewrite_inbound_links(text, 'notes/Old Name.md', 'notes/New Name.md', 'src.md', lookup)
        self.assertEqual(new_text, text)
        self.assertEqual(count, 0)

    def test_external_links_are_ignored(self):
        lookup = lookup_for('notes/Old Name.md')
        text = '[site](https://example.com/Old%20Name.md)\n'
        new_text, count = vli.rewrite_inbound_links(text, 'notes/Old Name.md', 'notes/New Name.md', 'src.md', lookup)
        self.assertEqual(new_text, text)
        self.assertEqual(count, 0)

    def test_no_trailing_newline_round_trips(self):
        lookup = lookup_for('notes/Old Name.md')
        text = '[[Old Name]]'
        new_text, count = vli.rewrite_inbound_links(text, 'notes/Old Name.md', 'notes/New Name.md', 'src.md', lookup)
        self.assertEqual(new_text, '[[New Name]]')
        self.assertEqual(count, 1)


class OwnMoveRewriteTests(unittest.TestCase):
    def test_relative_href_recomputed_after_a_folder_change(self):
        lookup = lookup_for('notes/Old Name.md', 'notes/Other.md')
        text = 'See [other](Other.md) for more.\n'
        new_text, count = vli.rewrite_own_relative_links(text, 'notes/Old Name.md', 'archive/New Name.md', lookup)
        self.assertEqual(new_text, 'See [other](../notes/Other.md) for more.\n')
        self.assertEqual(count, 1)

    def test_rename_in_place_no_folder_change_needs_no_href_rewrite(self):
        lookup = lookup_for('notes/Old Name.md', 'notes/Other.md')
        text = 'See [other](Other.md) for more.\n'
        new_text, count = vli.rewrite_own_relative_links(text, 'notes/Old Name.md', 'notes/New Name.md', lookup)
        self.assertEqual(new_text, text)
        self.assertEqual(count, 0)

    def test_wikilinks_in_the_moved_note_are_never_touched(self):
        lookup = lookup_for('notes/Old Name.md', 'notes/Other.md')
        text = 'See [[Other]] for more.\n'
        new_text, count = vli.rewrite_own_relative_links(text, 'notes/Old Name.md', 'archive/New Name.md', lookup)
        self.assertEqual(new_text, text)
        self.assertEqual(count, 0)

    def test_absolute_style_href_is_unaffected_by_the_notes_own_move(self):
        lookup = lookup_for('notes/Old Name.md', 'notes/Other.md')
        text = 'See [other](/notes/Other.md) for more.\n'
        new_text, count = vli.rewrite_own_relative_links(text, 'notes/Old Name.md', 'archive/New Name.md', lookup)
        self.assertEqual(new_text, text)
        self.assertEqual(count, 0)


if __name__ == '__main__':
    unittest.main()
