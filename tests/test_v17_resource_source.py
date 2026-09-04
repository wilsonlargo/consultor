import ast
import unittest
from pathlib import Path


class V18ResourceSourceTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        self.main_text = (
            root / "src" / "main_window.py"
        ).read_text(encoding="utf-8")
        self.panel_text = (
            root / "src" / "resource_panel.py"
        ).read_text(encoding="utf-8")
        self.core_text = (
            root / "src" / "native_resources.py"
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

    def test_resource_methods_stay_in_mainwindow(self):
        required = {
            "_build_resources_dock",
            "toggle_resources_panel",
            "_move_widget_to_next_screen",
            "_new_resource_window",
            "_sync_resource_reference",
            "_use_resource_with_chatgpt",
            "_navigate_to_resource_reference",
        }
        self.assertFalse(
            required - self.methods
        )

    def test_panel_is_native_not_web(self):
        self.assertNotIn(
            "QWebEngineView",
            self.panel_text,
        )
        self.assertIn(
            '"Texto fuente"',
            self.panel_text,
        )
        self.assertIn(
            '"Léxico"',
            self.panel_text,
        )
        self.assertIn(
            '"Referencias"',
            self.panel_text,
        )
        self.assertIn(
            '"Notas privadas"',
            self.panel_text,
        )

    def test_open_datasets_have_explicit_urls(self):
        for token in (
            "SBLGNT.json",
            "OSHB.json",
            "lexicon.json",
            "tokens-sblgnt.json",
            "cross_references.txt",
        ):
            self.assertIn(
                token,
                self.core_text,
            )

    def test_resources_are_downloaded_once_then_sqlite(self):
        self.assertIn(
            "class NativeInstallWorker",
            self.panel_text,
        )
        self.assertIn(
            "urllib.request.urlopen",
            self.panel_text,
        )
        self.assertIn(
            "sqlite3.connect",
            self.core_text,
        )
        self.assertIn(
            "native_resources.sqlite3",
            self.panel_text,
        )

    def test_crossrefs_can_navigate_main_project(self):
        self.assertIn(
            "navigate_reference_requested",
            self.panel_text,
        )
        self.assertIn(
            "self._navigate_to_note_reference(",
            self.main_text,
        )

    def test_multimonitor_and_floating_resources_remain(self):
        self.assertIn(
            '"Mover Recursos a otra pantalla"',
            self.main_text,
        )
        self.assertIn(
            '"Nueva ventana de recurso"',
            self.main_text,
        )
        self.assertIn(
            "self.resources_dock.setFloating(",
            self.main_text,
        )


if __name__ == "__main__":
    unittest.main()
