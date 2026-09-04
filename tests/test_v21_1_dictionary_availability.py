import ast
import unittest
from pathlib import Path


class V211DictionaryAvailabilityTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        self.main_text = (
            root / "src" / "main_window.py"
        ).read_text(encoding="utf-8")
        self.qt_text = (
            root / "src" / "spellcheck_qt.py"
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

    def test_missing_dictionary_is_visible_not_silent(self):
        self.assertIn(
            "SIN DICCIONARIO",
            self.qt_text,
        )
        self.assertIn(
            'f"{language} !"',
            self.main_text,
        )
        self.assertIn(
            'f"{language} ✓"',
            self.main_text,
        )

    def test_integrated_dictionary_can_be_installed_inside_app(self):
        self.assertIn(
            "class SpellDependencyInstaller",
            self.qt_text,
        )
        self.assertIn(
            '"pip"',
            self.qt_text,
        )
        self.assertIn(
            '"pyspellchecker>=0.8.2"',
            self.qt_text,
        )
        self.assertIn(
            '"Instalar diccionario integrado…"',
            self.main_text,
        )

        required = {
            "_install_spell_dictionary",
            "_spell_dictionary_install_finished",
        }
        self.assertFalse(
            required - self.methods
        )

    def test_system_hunspell_dictionary_is_a_zero_setup_fallback(self):
        for token in (
            "SYSTEM_DICTIONARY_PATTERNS",
            "/usr/share/hunspell",
            "def _find_system_dictionary(",
            "self.system_backend",
            "diccionario del sistema",
        ):
            self.assertIn(
                token,
                self.qt_text,
            )

    def test_manager_can_report_backend_readiness(self):
        self.assertIn(
            "def backend_ready(self)",
            self.qt_text,
        )
        self.assertIn(
            "def reload_backend(self)",
            self.qt_text,
        )


if __name__ == "__main__":
    unittest.main()
