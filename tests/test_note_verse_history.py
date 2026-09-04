import tempfile
import unittest
from pathlib import Path

from src.notes_parser import NotesDocument


class NoteVerseHistoryTests(unittest.TestCase):
    def test_parser_preserves_verse_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Notes_Test.xml"
            path.write_text(
                '<?xml version="1.0" encoding="utf-8"?>'
                '<CommentList>'
                '<Comment Thread="abc" User="Test" VerseRef="MRK 1:1" '
                'Language="es" Date="2026-01-01T00:00:00-05:00">'
                '<SelectedText />'
                '<StartPosition>0</StartPosition>'
                '<ContextBefore />'
                '<ContextAfter />'
                '<Status />'
                '<Type />'
                '<ConflictType>unknownConflictType</ConflictType>'
                '<Verse>\\v 1 Texto histórico.</Verse>'
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
            self.assertEqual(
                msg.verse_text,
                "\\v 1 Texto histórico.",
            )


if __name__ == "__main__":
    unittest.main()
