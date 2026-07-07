#!/usr/bin/env python3
"""Check published GPT/Codex eval metrics, docs caveats, and README SVG scope."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SUMMARY = Path(".eval-results/v4.13-final-gpt55-full-49-v11/compare-HEAD-current/summary.json")
DEFAULT_QUALITY = Path(".eval-results/v4.13-final-gpt55-full-49-v11/compare-HEAD-current/quality.json")
DEFAULT_DOCS = [Path("README.md"), Path("evals/RESULTS.md"), Path("evals/CHANGELOG.md")]
DEFAULT_SVG_DIR = Path("docs/assets/readme")
EXPECTED_SVG_SCOPE = "Scope: v4.12 all-model snapshot. v4.13 is GPT/Codex-only until external providers rerun."
REQUIRED_README_SVGS = [
    "case-detail-comparisons.svg",
    "coverage-watchlist.svg",
    "empty-current-lift.svg",
    "instruction-lift.svg",
    "model-transfer.svg",
    "quality-only-case-matrix.svg",
    "quality-only-comparisons.svg",
    "reference-prompts.svg",
]
FORBIDDEN_SCOPE_OVERCLAIMS = [
    "v4.13 all-model refresh",
    "v4.13 all-model evidence",
    "v4.13 all-model comparison",
    "all-model v4.13 refresh",
    "all-model v4.13 evidence",
    "all-model v4.13 comparison",
    "fresh all-model v4.13 refresh",
    "fresh all-model v4.13 evidence",
    "external model rows were rerun after v4.13",
    "external provider rows were rerun after v4.13",
]
FORBIDDEN_SCOPE_OVERCLAIM_PATTERNS = [
    re.compile(r"\bv4\.13 all[- ]models? (?:refresh|evidence|comparison)\b"),
    re.compile(r"\ball[- ]models? v4\.13 (?:refresh|evidence|comparison)\b"),
    re.compile(r"\bv4\.13 (?:refresh|evidence|comparison) across all[- ]models?\b"),
    re.compile(r"\bexternal (?:model|provider) rows were re[- ]?run after v4\.13\b"),
]
EXPECTED_SUMMARY_LABELS = {"baseline-HEAD", "current"}
README_SVG_PREFIX = "docs/assets/readme/"


@dataclass(frozen=True)
class PublishedMetrics:
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


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing artifact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def require_list(value: Any, path: Path, key: str) -> list[Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected object")
    items = value.get(key)
    if not isinstance(items, list):
        raise ValueError(f"{path}: expected list field {key!r}")
    return items


def summarize_artifacts(summary: dict[str, Any], quality: dict[str, Any], *, summary_path: Path, quality_path: Path) -> PublishedMetrics:
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

    label_passes = {"baseline-HEAD": 0, "current": 0}
    labels_by_case: dict[str, set[str]] = {}
    for record in results:
        if not isinstance(record, dict):
            raise ValueError(f"{summary_path}: summary result must be an object")
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"{summary_path}: summary result requires non-empty case_id")
        label = record.get("label")
        if label not in EXPECTED_SUMMARY_LABELS:
            raise ValueError(f"{summary_path}: unexpected summary label {label!r} for case_id {case_id!r}")
        case_labels = labels_by_case.setdefault(case_id, set())
        if label in case_labels:
            raise ValueError(f"{summary_path}: duplicate summary label {label!r} for case_id {case_id!r}")
        case_labels.add(label)
        if label in label_passes and record.get("passed") is True:
            label_passes[label] += 1

    winners = {"current": 0, "baseline": 0, "tie": 0, "inconclusive": 0}
    deltas: list[float] = []
    quality_case_ids: set[str] = set()
    for item in comparisons:
        if not isinstance(item, dict):
            raise ValueError(f"{quality_path}: comparison must be an object")
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"{quality_path}: comparison requires non-empty case_id")
        if case_id in quality_case_ids:
            raise ValueError(f"{quality_path}: duplicate comparison case_id {case_id!r}")
        quality_case_ids.add(case_id)
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
    for case_id, labels in sorted(labels_by_case.items()):
        if labels != EXPECTED_SUMMARY_LABELS:
            missing = ", ".join(sorted(EXPECTED_SUMMARY_LABELS - labels))
            raise ValueError(f"{summary_path}: case_id {case_id!r} missing summary label(s): {missing}")
    summary_case_ids = set(labels_by_case)
    if summary_case_ids != quality_case_ids:
        only_summary = ", ".join(sorted(summary_case_ids - quality_case_ids))
        only_quality = ", ".join(sorted(quality_case_ids - summary_case_ids))
        details = []
        if only_summary:
            details.append(f"only in summary: {only_summary}")
        if only_quality:
            details.append(f"only in quality: {only_quality}")
        raise ValueError(f"{summary_path} / {quality_path}: case_id mismatch ({'; '.join(details)})")

    return PublishedMetrics(
        summary_passed=summary_passed,
        summary_total=summary_total,
        case_count=len(comparisons),
        baseline_passed=label_passes["baseline-HEAD"],
        current_passed=label_passes["current"],
        current_wins=winners["current"],
        baseline_wins=winners["baseline"],
        ties=winners["tie"],
        inconclusive=winners["inconclusive"],
        average_delta=round(sum(deltas) / len(deltas), 2),
    )


def expected_doc_snippets(metrics: PublishedMetrics) -> dict[str, list[str]]:
    return {
        "README.md": [
            f"{metrics.summary_passed}/{metrics.summary_total} hard gates passed",
            (
                f"current winning {metrics.current_wins} quality comparisons, "
                f"baseline winning {metrics.baseline_wins}, {metrics.ties} ties, "
                f"and average delta {metrics.average_delta_text}"
            ),
            "This is GPT-only evidence",
            "external model rows and README infographics below still reflect",
        ],
        "evals/RESULTS.md": [
            "This is a GPT/Codex full-suite result, not an all-model refresh.",
            "External model rows below were not rerun after v4.13 and the phrase-matcher change.",
            f"| Baseline `HEAD` | {metrics.baseline_passed} / {metrics.case_count} | 0 |",
            f"| Current worktree | {metrics.current_passed} / {metrics.case_count} | 0 |",
            (
                f"| {metrics.case_count} pass/pass cases | {metrics.current_wins} | "
                f"{metrics.baseline_wins} | {metrics.ties} | {metrics.average_delta_text} |"
            ),
        ],
        "evals/CHANGELOG.md": [
            "This is not publication-grade all-model evidence yet.",
            "Do not use this entry as all-model README/infographic evidence",
            f"v11 full compare: {metrics.summary_passed} / {metrics.summary_total} hard gates passed",
            (
                f"current {metrics.current_wins} wins, baseline {metrics.baseline_wins} wins, "
                f"{metrics.ties} ties, average delta {metrics.average_delta_text}"
            ),
        ],
    }


def with_trailing_slash(path: Path) -> str:
    return f"{path.as_posix().rstrip('/')}/"


def expected_artifact_snippets(summary_path: Path) -> dict[str, list[str]]:
    compare_root = summary_path.parent
    run_root = compare_root.parent if compare_root.name == "compare-HEAD-current" else compare_root
    return {
        "README.md": [with_trailing_slash(run_root)],
        "evals/RESULTS.md": [with_trailing_slash(compare_root)],
        "evals/CHANGELOG.md": [with_trailing_slash(run_root)],
    }


def doc_expectation_key(path: Path, snippets: dict[str, list[str]]) -> str | None:
    raw = path.as_posix()
    for key in snippets:
        if raw == key or raw.endswith(f"/{key}"):
            return key
    return None


def forbidden_scope_overclaims(text: str) -> list[str]:
    normalized = normalize_text(text).casefold()
    literal_claims = [claim for claim in FORBIDDEN_SCOPE_OVERCLAIMS if claim in normalized]
    pattern_claims = [match.group(0) for pattern in FORBIDDEN_SCOPE_OVERCLAIM_PATTERNS for match in pattern.finditer(normalized)]
    return literal_claims + pattern_claims


def missing_readme_svg_references(text: str, required_names: list[str] | None = None) -> list[str]:
    required = required_names or REQUIRED_README_SVGS
    return [name for name in sorted(required) if f"{README_SVG_PREFIX}{name}" not in text]


def check_docs(
    metrics: PublishedMetrics,
    docs: list[Path],
    artifact_snippets: dict[str, list[str]] | None = None,
) -> list[str]:
    problems = []
    snippets = expected_doc_snippets(metrics)
    if artifact_snippets is not None:
        for key, artifact_expected in artifact_snippets.items():
            snippets.setdefault(key, []).extend(artifact_expected)
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
                problems.append(f"{path}: missing published metric/caveat snippet: {snippet}")
        for claim in forbidden_scope_overclaims(raw_text):
            problems.append(f"{path}: forbidden v4.13 publication overclaim: {claim}")
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
    return problems


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="Saved compare summary.json artifact.")
    parser.add_argument("--quality", default=str(DEFAULT_QUALITY), help="Saved compare quality.json artifact.")
    parser.add_argument(
        "--doc",
        action="append",
        dest="docs",
        help="Documentation file to check. Defaults to README.md, evals/RESULTS.md, and evals/CHANGELOG.md.",
    )
    parser.add_argument("--svg-dir", default=str(DEFAULT_SVG_DIR), help="Directory containing generated README SVGs.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary_path = Path(args.summary)
    quality_path = Path(args.quality)
    docs = [Path(path) for path in (args.docs or [str(path) for path in DEFAULT_DOCS])]
    try:
        metrics = summarize_artifacts(
            read_json(summary_path),
            read_json(quality_path),
            summary_path=summary_path,
            quality_path=quality_path,
        )
    except ValueError as exc:
        print(f"published eval metric check failed: {exc}", file=sys.stderr)
        return 2

    svg_dir = Path(args.svg_dir)
    problems = check_docs(metrics, docs, expected_artifact_snippets(summary_path))
    problems.extend(check_svg_scope(svg_dir))
    if problems:
        print("published eval publication guard failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    svg_count = len(list(svg_dir.glob("*.svg")))
    print(
        "published eval publication guard ok: "
        f"{metrics.summary_passed}/{metrics.summary_total} hard gates, "
        f"quality current={metrics.current_wins} baseline={metrics.baseline_wins} "
        f"ties={metrics.ties} avg_delta={metrics.average_delta_text}, "
        f"docs={len(docs)} svgs={svg_count} scope=checked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
