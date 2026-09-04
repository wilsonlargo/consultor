import tempfile
import unittest
from pathlib import Path

from src.native_resources import (
    NativeResourceStore,
)


class ContextCacheTests(unittest.TestCase):
    def test_context_chapter_cache_is_reference_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = NativeResourceStore(
                Path(tmp) / "resources.sqlite3"
            )

            count = (
                store.replace_context_chapter(
                    "darby-translation-notes",
                    "1CO",
                    3,
                    [
                        {
                            "reference": "1CO.3.1",
                            "heading": "word",
                            "text": "First note",
                        },
                        {
                            "reference": "1CO.3.1",
                            "heading": "other",
                            "text": "Second note",
                        },
                        {
                            "reference": "1CO.3.5",
                            "text": "Another verse",
                        },
                    ],
                    provider_name=(
                        "Darby Translation Notes"
                    ),
                    source_url="https://example.test/",
                    license_name="Dominio público",
                    license_url="https://example.test/license",
                    fetched_at="2026-09-04T00:00:00+00:00",
                )
            )

            self.assertEqual(
                count,
                3,
            )
            self.assertTrue(
                store.context_chapter_cached(
                    "darby-translation-notes",
                    "1CO",
                    3,
                )
            )

            rows = store.context_notes_for(
                "darby-translation-notes",
                "1CO.3.1",
            )
            self.assertEqual(
                len(rows),
                2,
            )
            self.assertEqual(
                rows[0]["text"],
                "First note",
            )
            self.assertEqual(
                rows[1]["text"],
                "Second note",
            )

            meta = store.context_chapter_meta(
                "darby-translation-notes",
                "1CO",
                3,
            )
            self.assertEqual(
                meta["license_name"],
                "Dominio público",
            )


if __name__ == "__main__":
    unittest.main()
