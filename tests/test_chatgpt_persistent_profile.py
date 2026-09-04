import unittest
from pathlib import Path


class ChatGPTPersistentProfileTests(unittest.TestCase):
    def test_persistent_profile_configuration_present(self):
        path = Path(__file__).parents[1] / "src" / "main_window.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn('QWebEngineProfile(', text)
        self.assertIn('"ChatGPTPersistent"', text)
        self.assertIn('setPersistentStoragePath', text)
        self.assertIn('setCachePath', text)
        self.assertIn('ForcePersistentCookies', text)
        self.assertIn('DiskHttpCache', text)
        self.assertIn('webprofiles" / "chatgpt"', text)


if __name__ == "__main__":
    unittest.main()
