import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from src.note_tools import (
    apply_bulk_operation,
    search_documents,
)
from src.notes_parser import NotesDocument


SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<CommentList>
  <Comment Thread="t1" User="wilson largo" VerseRef="2CO 2:1" Language="es" Date="2026-09-01T10:00:00-05:00">
    <SelectedText />
    <StartPosition>0</StartPosition>
    <ContextBefore />
    <ContextAfter />
    <Status />
    <Type />
    <ConflictType>unknownConflictType</ConflictType>
    <Verse>\\v 1 Texto uno.</Verse>
    <AssignedUser>Team</AssignedUser>
    <ReplyToUser>Team</ReplyToUser>
    <HideInTextWindow>false</HideInTextWindow>
    <Contents>
      <p>COM: Se conserva la idea principal.</p>
      <p />
      <p>IndS: 90 %</p>
    </Contents>
  </Comment>
  <Comment Thread="t2" User="wilson largo" VerseRef="2CO 2:2" Language="es" Date="2026-09-01T10:01:00-05:00">
    <SelectedText />
    <StartPosition>0</StartPosition>
    <ContextBefore />
    <ContextAfter />
    <Status />
    <Type />
    <ConflictType>unknownConflictType</ConflictType>
    <Verse>\\v 2 Texto dos.</Verse>
    <AssignedUser>Team</AssignedUser>
    <ReplyToUser>Team</ReplyToUser>
    <HideInTextWindow>false</HideInTextWindow>
    <Contents>
      <p>COM: Se conserva que la capacidad no está clara. Debe revisarse.</p>
      <p />
      <p>IndS: 84 %</p>
    </Contents>
  </Comment>
</CommentList>
"""


class NoteToolsTests(unittest.TestCase):
    def make_doc(self):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "Notes_wilson largo.xml"
        path.write_text(
            SAMPLE,
            encoding="utf-8",
        )
        return (
            tmp,
            path,
            NotesDocument(
                path,
                "wilson largo",
            ),
        )

    def test_delete_comment_matching_90_percent(self):
        tmp, path, doc = self.make_doc()
        try:
            pattern = r"\bIndS:\s*90\s*%"
            hits = search_documents(
                [doc],
                pattern,
                operation="delete_comment",
            )
            self.assertEqual(
                len(hits),
                1,
            )
            self.assertEqual(
                hits[0].verse_ref,
                "2CO.2.1",
            )

            result = apply_bulk_operation(
                doc,
                hits,
                pattern,
                "delete_comment",
            )

            root = ET.parse(path).getroot()
            comments = root.findall(
                "Comment"
            )
            self.assertEqual(
                len(comments),
                1,
            )
            self.assertEqual(
                comments[0].attrib["Thread"],
                "t2",
            )
            self.assertEqual(
                result.deleted_comments,
                1,
            )
            self.assertIsNotNone(
                result.backup_path
            )
            self.assertTrue(
                result.backup_path.exists()
            )
        finally:
            tmp.cleanup()

    def test_delete_individual_percentage_paragraphs(self):
        tmp, path, doc = self.make_doc()
        try:
            pattern = (
                r"^\s*IndS:\s*\d{1,3}"
                r"(?:[.,]\d+)?\s*%\s*$"
            )
            hits = search_documents(
                [doc],
                pattern,
                operation="delete_paragraph",
            )
            self.assertEqual(
                len(hits),
                2,
            )

            result = apply_bulk_operation(
                doc,
                hits,
                pattern,
                "delete_paragraph",
            )

            root = ET.parse(path).getroot()
            all_p = [
                "".join(p.itertext())
                for p in root.findall(
                    ".//Contents/p"
                )
            ]
            self.assertFalse(
                any(
                    "IndS:" in value
                    for value in all_p
                )
            )
            self.assertEqual(
                result.changed_paragraphs,
                2,
            )
        finally:
            tmp.cleanup()

    def test_remove_phrase_until_next_period(self):
        tmp, path, doc = self.make_doc()
        try:
            pattern = (
                r"Se\ conserva\ que\ la\ capacidad"
                r"[^.]*\."
            )
            hits = search_documents(
                [doc],
                pattern,
                operation="replace",
            )
            self.assertEqual(
                len(hits),
                1,
            )

            apply_bulk_operation(
                doc,
                hits,
                pattern,
                "replace",
                replacement="",
            )

            root = ET.parse(path).getroot()
            t2 = next(
                c
                for c in root.findall(
                    "Comment"
                )
                if c.attrib["Thread"] == "t2"
            )
            text = "\n".join(
                "".join(p.itertext())
                for p in t2.findall(
                    "./Contents/p"
                )
            )

            self.assertNotIn(
                "Se conserva que la capacidad",
                text,
            )
            self.assertIn(
                "Debe revisarse.",
                text,
            )
        finally:
            tmp.cleanup()

    def test_search_can_span_multiple_documents(self):
        tmp1, path1, doc1 = self.make_doc()
        tmp2 = tempfile.TemporaryDirectory()
        try:
            path2 = Path(
                tmp2.name
            ) / "Notes_Nicolas.xml"
            path2.write_text(
                SAMPLE.replace(
                    "wilson largo",
                    "Nicolas",
                ),
                encoding="utf-8",
            )
            doc2 = NotesDocument(
                path2,
                "Nicolas",
            )

            hits = search_documents(
                [doc1, doc2],
                r"IndS:",
                operation="search",
            )
            self.assertEqual(
                len(hits),
                4,
            )
            self.assertEqual(
                {hit.owner for hit in hits},
                {
                    "wilson largo",
                    "Nicolas",
                },
            )
        finally:
            tmp1.cleanup()
            tmp2.cleanup()


if __name__ == "__main__":
    unittest.main()
