import unittest

from src.slug import slugify


class SlugTests(unittest.TestCase):
    def test_whitespace_run_becomes_one_separator(self):
        self.assertEqual(slugify("alpha   beta"), "alpha-beta")


if __name__ == "__main__":
    unittest.main()
