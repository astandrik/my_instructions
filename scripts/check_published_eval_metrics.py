#!/usr/bin/env python3
"""Check published 50-case eval metrics, docs caveats, README SVG scope, and social PNG metadata."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CASE_FILE = Path("evals/cases.jsonl")
PUBLIC_ROOT = Path(".eval-results/refresh-2026-07-08-50-case-public-v1")
PROVIDER_ROOT_V1 = Path(".eval-results/refresh-2026-07-08-50-case-v1")
PROVIDER_ROOT_V2 = Path(".eval-results/refresh-2026-07-08-50-case-v2")
QUALITY_ROOT = Path(".eval-results/refresh-2026-07-08-50-case-quality-v1")
DEFAULT_DOCS = [
    Path("README.md"),
    Path("evals/RESULTS.md"),
    Path("evals/PROMPT_QUALITY_CASES.md"),
    Path("evals/CHANGELOG.md"),
]
DEFAULT_SVG_DIR = Path("docs/assets/readme")
DEFAULT_SOCIAL_IMAGE = Path("docs/assets/social/instruction-quality-lift-linkedin.png")
EXPECTED_SVG_SCOPE = (
    "Scope: 50-case saved hard-gate and quality snapshot; "
    "all-model reference rows included."
)
EXPECTED_SOCIAL_PNG_METADATA = {
    "instruction_snapshot_cases": "50",
    "instruction_snapshot_scope": EXPECTED_SVG_SCOPE,
    "instruction_snapshot_quality_root": str(QUALITY_ROOT),
    "generated_by": "scripts/build_readme_infographics.py",
}
REQUIRED_README_SVGS = [
    "case-detail-comparisons.svg",
    "coverage-watchlist.svg",
    "empty-current-lift.svg",
    "hard-gates-50.svg",
    "instruction-lift.svg",
    "model-gap.svg",
    "model-transfer.svg",
    "quality-only-case-matrix.svg",
    "quality-only-comparisons.svg",
    "reference-prompts.svg",
]
README_SVG_PREFIX = "docs/assets/readme/"

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
                "current_passed": current["passed"],
                "empty_passed": empty["passed"],
                "total": current["total"],
                "quality_delta": aggregate["average_delta"],
                "current_wins": winners["current"],
                "baseline_wins": winners["baseline"],
                "ties": winners["tie"],
                "inconclusive": winners.get("inconclusive", 0),
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
            "50-case saved quality snapshot",
            f"GPT/Codex passed {gpt['current_passed']}/{gpt['total']} current and {gpt['empty_passed']}/{gpt['total']} empty",
            f"GLM-5.2 reached {glm['current_passed']}/{glm['total']} current",
            positive_quality_text,
            "all-model reference rows are now included",
            ".eval-results/refresh-2026-07-08-50-case-quality-v1/",
        ],
        "evals/RESULTS.md": [
            "## 50-Case Refresh Snapshot",
            f"| GPT-5.5 via Codex CLI | {gpt['current_passed']} / {gpt['total']} | {gpt['empty_passed']} / {gpt['total']} | +{gpt['current_passed'] - gpt['empty_passed']} |",
            f"| GLM-5.2 via Z.ai adapter | {glm['current_passed']} / {glm['total']} | {glm['empty_passed']} / {glm['total']} | +{glm['current_passed'] - glm['empty_passed']} |",
            f"| Grok 4.3 via xAI adapter | {grok['current_passed']} / {grok['total']} | {grok['empty_passed']} / {grok['total']} | +{grok['current_passed'] - grok['empty_passed']} |",
            f"| Grok Build 0.1 via xAI adapter | {grok_build['current_passed']} / {grok_build['total']} | {grok_build['empty_passed']} / {grok_build['total']} | +{grok_build['current_passed'] - grok_build['empty_passed']} |",
            f"| DeepSeek V4 Flash via DeepSeek adapter | {deepseek['current_passed']} / {deepseek['total']} | {deepseek['empty_passed']} / {deepseek['total']} | +{deepseek['current_passed'] - deepseek['empty_passed']} |",
            f"| DeepSeek V4 Flash thinking mode | {deepseek_thinking['current_passed']} / {deepseek_thinking['total']} | {deepseek_thinking['empty_passed']} / {deepseek_thinking['total']} | +{deepseek_thinking['current_passed'] - deepseek_thinking['empty_passed']} |",
            "### All-Model Reference Prompt Quality",
            reference_doc_row(openhands_gpt, "OpenHands"),
            reference_doc_row(openhands_glm, "OpenHands"),
            reference_doc_row(fable_gpt, "Claude/Fable"),
            reference_doc_row(fable_glm, "Claude/Fable"),
        ],
        "evals/PROMPT_QUALITY_CASES.md": [
            "2026-07-08 50-case all-model reference comparisons",
            "quality-reference-openhands-vs-current-all-models-full-v1",
            "quality-reference-claude-fable-vs-current-all-models-full-v1",
            f"| OpenHands `AGENTS.md` | GPT-5.5-current | {openhands_gpt['current_passed']} / {openhands_gpt['total']} | {openhands_gpt['reference_passed']} / {openhands_gpt['total']} | current {openhands_gpt['current_wins']}, OpenHands {openhands_gpt['reference_wins']}, tie {openhands_gpt['ties']}, inconclusive {openhands_gpt['inconclusive']} |",
            f"| Claude/Fable prompt | GPT-5.5-current | {fable_gpt['current_passed']} / {fable_gpt['total']} | {fable_gpt['reference_passed']} / {fable_gpt['total']} | current {fable_gpt['current_wins']}, Fable {fable_gpt['reference_wins']}, tie {fable_gpt['ties']}, inconclusive {fable_gpt['inconclusive']} |",
            "`agent-data-injection-trusted-metadata`",
        ],
        "evals/CHANGELOG.md": [
            "50-case saved-output quality refresh",
            f"GPT/Codex `{gpt['current_passed']}/{gpt['total']}` current and `{gpt['empty_passed']}/{gpt['total']}` empty",
            positive_quality_text,
            "all-model reference rows are now included",
        ],
    }


def doc_expectation_key(path: Path, snippets: dict[str, list[str]]) -> str | None:
    raw = path.as_posix()
    for key in snippets:
        if raw == key or raw.endswith(f"/{key}"):
            return key
    return None


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
        for claim in forbidden_publication_overclaims(raw_text):
            problems.append(f"{path}: forbidden 50-case publication overclaim/stale caveat: {claim}")
        if key == "README.md":
            for name in missing_readme_svg_references(raw_text):
                problems.append(f"{path}: missing README SVG reference: {README_SVG_PREFIX}{name}")
    return problems


def check_svg_scope(svg_dir: Path, required_names: list[str] | None = None) -> list[str]:
    if not svg_dir.exists():
        return [f"missing SVG directory: {svg_dir}"]
    svg_files = sorted(svg_dir.glob("*.svg"))
    if not svg_files:
        return [f"no SVG files found in: {svg_dir}"]
    problems = []
    svg_by_name = {path.name: path for path in svg_files}
    for name in sorted(required_names or REQUIRED_README_SVGS):
        if name not in svg_by_name:
            problems.append(f"{svg_dir / name}: missing required README SVG")
    for path in svg_files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(f"{path}: failed to read SVG: {exc}")
            continue
        if EXPECTED_SVG_SCOPE not in text:
            problems.append(f"{path}: missing SVG scope footer: {EXPECTED_SVG_SCOPE}")
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
        help="Documentation file to check. Defaults to README, RESULTS, PROMPT_QUALITY_CASES, and CHANGELOG.",
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
    except ValueError as exc:
        print(f"published eval metric check failed: {exc}", file=sys.stderr)
        return 2

    svg_dir = Path(args.svg_dir)
    social_image = Path(args.social_image)
    problems = check_docs(snapshot, docs)
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
        f"docs={len(docs)} svgs={svg_count} social=checked scope=checked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
