import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "aggregate_saved_model_quality.py"
BASELINE_LABEL = "empty"
CURRENT_LABEL = "current"
JUDGE = {
    "preset": "gpt-5.6-sol-medium",
    "model": "gpt-5.6-sol",
    "reasoning_effort": "medium",
    "service_tier": "fast",
    "agent_command_mode": "current-codex",
}
CHECK_IDS = [
    "instruction_activation",
    "evidence_grounding",
    "scope_control",
    "engineering_specificity",
    "verification_quality",
    "risk_handling",
    "noise_control",
]


def load_script():
    if not SCRIPT_PATH.is_file():
        raise ImportError(f"missing TDD target: {SCRIPT_PATH}")
    spec = importlib.util.spec_from_file_location("aggregate_saved_model_quality", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def semantic_comparison(
    case_id,
    *,
    orientation,
    winner,
    baseline_score,
    current_score,
    source="llm_judge",
    baseline_passed=True,
    current_passed=True,
):
    baseline_record = {
        "label": BASELINE_LABEL,
        "passed": baseline_passed,
        "failure_type": "none" if baseline_passed else "behavior",
        "decision": "pass" if baseline_passed else "no_op",
        "risk_level": "low",
        "summary": f"baseline response for {case_id}",
        "evidence_count": 1,
        "actions_count": 1,
    }
    current_record = {
        "label": CURRENT_LABEL,
        "passed": current_passed,
        "failure_type": "none" if current_passed else "behavior",
        "decision": "pass" if current_passed else "no_op",
        "risk_level": "low",
        "summary": f"current response for {case_id}",
        "evidence_count": 1,
        "actions_count": 1,
    }

    if orientation == "baseline_first":
        raw_baseline = baseline_record
        raw_candidate = current_record
        raw_winner = winner
        raw_baseline_score = baseline_score
        raw_current_score = current_score
    elif orientation == "current_first":
        raw_baseline = current_record
        raw_candidate = baseline_record
        raw_winner = {"baseline": "current", "current": "baseline"}.get(winner, winner)
        raw_baseline_score = current_score
        raw_current_score = baseline_score
    else:
        raise AssertionError(f"unknown fixture orientation: {orientation}")

    checks = []
    if source == "llm_judge":
        checks = [
            {
                "id": check_id,
                "baseline_score": raw_baseline_score,
                "current_score": raw_current_score,
                "winner": raw_winner,
                "note": "fixture judgment",
            }
            for check_id in CHECK_IDS
        ]
    return {
        "case_id": case_id,
        "baseline": raw_baseline,
        "candidate": raw_candidate,
        "quality": {
            "source": source,
            "winner": raw_winner,
            "baseline_score": raw_baseline_score,
            "current_score": raw_current_score,
            "delta": raw_current_score - raw_baseline_score,
            "confidence": "low" if raw_winner == "inconclusive" else "high",
            "review_needed": raw_winner == "inconclusive",
            "reason": "fixture judgment",
            "checks": checks,
        },
    }


def raw_aggregate(comparisons):
    winners = {"baseline": 0, "current": 0, "tie": 0, "inconclusive": 0}
    sources = {}
    confidence = {}
    baseline_scores = []
    current_scores = []
    for item in comparisons:
        quality = item["quality"]
        winners[quality["winner"]] += 1
        source = quality["source"]
        sources[source] = sources.get(source, 0) + 1
        conf = quality["confidence"]
        confidence[conf] = confidence.get(conf, 0) + 1
        baseline_scores.append(quality["baseline_score"])
        current_scores.append(quality["current_score"])
    average_baseline = round(sum(baseline_scores) / len(baseline_scores), 1)
    average_current = round(sum(current_scores) / len(current_scores), 1)
    return {
        "total": len(comparisons),
        "baseline_passed": sum(1 for item in comparisons if item["baseline"]["passed"]),
        "candidate_passed": sum(1 for item in comparisons if item["candidate"]["passed"]),
        "winners": winners,
        "sources": sources,
        "confidence": confidence,
        "average_baseline_score": average_baseline,
        "average_current_score": average_current,
        "average_delta": round(average_current - average_baseline, 1),
    }


def refresh_aggregate(report):
    report["aggregate"] = raw_aggregate(report["comparisons"])


def collect_keys(value):
    if isinstance(value, dict):
        keys = set(value)
        for nested in value.values():
            keys.update(collect_keys(nested))
        return keys
    if isinstance(value, list):
        keys = set()
        for nested in value:
            keys.update(collect_keys(nested))
        return keys
    return set()


def order_report(orientation, comparisons):
    if orientation == "baseline_first":
        baseline_label, candidate_label = BASELINE_LABEL, CURRENT_LABEL
    elif orientation == "current_first":
        baseline_label, candidate_label = CURRENT_LABEL, BASELINE_LABEL
    else:
        raise AssertionError(f"unknown fixture orientation: {orientation}")
    return {
        "baseline_label": baseline_label,
        "candidate_label": candidate_label,
        "judge": dict(JUDGE),
        "aggregate": raw_aggregate(comparisons),
        "comparisons": comparisons,
    }


def semantic_record(report, item, label):
    if report["baseline_label"] == label:
        return item["baseline"]
    if report["candidate_label"] == label:
        return item["candidate"]
    raise AssertionError(f"fixture report does not contain label {label!r}")


def source_records(report, label):
    return {item["case_id"]: copy.deepcopy(semantic_record(report, item, label)) for item in report["comparisons"]}


def source_summary(report, label):
    results = []
    for item in report["comparisons"]:
        reduced = semantic_record(report, item, label)
        results.append(
            {
                "case_id": item["case_id"],
                "label": label,
                "passed": reduced["passed"],
                "failure_type": reduced["failure_type"],
                "final_response": {
                    "decision": reduced["decision"],
                    "risk_level": reduced["risk_level"],
                    "summary": reduced["summary"],
                    "evidence": ["fixture evidence"] * reduced["evidence_count"],
                    "actions": ["fixture action"] * reduced["actions_count"],
                },
            }
        )
    passed = sum(1 for item in results if item["passed"])
    return {
        "label": label,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_order_artifact(root, name, report):
    summary_dir = root / name / f"{report['baseline_label']}-saved-model-quality"
    quality_path = summary_dir / "pairs" / report["candidate_label"] / "quality.json"
    summary_path = summary_dir / "model-quality-summary.json"
    write_json(quality_path, report)
    write_json(
        summary_path,
        {
            "label": f"{report['baseline_label']}-saved-model-quality",
            "baseline_label": report["baseline_label"],
            "judge": report["judge"],
            "pairs": [
                {
                    "candidate_label": report["candidate_label"],
                    "judge": report["judge"],
                    "aggregate": report["aggregate"],
                    "quality_json": str(quality_path),
                }
            ],
        },
    )
    return {"summary": summary_path, "quality": quality_path}


def write_complete_fixture(root):
    cases = [
        {
            "case_id": "case-llm",
            "winner": "current",
            "baseline_score": 80,
            "current_score": 90,
            "source": "llm_judge",
            "baseline_passed": True,
            "current_passed": True,
        },
        {
            "case_id": "case-hard",
            "winner": "current",
            "baseline_score": 0,
            "current_score": 100,
            "source": "hard_gate",
            "baseline_passed": False,
            "current_passed": True,
        },
    ]

    def report_for(orientation):
        return order_report(
            orientation,
            [semantic_comparison(orientation=orientation, **case) for case in cases],
        )

    baseline_first = report_for("baseline_first")
    current_first = report_for("current_first")
    baseline_source = root / "sources" / BASELINE_LABEL / "summary.json"
    current_source = root / "sources" / CURRENT_LABEL / "summary.json"
    write_json(baseline_source, source_summary(baseline_first, BASELINE_LABEL))
    write_json(current_source, source_summary(baseline_first, CURRENT_LABEL))
    return {
        "baseline_first_report": baseline_first,
        "current_first_report": current_first,
        "baseline_first": write_order_artifact(root, "baseline-first", baseline_first),
        "current_first": write_order_artifact(root, "current-first", current_first),
        "baseline_source": baseline_source,
        "current_source": current_source,
    }


def cli_args(root, fixture, output_root="out"):
    return [
        "--repo-root",
        str(root),
        "--model-id",
        "gpt-5.5",
        "--model-label",
        "GPT-5.5",
        "--baseline-label",
        BASELINE_LABEL,
        "--current-label",
        CURRENT_LABEL,
        "--baseline-source-summary",
        str(fixture["baseline_source"].relative_to(root)),
        "--current-source-summary",
        str(fixture["current_source"].relative_to(root)),
        "--order-summary",
        str(fixture["current_first"]["summary"].relative_to(root)),
        "--order-summary",
        str(fixture["baseline_first"]["summary"].relative_to(root)),
        "--output-root",
        output_root,
    ]


class AggregateSavedModelQualityTests(unittest.TestCase):
    def test_eval_readme_documents_grader_side_inputs_and_canonical_offline_aggregation(self):
        readme = (REPO_ROOT / "evals" / "README.md").read_text(encoding="utf-8")
        normalized = " ".join(readme.split())

        for required in (
            "only the candidate instruction bundle and final-response schema",
            "Cases, rubrics, fixtures, presets, and reference metadata stay grader-side",
            "scripts/aggregate_saved_model_quality.py",
            "baseline",
            "current",
            "tie",
            "inconclusive",
            "order_sensitive",
            "source/order path, hash, and orientation validation",
        ):
            self.assertIn(required, normalized)
        self.assertNotIn(
            "keeps eval cases, schemas, presets, and reference metadata available in the temporary workspace",
            normalized,
        )
        self.assertNotIn(
            "automatic dual-order aggregation is intentionally a follow-up change",
            normalized,
        )

    def test_normalize_order_comparison_maps_both_orientations_to_semantic_arms(self):
        module = load_script()
        baseline_first_item = semantic_comparison(
            "case-a",
            orientation="baseline_first",
            winner="current",
            baseline_score=40,
            current_score=90,
        )
        current_first_item = semantic_comparison(
            "case-a",
            orientation="current_first",
            winner="current",
            baseline_score=40,
            current_score=90,
        )
        baseline_first = order_report("baseline_first", [baseline_first_item])
        current_first = order_report("current_first", [current_first_item])

        self.assertEqual(baseline_first_item["quality"]["winner"], "current")
        self.assertEqual(current_first_item["quality"]["winner"], "baseline")

        expected = {
            "case_id": "case-a",
            "baseline_passed": True,
            "current_passed": True,
            "source": "llm_judge",
            "winner": "current",
            "baseline_score": 40,
            "current_score": 90,
            "delta": 50,
        }
        for report, item in [(baseline_first, baseline_first_item), (current_first, current_first_item)]:
            normalized = module.normalize_order_comparison(
                report,
                item,
                baseline_label=BASELINE_LABEL,
                current_label=CURRENT_LABEL,
            )
            for key, value in expected.items():
                self.assertEqual(normalized[key], value, key)

    def test_aggregate_dual_order_uses_strict_verdict_consensus(self):
        module = load_script()
        baseline_first_verdicts = {
            "stable-current": "current",
            "stable-baseline": "baseline",
            "stable-tie": "tie",
            "stable-inconclusive": "inconclusive",
            "winner-flip": "current",
            "tie-vs-current": "tie",
            "inconclusive-vs-tie": "inconclusive",
        }
        current_first_verdicts = {
            "stable-current": "current",
            "stable-baseline": "baseline",
            "stable-tie": "tie",
            "stable-inconclusive": "inconclusive",
            "winner-flip": "baseline",
            "tie-vs-current": "current",
            "inconclusive-vs-tie": "tie",
        }
        baseline_first = order_report(
            "baseline_first",
            [
                semantic_comparison(
                    case_id,
                    orientation="baseline_first",
                    winner=winner,
                    baseline_score=50,
                    current_score=50,
                )
                for case_id, winner in baseline_first_verdicts.items()
            ],
        )
        current_first = order_report(
            "current_first",
            [
                semantic_comparison(
                    case_id,
                    orientation="current_first",
                    winner=winner,
                    baseline_score=50,
                    current_score=50,
                )
                for case_id, winner in current_first_verdicts.items()
            ],
        )

        result = module.aggregate_dual_order(
            [current_first, baseline_first],
            baseline_label=BASELINE_LABEL,
            current_label=CURRENT_LABEL,
        )

        self.assertEqual(
            result["aggregate"]["winners"],
            {"baseline": 1, "current": 1, "tie": 1, "inconclusive": 1, "order_sensitive": 3},
        )
        by_case = {item["case_id"]: item for item in result["comparisons"]}
        self.assertEqual(by_case["stable-current"]["winner"], "current")
        self.assertEqual(by_case["stable-baseline"]["winner"], "baseline")
        self.assertEqual(by_case["stable-tie"]["winner"], "tie")
        self.assertEqual(by_case["stable-inconclusive"]["winner"], "inconclusive")
        self.assertEqual(by_case["winner-flip"]["winner"], "order_sensitive")
        self.assertEqual(by_case["tie-vs-current"]["winner"], "order_sensitive")
        self.assertEqual(by_case["inconclusive-vs-tie"]["winner"], "order_sensitive")

    def test_aggregate_dual_order_rejects_hard_gate_disagreement(self):
        module = load_script()
        baseline_first_item = semantic_comparison(
            "case-hard",
            orientation="baseline_first",
            winner="baseline",
            baseline_score=100,
            current_score=0,
            source="hard_gate",
            baseline_passed=True,
            current_passed=False,
        )
        current_first_item = semantic_comparison(
            "case-hard",
            orientation="current_first",
            winner="baseline",
            baseline_score=100,
            current_score=0,
            source="hard_gate",
            baseline_passed=True,
            current_passed=False,
        )
        current_first_item["quality"]["winner"] = "baseline"
        baseline_first = order_report("baseline_first", [baseline_first_item])
        current_first = order_report("current_first", [current_first_item])

        with self.assertRaises(module.evals.ValidationError):
            module.aggregate_dual_order(
                [baseline_first, current_first],
                baseline_label=BASELINE_LABEL,
                current_label=CURRENT_LABEL,
            )

    def test_aggregate_dual_order_pools_raw_all_and_llm_scores_before_rounding(self):
        module = load_script()
        cases = [
            {
                "case_id": "llm-one",
                "winner": "current",
                "baseline_score": 50,
                "current_score": 51,
                "source": "llm_judge",
                "baseline_passed": True,
                "current_passed": True,
            },
            {
                "case_id": "llm-two",
                "winner": "tie",
                "baseline_score": 50,
                "current_score": 50,
                "source": "llm_judge",
                "baseline_passed": True,
                "current_passed": True,
            },
            {
                "case_id": "llm-three",
                "winner": "tie",
                "baseline_score": 50,
                "current_score": 50,
                "source": "llm_judge",
                "baseline_passed": True,
                "current_passed": True,
            },
            {
                "case_id": "hard-current",
                "winner": "current",
                "baseline_score": 0,
                "current_score": 100,
                "source": "hard_gate",
                "baseline_passed": False,
                "current_passed": True,
            },
        ]

        def comparisons_for(orientation):
            return [semantic_comparison(orientation=orientation, **case) for case in cases]

        baseline_first = order_report("baseline_first", comparisons_for("baseline_first"))
        current_first = order_report("current_first", comparisons_for("current_first"))
        self.assertEqual(baseline_first["aggregate"]["average_delta"], 25.3)
        self.assertEqual(current_first["aggregate"]["average_delta"], -25.3)

        result = module.aggregate_dual_order(
            [baseline_first, current_first],
            baseline_label=BASELINE_LABEL,
            current_label=CURRENT_LABEL,
        )

        self.assertEqual(
            result["aggregate"]["scores"]["all_cases"],
            {"cases": 4, "baseline": 37.5, "current": 62.75, "delta": 25.25},
        )
        self.assertEqual(
            result["aggregate"]["scores"]["llm_judge"],
            {"cases": 3, "baseline": 50.0, "current": 50.33, "delta": 0.33},
        )

    def test_load_order_reports_accepts_exactly_two_reversed_wrappers(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = write_complete_fixture(root)

            reports = module.load_order_reports(
                [fixture["current_first"]["summary"], fixture["baseline_first"]["summary"]],
                repo_root=root,
                baseline_label=BASELINE_LABEL,
                current_label=CURRENT_LABEL,
            )

        self.assertEqual(set(reports), {"baseline_first", "current_first"})
        self.assertEqual(reports["baseline_first"]["baseline_label"], BASELINE_LABEL)
        self.assertEqual(reports["current_first"]["baseline_label"], CURRENT_LABEL)

    def test_load_order_reports_rejects_wrong_count_orientation_and_quality_pointer(self):
        module = load_script()
        for scenario in ["one-wrapper", "three-wrappers", "same-orientation", "wrong-pointer"]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fixture = write_complete_fixture(root)
                baseline_summary = fixture["baseline_first"]["summary"]
                current_summary = fixture["current_first"]["summary"]
                if scenario == "one-wrapper":
                    paths = [baseline_summary]
                elif scenario == "three-wrappers":
                    paths = [baseline_summary, current_summary, baseline_summary]
                elif scenario == "same-orientation":
                    paths = [baseline_summary, baseline_summary]
                else:
                    wrapper = read_json(current_summary)
                    outside_quality = root / "outside" / "quality.json"
                    write_json(outside_quality, fixture["current_first_report"])
                    wrapper["pairs"][0]["quality_json"] = str(outside_quality)
                    write_json(current_summary, wrapper)
                    paths = [baseline_summary, current_summary]

                with self.assertRaises(module.evals.ValidationError):
                    module.load_order_reports(
                        paths,
                        repo_root=root,
                        baseline_label=BASELINE_LABEL,
                        current_label=CURRENT_LABEL,
                    )

    def test_aggregate_dual_order_rejects_duplicate_and_missing_ids_but_accepts_reordering(self):
        module = load_script()
        cases = [
            {
                "case_id": case_id,
                "winner": "current",
                "baseline_score": 80,
                "current_score": 90,
            }
            for case_id in ["case-b", "case-a"]
        ]

        def reports():
            baseline_first = order_report(
                "baseline_first",
                [semantic_comparison(orientation="baseline_first", **case) for case in cases],
            )
            current_first = order_report(
                "current_first",
                [semantic_comparison(orientation="current_first", **case) for case in cases],
            )
            return baseline_first, current_first

        baseline_first, current_first = reports()
        baseline_first["comparisons"].append(copy.deepcopy(baseline_first["comparisons"][0]))
        refresh_aggregate(baseline_first)
        with self.assertRaises(module.evals.ValidationError):
            module.aggregate_dual_order(
                [baseline_first, current_first],
                baseline_label=BASELINE_LABEL,
                current_label=CURRENT_LABEL,
            )

        baseline_first, current_first = reports()
        current_first["comparisons"].pop()
        refresh_aggregate(current_first)
        with self.assertRaises(module.evals.ValidationError):
            module.aggregate_dual_order(
                [baseline_first, current_first],
                baseline_label=BASELINE_LABEL,
                current_label=CURRENT_LABEL,
            )

        baseline_first, current_first = reports()
        current_first["comparisons"].reverse()
        result = module.aggregate_dual_order(
            [baseline_first, current_first],
            baseline_label=BASELINE_LABEL,
            current_label=CURRENT_LABEL,
        )
        self.assertEqual([item["case_id"] for item in result["comparisons"]], ["case-a", "case-b"])

    def test_aggregate_dual_order_rejects_identity_and_source_summary_mismatches(self):
        module = load_script()

        def reports():
            case = {
                "case_id": "case-a",
                "winner": "current",
                "baseline_score": 80,
                "current_score": 90,
            }
            baseline_first = order_report(
                "baseline_first",
                [semantic_comparison(orientation="baseline_first", **case)],
            )
            current_first = order_report(
                "current_first",
                [semantic_comparison(orientation="current_first", **case)],
            )
            return baseline_first, current_first

        for scenario in [
            "judge",
            "source",
            "reduced-record",
            "source-summary",
            "cross-family",
        ]:
            with self.subTest(scenario=scenario):
                baseline_first, current_first = reports()
                baseline_sources = source_records(baseline_first, BASELINE_LABEL)
                current_sources = source_records(baseline_first, CURRENT_LABEL)
                if scenario == "judge":
                    current_first["judge"]["reasoning_effort"] = "high"
                elif scenario == "source":
                    current_first["comparisons"][0]["quality"]["source"] = "hard_gate"
                    refresh_aggregate(current_first)
                elif scenario == "reduced-record":
                    current_first["comparisons"][0]["baseline"]["summary"] = "different current response"
                elif scenario == "source-summary":
                    current_sources["case-a"]["summary"] = "different source summary"
                else:
                    current_first["comparisons"][0]["baseline"]["summary"] = "other-family current"
                    current_first["comparisons"][0]["candidate"]["summary"] = "other-family baseline"

                with self.assertRaises(module.evals.ValidationError):
                    module.aggregate_dual_order(
                        [baseline_first, current_first],
                        baseline_label=BASELINE_LABEL,
                        current_label=CURRENT_LABEL,
                        baseline_source_records=baseline_sources,
                        current_source_records=current_sources,
                    )

    def test_aggregate_dual_order_rejects_invalid_scores_and_delta(self):
        module = load_script()
        for scenario in ["bool-score", "out-of-range", "inconsistent-delta"]:
            with self.subTest(scenario=scenario):
                case = {
                    "case_id": "case-a",
                    "winner": "current",
                    "baseline_score": 80,
                    "current_score": 90,
                }
                baseline_first = order_report(
                    "baseline_first",
                    [semantic_comparison(orientation="baseline_first", **case)],
                )
                current_first = order_report(
                    "current_first",
                    [semantic_comparison(orientation="current_first", **case)],
                )
                quality = current_first["comparisons"][0]["quality"]
                if scenario == "bool-score":
                    quality["baseline_score"] = True
                    quality["delta"] = quality["current_score"] - quality["baseline_score"]
                    refresh_aggregate(current_first)
                elif scenario == "out-of-range":
                    quality["current_score"] = 101
                    quality["delta"] = quality["current_score"] - quality["baseline_score"]
                    refresh_aggregate(current_first)
                else:
                    quality["delta"] = 999

                with self.assertRaises(module.evals.ValidationError):
                    module.aggregate_dual_order(
                        [baseline_first, current_first],
                        baseline_label=BASELINE_LABEL,
                        current_label=CURRENT_LABEL,
                    )

    def test_load_order_reports_rejects_stale_aggregate_even_when_wrapper_matches_quality(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = write_complete_fixture(root)
            quality_path = fixture["baseline_first"]["quality"]
            summary_path = fixture["baseline_first"]["summary"]
            quality = read_json(quality_path)
            quality["aggregate"]["total"] = 999
            write_json(quality_path, quality)
            wrapper = read_json(summary_path)
            wrapper["pairs"][0]["aggregate"] = copy.deepcopy(quality["aggregate"])
            write_json(summary_path, wrapper)

            with self.assertRaises(module.evals.ValidationError):
                module.load_order_reports(
                    [summary_path, fixture["current_first"]["summary"]],
                    repo_root=root,
                    baseline_label=BASELINE_LABEL,
                    current_label=CURRENT_LABEL,
                )

    def test_main_writes_deterministic_schema_relative_pointer_and_input_hashes(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = write_complete_fixture(root)
            args = cli_args(root, fixture)
            output_dir = root / "out" / "gpt-5.5"
            summary_path = output_dir / "dual-order-summary.json"
            quality_path = output_dir / "dual-order-quality.json"
            summary_md = output_dir / "dual-order-summary.md"
            quality_md = output_dir / "dual-order-quality.md"

            self.assertEqual(module.main(args), 0)
            paths = [summary_path, quality_path, summary_md, quality_md]
            first_bytes = {path.name: path.read_bytes() for path in paths}
            summary = read_json(summary_path)
            quality = read_json(quality_path)

            self.assertEqual(
                set(summary),
                {
                    "schema_version",
                    "aggregation",
                    "model_id",
                    "model_label",
                    "baseline_label",
                    "current_label",
                    "judge",
                    "aggregate",
                    "quality_json",
                },
            )
            self.assertEqual(summary["schema_version"], 1)
            self.assertEqual(summary["aggregation"], "dual_order_consensus")
            self.assertEqual(summary["quality_json"], "dual-order-quality.json")
            self.assertEqual(
                set(quality),
                {
                    "schema_version",
                    "aggregation",
                    "model_id",
                    "model_label",
                    "baseline_label",
                    "current_label",
                    "judge",
                    "inputs",
                    "aggregate",
                    "comparisons",
                },
            )
            self.assertEqual(summary["aggregate"], quality["aggregate"])

            rel = lambda path: path.relative_to(root).as_posix()
            self.assertEqual(
                quality["inputs"],
                {
                    "source_summaries": {
                        "baseline": {"path": rel(fixture["baseline_source"]), "sha256": sha256(fixture["baseline_source"])},
                        "current": {"path": rel(fixture["current_source"]), "sha256": sha256(fixture["current_source"])},
                    },
                    "orders": {
                        "baseline_first": {
                            "summary_path": rel(fixture["baseline_first"]["summary"]),
                            "summary_sha256": sha256(fixture["baseline_first"]["summary"]),
                            "quality_path": rel(fixture["baseline_first"]["quality"]),
                            "quality_sha256": sha256(fixture["baseline_first"]["quality"]),
                        },
                        "current_first": {
                            "summary_path": rel(fixture["current_first"]["summary"]),
                            "summary_sha256": sha256(fixture["current_first"]["summary"]),
                            "quality_path": rel(fixture["current_first"]["quality"]),
                            "quality_sha256": sha256(fixture["current_first"]["quality"]),
                        },
                    },
                },
            )
            for item in quality["comparisons"]:
                self.assertEqual(
                    set(item),
                    {
                        "case_id",
                        "baseline_passed",
                        "current_passed",
                        "source",
                        "orders",
                        "winner",
                        "balanced_scores",
                    },
                )
                self.assertEqual(set(item["orders"]), {"baseline_first", "current_first"})
                for order in item["orders"].values():
                    self.assertEqual(set(order), {"winner", "baseline_score", "current_score", "delta"})
                self.assertEqual(set(item["balanced_scores"]), {"baseline", "current", "delta"})
            self.assertNotIn("reason", collect_keys(quality))
            self.assertNotIn("checks", collect_keys(quality))

            self.assertEqual(module.main(args), 0)
            self.assertEqual(first_bytes, {path.name: path.read_bytes() for path in paths})

    def test_main_validation_failure_leaves_no_partial_output(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = write_complete_fixture(root)
            current_source = read_json(fixture["current_source"])
            current_source["results"][0]["final_response"]["summary"] = "mismatched source response"
            write_json(fixture["current_source"], current_source)

            self.assertEqual(module.main(cli_args(root, fixture)), 2)
            self.assertFalse((root / "out").exists())

    def test_main_accepts_path_safe_dotted_and_hyphenated_model_ids(self):
        module = load_script()
        for model_id in ("gpt-5.5", "gpt-5.6-sol", "deepseek-v4-flash-thinking"):
            with self.subTest(model_id=model_id), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fixture = write_complete_fixture(root)
                args = cli_args(root, fixture)
                args[args.index("--model-id") + 1] = model_id

                self.assertEqual(module.main(args), 0)
                self.assertTrue((root / "out" / model_id / "dual-order-quality.json").is_file())

    def test_main_rejects_model_ids_that_are_not_strict_path_safe_slugs(self):
        module = load_script()
        for model_id in (".", "..", "bad/id", "Bad", "bad id", " bad", "bad "):
            with self.subTest(model_id=model_id), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fixture = write_complete_fixture(root)
                args = cli_args(root, fixture)
                args[args.index("--model-id") + 1] = model_id

                self.assertEqual(module.main(args), 2)


if __name__ == "__main__":
    unittest.main()
