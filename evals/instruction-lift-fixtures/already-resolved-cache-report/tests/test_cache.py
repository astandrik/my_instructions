import unittest

from src.cache import Cache


class CacheTest(unittest.TestCase):
    def test_none_key_returns_none(self):
        self.assertIsNone(Cache().get(None))
