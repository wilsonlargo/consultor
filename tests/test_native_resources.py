import json
import tempfile
import unittest
from pathlib import Path

from src.native_resources import (
    NativeResourceStore,
    describe_morphology,
    normalize_crossref_target,
    normalize_external_reference,
)


class NativeResourceStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.store = NativeResourceStore(
            self.folder / "resources.sqlite3"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def write_json(self, name, data):
        path = self.folder / name
        path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def test_imports_translation_tokens_and_lexicon(self):
        translation = self.write_json(
            "SBLGNT.json",
            {
                "language": "grc",
                "copyright": "CC BY test",
                "books": [
                    {
                        "abbreviation": "MRK",
                        "chapters": [
                            {
                                "number": 1,
                                "verses": [
                                    {
                                        "number": 1,
                                        "text": "Ἀρχὴ τοῦ εὐαγγελίου",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        )
        tokens = self.write_json(
            "tokens.json",
            {
                "tokens": [
                    {
                        "book": "MRK",
                        "chapter": 1,
                        "verse": 1,
                        "position": 1,
                        "surface_form": "Ἀρχὴ",
                        "strongs_id": "G0746",
                        "morph_code": "N-NSF",
                    }
                ]
            },
        )
        lexicon = self.write_json(
            "lexicon.json",
            {
                "entries": [
                    {
                        "strongs_id": "G746",
                        "language": "grc",
                        "lemma": "ἀρχή",
                        "transliteration": "arche",
                        "gloss": "beginning",
                        "definition": "beginning, origin",
                    }
                ]
            },
        )

        self.assertEqual(
            self.store.import_translation_json(
                translation
            ),
            1,
        )
        self.assertEqual(
            self.store.import_tokens_json(
                tokens
            ),
            1,
        )
        self.assertEqual(
            self.store.import_lexicon_json(
                lexicon
            ),
            1,
        )

        verse = self.store.verse_text(
            "MRK.1.1"
        )
        self.assertEqual(
            verse["text"],
            "Ἀρχὴ τοῦ εὐαγγελίου",
        )

        words = self.store.words_for_verse(
            "MRK 1:1"
        )
        self.assertEqual(
            len(words),
            1,
        )
        self.assertEqual(
            words[0].strongs_id,
            "G746",
        )
        self.assertEqual(
            words[0].lemma,
            "ἀρχή",
        )
        self.assertEqual(
            words[0].gloss,
            "beginning",
        )

    def test_imports_cross_references(self):
        path = self.folder / "cross_references.txt"
        path.write_text(
            "#www.openbible.info CC-BY test\n"
            "From Verse\tTo Verse\tVotes\n"
            "Mark.1.1\tJohn.1.1\t12\n"
            "Mark.1.1\tIsa.40.3\t8\n",
            encoding="utf-8",
        )

        count = self.store.import_crossrefs(
            path
        )
        self.assertEqual(
            count,
            2,
        )

        rows = self.store.crossrefs_for(
            "MRK.1.1"
        )
        self.assertEqual(
            rows[0]["to_ref"],
            "JHN.1.1",
        )
        self.assertEqual(
            rows[0]["votes"],
            12,
        )
        self.assertEqual(
            rows[1]["to_ref"],
            "ISA.40.3",
        )

    def test_private_notes_remain_local(self):
        path = self.write_json(
            "private.json",
            {
                "translation": "TEST",
                "notes": [
                    {
                        "book": "MRK",
                        "chapter": 1,
                        "verse": 1,
                        "text": "Nota del usuario.",
                        "type": "tn",
                        "marker": "1",
                    }
                ],
            },
        )

        self.assertEqual(
            self.store.import_private_notes_json(
                path
            ),
            1,
        )

        rows = self.store.private_notes_for(
            "MRK.1.1"
        )
        self.assertEqual(
            rows[0]["text"],
            "Nota del usuario.",
        )
        self.assertEqual(
            rows[0]["note_type"],
            "tn",
        )

    def test_imports_topics_and_queries_by_verse(self):
        path = self.write_json(
            "naves.json",
            {
                "topics": [
                    {
                        "id": "creation",
                        "name": "CREATION",
                        "section": "C",
                        "see_also": "WORLD",
                        "verses": [
                            "Gen.1.1",
                            "John.1.1",
                        ],
                    },
                    {
                        "id": "word",
                        "name": "WORD OF GOD",
                        "section": "W",
                        "verses": [
                            {
                                "book": "JHN",
                                "chapter": 1,
                                "verse": 1
                            }
                        ],
                    },
                ]
            },
        )

        count = self.store.import_topics_json(
            path
        )
        self.assertEqual(
            count,
            3,
        )

        topics = self.store.topics_for(
            "JHN.1.1"
        )
        self.assertEqual(
            {
                row["name"]
                for row in topics
            },
            {
                "CREATION",
                "WORD OF GOD",
            },
        )

        verses = self.store.topic_verses(
            "creation"
        )
        self.assertEqual(
            {
                row["reference"]
                for row in verses
            },
            {
                "GEN.1.1",
                "JHN.1.1",
            },
        )

    def test_imports_openbible_like_places(self):
        path = self.folder / "ancient.jsonl"
        record = {
            "id": "a000001",
            "friendly_id": "Eden",
            "verses": [
                {
                    "osis": "Gen.2.8",
                    "readable": "Genesis 2:8",
                }
            ],
            "identifications": [
                {
                    "score": {
                        "time_total": 800
                    },
                    "resolutions": [
                        {
                            "lonlat": "44.12345,33.54321",
                            "type": "region",
                            "best_time_score": 700,
                            "description": '<modern id="m1">Example</modern>',
                        }
                    ],
                }
            ],
        }
        path.write_text(
            json.dumps(record)
            + "\n",
            encoding="utf-8",
        )

        count = self.store.import_places_jsonl(
            path
        )
        self.assertEqual(
            count,
            1,
        )

        places = self.store.places_for(
            "GEN.2.8"
        )
        self.assertEqual(
            len(places),
            1,
        )
        self.assertEqual(
            places[0]["name"],
            "Eden",
        )
        self.assertEqual(
            places[0]["status"],
            "identified",
        )
        self.assertAlmostEqual(
            places[0]["longitude"],
            44.12345,
        )
        self.assertAlmostEqual(
            places[0]["latitude"],
            33.54321,
        )
        self.assertEqual(
            places[0]["confidence"],
            560,
        )

        verses = self.store.place_verses(
            "a000001"
        )
        self.assertEqual(
            verses[0]["reference"],
            "GEN.2.8",
        )


    def test_reference_normalization(self):
        self.assertEqual(
            normalize_external_reference(
                "John.3.16"
            ),
            "JHN.3.16",
        )
        self.assertEqual(
            normalize_external_reference(
                "2Cor.2.7"
            ),
            "2CO.2.7",
        )
        self.assertEqual(
            normalize_crossref_target(
                "John.3.16-John.3.17"
            ),
            "JHN.3.16-17",
        )

    def test_morphology_is_explained_in_spanish(self):
        result = describe_morphology(
            "V-AAI-3S"
        )
        self.assertIn(
            "verbo",
            result,
        )
        self.assertIn(
            "aoristo",
            result,
        )
        self.assertIn(
            "activa",
            result,
        )
        self.assertIn(
            "indicativo",
            result,
        )
        self.assertIn(
            "3.ª persona",
            result,
        )
        self.assertIn(
            "singular",
            result,
        )

        noun = describe_morphology(
            "N-NSF"
        )
        self.assertIn(
            "sustantivo",
            noun,
        )
        self.assertIn(
            "nominativo",
            noun,
        )
        self.assertIn(
            "femenino",
            noun,
        )


if __name__ == "__main__":
    unittest.main()
