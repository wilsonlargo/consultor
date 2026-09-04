import tempfile
import unittest
from pathlib import Path

from src.spellcheck_core import (
    WordListBackend,
    iter_spell_tokens,
    load_plain_wordlist,
)


class SpellcheckCoreTests(unittest.TestCase):
    def test_markers_options_references_and_sfm_are_excluded(self):
        text = (
            "COM: Esta es una sujerencia para el equipo.\n"
            "PT: revisar la palabra versiculo.\n"
            "SUG:\n"
            "A) Podrían espresarlo de otra forma.\n"
            "B) Otra alternativa.\n"
            "CONT: Comparar con 1 Corintios 3:10 y MRK.8.31.\n"
            "IndS: 85 %\n"
            "RES: pendiente.\n"
            "\\v 7 texto de prueba.\n"
        )

        words = [
            token.word
            for token in iter_spell_tokens(
                text
            )
        ]
        upper = {
            word.upper()
            for word in words
        }

        for structural in (
            "COM",
            "PT",
            "SUG",
            "CONT",
            "INDS",
            "RES",
            "A",
            "B",
            "MRK",
        ):
            self.assertNotIn(
                structural,
                upper,
            )

        self.assertNotIn(
            "Corintios",
            words,
        )
        self.assertIn(
            "sujerencia",
            words,
        )
        self.assertIn(
            "versiculo",
            words,
        )
        self.assertIn(
            "espresarlo",
            words,
        )

    def test_acronyms_are_not_checked(self):
        words = [
            token.word
            for token in iter_spell_tokens(
                "Comparar DHH NVI NTV XML CBT con esta palabra."
            )
        ]

        for acronym in (
            "DHH",
            "NVI",
            "NTV",
            "XML",
            "CBT",
        ):
            self.assertNotIn(
                acronym,
                words,
            )

        self.assertIn(
            "Comparar",
            words,
        )
        self.assertIn(
            "palabra",
            words,
        )

    def test_plain_wordlist_and_hunspell_dic_are_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)

            plain = folder / "lengua.txt"
            plain.write_text(
                "namtrik\nYukpa\n",
                encoding="utf-8",
            )

            hunspell = folder / "test.dic"
            hunspell.write_text(
                "3\n"
                "casa/AB\n"
                "camino\n"
                "perdón/XY\tpo:noun\n",
                encoding="utf-8",
            )

            self.assertEqual(
                load_plain_wordlist(
                    plain
                ),
                {
                    "namtrik",
                    "yukpa",
                },
            )
            self.assertEqual(
                load_plain_wordlist(
                    hunspell
                ),
                {
                    "casa",
                    "camino",
                    "perdón",
                },
            )

    def test_wordlist_backend_checks_and_suggests(self):
        backend = WordListBackend(
            {
                "sugerencia",
                "versículo",
                "expresarlo",
            }
        )

        self.assertTrue(
            backend.lookup(
                "Sugerencia"
            )
        )
        self.assertFalse(
            backend.lookup(
                "sujerencia"
            )
        )

        suggestions = backend.suggest(
            "sujerencia"
        )
        self.assertIn(
            "sugerencia",
            suggestions,
        )


if __name__ == "__main__":
    unittest.main()
