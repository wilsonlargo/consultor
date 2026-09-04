import ast
import unittest
from pathlib import Path


class V15UiSourceTests(unittest.TestCase):
    def setUp(self):
        self.path = (
            Path(__file__).parents[1]
            / "src"
            / "main_window.py"
        )
        self.text = self.path.read_text(
            encoding="utf-8"
        )
        tree = ast.parse(
            self.text
        )
        self.cls = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "MainWindow"
        )
        self.methods = {
            node.name
            for node in self.cls.body
            if isinstance(node, ast.FunctionDef)
        }

    def test_note_tools_are_real_mainwindow_methods(self):
        required = {
            "_build_note_tools_dock",
            "_note_tools_visibility_changed",
            "_note_tool_hit_in_scope",
            "preview_note_tool_search",
            "apply_note_tool_changes",
            "_note_tools_preset_changed",
            "_note_tool_result_clicked",
            "move_consultant_note",
            "_navigate_to_note_reference",
        }
        self.assertFalse(
            required - self.methods
        )

    def test_tools_menu_and_hidden_dock_exist(self):
        self.assertIn(
            '"Herramientas"',
            self.text,
        )
        self.assertIn(
            '"Buscar y editar notas…"',
            self.text,
        )
        self.assertIn(
            'self.note_tools_dock.hide()',
            self.text,
        )

    def test_search_scope_is_chapter_by_default_then_project(self):
        self.assertIn(
            '"Capítulo actual"',
            self.text,
        )
        self.assertIn(
            '"Todo el proyecto"',
            self.text,
        )
        self.assertIn(
            '"chapter"',
            self.text,
        )
        self.assertIn(
            '"project"',
            self.text,
        )
        self.assertNotIn(
            '"Mis notas — todo el proyecto"',
            self.text,
        )
        self.assertNotIn(
            '"Todas las notas — solo búsqueda"',
            self.text,
        )

    def test_history_was_removed(self):
        self.assertNotIn(
            "note_tools_history_tree",
            self.text,
        )
        self.assertNotIn(
            "note_tools_history",
            self.text,
        )

    def test_search_panel_hides_bible_when_opened(self):
        self.assertIn(
            'def _note_tools_visibility_changed',
            self.text,
        )
        self.assertIn(
            'self.bible_dock.hide()',
            self.text,
        )

    def test_reference_click_navigates_to_note(self):
        self.assertIn(
            'self.note_tools_results.itemClicked.connect(',
            self.text,
        )
        self.assertIn(
            'if column != 1:',
            self.text,
        )
        self.assertIn(
            'self._navigate_to_note_reference(',
            self.text,
        )

    def test_previous_next_note_controls_exist(self):
        self.assertIn(
            'self.prev_note_button',
            self.text,
        )
        self.assertIn(
            'self.next_note_button',
            self.text,
        )
        self.assertIn(
            'move_consultant_note(-1)',
            self.text,
        )
        self.assertIn(
            'move_consultant_note(1)',
            self.text,
        )

    def test_uniform_button_size_helper_is_used(self):
        self.assertIn(
            'def _configure_icon_button',
            self.text,
        )
        self.assertIn(
            'QSize(size, size)',
            self.text,
        )

    def test_regex_presets_and_confirmation_exist(self):
        for token in (
            '"inds90"',
            '"delete_note_inds90"',
            '"delete_inds"',
            '"delete_percent_paragraph"',
            '"phrase_to_period"',
            '"Confirmar edición masiva"',
        ):
            self.assertIn(
                token,
                self.text,
            )


if __name__ == "__main__":
    unittest.main()
