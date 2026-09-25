"""U1 (combined review of 02f2285): implementer-added edge checks next to the reviewer's
own tests in test_phase1b_review_02f2285.py. PublicFilter compares an ASCII-folded copy
whose indices are the original string's, so Unicode text that changes length under
str.lower() must not shift a tag, split a tag, or lose an unclosed block. Synthetic only."""
import unittest

from kit.app.chat_send_routes import PublicFilter, public_text

EXPANDS = 'İ'          # İ: str.lower() gives two code points


def fragmented(raw, size):
    f = PublicFilter()
    return ''.join(f.feed(raw[i:i + size]) for i in range(0, len(raw), size)) + f.finish()


class UnicodeOffsets(unittest.TestCase):
    def test_uppercase_tags_after_expanding_characters(self):
        raw = EXPANDS * 7 + '<THINKING>private</Thinking>' + EXPANDS + ' ok'
        for size in (1, 2, 3, 5, len(raw)):
            self.assertEqual(fragmented(raw, size), EXPANDS * 8 + ' ok', size)

    def test_split_tags_and_unclosed_block_after_expanding_characters(self):
        raw = EXPANDS * 3 + 'a<reasoning>private</reasoning>b<think>still private'
        for size in (1, 4, 9, len(raw)):
            self.assertEqual(fragmented(raw, size), EXPANDS * 3 + 'ab', size)

    def test_non_ascii_text_is_returned_unchanged(self):
        text = 'Straße İ Σα K <b> \U0001f600 <thin'
        self.assertEqual(public_text(text), text)

    def test_partial_state_stays_bounded(self):
        f = PublicFilter()
        f.feed(EXPANDS * 50 + '<think>' + EXPANDS * 5000 + '</thi')
        self.assertLessEqual(len(f.pending), len('</think>'))
        self.assertEqual(f.feed('nk>' + EXPANDS) + f.finish(), EXPANDS)


if __name__ == '__main__':
    unittest.main()
