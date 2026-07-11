import importlib.util
import hashlib
import io
import json
import os
import zlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_published_eval_metrics.py"
LEGACY_CAVEAT = (
    "Legacy pre-blinding snapshot: primary prompts exposed case id/scenario metadata "
    "(prompt contamination). The unchanged numbers are historical and are not clean blinded "
    "instruction-lift evidence."
)
LEGACY_SCOPE = (
    "Scope: legacy pre-blinding snapshot, 50 cases; primary prompts exposed case id/scenario metadata; "
    "all-model reference rows included."
)
SIX_MODEL_IDS = [
    "gpt-5.6-sol",
    "gpt-5.5",
    "glm-5.2",
    "grok-4.3",
    "deepseek-v4-flash",
    "deepseek-v4-flash-thinking",
]
EXPECTED_JUDGE_IDENTITY = {
    "model": "gpt-5.6-sol",
    "reasoning_effort": "medium",
    "service_tier": "fast",
    "agent_command_mode": "current-codex",
}
EXPECTED_JUDGE_PRESET = "gpt-5.6-sol-medium"
ORDER_CHECK_IDS = [
    "instruction_activation",
    "evidence_grounding",
    "scope_control",
    "engineering_specificity",
    "verification_quality",
    "risk_handling",
    "noise_control",
]
EXPECTED_BLINDED_SVGS = [
    "coverage-watchlist.svg",
    "empty-current-lift.svg",
    "hard-gates-50.svg",
    "quality-only-comparisons.svg",
    "model-quality-absolute.svg",
    "model-quality-common-cases.svg",
    "model-quality-judge-audit.svg",
]
BLINDED_HARD_GATE_SCOPE = (
    "Scope: blinded With instructions v4.13 vs Empty instructions hard gates, "
    "50 cases, 6 model/runner rows; no reference rows."
)
BLINDED_DUAL_ORDER_SCOPE = (
    "Scope: blinded With instructions v4.13 vs Empty instructions dual-order quality, "
    "50 cases, 6 model/runner rows; fixed gpt-5.6-sol-medium judge; "
    "order-sensitive verdicts are separate; no reference rows."
)
ABSOLUTE_QUALITY_SCOPE = (
    "Scope: blinded absolute quality, 157 hard-gate-passed responses across 6 models; "
    "single-response gpt-5.6-sol-medium judge; comparisons use common passed cases; no global ranking."
)
ABSOLUTE_JUDGE_AUDIT_SCOPE = (
    "Scope: Sol medium vs Terra high audit on the same 157 blinded responses; "
    "judge scores are shown separately and are not averaged."
)
EXPECTED_BLINDED_SVG_SCOPES = {
    "coverage-watchlist.svg": BLINDED_HARD_GATE_SCOPE,
    "empty-current-lift.svg": BLINDED_DUAL_ORDER_SCOPE,
    "hard-gates-50.svg": BLINDED_HARD_GATE_SCOPE,
    "quality-only-comparisons.svg": BLINDED_DUAL_ORDER_SCOPE,
    "model-quality-absolute.svg": ABSOLUTE_QUALITY_SCOPE,
    "model-quality-common-cases.svg": ABSOLUTE_QUALITY_SCOPE,
    "model-quality-judge-audit.svg": ABSOLUTE_JUDGE_AUDIT_SCOPE,
}
EXPECTED_BLINDED_DOC_HEADINGS = {
    "README.md": "## Blinded Six-Model Evidence",
    "evals/README.md": "## Blinded Six-Model Publication",
    "evals/RESULTS.md": "## Blinded Six-Model Snapshot",
    "evals/PROMPT_QUALITY_CASES.md": "## Blinded Six-Model Publication Scope",
    "evals/CHANGELOG.md": "## 2026-07-10 - Blinded Six-Model Refresh",
}
EXPECTED_ABSOLUTE_DOC_HEADINGS = {
    "README.md": "## Absolute Cross-Model Quality",
    "evals/README.md": "## Absolute Cross-Model Quality",
    "evals/RESULTS.md": "## Absolute Cross-Model Quality Snapshot",
    "evals/PROMPT_QUALITY_CASES.md": "## Absolute Cross-Model Quality Scope",
    "evals/CHANGELOG.md": "## 2026-07-10 - Absolute Cross-Model Quality",
}
FIXED_JUDGE_CAVEAT = "Fixed dual-order quality judge: `gpt-5.6-sol-medium`."
SAME_MODEL_JUDGE_CAVEAT = (
    "The GPT-5.6 Sol row uses the same model family as the fixed quality judge; "
    "this is instruction-lift evidence, not a cross-model leaderboard."
)
WITHIN_RUNNER_CAVEAT = (
    "These are within-runner With instructions v4.13 versus Empty instructions comparisons, not a cross-model leaderboard."
)
NO_REFERENCE_CAVEAT = "No OpenHands, Claude/Fable, or other reference rows are included."
GROK_BUILD_EXCLUSION_CAVEAT = (
    "Grok Build is excluded because repeated transport failures prevented a clean primary pair."
)


def load_script():
    spec = importlib.util.spec_from_file_location("check_published_eval_metrics", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def summary_fixture():
    return {
        "passed": 4,
        "failed": 0,
        "results": [
            {"case_id": "case-a", "label": "baseline-HEAD", "passed": True},
            {"case_id": "case-a", "label": "current", "passed": True},
            {"case_id": "case-b", "label": "baseline-HEAD", "passed": True},
            {"case_id": "case-b", "label": "current", "passed": True},
        ],
    }


def quality_fixture():
    return {
        "comparisons": [
            {"case_id": "case-a", "quality": {"winner": "current", "delta": 3}},
            {"case_id": "case-b", "quality": {"winner": "baseline", "delta": -1}},
        ]
    }


def snapshot_fixture(module):
    model_rows = [
        ("GPT-5.5", "GPT/Codex", 2, 1, 2, 28.4),
        ("GLM-5.2", "GLM-5.2", 2, 1, 2, 62.9),
        ("Grok 4.3", "Grok 4.3", 1, 0, 2, 56.4),
        ("Grok Build 0.1", "Grok Build 0.1", 1, 0, 2, 42.6),
        ("DeepSeek V4 Flash", "DeepSeek V4 Flash", 1, 0, 2, 52.9),
        ("DeepSeek V4 thinking", "DeepSeek V4 thinking", 1, 0, 2, 52.9),
    ]
    return module.SnapshotMetrics(
        case_count=2,
        model_rows=[
            {
                "label": label,
                "readme_label": readme_label,
                "current_passed": current,
                "empty_passed": empty,
                "total": total,
                "quality_delta": quality_delta,
                "current_wins": 1,
                "baseline_wins": 0,
                "ties": 1,
                "inconclusive": 0,
                "current_score": 20.0 + quality_delta,
                "empty_score": 20.0,
                "judge_calls": 1,
                "hard_gate_shortcuts": 1,
            }
            for label, readme_label, current, empty, total, quality_delta in model_rows
        ],
        external_rows=[],
        reference_rows=[
            {
                "label": "OpenHands `AGENTS.md`",
                "candidate_label": "GPT-5.5-current",
                "current_passed": 2,
                "reference_passed": 1,
                "total": 2,
                "current_wins": 1,
                "reference_wins": 0,
                "ties": 1,
                "inconclusive": 0,
                "delta": 27.2,
                "current_score": 95.9,
                "reference_score": 68.8,
                "judge_calls": 1,
                "hard_gate_shortcuts": 1,
            },
            {
                "label": "OpenHands `AGENTS.md`",
                "candidate_label": "GLM-5.2-current",
                "current_passed": 2,
                "reference_passed": 1,
                "total": 2,
                "current_wins": 1,
                "reference_wins": 0,
                "ties": 1,
                "inconclusive": 0,
                "delta": 16.3,
                "current_score": 84.7,
                "reference_score": 68.4,
                "judge_calls": 1,
                "hard_gate_shortcuts": 1,
            },
            {
                "label": "Claude/Fable prompt",
                "candidate_label": "GPT-5.5-current",
                "current_passed": 2,
                "reference_passed": 1,
                "total": 2,
                "current_wins": 1,
                "reference_wins": 0,
                "ties": 1,
                "inconclusive": 0,
                "delta": 23.9,
                "current_score": 94.5,
                "reference_score": 70.5,
                "judge_calls": 1,
                "hard_gate_shortcuts": 1,
            },
            {
                "label": "Claude/Fable prompt",
                "candidate_label": "GLM-5.2-current",
                "current_passed": 2,
                "reference_passed": 1,
                "total": 2,
                "current_wins": 1,
                "reference_wins": 0,
                "ties": 1,
                "inconclusive": 0,
                "delta": 17.9,
                "current_score": 87.9,
                "reference_score": 70.0,
                "judge_calls": 1,
                "hard_gate_shortcuts": 1,
            },
        ],
    )


def readme_svg_references(module):
    return " ".join(f"docs/assets/readme/{name}" for name in module.REQUIRED_README_SVGS)


def png_chunk(kind, payload):
    return len(payload).to_bytes(4, "big") + kind + payload + zlib.crc32(kind + payload).to_bytes(4, "big")


def write_text_png(path, metadata):
    path.parent.mkdir(parents=True, exist_ok=True)
    ihdr = (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 2, 0, 0, 0])
    idat = zlib.compress(b"\x00\xff\xff\xff")
    chunks = [png_chunk(b"IHDR", ihdr)]
    for key, value in metadata.items():
        chunks.append(png_chunk(b"tEXt", key.encode("latin-1") + b"\0" + value.encode("latin-1")))
    chunks.append(png_chunk(b"IDAT", idat))
    chunks.append(png_chunk(b"IEND", b""))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"".join(chunks))


def write_social_png(root, module, metadata=None):
    write_text_png(root / module.DEFAULT_SOCIAL_IMAGE, metadata or module.EXPECTED_SOCIAL_PNG_METADATA)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_summary(path, label, passed, total=2):
    results = []
    for index in range(total):
        results.append(
            {
                "case_id": f"case-{index}",
                "label": label,
                "passed": index < passed,
                "failure_type": "none" if index < passed else "behavior",
            }
        )
    write_json(path, {"passed": passed, "failed": total - passed, "total": total, "results": results})


def write_quality_summary(path, candidate_label, candidate_passed, baseline_passed, average_delta):
    write_json(
        path,
        {
            "baseline_label": "empty",
            "label": "saved-model-quality",
            "pairs": [
                {
                    "candidate_label": candidate_label,
                    "aggregate": {
                        "average_baseline_score": 20.0,
                        "average_current_score": 20.0 + average_delta,
                        "average_delta": average_delta,
                        "baseline_passed": baseline_passed,
                        "candidate_passed": candidate_passed,
                        "confidence": {"high": 2},
                        "sources": {"llm_judge": 1, "hard_gate": 1},
                        "total": 2,
                        "winners": {"baseline": 0, "current": 1, "inconclusive": 0, "tie": 1},
                    },
                    "quality_json": str(path.parent / "quality.json"),
                }
            ],
        },
    )


def write_reference_quality_summary(path, baseline_label):
    write_json(
        path,
        {
            "baseline_label": baseline_label,
            "label": f"{baseline_label}-saved-model-quality",
            "pairs": [
                {
                    "candidate_label": "GPT-5.5-current",
                    "aggregate": {
                        "average_baseline_score": 70.0,
                        "average_current_score": 95.0,
                        "average_delta": 25.0,
                        "baseline_passed": 1,
                        "candidate_passed": 2,
                        "sources": {"llm_judge": 1, "hard_gate": 1},
                        "total": 2,
                        "winners": {"baseline": 0, "current": 1, "inconclusive": 0, "tie": 1},
                    },
                    "quality_json": str(path.parent / "pairs/GPT-5.5-current/quality.json"),
                },
                {
                    "candidate_label": "GLM-5.2-current",
                    "aggregate": {
                        "average_baseline_score": 68.0,
                        "average_current_score": 84.0,
                        "average_delta": 16.0,
                        "baseline_passed": 1,
                        "candidate_passed": 2,
                        "sources": {"llm_judge": 1, "hard_gate": 1},
                        "total": 2,
                        "winners": {"baseline": 0, "current": 1, "inconclusive": 0, "tie": 1},
                    },
                    "quality_json": str(path.parent / "pairs/GLM-5.2-current/quality.json"),
                },
            ],
        },
    )


def write_snapshot_artifacts(root, module):
    (root / "evals").mkdir(parents=True)
    (root / module.CASE_FILE).write_text(
        "\n".join(json.dumps({"id": f"case-{index}"}) for index in range(2)) + "\n",
        encoding="utf-8",
    )
    rows = {
        "GPT-5.5": (2, 1, 28.4),
        "GLM-5.2": (2, 1, 62.9),
        "Grok 4.3": (1, 0, 56.4),
        "Grok Build 0.1": (1, 0, 42.6),
        "DeepSeek V4 Flash": (1, 0, 52.9),
        "DeepSeek V4 thinking": (1, 0, 52.9),
    }
    for item in module.MODEL_ARTIFACTS:
        current_passed, empty_passed, quality_delta = rows[item["label"]]
        write_summary(root / item["current"], "current", current_passed)
        write_summary(root / item["empty"], "empty", empty_passed)
        write_quality_summary(root / item["quality"], item["label"], current_passed, empty_passed, quality_delta)
    write_json(
        root / module.GPT_EXTERNAL_QUALITY,
        {
            "baseline_label": "GPT-5.5",
            "label": "GPT-5.5-saved-model-quality",
            "pairs": [
                {
                    "candidate_label": "GLM-5.2",
                    "aggregate": {
                        "average_baseline_score": 90.0,
                        "average_current_score": 80.0,
                        "average_delta": -10.0,
                        "baseline_passed": 2,
                        "candidate_passed": 2,
                        "confidence": {"high": 2},
                        "sources": {"llm_judge": 2},
                        "total": 2,
                        "winners": {"baseline": 1, "current": 1, "inconclusive": 0, "tie": 0},
                    },
                    "quality_json": str(root / module.QUALITY_ROOT / "gpt-vs-external-current/pairs/glm/quality.json"),
                }
            ],
        },
    )
    for item in module.REFERENCE_QUALITY_SUMMARIES:
        write_reference_quality_summary(root / item["quality"], item["label"])


def write_blinded_sol_artifacts(root, module, *, current_passed=2, empty_passed=1):
    write_summary(root / module.BLINDED_SOL_CURRENT, "current", current_passed)
    write_summary(root / module.BLINDED_SOL_EMPTY, "empty", empty_passed)


def blinded_model_artifacts():
    labels = [
        "GPT-5.5",
        "GPT-5.6 Sol medium",
        "GLM-5.2",
        "Grok 4.3",
        "DeepSeek V4 Flash",
        "DeepSeek V4 Flash thinking",
    ]
    root = Path(".eval-results/blinded-six-row-test")
    quality_root = Path(".eval-results/blinded-50-case-v1/dual-order-quality-v2")
    return [
        {
            "model_id": model_id,
            "model_label": labels[index],
            "current": root / model_id / "current/summary.json",
            "empty": root / model_id / "empty/summary.json",
            "quality": quality_root / model_id / "dual-order-summary.json",
            "same_model_judge": model_id == "gpt-5.6-sol",
        }
        for index, model_id in enumerate(SIX_MODEL_IDS)
    ]


def dual_order_comparisons(total=50, baseline_passed=25, current_passed=35):
    winner_order = ["baseline", "current", "tie", "inconclusive", "order_sensitive"]
    comparisons = []
    for index in range(total):
        baseline_is_passed = index < baseline_passed
        current_is_passed = index < current_passed
        if baseline_is_passed and current_is_passed:
            source = "llm_judge"
            winner = winner_order[index % len(winner_order)]
            if winner == "baseline":
                baseline_first = current_first = ("baseline", 75, 50)
            elif winner == "current":
                baseline_first = current_first = ("current", 50, 75)
            elif winner == "tie":
                baseline_first = current_first = ("tie", 70, 70)
            elif winner == "inconclusive":
                baseline_first = current_first = ("inconclusive", 50, 50)
            else:
                baseline_first = ("current", 50, 75)
                current_first = ("baseline", 75, 50)
        else:
            source = "hard_gate"
            if baseline_is_passed:
                winner = "baseline"
                baseline_first = current_first = ("baseline", 100, 0)
            elif current_is_passed:
                winner = "current"
                baseline_first = current_first = ("current", 0, 100)
            else:
                winner = "inconclusive"
                baseline_first = current_first = ("inconclusive", 0, 0)

        orders = {}
        for orientation, (order_winner, baseline_score, current_score) in (
            ("baseline_first", baseline_first),
            ("current_first", current_first),
        ):
            orders[orientation] = {
                "winner": order_winner,
                "baseline_score": baseline_score,
                "current_score": current_score,
                "delta": current_score - baseline_score,
            }
        balanced_baseline = round(
            sum(order["baseline_score"] for order in orders.values()) / 2,
            2,
        )
        balanced_current = round(
            sum(order["current_score"] for order in orders.values()) / 2,
            2,
        )
        comparisons.append(
            {
                "case_id": f"case-{index}",
                "baseline_passed": baseline_is_passed,
                "current_passed": current_is_passed,
                "source": source,
                "orders": orders,
                "winner": winner,
                "balanced_scores": {
                    "baseline": balanced_baseline,
                    "current": balanced_current,
                    "delta": round(balanced_current - balanced_baseline, 2),
                },
            }
        )
    return comparisons


def dual_order_score_summary(comparisons, *, source=None):
    selected = [
        item for item in comparisons if source is None or item["source"] == source
    ]
    if not selected:
        return {"cases": 0, "baseline": None, "current": None, "delta": None}
    baseline_values = [
        order["baseline_score"] for item in selected for order in item["orders"].values()
    ]
    current_values = [
        order["current_score"] for item in selected for order in item["orders"].values()
    ]
    baseline = round(sum(baseline_values) / len(baseline_values), 2)
    current = round(sum(current_values) / len(current_values), 2)
    return {
        "cases": len(selected),
        "baseline": baseline,
        "current": current,
        "delta": round(current - baseline, 2),
    }


def dual_order_aggregate_fixture(comparisons):
    winners = {
        bucket: 0
        for bucket in ["baseline", "current", "tie", "inconclusive", "order_sensitive"]
    }
    sources = {"hard_gate": 0, "llm_judge": 0}
    for item in comparisons:
        winners[item["winner"]] += 1
        sources[item["source"]] += 1
    return {
        "total": len(comparisons),
        "baseline_passed": sum(item["baseline_passed"] for item in comparisons),
        "current_passed": sum(item["current_passed"] for item in comparisons),
        "sources": sources,
        "winners": winners,
        "scores": {
            "all_cases": dual_order_score_summary(comparisons),
            "llm_judge": dual_order_score_summary(comparisons, source="llm_judge"),
        },
    }


def dual_order_summary_fixture(spec, *, total=50, baseline_passed=25, current_passed=35):
    comparisons = dual_order_comparisons(total, baseline_passed, current_passed)
    return {
        "schema_version": 1,
        "aggregation": "dual_order_consensus",
        "model_id": spec["model_id"],
        "model_label": spec["model_label"],
        "baseline_label": "empty",
        "current_label": "current",
        "judge": {
            **EXPECTED_JUDGE_IDENTITY,
            "preset": EXPECTED_JUDGE_PRESET,
        },
        "aggregate": dual_order_aggregate_fixture(comparisons),
        "quality_json": "dual-order-quality.json",
    }


def dual_order_detail_fixture(root, spec, summary):
    comparisons = sorted(
        dual_order_comparisons(
            summary["aggregate"]["total"],
            summary["aggregate"]["baseline_passed"],
            summary["aggregate"]["current_passed"],
        ),
        key=lambda item: item["case_id"],
    )
    return {
        **{key: value for key, value in summary.items() if key not in {"aggregate", "quality_json"}},
        "inputs": {
            "source_summaries": {
                "baseline": {
                    "path": spec["empty"].as_posix(),
                    "sha256": sha256(root / spec["empty"]),
                },
                "current": {
                    "path": spec["current"].as_posix(),
                    "sha256": sha256(root / spec["current"]),
                },
            },
            "orders": write_raw_order_artifacts(root, spec, summary, comparisons),
        },
        "aggregate": summary["aggregate"],
        "comparisons": comparisons,
    }


def raw_order_aggregate(comparisons):
    winners = {"baseline": 0, "current": 0, "tie": 0, "inconclusive": 0}
    sources = {}
    confidence = {}
    baseline_scores = []
    current_scores = []
    for item in comparisons:
        quality = item["quality"]
        winners[quality["winner"]] += 1
        sources[quality["source"]] = sources.get(quality["source"], 0) + 1
        confidence[quality["confidence"]] = confidence.get(quality["confidence"], 0) + 1
        baseline_scores.append(quality["baseline_score"])
        current_scores.append(quality["current_score"])
    return {
        "total": len(comparisons),
        "baseline_passed": sum(item["baseline"]["passed"] for item in comparisons),
        "candidate_passed": sum(item["candidate"]["passed"] for item in comparisons),
        "winners": winners,
        "sources": sources,
        "confidence": confidence,
        "average_baseline_score": round(sum(baseline_scores) / len(comparisons), 1),
        "average_current_score": round(sum(current_scores) / len(comparisons), 1),
        "average_delta": round(
            sum(current_scores) / len(comparisons)
            - sum(baseline_scores) / len(comparisons),
            1,
        ),
    }


def raw_order_comparison(comparison, orientation):
    order = comparison["orders"][orientation]
    if orientation == "baseline_first":
        baseline_label, candidate_label = "empty", "current"
        baseline_passed = comparison["baseline_passed"]
        candidate_passed = comparison["current_passed"]
        winner = order["winner"]
        baseline_score = order["baseline_score"]
        current_score = order["current_score"]
    else:
        baseline_label, candidate_label = "current", "empty"
        baseline_passed = comparison["current_passed"]
        candidate_passed = comparison["baseline_passed"]
        winner = {"baseline": "current", "current": "baseline"}.get(
            order["winner"], order["winner"]
        )
        baseline_score = order["current_score"]
        current_score = order["baseline_score"]
    checks = []
    if comparison["source"] == "llm_judge":
        checks = [
            {
                "id": check_id,
                "baseline_score": baseline_score,
                "current_score": current_score,
                "winner": winner,
                "note": "fixture judgment",
            }
            for check_id in ORDER_CHECK_IDS
        ]
    return {
        "case_id": comparison["case_id"],
        "baseline": {"label": baseline_label, "passed": baseline_passed},
        "candidate": {"label": candidate_label, "passed": candidate_passed},
        "quality": {
            "source": comparison["source"],
            "winner": winner,
            "baseline_score": baseline_score,
            "current_score": current_score,
            "delta": current_score - baseline_score,
            "confidence": "low" if winner == "inconclusive" else "high",
            "review_needed": winner == "inconclusive",
            "reason": "fixture judgment",
            "checks": checks,
        },
    }


def write_raw_order_artifacts(root, spec, summary, comparisons):
    order_root = (root / spec["quality"]).parent / "orders"
    recorded = {}
    for orientation in ("baseline_first", "current_first"):
        raw_comparisons = [
            raw_order_comparison(comparison, orientation) for comparison in comparisons
        ]
        baseline_label = "empty" if orientation == "baseline_first" else "current"
        candidate_label = "current" if orientation == "baseline_first" else "empty"
        quality = {
            "baseline_label": baseline_label,
            "candidate_label": candidate_label,
            "judge": summary["judge"],
            "aggregate": raw_order_aggregate(raw_comparisons),
            "comparisons": raw_comparisons,
        }
        summary_path = order_root / f"{orientation.replace('_', '-')}-summary.json"
        quality_path = order_root / "pairs" / candidate_label / "quality.json"
        write_json(quality_path, quality)
        write_json(
            summary_path,
            {
                "baseline_label": baseline_label,
                "judge": summary["judge"],
                "pairs": [
                    {
                        "candidate_label": candidate_label,
                        "judge": summary["judge"],
                        "aggregate": quality["aggregate"],
                        "quality_json": quality_path.relative_to(order_root).as_posix(),
                    }
                ],
            },
        )
        recorded[orientation] = {
            "summary_path": summary_path.relative_to(root).as_posix(),
            "summary_sha256": sha256(summary_path),
            "quality_path": quality_path.relative_to(root).as_posix(),
            "quality_sha256": sha256(quality_path),
        }
    return recorded


def write_blinded_publication_artifacts(root, specs, *, total=50):
    baseline_passed = total // 2
    current_passed = baseline_passed + total // 5
    case_file = root / "evals/cases.jsonl"
    case_file.parent.mkdir(parents=True, exist_ok=True)
    case_file.write_text(
        "\n".join(json.dumps({"id": f"case-{index}"}) for index in range(total)) + "\n",
        encoding="utf-8",
    )
    for spec in specs:
        write_summary(root / spec["current"], "current", current_passed, total)
        write_summary(root / spec["empty"], "empty", baseline_passed, total)
        summary = dual_order_summary_fixture(
            spec,
            total=total,
            baseline_passed=baseline_passed,
            current_passed=current_passed,
        )
        write_json(root / spec["quality"], summary)
        write_json(
            (root / spec["quality"]).with_name(summary["quality_json"]),
            dual_order_detail_fixture(root, spec, summary),
        )


def write_matching_docs(root, module, snapshot):
    sections = module.expected_doc_sections(snapshot)
    snippets = module.expected_doc_snippets(snapshot)
    for relative_path, expected_sections in sections.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        suffix = f" {readme_svg_references(module)}" if relative_path == "README.md" else ""
        content = "\n\n".join(
            heading + "\n\n" + "\n".join(required)
            for heading, required in expected_sections
        )
        extras = [snippet for snippet in snippets[relative_path] if module.normalize_text(snippet) not in module.normalize_text(content)]
        if extras:
            content += "\n\n## Other Published Context\n\n" + "\n".join(extras)
        path.write_text(content + suffix + "\n", encoding="utf-8")


def blinded_hard_gate_doc_row(row):
    return (
        f"| {row['model_label']} | {row['current_passed']} / {row['total']} | "
        f"{row['empty_passed']} / {row['total']} | {row['current_passed'] - row['empty_passed']:+d} |"
    )


def blinded_dual_order_doc_row(row):
    winners = row["dual_order_winners"]
    return (
        f"| {row['model_label']} | {winners['current']} | {winners['baseline']} | "
        f"{winners['tie']} | {winners['order_sensitive']} | {winners['inconclusive']} |"
    )


def six_model_doc_sections(module, metrics):
    hard_gate_rows = [blinded_hard_gate_doc_row(row) for row in metrics.model_rows]
    dual_order_rows = [blinded_dual_order_doc_row(row) for row in metrics.model_rows]
    caveats = [
        FIXED_JUDGE_CAVEAT,
        SAME_MODEL_JUDGE_CAVEAT,
        WITHIN_RUNNER_CAVEAT,
        NO_REFERENCE_CAVEAT,
        GROK_BUILD_EXCLUSION_CAVEAT,
    ]
    artifact_root = f"`{module.BLINDED_QUALITY_ROOT}/`"
    return {
        "README.md": [
            (EXPECTED_BLINDED_DOC_HEADINGS["README.md"], [*hard_gate_rows, *dual_order_rows, *caveats, artifact_root]),
        ],
        "evals/README.md": [
            (EXPECTED_BLINDED_DOC_HEADINGS["evals/README.md"], [*caveats, artifact_root]),
        ],
        "evals/RESULTS.md": [
            (
                EXPECTED_BLINDED_DOC_HEADINGS["evals/RESULTS.md"],
                [*hard_gate_rows, *dual_order_rows, *caveats, artifact_root],
            ),
        ],
        "evals/PROMPT_QUALITY_CASES.md": [
            (
                EXPECTED_BLINDED_DOC_HEADINGS["evals/PROMPT_QUALITY_CASES.md"],
                [*caveats, "order-sensitive", artifact_root],
            ),
        ],
        "evals/CHANGELOG.md": [
            (
                EXPECTED_BLINDED_DOC_HEADINGS["evals/CHANGELOG.md"],
                [*hard_gate_rows, *dual_order_rows, *caveats, artifact_root],
            ),
        ],
    }


def write_matching_blinded_docs(root, module, metrics):
    for relative_path, expected_sections in six_model_doc_sections(module, metrics).items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n\n".join(
            heading + "\n\n" + "\n".join(required)
            for heading, required in expected_sections
        )
        with path.open("a", encoding="utf-8") as stream:
            stream.write("\n\n" + content + "\n")


class CheckPublishedEvalMetricsTests(unittest.TestCase):
    def require_blinded_snapshot_loader(self, module):
        self.assertTrue(
            hasattr(module, "load_blinded_snapshot_metrics"),
            "publication guard must load all six blinded primary and dual-order rows",
        )
        return module.load_blinded_snapshot_metrics

    def test_blinded_snapshot_guard_rejects_execution_failures(self):
        module = load_script()
        specs = blinded_model_artifacts()
        loader = self.require_blinded_snapshot_loader(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_publication_artifacts(root, specs)
            current_path = root / specs[0]["current"]
            current = json.loads(current_path.read_text(encoding="utf-8"))
            current["results"][0]["passed"] = False
            current["results"][0]["failure_type"] = "agent"
            current["passed"] -= 1
            current["failed"] += 1
            write_json(current_path, current)

            with (
                mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                self.assertRaisesRegex(ValueError, r"execution failures|agent=1"),
            ):
                loader(root)

    def test_blinded_snapshot_guard_accepts_canonical_50_case_details(self):
        module = load_script()
        specs = blinded_model_artifacts()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_publication_artifacts(root, specs)
            with mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True):
                metrics = module.load_blinded_snapshot_metrics(root)

        self.assertEqual(metrics.case_count, 50)
        self.assertEqual(len(metrics.model_rows), 6)

    def test_blinded_snapshot_guard_rejects_non_50_case_catalog(self):
        module = load_script()
        specs = blinded_model_artifacts()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_publication_artifacts(root, specs, total=49)
            with (
                mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                self.assertRaisesRegex(ValueError, r"exactly 50|50 cases"),
            ):
                module.load_blinded_snapshot_metrics(root)

    def test_blinded_model_manifest_has_exact_six_rows_v2_quality_root_and_no_grok_build(self):
        module = load_script()
        self.assertEqual(
            [row["model_id"] for row in module.BLINDED_MODEL_ARTIFACTS],
            SIX_MODEL_IDS,
        )
        self.assertEqual(
            module.BLINDED_QUALITY_ROOT,
            Path(".eval-results/blinded-50-case-v1/dual-order-quality-v2"),
        )
        manifest_text = "\n".join(
            str(value)
            for row in module.BLINDED_MODEL_ARTIFACTS
            for value in row.values()
        )
        self.assertNotIn("grok-build-0.1", manifest_text)
        self.assertNotIn("blinded-all-models-50-case-v2", manifest_text)
        self.assertNotIn("blinded-all-models-50-case-v3", manifest_text)

    def test_blinded_publication_contract_uses_exact_headings_and_exclusion_caveat(self):
        module = load_script()

        self.assertEqual(module.BLINDED_DOC_HEADINGS, EXPECTED_BLINDED_DOC_HEADINGS)

    def test_absolute_publication_contract_uses_exact_headings_and_scopes(self):
        module = load_script()

        self.assertEqual(module.ABSOLUTE_DOC_HEADINGS, EXPECTED_ABSOLUTE_DOC_HEADINGS)
        self.assertEqual(module.ABSOLUTE_QUALITY_SCOPE, ABSOLUTE_QUALITY_SCOPE)
        self.assertEqual(module.ABSOLUTE_JUDGE_AUDIT_SCOPE, ABSOLUTE_JUDGE_AUDIT_SCOPE)
        self.assertEqual(module.ABSOLUTE_QUALITY_ROOT, Path(".eval-results/blinded-model-absolute-v1/canonical"))
        self.assertEqual(module.GROK_BUILD_EXCLUSION_CAVEAT, GROK_BUILD_EXCLUSION_CAVEAT)
        self.assertEqual(module.EXPECTED_SOCIAL_PNG_METADATA["instruction_snapshot_models"], "6")

    def test_blinded_snapshot_guard_requires_exact_sibling_quality_detail(self):
        module = load_script()
        specs = blinded_model_artifacts()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_publication_artifacts(root, specs)
            summary_path = root / specs[0]["quality"]
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["quality_json"] = "nested/dual-order-quality.json"
            write_json(summary_path, summary)

            with (
                mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                self.assertRaisesRegex(ValueError, r"quality_json.*sibling|sibling.*quality_json"),
            ):
                module.load_blinded_snapshot_metrics(root)

    def test_blinded_snapshot_guard_rejects_detail_metadata_or_aggregate_drift(self):
        module = load_script()
        specs = blinded_model_artifacts()

        for field in ("model_id", "aggregate"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_blinded_publication_artifacts(root, specs)
                detail_path = (root / specs[1]["quality"]).with_name("dual-order-quality.json")
                detail = json.loads(detail_path.read_text(encoding="utf-8"))
                if field == "model_id":
                    detail[field] = "wrong-model"
                else:
                    detail[field]["total"] = 49
                write_json(detail_path, detail)

                with (
                    mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                    self.assertRaisesRegex(ValueError, r"detail.*(?:metadata|aggregate)|(?:metadata|aggregate).*detail"),
                ):
                    module.load_blinded_snapshot_metrics(root)

    def test_blinded_snapshot_guard_rejects_duplicate_or_missing_detail_case_ids(self):
        module = load_script()
        specs = blinded_model_artifacts()

        for mutation in ("duplicate", "missing"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_blinded_publication_artifacts(root, specs)
                detail_path = (root / specs[2]["quality"]).with_name("dual-order-quality.json")
                detail = json.loads(detail_path.read_text(encoding="utf-8"))
                if mutation == "duplicate":
                    detail["comparisons"][-1]["case_id"] = detail["comparisons"][0]["case_id"]
                else:
                    detail["comparisons"].pop()
                write_json(detail_path, detail)

                with (
                    mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                    self.assertRaisesRegex(ValueError, r"detail.*case(?:_id| set| count)|(?:duplicate|missing).*case"),
                ):
                    module.load_blinded_snapshot_metrics(root)

    def test_blinded_snapshot_guard_rejects_detail_primary_pass_state_drift(self):
        module = load_script()
        specs = blinded_model_artifacts()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_publication_artifacts(root, specs)
            detail_path = (root / specs[3]["quality"]).with_name("dual-order-quality.json")
            detail = json.loads(detail_path.read_text(encoding="utf-8"))
            detail["comparisons"][0]["current_passed"] = False
            write_json(detail_path, detail)

            with (
                mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                self.assertRaisesRegex(ValueError, r"pass state|primary.*pass"),
            ):
                module.load_blinded_snapshot_metrics(root)

    def test_blinded_snapshot_guard_recomputes_detail_sources_and_winners(self):
        module = load_script()
        specs = blinded_model_artifacts()

        for field, replacement in (("source", "hard_gate"), ("winner", "current")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_blinded_publication_artifacts(root, specs)
                detail_path = (root / specs[4]["quality"]).with_name("dual-order-quality.json")
                detail = json.loads(detail_path.read_text(encoding="utf-8"))
                detail["comparisons"][0][field] = replacement
                write_json(detail_path, detail)

                with (
                    mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                    self.assertRaisesRegex(ValueError, rf"detail.*{field}|{field}.*(?:count|aggregate)"),
                ):
                    module.load_blinded_snapshot_metrics(root)

    def test_blinded_snapshot_guard_derives_source_and_hard_gate_result_from_primary_states(self):
        module = load_script()
        specs = blinded_model_artifacts()

        for mutation in ("source", "hard_gate_result"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_blinded_publication_artifacts(root, specs)
                summary_path = root / specs[4]["quality"]
                detail_path = summary_path.with_name("dual-order-quality.json")
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                detail = json.loads(detail_path.read_text(encoding="utf-8"))

                if mutation == "source":
                    target = detail["comparisons"][0]
                    self.assertTrue(target["baseline_passed"] and target["current_passed"])
                    target["source"] = "hard_gate"
                else:
                    target = next(
                        item
                        for item in detail["comparisons"]
                        if item["source"] == "hard_gate"
                        and not item["baseline_passed"]
                        and item["current_passed"]
                    )
                    target["orders"] = {
                        orientation: {
                            "winner": "tie",
                            "baseline_score": 50,
                            "current_score": 50,
                            "delta": 0,
                        }
                        for orientation in ("baseline_first", "current_first")
                    }
                    target["winner"] = "tie"
                    target["balanced_scores"] = {
                        "baseline": 50.0,
                        "current": 50.0,
                        "delta": 0.0,
                    }

                detail["aggregate"] = dual_order_aggregate_fixture(detail["comparisons"])
                summary["aggregate"] = detail["aggregate"]
                write_json(detail_path, detail)
                write_json(summary_path, summary)

                with (
                    mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                    self.assertRaisesRegex(
                        ValueError,
                        r"source.*pass|pass.*source|hard.?gate.*pass states|pass states.*hard.?gate",
                    ),
                ):
                    module.load_blinded_snapshot_metrics(root)

    def test_blinded_snapshot_guard_binds_detail_inputs_to_primary_paths_and_hashes(self):
        module = load_script()
        specs = blinded_model_artifacts()

        for field in ("path", "sha256"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_blinded_publication_artifacts(root, specs)
                detail_path = (root / specs[5]["quality"]).with_name("dual-order-quality.json")
                detail = json.loads(detail_path.read_text(encoding="utf-8"))
                detail["inputs"]["source_summaries"]["current"][field] = "wrong"
                write_json(detail_path, detail)

                with (
                    mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                    self.assertRaisesRegex(ValueError, rf"source.*{field}|{field}.*primary"),
                ):
                    module.load_blinded_snapshot_metrics(root)

    def test_blinded_snapshot_guard_binds_canonical_detail_to_recorded_raw_orders(self):
        module = load_script()
        specs = blinded_model_artifacts()

        for scenario in (
            "missing_orientation",
            "extra_orientation",
            "path_drift",
            "hash_drift",
            "swapped_orientation",
            "raw_comparison_drift",
        ):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_blinded_publication_artifacts(root, specs)
                detail_path = (root / specs[0]["quality"]).with_name(
                    "dual-order-quality.json"
                )
                detail = json.loads(detail_path.read_text(encoding="utf-8"))
                orders = detail["inputs"]["orders"]
                if scenario == "missing_orientation":
                    del orders["current_first"]
                elif scenario == "extra_orientation":
                    orders["unexpected"] = dict(orders["baseline_first"])
                elif scenario == "path_drift":
                    orders["baseline_first"]["quality_path"] = orders["current_first"][
                        "quality_path"
                    ]
                    orders["baseline_first"]["quality_sha256"] = orders["current_first"][
                        "quality_sha256"
                    ]
                elif scenario == "hash_drift":
                    orders["baseline_first"]["summary_sha256"] = "0" * 64
                elif scenario == "swapped_orientation":
                    orders["baseline_first"], orders["current_first"] = (
                        orders["current_first"],
                        orders["baseline_first"],
                    )
                else:
                    for orientation in ("baseline_first", "current_first"):
                        raw_input = orders[orientation]
                        quality_path = root / raw_input["quality_path"]
                        summary_path = root / raw_input["summary_path"]
                        quality = json.loads(quality_path.read_text(encoding="utf-8"))
                        raw_quality = quality["comparisons"][0]["quality"]
                        score_field = (
                            "baseline_score"
                            if orientation == "baseline_first"
                            else "current_score"
                        )
                        raw_quality[score_field] -= 1
                        raw_quality["delta"] = (
                            raw_quality["current_score"] - raw_quality["baseline_score"]
                        )
                        for check in raw_quality["checks"]:
                            check[score_field] = raw_quality[score_field]
                        quality["aggregate"] = raw_order_aggregate(quality["comparisons"])
                        write_json(quality_path, quality)
                        wrapper = json.loads(summary_path.read_text(encoding="utf-8"))
                        wrapper["pairs"][0]["aggregate"] = quality["aggregate"]
                        write_json(summary_path, wrapper)
                        raw_input["quality_sha256"] = sha256(quality_path)
                        raw_input["summary_sha256"] = sha256(summary_path)
                write_json(detail_path, detail)

                with (
                    mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                    self.assertRaisesRegex(
                        ValueError,
                        r"raw order|orientation|summary_sha256|quality_path|comparison",
                    ),
                ):
                    module.load_blinded_snapshot_metrics(root)

    def test_blinded_snapshot_guard_rejects_out_of_domain_detail_order_scores(self):
        module = load_script()
        specs = blinded_model_artifacts()

        for scenario in (
            "negative_score",
            "high_score",
            "fractional_score",
            "fractional_delta",
            "mismatched_delta",
        ):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_blinded_publication_artifacts(root, specs)
                summary_path = root / specs[0]["quality"]
                detail_path = summary_path.with_name("dual-order-quality.json")
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                detail = json.loads(detail_path.read_text(encoding="utf-8"))
                comparison = detail["comparisons"][0]
                order = comparison["orders"]["baseline_first"]
                if scenario == "negative_score":
                    order["baseline_score"] = -1
                    order["delta"] = order["current_score"] - order["baseline_score"]
                elif scenario == "high_score":
                    order["current_score"] = 101
                    order["delta"] = order["current_score"] - order["baseline_score"]
                elif scenario == "fractional_score":
                    order["baseline_score"] = 1.5
                    order["delta"] = order["current_score"] - order["baseline_score"]
                elif scenario == "fractional_delta":
                    order["delta"] = (
                        order["current_score"] - order["baseline_score"] + 0.5
                    )
                else:
                    order["delta"] = (
                        order["current_score"] - order["baseline_score"] + 1
                    )
                comparison["balanced_scores"] = {
                    "baseline": round(
                        sum(
                            item["baseline_score"]
                            for item in comparison["orders"].values()
                        )
                        / 2,
                        2,
                    ),
                    "current": round(
                        sum(
                            item["current_score"]
                            for item in comparison["orders"].values()
                        )
                        / 2,
                        2,
                    ),
                }
                comparison["balanced_scores"]["delta"] = round(
                    comparison["balanced_scores"]["current"]
                    - comparison["balanced_scores"]["baseline"],
                    2,
                )
                detail["aggregate"] = dual_order_aggregate_fixture(detail["comparisons"])
                summary["aggregate"] = detail["aggregate"]
                write_json(detail_path, detail)
                write_json(summary_path, summary)

                with (
                    mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                    self.assertRaisesRegex(
                        ValueError,
                        r"detail order.*(?:integer|0 to 100|derived)",
                    ),
                ):
                    module.load_blinded_snapshot_metrics(root)

    def test_blinded_snapshot_guard_rejects_wrong_judge_identity(self):
        module = load_script()
        specs = blinded_model_artifacts()
        loader = self.require_blinded_snapshot_loader(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_publication_artifacts(root, specs)
            quality_path = root / specs[2]["quality"]
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
            quality["judge"]["model"] = "gpt-5.6-terra"
            write_json(quality_path, quality)

            with (
                mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                self.assertRaisesRegex(ValueError, r"judge identity"),
            ):
                loader(root)

    def test_blinded_snapshot_guard_requires_exact_judge_preset_in_summary_and_detail(self):
        module = load_script()
        specs = blinded_model_artifacts()
        loader = self.require_blinded_snapshot_loader(module)

        for target in ("summary", "detail", "summary_and_detail"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_blinded_publication_artifacts(root, specs)
                summary_path = root / specs[2]["quality"]
                detail_path = summary_path.with_name("dual-order-quality.json")
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                detail = json.loads(detail_path.read_text(encoding="utf-8"))
                if target in {"summary", "summary_and_detail"}:
                    summary["judge"]["preset"] = "gpt-5.6-sol-low"
                    write_json(summary_path, summary)
                if target in {"detail", "summary_and_detail"}:
                    detail["judge"]["preset"] = "gpt-5.6-sol-low"
                    write_json(detail_path, detail)

                with (
                    mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                    self.assertRaisesRegex(
                        ValueError,
                        r"judge preset.*gpt-5\.6-sol-medium",
                    ),
                ):
                    loader(root)

    def test_blinded_snapshot_guard_requires_order_sensitive_bucket(self):
        module = load_script()
        specs = blinded_model_artifacts()
        loader = self.require_blinded_snapshot_loader(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_publication_artifacts(root, specs)
            quality_path = root / specs[3]["quality"]
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
            del quality["aggregate"]["winners"]["order_sensitive"]
            write_json(quality_path, quality)

            with (
                mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                self.assertRaisesRegex(ValueError, r"order_sensitive"),
            ):
                loader(root)

    def test_blinded_snapshot_guard_rejects_winner_bucket_sum_mismatch(self):
        module = load_script()
        specs = blinded_model_artifacts()
        loader = self.require_blinded_snapshot_loader(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_publication_artifacts(root, specs)
            quality_path = root / specs[4]["quality"]
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
            quality["aggregate"]["winners"]["current"] += 1
            write_json(quality_path, quality)

            with (
                mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                self.assertRaisesRegex(ValueError, r"winner.*(?:sum|total)|(?:sum|total).*winner"),
            ):
                loader(root)

    def test_check_svg_scope_rejects_unexpected_legacy_svg(self):
        module = load_script()

        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp)
            for name in [*EXPECTED_BLINDED_SVGS, "model-gap.svg"]:
                (svg_dir / name).write_text(
                    f"<svg><text>{module.EXPECTED_SVG_SCOPE}</text></svg>\n",
                    encoding="utf-8",
                )

            problems = module.check_svg_scope(svg_dir, EXPECTED_BLINDED_SVGS)

        self.assertTrue(
            any("model-gap.svg" in problem and "unexpected" in problem for problem in problems),
            problems,
        )

    def test_default_docs_include_five_publication_surfaces(self):
        module = load_script()

        self.assertEqual(
            module.DEFAULT_DOCS,
            [
                Path("README.md"),
                Path("evals/README.md"),
                Path("evals/RESULTS.md"),
                Path("evals/PROMPT_QUALITY_CASES.md"),
                Path("evals/CHANGELOG.md"),
            ],
        )

    def test_doc_expectation_key_prefers_exact_nested_path(self):
        module = load_script()
        snippets = {"README.md": [], "evals/README.md": []}

        self.assertEqual(module.doc_expectation_key(Path("evals/README.md"), snippets), "evals/README.md")

    def test_expected_doc_snippets_anchor_legacy_caveat_to_snapshot_sections(self):
        module = load_script()
        snippets = module.expected_doc_snippets(snapshot_fixture(module))
        headings = {
            "README.md": "## Historical Evidence",
            "evals/README.md": "# Instruction Evals",
            "evals/RESULTS.md": "## 50-Case Refresh Snapshot",
            "evals/PROMPT_QUALITY_CASES.md": "## Snapshot Sources",
            "evals/CHANGELOG.md": "## 2026-07-08 - Agent Data Injection Eval Coverage and 50-Case Refresh",
        }

        self.assertEqual(set(snippets), set(headings))
        for path, heading in headings.items():
            with self.subTest(path=path):
                expected = module.normalize_text(f"{heading}\n\n{LEGACY_CAVEAT}")
                self.assertTrue(
                    any(expected in module.normalize_text(snippet) for snippet in snippets[path]),
                    f"{path} does not anchor the legacy caveat to {heading!r}",
                )

    def test_readme_uses_one_historical_evidence_heading_and_no_current_evidence_heading(self):
        module = load_script()
        snapshot = snapshot_fixture(module)
        sections = module.expected_doc_sections(snapshot)["README.md"]
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertEqual([heading for heading, _snippets in sections], ["## Historical Evidence"])
        self.assertEqual(readme.count("## Historical Evidence"), 1)
        self.assertNotIn("## Current Evidence", readme)

    def test_summarize_artifacts_computes_metric_snapshot(self):
        module = load_script()

        metrics = module.summarize_artifacts(
            summary_fixture(),
            quality_fixture(),
            summary_path=Path("summary.json"),
            quality_path=Path("quality.json"),
        )

        self.assertEqual(metrics.summary_passed, 4)
        self.assertEqual(metrics.summary_total, 4)
        self.assertEqual(metrics.case_count, 2)
        self.assertEqual(metrics.baseline_passed, 2)
        self.assertEqual(metrics.current_passed, 2)
        self.assertEqual(metrics.current_wins, 1)
        self.assertEqual(metrics.baseline_wins, 1)
        self.assertEqual(metrics.average_delta_text, "+1.00")

    def test_summarize_artifacts_rejects_missing_summary_side(self):
        module = load_script()
        summary = summary_fixture()
        summary["results"] = summary["results"][:-1]
        summary["passed"] = 3

        with self.assertRaisesRegex(ValueError, "missing summary label"):
            module.summarize_artifacts(
                summary,
                quality_fixture(),
                summary_path=Path("summary.json"),
                quality_path=Path("quality.json"),
            )

    def test_summarize_artifacts_rejects_duplicate_summary_label(self):
        module = load_script()
        summary = summary_fixture()
        summary["results"][-1]["case_id"] = "case-a"

        with self.assertRaisesRegex(ValueError, "duplicate summary label"):
            module.summarize_artifacts(
                summary,
                quality_fixture(),
                summary_path=Path("summary.json"),
                quality_path=Path("quality.json"),
            )

    def test_summarize_artifacts_rejects_summary_quality_case_mismatch(self):
        module = load_script()
        quality = quality_fixture()
        quality["comparisons"][-1]["case_id"] = "case-c"

        with self.assertRaisesRegex(ValueError, "case_id mismatch"):
            module.summarize_artifacts(
                summary_fixture(),
                quality,
                summary_path=Path("summary.json"),
                quality_path=Path("quality.json"),
            )

    def test_summarize_artifacts_rejects_duplicate_quality_case_id(self):
        module = load_script()
        quality = quality_fixture()
        quality["comparisons"][-1]["case_id"] = "case-a"

        with self.assertRaisesRegex(ValueError, "duplicate comparison case_id"):
            module.summarize_artifacts(
                summary_fixture(),
                quality,
                summary_path=Path("summary.json"),
                quality_path=Path("quality.json"),
            )

    def test_load_blinded_sol_metrics_validates_separate_primary_pair(self):
        module = load_script()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_sol_artifacts(root, module)
            metrics = module.load_blinded_sol_metrics(root)

        self.assertEqual(metrics.model_label, "GPT-5.6 Sol medium")
        self.assertEqual(metrics.current_passed, 2)
        self.assertEqual(metrics.empty_passed, 1)
        self.assertEqual(metrics.total, 2)
        self.assertEqual(metrics.agent_failures, 0)

    def test_load_blinded_sol_metrics_rejects_case_mismatch(self):
        module = load_script()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_sol_artifacts(root, module)
            empty_path = root / module.BLINDED_SOL_EMPTY
            empty = json.loads(empty_path.read_text(encoding="utf-8"))
            empty["results"][-1]["case_id"] = "empty-only"
            write_json(empty_path, empty)

            with self.assertRaisesRegex(ValueError, "current/empty case_id mismatch"):
                module.load_blinded_sol_metrics(root)

    def test_load_blinded_sol_metrics_rejects_agent_failure(self):
        module = load_script()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_sol_artifacts(root, module)
            current_path = root / module.BLINDED_SOL_CURRENT
            current = json.loads(current_path.read_text(encoding="utf-8"))
            current["results"][-1]["passed"] = False
            current["results"][-1]["failure_type"] = "agent"
            current["passed"] = 1
            current["failed"] = 1
            write_json(current_path, current)

            with self.assertRaisesRegex(ValueError, "agent=1 transport=0"):
                module.load_blinded_sol_metrics(root)

    def test_load_blinded_sol_metrics_rejects_unclassified_failure(self):
        module = load_script()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_sol_artifacts(root, module)
            current_path = root / module.BLINDED_SOL_CURRENT
            current = json.loads(current_path.read_text(encoding="utf-8"))
            current["results"][-1]["passed"] = False
            current["results"][-1]["failure_type"] = "harness"
            current["passed"] = 1
            current["failed"] = 1
            write_json(current_path, current)

            with self.assertRaisesRegex(ValueError, "unexpected failure_type 'harness'"):
                module.load_blinded_sol_metrics(root)

    def test_check_blinded_docs_accepts_six_model_sections(self):
        module = load_script()
        specs = blinded_model_artifacts()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_publication_artifacts(root, specs)
            with mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True):
                metrics = module.load_blinded_snapshot_metrics(root)
            write_matching_blinded_docs(root, module, metrics)
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_blinded_docs(metrics, module.DEFAULT_DOCS)
            finally:
                os.chdir(cwd)

        self.assertEqual(problems, [])

    def test_check_blinded_docs_rejects_retained_seven_model_section(self):
        module = load_script()
        specs = blinded_model_artifacts()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_publication_artifacts(root, specs)
            with mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True):
                metrics = module.load_blinded_snapshot_metrics(root)
            write_matching_blinded_docs(root, module, metrics)
            path = root / "README.md"
            with path.open("a", encoding="utf-8") as stream:
                stream.write("\n## Blinded Seven-Model Evidence\n\nRetained stale section.\n")

            problems = module.check_blinded_docs(metrics, [path])

        self.assertTrue(
            any("retained Blinded Seven-Model section" in problem for problem in problems),
            problems,
        )

    def test_check_blinded_docs_rejects_numeric_grok_build_row_in_six_model_section(self):
        module = load_script()
        specs = blinded_model_artifacts()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_blinded_publication_artifacts(root, specs)
            with mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True):
                metrics = module.load_blinded_snapshot_metrics(root)
            write_matching_blinded_docs(root, module, metrics)
            path = root / "README.md"
            with path.open("a", encoding="utf-8") as stream:
                stream.write("\n| Grok Build 0.1 | 31 / 50 | 21 / 50 | +10 |\n")

            problems = module.check_blinded_docs(metrics, [path])

        self.assertTrue(
            any("numeric Grok Build Markdown table row" in problem for problem in problems),
            problems,
        )

    def test_check_docs_accepts_matching_50_case_text(self):
        module = load_script()
        snapshot = snapshot_fixture(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evals").mkdir()
            write_matching_docs(root, module, snapshot)
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(snapshot, module.DEFAULT_DOCS)
            finally:
                os.chdir(cwd)

        self.assertEqual(problems, [])

    def test_check_docs_rejects_detached_legacy_pre_blinding_caveat(self):
        module = load_script()
        snapshot = snapshot_fixture(module)
        snippets = module.expected_doc_snippets(snapshot)["evals/RESULTS.md"]
        detached = [snippet for snippet in snippets if LEGACY_CAVEAT not in snippet]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evals" / "RESULTS.md"
            path.parent.mkdir()
            path.write_text("\n".join(detached) + f"\n\n{LEGACY_CAVEAT}\n", encoding="utf-8")
            problems = module.check_docs(snapshot, [path])

        self.assertTrue(any("missing published 50-case metric/caveat snippet" in problem for problem in problems))

    def test_check_docs_rejects_legacy_metrics_detached_from_caveated_section(self):
        module = load_script()
        snapshot = snapshot_fixture(module)
        snippets = module.expected_doc_snippets(snapshot)["evals/RESULTS.md"]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evals" / "RESULTS.md"
            path.parent.mkdir()
            path.write_text(
                snippets[0]
                + "\n\n"
                + snippets[0]
                + "\n\n## Detached Legacy Metrics\n\n"
                + "\n".join(snippets[2:])
                + "\n",
                encoding="utf-8",
            )
            problems = module.check_docs(snapshot, [path])

        self.assertTrue(any("outside its caveated section" in problem for problem in problems))

    def test_check_docs_rejects_duplicate_caveated_target_heading(self):
        module = load_script()
        snapshot = snapshot_fixture(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_matching_docs(root, module, snapshot)
            path = root / "evals" / "RESULTS.md"
            path.write_text(
                path.read_text(encoding="utf-8")
                + f"\n## 50-Case Refresh Snapshot\n\n{LEGACY_CAVEAT}\n",
                encoding="utf-8",
            )
            problems = module.check_docs(snapshot, [path])

        self.assertTrue(any("expected one legacy publication section" in problem for problem in problems))

    def test_check_docs_rejects_detached_current_vs_empty_quality_row(self):
        module = load_script()
        snapshot = snapshot_fixture(module)
        gpt = module.model_row(snapshot, "GPT-5.5")
        quality_row = (
            f"| GPT-5.5 | {gpt['current_wins']} | {gpt['baseline_wins']} | {gpt['ties']} | "
            f"{gpt['inconclusive']} | {gpt['current_score']:.1f} | {gpt['empty_score']:.1f} | "
            f"{gpt['quality_delta']:+.1f} | {gpt['judge_calls']} | {gpt['hard_gate_shortcuts']} |"
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_matching_docs(root, module, snapshot)
            path = root / "evals" / "RESULTS.md"
            path.write_text(
                path.read_text(encoding="utf-8")
                + f"\n## Detached Legacy Metrics\n\n{quality_row}\n",
                encoding="utf-8",
            )
            problems = module.check_docs(snapshot, [path])

        self.assertTrue(any("outside its caveated section" in problem for problem in problems))

    def test_check_docs_rejects_prelabel_changelog_row_outside_caveated_ledger(self):
        module = load_script()
        snapshot = snapshot_fixture(module)
        gpt = module.model_row(snapshot, "GPT-5.5")
        glm = module.model_row(snapshot, "GLM-5.2")
        old_row = (
            "| 2026-07-08 50-case snapshot | 50 current-vs-empty cases, all tested runners | "
            f"`{module.QUALITY_ROOT}/` | GPT {gpt['current_passed']} / {gpt['total']}, "
            f"GLM {glm['current_passed']} / {glm['total']} | current-vs-empty saved quality positive "
            "for all six runners; all-model reference rows included | mixed | empty baselines and "
            "OpenHands/Fable references |"
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_matching_docs(root, module, snapshot)
            path = root / "evals" / "CHANGELOG.md"
            path.write_text(
                path.read_text(encoding="utf-8")
                + f"\n## Detached Legacy Metrics\n\n{old_row}\n",
                encoding="utf-8",
            )
            problems = module.check_docs(snapshot, [path])

        self.assertTrue(any("outside its caveated section" in problem for problem in problems))

    def test_check_docs_reports_stale_quality_pending_text(self):
        module = load_script()
        snapshot = snapshot_fixture(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evals").mkdir()
            write_matching_docs(root, module, snapshot)
            readme = root / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + " 50-case saved quality evidence is still pending.", encoding="utf-8")
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(snapshot, [Path("README.md")])
            finally:
                os.chdir(cwd)

        self.assertTrue(any("forbidden 50-case publication overclaim/stale caveat" in problem for problem in problems))

    def test_missing_readme_svg_references_reports_unlinked_assets(self):
        module = load_script()
        text = "docs/assets/readme/instruction-lift.svg"

        missing = module.missing_readme_svg_references(text, ["instruction-lift.svg", "model-transfer.svg"])

        self.assertEqual(missing, ["model-transfer.svg"])

    def test_readme_places_absolute_quality_graphs_before_the_first_table(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        section_start = readme.index("## Absolute Cross-Model Quality")
        section_end = readme.index("\n## ", section_start + 1)
        section = readme[section_start:section_end]
        first_table = section.index("| Model | Role |")

        for name in (
            "model-quality-absolute.svg",
            "model-quality-common-cases.svg",
            "model-quality-judge-audit.svg",
        ):
            with self.subTest(name=name):
                self.assertLess(section.index(f"docs/assets/readme/{name}"), first_table)

    def test_forbidden_publication_overclaims_reports_variant_phrases(self):
        module = load_script()

        claims = module.forbidden_publication_overclaims(
            "This is a hard-gate-only 50-case snapshot. "
            "The complete 50-case reference refresh is ready. "
            "External reference rows are complete. "
            "GPT reference rows only; external reference rows remain pending. "
            "This is an all-model quality improvement. "
            "The current instructions improved every tested model."
        )

        self.assertTrue(any("hard-gate-only 50-case snapshot" in claim for claim in claims))
        self.assertTrue(any("complete 50-case reference refresh" in claim for claim in claims))
        self.assertTrue(any("external reference rows are complete" in claim for claim in claims))
        self.assertTrue(any("external reference rows remain pending" in claim for claim in claims))
        self.assertTrue(any("all-model quality improvement" in claim for claim in claims))
        self.assertTrue(any("improved every tested model" in claim for claim in claims))

    def test_forbidden_publication_overclaims_reports_pending_reference_caveat(self):
        module = load_script()

        claims = module.forbidden_publication_overclaims(
            "This is a 50-case saved quality snapshot. "
            "GPT reference rows are complete; external reference rows remain pending."
        )

        self.assertTrue(any("external reference rows remain pending" in claim for claim in claims))

    def test_check_svg_scope_accepts_scoped_svg_files(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp)
            (svg_dir / "chart.svg").write_text(
                f"<svg><text>{module.EXPECTED_SVG_SCOPE}</text></svg>\n",
                encoding="utf-8",
            )

            self.assertEqual(module.check_svg_scope(svg_dir, ["chart.svg"]), [])

    def test_default_blinded_svg_scope_requires_quality_progress_bars(self):
        module = load_script()

        self.assertEqual(
            module.EXPECTED_BLINDED_SVG_SCOPES,
            EXPECTED_BLINDED_SVG_SCOPES,
        )
        self.assertEqual(module.REQUIRED_README_SVGS, EXPECTED_BLINDED_SVGS)

    def test_check_svg_scope_accepts_exact_four_blinded_scopes(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp)
            for name, scope in module.EXPECTED_BLINDED_SVG_SCOPES.items():
                (svg_dir / name).write_text(
                    f"<svg><text>{scope}</text></svg>\n",
                    encoding="utf-8",
                )

            self.assertEqual(module.check_svg_scope(svg_dir), [])

    def test_check_svg_scope_reports_missing_scope_footer(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp)
            (svg_dir / "chart.svg").write_text("<svg><text>No scope</text></svg>\n", encoding="utf-8")

            problems = module.check_svg_scope(svg_dir, ["chart.svg"])

        self.assertIn("missing SVG scope footer", problems[0])

    def test_check_svg_scope_rejects_old_non_blinded_scope_footer(self):
        module = load_script()
        old_scope = "Scope: 50-case saved hard-gate and quality snapshot; all-model reference rows included."
        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp)
            (svg_dir / "chart.svg").write_text(f"<svg><text>{old_scope}</text></svg>\n", encoding="utf-8")

            problems = module.check_svg_scope(svg_dir, ["chart.svg"])

        self.assertTrue(any("missing SVG scope footer" in problem for problem in problems))

    def test_check_svg_scope_rejects_ambiguous_current_labels_in_blinded_assets(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp)
            for name, scope in module.EXPECTED_BLINDED_SVG_SCOPES.items():
                extra = "<text>current instructions</text>" if name == "hard-gates-50.svg" else ""
                (svg_dir / name).write_text(
                    f"<svg><text>{scope}</text>{extra}</svg>\n",
                    encoding="utf-8",
                )

            problems = module.check_svg_scope(svg_dir)

        self.assertTrue(any("ambiguous public label" in problem for problem in problems), problems)
        self.assertEqual(module.EXPECTED_SVG_SCOPE, LEGACY_SCOPE)

    def test_check_svg_scope_reports_forbidden_publication_overclaim(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp)
            (svg_dir / "chart.svg").write_text(
                f"<svg><text>{module.EXPECTED_SVG_SCOPE}</text>"
                "<text>The complete 50-case reference refresh is ready.</text></svg>\n",
                encoding="utf-8",
            )

            problems = module.check_svg_scope(svg_dir, ["chart.svg"])

        self.assertTrue(any("forbidden 50-case publication overclaim" in problem for problem in problems))

    def test_check_svg_scope_reports_missing_required_svg(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp)
            (svg_dir / "other.svg").write_text(
                f"<svg><text>{module.EXPECTED_SVG_SCOPE}</text></svg>\n",
                encoding="utf-8",
            )

            problems = module.check_svg_scope(svg_dir, ["required.svg"])

        self.assertIn("missing required README SVG", problems[0])

    def test_check_social_png_accepts_expected_metadata(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "social.png"
            write_text_png(path, module.EXPECTED_SOCIAL_PNG_METADATA)

            self.assertEqual(module.check_social_png(path), [])

    def test_check_social_png_reports_stale_metadata(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "social.png"
            metadata = dict(module.EXPECTED_SOCIAL_PNG_METADATA)
            metadata["instruction_snapshot_cases"] = "49"
            write_text_png(path, metadata)

            problems = module.check_social_png(path)

        self.assertTrue(any("instruction_snapshot_cases" in problem for problem in problems))

    def test_check_social_png_rejects_old_non_blinded_scope_metadata(self):
        module = load_script()
        old_scope = "Scope: 50-case saved hard-gate and quality snapshot; all-model reference rows included."
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "social.png"
            metadata = dict(module.EXPECTED_SOCIAL_PNG_METADATA)
            metadata["instruction_snapshot_scope"] = old_scope
            write_text_png(path, metadata)

            problems = module.check_social_png(path)

        self.assertTrue(any("instruction_snapshot_scope" in problem for problem in problems))
        self.assertEqual(
            module.EXPECTED_SOCIAL_PNG_METADATA["instruction_snapshot_scope"],
            BLINDED_DUAL_ORDER_SCOPE,
        )

    def test_main_success_output_mentions_publication_scope_checks(self):
        module = load_script()
        specs = blinded_model_artifacts()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_snapshot_artifacts(root, module)
            write_blinded_publication_artifacts(root, specs, total=50)
            snapshot = module.load_snapshot_metrics(root)
            with mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True):
                blinded = module.load_blinded_snapshot_metrics(root)
            write_matching_docs(root, module, snapshot)
            write_matching_blinded_docs(root, module, blinded)
            write_social_png(root, module)
            svg_dir = root / "svg"
            svg_dir.mkdir()
            for name, scope in module.EXPECTED_BLINDED_SVG_SCOPES.items():
                (svg_dir / name).write_text(
                    f"<svg><text>{scope}</text></svg>\n",
                    encoding="utf-8",
                )

            stdout = io.StringIO()
            cwd = Path.cwd()
            try:
                os.chdir(root)
                with (
                    redirect_stdout(stdout),
                    mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                    mock.patch.object(
                        module,
                        "load_absolute_publication",
                        return_value=({}, {}, {}),
                    ),
                    mock.patch.object(module, "check_absolute_docs", return_value=[]),
                ):
                    rc = module.main(["--svg-dir", str(svg_dir)])
            finally:
                os.chdir(cwd)

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("published 50-case eval publication guard ok:", output)
        self.assertIn("cases=50", output)
        self.assertIn("docs=5", output)
        self.assertIn("models=6", output)
        self.assertIn("svgs=7", output)
        self.assertIn("social=checked", output)
        self.assertIn("scope=checked", output)
        self.assertIn("judge=gpt-5.6-sol-medium", output)
        self.assertIn("dual_order=checked", output)
        self.assertIn("absolute=157x2", output)
        self.assertIn("common_pairs=15", output)
        self.assertIn("terra_audit=checked", output)

    def test_main_failure_output_mentions_publication_guard(self):
        module = load_script()
        specs = blinded_model_artifacts()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_snapshot_artifacts(root, module)
            write_blinded_publication_artifacts(root, specs, total=50)
            snapshot = module.load_snapshot_metrics(root)
            with mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True):
                blinded = module.load_blinded_snapshot_metrics(root)
            write_matching_docs(root, module, snapshot)
            write_matching_blinded_docs(root, module, blinded)
            write_social_png(root, module)
            svg_dir = root / "svg"
            svg_dir.mkdir()

            stderr = io.StringIO()
            cwd = Path.cwd()
            try:
                os.chdir(root)
                with (
                    redirect_stderr(stderr),
                    mock.patch.object(module, "BLINDED_MODEL_ARTIFACTS", specs, create=True),
                    mock.patch.object(
                        module,
                        "load_absolute_publication",
                        return_value=({}, {}, {}),
                    ),
                    mock.patch.object(module, "check_absolute_docs", return_value=[]),
                ):
                    rc = module.main(["--svg-dir", str(svg_dir)])
            finally:
                os.chdir(cwd)

        self.assertEqual(rc, 1)
        output = stderr.getvalue()
        self.assertIn("published eval publication guard failed:", output)
        self.assertIn("no SVG files found", output)

    def test_cli_description_mentions_docs_and_svg_scope(self):
        module = load_script()
        stdout = io.StringIO()

        with self.assertRaises(SystemExit) as raised:
            with redirect_stdout(stdout):
                module.parse_args(["--help"])

        self.assertEqual(raised.exception.code, 0)
        help_text = stdout.getvalue()
        self.assertIn(
            "50-case eval metrics, docs caveats, README SVG scope, and social PNG metadata",
            " ".join(help_text.split()),
        )


if __name__ == "__main__":
    unittest.main()
