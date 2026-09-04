import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

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


class ResolveDeleteTests(unittest.TestCase):
    def make_workspace(self):
        tmp = tempfile.TemporaryDirectory()
        folder = Path(tmp.name)
        wp = folder / "Notes_wilson largo.xml"
        np = folder / "Notes_Nicolas Sanchez Procopio.xml"
        wp.write_text(WILSON, encoding="utf-8")
        np.write_text(NICOLAS, encoding="utf-8")
        ws = NotesWorkspace(
            [
                NotesFile(wp, "wilson largo"),
                NotesFile(np, "Nicolas Sanchez Procopio"),
            ],
            "wilson largo",
        )
        return tmp, ws, wp, np

    def test_resolve_adds_deleted_marker_and_preserves_original(self):
        tmp, ws, wp, np = self.make_workspace()
        try:
            thread = ws.threads_for_reference("MRK.1.1")[0]
            ws.resolve_thread(thread)

            tree = ET.parse(wp)
            comments = tree.getroot().findall("Comment")
            self.assertEqual(len(comments), 2)
            self.assertEqual(comments[0].findtext("Status") or "", "")
            self.assertEqual(comments[1].attrib["Thread"], "abc")
            self.assertEqual(comments[1].findtext("Status"), "deleted")

            reread = NotesWorkspace(
                [
                    NotesFile(wp, "wilson largo"),
                    NotesFile(np, "Nicolas Sanchez Procopio"),
                ],
                "wilson largo",
            )
            thread2 = reread.thread("abc")
            self.assertTrue(thread2.resolved_for_consultant())
        finally:
            tmp.cleanup()

    def test_delete_removes_only_own_selected_comment(self):
        tmp, ws, wp, np = self.make_workspace()
        try:
            nicolas_before = np.read_text(encoding="utf-8")
            thread = ws.threads_for_reference("MRK.1.1")[0]
            mine = thread.original_consultant_message()

            ws.delete_consultant_message(mine)

            wilson_tree = ET.parse(wp)
            self.assertEqual(
                len(wilson_tree.getroot().findall("Comment")),
                0,
            )
            self.assertEqual(
                np.read_text(encoding="utf-8"),
                nicolas_before,
            )
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
