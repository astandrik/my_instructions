#!/usr/bin/env python3
"""Aggregate independent absolute quality judgments without new model calls."""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_model_absolute_quality as runner


def mean(values: list[int | float]) -> float:
    if not values:
        raise runner.MatrixError("cannot average an empty score set")
    return round(sum(values) / len(values), 2)


def direction(model_a_id: str, score_a: int | float, model_b_id: str, score_b: int | float) -> str:
    if score_a > score_b:
        return model_a_id
    if score_b > score_a:
        return model_b_id
    return "equal"


def load_completed_summaries(
    plan: runner.AbsolutePlan,
) -> dict[str, dict[str, Any]]:
    states = runner.validate_output_state(plan)
    incomplete = [model_id for model_id, state in states.items() if state != "complete"]
    if incomplete:
        raise runner.MatrixError(
            f"incomplete absolute judgments for {plan.judge_name}: {', '.join(incomplete)}"
        )
    summaries: dict[str, dict[str, Any]] = {}
    for job in plan.jobs:
        path = job.output_path / "summary.json"
        runner.validate_model_summary(plan, job, path)
        summaries[job.model_id] = json.loads(path.read_text(encoding="utf-8"))
    return summaries


def aggregate_judge(
    repo_root: Path,
    manifest_path: Path,
    judge_name: str,
    *,
    output_root: Path | None = None,
) -> dict[str, Any]:
    plan = runner.build_plan(
        repo_root,
        manifest_path,
        judge_name,
        output_root=output_root,
    )
    summaries = load_completed_summaries(plan)
    model_rows: list[dict[str, Any]] = []
    scores_by_model: dict[str, dict[str, int]] = {}
    for job in plan.jobs:
        summary = summaries[job.model_id]
        judgments = summary["judgments"]
        scores = {item["case_id"]: item["score"] for item in judgments}
        scores_by_model[job.model_id] = scores
        dimension_scores = {
            check_id: mean(
                [
                    next(check["score"] for check in item["checks"] if check["id"] == check_id)
                    for item in judgments
                ]
            )
            for check_id in runner.evals.QUALITY_CHECK_IDS
        }
        summary_path = job.output_path / "summary.json"
        model_rows.append(
            {
                "model_id": job.model_id,
                "model_label": job.model_label,
                "role": job.role,
                "hard_gate_passed": len(job.case_ids),
                "hard_gate_total": len(plan.cases_by_id),
                "hard_gate_pass_rate": round(len(job.case_ids) / len(plan.cases_by_id), 2),
                "mean_absolute_score": mean(list(scores.values())),
                "dimension_scores": dimension_scores,
                "source": {
                    "path": job.source_path,
                    "sha256": job.source_sha256,
                },
                "judgment_summary": {
                    "path": summary_path.relative_to(plan.repo_root).as_posix(),
                    "sha256": runner.file_sha256(summary_path),
                },
                "case_scores": scores,
            }
        )

    pair_rows: list[dict[str, Any]] = []
    for job_a, job_b in combinations(plan.jobs, 2):
        scores_a = scores_by_model[job_a.model_id]
        scores_b = scores_by_model[job_b.model_id]
        overlap_ids = [case_id for case_id in plan.cases_by_id if case_id in scores_a and case_id in scores_b]
        if not overlap_ids:
            raise runner.MatrixError(f"no passed-case overlap: {job_a.model_id} vs {job_b.model_id}")
        cases = []
        counts = {"a_higher": 0, "equal": 0, "b_higher": 0}
        for case_id in overlap_ids:
            case_direction = direction(
                job_a.model_id,
                scores_a[case_id],
                job_b.model_id,
                scores_b[case_id],
            )
            if case_direction == job_a.model_id:
                counts["a_higher"] += 1
            elif case_direction == job_b.model_id:
                counts["b_higher"] += 1
            else:
                counts["equal"] += 1
            cases.append(
                {
                    "case_id": case_id,
                    "model_a_score": scores_a[case_id],
                    "model_b_score": scores_b[case_id],
                    "direction": case_direction,
                }
            )
        mean_a = mean([scores_a[case_id] for case_id in overlap_ids])
        mean_b = mean([scores_b[case_id] for case_id in overlap_ids])
        pair_rows.append(
            {
                "model_a_id": job_a.model_id,
                "model_b_id": job_b.model_id,
                "overlap": len(overlap_ids),
                "mean_model_a_score": mean_a,
                "mean_model_b_score": mean_b,
                "mean_delta_b_minus_a": round(mean_b - mean_a, 2),
                "direction": direction(job_a.model_id, mean_a, job_b.model_id, mean_b),
                **counts,
                "cases": cases,
            }
        )

    return {
        "version": 1,
        "methodology": "single_response_absolute_scoring",
        "judge": plan.judge_metadata,
        "snapshots": plan.snapshots,
        "total_judgments": sum(row["hard_gate_passed"] for row in model_rows),
        "models": model_rows,
        "common_case_comparisons": pair_rows,
    }


def aggregate_judge_audit(sol: dict[str, Any], terra: dict[str, Any]) -> dict[str, Any]:
    if sol.get("methodology") != "single_response_absolute_scoring" or terra.get("methodology") != sol.get("methodology"):
        raise runner.MatrixError("judge audit methodology mismatch")
    if sol.get("snapshots") != terra.get("snapshots"):
        raise runner.MatrixError("judge audit snapshot mismatch")
    if sol.get("total_judgments") != 157 or terra.get("total_judgments") != 157:
        raise runner.MatrixError("judge audit requires exact 157-record coverage")
    terra_models = {row["model_id"]: row for row in terra["models"]}
    model_rows = []
    for sol_row in sol["models"]:
        terra_row = terra_models.get(sol_row["model_id"])
        if terra_row is None or terra_row["case_scores"].keys() != sol_row["case_scores"].keys():
            raise runner.MatrixError(f"judge audit model coverage mismatch: {sol_row['model_id']}")
        model_rows.append(
            {
                "model_id": sol_row["model_id"],
                "model_label": sol_row["model_label"],
                "role": sol_row["role"],
                "sol_mean_score": sol_row["mean_absolute_score"],
                "terra_mean_score": terra_row["mean_absolute_score"],
                "terra_minus_sol_mean_score": round(
                    terra_row["mean_absolute_score"] - sol_row["mean_absolute_score"], 2
                ),
                "dimension_deltas": {
                    check_id: round(
                        terra_row["dimension_scores"][check_id]
                        - sol_row["dimension_scores"][check_id],
                        2,
                    )
                    for check_id in runner.evals.QUALITY_CHECK_IDS
                },
            }
        )

    terra_pairs = {
        (row["model_a_id"], row["model_b_id"]): row
        for row in terra["common_case_comparisons"]
    }
    pair_rows = []
    for sol_pair in sol["common_case_comparisons"]:
        key = (sol_pair["model_a_id"], sol_pair["model_b_id"])
        terra_pair = terra_pairs.get(key)
        if terra_pair is None or terra_pair["overlap"] != sol_pair["overlap"]:
            raise runner.MatrixError(f"judge audit pair coverage mismatch: {key}")
        sol_cases = {item["case_id"]: item for item in sol_pair["cases"]}
        terra_cases = {item["case_id"]: item for item in terra_pair["cases"]}
        if sol_cases.keys() != terra_cases.keys():
            raise runner.MatrixError(f"judge audit case coverage mismatch: {key}")
        changed = sum(
            sol_cases[case_id]["direction"] != terra_cases[case_id]["direction"]
            for case_id in sol_cases
        )
        pair_rows.append(
            {
                "model_a_id": key[0],
                "model_b_id": key[1],
                "overlap": sol_pair["overlap"],
                "sol_direction": sol_pair["direction"],
                "terra_direction": terra_pair["direction"],
                "sol_mean_delta_b_minus_a": sol_pair["mean_delta_b_minus_a"],
                "terra_mean_delta_b_minus_a": terra_pair["mean_delta_b_minus_a"],
                "changed_case_directions": changed,
                "judge_sensitive": sol_pair["direction"] != terra_pair["direction"],
            }
        )
    return {
        "version": 1,
        "methodology": "single_response_absolute_scoring_judge_audit",
        "snapshots": sol["snapshots"],
        "sol_judge": sol["judge"],
        "terra_judge": terra["judge"],
        "models": model_rows,
        "common_case_comparisons": pair_rows,
    }


def markdown_for_judge(result: dict[str, Any]) -> str:
    lines = [
        f"# Absolute quality — {result['judge']['key']}",
        "",
        "Hard-gate pass rate and quality among passed responses are separate metrics.",
        "",
        "| Model | Role | Hard gate | Mean absolute score |",
        "|---|---:|---:|---:|",
    ]
    for row in result["models"]:
        lines.append(
            f"| {row['model_label']} | {row['role']} | {row['hard_gate_passed']}/{row['hard_gate_total']} | {row['mean_absolute_score']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Common passed-case comparisons",
            "",
            "| Model A | Model B | n | Mean A | Mean B | B-A | A higher | Equal | B higher | Direction |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    labels = {row["model_id"]: row["model_label"] for row in result["models"]}
    for row in result["common_case_comparisons"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    labels[row["model_a_id"]],
                    labels[row["model_b_id"]],
                    str(row["overlap"]),
                    f"{row['mean_model_a_score']:.2f}",
                    f"{row['mean_model_b_score']:.2f}",
                    f"{row['mean_delta_b_minus_a']:.2f}",
                    str(row["a_higher"]),
                    str(row["equal"]),
                    str(row["b_higher"]),
                    row["direction"],
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def markdown_for_audit(result: dict[str, Any]) -> str:
    lines = [
        "# Sol medium vs Terra high absolute-judge audit",
        "",
        "| Model | Sol mean | Terra mean | Terra-Sol |",
        "|---|---:|---:|---:|",
    ]
    for row in result["models"]:
        lines.append(
            f"| {row['model_label']} | {row['sol_mean_score']:.2f} | {row['terra_mean_score']:.2f} | {row['terra_minus_sol_mean_score']:.2f} |"
        )
    lines.extend(
        [
            "",
            "| Model A | Model B | n | Sol direction | Terra direction | Changed cases | Judge-sensitive |",
            "|---|---|---:|---|---|---:|---|",
        ]
    )
    for row in result["common_case_comparisons"]:
        lines.append(
            f"| {row['model_a_id']} | {row['model_b_id']} | {row['overlap']} | {row['sol_direction']} | {row['terra_direction']} | {row['changed_case_directions']} | {'yes' if row['judge_sensitive'] else 'no'} |"
        )
    return "\n".join(lines) + "\n"


def encoded_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_all(
    repo_root: Path,
    manifest_path: Path,
    *,
    output_root: Path,
    canonical_root: Path,
    check: bool,
) -> None:
    sol = aggregate_judge(repo_root, manifest_path, "sol", output_root=output_root)
    terra = aggregate_judge(repo_root, manifest_path, "terra", output_root=output_root)
    audit = aggregate_judge_audit(sol, terra)
    artifacts = {
        "sol-absolute.json": encoded_json(sol),
        "sol-absolute.md": markdown_for_judge(sol).encode("utf-8"),
        "terra-absolute.json": encoded_json(terra),
        "terra-absolute.md": markdown_for_judge(terra).encode("utf-8"),
        "sol-terra-audit.json": encoded_json(audit),
        "sol-terra-audit.md": markdown_for_audit(audit).encode("utf-8"),
    }
    if check:
        for name, expected in artifacts.items():
            path = canonical_root / name
            if not path.is_file() or path.read_bytes() != expected:
                raise runner.MatrixError(f"stale or missing canonical artifact: {path}")
        unexpected = {path.name for path in canonical_root.iterdir()} - set(artifacts)
        if unexpected:
            raise runner.MatrixError(
                f"unexpected canonical artifacts: {', '.join(sorted(unexpected))}"
            )
        return
    canonical_root.mkdir(parents=True, exist_ok=True)
    for name, content in artifacts.items():
        (canonical_root / name).write_bytes(content)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=runner.DEFAULT_MANIFEST)
    parser.add_argument("--output-root", type=Path, default=runner.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--canonical-root", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
    output_root = args.output_root if args.output_root.is_absolute() else repo_root / args.output_root
    canonical_root = args.canonical_root or (output_root / "canonical")
    if not canonical_root.is_absolute():
        canonical_root = repo_root / canonical_root
    try:
        write_all(
            repo_root,
            manifest_path,
            output_root=output_root,
            canonical_root=canonical_root,
            check=args.check,
        )
    except (runner.MatrixError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
