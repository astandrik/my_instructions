import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "compare_saved_model_quality.py"


def load_script():
    spec = importlib.util.spec_from_file_location("compare_saved_model_quality", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CompareSavedModelQualityTests(unittest.TestCase):
    def test_parse_label_path(self):
        module = load_script()

        label, path = module.parse_label_path("GPT-5.5=.eval-results/current/summary.json")

        self.assertEqual(label, "GPT-5.5")
        self.assertEqual(path, Path(".eval-results/current/summary.json"))

    def test_read_summary_overrides_labels(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            path.write_text(
                json.dumps(
                    {
                        "results": [
                            {
                                "case_id": "case-a",
                                "label": "current",
                                "passed": True,
                                "failure_type": "none",
                                "details": [],
                                "final_response": {"summary": "ok"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            records = module.read_summary(path, "DeepSeek")

        self.assertEqual(records["case-a"]["label"], "DeepSeek")

    def test_read_summary_rejects_duplicate_case_ids(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            path.write_text(
                json.dumps(
                    {
                        "results": [
                            {
                                "case_id": "case-a",
                                "label": "baseline-HEAD",
                                "passed": True,
                                "failure_type": "none",
                                "details": [],
                                "final_response": {"summary": "baseline"},
                            },
                            {
                                "case_id": "case-a",
                                "label": "current",
                                "passed": True,
                                "failure_type": "none",
                                "details": [],
                                "final_response": {"summary": "current"},
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(module.evals.ValidationError, "split_eval_summary.py"):
                module.read_summary(path, "combined")

    def test_aggregate_pair_counts_winners_and_scores(self):
        module = load_script()
        comparisons = [
            {
                "baseline": {"passed": True},
                "candidate": {"passed": True},
                "quality": {
                    "winner": "baseline",
                    "source": "judge",
                    "confidence": "high",
                    "baseline_score": 90,
                    "current_score": 80,
                },
            },
            {
                "baseline": {"passed": True},
                "candidate": {"passed": False},
                "quality": {
                    "winner": "baseline",
                    "source": "hard_gate",
                    "confidence": "high",
                    "baseline_score": 100,
                    "current_score": 0,
                },
            },
        ]

        aggregate = module.aggregate_pair(comparisons)

        self.assertEqual(aggregate["candidate_passed"], 1)
        self.assertEqual(aggregate["winners"]["baseline"], 2)
        self.assertEqual(aggregate["sources"], {"judge": 1, "hard_gate": 1})
        self.assertEqual(aggregate["average_delta"], -55.0)


if __name__ == "__main__":
    unittest.main()
