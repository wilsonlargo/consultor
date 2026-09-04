import unittest
from pathlib import Path


class V13SourceFeatureTests(unittest.TestCase):
    def setUp(self):
        self.path = (
            Path(__file__).parents[1]
            / "src"
            / "main_window.py"
        )
        self.text = self.path.read_text(
            encoding="utf-8"
        )

    def test_consultant_panel_comparison_present(self):
        self.assertIn(
            '"VerseRef: —"',
            self.text,
        )
        self.assertIn(
            '"<b>ANTES ·</b> "',
            self.text,
        )
        self.assertIn(
            '"<b>ACTUAL ·</b> "',
            self.text,
        )
        self.assertIn(
            'def _current_sfm_source_for_message',
            self.text,
        )
        self.assertIn(
            'def _verse_change_percentage',
            self.text,
        )
        self.assertIn(
            '"Cambio textual: ',
            self.text,
        )

    def test_marker_template_present(self):
        for marker in (
            '"COM:"',
            '"PT:"',
            '"SUG:"',
            '"CONT:"',
            '"IndS: %"',
            '"RES:"',
            '"Plantilla completa"',
        ):
            self.assertIn(marker, self.text)

    def test_recent_projects_and_session_present(self):
        self.assertIn(
            '"Proyectos recientes"',
            self.text,
        )
        self.assertIn(
            'def _save_project_session',
            self.text,
        )
        self.assertIn(
            'def _restore_project_session',
            self.text,
        )
        self.assertIn(
            'def _restore_last_project',
            self.text,
        )
        self.assertIn(
            'current_verse_position',
            self.text,
        )
        self.assertIn(
            'window_state',
            self.text,
        )

    def test_manual_notes_backup_present(self):
        self.assertIn(
            '"Crear backup de mis notas ahora…"',
            self.text,
        )
        self.assertIn(
            'def create_manual_notes_backup',
            self.text,
        )
        self.assertIn(
            '".consultor_backups"',
            self.text,
        )
        self.assertIn(
            '"manual"',
            self.text,
        )

    def test_face_to_face_panel_filters_external_responses(self):
        self.assertIn(
            '"Mi nota"',
            self.text,
        )
        self.assertIn(
            '"Respuesta del interlocutor"',
            self.text,
        )
        self.assertIn(
            'if not _same_name(',
            self.text,
        )
        self.assertIn(
            'def _my_message_changed',
            self.text,
        )
        self.assertIn(
            'self.reply_editor = SpellCheckPlainTextEdit(',
            self.text,
        )

    def test_visible_app_name(self):
        self.assertIn(
            'self.setWindowTitle("Consultor App")',
            self.text,
        )


if __name__ == "__main__":
    unittest.main()
