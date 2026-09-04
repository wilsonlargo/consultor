import tempfile
import unittest
from pathlib import Path

from src.project_loader import load_project


class ProjectLoaderTests(unittest.TestCase):
    def test_project_folder_discovers_sfm_and_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "MRK.sfm").write_text(
                "\\id MRK\n\\c 1\n\\v 1 Texto\n",
                encoding="utf-8",
            )
            (folder / "Notes_copia(1).xml").write_text(
                '<?xml version="1.0"?><CommentList>'
                '<Comment Thread="x" User="Wilson" VerseRef="MRK 1:1" '
                'Language="es" Date="2026-01-01T00:00:00-05:00">'
                '<Contents>Hola</Contents></Comment></CommentList>',
                encoding="utf-8",
            )

            project = load_project(folder)
            self.assertEqual(len(project.texts), 1)
            self.assertEqual(len(project.notes_files), 1)
            self.assertEqual(project.notes_files[0].owner, "Wilson")


if __name__ == "__main__":
    unittest.main()
