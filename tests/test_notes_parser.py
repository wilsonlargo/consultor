import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from src.notes_parser import NotesDocument


SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<CommentList>
  <Comment Thread="abc123" User="Consultor" VerseRef="MRK 1:1" Language="es" Date="2026-01-01T10:00:00-05:00">
    <SelectedText>palabra</SelectedText>
    <StartPosition>1</StartPosition>
    <ContextBefore />
    <ContextAfter />
    <Status></Status>
    <Type></Type>
    <ConflictType>unknownConflictType</ConflictType>
    <Verse />
    <AssignedUser>Traductor</AssignedUser>
    <ReplyToUser>Traductor</ReplyToUser>
    <HideInTextWindow>false</HideInTextWindow>
    <Contents>
      <p>COM: Primera línea</p>
      <p />
      <p>PT: Pregunta</p>
    </Contents>
  </Comment>
</CommentList>
"""


class NotesParserTests(unittest.TestCase):
    def make_doc(self):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "Notes_Consultor.xml"
        path.write_text(SAMPLE, encoding="utf-8")
        return tmp, path, NotesDocument(path, "Consultor")

    def test_reads_paragraph_contents(self):
        tmp, path, doc = self.make_doc()
        try:
            thread = doc.thread_by_id("abc123")
            self.assertIsNotNone(thread)
            self.assertEqual(
                thread.messages[0].contents,
                "COM: Primera línea\n\nPT: Pregunta",
            )
        finally:
            tmp.cleanup()

    def test_update_message_keeps_paragraph_model(self):
        tmp, path, doc = self.make_doc()
        try:
            thread = doc.thread_by_id("abc123")
            msg = thread.messages[0]
            doc.update_message_contents(
                msg,
                "COM: Nuevo\n\nSUG:\nA) Opción",
            )

            tree = ET.parse(path)
            contents = tree.getroot().find("Comment/Contents")
            ps = contents.findall("p")
            self.assertEqual(len(ps), 4)
            self.assertEqual(ps[0].text, "COM: Nuevo")
            self.assertIsNone(ps[1].text)
            self.assertEqual(ps[2].text, "SUG:")
            self.assertEqual(ps[3].text, "A) Opción")
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
