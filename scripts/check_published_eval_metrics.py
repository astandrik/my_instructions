#!/usr/bin/env python3
"""Check published 50-case eval metrics, docs caveats, README SVG scope, and social PNG metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aggregate_saved_model_quality as quality_aggregator
import aggregate_model_absolute_quality as absolute_aggregator


CASE_FILE = Path("evals/cases.jsonl")
PUBLIC_ROOT = Path(".eval-results/refresh-2026-07-08-50-case-public-v1")
PROVIDER_ROOT_V1 = Path(".eval-results/refresh-2026-07-08-50-case-v1")
PROVIDER_ROOT_V2 = Path(".eval-results/refresh-2026-07-08-50-case-v2")
QUALITY_ROOT = Path(".eval-results/refresh-2026-07-08-50-case-quality-v1")
BLINDED_ROOT = Path(".eval-results/blinded-50-case-v1")
BLINDED_EXTERNAL_ROOT = Path(".eval-results/blinded-all-models-50-case-v1")
BLINDED_QUALITY_ROOT = BLINDED_ROOT / "dual-order-quality-v2"
ABSOLUTE_QUALITY_ROOT = Path(".eval-results/blinded-model-absolute-v1/canonical")
ABSOLUTE_SOL_QUALITY = ABSOLUTE_QUALITY_ROOT / "sol-absolute.json"
ABSOLUTE_TERRA_QUALITY = ABSOLUTE_QUALITY_ROOT / "terra-absolute.json"
ABSOLUTE_JUDGE_AUDIT = ABSOLUTE_QUALITY_ROOT / "sol-terra-audit.json"
BLINDED_SOL_CURRENT = BLINDED_ROOT / "current-sol56-medium-v1/current/summary.json"
BLINDED_SOL_EMPTY = BLINDED_ROOT / "empty-sol56-medium-v1/empty/summary.json"
EXPECTED_JUDGE_IDENTITY = {
    "model": "gpt-5.6-sol",
    "reasoning_effort": "medium",
    "service_tier": "fast",
    "agent_command_mode": "current-codex",
}
EXPECTED_JUDGE_PRESET = "gpt-5.6-sol-medium"
DUAL_ORDER_WINNER_BUCKETS = {
    "baseline",
    "current",
    "tie",
    "inconclusive",
    "order_sensitive",
}
PUBLISHED_CASE_COUNT = 50
DEFAULT_DOCS = [
    Path("README.md"),
    Path("evals/README.md"),
    Path("evals/RESULTS.md"),
    Path("evals/PROMPT_QUALITY_CASES.md"),
    Path("evals/CHANGELOG.md"),
]
DEFAULT_SVG_DIR = Path("docs/assets/readme")
DEFAULT_SOCIAL_IMAGE = Path("docs/assets/social/instruction-quality-lift-linkedin.png")
EXPECTED_SVG_SCOPE = (
    "Scope: legacy pre-blinding snapshot, 50 cases; primary prompts exposed case id/scenario metadata; "
    "all-model reference rows included."
)
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
ABSOLUTE_SEPARATE_METRICS_CAVEAT = (
    "Hard-gate pass rate and quality among passed responses are separate metrics."
)
ABSOLUTE_COMMON_CASE_CAVEAT = (
    "Direct model comparisons use only common hard-gate-passed cases and are derived from saved absolute scores."
)
ABSOLUTE_JUDGES_CAVEAT = (
    "Sol medium is the primary judge; Terra high is an audit judge. Their scores are shown separately and are not averaged."
)
ABSOLUTE_NO_RANK_CAVEAT = "No global leaderboard or rank is computed."
BLINDED_DOC_HEADINGS = {
    "README.md": "## Blinded Six-Model Evidence",
    "evals/README.md": "## Blinded Six-Model Publication",
    "evals/RESULTS.md": "## Blinded Six-Model Snapshot",
    "evals/PROMPT_QUALITY_CASES.md": "## Blinded Six-Model Publication Scope",
    "evals/CHANGELOG.md": "## 2026-07-10 - Blinded Six-Model Refresh",
}
ABSOLUTE_DOC_HEADINGS = {
    "README.md": "## Absolute Cross-Model Quality",
    "evals/README.md": "## Absolute Cross-Model Quality",
    "evals/RESULTS.md": "## Absolute Cross-Model Quality Snapshot",
    "evals/PROMPT_QUALITY_CASES.md": "## Absolute Cross-Model Quality Scope",
    "evals/CHANGELOG.md": "## 2026-07-10 - Absolute Cross-Model Quality",
}
LEGACY_DOC_CAVEAT = (
    "Legacy pre-blinding snapshot: primary prompts exposed case id/scenario metadata "
    "(prompt contamination). The unchanged numbers are historical and are not clean blinded "
    "instruction-lift evidence."
)
EXPECTED_SOCIAL_PNG_METADATA = {
    "instruction_snapshot_cases": "50",
    "instruction_snapshot_scope": BLINDED_DUAL_ORDER_SCOPE,
    "instruction_snapshot_models": "6",
    "instruction_snapshot_aggregation": "dual_order_consensus",
    "instruction_snapshot_judge": "gpt-5.6-sol-medium",
    "instruction_snapshot_quality_root": str(BLINDED_QUALITY_ROOT),
    "generated_by": "scripts/build_readme_infographics.py",
}
REQUIRED_README_SVGS = list(EXPECTED_BLINDED_SVG_SCOPES)
README_SVG_PREFIX = "docs/assets/readme/"

BLINDED_MODEL_ARTIFACTS = [
    {
        "model_id": "gpt-5.6-sol",
        "model_label": "GPT-5.6 Sol medium",
        "current": BLINDED_SOL_CURRENT,
        "empty": BLINDED_SOL_EMPTY,
        "quality": BLINDED_QUALITY_ROOT / "gpt-5.6-sol/dual-order-summary.json",
        "same_model_judge": True,
    },
    {
        "model_id": "gpt-5.5",
        "model_label": "GPT-5.5",
        "current": BLINDED_ROOT / "current-gpt55/current/summary.json",
        "empty": BLINDED_ROOT / "empty-gpt55/empty/summary.json",
        "quality": BLINDED_QUALITY_ROOT / "gpt-5.5/dual-order-summary.json",
        "same_model_judge": False,
    },
    {
        "model_id": "glm-5.2",
        "model_label": "GLM-5.2",
        "current": BLINDED_EXTERNAL_ROOT / "current-glm-5.2/current/summary.json",
        "empty": BLINDED_EXTERNAL_ROOT / "empty-glm-5.2/empty/summary.json",
        "quality": BLINDED_QUALITY_ROOT / "glm-5.2/dual-order-summary.json",
        "same_model_judge": False,
    },
    {
        "model_id": "grok-4.3",
        "model_label": "Grok 4.3",
        "current": BLINDED_EXTERNAL_ROOT / "current-grok-4.3/current/summary.json",
        "empty": BLINDED_EXTERNAL_ROOT / "empty-grok-4.3/empty/summary.json",
        "quality": BLINDED_QUALITY_ROOT / "grok-4.3/dual-order-summary.json",
        "same_model_judge": False,
    },
    {
        "model_id": "deepseek-v4-flash",
        "model_label": "DeepSeek V4 Flash",
        "current": BLINDED_EXTERNAL_ROOT / "current-deepseek-v4-flash/current/summary.json",
        "empty": BLINDED_EXTERNAL_ROOT / "empty-deepseek-v4-flash/empty/summary.json",
        "quality": BLINDED_QUALITY_ROOT / "deepseek-v4-flash/dual-order-summary.json",
        "same_model_judge": False,
    },
    {
        "model_id": "deepseek-v4-flash-thinking",
        "model_label": "DeepSeek V4 Flash thinking",
        "current": BLINDED_EXTERNAL_ROOT / "current-deepseek-v4-flash-thinking/current/summary.json",
        "empty": BLINDED_EXTERNAL_ROOT / "empty-deepseek-v4-flash-thinking/empty/summary.json",
        "quality": BLINDED_QUALITY_ROOT / "deepseek-v4-flash-thinking/dual-order-summary.json",
        "same_model_judge": False,
    },
]

MODEL_ARTIFACTS = [
    {
        "label": "GPT-5.5",
        "readme_label": "GPT/Codex",
        "current": PUBLIC_ROOT / "current-gpt55/current/summary.json",
        "empty": PUBLIC_ROOT / "empty-gpt55/empty/summary.json",
        "quality": QUALITY_ROOT
        / "empty-vs-current-gpt55/GPT-5.5-empty-saved-model-quality/model-quality-summary.json",
    },
    {
        "label": "GLM-5.2",
        "readme_label": "GLM-5.2",
        "current": PROVIDER_ROOT_V2 / "current-glm-5.2/current/summary.json",
        "empty": PROVIDER_ROOT_V2 / "empty-glm-5.2/empty/summary.json",
        "quality": QUALITY_ROOT
        / "empty-vs-current-glm-5.2/GLM-5.2-empty-saved-model-quality/model-quality-summary.json",
    },
    {
        "label": "Grok 4.3",
        "readme_label": "Grok 4.3",
        "current": PROVIDER_ROOT_V1 / "current-grok-4.3/current/summary.json",
        "empty": PROVIDER_ROOT_V1 / "empty-grok-4.3/empty/summary.json",
        "quality": QUALITY_ROOT
        / "empty-vs-current-grok-4.3/Grok-4.3-empty-saved-model-quality/model-quality-summary.json",
    },
    {
        "label": "Grok Build 0.1",
        "readme_label": "Grok Build 0.1",
        "current": PROVIDER_ROOT_V1 / "current-grok-build-0.1/current/summary.json",
        "empty": PROVIDER_ROOT_V1 / "empty-grok-build-0.1/empty/summary.json",
        "quality": QUALITY_ROOT
        / "empty-vs-current-grok-build-0.1/Grok-Build-0.1-empty-saved-model-quality/model-quality-summary.json",
    },
    {
        "label": "DeepSeek V4 Flash",
        "readme_label": "DeepSeek V4 Flash",
        "current": PUBLIC_ROOT / "current-deepseek-v4-flash/current/summary.json",
        "empty": PROVIDER_ROOT_V1 / "empty-deepseek-v4-flash/empty/summary.json",
        "quality": QUALITY_ROOT
        / "empty-vs-current-deepseek-v4-flash/DeepSeek-V4-Flash-empty-saved-model-quality/model-quality-summary.json",
    },
    {
        "label": "DeepSeek V4 thinking",
        "readme_label": "DeepSeek V4 thinking",
        "quality_label": "DeepSeek V4 Flash thinking",
        "current": PROVIDER_ROOT_V1 / "current-deepseek-v4-flash-thinking/current/summary.json",
        "empty": PROVIDER_ROOT_V1 / "empty-deepseek-v4-flash-thinking/empty/summary.json",
        "quality": QUALITY_ROOT
        / "empty-vs-current-deepseek-v4-flash-thinking/DeepSeek-V4-Flash-thinking-empty-saved-model-quality/model-quality-summary.json",
    },
]
GPT_EXTERNAL_QUALITY = (
    QUALITY_ROOT / "gpt-vs-external-current/GPT-5.5-saved-model-quality/model-quality-summary.json"
)
REFERENCE_QUALITY_SUMMARIES = [
    {
        "label": "OpenHands `AGENTS.md`",
        "quality": QUALITY_ROOT
        / "quality-reference-openhands-vs-current-all-models-full-v1/Reference-OpenHands-saved-model-quality/model-quality-summary.json",
    },
    {
        "label": "Claude/Fable prompt",
        "quality": QUALITY_ROOT
        / "quality-reference-claude-fable-vs-current-all-models-full-v1/Reference-Fable-saved-model-quality/model-quality-summary.json",
    },
]

FORBIDDEN_PUBLICATION_OVERCLAIMS = [
    "hard-gate-only 50-case snapshot",
    "50-case hard-gate-only snapshot",
    "quality evidence is still pending for the 50-case suite",
    "quality matrices remain pending for the 50-case suite",
    "GPT reference rows only",
    "external reference rows remain pending",
    "external reference rows are pending",
    "complete 50-case reference refresh",
    "full 50-case reference refresh",
    "all external reference rows are complete",
    "external reference rows are complete",
    "external reference rows completed",
    "all-model reference refresh",
    "all-model quality improvement",
    "improved every tested model",
    "improves every tested model",
    "improved all tested models",
]
FORBIDDEN_PUBLICATION_OVERCLAIM_PATTERNS = [
    re.compile(r"\b50-case (?:saved )?quality (?:is |evidence is |matrices are )?(?:still )?pending\b"),
    re.compile(r"\b(?:complete|full) 50-case reference refresh\b"),
    re.compile(r"\bexternal reference rows (?:are )?(?:complete|completed|done)\b"),
    re.compile(r"\ball[- ]models? reference refresh\b"),
    re.compile(r"\ball[- ]models? quality (?:improved|improvement)\b"),
    re.compile(r"\b(?:all|every) tested models? improved\b"),
    re.compile(r"\bimprov(?:ed|es) (?:all|every) tested models?\b"),
]


@dataclass(frozen=True)
class CompareMetrics:
    summary_passed: int
    summary_total: int
    case_count: int
    baseline_passed: int
    current_passed: int
    current_wins: int
    baseline_wins: int
    ties: int
    inconclusive: int
    average_delta: float

    @property
    def average_delta_text(self) -> str:
        return f"{self.average_delta:+.2f}"


@dataclass(frozen=True)
class SnapshotMetrics:
    case_count: int
    model_rows: list[dict[str, Any]]
    external_rows: list[dict[str, Any]]
    reference_rows: list[dict[str, Any]]


@dataclass(frozen=True)
class PrimarySummaryMetrics:
    passed: int
    total: int
    case_ids: frozenset[str]
    agent_failures: int
    transport_failures: int
    pass_by_case: dict[str, bool]


@dataclass(frozen=True)
class BlindedSolMetrics:
    model_label: str
    current_passed: int
    empty_passed: int
    total: int
    agent_failures: int
    transport_failures: int


@dataclass(frozen=True)
class BlindedSnapshotMetrics:
    case_count: int
    model_rows: list[dict[str, Any]]
    judge_identity: dict[str, str]


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing artifact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except FileNotFoundError as exc:
        raise ValueError(f"missing case file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSONL: {exc}") from exc


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def require_list(value: Any, path: Path, key: str) -> list[Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected object")
    items = value.get(key)
    if not isinstance(items, list):
        raise ValueError(f"{path}: expected list field {key!r}")
    return items


def summarize_compare_artifacts(
    summary: dict[str, Any],
    quality: dict[str, Any],
    *,
    summary_path: Path,
    quality_path: Path,
    baseline_labels: set[str] | None = None,
    current_label: str = "current",
) -> CompareMetrics:
    results = require_list(summary, summary_path, "results")
    comparisons = require_list(quality, quality_path, "comparisons")
    if not comparisons:
        raise ValueError(f"{quality_path}: expected at least one comparison")

    summary_passed = sum(1 for record in results if isinstance(record, dict) and record.get("passed") is True)
    summary_total = len(results)
    reported_passed = summary.get("passed")
    reported_failed = summary.get("failed")
    if reported_passed is not None and reported_passed != summary_passed:
        raise ValueError(f"{summary_path}: reported passed={reported_passed}, computed passed={summary_passed}")
    if reported_failed is not None and reported_failed != summary_total - summary_passed:
        raise ValueError(f"{summary_path}: reported failed={reported_failed}, computed failed={summary_total - summary_passed}")

    labels_by_case: dict[str, set[str]] = {}
    pass_by_label: dict[str, int] = {}
    for record in results:
        if not isinstance(record, dict):
            raise ValueError(f"{summary_path}: summary result must be an object")
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"{summary_path}: summary result requires non-empty case_id")
        label = record.get("label")
        if not isinstance(label, str) or not label:
            raise ValueError(f"{summary_path}: summary result requires non-empty label for case_id {case_id!r}")
        case_labels = labels_by_case.setdefault(case_id, set())
        if label in case_labels:
            raise ValueError(f"{summary_path}: duplicate summary label {label!r} for case_id {case_id!r}")
        case_labels.add(label)
        if record.get("passed") is True:
            pass_by_label[label] = pass_by_label.get(label, 0) + 1

    expected_quality_case_ids: set[str] = set()
    winners = {"current": 0, "baseline": 0, "tie": 0, "inconclusive": 0}
    deltas: list[float] = []
    for item in comparisons:
        if not isinstance(item, dict):
            raise ValueError(f"{quality_path}: comparison must be an object")
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"{quality_path}: comparison requires non-empty case_id")
        if case_id in expected_quality_case_ids:
            raise ValueError(f"{quality_path}: duplicate comparison case_id {case_id!r}")
        expected_quality_case_ids.add(case_id)
        quality_result = item.get("quality")
        if not isinstance(quality_result, dict):
            raise ValueError(f"{quality_path}: comparison requires quality object")
        winner = quality_result.get("winner", "inconclusive")
        if winner not in winners:
            raise ValueError(f"{quality_path}: unknown winner {winner!r}")
        winners[winner] += 1
        delta = quality_result.get("delta")
        if isinstance(delta, (int, float)):
            deltas.append(float(delta))
    if len(deltas) != len(comparisons):
        raise ValueError(f"{quality_path}: every comparison must have a numeric quality delta")

    summary_case_ids = set(labels_by_case)
    if summary_case_ids != expected_quality_case_ids:
        only_summary = ", ".join(sorted(summary_case_ids - expected_quality_case_ids))
        only_quality = ", ".join(sorted(expected_quality_case_ids - summary_case_ids))
        details = []
        if only_summary:
            details.append(f"only in summary: {only_summary}")
        if only_quality:
            details.append(f"only in quality: {only_quality}")
        raise ValueError(f"{summary_path} / {quality_path}: case_id mismatch ({'; '.join(details)})")

    baseline_labels = baseline_labels or {"baseline-HEAD"}
    expected_labels = set(baseline_labels) | {current_label}
    for case_id, labels in sorted(labels_by_case.items()):
        if labels != expected_labels:
            missing = ", ".join(sorted(expected_labels - labels))
            extra = ", ".join(sorted(labels - expected_labels))
            detail = f"missing summary label(s): {missing}" if missing else f"unexpected summary label(s): {extra}"
            raise ValueError(f"{summary_path}: case_id {case_id!r} {detail}")

    return CompareMetrics(
        summary_passed=summary_passed,
        summary_total=summary_total,
        case_count=len(comparisons),
        baseline_passed=sum(pass_by_label.get(label, 0) for label in baseline_labels),
        current_passed=pass_by_label.get(current_label, 0),
        current_wins=winners["current"],
        baseline_wins=winners["baseline"],
        ties=winners["tie"],
        inconclusive=winners["inconclusive"],
        average_delta=round(sum(deltas) / len(deltas), 2),
    )


def summarize_artifacts(summary: dict[str, Any], quality: dict[str, Any], *, summary_path: Path, quality_path: Path) -> CompareMetrics:
    return summarize_compare_artifacts(summary, quality, summary_path=summary_path, quality_path=quality_path)


def summary_passes(path: Path) -> dict[str, int]:
    data = read_json(path)
    results = require_list(data, path, "results")
    passed = sum(1 for record in results if isinstance(record, dict) and record.get("passed") is True)
    total = len(results)
    reported_passed = data.get("passed")
    reported_failed = data.get("failed")
    if reported_passed is not None and reported_passed != passed:
        raise ValueError(f"{path}: reported passed={reported_passed}, computed passed={passed}")
    if reported_failed is not None and reported_failed != total - passed:
        raise ValueError(f"{path}: reported failed={reported_failed}, computed failed={total - passed}")
    return {"passed": passed, "failed": total - passed, "total": total}


def primary_summary_metrics(path: Path, expected_label: str) -> PrimarySummaryMetrics:
    data = read_json(path)
    results = require_list(data, path, "results")
    case_ids: set[str] = set()
    passed = 0
    agent_failures = 0
    transport_failures = 0
    pass_by_case: dict[str, bool] = {}
    for record in results:
        if not isinstance(record, dict):
            raise ValueError(f"{path}: summary result must be an object")
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"{path}: summary result requires non-empty case_id")
        if case_id in case_ids:
            raise ValueError(f"{path}: duplicate case_id {case_id!r}")
        case_ids.add(case_id)
        if record.get("label") != expected_label:
            raise ValueError(f"{path}: case_id {case_id!r} expected label {expected_label!r}")
        if not isinstance(record.get("passed"), bool):
            raise ValueError(f"{path}: case_id {case_id!r} requires boolean passed")
        pass_by_case[case_id] = record["passed"]
        failure_type = record.get("failure_type")
        if record["passed"]:
            if failure_type != "none":
                raise ValueError(
                    f"{path}: passed case_id {case_id!r} expected failure_type 'none', got {failure_type!r}"
                )
            passed += 1
        elif failure_type == "behavior":
            pass
        elif failure_type == "agent":
            agent_failures += 1
        elif failure_type == "transport":
            transport_failures += 1
        else:
            raise ValueError(f"{path}: case_id {case_id!r} has unexpected failure_type {failure_type!r}")

    total = len(results)
    reported_passed = data.get("passed")
    reported_failed = data.get("failed")
    reported_total = data.get("total")
    if reported_passed is not None and reported_passed != passed:
        raise ValueError(f"{path}: reported passed={reported_passed}, computed passed={passed}")
    if reported_failed is not None and reported_failed != total - passed:
        raise ValueError(f"{path}: reported failed={reported_failed}, computed failed={total - passed}")
    if reported_total is not None and reported_total != total:
        raise ValueError(f"{path}: reported total={reported_total}, computed total={total}")
    return PrimarySummaryMetrics(
        passed=passed,
        total=total,
        case_ids=frozenset(case_ids),
        agent_failures=agent_failures,
        transport_failures=transport_failures,
        pass_by_case=pass_by_case,
    )


def load_blinded_sol_metrics(repo_root: Path) -> BlindedSolMetrics:
    current = primary_summary_metrics(repo_root / BLINDED_SOL_CURRENT, "current")
    empty = primary_summary_metrics(repo_root / BLINDED_SOL_EMPTY, "empty")
    if current.case_ids != empty.case_ids:
        only_current = ", ".join(sorted(current.case_ids - empty.case_ids))
        only_empty = ", ".join(sorted(empty.case_ids - current.case_ids))
        raise ValueError(
            f"blinded Sol current/empty case_id mismatch "
            f"(only current: {only_current or 'none'}; only empty: {only_empty or 'none'})"
        )
    agent_failures = current.agent_failures + empty.agent_failures
    transport_failures = current.transport_failures + empty.transport_failures
    if agent_failures or transport_failures:
        raise ValueError(
            "blinded Sol primary pair has execution failures: "
            f"agent={agent_failures} transport={transport_failures}"
        )
    return BlindedSolMetrics(
        model_label="GPT-5.6 Sol medium",
        current_passed=current.passed,
        empty_passed=empty.passed,
        total=current.total,
        agent_failures=agent_failures,
        transport_failures=transport_failures,
    )


def require_nonnegative_int(value: Any, path: Path, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{path}: {field} must be a non-negative integer")
    return value


def validate_judge_preset(judge: Any, path: Path) -> None:
    actual = judge.get("preset") if isinstance(judge, dict) else None
    if actual != EXPECTED_JUDGE_PRESET:
        raise ValueError(
            f"{path}: judge preset mismatch: "
            f"expected={EXPECTED_JUDGE_PRESET!r} actual={actual!r}"
        )


def artifact_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f"cannot hash primary artifact {path}: {exc}") from exc


def repo_relative_artifact_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"primary artifact path is outside repo root: {path}") from exc


def detail_order_score(value: Any, detail_path: Path, field: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 100
    ):
        raise ValueError(
            f"{detail_path}: detail order {field} must be an integer from 0 to 100"
        )
    return value


def detail_order_delta(
    value: Any,
    *,
    baseline_score: int,
    current_score: int,
    detail_path: Path,
    field: str,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"{detail_path}: detail order {field} must be an exact derived integer"
        )
    if value != current_score - baseline_score:
        raise ValueError(
            f"{detail_path}: detail order {field} must equal the derived integer delta"
        )
    return value


def resolve_recorded_artifact_path(
    repo_root: Path, detail_path: Path, field: str, value: Any
) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError(f"{detail_path}: raw order {field} must be a repo-relative path")
    resolved = (repo_root / value).resolve()
    normalized = repo_relative_artifact_path(resolved, repo_root)
    if normalized != Path(value).as_posix():
        raise ValueError(f"{detail_path}: raw order {field} path drift")
    return resolved


def validate_raw_order_provenance(
    *,
    repo_root: Path,
    detail_path: Path,
    inputs: dict[str, Any],
    baseline_label: str,
    current_label: str,
    canonical_comparisons: list[dict[str, Any]],
) -> None:
    expected_orientations = {"baseline_first", "current_first"}
    raw_orders = inputs.get("orders")
    if not isinstance(raw_orders, dict) or set(raw_orders) != expected_orientations:
        actual = sorted(raw_orders) if isinstance(raw_orders, dict) else raw_orders
        raise ValueError(
            f"{detail_path}: raw order orientations must be exact: "
            f"expected={sorted(expected_orientations)} actual={actual}"
        )
    expected_fields = {
        "summary_path",
        "summary_sha256",
        "quality_path",
        "quality_sha256",
    }
    resolved_inputs: dict[str, dict[str, Path]] = {}
    for orientation in ("baseline_first", "current_first"):
        raw_input = raw_orders[orientation]
        if not isinstance(raw_input, dict) or set(raw_input) != expected_fields:
            raise ValueError(
                f"{detail_path}: raw order {orientation} input fields are invalid"
            )
        summary_path = resolve_recorded_artifact_path(
            repo_root,
            detail_path,
            f"{orientation}.summary_path",
            raw_input["summary_path"],
        )
        quality_path = resolve_recorded_artifact_path(
            repo_root,
            detail_path,
            f"{orientation}.quality_path",
            raw_input["quality_path"],
        )
        for artifact_kind, artifact_path in (
            ("summary", summary_path),
            ("quality", quality_path),
        ):
            hash_field = f"{artifact_kind}_sha256"
            if raw_input[hash_field] != artifact_sha256(artifact_path):
                raise ValueError(
                    f"{detail_path}: raw order {orientation}.{hash_field} mismatch"
                )
        resolved_inputs[orientation] = {
            "summary": summary_path,
            "quality": quality_path,
        }

    try:
        reports = quality_aggregator.load_order_reports(
            [
                resolved_inputs["baseline_first"]["summary"],
                resolved_inputs["current_first"]["summary"],
            ],
            repo_root=repo_root,
            baseline_label=baseline_label,
            current_label=current_label,
        )
        recomputed = quality_aggregator.aggregate_dual_order(
            [reports["baseline_first"], reports["current_first"]],
            baseline_label=baseline_label,
            current_label=current_label,
        )
    except quality_aggregator.evals.ValidationError as exc:
        raise ValueError(f"{detail_path}: raw order validation failed: {exc}") from exc

    for orientation in ("baseline_first", "current_first"):
        if reports[orientation]["_summary_path"] != resolved_inputs[orientation]["summary"]:
            raise ValueError(f"{detail_path}: raw order orientation path mismatch")
        if reports[orientation]["_quality_path"] != resolved_inputs[orientation]["quality"]:
            raise ValueError(f"{detail_path}: raw order {orientation}.quality_path mismatch")
    if recomputed["comparisons"] != canonical_comparisons:
        raise ValueError(
            f"{detail_path}: raw order comparisons do not match canonical detail comparisons"
        )


def detail_score_summary(
    comparisons: list[dict[str, Any]], *, source: str | None = None
) -> dict[str, int | float | None]:
    selected = [item for item in comparisons if source is None or item["source"] == source]
    if not selected:
        return {"cases": 0, "baseline": None, "current": None, "delta": None}
    baseline_values = [
        float(order["baseline_score"])
        for item in selected
        for order in item["orders"].values()
    ]
    current_values = [
        float(order["current_score"])
        for item in selected
        for order in item["orders"].values()
    ]
    baseline = round(sum(baseline_values) / len(baseline_values), 2)
    current = round(sum(current_values) / len(current_values), 2)
    return {
        "cases": len(selected),
        "baseline": baseline,
        "current": current,
        "delta": round(current - baseline, 2),
    }


def validate_dual_order_detail(
    *,
    repo_root: Path,
    item: dict[str, Any],
    quality_path: Path,
    quality: dict[str, Any],
    aggregate: dict[str, Any],
    case_ids: set[str],
    current: PrimarySummaryMetrics,
    empty: PrimarySummaryMetrics,
) -> None:
    pointer = quality.get("quality_json")
    if pointer != "dual-order-quality.json":
        raise ValueError(
            f"{quality_path}: quality_json must name the exact sibling dual-order-quality.json"
        )
    detail_path = quality_path.with_name(pointer)
    detail = read_json(detail_path)
    if not isinstance(detail, dict):
        raise ValueError(f"{detail_path}: detail artifact must be an object")
    validate_judge_preset(detail.get("judge"), detail_path)

    metadata_fields = (
        "schema_version",
        "aggregation",
        "model_id",
        "model_label",
        "baseline_label",
        "current_label",
        "judge",
    )
    metadata_drift = [field for field in metadata_fields if detail.get(field) != quality.get(field)]
    if metadata_drift:
        raise ValueError(
            f"{detail_path}: detail metadata does not match summary: {metadata_drift}"
        )
    if detail.get("aggregate") != aggregate:
        raise ValueError(f"{detail_path}: detail aggregate does not match summary aggregate")

    inputs = detail.get("inputs")
    source_summaries = inputs.get("source_summaries") if isinstance(inputs, dict) else None
    if not isinstance(source_summaries, dict) or set(source_summaries) != {"baseline", "current"}:
        raise ValueError(f"{detail_path}: detail source summary inputs are invalid")
    source_specs = {
        "baseline": (repo_root / item["empty"], empty),
        "current": (repo_root / item["current"], current),
    }
    for semantic_label, (primary_path, _metrics) in source_specs.items():
        source_input = source_summaries.get(semantic_label)
        if not isinstance(source_input, dict):
            raise ValueError(f"{detail_path}: detail source input {semantic_label!r} is invalid")
        expected_path = repo_relative_artifact_path(primary_path, repo_root)
        if source_input.get("path") != expected_path:
            raise ValueError(
                f"{detail_path}: source input path does not match primary {semantic_label}: "
                f"expected={expected_path!r} actual={source_input.get('path')!r}"
            )
        expected_hash = artifact_sha256(primary_path)
        if source_input.get("sha256") != expected_hash:
            raise ValueError(
                f"{detail_path}: source input sha256 does not match primary {semantic_label}"
            )

    comparisons = require_list(detail, detail_path, "comparisons")
    detail_case_ids: set[str] = set()
    source_counts = {"hard_gate": 0, "llm_judge": 0}
    winner_counts = {bucket: 0 for bucket in DUAL_ORDER_WINNER_BUCKETS}
    normalized_comparisons: list[dict[str, Any]] = []
    order_winners = {"baseline", "current", "tie", "inconclusive"}
    for comparison in comparisons:
        if not isinstance(comparison, dict):
            raise ValueError(f"{detail_path}: detail comparison must be an object")
        case_id = comparison.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"{detail_path}: detail comparison requires non-empty case_id")
        if case_id in detail_case_ids:
            raise ValueError(f"{detail_path}: duplicate detail case_id {case_id!r}")
        detail_case_ids.add(case_id)
        if case_id not in case_ids:
            raise ValueError(f"{detail_path}: unexpected detail case_id {case_id!r}")

        baseline_passed = comparison.get("baseline_passed")
        current_passed = comparison.get("current_passed")
        if not isinstance(baseline_passed, bool) or not isinstance(current_passed, bool):
            raise ValueError(f"{detail_path}: detail pass state must be boolean for {case_id!r}")
        if (
            baseline_passed != empty.pass_by_case[case_id]
            or current_passed != current.pass_by_case[case_id]
        ):
            raise ValueError(
                f"{detail_path}: detail primary pass state mismatch for {case_id!r}"
            )

        source = comparison.get("source")
        if source not in source_counts:
            raise ValueError(f"{detail_path}: invalid detail source for {case_id!r}: {source!r}")
        expected_source = (
            "llm_judge" if baseline_passed and current_passed else "hard_gate"
        )
        if source != expected_source:
            raise ValueError(
                f"{detail_path}: detail source does not match primary pass states "
                f"for {case_id!r}: expected={expected_source!r} actual={source!r}"
            )
        source_counts[source] += 1

        expected_gate_result = None
        if source == "hard_gate":
            if baseline_passed:
                expected_gate_result = ("baseline", 100, 0, -100)
            elif current_passed:
                expected_gate_result = ("current", 0, 100, 100)
            else:
                expected_gate_result = ("inconclusive", 0, 0, 0)

        orders = comparison.get("orders")
        if not isinstance(orders, dict) or set(orders) != {"baseline_first", "current_first"}:
            raise ValueError(f"{detail_path}: invalid detail orders for {case_id!r}")
        semantic_winners: list[str] = []
        normalized_orders: dict[str, dict[str, int | str]] = {}
        for orientation in ("baseline_first", "current_first"):
            order = orders[orientation]
            if not isinstance(order, dict) or order.get("winner") not in order_winners:
                raise ValueError(
                    f"{detail_path}: invalid detail order winner for {case_id!r}/{orientation}"
                )
            baseline_score = detail_order_score(
                order.get("baseline_score"), detail_path, f"{case_id}.{orientation}.baseline_score"
            )
            current_score = detail_order_score(
                order.get("current_score"), detail_path, f"{case_id}.{orientation}.current_score"
            )
            delta = detail_order_delta(
                order.get("delta"),
                baseline_score=baseline_score,
                current_score=current_score,
                detail_path=detail_path,
                field=f"{case_id}.{orientation}.delta",
            )
            if expected_gate_result is not None:
                actual_gate_result = (
                    order["winner"],
                    baseline_score,
                    current_score,
                    delta,
                )
                if actual_gate_result != expected_gate_result:
                    raise ValueError(
                        f"{detail_path}: hard-gate result disagrees with primary pass states "
                        f"for {case_id!r}/{orientation}"
                    )
            semantic_winners.append(order["winner"])
            normalized_orders[orientation] = {
                "winner": order["winner"],
                "baseline_score": baseline_score,
                "current_score": current_score,
                "delta": delta,
            }
        consensus = (
            semantic_winners[0]
            if semantic_winners[0] == semantic_winners[1]
            else "order_sensitive"
        )
        if comparison.get("winner") != consensus:
            raise ValueError(
                f"{detail_path}: detail winner does not match order consensus for {case_id!r}"
            )
        winner_counts[consensus] += 1

        expected_balanced_baseline = round(
            sum(float(order["baseline_score"]) for order in normalized_orders.values()) / 2,
            2,
        )
        expected_balanced_current = round(
            sum(float(order["current_score"]) for order in normalized_orders.values()) / 2,
            2,
        )
        expected_balanced = {
            "baseline": expected_balanced_baseline,
            "current": expected_balanced_current,
            "delta": round(expected_balanced_current - expected_balanced_baseline, 2),
        }
        if comparison.get("balanced_scores") != expected_balanced:
            raise ValueError(f"{detail_path}: detail balanced score drift for {case_id!r}")
        normalized_comparisons.append({**comparison, "orders": normalized_orders})

    if detail_case_ids != case_ids:
        missing = sorted(case_ids - detail_case_ids)
        extra = sorted(detail_case_ids - case_ids)
        raise ValueError(
            f"{detail_path}: detail case set mismatch (missing={missing or 'none'} extra={extra or 'none'})"
        )
    if len(comparisons) != aggregate["total"]:
        raise ValueError(
            f"{detail_path}: detail case count={len(comparisons)} does not match aggregate total={aggregate['total']}"
        )
    detail_baseline_passed = sum(item["baseline_passed"] for item in comparisons)
    detail_current_passed = sum(item["current_passed"] for item in comparisons)
    if (
        detail_baseline_passed != aggregate["baseline_passed"]
        or detail_current_passed != aggregate["current_passed"]
    ):
        raise ValueError(f"{detail_path}: detail primary pass counts do not match aggregate")
    if source_counts != aggregate["sources"]:
        raise ValueError(f"{detail_path}: detail source counts do not match aggregate")
    if winner_counts != aggregate["winners"]:
        raise ValueError(f"{detail_path}: detail winner counts do not match aggregate")
    expected_scores = {
        "all_cases": detail_score_summary(normalized_comparisons),
        "llm_judge": detail_score_summary(normalized_comparisons, source="llm_judge"),
    }
    if expected_scores != aggregate["scores"]:
        raise ValueError(f"{detail_path}: detail score aggregates do not match comparisons")
    validate_raw_order_provenance(
        repo_root=repo_root,
        detail_path=detail_path,
        inputs=inputs,
        baseline_label=quality["baseline_label"],
        current_label=quality["current_label"],
        canonical_comparisons=normalized_comparisons,
    )


def load_blinded_snapshot_metrics(repo_root: Path) -> BlindedSnapshotMetrics:
    cases = read_jsonl(repo_root / CASE_FILE)
    case_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"{repo_root / CASE_FILE}: case {index} must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"{repo_root / CASE_FILE}: case {index} requires non-empty id")
        if case_id in case_ids:
            raise ValueError(f"{repo_root / CASE_FILE}: duplicate case id {case_id!r}")
        case_ids.add(case_id)
    if len(case_ids) != PUBLISHED_CASE_COUNT:
        raise ValueError(
            f"{repo_root / CASE_FILE}: blinded publication requires exactly "
            f"{PUBLISHED_CASE_COUNT} cases; found {len(case_ids)}"
        )

    model_rows = []
    for item in BLINDED_MODEL_ARTIFACTS:
        model_id = item["model_id"]
        current_path = repo_root / item["current"]
        empty_path = repo_root / item["empty"]
        quality_path = repo_root / item["quality"]
        current = primary_summary_metrics(current_path, "current")
        empty = primary_summary_metrics(empty_path, "empty")

        if current.case_ids != empty.case_ids:
            raise ValueError(f"{model_id}: blinded current/empty case_id mismatch")
        if current.case_ids != case_ids:
            missing = sorted(case_ids - current.case_ids)
            extra = sorted(current.case_ids - case_ids)
            raise ValueError(
                f"{model_id}: blinded primary case_id mismatch "
                f"(missing={missing or 'none'} extra={extra or 'none'})"
            )

        agent_failures = current.agent_failures + empty.agent_failures
        transport_failures = current.transport_failures + empty.transport_failures
        if agent_failures or transport_failures:
            raise ValueError(
                f"{model_id}: blinded primary pair has execution failures: "
                f"agent={agent_failures} transport={transport_failures}"
            )

        quality = read_json(quality_path)
        if quality.get("schema_version") != 1:
            raise ValueError(f"{quality_path}: expected schema_version=1")
        if quality.get("aggregation") != "dual_order_consensus":
            raise ValueError(f"{quality_path}: expected aggregation='dual_order_consensus'")
        if quality.get("model_id") != model_id:
            raise ValueError(f"{quality_path}: expected model_id {model_id!r}")
        if quality.get("model_label") != item["model_label"]:
            raise ValueError(f"{quality_path}: expected model_label {item['model_label']!r}")
        if quality.get("baseline_label") != "empty" or quality.get("current_label") != "current":
            raise ValueError(f"{quality_path}: expected empty/current quality labels")

        judge = quality.get("judge")
        if not isinstance(judge, dict):
            raise ValueError(f"{quality_path}: missing judge identity")
        validate_judge_preset(judge, quality_path)
        actual_judge_identity = {key: judge.get(key) for key in EXPECTED_JUDGE_IDENTITY}
        if actual_judge_identity != EXPECTED_JUDGE_IDENTITY:
            raise ValueError(
                f"{quality_path}: judge identity mismatch: "
                f"expected={EXPECTED_JUDGE_IDENTITY} actual={actual_judge_identity}"
            )

        aggregate = quality.get("aggregate")
        if not isinstance(aggregate, dict):
            raise ValueError(f"{quality_path}: missing aggregate object")
        total = require_nonnegative_int(aggregate.get("total"), quality_path, "aggregate.total")
        baseline_passed = require_nonnegative_int(
            aggregate.get("baseline_passed"), quality_path, "aggregate.baseline_passed"
        )
        current_passed = require_nonnegative_int(
            aggregate.get("current_passed"), quality_path, "aggregate.current_passed"
        )
        if total != len(case_ids):
            raise ValueError(f"{quality_path}: aggregate total={total} does not match cases={len(case_ids)}")
        if baseline_passed != empty.passed or current_passed != current.passed:
            raise ValueError(
                f"{quality_path}: aggregate primary counts do not match summaries: "
                f"empty={baseline_passed}/{empty.passed} current={current_passed}/{current.passed}"
            )

        winners = aggregate.get("winners")
        if not isinstance(winners, dict) or set(winners) != DUAL_ORDER_WINNER_BUCKETS:
            actual_buckets = sorted(winners) if isinstance(winners, dict) else winners
            raise ValueError(
                f"{quality_path}: winner buckets must be {sorted(DUAL_ORDER_WINNER_BUCKETS)}; "
                f"actual={actual_buckets}"
            )
        winner_counts = {
            bucket: require_nonnegative_int(winners[bucket], quality_path, f"aggregate.winners.{bucket}")
            for bucket in DUAL_ORDER_WINNER_BUCKETS
        }
        winner_sum = sum(winner_counts.values())
        if winner_sum != total:
            raise ValueError(
                f"{quality_path}: winner bucket sum={winner_sum} does not match aggregate total={total}"
            )

        sources = aggregate.get("sources")
        if not isinstance(sources, dict) or set(sources) != {"hard_gate", "llm_judge"}:
            raise ValueError(f"{quality_path}: sources must contain hard_gate and llm_judge")
        source_counts = {
            source: require_nonnegative_int(sources[source], quality_path, f"aggregate.sources.{source}")
            for source in ("hard_gate", "llm_judge")
        }
        if sum(source_counts.values()) != total:
            raise ValueError(f"{quality_path}: source count sum does not match aggregate total={total}")

        scores = aggregate.get("scores")
        if not isinstance(scores, dict) or set(scores) != {"all_cases", "llm_judge"}:
            raise ValueError(f"{quality_path}: scores must contain all_cases and llm_judge")
        expected_score_cases = {"all_cases": total, "llm_judge": source_counts["llm_judge"]}
        for score_scope, expected_cases in expected_score_cases.items():
            score = scores[score_scope]
            if not isinstance(score, dict):
                raise ValueError(f"{quality_path}: scores.{score_scope} must be an object")
            score_cases = require_nonnegative_int(
                score.get("cases"), quality_path, f"aggregate.scores.{score_scope}.cases"
            )
            if score_cases != expected_cases:
                raise ValueError(
                    f"{quality_path}: scores.{score_scope}.cases={score_cases} "
                    f"does not match expected={expected_cases}"
                )
            for field in ("baseline", "current", "delta"):
                value = score.get(field)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{quality_path}: scores.{score_scope}.{field} must be numeric")

        validate_dual_order_detail(
            repo_root=repo_root,
            item=item,
            quality_path=quality_path,
            quality=quality,
            aggregate=aggregate,
            case_ids=case_ids,
            current=current,
            empty=empty,
        )

        model_rows.append(
            {
                **item,
                "current_passed": current.passed,
                "empty_passed": empty.passed,
                "total": total,
                "dual_order_winners": winner_counts,
                "sources": source_counts,
                "scores": scores,
            }
        )

    return BlindedSnapshotMetrics(
        case_count=len(case_ids),
        model_rows=model_rows,
        judge_identity=dict(EXPECTED_JUDGE_IDENTITY),
    )


def quality_model_pair(path: Path) -> dict[str, Any]:
    data = read_json(path)
    pairs = require_list(data, path, "pairs")
    if len(pairs) != 1:
        raise ValueError(f"{path}: expected exactly one model-quality pair")
    pair = pairs[0]
    if not isinstance(pair, dict) or not isinstance(pair.get("aggregate"), dict):
        raise ValueError(f"{path}: expected pair aggregate")
    return pair


def quality_model_pairs(path: Path) -> list[dict[str, Any]]:
    data = read_json(path)
    pairs = require_list(data, path, "pairs")
    if not pairs:
        raise ValueError(f"{path}: expected model-quality pairs")
    return pairs


def aggregate_quality(path: Path) -> dict[str, Any]:
    data = read_json(path)
    comparisons = require_list(data, path, "comparisons")
    winners = {"current": 0, "baseline": 0, "tie": 0, "inconclusive": 0}
    deltas = []
    for item in comparisons:
        if not isinstance(item, dict) or not isinstance(item.get("quality"), dict):
            raise ValueError(f"{path}: comparison requires quality object")
        quality = item["quality"]
        winner = quality.get("winner", "inconclusive")
        if winner not in winners:
            raise ValueError(f"{path}: unknown winner {winner!r}")
        winners[winner] += 1
        delta = quality.get("delta")
        if not isinstance(delta, (int, float)):
            raise ValueError(f"{path}: every comparison must have a numeric quality delta")
        deltas.append(float(delta))
    return {"total": len(comparisons), "winners": winners, "average_delta": round(sum(deltas) / len(deltas), 1)}


def pass_by_label(summary_path: Path) -> dict[str, int]:
    data = read_json(summary_path)
    results = require_list(data, summary_path, "results")
    passes: dict[str, int] = {}
    for item in results:
        if isinstance(item, dict) and item.get("passed") is True and isinstance(item.get("label"), str):
            passes[item["label"]] = passes.get(item["label"], 0) + 1
    return passes


def load_snapshot_metrics(repo_root: Path) -> SnapshotMetrics:
    cases = read_jsonl(repo_root / CASE_FILE)
    model_rows = []
    for item in MODEL_ARTIFACTS:
        current = summary_passes(repo_root / item["current"])
        empty = summary_passes(repo_root / item["empty"])
        pair = quality_model_pair(repo_root / item["quality"])
        aggregate = pair["aggregate"]
        winners = aggregate["winners"]
        model_rows.append(
            {
                "label": item["label"],
                "readme_label": item["readme_label"],
                "quality_label": item.get("quality_label", item["label"]),
                "current_passed": current["passed"],
                "empty_passed": empty["passed"],
                "total": current["total"],
                "quality_delta": aggregate["average_delta"],
                "current_wins": winners["current"],
                "baseline_wins": winners["baseline"],
                "ties": winners["tie"],
                "inconclusive": winners.get("inconclusive", 0),
                "current_score": aggregate["average_current_score"],
                "empty_score": aggregate["average_baseline_score"],
                "judge_calls": aggregate["sources"].get("llm_judge", 0),
                "hard_gate_shortcuts": aggregate["sources"].get("hard_gate", 0),
            }
        )

    external_rows = []
    for pair in quality_model_pairs(repo_root / GPT_EXTERNAL_QUALITY):
        aggregate = pair["aggregate"]
        winners = aggregate["winners"]
        external_rows.append(
            {
                "label": pair["candidate_label"],
                "hard_passed": aggregate["candidate_passed"],
                "gpt_passed": aggregate["baseline_passed"],
                "total": aggregate["total"],
                "wins": winners["current"],
                "gpt_wins": winners["baseline"],
                "ties": winners["tie"],
                "inconclusive": winners.get("inconclusive", 0),
                "delta": aggregate["average_delta"],
            }
        )

    reference_rows = []
    for item in REFERENCE_QUALITY_SUMMARIES:
        for pair in quality_model_pairs(repo_root / item["quality"]):
            aggregate = pair["aggregate"]
            winners = aggregate["winners"]
            reference_rows.append(
                {
                    "label": item["label"],
                    "candidate_label": pair["candidate_label"],
                    "current_passed": aggregate["candidate_passed"],
                    "reference_passed": aggregate["baseline_passed"],
                    "total": aggregate["total"],
                    "current_wins": winners["current"],
                    "reference_wins": winners["baseline"],
                    "ties": winners["tie"],
                    "inconclusive": winners.get("inconclusive", 0),
                    "delta": aggregate["average_delta"],
                    "current_score": aggregate["average_current_score"],
                    "reference_score": aggregate["average_baseline_score"],
                    "judge_calls": aggregate["sources"].get("llm_judge", 0),
                    "hard_gate_shortcuts": aggregate["sources"].get("hard_gate", 0),
                }
            )

    return SnapshotMetrics(case_count=len(cases), model_rows=model_rows, external_rows=external_rows, reference_rows=reference_rows)


def model_row(snapshot: SnapshotMetrics, label: str) -> dict[str, Any]:
    for row in snapshot.model_rows:
        if row["label"] == label or row.get("readme_label") == label:
            return row
    raise ValueError(f"missing model row: {label}")


def reference_row(snapshot: SnapshotMetrics, label_prefix: str) -> dict[str, Any]:
    for row in snapshot.reference_rows:
        if row["label"].startswith(label_prefix):
            return row
    raise ValueError(f"missing reference row: {label_prefix}")


def reference_rows_for(snapshot: SnapshotMetrics, label_prefix: str) -> list[dict[str, Any]]:
    rows = [row for row in snapshot.reference_rows if row["label"].startswith(label_prefix)]
    if not rows:
        raise ValueError(f"missing reference rows: {label_prefix}")
    return rows


def reference_doc_row(row: dict[str, Any], reference_name: str) -> str:
    return (
        f"| {row['candidate_label']} | {row['current_passed']} / {row['total']} | "
        f"{row['reference_passed']} / {row['total']} | {row['current_wins']} | "
        f"{row['reference_wins']} | {row['ties']} | {row['inconclusive']} | "
        f"{row['current_score']:.1f} | {row['reference_score']:.1f} | {row['delta']:+.1f} | "
        f"{row['judge_calls']} | {row['hard_gate_shortcuts']} |"
    )


def current_empty_quality_doc_row(row: dict[str, Any]) -> str:
    return (
        f"| {row.get('quality_label', row['label'])} | {row['current_wins']} | "
        f"{row['baseline_wins']} | {row['ties']} | "
        f"{row['inconclusive']} | {row['current_score']:.1f} | {row['empty_score']:.1f} | "
        f"{row['quality_delta']:+.1f} | {row['judge_calls']} | {row['hard_gate_shortcuts']} |"
    )


def changelog_ledger_row(snapshot: SnapshotMetrics) -> str:
    gpt = model_row(snapshot, "GPT-5.5")
    glm = model_row(snapshot, "GLM-5.2")
    if all(row["quality_delta"] > 0 for row in snapshot.model_rows):
        quality_status = "current-vs-empty saved quality positive for all six runners"
    else:
        quality_status = "current-vs-empty saved quality mixed across six runners"
    return (
        "| 2026-07-08 legacy pre-blinding snapshot | 50 current-vs-empty cases, all tested runners | "
        f"`{QUALITY_ROOT}/` | GPT {gpt['current_passed']} / {gpt['total']}, "
        f"GLM {glm['current_passed']} / {glm['total']} | {quality_status}; "
        "all-model reference rows included | mixed | empty baselines and OpenHands/Fable references |"
    )


def expected_doc_snippets(snapshot: SnapshotMetrics) -> dict[str, list[str]]:
    gpt = model_row(snapshot, "GPT-5.5")
    glm = model_row(snapshot, "GLM-5.2")
    grok = model_row(snapshot, "Grok 4.3")
    grok_build = model_row(snapshot, "Grok Build 0.1")
    deepseek = model_row(snapshot, "DeepSeek V4 Flash")
    deepseek_thinking = model_row(snapshot, "DeepSeek V4 thinking")
    openhands_rows = reference_rows_for(snapshot, "OpenHands")
    fable_rows = reference_rows_for(snapshot, "Claude/Fable")
    openhands_gpt = next(row for row in openhands_rows if row["candidate_label"] == "GPT-5.5-current")
    fable_gpt = next(row for row in fable_rows if row["candidate_label"] == "GPT-5.5-current")
    openhands_glm = next(row for row in openhands_rows if row["candidate_label"] == "GLM-5.2-current")
    fable_glm = next(row for row in fable_rows if row["candidate_label"] == "GLM-5.2-current")
    all_positive_quality = all(row["quality_delta"] > 0 for row in snapshot.model_rows)
    positive_quality_text = "current-vs-empty saved quality is positive for all six tested runners" if all_positive_quality else "current-vs-empty saved quality is mixed"
    return {
        "README.md": [
            f"## Historical Evidence\n\n{LEGACY_DOC_CAVEAT}",
            "50-case saved quality snapshot",
            f"GPT/Codex passed {gpt['current_passed']}/{gpt['total']} current and {gpt['empty_passed']}/{gpt['total']} empty",
            f"GLM-5.2 reached {glm['current_passed']}/{glm['total']} current",
            positive_quality_text,
            "all-model reference rows are now included",
            ".eval-results/refresh-2026-07-08-50-case-quality-v1/",
        ],
        "evals/README.md": [
            f"# Instruction Evals\n\n{LEGACY_DOC_CAVEAT}",
        ],
        "evals/RESULTS.md": [
            f"## 50-Case Refresh Snapshot\n\n{LEGACY_DOC_CAVEAT}",
            "## 50-Case Refresh Snapshot",
            f"| GPT-5.5 via Codex CLI | {gpt['current_passed']} / {gpt['total']} | {gpt['empty_passed']} / {gpt['total']} | +{gpt['current_passed'] - gpt['empty_passed']} |",
            f"| GLM-5.2 via Z.ai adapter | {glm['current_passed']} / {glm['total']} | {glm['empty_passed']} / {glm['total']} | +{glm['current_passed'] - glm['empty_passed']} |",
            f"| Grok 4.3 via xAI adapter | {grok['current_passed']} / {grok['total']} | {grok['empty_passed']} / {grok['total']} | +{grok['current_passed'] - grok['empty_passed']} |",
            f"| Grok Build 0.1 via xAI adapter | {grok_build['current_passed']} / {grok_build['total']} | {grok_build['empty_passed']} / {grok_build['total']} | +{grok_build['current_passed'] - grok_build['empty_passed']} |",
            f"| DeepSeek V4 Flash via DeepSeek adapter | {deepseek['current_passed']} / {deepseek['total']} | {deepseek['empty_passed']} / {deepseek['total']} | +{deepseek['current_passed'] - deepseek['empty_passed']} |",
            f"| DeepSeek V4 Flash thinking mode | {deepseek_thinking['current_passed']} / {deepseek_thinking['total']} | {deepseek_thinking['empty_passed']} / {deepseek_thinking['total']} | +{deepseek_thinking['current_passed'] - deepseek_thinking['empty_passed']} |",
            *(current_empty_quality_doc_row(row) for row in snapshot.model_rows),
            "### All-Model Reference Prompt Quality",
            reference_doc_row(openhands_gpt, "OpenHands"),
            reference_doc_row(openhands_glm, "OpenHands"),
            reference_doc_row(fable_gpt, "Claude/Fable"),
            reference_doc_row(fable_glm, "Claude/Fable"),
        ],
        "evals/PROMPT_QUALITY_CASES.md": [
            f"## Snapshot Sources\n\n{LEGACY_DOC_CAVEAT}",
            "2026-07-08 50-case all-model reference comparisons",
            "quality-reference-openhands-vs-current-all-models-full-v1",
            "quality-reference-claude-fable-vs-current-all-models-full-v1",
            f"| OpenHands `AGENTS.md` | GPT-5.5-current | {openhands_gpt['current_passed']} / {openhands_gpt['total']} | {openhands_gpt['reference_passed']} / {openhands_gpt['total']} | current {openhands_gpt['current_wins']}, OpenHands {openhands_gpt['reference_wins']}, tie {openhands_gpt['ties']}, inconclusive {openhands_gpt['inconclusive']} |",
            f"| Claude/Fable prompt | GPT-5.5-current | {fable_gpt['current_passed']} / {fable_gpt['total']} | {fable_gpt['reference_passed']} / {fable_gpt['total']} | current {fable_gpt['current_wins']}, Fable {fable_gpt['reference_wins']}, tie {fable_gpt['ties']}, inconclusive {fable_gpt['inconclusive']} |",
            "`agent-data-injection-trusted-metadata`",
        ],
        "evals/CHANGELOG.md": [
            f"## 2026-07-08 - Agent Data Injection Eval Coverage and 50-Case Refresh\n\n{LEGACY_DOC_CAVEAT}",
            changelog_ledger_row(snapshot),
            "50-case saved-output quality refresh",
            f"GPT/Codex `{gpt['current_passed']}/{gpt['total']}` current and `{gpt['empty_passed']}/{gpt['total']}` empty",
            positive_quality_text,
            "all-model reference rows are now included",
        ],
    }


def expected_doc_sections(snapshot: SnapshotMetrics) -> dict[str, list[tuple[str, list[str]]]]:
    snippets = expected_doc_snippets(snapshot)
    return {
        "README.md": [
            ("## Historical Evidence", [LEGACY_DOC_CAVEAT, *snippets["README.md"][1:]]),
        ],
        "evals/README.md": [
            ("# Instruction Evals", [LEGACY_DOC_CAVEAT]),
        ],
        "evals/RESULTS.md": [
            ("## 50-Case Refresh Snapshot", [LEGACY_DOC_CAVEAT, *snippets["evals/RESULTS.md"][2:]]),
        ],
        "evals/PROMPT_QUALITY_CASES.md": [
            (
                "## Snapshot Sources",
                [LEGACY_DOC_CAVEAT, *snippets["evals/PROMPT_QUALITY_CASES.md"][1:-1]],
            ),
        ],
        "evals/CHANGELOG.md": [
            ("## Version Metric Ledger", [LEGACY_DOC_CAVEAT, snippets["evals/CHANGELOG.md"][1]]),
            (
                "## 2026-07-08 - Agent Data Injection Eval Coverage and 50-Case Refresh",
                [LEGACY_DOC_CAVEAT, *snippets["evals/CHANGELOG.md"][2:]],
            ),
        ],
    }


def blinded_hard_gate_doc_row(row: dict[str, Any]) -> str:
    return (
        f"| {row['model_label']} | {row['current_passed']} / {row['total']} | "
        f"{row['empty_passed']} / {row['total']} | "
        f"{row['current_passed'] - row['empty_passed']:+d} |"
    )


def blinded_dual_order_doc_row(row: dict[str, Any]) -> str:
    winners = row["dual_order_winners"]
    return (
        f"| {row['model_label']} | {winners['current']} | {winners['baseline']} | "
        f"{winners['tie']} | {winners['order_sensitive']} | {winners['inconclusive']} |"
    )


def expected_blinded_doc_sections(
    metrics: BlindedSnapshotMetrics,
) -> dict[str, list[tuple[str, list[str]]]]:
    hard_gate_rows = [blinded_hard_gate_doc_row(row) for row in metrics.model_rows]
    dual_order_rows = [blinded_dual_order_doc_row(row) for row in metrics.model_rows]
    caveats = [
        FIXED_JUDGE_CAVEAT,
        SAME_MODEL_JUDGE_CAVEAT,
        WITHIN_RUNNER_CAVEAT,
        NO_REFERENCE_CAVEAT,
        GROK_BUILD_EXCLUSION_CAVEAT,
    ]
    artifact_root = f"`{BLINDED_QUALITY_ROOT}/`"
    return {
        "README.md": [
            (
                BLINDED_DOC_HEADINGS["README.md"],
                [*hard_gate_rows, *dual_order_rows, *caveats, artifact_root],
            ),
        ],
        "evals/README.md": [
            (
                BLINDED_DOC_HEADINGS["evals/README.md"],
                [*caveats, artifact_root],
            ),
        ],
        "evals/RESULTS.md": [
            (
                BLINDED_DOC_HEADINGS["evals/RESULTS.md"],
                [*hard_gate_rows, *dual_order_rows, *caveats, artifact_root],
            ),
        ],
        "evals/PROMPT_QUALITY_CASES.md": [
            (
                BLINDED_DOC_HEADINGS["evals/PROMPT_QUALITY_CASES.md"],
                [*caveats, "order-sensitive", artifact_root],
            ),
        ],
        "evals/CHANGELOG.md": [
            (
                BLINDED_DOC_HEADINGS["evals/CHANGELOG.md"],
                [*hard_gate_rows, *dual_order_rows, *caveats, artifact_root],
            ),
        ],
    }


def load_absolute_publication(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest_path = repo_root / "evals/model-quality-matrix.json"
    output_root = repo_root / ".eval-results/blinded-model-absolute-v1"
    sol = absolute_aggregator.aggregate_judge(
        repo_root, manifest_path, "sol", output_root=output_root
    )
    terra = absolute_aggregator.aggregate_judge(
        repo_root, manifest_path, "terra", output_root=output_root
    )
    audit = absolute_aggregator.aggregate_judge_audit(sol, terra)
    expected = {
        ABSOLUTE_SOL_QUALITY: sol,
        ABSOLUTE_TERRA_QUALITY: terra,
        ABSOLUTE_JUDGE_AUDIT: audit,
    }
    for relative_path, recomputed in expected.items():
        path = repo_root / relative_path
        saved = read_json(path)
        if saved != recomputed:
            raise ValueError(f"{path}: canonical absolute-quality artifact is stale")
    return sol, terra, audit


def absolute_doc_row(sol_row: dict[str, Any], terra_row: dict[str, Any]) -> str:
    role = {"primary": "Primary", "historical": "Historical", "external": "External"}[
        sol_row["role"]
    ]
    delta = terra_row["mean_absolute_score"] - sol_row["mean_absolute_score"]
    return (
        f"| {sol_row['model_label']} | {role} | {sol_row['hard_gate_passed']} / "
        f"{sol_row['hard_gate_total']} | {sol_row['mean_absolute_score']:.2f} | "
        f"{terra_row['mean_absolute_score']:.2f} | {delta:+.2f} |"
    )


def expected_absolute_doc_sections(
    sol: dict[str, Any], terra: dict[str, Any], audit: dict[str, Any]
) -> dict[str, list[tuple[str, list[str]]]]:
    terra_by_id = {row["model_id"]: row for row in terra["models"]}
    rows = [absolute_doc_row(row, terra_by_id[row["model_id"]]) for row in sol["models"]]
    stable = sum(not row["judge_sensitive"] for row in audit["common_case_comparisons"])
    changed = sum(row["changed_case_directions"] for row in audit["common_case_comparisons"])
    relations = sum(row["overlap"] for row in audit["common_case_comparisons"])
    caveats = [
        ABSOLUTE_SEPARATE_METRICS_CAVEAT,
        ABSOLUTE_COMMON_CASE_CAVEAT,
        ABSOLUTE_JUDGES_CAVEAT,
        ABSOLUTE_NO_RANK_CAVEAT,
        f"`{ABSOLUTE_QUALITY_ROOT}/`",
    ]
    summary = f"all {stable} aggregate pair directions"
    sensitivity = f"{changed} of {relations} pair-case score relations"
    return {
        "README.md": [(ABSOLUTE_DOC_HEADINGS["README.md"], [*rows, *caveats, summary, sensitivity])],
        "evals/README.md": [(ABSOLUTE_DOC_HEADINGS["evals/README.md"], caveats)],
        "evals/RESULTS.md": [
            (ABSOLUTE_DOC_HEADINGS["evals/RESULTS.md"], [*rows, *caveats, summary, sensitivity])
        ],
        "evals/PROMPT_QUALITY_CASES.md": [
            (ABSOLUTE_DOC_HEADINGS["evals/PROMPT_QUALITY_CASES.md"], caveats)
        ],
        "evals/CHANGELOG.md": [
            (ABSOLUTE_DOC_HEADINGS["evals/CHANGELOG.md"], [*rows, *caveats, summary, sensitivity])
        ],
    }


def check_absolute_docs(
    sol: dict[str, Any], terra: dict[str, Any], audit: dict[str, Any], docs: list[Path]
) -> list[str]:
    expectations = expected_absolute_doc_sections(sol, terra, audit)
    problems: list[str] = []
    for path in docs:
        key = doc_expectation_key(path, expectations)
        if key is None:
            continue
        try:
            raw_text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            problems.append(f"missing doc: {path}")
            continue
        for heading, snippets in expectations[key]:
            ranges = markdown_section_ranges(raw_text, heading)
            if len(ranges) != 1:
                problems.append(
                    f"{path}: expected one absolute-quality publication section {heading}, found {len(ranges)}"
                )
                continue
            section = normalize_text(raw_text[ranges[0][0] : ranges[0][1]])
            for snippet in snippets:
                if normalize_text(snippet) not in section:
                    problems.append(
                        f"{path}: missing absolute-quality metric snippet in {heading}: {snippet}"
                    )
    return problems


def doc_expectation_key(path: Path, snippets: dict[str, list[str]]) -> str | None:
    raw = path.as_posix()
    matches = [key for key in snippets if raw == key or raw.endswith(f"/{key}")]
    return max(matches, key=len) if matches else None


def markdown_section_ranges(text: str, heading: str) -> list[tuple[int, int]]:
    expected_level = len(heading) - len(heading.lstrip("#"))
    if expected_level < 1 or not heading.startswith("#" * expected_level + " "):
        raise ValueError(f"invalid Markdown heading: {heading}")
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    ranges: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        if line.strip() != heading:
            continue
        end = len(text)
        for next_index in range(index + 1, len(lines)):
            match = re.match(r"^\s{0,3}(#{1,6})\s+", lines[next_index])
            if match and len(match.group(1)) <= expected_level:
                end = offsets[next_index]
                break
        ranges.append((offsets[index], end))
    return ranges


def retained_seven_model_headings(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if re.match(r"^\s{0,3}#{1,6}\s+", line)
        and "Blinded Seven-Model" in line
    ]


def numeric_grok_build_markdown_rows(text: str) -> list[str]:
    numeric_cell = re.compile(r"(?<![\w.])[+-]?\d+(?:\.\d+)?(?:\s*/\s*\d+)?(?![\w.])")
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        grok_cells = {
            index for index, cell in enumerate(cells) if "grok build" in cell.casefold()
        }
        if grok_cells and any(
            numeric_cell.search(cell)
            for index, cell in enumerate(cells)
            if index not in grok_cells
        ):
            rows.append(stripped)
    return rows


def text_outside_ranges(text: str, ranges: list[tuple[int, int]]) -> str:
    if not ranges:
        return text
    merged: list[list[int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    chunks: list[str] = []
    offset = 0
    for start, end in merged:
        chunks.append(text[offset:start])
        offset = end
    chunks.append(text[offset:])
    return "".join(chunks)


def forbidden_publication_overclaims(text: str) -> list[str]:
    normalized = normalize_text(text).casefold()
    literal_claims = [claim for claim in FORBIDDEN_PUBLICATION_OVERCLAIMS if claim in normalized]
    pattern_claims = [match.group(0) for pattern in FORBIDDEN_PUBLICATION_OVERCLAIM_PATTERNS for match in pattern.finditer(normalized)]
    return literal_claims + pattern_claims


def missing_readme_svg_references(text: str, required_names: list[str] | None = None) -> list[str]:
    required = required_names or REQUIRED_README_SVGS
    return [name for name in sorted(required) if f"{README_SVG_PREFIX}{name}" not in text]


def check_docs(snapshot: SnapshotMetrics, docs: list[Path]) -> list[str]:
    problems = []
    snippets = expected_doc_snippets(snapshot)
    section_expectations = expected_doc_sections(snapshot)
    for path in docs:
        key = doc_expectation_key(path, snippets)
        expected = snippets.get(key)
        if expected is None:
            problems.append(f"{path}: no published metric expectations configured")
            continue
        try:
            raw_text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            problems.append(f"missing doc: {path}")
            continue
        text = normalize_text(raw_text)
        for snippet in expected:
            if normalize_text(snippet) not in text:
                problems.append(f"{path}: missing published 50-case metric/caveat snippet: {snippet}")
        caveated_ranges: list[tuple[int, int]] = []
        metric_signatures: list[str] = []
        for heading, required_snippets in section_expectations[key]:
            ranges = markdown_section_ranges(raw_text, heading)
            if not ranges:
                problems.append(f"{path}: missing legacy publication section: {heading}")
                continue
            if len(ranges) != 1:
                problems.append(
                    f"{path}: expected one legacy publication section {heading}, found {len(ranges)}"
                )
            caveated = [
                section_range
                for section_range in ranges
                if normalize_text(LEGACY_DOC_CAVEAT)
                in normalize_text(raw_text[section_range[0] : section_range[1]])
            ]
            if not caveated:
                problems.append(f"{path}: {heading} is missing the legacy prompt-contamination caveat")
                continue
            caveated_ranges.extend(caveated)
            for snippet in required_snippets:
                if not any(
                    normalize_text(snippet) in normalize_text(raw_text[start:end])
                    for start, end in caveated
                ):
                    problems.append(
                        f"{path}: missing published 50-case metric/caveat snippet in {heading}: {snippet}"
                    )
                if snippet != LEGACY_DOC_CAVEAT:
                    if key == "evals/CHANGELOG.md" and heading == "## Version Metric Ledger":
                        metric_signatures.append(snippet.split(" | ", 1)[1])
                    else:
                        metric_signatures.append(snippet)
        outside_text = normalize_text(text_outside_ranges(raw_text, caveated_ranges))
        for snippet in dict.fromkeys(metric_signatures):
            if normalize_text(snippet) in outside_text:
                problems.append(f"{path}: legacy metric appears outside its caveated section: {snippet}")
        for claim in forbidden_publication_overclaims(raw_text):
            problems.append(f"{path}: forbidden 50-case publication overclaim/stale caveat: {claim}")
        if key == "README.md":
            for name in missing_readme_svg_references(raw_text):
                problems.append(f"{path}: missing README SVG reference: {README_SVG_PREFIX}{name}")
    return problems


def check_blinded_docs(metrics: BlindedSnapshotMetrics, docs: list[Path]) -> list[str]:
    problems = []
    expectations = expected_blinded_doc_sections(metrics)
    for path in docs:
        key = doc_expectation_key(path, expectations)
        if key is None:
            continue
        try:
            raw_text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            problems.append(f"missing doc: {path}")
            continue
        for stale_heading in retained_seven_model_headings(raw_text):
            problems.append(
                f"{path}: retained Blinded Seven-Model section: {stale_heading}"
            )
        for heading, required_snippets in expectations[key]:
            ranges = markdown_section_ranges(raw_text, heading)
            if len(ranges) != 1:
                problems.append(
                    f"{path}: expected one blinded six-model publication section "
                    f"{heading}, found {len(ranges)}"
                )
                continue
            raw_section_text = raw_text[ranges[0][0] : ranges[0][1]]
            section_text = normalize_text(raw_section_text)
            for snippet in required_snippets:
                if normalize_text(snippet) not in section_text:
                    problems.append(
                        f"{path}: missing blinded six-model metric snippet in "
                        f"{heading}: {snippet}"
                    )
            for stale_row in numeric_grok_build_markdown_rows(raw_section_text):
                problems.append(
                    f"{path}: numeric Grok Build Markdown table row in {heading}: "
                    f"{stale_row}"
                )
    return problems


def check_svg_scope(svg_dir: Path, required_names: list[str] | None = None) -> list[str]:
    if not svg_dir.exists():
        return [f"missing SVG directory: {svg_dir}"]
    svg_files = sorted(svg_dir.glob("*.svg"))
    if not svg_files:
        return [f"no SVG files found in: {svg_dir}"]
    problems = []
    svg_by_name = {path.name: path for path in svg_files}
    required = set(required_names or REQUIRED_README_SVGS)
    for name in sorted(required):
        if name not in svg_by_name:
            problems.append(f"{svg_dir / name}: missing required README SVG")
    for name in sorted(set(svg_by_name) - required):
        problems.append(f"{svg_dir / name}: unexpected README SVG")
    for path in svg_files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(f"{path}: failed to read SVG: {exc}")
            continue
        expected_scope = (
            EXPECTED_BLINDED_SVG_SCOPES.get(path.name)
            if required_names is None
            else EXPECTED_SVG_SCOPE
        )
        if expected_scope is not None and expected_scope not in text:
            problems.append(f"{path}: missing SVG scope footer: {expected_scope}")
        if required_names is None:
            normalized_svg = normalize_text(text).casefold()
            ambiguous_labels = (
                "current instructions",
                "current-vs-empty",
                "current vs empty",
                "empty -> current",
                "empty -&gt; current",
            )
            for label in ambiguous_labels:
                if label in normalized_svg:
                    problems.append(f"{path}: ambiguous public label in blinded SVG: {label}")
        for claim in forbidden_publication_overclaims(text):
            problems.append(f"{path}: forbidden 50-case publication overclaim/stale caveat: {claim}")
    return problems


def png_text_chunks(path: Path) -> dict[str, str]:
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError(f"missing social PNG: {path}") from exc
    signature = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(signature):
        raise ValueError(f"{path}: not a PNG file")
    chunks: dict[str, str] = {}
    offset = len(signature)
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        kind = data[offset + 4 : offset + 8]
        start = offset + 8
        end = start + length
        if end + 4 > len(data):
            raise ValueError(f"{path}: truncated PNG chunk")
        payload = data[start:end]
        if kind == b"tEXt":
            key, separator, value = payload.partition(b"\0")
            if separator:
                chunks[key.decode("latin-1")] = value.decode("latin-1")
        offset = end + 4
        if kind == b"IEND":
            break
    return chunks


def check_social_png(path: Path, expected_metadata: dict[str, str] | None = None) -> list[str]:
    expected = expected_metadata or EXPECTED_SOCIAL_PNG_METADATA
    try:
        metadata = png_text_chunks(path)
    except ValueError as exc:
        return [str(exc)]
    problems = []
    for key, expected_value in expected.items():
        actual_value = metadata.get(key)
        if actual_value != expected_value:
            problems.append(f"{path}: stale or missing social PNG metadata {key}={expected_value!r}")
    return problems


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--doc",
        action="append",
        dest="docs",
        help="Documentation file to check. Defaults to README plus eval README, RESULTS, PROMPT_QUALITY_CASES, and CHANGELOG.",
    )
    parser.add_argument("--svg-dir", default=str(DEFAULT_SVG_DIR), help="Directory containing generated README SVGs.")
    parser.add_argument("--social-image", default=str(DEFAULT_SOCIAL_IMAGE), help="Generated social-card PNG to check.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path.cwd()
    docs = [Path(path) for path in (args.docs or [str(path) for path in DEFAULT_DOCS])]
    try:
        snapshot = load_snapshot_metrics(repo_root)
        blinded = load_blinded_snapshot_metrics(repo_root)
        absolute_sol, absolute_terra, absolute_audit = load_absolute_publication(repo_root)
        if blinded.case_count != snapshot.case_count:
            raise ValueError(
                "blinded six-model case count does not match the published 50-case contract: "
                f"blinded={blinded.case_count} contract={snapshot.case_count}"
            )
        if len(blinded.model_rows) != len(BLINDED_MODEL_ARTIFACTS):
            raise ValueError(
                "blinded six-model row count mismatch: "
                f"rows={len(blinded.model_rows)} expected={len(BLINDED_MODEL_ARTIFACTS)}"
            )
    except ValueError as exc:
        print(f"published eval metric check failed: {exc}", file=sys.stderr)
        return 2

    svg_dir = Path(args.svg_dir)
    social_image = Path(args.social_image)
    problems = check_docs(snapshot, docs)
    problems.extend(check_blinded_docs(blinded, docs))
    problems.extend(check_absolute_docs(absolute_sol, absolute_terra, absolute_audit, docs))
    problems.extend(check_svg_scope(svg_dir))
    problems.extend(check_social_png(social_image))
    if problems:
        print("published eval publication guard failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    svg_count = len(list(svg_dir.glob("*.svg")))
    print(
        "published 50-case eval publication guard ok: "
        f"cases={snapshot.case_count}, "
        f"docs={len(docs)} models={len(blinded.model_rows)} svgs={svg_count} "
        "social=checked scope=checked judge=gpt-5.6-sol-medium dual_order=checked "
        "absolute=157x2 common_pairs=15 terra_audit=checked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
