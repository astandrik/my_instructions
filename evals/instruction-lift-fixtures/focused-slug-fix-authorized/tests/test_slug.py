import unittest

from src.slug import slugify


class SlugifyTest(unittest.TestCase):
    def test_repeated_spaces_use_one_separator(self):
        self.assertEqual(slugify("Hello   World"), "hello-world")
