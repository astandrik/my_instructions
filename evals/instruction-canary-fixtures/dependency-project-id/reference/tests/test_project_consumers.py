import unittest

from src.cli import format_project_arg
from src.store import put_project


class ProjectConsumerTests(unittest.TestCase):
    def test_cli_uses_canonical_id(self):
        self.assertEqual(format_project_arg(" My Project "), "my-project")

    def test_store_uses_canonical_id(self):
        store = {}
        put_project(store, " My Project ", {"ok": True})
        self.assertEqual(store, {"my-project": {"ok": True}})


if __name__ == "__main__":
    unittest.main()
