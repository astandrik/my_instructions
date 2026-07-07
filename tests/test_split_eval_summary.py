import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "split_eval_summary.py"


def load_script():
    spec = importlib.util.spec_from_file_location("split_eval_summary", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SplitEvalSummaryTests(unittest.TestCase):
    def test_split_summary_writes_one_summary_per_label(self):
        module = load_script()
        summary = {
            "label": "compare-HEAD-current",
            "total": 4,
            "passed": 3,
            "failed": 1,
            "results": [
                {"case_id": "case-a", "label": "baseline-HEAD", "passed": True, "failure_type": "none", "details": []},
                {"case_id": "case-a", "label": "current", "passed": True, "failure_type": "none", "details": []},
                {
                    "case_id": "case-b",
                    "label": "baseline-HEAD",
                    "passed": False,
                    "failure_type": "behavior",
                    "details": ["missing"],
                },
                {"case_id": "case-b", "label": "current", "passed": True, "failure_type": "none", "details": []},
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            written = module.write_split_summaries(module.split_summary(summary), Path(tmp))
            baseline = json.loads(written["baseline-HEAD"].read_text(encoding="utf-8"))
            current = json.loads(written["current"].read_text(encoding="utf-8"))

        self.assertEqual(baseline["label"], "baseline-HEAD")
        self.assertEqual(baseline["total"], 2)
        self.assertEqual(baseline["passed"], 1)
        self.assertEqual(baseline["failed"], 1)
        self.assertEqual([record["case_id"] for record in baseline["results"]], ["case-a", "case-b"])
        self.assertTrue(all(record["label"] == "baseline-HEAD" for record in baseline["results"]))
        self.assertEqual(current["label"], "current")
        self.assertEqual(current["passed"], 2)

    def test_split_summary_can_extract_selected_label(self):
        module = load_script()
        summary = {
            "results": [
                {"case_id": "case-a", "label": "baseline-HEAD", "passed": True},
                {"case_id": "case-a", "label": "current", "passed": True},
            ]
        }

        split = module.split_summary(summary, ["current"])

        self.assertEqual(list(split), ["current"])
        self.assertEqual(split["current"][0]["case_id"], "case-a")

    def test_split_summary_rejects_missing_label(self):
        module = load_script()
        summary = {"results": [{"case_id": "case-a", "label": "current", "passed": True}]}

        with self.assertRaisesRegex(Exception, "summary has no records for label: baseline-HEAD"):
            module.split_summary(summary, ["baseline-HEAD"])


if __name__ == "__main__":
    unittest.main()
