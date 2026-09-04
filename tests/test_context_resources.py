import unittest

from src.context_resources import (
    parse_darby_html,
    parse_helloao_commentary,
    provider_by_key,
    providers_for_group,
)


class ContextResourceParserTests(unittest.TestCase):
    def test_open_provider_groups_are_explicit(self):
        notes = {
            provider.key
            for provider in providers_for_group(
                "notes"
            )
        }
        comments = {
            provider.key
            for provider in providers_for_group(
                "commentary"
            )
        }

        self.assertEqual(
            notes,
            {
                "darby-translation-notes",
                "tyndale",
            },
        )
        self.assertEqual(
            comments,
            {
                "adam-clarke",
                "jamieson-fausset-brown",
                "john-calvin",
                "john-gill",
                "keil-delitzsch",
                "matthew-henry",
            },
        )
        self.assertEqual(
            provider_by_key(
                "darby-translation-notes"
            ).license_name,
            "Dominio público",
        )
        self.assertEqual(
            provider_by_key(
                "tyndale"
            ).license_name,
            "CC BY-SA 4.0",
        )

    def test_parses_helloao_standard_commentary(self):
        payload = {
            "commentary": {
                "id": "tyndale",
                "name": "Tyndale Open Study Notes",
                "licenseUrl": (
                    "https://creativecommons.org/"
                    "licenses/by-sa/4.0/"
                ),
            },
            "book": {
                "id": "1CO",
            },
            "chapter": {
                "number": 3,
                "content": [
                    {
                        "type": "verse",
                        "number": 1,
                        "content": [
                            "First note.",
                            {
                                "text": "More context."
                            },
                        ],
                    },
                    {
                        "type": "verse",
                        "number": 2,
                        "content": [
                            {
                                "content": [
                                    "Second note."
                                ]
                            }
                        ],
                    },
                ],
            },
        }

        notes, meta = (
            parse_helloao_commentary(
                payload,
                fallback_book="1CO",
                fallback_chapter=3,
            )
        )

        self.assertEqual(
            notes[0]["reference"],
            "1CO.3.1",
        )
        self.assertIn(
            "First note.",
            notes[0]["text"],
        )
        self.assertIn(
            "More context.",
            notes[0]["text"],
        )
        self.assertEqual(
            notes[1]["reference"],
            "1CO.3.2",
        )
        self.assertEqual(
            meta["provider_name"],
            "Tyndale Open Study Notes",
        )

    def test_parses_darby_only_for_requested_chapter(self):
        sample = """
        <html><body>
          <nav>navigation text</nav>
          <h1>Colossians 3</h1>
          <p>2:20 old chapter note that must be ignored.</p>
          <h3>Colossians 3:12</h3>
          <p>3:12 on (a-2) The aorist.</p>
          <h3>Colossians 3:23</h3>
          <p>3:23 heartily, (k-7) Ek psuches, lit. from the soul.</p>
          <footer>site footer</footer>
        </body></html>
        """

        notes = parse_darby_html(
            sample,
            book="COL",
            chapter=3,
        )

        self.assertEqual(
            [note["reference"] for note in notes],
            [
                "COL.3.12",
                "COL.3.23",
            ],
        )
        self.assertIn(
            "aorist",
            notes[0]["text"],
        )
        self.assertNotIn(
            "old chapter",
            " ".join(
                note["text"]
                for note in notes
            ),
        )


if __name__ == "__main__":
    unittest.main()
