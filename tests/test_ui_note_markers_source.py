import unittest
from pathlib import Path


class UiNoteMarkerSourceTests(unittest.TestCase):
    def test_note_marker_and_bible_toggle_present(self):
        path = Path(__file__).parents[1] / "src" / "main_window.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn('"🚩"', text)
        self.assertIn('def _refresh_note_markers', text)
        self.assertIn('"📖"', text)
        self.assertIn('self.bible_dock.setVisible(', text)
        self.assertIn('def copy_sfm_range_to_clipboard', text)


if __name__ == "__main__":
    unittest.main()
