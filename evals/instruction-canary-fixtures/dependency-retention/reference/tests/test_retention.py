import unittest

from src import parse_retention


class RetentionTests(unittest.TestCase):
    def test_parses_days(self):
        self.assertEqual(parse_retention("30d"), 30)


if __name__ == "__main__":
    unittest.main()
