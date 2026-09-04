import json
import tempfile
import unittest
from pathlib import Path

from src.resource_index import LocalResourceIndex


class LocalResourceIndexTests(unittest.TestCase):
    def test_indexes_files_named_by_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "MRK.1.1.md").write_text(
                "Nota local para Marcos 1:1.",
                encoding="utf-8",
            )
            (folder / "MRK_1_2.txt").write_text(
                "Nota local para Marcos 1:2.",
                encoding="utf-8",
            )

            index = LocalResourceIndex()
            files, records = index.load_folder(
                folder
            )

            self.assertEqual(files, 2)
            self.assertEqual(records, 2)
            self.assertEqual(
                index.records_for(
                    "MRK 1:1"
                )[0]["content"],
                "Nota local para Marcos 1:1.",
            )
            self.assertEqual(
                index.records_for(
                    "MRK.1.2"
                )[0]["content"],
                "Nota local para Marcos 1:2.",
            )

    def test_indexes_tsv_by_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "notes.tsv").write_text(
                "Reference\tTitle\tContent\n"
                "2CO 2:7\tPerdón\tAyuda para el traductor.\n",
                encoding="utf-8",
            )

            index = LocalResourceIndex()
            index.load_folder(
                folder
            )

            records = index.records_for(
                "2CO.2.7"
            )
            self.assertEqual(
                len(records),
                1,
            )
            self.assertEqual(
                records[0]["title"],
                "Perdón",
            )
            self.assertEqual(
                records[0]["content"],
                "Ayuda para el traductor.",
            )

    def test_indexes_json_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            payload = [
                {
                    "VerseRef": "MRK 8:31",
                    "Title": "Nota",
                    "Text": "Contenido JSON",
                }
            ]
            (folder / "resource.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            index = LocalResourceIndex()
            index.load_folder(
                folder
            )

            records = index.records_for(
                "MRK.8.31"
            )
            self.assertEqual(
                records[0]["content"],
                "Contenido JSON",
            )


if __name__ == "__main__":
    unittest.main()
