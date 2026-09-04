import tempfile
import unittest
from pathlib import Path

from src.notes_workspace import NotesWorkspace
from src.project_loader import NotesFile


WILSON = """<?xml version="1.0" encoding="utf-8"?>
<CommentList>
  <Comment Thread="abc" User="wilson largo" VerseRef="MRK 1:1" Language="es" Date="2018-08-15T10:00:00-05:00">
    <SelectedText>palabra</SelectedText>
    <StartPosition>5</StartPosition>
    <ContextBefore />
    <ContextAfter />
    <Status></Status>
    <Type></Type>
    <ConflictType>unknownConflictType</ConflictType>
    <Verse />
    <AssignedUser>Nicolas Sanchez Procopio</AssignedUser>
    <ReplyToUser>Nicolas Sanchez Procopio</ReplyToUser>
    <HideInTextWindow>false</HideInTextWindow>
    <Contents><p>COM: Mi nota</p></Contents>
  </Comment>
</CommentList>
"""

NICOLAS = """<?xml version="1.0" encoding="utf-8"?>
<CommentList>
  <Comment Thread="abc" User="Nicolas Sanchez Procopio" VerseRef="MRK 1:1" Language="es" Date="2018-08-16T10:00:00-05:00">
    <SelectedText>palabra</SelectedText>
    <StartPosition>5</StartPosition>
    <ContextBefore />
    <ContextAfter />
    <Status></Status>
    <Type></Type>
    <ConflictType>unknownConflictType</ConflictType>
    <Verse />
    <AssignedUser>wilson largo</AssignedUser>
    <ReplyToUser>wilson largo</ReplyToUser>
    <HideInTextWindow>false</HideInTextWindow>
    <Contents><p>Respuesta de Nicolas</p></Contents>
  </Comment>
</CommentList>
"""


class NotesWorkspaceTests(unittest.TestCase):
    def make_workspace(self):
        tmp = tempfile.TemporaryDirectory()
        folder = Path(tmp.name)
        wp = folder / "Notes_wilson largo.xml"
        np = folder / "Notes_Nicolas Sanchez Procopio.xml"
        wp.write_text(WILSON, encoding="utf-8")
        np.write_text(NICOLAS, encoding="utf-8")

        workspace = NotesWorkspace(
            [
                NotesFile(wp, "wilson largo"),
                NotesFile(np, "Nicolas Sanchez Procopio"),
            ],
            "wilson largo",
        )
        return tmp, workspace, wp, np

    def test_merges_same_thread_across_files(self):
        tmp, ws, wp, np = self.make_workspace()
        try:
            threads = ws.threads_for_reference("MRK.1.1")
            self.assertEqual(len(threads), 1)
            thread = threads[0]
            self.assertEqual(len(thread.visible_messages), 2)
            self.assertEqual(
                thread.counterpart(),
                "Nicolas Sanchez Procopio",
            )
            self.assertTrue(
                thread.has_reply_from_counterpart()
            )
        finally:
            tmp.cleanup()

    def test_reply_is_written_only_to_consultant_file(self):
        tmp, ws, wp, np = self.make_workspace()
        try:
            nicolas_before = np.read_text(encoding="utf-8")
            thread = ws.threads_for_reference("MRK.1.1")[0]

            ws.append_consultant_reply(
                thread,
                "COM: Mi seguimiento",
                "Nicolas Sanchez Procopio",
            )

            nicolas_after = np.read_text(encoding="utf-8")
            self.assertEqual(nicolas_before, nicolas_after)

            reread = NotesWorkspace(
                [
                    NotesFile(wp, "wilson largo"),
                    NotesFile(np, "Nicolas Sanchez Procopio"),
                ],
                "wilson largo",
            )
            thread2 = reread.threads_for_reference("MRK.1.1")[0]
            self.assertEqual(len(thread2.visible_messages), 3)
            self.assertEqual(
                thread2.visible_messages[-1].owner,
                "wilson largo",
            )
            self.assertEqual(
                thread2.visible_messages[-1].message.reply_to_user,
                "Nicolas Sanchez Procopio",
            )
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
