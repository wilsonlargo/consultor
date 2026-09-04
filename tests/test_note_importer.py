import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from src.note_importer import (
    import_comments,
    parse_comment_xml,
)
from src.notes_parser import NotesDocument


SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<CommentList>
  <Comment Thread="chat001" User="wilson largo" VerseRef="2CO 2:1" Language="es" Date="2026-09-01T10:00:00-05:00">
    <SelectedText />
    <StartPosition>0</StartPosition>
    <ContextBefore />
    <ContextAfter>\\v 2 Texto siguiente</ContextAfter>
    <Status />
    <Type />
    <ConflictType>unknownConflictType</ConflictType>
    <Verse>\\v 1 Texto</Verse>
    <AssignedUser>Team</AssignedUser>
    <ReplyToUser>Team</ReplyToUser>
    <HideInTextWindow>false</HideInTextWindow>
    <Contents>
      <p>COM: Comentario</p>
      <p />
      <p>PT: Pregunta</p>
    </Contents>
  </Comment>
</CommentList>
"""


class NoteImporterTests(unittest.TestCase):
    def make_destination(self):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "Notes_wilson largo.xml"
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?><CommentList />',
            encoding="utf-8",
        )
        return tmp, path, NotesDocument(path, "wilson largo")

    def test_accepts_markdown_code_fence(self):
        preview = parse_comment_xml(
            "```xml\\n" + SAMPLE + "\\n```"
        )
        self.assertEqual(preview.count, 1)
        self.assertEqual(preview.verse_refs, ["2CO 2:1"])

    def test_import_preserves_contents_and_metadata(self):
        tmp, path, doc = self.make_destination()
        try:
            preview = parse_comment_xml(SAMPLE)
            result = import_comments(
                destination_document=doc,
                preview=preview,
                existing_thread_ids=set(),
                override_target=None,
                force_user="wilson largo",
                skip_duplicates=True,
            )
            self.assertEqual(result.imported, 1)

            comment = ET.parse(path).getroot().find("Comment")
            self.assertEqual(comment.attrib["Thread"], "chat001")
            self.assertEqual(comment.attrib["VerseRef"], "2CO 2:1")
            self.assertEqual(comment.findtext("AssignedUser"), "Team")
            ps = comment.find("Contents").findall("p")
            self.assertEqual(ps[0].text, "COM: Comentario")
            self.assertIsNone(ps[1].text)
            self.assertEqual(ps[2].text, "PT: Pregunta")
        finally:
            tmp.cleanup()

    def test_override_target_updates_assigned_and_reply(self):
        tmp, path, doc = self.make_destination()
        try:
            preview = parse_comment_xml(SAMPLE)
            import_comments(
                destination_document=doc,
                preview=preview,
                existing_thread_ids=set(),
                override_target="Nicolas Sanchez Procopio",
                force_user="wilson largo",
                skip_duplicates=True,
            )
            comment = ET.parse(path).getroot().find("Comment")
            self.assertEqual(
                comment.findtext("AssignedUser"),
                "Nicolas Sanchez Procopio",
            )
            self.assertEqual(
                comment.findtext("ReplyToUser"),
                "Nicolas Sanchez Procopio",
            )
        finally:
            tmp.cleanup()

    def test_duplicate_thread_is_skipped(self):
        tmp, path, doc = self.make_destination()
        try:
            preview = parse_comment_xml(SAMPLE)
            result = import_comments(
                destination_document=doc,
                preview=preview,
                existing_thread_ids={"chat001"},
                override_target=None,
                force_user="wilson largo",
                skip_duplicates=True,
            )
            self.assertEqual(result.imported, 0)
            self.assertEqual(result.skipped_duplicates, 1)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
