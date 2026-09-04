import tempfile
import unittest
from pathlib import Path

from src.sfm_parser import parse_sfm
from src.sfm_clipboard import build_sfm_range


class SfmClipboardTests(unittest.TestCase):
    def test_copies_only_sections_and_verses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MAT.sfm"
            path.write_text(
                "\\id MAT\n"
                "\\mt Mateo\n"
                "\\c 1\n"
                "\\s1 Primer subtítulo\n"
                "\\p\n"
                "\\v 1 Texto uno "
                "\\f + \\fr 1:1 \\ft Nota al pie. \\f*\n"
                "\\v 2 Texto dos.\n"
                "\\s Segundo subtítulo\n"
                "\\v 3 Texto tres.\n",
                encoding="utf-8",
            )

            doc = parse_sfm(path)
            chapter = [
                v for v in doc.verses
                if v.chapter == "1"
            ]

            copied = build_sfm_range(
                chapter,
                0,
                2,
            )

            self.assertIn("\\s1 Primer subtítulo", copied)
            self.assertIn("\\s Segundo subtítulo", copied)
            self.assertIn("\\v 1 Texto uno", copied)
            self.assertIn("\\v 2 Texto dos.", copied)
            self.assertIn("\\v 3 Texto tres.", copied)

            self.assertNotIn("\\p", copied)
            self.assertNotIn("\\f", copied)
            self.assertNotIn("\\ft", copied)
            self.assertNotIn("Nota al pie", copied)
            self.assertNotIn("[1]", copied)

    def test_range_is_inclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MRK.sfm"
            path.write_text(
                "\\id MRK\n"
                "\\mt Marcos\n"
                "\\c 1\n"
                "\\v 1 Uno.\n"
                "\\v 2 Dos.\n"
                "\\v 3 Tres.\n",
                encoding="utf-8",
            )
            doc = parse_sfm(path)

            copied = build_sfm_range(
                doc.verses,
                1,
                2,
            )

            self.assertNotIn("\\v 1", copied)
            self.assertIn("\\v 2 Dos.", copied)
            self.assertIn("\\v 3 Tres.", copied)


if __name__ == "__main__":
    unittest.main()
