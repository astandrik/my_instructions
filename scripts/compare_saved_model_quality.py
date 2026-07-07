#!/usr/bin/env python3
"""Compare saved model eval artifacts with the existing quality judge.

This does not rerun the evaluated models. It reads saved summary.json files,
uses deterministic hard-gate shortcuts when hard gates differ or both sides
fail, and calls the configured judge only for pass/pass pairs.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_instruction_evals as evals


def parse_label_path(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected LABEL=PATH")
    label, raw_path = value.split("=", 1)
    label = label.strip()
    if not label:
        raise argparse.ArgumentTypeError("label must be non-empty")
    path = Path(raw_path)
    if not raw_path.strip():
        raise argparse.ArgumentTypeError("path must be non-empty")
    return label, path


def read_summary(path: Path, label: str) -> dict[str, dict[str, Any]]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    results = parsed.get("results")
    if not isinstance(results, list):
        raise evals.ValidationError(f"{path}: summary results must be a list")
    by_case: dict[str, dict[str, Any]] = {}
    for record in results:
        if not isinstance(record, dict) or not isinstance(record.get("case_id"), str):
            raise evals.ValidationError(f"{path}: invalid result record")
        case_id = record["case_id"]
        if case_id in by_case:
            raise evals.ValidationError(
                f"{path}: duplicate case_id {case_id!r}; split combined compare summaries "
                "with scripts/split_eval_summary.py before saved-quality comparison"
            )
        copied = dict(record)
        copied["label"] = label
        by_case[case_id] = copied
    return by_case


def require_case_record(records: dict[str, dict[str, Any]], label: str, case_id: str) -> dict[str, Any]:
    try:
        return records[case_id]
    except KeyError as exc:
        raise evals.ValidationError(f"{label}: missing case in summary: {case_id}") from exc


def run_saved_quality_judge(
    case: dict[str, Any],
    *,
    repo_root: Path,
    agent_command: str,
    model: str,
    reasoning_effort: str,
    service_tier: str | None,
    output_dir: Path,
    summary_label: str,
    baseline_label: str,
    baseline_record: dict[str, Any],
    candidate_label: str,
    candidate_record: dict[str, Any],
    agent_command_mode: str,
    case_timeout_seconds: int | None,
) -> dict[str, Any]:
    schema_source = repo_root / evals.QUALITY_JUDGE_SCHEMA
    if not schema_source.exists():
        raise evals.HarnessFailure(f"quality judge schema does not exist: {schema_source}")
    case_output = output_dir / evals.safe_label(summary_label) / "judge" / evals.safe_label(candidate_label) / case["id"]
    output_last_message = case_output / "final-message.json"
    prompt = evals.quality_judge_prompt(case, baseline_label, baseline_record, candidate_label, candidate_record)
    try:
        if output_last_message.exists():
            response = evals.parse_final_response(output_last_message.read_text(encoding="utf-8"))
            try:
                return evals.normalize_quality_judge_response(response if isinstance(response, dict) else None)
            except evals.ValidationError:
                pass
        with tempfile.TemporaryDirectory(prefix=f"instruction-eval-saved-judge-{case['id']}-") as tmp:
            workspace = Path(tmp)
            schema_path = workspace / evals.QUALITY_JUDGE_SCHEMA
            schema_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(schema_source, schema_path)
            command = evals.build_quality_judge_command(
                agent_command,
                model=model,
                reasoning_effort=reasoning_effort,
                service_tier=service_tier,
                workspace=workspace,
                output_last_message=output_last_message,
                schema_path=schema_path,
                agent_command_mode=agent_command_mode,
            )
            case_output.mkdir(parents=True, exist_ok=True)
            try:
                completed = subprocess.run(
                    command,
                    cwd=repo_root,
                    text=True,
                    input=prompt,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=case_timeout_seconds,
                )
                stdout = completed.stdout
                stderr = completed.stderr
                returncode = completed.returncode
            except subprocess.TimeoutExpired as exc:
                stdout = evals.timeout_stream_text(exc.stdout)
                stderr = evals.timeout_stream_text(exc.stderr)
                returncode = 124
                (case_output / "timeout.txt").write_text(
                    f"quality judge timed out after {case_timeout_seconds}s\n",
                    encoding="utf-8",
                )
            (case_output / "events.jsonl").write_text(stdout, encoding="utf-8")
            (case_output / "stderr.txt").write_text(stderr, encoding="utf-8")
            if returncode == 124:
                raise evals.AgentExecutionFailure(f"quality judge timed out after {case_timeout_seconds}s")
            if returncode != 0:
                raise evals.AgentExecutionFailure(f"quality judge exited with code {returncode}")
            final_text = output_last_message.read_text(encoding="utf-8") if output_last_message.exists() else stdout
            response = evals.parse_final_response(final_text)
            try:
                return evals.normalize_quality_judge_response(response if isinstance(response, dict) else None)
            except evals.ValidationError as exc:
                raise evals.AgentExecutionFailure(f"quality judge output failed validation: {exc}") from exc
    except OSError as exc:
        raise evals.HarnessFailure(f"cannot create quality judge workspace or artifacts: {exc}") from exc


def compare_case(
    item: tuple[int, dict[str, Any]],
    *,
    baseline_label: str,
    baseline_records: dict[str, dict[str, Any]],
    candidate_label: str,
    candidate_records: dict[str, dict[str, Any]],
    repo_root: Path,
    agent_command: str,
    model: str,
    reasoning_effort: str,
    service_tier: str | None,
    output_dir: Path,
    summary_label: str,
    agent_command_mode: str,
    case_timeout_seconds: int | None,
) -> dict[str, Any]:
    index, case = item
    case_id = case["id"]
    baseline_record = require_case_record(baseline_records, baseline_label, case_id)
    candidate_record = require_case_record(candidate_records, candidate_label, case_id)
    judgment = evals.quality_gate_judgment(baseline_record, candidate_record)
    source = "hard_gate"
    if judgment is None:
        source = "judge"
        judgment = run_saved_quality_judge(
            case,
            repo_root=repo_root,
            agent_command=agent_command,
            model=model,
            reasoning_effort=reasoning_effort,
            service_tier=service_tier,
            output_dir=output_dir,
            summary_label=summary_label,
            baseline_label=baseline_label,
            baseline_record=baseline_record,
            candidate_label=candidate_label,
            candidate_record=candidate_record,
            agent_command_mode=agent_command_mode,
            case_timeout_seconds=case_timeout_seconds,
        )
    print(
        "quality "
        f"candidate={candidate_label} case={case_id} index={index} "
        f"source={source} winner={judgment.get('winner')} "
        f"baseline_score={judgment.get('baseline_score')} current_score={judgment.get('current_score')}",
        flush=True,
    )
    return {
        "case_id": case_id,
        "baseline": evals.quality_metrics(baseline_record),
        "candidate": evals.quality_metrics(candidate_record),
        "quality": judgment,
    }


def dry_run_candidate_plan(
    cases: list[dict[str, Any]],
    *,
    baseline_label: str,
    baseline_records: dict[str, dict[str, Any]],
    candidate_label: str,
    candidate_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    judge_cases: list[str] = []
    hard_gate_shortcuts = 0
    for case in cases:
        case_id = case["id"]
        baseline_record = require_case_record(baseline_records, baseline_label, case_id)
        candidate_record = require_case_record(candidate_records, candidate_label, case_id)
        if evals.quality_gate_judgment(baseline_record, candidate_record) is None:
            judge_cases.append(case_id)
        else:
            hard_gate_shortcuts += 1
    return {
        "candidate_label": candidate_label,
        "total": len(cases),
        "judge_calls": len(judge_cases),
        "hard_gate_shortcuts": hard_gate_shortcuts,
        "judge_cases": judge_cases,
    }


def aggregate_pair(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    winners = {"baseline": 0, "current": 0, "tie": 0, "inconclusive": 0}
    sources: dict[str, int] = {}
    confidence: dict[str, int] = {}
    baseline_scores: list[int] = []
    current_scores: list[int] = []
    for item in comparisons:
        quality = item["quality"]
        winner = quality.get("winner")
        if winner in winners:
            winners[winner] += 1
        source = str(quality.get("source", ""))
        sources[source] = sources.get(source, 0) + 1
        conf = str(quality.get("confidence", ""))
        confidence[conf] = confidence.get(conf, 0) + 1
        baseline_score = quality.get("baseline_score")
        current_score = quality.get("current_score")
        if isinstance(baseline_score, int) and isinstance(current_score, int):
            baseline_scores.append(baseline_score)
            current_scores.append(current_score)
    total = len(comparisons)
    baseline_passed = sum(1 for item in comparisons if item["baseline"]["passed"])
    candidate_passed = sum(1 for item in comparisons if item["candidate"]["passed"])
    avg_baseline = round(sum(baseline_scores) / len(baseline_scores), 1) if baseline_scores else 0.0
    avg_current = round(sum(current_scores) / len(current_scores), 1) if current_scores else 0.0
    return {
        "total": total,
        "baseline_passed": baseline_passed,
        "candidate_passed": candidate_passed,
        "winners": winners,
        "sources": sources,
        "confidence": confidence,
        "average_baseline_score": avg_baseline,
        "average_current_score": avg_current,
        "average_delta": round(avg_current - avg_baseline, 1),
    }


def write_pair_report(
    output_dir: Path,
    summary_label: str,
    baseline_label: str,
    candidate_label: str,
    comparisons: list[dict[str, Any]],
    judge_metadata: dict[str, str | None],
) -> dict[str, Any]:
    summary_dir = output_dir / evals.safe_label(summary_label) / "pairs" / evals.safe_label(candidate_label)
    summary_dir.mkdir(parents=True, exist_ok=True)
    aggregate = aggregate_pair(comparisons)
    payload = {
        "baseline_label": baseline_label,
        "candidate_label": candidate_label,
        "judge": judge_metadata,
        "aggregate": aggregate,
        "comparisons": comparisons,
    }
    json_path = summary_dir / "quality.json"
    md_path = summary_dir / "quality.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        f"# Saved Model Quality: {baseline_label} vs {candidate_label}",
        "",
        f"Baseline: `{baseline_label}`",
        f"Candidate: `{candidate_label}`",
        f"Judge: `{judge_metadata['model']}` (preset `{judge_metadata['preset']}`, reasoning `{judge_metadata['reasoning_effort']}`)",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Cases | {aggregate['total']} |",
        f"| Baseline hard-gate passed | {aggregate['baseline_passed']} |",
        f"| Candidate hard-gate passed | {aggregate['candidate_passed']} |",
        f"| Baseline wins | {aggregate['winners']['baseline']} |",
        f"| Candidate wins | {aggregate['winners']['current']} |",
        f"| Ties | {aggregate['winners']['tie']} |",
        f"| Inconclusive | {aggregate['winners']['inconclusive']} |",
        f"| Average baseline score | {aggregate['average_baseline_score']} |",
        f"| Average candidate score | {aggregate['average_current_score']} |",
        f"| Average delta | {aggregate['average_delta']} |",
        "",
        "| Case | Baseline pass | Candidate pass | Winner | Baseline score | Candidate score | Delta | Confidence | Source | Reason |",
        "|---|---:|---:|---|---:|---:|---:|---|---|---|",
    ]
    for item in comparisons:
        quality = item["quality"]
        baseline_score = quality.get("baseline_score", "")
        current_score = quality.get("current_score", "")
        delta = current_score - baseline_score if isinstance(baseline_score, int) and isinstance(current_score, int) else ""
        lines.append(
            "| "
            + " | ".join(
                [
                    evals.markdown_escape(item["case_id"]),
                    "yes" if item["baseline"]["passed"] else "no",
                    "yes" if item["candidate"]["passed"] else "no",
                    evals.markdown_escape(str(quality.get("winner", ""))),
                    str(baseline_score),
                    str(current_score),
                    str(delta),
                    evals.markdown_escape(str(quality.get("confidence", ""))),
                    evals.markdown_escape(str(quality.get("source", ""))),
                    evals.compact_markdown_cell(str(quality.get("reason", ""))),
                ]
            )
            + " |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "candidate_label": candidate_label,
        "judge": judge_metadata,
        "aggregate": aggregate,
        "quality_json": str(json_path),
        "quality_md": str(md_path),
    }


def write_summary_report(
    output_dir: Path,
    summary_label: str,
    baseline_label: str,
    pair_reports: list[dict[str, Any]],
    judge_metadata: dict[str, str | None],
) -> None:
    summary_dir = output_dir / evals.safe_label(summary_label)
    summary_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "label": summary_label,
        "baseline_label": baseline_label,
        "judge": judge_metadata,
        "pairs": pair_reports,
    }
    (summary_dir / "model-quality-summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"# Saved Model Quality Summary: {summary_label}",
        "",
        f"Baseline: `{baseline_label}`",
        f"Judge: `{judge_metadata['model']}` (preset `{judge_metadata['preset']}`, reasoning `{judge_metadata['reasoning_effort']}`)",
        "",
        "| Candidate | Hard passed | Candidate wins | Baseline wins | Ties | Inconclusive | Avg candidate score | Avg delta | Judge calls | Hard-gate shortcuts |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for report in pair_reports:
        aggregate = report["aggregate"]
        sources = aggregate["sources"]
        lines.append(
            "| "
            + " | ".join(
                [
                    evals.markdown_escape(report["candidate_label"]),
                    str(aggregate["candidate_passed"]),
                    str(aggregate["winners"]["current"]),
                    str(aggregate["winners"]["baseline"]),
                    str(aggregate["winners"]["tie"]),
                    str(aggregate["winners"]["inconclusive"]),
                    str(aggregate["average_current_score"]),
                    str(aggregate["average_delta"]),
                    str(sources.get("llm_judge", 0)),
                    str(sources.get("hard_gate", 0)),
                ]
            )
            + " |"
        )
    (summary_dir / "model-quality-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_ordered(items: list[Any], jobs: int, fn) -> list[Any]:
    if jobs <= 1:
        return [fn(item) for item in items]
    results: list[Any] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        future_by_index = {executor.submit(fn, item): index for index, item in enumerate(items)}
        for future, index in future_by_index.items():
            results[index] = future.result()
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quality-judge saved model eval artifacts.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--cases", default=str(evals.DEFAULT_CASES), help="Eval cases JSONL.")
    parser.add_argument("--presets", default=str(evals.DEFAULT_PRESETS), help="Model presets JSON.")
    parser.add_argument("--references", default=str(evals.DEFAULT_REFERENCES), help="Reference bundle JSON.")
    parser.add_argument("--baseline", required=True, type=parse_label_path, help="Baseline LABEL=summary.json.")
    parser.add_argument("--candidate", required=True, action="append", type=parse_label_path, help="Candidate LABEL=summary.json. Repeatable.")
    parser.add_argument("--agent-command", required=True, help="Judge agent command.")
    parser.add_argument("--agent-command-mode", default="current-codex", choices=sorted(evals.AGENT_COMMAND_MODES))
    parser.add_argument("--judge-preset", default=evals.DEFAULT_PRESET, help="Judge model preset.")
    parser.add_argument("--judge-model", help="Override judge model.")
    parser.add_argument("--judge-reasoning-effort", help="Override judge reasoning effort.")
    parser.add_argument("--judge-service-tier", help="Override judge service tier.")
    parser.add_argument("--jobs", type=int, default=1, help="Parallel judge calls per candidate.")
    parser.add_argument("--case-timeout-seconds", type=int, default=900)
    parser.add_argument("--output-dir", required=True, help="Output directory.")
    parser.add_argument("--dry-run", action="store_true", help="Print the saved-quality judge plan without running it.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = evals.repo_root_from(Path(args.repo_root))
    try:
        cases, _, presets, _ = evals.validate_all(
            repo_root,
            Path(args.cases),
            Path(args.presets),
            Path(args.references),
        )
        judge_args = argparse.Namespace(
            judge_preset=args.judge_preset,
            judge_model=args.judge_model,
            judge_reasoning_effort=args.judge_reasoning_effort,
            judge_service_tier=args.judge_service_tier,
        )
        judge_model, judge_reasoning_effort, judge_service_tier = evals.resolve_judge_model_config(judge_args, presets)
        judge_metadata = {
            "preset": args.judge_preset,
            "model": judge_model,
            "reasoning_effort": judge_reasoning_effort,
            "service_tier": judge_service_tier,
            "agent_command_mode": args.agent_command_mode,
        }
        evals.preflight_agent_command(args.agent_command)
        baseline_label, baseline_path = args.baseline
        baseline_records = read_summary(repo_root / baseline_path, baseline_label)
        output_dir = repo_root / args.output_dir
        summary_label = f"{evals.safe_label(baseline_label)}-saved-model-quality"
        pair_reports: list[dict[str, Any]] = []
        case_items = list(enumerate(cases, 1))
        if args.dry_run:
            print(
                "dry_run=true "
                f"summary_label={summary_label} "
                f"judge_model={judge_metadata['model']} "
                f"judge_preset={judge_metadata['preset']} "
                f"judge_reasoning_effort={judge_metadata['reasoning_effort']} "
                f"agent_command_mode={judge_metadata['agent_command_mode']} "
                f"output_dir={output_dir / evals.safe_label(summary_label)}"
            )
        for candidate_label, candidate_path in args.candidate:
            candidate_records = read_summary(repo_root / candidate_path, candidate_label)
            if args.dry_run:
                plan = dry_run_candidate_plan(
                    cases,
                    baseline_label=baseline_label,
                    baseline_records=baseline_records,
                    candidate_label=candidate_label,
                    candidate_records=candidate_records,
                )
                print(
                    "dry_run_candidate "
                    f"candidate={candidate_label} "
                    f"cases={plan['total']} "
                    f"judge_calls={plan['judge_calls']} "
                    f"hard_gate_shortcuts={plan['hard_gate_shortcuts']}"
                )
                if plan["judge_cases"]:
                    print("dry_run_judge_cases " + " ".join(plan["judge_cases"]))
                continue

            def run_one(item: tuple[int, dict[str, Any]]) -> dict[str, Any]:
                return compare_case(
                    item,
                    baseline_label=baseline_label,
                    baseline_records=baseline_records,
                    candidate_label=candidate_label,
                    candidate_records=candidate_records,
                    repo_root=repo_root,
                    agent_command=args.agent_command,
                    model=judge_model,
                    reasoning_effort=judge_reasoning_effort,
                    service_tier=judge_service_tier,
                    output_dir=output_dir,
                    summary_label=summary_label,
                    agent_command_mode=args.agent_command_mode,
                    case_timeout_seconds=args.case_timeout_seconds,
                )

            comparisons = run_ordered(case_items, args.jobs, run_one)
            pair_reports.append(
                write_pair_report(output_dir, summary_label, baseline_label, candidate_label, comparisons, judge_metadata)
            )
        if args.dry_run:
            return 0
        write_summary_report(output_dir, summary_label, baseline_label, pair_reports, judge_metadata)
        summary_path = output_dir / evals.safe_label(summary_label) / "model-quality-summary.md"
        print(f"quality_summary={summary_path}")
        return 0
    except evals.AgentExecutionFailure as exc:
        print(f"failure_type=agent error={exc}", file=sys.stderr)
        return 3
    except (evals.ValidationError, evals.HarnessFailure, OSError, json.JSONDecodeError) as exc:
        print(f"failure_type=harness error={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
