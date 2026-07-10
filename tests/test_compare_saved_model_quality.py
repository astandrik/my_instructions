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

    def test_saved_quality_reports_record_judge_metadata(self):
        module = load_script()
        comparisons = [
            {
                "case_id": "case-a",
                "baseline": {"passed": True},
                "candidate": {"passed": True},
                "quality": {
                    "winner": "current",
                    "source": "llm_judge",
                    "confidence": "high",
                    "baseline_score": 82,
                    "current_score": 91,
                    "reason": "Candidate is more specific.",
                },
            }
        ]
        judge = {
            "preset": "glm-5.2-medium",
            "model": "glm-5.2",
            "reasoning_effort": "medium",
            "service_tier": None,
            "agent_command_mode": "current-codex",
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            pair_report = module.write_pair_report(
                output_dir,
                "GLM-5.2-prev-saved-model-quality",
                "GLM-5.2-prev",
                "GLM-5.2-current",
                comparisons,
                judge,
            )
            module.write_summary_report(
                output_dir,
                "GLM-5.2-prev-saved-model-quality",
                "GLM-5.2-prev",
                [pair_report],
                judge,
            )

            pair_json = json.loads(Path(pair_report["quality_json"]).read_text(encoding="utf-8"))
            self.assertEqual(pair_json["judge"], judge)
            pair_md = Path(pair_report["quality_md"]).read_text(encoding="utf-8")
            self.assertIn("Judge: `glm-5.2` (preset `glm-5.2-medium`, reasoning `medium`)", pair_md)

            summary_json = json.loads(
                (output_dir / "GLM-5.2-prev-saved-model-quality" / "model-quality-summary.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(summary_json["judge"], judge)
            self.assertEqual(summary_json["pairs"][0]["judge"], judge)
            summary_md = (output_dir / "GLM-5.2-prev-saved-model-quality" / "model-quality-summary.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("Judge: `glm-5.2` (preset `glm-5.2-medium`, reasoning `medium`)", summary_md)

    def test_dry_run_candidate_plan_counts_judge_calls_and_shortcuts(self):
        module = load_script()
        cases = [{"id": "pass-pass"}, {"id": "baseline-only"}, {"id": "fail-fail"}]
        baseline_records = {
            "pass-pass": {"passed": True},
            "baseline-only": {"passed": True, "failure_type": "none"},
            "fail-fail": {"passed": False, "failure_type": "behavior"},
        }
        candidate_records = {
            "pass-pass": {"passed": True},
            "baseline-only": {"passed": False, "failure_type": "behavior"},
            "fail-fail": {"passed": False, "failure_type": "behavior"},
        }

        plan = module.dry_run_candidate_plan(
            cases,
            baseline_label="baseline",
            baseline_records=baseline_records,
            candidate_label="candidate",
            candidate_records=candidate_records,
        )

        self.assertEqual(plan["candidate_label"], "candidate")
        self.assertEqual(plan["total"], 3)
        self.assertEqual(plan["judge_calls"], 1)
        self.assertEqual(plan["hard_gate_shortcuts"], 2)
        self.assertEqual(plan["judge_cases"], ["pass-pass"])

    def test_parse_args_accepts_dry_run(self):
        module = load_script()

        args = module.parse_args(
            [
                "--baseline",
                "baseline=.eval-results/baseline/summary.json",
                "--candidate",
                "candidate=.eval-results/candidate/summary.json",
                "--agent-command",
                "codex exec",
                "--output-dir",
                ".eval-results/quality",
                "--dry-run",
            ]
        )

        self.assertTrue(args.dry_run)

    def test_parse_args_defaults_to_sol_medium_judge(self):
        module = load_script()

        args = module.parse_args(
            [
                "--baseline",
                "baseline=.eval-results/baseline/summary.json",
                "--candidate",
                "candidate=.eval-results/candidate/summary.json",
                "--agent-command",
                "codex exec",
                "--output-dir",
                ".eval-results/quality",
            ]
        )

        self.assertEqual(args.judge_preset, "gpt-5.6-sol-medium")


if __name__ == "__main__":
    unittest.main()
