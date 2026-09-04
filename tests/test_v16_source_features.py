import ast
import unittest
from pathlib import Path


class V16SourceFeatureTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        self.main_path = root / "src" / "main_window.py"
        self.main_text = self.main_path.read_text(
            encoding="utf-8"
        )
        self.anchor_text = (
            root / "src" / "anchor_text_edit.py"
        ).read_text(encoding="utf-8")

        tree = ast.parse(self.main_text)
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

    def test_review_mode_is_inside_mainwindow(self):
        required = {
            "_review_threads",
            "_review_mode_toggled",
            "_review_filter_changed",
            "_update_review_progress",
            "_advance_review_after_action",
        }
        self.assertFalse(
            required - self.methods
        )
        self.assertIn(
            '"Pendientes"',
            self.main_text,
        )
        self.assertIn(
            '"Respondidas"',
            self.main_text,
        )
        self.assertIn(
            '"Resueltas"',
            self.main_text,
        )
        self.assertIn(
            '"Todas"',
            self.main_text,
        )

    def test_exact_note_anchor_highlight_exists(self):
        required = {
            "_clear_note_anchor_highlights",
            "_find_anchor_widget_for_message",
            "_highlight_note_anchor",
        }
        self.assertFalse(
            required - self.methods
        )
        self.assertIn(
            "def highlight_note(",
            self.anchor_text,
        )
        self.assertIn(
            "StartPosition",
            self.main_text,
        )

    def test_external_file_watcher_exists(self):
        required = {
            "_configure_project_file_watcher",
            "_project_file_changed",
            "_process_project_file_change",
            "_reload_external_changes",
            "_after_internal_file_write",
        }
        self.assertFalse(
            required - self.methods
        )
        self.assertIn(
            "QFileSystemWatcher",
            self.main_text,
        )
        self.assertIn(
            '"Recargar"',
            self.main_text,
        )

    def test_review_advances_after_reply_and_resolve(self):
        self.assertGreaterEqual(
            self.main_text.count(
                "self._advance_review_after_action("
            ),
            2,
        )
        self.assertIn(
            "def _next_review_target",
            self.main_text,
        )

    def test_diff_html_is_used(self):
        self.assertIn(
            "from .verse_diff import diff_html",
            self.main_text,
        )
        self.assertIn(
            "old_diff, current_diff = diff_html(",
            self.main_text,
        )


if __name__ == "__main__":
    unittest.main()
