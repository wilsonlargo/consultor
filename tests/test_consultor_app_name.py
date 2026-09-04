import unittest
from pathlib import Path


class ConsultorAppNameTests(unittest.TestCase):
    def test_display_name_and_legacy_storage_name(self):
        path = Path(__file__).parents[1] / "app.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn(
            'app.setApplicationDisplayName("Consultor App")',
            text,
        )
        self.assertIn(
            'app.setApplicationName("Consultor Bíblico")',
            text,
        )


if __name__ == "__main__":
    unittest.main()
