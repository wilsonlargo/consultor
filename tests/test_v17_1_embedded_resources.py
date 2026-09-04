import unittest
from pathlib import Path


class EmbeddedResourceSourceTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        self.text = (
            root / "src" / "resource_panel.py"
        ).read_text(encoding="utf-8")

    def test_web_resources_use_embedded_qwebengine(self):
        self.assertIn(
            "QWebEngineView",
            self.text,
        )
        self.assertIn(
            "self.browser.setUrl(",
            self.text,
        )
        self.assertIn(
            "self.stack.setCurrentWidget(\n            self.browser",
            self.text,
        )

    def test_translation_notes_are_reference_aware(self):
        self.assertIn(
            "def _tn_live_url(",
            self.text,
        )
        self.assertIn(
            "en_tn_{number}-{book}.html",
            self.text,
        )
        self.assertIn(
            "def _scroll_to_reference(",
            self.text,
        )
        self.assertIn(
            "scrollIntoView",
            self.text,
        )

    def test_translation_notes_have_embedded_fallback(self):
        self.assertIn(
            "def _tn_fallback_url(",
            self.text,
        )
        self.assertIn(
            "en_tn_{number}-{book}.tsv",
            self.text,
        )
        self.assertIn(
            "def _load_tn_fallback(",
            self.text,
        )

    def test_browser_navigation_is_inside_panel(self):
        for token in (
            'self.back_button',
            'self.forward_button',
            'self.reload_button',
            'self.home_button',
            'self.external_button',
        ):
            self.assertIn(
                token,
                self.text,
            )

    def test_custom_web_resource_is_embedded(self):
        self.assertIn(
            '"custom_web"',
            self.text,
        )
        self.assertIn(
            '"Abrir URL dentro del panel…"',
            self.text,
        )

    def test_web_chatgpt_uses_only_user_selection(self):
        self.assertIn(
            "window.getSelection",
            self.text,
        )
        self.assertIn(
            "No se extrae silenciosamente",
            self.text,
        )


if __name__ == "__main__":
    unittest.main()
