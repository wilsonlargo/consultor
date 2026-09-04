import tempfile
import unittest
from pathlib import Path

from src.notes_parser import NotesDocument


class NoteAnchorMetadataTests(unittest.TestCase):
    def test_start_position_and_context_are_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Notes_Test.xml"
            path.write_text(
                '<?xml version="1.0" encoding="utf-8"?>'
                '<CommentList>'
                '<Comment Thread="abc" User="Test" VerseRef="MRK 1:1" '
                'Language="es" Date="2026-01-01T00:00:00-05:00">'
                '<SelectedText>Donde</SelectedText>'
                '<StartPosition>5</StartPosition>'
                '<ContextBefore>\\v 1 </ContextBefore>'
                '<ContextAfter> comenzó</ContextAfter>'
                '<Status />'
                '<Type />'
                '<ConflictType>unknownConflictType</ConflictType>'
                '<Verse>\\v 1 Donde comenzó.</Verse>'
                '<AssignedUser>Team</AssignedUser>'
                '<ReplyToUser>Team</ReplyToUser>'
                '<HideInTextWindow>false</HideInTextWindow>'
                '<Contents><p>COM: Nota</p></Contents>'
                '</Comment>'
                '</CommentList>',
                encoding="utf-8",
            )

            doc = NotesDocument(path, "Test")
            msg = doc.thread_by_id("abc").messages[0]

            self.assertEqual(msg.start_position, 5)
            self.assertEqual(msg.context_before, "\\v 1 ")
            self.assertEqual(msg.context_after, " comenzó")


if __name__ == "__main__":
    unittest.main()
