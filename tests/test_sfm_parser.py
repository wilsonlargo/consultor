import tempfile
import unittest
from pathlib import Path

from src.sfm_parser import parse_sfm


class SfmParserTests(unittest.TestCase):
    def test_basic_sfm(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MRK.sfm"
            path.write_text(
                "\\id MRK\n"
                "\\mt Marcos\n"
                "\\c 1\n"
                "\\v 1 Texto uno.\n"
                "\\v 2 Texto dos.\n",
                encoding="utf-8",
            )
            doc = parse_sfm(path)
            self.assertEqual(doc.book, "MRK")
            self.assertEqual(doc.title, "Marcos")
            self.assertEqual(len(doc.verses), 2)
            self.assertEqual(doc.verses[0].reference, "MRK.1.1")

    def test_section_and_footnote(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MAT.sfm"
            path.write_text(
                "\\id MAT\n"
                "\\mt Mateo\n"
                "\\c 1\n"
                "\\s Nacimiento de Jesús\n"
                "\\v 1 Texto principal "
                "\\f + \\fr 1:1 \\ft Esta es la nota al pie. \\f* "
                "continúa el versículo.\n"
                "\\v 2 Segundo versículo.\n",
                encoding="utf-8",
            )
            doc = parse_sfm(path)

            self.assertEqual(doc.title, "Mateo")
            v1 = doc.verses[0]
            self.assertEqual(v1.subtitles, ["Nacimiento de Jesús"])
            self.assertNotIn("\\f", v1.text)
            self.assertNotIn("Esta es la nota al pie", v1.text)
            self.assertIn("[1]", v1.text)
            self.assertEqual(len(v1.footnotes), 1)
            self.assertEqual(
                v1.footnotes[0].text,
                "Esta es la nota al pie.",
            )

    def test_section_not_appended_to_previous_verse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MRK.sfm"
            path.write_text(
                "\\id MRK\n"
                "\\mt Marcos\n"
                "\\c 1\n"
                "\\v 1 Primer texto.\n"
                "\\s Otra sección\n"
                "\\v 2 Segundo texto.\n",
                encoding="utf-8",
            )
            doc = parse_sfm(path)
            self.assertEqual(doc.verses[0].subtitles, [])
            self.assertEqual(doc.verses[1].subtitles, ["Otra sección"])


if __name__ == "__main__":
    unittest.main()
