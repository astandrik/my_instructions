import unittest

from src import canonical_project_id


class ProjectIdTests(unittest.TestCase):
    def test_canonicalizes_project_id(self):
        self.assertEqual(canonical_project_id(" My Project "), "my-project")


if __name__ == "__main__":
    unittest.main()
