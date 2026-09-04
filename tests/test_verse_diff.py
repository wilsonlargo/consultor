import unittest

from src.verse_diff import diff_html


class VerseDiffTests(unittest.TestCase):
    def test_marks_changed_words_in_both_versions(self):
        old_html, new_html = diff_html(
            r"\v 1 Jesús vino a la casa.",
            r"\v 1 Jesús vino al pueblo.",
        )

        self.assertIn("background:#f8dddd", old_html)
        self.assertIn("background:#dff2e2", new_html)
        self.assertIn("casa", old_html)
        self.assertIn("pueblo", new_html)

    def test_equal_text_has_no_change_spans(self):
        old_html, new_html = diff_html(
            "Texto igual.",
            "Texto igual.",
        )

        self.assertNotIn("<span", old_html)
        self.assertNotIn("<span", new_html)


if __name__ == "__main__":
    unittest.main()
