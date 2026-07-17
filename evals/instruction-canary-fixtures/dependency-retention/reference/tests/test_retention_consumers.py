import unittest

from src.config import serialize_config
from src.scheduler import schedule_state


class RetentionConsumerTests(unittest.TestCase):
    def test_scheduler_uses_integer_days(self):
        self.assertEqual(schedule_state("30d"), {"retention_days": 30})

    def test_config_uses_integer_days(self):
        self.assertEqual(serialize_config("30d"), {"retention": 30})


if __name__ == "__main__":
    unittest.main()
