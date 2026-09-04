import ast
import unittest
from pathlib import Path


class V21SpellcheckSourceTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        self.main_text = (
            root / "src" / "main_window.py"
        ).read_text(encoding="utf-8")
        self.qt_text = (
            root / "src" / "spellcheck_qt.py"
        ).read_text(encoding="utf-8")
        self.core_text = (
            root / "src" / "spellcheck_core.py"
        ).read_text(encoding="utf-8")
        self.requirements = (
            root / "requirements.txt"
        ).read_text(encoding="utf-8")

        tree = ast.parse(
            self.main_text
        )
        cls = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "MainWindow"
        )
        self.methods = {
            node.name
            for node in cls.body
            if isinstance(node, ast.FunctionDef)
        }

    def test_spellcheck_methods_are_direct_mainwindow_methods(self):
        required = {
            "_spell_status_changed",
            "_refresh_spellcheck_controls",
            "_spellcheck_toggled",
            "_spell_language_changed",
            "_show_spellcheck_menu",
            "_review_note_spelling",
            "_review_reply_spelling",
            "_import_spell_project_wordlist",
            "_choose_custom_spell_dictionary",
        }
        self.assertFalse(
            required - self.methods
        )

    def test_only_editable_note_fields_use_spell_editor(self):
        self.assertIn(
            "self.note_editor = SpellCheckPlainTextEdit(",
            self.main_text,
        )
        self.assertIn(
            "self.reply_editor = SpellCheckPlainTextEdit(",
            self.main_text,
        )
        self.assertNotIn(
            "self.message_tree = SpellCheckPlainTextEdit(",
            self.main_text,
        )

    def test_compact_abc_controls_exist(self):
        self.assertIn(
            '"ABC✓"',
            self.main_text,
        )
        self.assertIn(
            "self.spell_language_combo",
            self.main_text,
        )
        self.assertIn(
            '"Importar vocabulario al diccionario del proyecto…"',
            self.main_text,
        )
        self.assertIn(
            '"Usar lista como diccionario principal…"',
            self.main_text,
        )

    def test_markers_are_explicitly_excluded(self):
        for marker in (
            '"COM"',
            '"PT"',
            '"SUG"',
            '"CONT"',
            '"INDS"',
            '"RES"',
        ):
            self.assertIn(
                marker,
                self.core_text,
            )

    def test_context_menu_has_suggestions_and_word_actions(self):
        self.assertIn(
            "class SpellCheckPlainTextEdit",
            self.qt_text,
        )
        self.assertIn(
            "def contextMenuEvent(",
            self.qt_text,
        )
        self.assertIn(
            "Agregar «{word}» al diccionario personal",
            self.qt_text,
        )
        self.assertIn(
            "Agregar «{word}» al diccionario del proyecto",
            self.qt_text,
        )
        self.assertIn(
            "Ignorar durante esta sesión",
            self.qt_text,
        )

    def test_spanish_and_other_languages_are_integrated(self):
        for code in (
            '"es"',
            '"en"',
            '"fr"',
            '"pt"',
            '"de"',
            '"it"',
            '"eu"',
            '"custom"',
        ):
            self.assertIn(
                code,
                self.qt_text,
            )

        self.assertIn(
            "pyspellchecker>=0.8.2",
            self.requirements,
        )

    def test_project_switch_updates_project_dictionary(self):
        self.assertIn(
            "self.spell_manager.set_project_key(",
            self.main_text,
        )


if __name__ == "__main__":
    unittest.main()
