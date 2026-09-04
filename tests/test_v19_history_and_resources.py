import ast
import unittest
from pathlib import Path


class V19HistoryAndResourceTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        self.main_text = (
            root / "src" / "main_window.py"
        ).read_text(encoding="utf-8")
        self.panel_text = (
            root / "src" / "resource_panel.py"
        ).read_text(encoding="utf-8")
        self.native_text = (
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

    def test_reference_history_methods_are_real_mainwindow_methods(self):
        required = {
            "_record_reference_history",
            "_update_reference_history_controls",
            "_navigate_reference_history_position",
            "move_reference_history",
            "_reference_history_combo_changed",
        }
        self.assertFalse(
            required - self.methods
        )

    def test_reference_history_controls_are_after_chapter_navigation(self):
        chapter_pos = self.main_text.index(
            "self.next_chapter_button"
        )
        history_pos = self.main_text.index(
            "self.reference_history_combo"
        )
        verse_pos = self.main_text.index(
            "self.prev_verse_button"
        )

        self.assertLess(
            chapter_pos,
            history_pos,
        )
        self.assertLess(
            history_pos,
            verse_pos,
        )
        self.assertIn(
            '"↶"',
            self.main_text,
        )
        self.assertIn(
            '"↷"',
            self.main_text,
        )

    def test_reference_history_is_saved_per_project(self):
        self.assertIn(
            'f"{base}/reference_history"',
            self.main_text,
        )
        self.assertIn(
            'f"{base}/reference_history_index"',
            self.main_text,
        )
        self.assertIn(
            "self.reference_history = []",
            self.main_text,
        )

    def test_topics_and_places_tabs_exist(self):
        self.assertIn(
            '"Temas"',
            self.panel_text,
        )
        self.assertIn(
            '"Lugares"',
            self.panel_text,
        )
        self.assertIn(
            "def _render_topics(",
            self.panel_text,
        )
        self.assertIn(
            "def _render_places(",
            self.panel_text,
        )

    def test_extra_open_datasets_are_installed_incrementally(self):
        self.assertIn(
            'EXTRA_DATASETS = (',
            self.native_text,
        )
        self.assertIn(
            '"topics"',
            self.native_text,
        )
        self.assertIn(
            '"places"',
            self.native_text,
        )
        self.assertIn(
            "def install_extras(",
            self.panel_text,
        )
        self.assertIn(
            '"Instalar extras"',
            self.panel_text,
        )

    def test_topics_and_places_are_native_sqlite_resources(self):
        for token in (
            "CREATE TABLE IF NOT EXISTS topics",
            "CREATE TABLE IF NOT EXISTS topic_verses",
            "CREATE TABLE IF NOT EXISTS places",
            "CREATE TABLE IF NOT EXISTS place_verses",
            "def import_topics_json(",
            "def import_places_jsonl(",
            "def topics_for(",
            "def places_for(",
        ):
            self.assertIn(
                token,
                self.native_text,
            )


if __name__ == "__main__":
    unittest.main()
