import unittest

from src.parser import parse_fields


class ParseFieldsTest(unittest.TestCase):
    def test_parse_fields_trims_whitespace(self):
        self.assertEqual(parse_fields("alpha, beta"), ["alpha", "beta"])
