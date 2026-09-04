import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from src.sfm_parser import parse_sfm
from src.notes_workspace import NotesWorkspace
from src.project_loader import NotesFile


class AnchorCreationTests(unittest.TestCase):
    def test_start_position_matches_zero_based_sfm_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MRK.sfm"
            path.write_text(
                "\\id MRK\n"
                "\\mt Marcos\n"
                "\\c 1\n"
                "\\v 1 Donde comenzó a hablar.\n",
                encoding="utf-8",
            )
            doc = parse_sfm(path)
            anchor = doc.verses[0].anchor
            self.assertEqual(anchor.visible_text, "Donde comenzó a hablar.")
            meta = anchor.selection_metadata(0, 5)
            self.assertEqual(meta["SelectedText"], "Donde")
            self.assertEqual(meta["StartPosition"], 5)
            self.assertEqual(meta["VerseRef"], "MRK.1.1")

    def test_inline_section_uses_previous_verse_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MRK.sfm"
            path.write_text(
                "\\id MRK\n"
                "\\mt Marcos\n"
                "\\c 1\n"
                "\\v 8 Texto del verso. \\s1 Donde bautizo Jesús \\r (Mt 3.13) \\p\n"
                "\\v 9 Otro texto.\n",
                encoding="utf-8",
            )
            doc = parse_sfm(path)
            v9 = doc.verses[1]
            self.assertEqual(v9.subtitles, ["Donde bautizo Jesús"])
            target = v9.subtitle_anchors[0]
            self.assertEqual(target.reference, "MRK.1.8")

            start = target.visible_text.index("bautizo")
            meta = target.selection_metadata(start, start + len("bautizo"))
            self.assertEqual(meta["SelectedText"], "bautizo")
            self.assertEqual(
                meta["StartPosition"],
                meta["Verse"].index("bautizo"),
            )

    def test_initial_section_uses_verse_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MRK.sfm"
            path.write_text(
                "\\id MRK - Retro\n"
                "\\mt Marcos\n"
                "\\c 1\n"
                "\\s1 Juan que bautizó estuvo en la tierra seca\n"
                "\\r (Mt 3.1-12)\n"
                "\\p\n"
                "\\v 1 Primer verso.\n",
                encoding="utf-8",
            )
            doc = parse_sfm(path)
            v1 = doc.verses[0]
            self.assertEqual(
                v1.subtitles,
                ["Juan que bautizó estuvo en la tierra seca"],
            )
            target = v1.subtitle_anchors[0]
            self.assertEqual(target.reference, "MRK.1.0")
            self.assertIn("\\id MRK - Retro", target.source_text)
            self.assertIn("\\c 1", target.source_text)
            self.assertIn("\\s1", target.source_text)

    def test_create_note_writes_anchor_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            notes_path = folder / "Notes_wilson largo.xml"
            notes_path.write_text(
                '<?xml version="1.0" encoding="utf-8"?><CommentList />',
                encoding="utf-8",
            )

            workspace = NotesWorkspace(
                [NotesFile(notes_path, "wilson largo")],
                "wilson largo",
            )
            anchor = {
                "SelectedText": "Donde",
                "StartPosition": 5,
                "ContextBefore": "\\v 1 ",
                "ContextAfter": " comenzó a hablar",
                "VerseRef": "MRK.1.1",
                "Verse": "\\v 1 Donde comenzó a hablar.",
                "Kind": "verse",
            }

            thread_id = workspace.create_consultant_note(
                anchor,
                "COM: Nueva nota",
                "Team",
            )
            self.assertTrue(thread_id)

            tree = ET.parse(notes_path)
            comment = tree.getroot().find("Comment")
            self.assertEqual(comment.attrib["User"], "wilson largo")
            self.assertEqual(comment.attrib["VerseRef"], "MRK 1:1")
            self.assertEqual(comment.findtext("SelectedText"), "Donde")
            self.assertEqual(comment.findtext("StartPosition"), "5")
            self.assertEqual(comment.findtext("ContextBefore"), "\\v 1 ")
            self.assertEqual(comment.findtext("Status") or "", "")
            self.assertEqual(comment.findtext("HideInTextWindow"), "false")
            self.assertEqual(comment.findtext("AssignedUser"), "Team")
            self.assertEqual(comment.findtext("ReplyToUser"), "Team")
            self.assertEqual(
                comment.find("Contents").find("p").text,
                "COM: Nueva nota",
            )


if __name__ == "__main__":
    unittest.main()
