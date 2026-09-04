import ast
import unittest
from pathlib import Path


class V20NotesCommentarySourceTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        self.panel_text = (
            root / "src" / "resource_panel.py"
        ).read_text(encoding="utf-8")
        self.context_text = (
            root / "src" / "context_resources.py"
        ).read_text(encoding="utf-8")
        self.native_text = (
            root / "src" / "native_resources.py"
        ).read_text(encoding="utf-8")

        tree = ast.parse(
            self.panel_text
        )
        cls = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "ResourcePanelWidget"
        )
        self.methods = {
            node.name
            for node in cls.body
            if isinstance(node, ast.FunctionDef)
        }

    def test_notes_and_commentaries_are_native_tabs(self):
        self.assertIn(
            '"Notas"',
            self.panel_text,
        )
        self.assertIn(
            '"Comentarios"',
            self.panel_text,
        )
        self.assertNotIn(
            "QWebEngineView",
            self.panel_text,
        )

    def test_context_methods_are_inside_resource_panel(self):
        required = {
            "_build_notes_tab",
            "_build_commentary_tab",
            "_context_provider_changed",
            "_render_context_group",
            "_ensure_context_loaded",
            "_context_fetch_finished",
            "_context_fetch_failed",
            "_context_to_chatgpt",
        }
        self.assertFalse(
            required - self.methods
        )

    def test_open_sources_are_named_and_licensed(self):
        for token in (
            '"Darby Translation Notes"',
            '"Tyndale Open Study Notes"',
            '"Adam Clarke Bible Commentary"',
            '"Jamieson-Fausset-Brown"',
            "\"John Calvin's Commentaries\"",
            '"John Gill Bible Commentary"',
            '"Keil & Delitzsch (AT)"',
            '"Matthew Henry Bible Commentary"',
            '"Dominio público"',
            '"CC BY-SA 4.0"',
        ):
            self.assertIn(
                token,
                self.context_text,
            )

    def test_context_is_cached_in_sqlite(self):
        for token in (
            "CREATE TABLE IF NOT EXISTS context_chapters",
            "CREATE TABLE IF NOT EXISTS context_notes",
            "def replace_context_chapter(",
            "def context_chapter_cached(",
            "def context_notes_for(",
        ):
            self.assertIn(
                token,
                self.native_text,
            )

    def test_chatgpt_integration_uses_displayed_context(self):
        self.assertIn(
            "def _context_to_chatgpt(",
            self.panel_text,
        )
        self.assertIn(
            "self.use_chatgpt_requested.emit(",
            self.panel_text,
        )


if __name__ == "__main__":
    unittest.main()
