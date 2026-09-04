import unittest
from src.reference_parser import parse_reference, to_spanish_reference, to_osis_reference


class ReferenceParserTests(unittest.TestCase):
    def test_spanish(self):
        self.assertEqual(parse_reference("Marcos 8:31"), "MRK.8.31")

    def test_range(self):
        self.assertEqual(parse_reference("Marcos 8:31-33"), "MRK.8.31-33")

    def test_numbered_book(self):
        self.assertEqual(parse_reference("1 Corintios 13:4-7"), "1CO.13.4-7")

    def test_accent(self):
        self.assertEqual(parse_reference("Gálatas 5:22"), "GAL.5.22")

    def test_spanish_output(self):
        self.assertEqual(to_spanish_reference("MRK.8.31"), "Marcos 8:31")

    def test_step_output(self):
        self.assertEqual(to_osis_reference("MRK.8.31"), "Mark.8.31")


if __name__ == "__main__":
    unittest.main()
