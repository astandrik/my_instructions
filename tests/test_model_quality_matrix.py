import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "evals" / "model-quality-matrix.json"
PRESETS_PATH = REPO_ROOT / "evals" / "model-presets.json"
RUNNER_PATH = REPO_ROOT / "scripts" / "run_model_absolute_quality.py"
AGGREGATOR_PATH = REPO_ROOT / "scripts" / "aggregate_model_absolute_quality.py"

MODEL_IDS = [
    "gpt-5.6-sol",
    "gpt-5.5",
    "glm-5.2",
    "grok-4.3",
    "deepseek-v4-flash",
    "deepseek-v4-flash-thinking",
]
MODEL_LABELS = [
    "GPT-5.6 Sol medium",
    "GPT-5.5",
    "GLM-5.2",
    "Grok 4.3",
    "DeepSeek V4 Flash",
    "DeepSeek V4 Flash thinking",
]
MODEL_ROLES = ["primary", "historical", "external", "external", "external", "external"]
PASS_COUNTS = [33, 35, 29, 25, 18, 23]
PASS_PATTERNS = {
    model_id: "1" * count + "0" * (50 - count)
    for model_id, count in zip(MODEL_IDS, PASS_COUNTS, strict=True)
}
SOURCE_SUMMARIES = [
    {
        "path": ".eval-results/blinded-50-case-v2-762db4f/current-gpt56-sol/current/summary.json",
        "sha256": "5af24dbfcc7ab03d8fd01992a683644ce9555d32c244ff412b20853b8749d87d",
    },
    {
        "path": ".eval-results/blinded-50-case-v2-762db4f/current-gpt55/current/summary.json",
        "sha256": "c5643303c4f2d795cb33a0de4c9ded358d663c145f65542330a04ecb1a1a0ad3",
    },
    {
        "path": ".eval-results/blinded-50-case-v2-762db4f/current-glm-5.2/current/summary.json",
        "sha256": "69ee04fec39fdede786bccb4947306d2c6a4964ae5bbd387b19d4a450960021c",
    },
    {
        "path": ".eval-results/blinded-50-case-v2-762db4f/current-grok-4.3/current/summary.json",
        "sha256": "809d7e8e438fbaf51bf561ec2726f15d5a61748bc4cf4f26156954d3b9fbf1bb",
    },
    {
        "path": ".eval-results/blinded-50-case-v2-762db4f/current-deepseek-v4-flash/current/summary.json",
        "sha256": "6e39b861259f271ba7d3a132fc52234093efa2d263c585bdde2a929a69cf0423",
    },
    {
        "path": ".eval-results/blinded-50-case-v2-762db4f/current-deepseek-v4-flash-thinking/current/summary.json",
        "sha256": "d3440b513fe60c6ecbe5da72850b314764b3c83b78df95ef8d9713dffe28ccb9",
    },
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_runner():
    spec = importlib.util.spec_from_file_location("run_model_absolute_quality", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_aggregator():
    spec = importlib.util.spec_from_file_location(
        "aggregate_model_absolute_quality", AGGREGATOR_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_fixture(root):
    root = Path(root)
    (root / "evals").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(exist_ok=True)
    (root / ".eval-results" / "sources").mkdir(parents=True, exist_ok=True)
    instructions_path = root / "CRITICAL_INSTRUCTIONS.md"
    instructions_path.write_text("fixture instructions\n", encoding="utf-8")
    shutil.copy2(
        REPO_ROOT / "evals" / "absolute-quality-judge.schema.json",
        root / "evals" / "absolute-quality-judge.schema.json",
    )
    shutil.copy2(
        REPO_ROOT / "scripts" / "run_instruction_evals.py",
        root / "scripts" / "run_instruction_evals.py",
    )

    case_ids = [f"case-{index:02d}" for index in range(1, 51)]
    cases_path = root / "evals" / "cases.jsonl"
    cases_path.write_text(
        "".join(
            json.dumps(
                {
                    "id": case_id,
                    "scenario": f"Scenario {case_id}",
                    "prompt": f"Prompt {case_id}",
                    "expected_behavior": ["Expected"],
                    "forbidden_behavior": ["Forbidden"],
                    "rubric": "Fixed rubric",
                }
            )
            + "\n"
            for case_id in case_ids
        ),
        encoding="utf-8",
    )
    presets = {
        "gpt-5.6-sol-medium": {
            "model": "gpt-5.6-sol",
            "reasoning_effort": "medium",
            "service_tier": "fast",
        },
        "gpt-5.6-terra-high": {
            "model": "gpt-5.6-terra",
            "reasoning_effort": "high",
            "service_tier": "fast",
        },
    }
    (root / "evals" / "model-presets.json").write_text(
        json.dumps(presets), encoding="utf-8"
    )

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["snapshots"]["instructions"]["sha256"] = sha256(instructions_path)
    manifest["snapshots"]["cases"].update(
        {"path": "evals/cases.jsonl", "count": 50, "sha256": sha256(cases_path)}
    )
    for model in manifest["models"]:
        model_id = model["id"]
        pattern = PASS_PATTERNS[model_id]
        results = []
        for case_id, marker in zip(case_ids, pattern, strict=True):
            passed = marker == "1"
            results.append(
                {
                    "case_id": case_id,
                    "label": "current",
                    "passed": passed,
                    "failure_type": "none" if passed else "behavior",
                    "details": ["all deterministic checks passed"] if passed else ["failed"],
                    "final_response": {
                        "decision": "pass" if passed else "no_op",
                        "risk_level": "low",
                        "summary": f"Response for {case_id}",
                        "evidence": ["fixture"],
                        "actions": ["verify"],
                    },
                }
            )
        source_path = root / ".eval-results" / "sources" / f"{model_id}.json"
        source_path.write_text(
            json.dumps(
                {
                    "label": "current",
                    "total": 50,
                    "passed": pattern.count("1"),
                    "failed": pattern.count("0"),
                    "results": results,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        model["source_summary"] = {
            "path": source_path.relative_to(root).as_posix(),
            "sha256": sha256(source_path),
        }
    manifest_path = root / "evals" / "model-quality-matrix.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


class ModelQualityManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_freezes_snapshots_models_and_roles(self):
        self.assertEqual(self.manifest["snapshots"]["cases"]["count"], 50)
        self.assertEqual([model["id"] for model in self.manifest["models"]], MODEL_IDS)
        self.assertEqual([model["label"] for model in self.manifest["models"]], MODEL_LABELS)
        self.assertEqual([model["role"] for model in self.manifest["models"]], MODEL_ROLES)
        self.assertEqual(
            [model["source_summary"] for model in self.manifest["models"]], SOURCE_SUMMARIES
        )

    def test_both_judges_cover_the_identical_163_passed_responses(self):
        expected_counts = dict(zip(MODEL_IDS, PASS_COUNTS, strict=True))
        for judge_name, judge in self.manifest["judges"].items():
            with self.subTest(judge=judge_name):
                self.assertEqual(judge["coverage"], "all_hard_gate_passed_responses")
                self.assertEqual(judge["model_passed_counts"], expected_counts)
                self.assertEqual(judge["budget"], {"model_jobs": 6, "judge_calls": 163})
        self.assertEqual(
            sum(judge["budget"]["judge_calls"] for judge in self.manifest["judges"].values()),
            326,
        )
        serialized = json.dumps(self.manifest["judges"], sort_keys=True)
        for obsolete in ("pairs", "pair_count", "order_jobs", "deterministic_shortcuts"):
            self.assertNotIn(obsolete, serialized)

    def test_execution_is_single_job_fail_closed(self):
        self.assertEqual(
            self.manifest["execution"],
            {"jobs": 1, "per_case_timeout_seconds": 900, "automatic_retries": 0},
        )

    def test_terra_high_preset_resolves_to_real_model(self):
        presets = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            presets["gpt-5.6-terra-high"],
            {
                "model": "gpt-5.6-terra",
                "reasoning_effort": "high",
                "service_tier": "fast",
            },
        )


class ModelAbsoluteQualityRunnerTests(unittest.TestCase):
    def setUp(self):
        self.runner = load_runner()
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.manifest_path = write_fixture(self.root)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_plan_reports_six_jobs_and_exact_163_calls_for_each_judge(self):
        for judge_name in ("sol", "terra"):
            with self.subTest(judge=judge_name):
                plan = self.runner.build_plan(self.root, self.manifest_path, judge_name)
                self.assertEqual(len(plan.jobs), 6)
                self.assertEqual([len(job.case_ids) for job in plan.jobs], PASS_COUNTS)
                self.assertEqual(plan.judge_calls, 163)
                self.assertTrue(
                    all(job.output_path.is_relative_to(self.root.resolve()) for job in plan.jobs)
                )

    def test_plan_selects_only_hard_gate_passed_records(self):
        plan = self.runner.build_plan(self.root, self.manifest_path, "sol")
        for job in plan.jobs:
            records = {record["case_id"]: record for record in job.source_records}
            self.assertEqual(job.case_ids, tuple(case_id for case_id, record in records.items() if record["passed"]))
            self.assertTrue(all(records[case_id]["failure_type"] == "none" for case_id in job.case_ids))

    def test_plan_accepts_snapshot_specific_call_budget(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        source_path = self.root / manifest["models"][0]["source_summary"]["path"]
        source = json.loads(source_path.read_text(encoding="utf-8"))
        newly_passed = next(record for record in source["results"] if not record["passed"])
        newly_passed.update(
            {
                "passed": True,
                "failure_type": "none",
                "details": ["all deterministic checks passed"],
            }
        )
        source["passed"] += 1
        source["failed"] -= 1
        source_path.write_text(json.dumps(source, sort_keys=True) + "\n", encoding="utf-8")
        manifest["models"][0]["source_summary"]["sha256"] = sha256(source_path)
        for judge in manifest["judges"].values():
            judge["model_passed_counts"]["gpt-5.6-sol"] += 1
            judge["budget"]["judge_calls"] += 1
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        plan = self.runner.build_plan(self.root, self.manifest_path, "sol")

        self.assertEqual(plan.judge_calls, 164)
        self.assertEqual(len(plan.jobs[0].case_ids), 34)

    def test_frozen_plan_reconstructs_case_order_from_hashed_sources_after_catalog_drift(self):
        cases_path = self.root / "evals" / "cases.jsonl"
        cases_path.write_text(cases_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

        with self.assertRaisesRegex(self.runner.MatrixError, "cases snapshot hash drift"):
            self.runner.build_plan(self.root, self.manifest_path, "sol")

        (self.root / "CRITICAL_INSTRUCTIONS.md").write_text(
            "new live instructions\n",
            encoding="utf-8",
        )

        plan = self.runner.build_frozen_plan(
            self.root,
            self.manifest_path,
            "sol",
        )

        self.assertEqual(len(plan.cases_by_id), 50)
        self.assertEqual(len(plan.jobs), 6)
        self.assertEqual([len(job.case_ids) for job in plan.jobs], PASS_COUNTS)
        self.assertEqual(plan.judge_calls, 163)

    def test_frozen_plan_still_rejects_source_hash_drift(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        source = self.root / manifest["models"][0]["source_summary"]["path"]
        source.write_text(source.read_text(encoding="utf-8") + " ", encoding="utf-8")

        with self.assertRaisesRegex(self.runner.MatrixError, "source hash"):
            self.runner.build_frozen_plan(self.root, self.manifest_path, "sol")

    def test_plan_rejects_source_hash_or_pass_count_drift(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        source = self.root / manifest["models"][0]["source_summary"]["path"]
        source.write_text(source.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaisesRegex(self.runner.MatrixError, "source hash"):
            self.runner.build_plan(self.root, self.manifest_path, "sol")

        write_fixture(self.root)
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["judges"]["sol"]["model_passed_counts"]["gpt-5.6-sol"] = 32
        manifest["judges"]["sol"]["budget"]["judge_calls"] = 162
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(self.runner.MatrixError, "passed counts"):
            self.runner.build_plan(self.root, self.manifest_path, "sol")

    def test_plan_rejects_pairwise_fields_or_noncanonical_model_identity(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["judges"]["sol"]["pairs"] = [["gpt-5.6-sol", "gpt-5.5"]]
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(self.runner.MatrixError, "pairwise"):
            self.runner.build_plan(self.root, self.manifest_path, "sol")

        self.manifest_path = write_fixture(self.root)
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["models"][0]["id"] = "../escape"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(self.runner.MatrixError, "model contract"):
            self.runner.build_plan(self.root, self.manifest_path, "sol")

    def test_command_is_single_response_blinded_and_schema_bound(self):
        plan = self.runner.build_plan(self.root, self.manifest_path, "sol")
        job = plan.jobs[0]
        case_id = job.case_ids[0]
        command, prompt = self.runner.build_case_invocation(
            plan,
            job,
            case_id,
            agent_command="/opt/codex -a never exec",
        )
        payload = json.loads(prompt)
        self.assertEqual(payload["response"]["label"], "response")
        self.assertNotIn(job.model_id, prompt)
        self.assertNotIn(job.model_label, prompt)
        self.assertNotIn("baseline", payload)
        self.assertNotIn("candidate", payload)
        self.assertIn("absolute-quality-judge.schema.json", " ".join(command))
        self.assertIn("gpt-5.6-sol", command)
        self.assertIn('model_reasoning_effort="medium"', command)

    def test_existing_output_rejects_unexpected_entries_and_symlinks(self):
        plan = self.runner.build_plan(self.root, self.manifest_path, "sol")
        judge_root = plan.output_root / "judgments" / "sol"
        judge_root.mkdir(parents=True)
        (judge_root / "unexpected").mkdir()
        with self.assertRaisesRegex(self.runner.MatrixError, "unexpected"):
            self.runner.validate_output_state(plan)

        shutil.rmtree(judge_root)
        judge_root.mkdir(parents=True)
        target = self.root / "outside"
        target.mkdir()
        (judge_root / plan.jobs[0].model_id).symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(self.runner.MatrixError, "symlink"):
            self.runner.validate_output_state(plan)

    def test_run_stops_after_first_failure_without_retry(self):
        plan = self.runner.build_plan(self.root, self.manifest_path, "sol")
        failed = subprocess.CompletedProcess([], 7, stdout="", stderr="failure")
        with mock.patch.object(self.runner.subprocess, "run", return_value=failed) as run:
            with self.assertRaisesRegex(self.runner.MatrixError, "exited with code 7"):
                self.runner.execute_plan(plan, "/opt/codex -a never exec")
        self.assertEqual(run.call_count, 1)

    def test_complete_summary_is_skipped_only_after_full_provenance_validation(self):
        plan = self.runner.build_plan(self.root, self.manifest_path, "sol")
        first = plan.jobs[0]
        records = {record["case_id"]: record for record in first.source_records}
        judgments = [
            {
                "case_id": case_id,
                "response_sha256": self.runner.response_sha256(records[case_id]),
                "score": 80,
                "confidence": "high",
                "reason": "fixture",
                "checks": [
                    {"id": check_id, "score": 80, "note": "fixture"}
                    for check_id in self.runner.evals.QUALITY_CHECK_IDS
                ],
            }
            for case_id in first.case_ids
        ]
        first.output_path.mkdir(parents=True)
        (first.output_path / "summary.json").write_text(
            json.dumps(self.runner.build_model_summary(plan, first, judgments)),
            encoding="utf-8",
        )
        states = self.runner.validate_output_state(plan)
        self.assertEqual(states[first.model_id], "complete")

        summary_path = first.output_path / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["judgments"][0]["response_sha256"] = "0" * 64
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        with self.assertRaisesRegex(self.runner.MatrixError, "response digest"):
            self.runner.validate_output_state(plan)

        summary["judgments"][0]["response_sha256"] = self.runner.response_sha256(
            records[first.case_ids[0]]
        )
        summary["judgments"][0]["winner"] = "gpt-5.6-sol"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        with self.assertRaisesRegex(self.runner.MatrixError, "judgment contract"):
            self.runner.validate_output_state(plan)


class ModelAbsoluteQualityAggregatorTests(unittest.TestCase):
    def setUp(self):
        self.runner = load_runner()
        self.aggregator = load_aggregator()
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.manifest_path = write_fixture(self.root)
        self.plans = {
            judge: self.runner.build_plan(self.root, self.manifest_path, judge)
            for judge in ("sol", "terra")
        }
        for judge_name, plan in self.plans.items():
            for model_index, job in enumerate(plan.jobs):
                records = {record["case_id"]: record for record in job.source_records}
                base_score = 60 + model_index * 3 + (2 if judge_name == "terra" else 0)
                judgments = []
                for case_index, case_id in enumerate(job.case_ids):
                    score = base_score + case_index % 3
                    judgments.append(
                        {
                            "case_id": case_id,
                            "response_sha256": self.runner.response_sha256(records[case_id]),
                            "score": score,
                            "confidence": "high",
                            "reason": "fixture",
                            "checks": [
                                {"id": check_id, "score": score, "note": "fixture"}
                                for check_id in self.runner.evals.QUALITY_CHECK_IDS
                            ],
                        }
                    )
                job.output_path.mkdir(parents=True)
                (job.output_path / "summary.json").write_text(
                    json.dumps(self.runner.build_model_summary(plan, job, judgments)),
                    encoding="utf-8",
                )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_aggregates_six_absolute_models_and_all_15_common_case_pairs(self):
        result = self.aggregator.aggregate_judge(
            self.root, self.manifest_path, "sol", output_root=self.plans["sol"].output_root
        )

        self.assertEqual(result["methodology"], "single_response_absolute_scoring")
        self.assertEqual(result["total_judgments"], 163)
        self.assertEqual(len(result["models"]), 6)
        self.assertEqual(len(result["common_case_comparisons"]), 15)
        self.assertEqual(
            [model["hard_gate_passed"] for model in result["models"]], PASS_COUNTS
        )
        self.assertEqual(result["models"][0]["hard_gate_pass_rate"], 0.66)
        self.assertEqual(
            set(result["models"][0]["dimension_scores"]),
            set(self.runner.evals.QUALITY_CHECK_IDS),
        )
        first_pair = result["common_case_comparisons"][0]
        self.assertEqual((first_pair["model_a_id"], first_pair["model_b_id"]), tuple(MODEL_IDS[:2]))
        self.assertGreater(first_pair["overlap"], 0)
        self.assertEqual(
            first_pair["a_higher"] + first_pair["equal"] + first_pair["b_higher"],
            first_pair["overlap"],
        )
        serialized = json.dumps(result, sort_keys=True)
        for forbidden in ("global_rank", "leaderboard", "pairwise_judge", "orientation"):
            self.assertNotIn(forbidden, serialized)

    def test_pair_comparison_uses_only_intersection_and_saved_absolute_scores(self):
        result = self.aggregator.aggregate_judge(
            self.root, self.manifest_path, "sol", output_root=self.plans["sol"].output_root
        )
        pair = result["common_case_comparisons"][0]
        a_passed = set(self.plans["sol"].jobs[0].case_ids)
        b_passed = set(self.plans["sol"].jobs[1].case_ids)
        self.assertEqual(pair["overlap"], len(a_passed & b_passed))
        self.assertEqual(pair["direction"], "gpt-5.5")
        self.assertGreater(pair["mean_delta_b_minus_a"], 0)

    def test_sol_terra_audit_keeps_both_judges_visible(self):
        sol = self.aggregator.aggregate_judge(
            self.root, self.manifest_path, "sol", output_root=self.plans["sol"].output_root
        )
        terra = self.aggregator.aggregate_judge(
            self.root, self.manifest_path, "terra", output_root=self.plans["terra"].output_root
        )
        audit = self.aggregator.aggregate_judge_audit(sol, terra)

        self.assertEqual(len(audit["models"]), 6)
        self.assertEqual(len(audit["common_case_comparisons"]), 15)
        self.assertEqual(audit["models"][0]["terra_minus_sol_mean_score"], 2.0)
        pair = audit["common_case_comparisons"][0]
        self.assertIn("sol_direction", pair)
        self.assertIn("terra_direction", pair)
        self.assertIn("judge_sensitive", pair)
        self.assertIn("changed_case_directions", pair)

    def test_sol_terra_audit_accepts_snapshot_specific_equal_coverage(self):
        sol = self.aggregator.aggregate_judge(
            self.root, self.manifest_path, "sol", output_root=self.plans["sol"].output_root
        )
        terra = self.aggregator.aggregate_judge(
            self.root, self.manifest_path, "terra", output_root=self.plans["terra"].output_root
        )
        for result in (sol, terra):
            result["models"][0]["hard_gate_passed"] += 1
            result["models"][0]["case_scores"]["newly-passed-case"] = 80
            result["total_judgments"] += 1

        audit = self.aggregator.aggregate_judge_audit(sol, terra)

        self.assertEqual(len(audit["models"]), 6)

    def test_aggregation_fails_closed_on_incomplete_or_drifted_judgments(self):
        missing = self.plans["sol"].jobs[-1].output_path / "summary.json"
        missing.unlink()
        with self.assertRaisesRegex(self.runner.MatrixError, "incomplete"):
            self.aggregator.aggregate_judge(
                self.root,
                self.manifest_path,
                "sol",
                output_root=self.plans["sol"].output_root,
            )

    def test_write_and_check_are_byte_identical(self):
        canonical_root = self.plans["sol"].output_root / "canonical"
        self.aggregator.write_all(
            self.root,
            self.manifest_path,
            output_root=self.plans["sol"].output_root,
            canonical_root=canonical_root,
            check=False,
        )
        before = {path.name: path.read_bytes() for path in canonical_root.iterdir()}
        self.aggregator.write_all(
            self.root,
            self.manifest_path,
            output_root=self.plans["sol"].output_root,
            canonical_root=canonical_root,
            check=True,
        )
        after = {path.name: path.read_bytes() for path in canonical_root.iterdir()}
        self.assertEqual(after, before)

    def test_write_uses_frozen_plan_after_instruction_metadata_drift(self):
        (self.root / "CRITICAL_INSTRUCTIONS.md").write_text(
            "Custom Instructions v4.14 metadata-only release\n",
            encoding="utf-8",
        )
        canonical_root = self.plans["sol"].output_root / "canonical"

        self.aggregator.write_all(
            self.root,
            self.manifest_path,
            output_root=self.plans["sol"].output_root,
            canonical_root=canonical_root,
            check=False,
        )

        self.assertTrue((canonical_root / "sol-absolute.json").is_file())
        self.assertTrue((canonical_root / "terra-absolute.json").is_file())


if __name__ == "__main__":
    unittest.main()
