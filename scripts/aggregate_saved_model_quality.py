#!/usr/bin/env python3
"""Aggregate two saved quality-judge orders without calling a model."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_instruction_evals as evals


VERDICTS = {"baseline", "current", "tie", "inconclusive"}
SOURCES = {"hard_gate", "llm_judge"}
MODEL_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")


def _require_score(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise evals.ValidationError(f"{field} must be an integer from 0 to 100")
    return value


def _orientation(
    report: dict[str, Any], *, baseline_label: str, current_label: str
) -> str:
    labels = (report.get("baseline_label"), report.get("candidate_label"))
    if labels == (baseline_label, current_label):
        return "baseline_first"
    if labels == (current_label, baseline_label):
        return "current_first"
    raise evals.ValidationError(
        "quality order labels must be exact reversed baseline/current pairs"
    )


def _raw_aggregate(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    winners = {"baseline": 0, "current": 0, "tie": 0, "inconclusive": 0}
    sources: dict[str, int] = {}
    confidence: dict[str, int] = {}
    baseline_scores: list[int] = []
    current_scores: list[int] = []
    for item in comparisons:
        quality = item.get("quality")
        if not isinstance(quality, dict):
            raise evals.ValidationError("quality comparison is missing judgment")
        winner = quality.get("winner")
        source = quality.get("source")
        conf = quality.get("confidence")
        if winner not in winners or source not in SOURCES or conf not in evals.QUALITY_CONFIDENCE:
            raise evals.ValidationError("quality comparison has invalid aggregate fields")
        winners[winner] += 1
        sources[source] = sources.get(source, 0) + 1
        confidence[conf] = confidence.get(conf, 0) + 1
        baseline_scores.append(_require_score(quality.get("baseline_score"), "baseline_score"))
        current_scores.append(_require_score(quality.get("current_score"), "current_score"))
    if not comparisons:
        average_baseline = 0.0
        average_current = 0.0
    else:
        average_baseline = round(sum(baseline_scores) / len(baseline_scores), 1)
        average_current = round(sum(current_scores) / len(current_scores), 1)
    return {
        "total": len(comparisons),
        "baseline_passed": sum(
            1 for item in comparisons if item.get("baseline", {}).get("passed") is True
        ),
        "candidate_passed": sum(
            1 for item in comparisons if item.get("candidate", {}).get("passed") is True
        ),
        "winners": winners,
        "sources": sources,
        "confidence": confidence,
        "average_baseline_score": average_baseline,
        "average_current_score": average_current,
        "average_delta": round(average_current - average_baseline, 1),
    }


def _validate_report_aggregate(report: dict[str, Any]) -> None:
    comparisons = report.get("comparisons")
    if not isinstance(comparisons, list):
        raise evals.ValidationError("quality comparisons must be an array")
    if report.get("aggregate") != _raw_aggregate(comparisons):
        raise evals.ValidationError("quality aggregate does not match comparisons")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise evals.ValidationError(f"cannot read JSON artifact {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise evals.ValidationError(f"{path}: expected a JSON object")
    return parsed


def _quality_pointer_matches_checkout(
    pointer: Path,
    *,
    summary_dir: Path,
    expected_quality: Path,
    repo_root: Path,
) -> bool:
    resolved_pointer = pointer.resolve() if pointer.is_absolute() else (summary_dir / pointer).resolve()
    if resolved_pointer == expected_quality:
        return True
    if not pointer.is_absolute():
        return False
    try:
        expected_relative = expected_quality.relative_to(repo_root.resolve())
    except ValueError:
        return False
    expected_parts = expected_relative.parts
    return (
        len(pointer.parts) >= len(expected_parts)
        and pointer.parts[-len(expected_parts) :] == expected_parts
    )


def _resolve_path(path: Path, repo_root: Path) -> Path:
    resolved = path if path.is_absolute() else repo_root / path
    return resolved.resolve()


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise evals.ValidationError(f"artifact path is outside repo root: {path}") from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_source_summary(
    path: Path, *, repo_root: Path, expected_label: str
) -> tuple[dict[str, dict[str, Any]], Path]:
    resolved = _resolve_path(path, repo_root)
    parsed = _read_json(resolved)
    results = parsed.get("results")
    if parsed.get("label") != expected_label or not isinstance(results, list):
        raise evals.ValidationError(f"{resolved}: invalid source summary label/results")
    records: dict[str, dict[str, Any]] = {}
    for raw in results:
        if not isinstance(raw, dict):
            raise evals.ValidationError(f"{resolved}: invalid source result")
        case_id = raw.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in records:
            raise evals.ValidationError(f"{resolved}: invalid or duplicate case_id")
        if raw.get("label") != expected_label or not isinstance(raw.get("passed"), bool):
            raise evals.ValidationError(f"{resolved}: invalid source result label/pass state")
        records[case_id] = evals.quality_metrics(raw)
    passed = sum(record["passed"] for record in records.values())
    if (
        parsed.get("total") != len(records)
        or parsed.get("passed") != passed
        or parsed.get("failed") != len(records) - passed
    ):
        raise evals.ValidationError(f"{resolved}: source summary counters are stale")
    return records, resolved


def load_order_reports(
    paths: list[Path],
    *,
    repo_root: Path,
    baseline_label: str,
    current_label: str,
) -> dict[str, dict[str, Any]]:
    if len(paths) != 2:
        raise evals.ValidationError("exactly two order summaries are required")
    reports: dict[str, dict[str, Any]] = {}
    for path in paths:
        summary_path = _resolve_path(path, repo_root)
        wrapper = _read_json(summary_path)
        pairs = wrapper.get("pairs")
        if not isinstance(pairs, list) or len(pairs) != 1 or not isinstance(pairs[0], dict):
            raise evals.ValidationError(f"{summary_path}: expected exactly one quality pair")
        pair = pairs[0]
        baseline = wrapper.get("baseline_label")
        candidate = pair.get("candidate_label")
        orientation_probe = {"baseline_label": baseline, "candidate_label": candidate}
        orientation = _orientation(
            orientation_probe,
            baseline_label=baseline_label,
            current_label=current_label,
        )
        if orientation in reports:
            raise evals.ValidationError("quality order orientations must be unique")
        expected_quality = (
            summary_path.parent
            / "pairs"
            / evals.safe_label(str(candidate))
            / "quality.json"
        ).resolve()
        pointer = pair.get("quality_json")
        if not isinstance(pointer, str) or not pointer.strip():
            raise evals.ValidationError(f"{summary_path}: invalid quality_json pointer")
        pointer_path = Path(pointer)
        if not _quality_pointer_matches_checkout(
            pointer_path,
            summary_dir=summary_path.parent,
            expected_quality=expected_quality,
            repo_root=repo_root,
        ):
            raise evals.ValidationError(
                f"{summary_path}: quality_json must point to the expected sibling artifact"
            )
        quality = _read_json(expected_quality)
        if (
            quality.get("baseline_label") != baseline
            or quality.get("candidate_label") != candidate
            or wrapper.get("judge") != pair.get("judge")
            or wrapper.get("judge") != quality.get("judge")
            or pair.get("aggregate") != quality.get("aggregate")
        ):
            raise evals.ValidationError(f"{summary_path}: wrapper and quality artifact disagree")
        _validate_report_aggregate(quality)
        loaded = dict(quality)
        loaded["_summary_path"] = summary_path
        loaded["_quality_path"] = expected_quality
        reports[orientation] = loaded
    if set(reports) != {"baseline_first", "current_first"}:
        raise evals.ValidationError("quality orders must be exact reversals")
    return reports


def normalize_order_comparison(
    report: dict[str, Any],
    item: dict[str, Any],
    *,
    baseline_label: str,
    current_label: str,
) -> dict[str, Any]:
    orientation = _orientation(
        report, baseline_label=baseline_label, current_label=current_label
    )
    case_id = item.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise evals.ValidationError("quality comparison case_id must be non-empty")

    raw_baseline = item.get("baseline")
    raw_candidate = item.get("candidate")
    quality = item.get("quality")
    if not all(isinstance(value, dict) for value in (raw_baseline, raw_candidate, quality)):
        raise evals.ValidationError(f"{case_id}: invalid quality comparison")
    expected_labels = (
        report["baseline_label"],
        report["candidate_label"],
    )
    if (raw_baseline.get("label"), raw_candidate.get("label")) != expected_labels:
        raise evals.ValidationError(f"{case_id}: comparison labels do not match order")
    if not isinstance(raw_baseline.get("passed"), bool) or not isinstance(
        raw_candidate.get("passed"), bool
    ):
        raise evals.ValidationError(f"{case_id}: passed must be boolean")

    winner = quality.get("winner")
    if winner not in VERDICTS:
        raise evals.ValidationError(f"{case_id}: invalid quality winner")
    source = quality.get("source")
    if source not in SOURCES:
        raise evals.ValidationError(f"{case_id}: invalid quality source")
    raw_baseline_score = _require_score(
        quality.get("baseline_score"), f"{case_id}: baseline_score"
    )
    raw_current_score = _require_score(
        quality.get("current_score"), f"{case_id}: current_score"
    )
    raw_delta = quality.get("delta")
    if isinstance(raw_delta, bool) or not isinstance(raw_delta, int):
        raise evals.ValidationError(f"{case_id}: delta must be an integer")
    if raw_delta != raw_current_score - raw_baseline_score:
        raise evals.ValidationError(f"{case_id}: delta does not match scores")
    confidence = quality.get("confidence")
    if confidence not in evals.QUALITY_CONFIDENCE:
        raise evals.ValidationError(f"{case_id}: invalid confidence")
    if not isinstance(quality.get("review_needed"), bool):
        raise evals.ValidationError(f"{case_id}: review_needed must be boolean")
    if not isinstance(quality.get("reason"), str) or not quality["reason"].strip():
        raise evals.ValidationError(f"{case_id}: reason must be non-empty")
    if not isinstance(quality.get("checks"), list):
        raise evals.ValidationError(f"{case_id}: checks must be an array")
    if source == "llm_judge":
        evals.validate_quality_judge_response(
            {
                key: quality[key]
                for key in (
                    "winner",
                    "baseline_score",
                    "current_score",
                    "confidence",
                    "reason",
                    "checks",
                )
            }
        )

    if orientation == "baseline_first":
        baseline_record = raw_baseline
        current_record = raw_candidate
        semantic_winner = winner
        baseline_score = raw_baseline_score
        current_score = raw_current_score
    else:
        baseline_record = raw_candidate
        current_record = raw_baseline
        semantic_winner = {"baseline": "current", "current": "baseline"}.get(
            winner, winner
        )
        baseline_score = raw_current_score
        current_score = raw_baseline_score

    return {
        "case_id": case_id,
        "baseline_passed": baseline_record["passed"],
        "current_passed": current_record["passed"],
        "source": source,
        "winner": semantic_winner,
        "baseline_score": baseline_score,
        "current_score": current_score,
        "delta": current_score - baseline_score,
    }


def _score_summary(items: list[dict[str, Any]]) -> dict[str, int | float | None]:
    if not items:
        return {"cases": 0, "baseline": None, "current": None, "delta": None}
    baseline = round(
        sum(item["baseline_score"] for item in items) / len(items), 2
    )
    current = round(
        sum(item["current_score"] for item in items) / len(items), 2
    )
    return {
        "cases": len(items) // 2,
        "baseline": baseline,
        "current": current,
        "delta": round(current - baseline, 2),
    }


def _validate_gate(item: dict[str, Any]) -> None:
    baseline_passed = item["baseline_passed"]
    current_passed = item["current_passed"]
    if baseline_passed and current_passed:
        raise evals.ValidationError(
            f"{item['case_id']}: pass/pass comparison must use llm_judge"
        )
    if baseline_passed:
        expected = ("baseline", 100, 0, -100)
    elif current_passed:
        expected = ("current", 0, 100, 100)
    else:
        expected = ("inconclusive", 0, 0, 0)
    actual = (
        item["winner"],
        item["baseline_score"],
        item["current_score"],
        item["delta"],
    )
    if actual != expected:
        raise evals.ValidationError(
            f"{item['case_id']}: hard-gate judgment disagrees with pass states"
        )


def aggregate_dual_order(
    reports: list[dict[str, Any]],
    *,
    baseline_label: str,
    current_label: str,
    baseline_source_records: dict[str, dict[str, Any]] | None = None,
    current_source_records: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if len(reports) != 2:
        raise evals.ValidationError("exactly two quality orders are required")
    by_orientation: dict[str, dict[str, Any]] = {}
    normalized: dict[str, dict[str, dict[str, Any]]] = {}
    semantic_records: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    judge: dict[str, Any] | None = None
    for report in reports:
        _validate_report_aggregate(report)
        report_judge = report.get("judge")
        if not isinstance(report_judge, dict):
            raise evals.ValidationError("quality report judge must be an object")
        if judge is None:
            judge = report_judge
        elif report_judge != judge:
            raise evals.ValidationError("quality orders use different judges")
        orientation = _orientation(
            report, baseline_label=baseline_label, current_label=current_label
        )
        if orientation in by_orientation:
            raise evals.ValidationError("quality orders must have reversed orientations")
        by_orientation[orientation] = report
        comparisons = report.get("comparisons")
        if not isinstance(comparisons, list):
            raise evals.ValidationError("quality comparisons must be an array")
        by_case: dict[str, dict[str, Any]] = {}
        records_by_case: dict[str, dict[str, dict[str, Any]]] = {}
        for raw_item in comparisons:
            if not isinstance(raw_item, dict):
                raise evals.ValidationError("quality comparison must be an object")
            item = normalize_order_comparison(
                report,
                raw_item,
                baseline_label=baseline_label,
                current_label=current_label,
            )
            if item["case_id"] in by_case:
                raise evals.ValidationError(
                    f"duplicate quality case_id: {item['case_id']}"
                )
            by_case[item["case_id"]] = item
            if orientation == "baseline_first":
                baseline_record = raw_item["baseline"]
                current_record = raw_item["candidate"]
            else:
                baseline_record = raw_item["candidate"]
                current_record = raw_item["baseline"]
            records_by_case[item["case_id"]] = {
                "baseline": baseline_record,
                "current": current_record,
            }
        normalized[orientation] = by_case
        semantic_records[orientation] = records_by_case

    first_ids = set(normalized["baseline_first"])
    second_ids = set(normalized["current_first"])
    if first_ids != second_ids:
        raise evals.ValidationError("quality order case sets do not match")
    for case_id in first_ids:
        if (
            semantic_records["baseline_first"][case_id]
            != semantic_records["current_first"][case_id]
        ):
            raise evals.ValidationError(
                f"{case_id}: quality orders contain different reduced records"
            )
    for label, records, key in (
        (baseline_label, baseline_source_records, "baseline"),
        (current_label, current_source_records, "current"),
    ):
        if records is None:
            continue
        if set(records) != first_ids:
            raise evals.ValidationError(f"{label}: source summary case set does not match")
        for case_id in first_ids:
            if records[case_id] != semantic_records["baseline_first"][case_id][key]:
                raise evals.ValidationError(
                    f"{case_id}: {label} source summary does not match quality input"
                )

    winners = {
        "baseline": 0,
        "current": 0,
        "tie": 0,
        "inconclusive": 0,
        "order_sensitive": 0,
    }
    sources = {"hard_gate": 0, "llm_judge": 0}
    comparisons: list[dict[str, Any]] = []
    all_score_items: list[dict[str, Any]] = []
    llm_score_items: list[dict[str, Any]] = []
    for case_id in sorted(first_ids):
        baseline_first = normalized["baseline_first"][case_id]
        current_first = normalized["current_first"][case_id]
        if (
            baseline_first["baseline_passed"],
            baseline_first["current_passed"],
            baseline_first["source"],
        ) != (
            current_first["baseline_passed"],
            current_first["current_passed"],
            current_first["source"],
        ):
            raise evals.ValidationError(f"{case_id}: quality orders disagree on source data")
        source = baseline_first["source"]
        if source == "hard_gate":
            _validate_gate(baseline_first)
            _validate_gate(current_first)
            if baseline_first != current_first:
                raise evals.ValidationError(
                    f"{case_id}: hard-gate orders must be identical after normalization"
                )
        elif not (
            baseline_first["baseline_passed"]
            and baseline_first["current_passed"]
        ):
            raise evals.ValidationError(
                f"{case_id}: llm_judge requires both arms to pass"
            )

        verdicts = (baseline_first["winner"], current_first["winner"])
        consensus = verdicts[0] if verdicts[0] == verdicts[1] else "order_sensitive"
        winners[consensus] += 1
        sources[source] += 1
        order_items = [baseline_first, current_first]
        all_score_items.extend(order_items)
        if source == "llm_judge":
            llm_score_items.extend(order_items)
        balanced_baseline = round(
            sum(item["baseline_score"] for item in order_items) / 2, 2
        )
        balanced_current = round(
            sum(item["current_score"] for item in order_items) / 2, 2
        )
        comparisons.append(
            {
                "case_id": case_id,
                "baseline_passed": baseline_first["baseline_passed"],
                "current_passed": baseline_first["current_passed"],
                "source": source,
                "orders": {
                    "baseline_first": {
                        key: baseline_first[key]
                        for key in ("winner", "baseline_score", "current_score", "delta")
                    },
                    "current_first": {
                        key: current_first[key]
                        for key in ("winner", "baseline_score", "current_score", "delta")
                    },
                },
                "winner": consensus,
                "balanced_scores": {
                    "baseline": balanced_baseline,
                    "current": balanced_current,
                    "delta": round(balanced_current - balanced_baseline, 2),
                },
            }
        )

    baseline_passed = sum(item["baseline_passed"] for item in comparisons)
    current_passed = sum(item["current_passed"] for item in comparisons)
    return {
        "baseline_label": baseline_label,
        "current_label": current_label,
        "judge": judge,
        "aggregate": {
            "total": len(comparisons),
            "baseline_passed": baseline_passed,
            "current_passed": current_passed,
            "sources": sources,
            "winners": winners,
            "scores": {
                "all_cases": _score_summary(all_score_items),
                "llm_judge": _score_summary(llm_score_items),
            },
        },
        "comparisons": comparisons,
    }


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _summary_markdown(payload: dict[str, Any]) -> str:
    aggregate = payload["aggregate"]
    winners = aggregate["winners"]
    scores = aggregate["scores"]
    lines = [
        f"# Dual-Order Quality: {payload['model_label']}",
        "",
        "Consensus requires the same semantic verdict in both presentation orders; disagreements are `order_sensitive`.",
        "",
        "| Baseline passed | Current passed | Hard gate | LLM judge | Baseline | Current | Tie | Inconclusive | Order-sensitive |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| "
        + " | ".join(
            str(value)
            for value in (
                aggregate["baseline_passed"],
                aggregate["current_passed"],
                aggregate["sources"]["hard_gate"],
                aggregate["sources"]["llm_judge"],
                winners["baseline"],
                winners["current"],
                winners["tie"],
                winners["inconclusive"],
                winners["order_sensitive"],
            )
        )
        + " |",
        "",
        "| Score scope | Cases | Baseline | Current | Delta |",
        "|---|---:|---:|---:|---:|",
    ]
    for scope in ("all_cases", "llm_judge"):
        item = scores[scope]
        lines.append(
            f"| {scope} | {item['cases']} | {item['baseline']} | {item['current']} | {item['delta']} |"
        )
    lines.extend(
        [
            "",
            "`all_cases` is a composite that includes deterministic 0/100 hard-gate sentinels; it is not judge-only quality.",
            "",
        ]
    )
    return "\n".join(lines)


def _quality_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Dual-Order Quality Cases: {payload['model_label']}",
        "",
        "| Case | Source | Baseline pass | Current pass | Baseline-first winner | Current-first winner | Consensus | Baseline-first delta | Current-first delta | Balanced delta |",
        "|---|---|---:|---:|---|---|---|---:|---:|---:|",
    ]
    for item in payload["comparisons"]:
        baseline_first = item["orders"]["baseline_first"]
        current_first = item["orders"]["current_first"]
        lines.append(
            "| "
            + " | ".join(
                [
                    evals.markdown_escape(item["case_id"]),
                    item["source"],
                    str(item["baseline_passed"]),
                    str(item["current_passed"]),
                    baseline_first["winner"],
                    current_first["winner"],
                    item["winner"],
                    str(baseline_first["delta"]),
                    str(current_first["delta"]),
                    str(item["balanced_scores"]["delta"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate two saved quality orders without model calls."
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-label", required=True)
    parser.add_argument("--baseline-label", default="empty")
    parser.add_argument("--current-label", default="current")
    parser.add_argument("--baseline-source-summary", required=True)
    parser.add_argument("--current-source-summary", required=True)
    parser.add_argument("--order-summary", action="append", required=True)
    parser.add_argument("--output-root", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repo_root = Path(args.repo_root).resolve()
        if (
            MODEL_ID_PATTERN.fullmatch(args.model_id) is None
            or not args.model_label.strip()
            or not args.baseline_label.strip()
            or not args.current_label.strip()
            or args.baseline_label == args.current_label
        ):
            raise evals.ValidationError("invalid model or semantic labels")
        baseline_records, baseline_source_path = load_source_summary(
            Path(args.baseline_source_summary),
            repo_root=repo_root,
            expected_label=args.baseline_label,
        )
        current_records, current_source_path = load_source_summary(
            Path(args.current_source_summary),
            repo_root=repo_root,
            expected_label=args.current_label,
        )
        reports = load_order_reports(
            [Path(value) for value in args.order_summary],
            repo_root=repo_root,
            baseline_label=args.baseline_label,
            current_label=args.current_label,
        )
        aggregate = aggregate_dual_order(
            [reports["baseline_first"], reports["current_first"]],
            baseline_label=args.baseline_label,
            current_label=args.current_label,
            baseline_source_records=baseline_records,
            current_source_records=current_records,
        )
        inputs = {
            "source_summaries": {
                "baseline": {
                    "path": _repo_relative(baseline_source_path, repo_root),
                    "sha256": _sha256(baseline_source_path),
                },
                "current": {
                    "path": _repo_relative(current_source_path, repo_root),
                    "sha256": _sha256(current_source_path),
                },
            },
            "orders": {},
        }
        for orientation in ("baseline_first", "current_first"):
            report = reports[orientation]
            summary_path = report["_summary_path"]
            quality_path = report["_quality_path"]
            inputs["orders"][orientation] = {
                "summary_path": _repo_relative(summary_path, repo_root),
                "summary_sha256": _sha256(summary_path),
                "quality_path": _repo_relative(quality_path, repo_root),
                "quality_sha256": _sha256(quality_path),
            }

        common = {
            "schema_version": 1,
            "aggregation": "dual_order_consensus",
            "model_id": args.model_id,
            "model_label": args.model_label,
            "baseline_label": args.baseline_label,
            "current_label": args.current_label,
            "judge": aggregate["judge"],
            "aggregate": aggregate["aggregate"],
        }
        summary = {**common, "quality_json": "dual-order-quality.json"}
        quality = {
            **{key: common[key] for key in common if key != "aggregate"},
            "inputs": inputs,
            "aggregate": common["aggregate"],
            "comparisons": aggregate["comparisons"],
        }
        output_root = _resolve_path(Path(args.output_root), repo_root)
        output_dir = output_root / args.model_id
        outputs = {
            output_dir / "dual-order-summary.json": _json_text(summary),
            output_dir / "dual-order-quality.json": _json_text(quality),
            output_dir / "dual-order-summary.md": _summary_markdown(summary),
            output_dir / "dual-order-quality.md": _quality_markdown(quality),
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        for path, content in outputs.items():
            path.write_text(content, encoding="utf-8")
        print(f"dual_order_summary={output_dir / 'dual-order-summary.json'}")
        return 0
    except (evals.ValidationError, OSError) as exc:
        print(f"dual-order aggregation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
