import ast
import unittest
from pathlib import Path


class MainWindowStructureTests(unittest.TestCase):
    def test_critical_methods_belong_to_mainwindow(self):
        path = Path(__file__).parents[1] / "src" / "main_window.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        cls = next(
            n for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "MainWindow"
        )
        methods = {
            n.name for n in cls.body
            if isinstance(n, ast.FunctionDef)
        }

        required = {
            "_build_notes_dock",
            "_build_chatgpt_dock",
            "_build_toolbar",
            "_build_menu",
            "_reference_changed",
            "search_reference",
            "_populate_conversation",
            "begin_reply",
            "save_reply",
        }

        self.assertFalse(required - methods)


if __name__ == "__main__":
    unittest.main()
