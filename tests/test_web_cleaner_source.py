import unittest
from pathlib import Path


class WebCleanerSourceTests(unittest.TestCase):
    def test_expected_sites_and_domains(self):
        path = Path(__file__).parents[1] / "src" / "web_cleaner.py"
        content = path.read_text(encoding="utf-8")
        self.assertIn("doubleclick.net", content)
        self.assertIn("biblegateway.com", content)
        self.assertIn("stepbible.org", content)


if __name__ == "__main__":
    unittest.main()
