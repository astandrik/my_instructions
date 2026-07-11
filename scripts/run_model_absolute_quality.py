#!/usr/bin/env python3
"""Score saved hard-gate-passed eval responses independently with one judge."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_instruction_evals as evals


DEFAULT_MANIFEST = Path("evals/model-quality-matrix.json")
DEFAULT_OUTPUT_ROOT = Path(".eval-results/blinded-model-absolute-v1")
CANONICAL_MODELS = (
    ("gpt-5.6-sol", "GPT-5.6 Sol medium", "primary"),
    ("gpt-5.5", "GPT-5.5", "historical"),
    ("glm-5.2", "GLM-5.2", "external"),
    ("grok-4.3", "Grok 4.3", "external"),
    ("deepseek-v4-flash", "DeepSeek V4 Flash", "external"),
    ("deepseek-v4-flash-thinking", "DeepSeek V4 Flash thinking", "external"),
)
CANONICAL_JUDGES = {
    "sol": {
        "preset": "gpt-5.6-sol-medium",
        "model": "gpt-5.6-sol",
        "reasoning_effort": "medium",
        "service_tier": "fast",
    },
    "terra": {
        "preset": "gpt-5.6-terra-high",
        "model": "gpt-5.6-terra",
        "reasoning_effort": "high",
        "service_tier": "fast",
    },
}
PAIRWISE_FIELDS = {
    "pairs",
    "pair_count",
    "order_jobs",
    "deterministic_shortcuts",
    "total_case_comparisons",
}


class MatrixError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelJob:
    model_id: str
    model_label: str
    role: str
    source_path: str
    source_sha256: str
    source_records: tuple[dict[str, Any], ...]
    case_ids: tuple[str, ...]
    output_path: Path


@dataclass(frozen=True)
class AbsolutePlan:
    repo_root: Path
    manifest_path: Path
    output_root: Path
    judge_name: str
    judge_metadata: dict[str, str]
    snapshots: dict[str, Any]
    cases_by_id: dict[str, dict[str, Any]]
    jobs: tuple[ModelJob, ...]
    judge_calls: int
    timeout_seconds: int


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def response_sha256(record: dict[str, Any]) -> str:
    safe = evals.safe_quality_record("response", record)
    return hashlib.sha256(canonical_json_bytes(safe)).hexdigest()


def require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MatrixError(f"{context} must be an object")
    return value


def confined_path(repo_root: Path, raw_path: str, context: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise MatrixError(f"{context} must be repo-relative")
    resolved = (repo_root / candidate).resolve()
    if not resolved.is_relative_to(repo_root.resolve()):
        raise MatrixError(f"{context} escapes repository")
    return resolved


def load_cases(path: Path, expected_count: int) -> tuple[dict[str, dict[str, Any]], tuple[str, ...]]:
    cases: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MatrixError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise MatrixError(f"{path}:{line_number}: invalid case")
        case_id = case["id"]
        if case_id in cases:
            raise MatrixError(f"{path}: duplicate case id {case_id}")
        cases[case_id] = case
        order.append(case_id)
    if len(cases) != expected_count:
        raise MatrixError(f"{path}: expected {expected_count} cases, found {len(cases)}")
    return cases, tuple(order)


def load_source_summary(
    path: Path,
    *,
    expected_case_ids: tuple[str, ...],
    expected_sha256: str,
) -> tuple[dict[str, Any], ...]:
    if not path.is_file():
        raise MatrixError(f"source summary does not exist: {path}")
    if file_sha256(path) != expected_sha256:
        raise MatrixError(f"source hash drift: {path}")
    parsed = require_object(json.loads(path.read_text(encoding="utf-8")), str(path))
    results = parsed.get("results")
    if not isinstance(results, list):
        raise MatrixError(f"{path}: results must be an array")
    by_id: dict[str, dict[str, Any]] = {}
    for record in results:
        if not isinstance(record, dict) or not isinstance(record.get("case_id"), str):
            raise MatrixError(f"{path}: invalid result record")
        case_id = record["case_id"]
        if case_id in by_id:
            raise MatrixError(f"{path}: duplicate case id {case_id}")
        by_id[case_id] = record
    if tuple(by_id) != expected_case_ids:
        raise MatrixError(f"{path}: case set or order drift")
    passed = sum(record.get("passed") is True for record in by_id.values())
    if parsed.get("total") != len(expected_case_ids) or parsed.get("passed") != passed:
        raise MatrixError(f"{path}: aggregate counts drift")
    if parsed.get("failed") != len(expected_case_ids) - passed:
        raise MatrixError(f"{path}: failed count drift")
    if any(record.get("failure_type") == "agent" for record in by_id.values()):
        raise MatrixError(f"{path}: source contains agent failure")
    return tuple(by_id[case_id] for case_id in expected_case_ids)


def validate_manifest_contract(manifest: dict[str, Any]) -> None:
    models = manifest.get("models")
    if not isinstance(models, list):
        raise MatrixError("models must be an array")
    actual_models = tuple(
        (model.get("id"), model.get("label"), model.get("role"))
        for model in models
        if isinstance(model, dict)
    )
    if actual_models != CANONICAL_MODELS:
        raise MatrixError("model contract drift")
    if manifest.get("execution") != {
        "jobs": 1,
        "per_case_timeout_seconds": 900,
        "automatic_retries": 0,
    }:
        raise MatrixError("execution contract drift")
    judges = require_object(manifest.get("judges"), "judges")
    if set(judges) != set(CANONICAL_JUDGES):
        raise MatrixError("judge contract drift")
    expected_ids = [model_id for model_id, _, _ in CANONICAL_MODELS]
    for judge_name, canonical in CANONICAL_JUDGES.items():
        judge = require_object(judges.get(judge_name), f"judge {judge_name}")
        serialized_keys = set(judge) | set(require_object(judge.get("budget"), "budget"))
        if serialized_keys & PAIRWISE_FIELDS:
            raise MatrixError("pairwise judge fields are forbidden in absolute scoring")
        if {key: judge.get(key) for key in canonical} != canonical:
            raise MatrixError(f"judge {judge_name} metadata drift")
        if judge.get("coverage") != "all_hard_gate_passed_responses":
            raise MatrixError(f"judge {judge_name} coverage drift")
        counts = judge.get("model_passed_counts")
        if not isinstance(counts, dict) or list(counts) != expected_ids:
            raise MatrixError(f"judge {judge_name} passed counts drift")
        if judge.get("budget") != {"model_jobs": 6, "judge_calls": 157}:
            raise MatrixError(f"judge {judge_name} budget drift")


def _build_plan_from_cases(
    repo_root: Path,
    manifest_path: Path,
    judge_name: str,
    manifest: dict[str, Any],
    snapshots: dict[str, Any],
    cases_by_id: dict[str, dict[str, Any]],
    case_ids: tuple[str, ...],
    *,
    output_root: Path | None = None,
) -> AbsolutePlan:
    presets_path = repo_root / "evals" / "model-presets.json"
    presets = require_object(json.loads(presets_path.read_text(encoding="utf-8")), "presets")
    judge_manifest = manifest["judges"][judge_name]
    preset = presets.get(judge_manifest["preset"])
    expected_preset = {
        key: judge_manifest[key] for key in ("model", "reasoning_effort", "service_tier")
    }
    if preset != expected_preset:
        raise MatrixError(f"judge {judge_name} preset drift")

    root = (output_root or (repo_root / DEFAULT_OUTPUT_ROOT)).resolve()
    if not root.is_relative_to(repo_root):
        raise MatrixError("output root escapes repository")
    jobs: list[ModelJob] = []
    actual_counts: dict[str, int] = {}
    for model in manifest["models"]:
        source = require_object(model.get("source_summary"), f"source {model['id']}")
        source_path = confined_path(repo_root, source.get("path", ""), f"source {model['id']}")
        records = load_source_summary(
            source_path,
            expected_case_ids=case_ids,
            expected_sha256=source.get("sha256"),
        )
        passed_ids = tuple(
            record["case_id"]
            for record in records
            if record.get("passed") is True and record.get("failure_type") == "none"
        )
        actual_counts[model["id"]] = len(passed_ids)
        jobs.append(
            ModelJob(
                model_id=model["id"],
                model_label=model["label"],
                role=model["role"],
                source_path=source["path"],
                source_sha256=source["sha256"],
                source_records=records,
                case_ids=passed_ids,
                output_path=root / "judgments" / judge_name / model["id"],
            )
        )
    if actual_counts != judge_manifest["model_passed_counts"]:
        raise MatrixError(f"judge {judge_name} passed counts drift")
    total = sum(actual_counts.values())
    if total != judge_manifest["budget"]["judge_calls"]:
        raise MatrixError(f"judge {judge_name} call budget drift")
    return AbsolutePlan(
        repo_root=repo_root,
        manifest_path=manifest_path,
        output_root=root,
        judge_name=judge_name,
        judge_metadata={"key": judge_name, **CANONICAL_JUDGES[judge_name]},
        snapshots=snapshots,
        cases_by_id=cases_by_id,
        jobs=tuple(jobs),
        judge_calls=total,
        timeout_seconds=manifest["execution"]["per_case_timeout_seconds"],
    )


def build_plan(
    repo_root: Path,
    manifest_path: Path,
    judge_name: str,
    *,
    output_root: Path | None = None,
) -> AbsolutePlan:
    repo_root = repo_root.resolve()
    manifest_path = manifest_path.resolve()
    if judge_name not in CANONICAL_JUDGES:
        raise MatrixError(f"unknown judge: {judge_name}")
    manifest = require_object(json.loads(manifest_path.read_text(encoding="utf-8")), "manifest")
    validate_manifest_contract(manifest)

    snapshots = require_object(manifest.get("snapshots"), "snapshots")
    instruction_snapshot = require_object(snapshots.get("instructions"), "instruction snapshot")
    instruction_path = repo_root / "CRITICAL_INSTRUCTIONS.md"
    if file_sha256(instruction_path) != instruction_snapshot.get("sha256"):
        raise MatrixError("instruction snapshot hash drift")
    cases_snapshot = require_object(snapshots.get("cases"), "cases snapshot")
    cases_path = confined_path(repo_root, cases_snapshot.get("path", ""), "cases path")
    if file_sha256(cases_path) != cases_snapshot.get("sha256"):
        raise MatrixError("cases snapshot hash drift")
    cases_by_id, case_ids = load_cases(cases_path, cases_snapshot.get("count"))
    return _build_plan_from_cases(
        repo_root,
        manifest_path,
        judge_name,
        manifest,
        snapshots,
        cases_by_id,
        case_ids,
        output_root=output_root,
    )


def frozen_case_ids(
    repo_root: Path,
    manifest: dict[str, Any],
    expected_count: int,
) -> tuple[str, ...]:
    first_model = manifest["models"][0]
    source = require_object(first_model.get("source_summary"), f"source {first_model['id']}")
    source_path = confined_path(repo_root, source.get("path", ""), f"source {first_model['id']}")
    if file_sha256(source_path) != source.get("sha256"):
        raise MatrixError(f"source hash drift: {source_path}")
    parsed = require_object(json.loads(source_path.read_text(encoding="utf-8")), str(source_path))
    results = parsed.get("results")
    if not isinstance(results, list):
        raise MatrixError(f"{source_path}: results must be an array")
    case_ids: list[str] = []
    seen: set[str] = set()
    for record in results:
        if not isinstance(record, dict) or not isinstance(record.get("case_id"), str):
            raise MatrixError(f"{source_path}: invalid result record")
        case_id = record["case_id"]
        if case_id in seen:
            raise MatrixError(f"{source_path}: duplicate case id {case_id}")
        seen.add(case_id)
        case_ids.append(case_id)
    if len(case_ids) != expected_count:
        raise MatrixError(f"{source_path}: expected {expected_count} frozen case ids")
    return tuple(case_ids)


def build_frozen_plan(
    repo_root: Path,
    manifest_path: Path,
    judge_name: str,
    *,
    output_root: Path | None = None,
) -> AbsolutePlan:
    """Rebuild a frozen publication from hashed sources after the live case catalog changes."""
    repo_root = repo_root.resolve()
    manifest_path = manifest_path.resolve()
    if judge_name not in CANONICAL_JUDGES:
        raise MatrixError(f"unknown judge: {judge_name}")
    manifest = require_object(json.loads(manifest_path.read_text(encoding="utf-8")), "manifest")
    validate_manifest_contract(manifest)
    snapshots = require_object(manifest.get("snapshots"), "snapshots")
    require_object(snapshots.get("instructions"), "instruction snapshot")
    cases_snapshot = require_object(snapshots.get("cases"), "cases snapshot")
    expected_count = cases_snapshot.get("count")
    if isinstance(expected_count, bool) or not isinstance(expected_count, int) or expected_count < 1:
        raise MatrixError("cases snapshot count must be a positive integer")
    case_ids = frozen_case_ids(repo_root, manifest, expected_count)
    cases_by_id = {case_id: {"id": case_id} for case_id in case_ids}
    return _build_plan_from_cases(
        repo_root,
        manifest_path,
        judge_name,
        manifest,
        snapshots,
        cases_by_id,
        case_ids,
        output_root=output_root,
    )


def record_for_case(job: ModelJob, case_id: str) -> dict[str, Any]:
    for record in job.source_records:
        if record["case_id"] == case_id:
            return record
    raise MatrixError(f"{job.model_id}: missing source record {case_id}")


def build_case_invocation(
    plan: AbsolutePlan,
    job: ModelJob,
    case_id: str,
    *,
    agent_command: str,
    workspace: Path | None = None,
) -> tuple[list[str], str]:
    if case_id not in job.case_ids:
        raise MatrixError(f"{job.model_id}: case {case_id} is not a passed response")
    record = record_for_case(job, case_id)
    prompt = evals.absolute_quality_judge_prompt(plan.cases_by_id[case_id], record)
    case_output = job.output_path / "cases" / case_id
    active_workspace = workspace or (case_output / "workspace")
    schema_path = active_workspace / evals.ABSOLUTE_QUALITY_JUDGE_SCHEMA
    command = evals.build_quality_judge_command(
        agent_command,
        model=plan.judge_metadata["model"],
        reasoning_effort=plan.judge_metadata["reasoning_effort"],
        service_tier=plan.judge_metadata["service_tier"],
        workspace=active_workspace,
        output_last_message=case_output / "final-message.json",
        schema_path=schema_path,
        agent_command_mode="current-codex",
    )
    return command, prompt


def build_model_summary(
    plan: AbsolutePlan,
    job: ModelJob,
    judgments: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "version": 1,
        "judge": plan.judge_metadata,
        "snapshots": plan.snapshots,
        "source": {
            "model_id": job.model_id,
            "model_label": job.model_label,
            "role": job.role,
            "path": job.source_path,
            "sha256": job.source_sha256,
        },
        "total_cases": len(plan.cases_by_id),
        "hard_gate_passed": len(job.case_ids),
        "judgments": judgments,
    }


def validate_model_summary(plan: AbsolutePlan, job: ModelJob, path: Path) -> None:
    if path.is_symlink():
        raise MatrixError(f"symlink artifact is forbidden: {path}")
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MatrixError(f"invalid completed summary {path}: {exc}") from exc
    expected_top = {
        "version",
        "judge",
        "snapshots",
        "source",
        "total_cases",
        "hard_gate_passed",
        "judgments",
    }
    if not isinstance(summary, dict) or set(summary) != expected_top:
        raise MatrixError(f"{path}: summary contract drift")
    if summary["version"] != 1 or summary["judge"] != plan.judge_metadata:
        raise MatrixError(f"{path}: judge metadata drift")
    if summary["snapshots"] != plan.snapshots:
        raise MatrixError(f"{path}: snapshot provenance drift")
    expected_source = {
        "model_id": job.model_id,
        "model_label": job.model_label,
        "role": job.role,
        "path": job.source_path,
        "sha256": job.source_sha256,
    }
    if summary["source"] != expected_source:
        raise MatrixError(f"{path}: source provenance drift")
    if summary["total_cases"] != len(plan.cases_by_id):
        raise MatrixError(f"{path}: total case count drift")
    if summary["hard_gate_passed"] != len(job.case_ids):
        raise MatrixError(f"{path}: hard gate count drift")
    judgments = summary["judgments"]
    if not isinstance(judgments, list) or [item.get("case_id") for item in judgments] != list(job.case_ids):
        raise MatrixError(f"{path}: judgment case coverage drift")
    for judgment in judgments:
        expected_judgment_fields = {
            "case_id",
            "response_sha256",
            "score",
            "confidence",
            "reason",
            "checks",
        }
        if not isinstance(judgment, dict) or set(judgment) != expected_judgment_fields:
            raise MatrixError(f"{path}: judgment contract drift")
        record = record_for_case(job, judgment["case_id"])
        if judgment.get("response_sha256") != response_sha256(record):
            raise MatrixError(f"{path}: response digest drift")
        payload = {key: judgment.get(key) for key in ("score", "confidence", "reason", "checks")}
        try:
            evals.validate_absolute_quality_judge_response(payload)
        except evals.ValidationError as exc:
            raise MatrixError(f"{path}: invalid absolute judgment: {exc}") from exc


def reject_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise MatrixError(f"symlink output path is forbidden: {root}")
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_symlink():
            raise MatrixError(f"symlink output path is forbidden: {path}")


def validate_output_state(plan: AbsolutePlan) -> dict[str, str]:
    reject_symlinks(plan.output_root)
    if not plan.output_root.exists():
        return {job.model_id: "fresh" for job in plan.jobs}
    allowed_root = {"judgments", "canonical"}
    unexpected_root = {path.name for path in plan.output_root.iterdir()} - allowed_root
    if unexpected_root:
        raise MatrixError(f"unexpected output entries: {', '.join(sorted(unexpected_root))}")
    judge_root = plan.output_root / "judgments" / plan.judge_name
    if not judge_root.exists():
        return {job.model_id: "fresh" for job in plan.jobs}
    expected_models = {job.model_id for job in plan.jobs}
    unexpected = {path.name for path in judge_root.iterdir()} - expected_models
    if unexpected:
        raise MatrixError(f"unexpected judge output entries: {', '.join(sorted(unexpected))}")
    states: dict[str, str] = {}
    for job in plan.jobs:
        if not job.output_path.exists():
            states[job.model_id] = "fresh"
            continue
        summary_path = job.output_path / "summary.json"
        if not summary_path.is_file():
            raise MatrixError(f"incomplete existing output: {job.output_path}")
        validate_model_summary(plan, job, summary_path)
        states[job.model_id] = "complete"
    return states


def run_model_job(plan: AbsolutePlan, job: ModelJob, agent_command: str) -> None:
    schema_source = plan.repo_root / evals.ABSOLUTE_QUALITY_JUDGE_SCHEMA
    evals.validate_absolute_quality_judge_schema(schema_source)
    judgments: list[dict[str, Any]] = []
    for index, case_id in enumerate(job.case_ids, 1):
        case_output = job.output_path / "cases" / case_id
        case_output.mkdir(parents=True, exist_ok=False)
        with tempfile.TemporaryDirectory(prefix=f"absolute-quality-{case_id}-") as tmp:
            workspace = Path(tmp)
            schema_path = workspace / evals.ABSOLUTE_QUALITY_JUDGE_SCHEMA
            schema_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(schema_source, schema_path)
            command, prompt = build_case_invocation(
                plan,
                job,
                case_id,
                agent_command=agent_command,
                workspace=workspace,
            )
            try:
                completed = subprocess.run(
                    command,
                    cwd=plan.repo_root,
                    text=True,
                    input=prompt,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=plan.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise MatrixError(
                    f"absolute judge timed out after {plan.timeout_seconds}s: "
                    f"{job.model_id}/{case_id}"
                ) from exc
            (case_output / "events.jsonl").write_text(completed.stdout, encoding="utf-8")
            (case_output / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
            if completed.returncode != 0:
                raise MatrixError(
                    f"absolute judge exited with code {completed.returncode}: "
                    f"{job.model_id}/{case_id}"
                )
            final_path = case_output / "final-message.json"
            final_text = final_path.read_text(encoding="utf-8") if final_path.exists() else completed.stdout
            response = evals.parse_final_response(final_text)
            try:
                evals.validate_absolute_quality_judge_response(response)
            except evals.ValidationError as exc:
                raise MatrixError(
                    f"absolute judge output failed validation: {job.model_id}/{case_id}: {exc}"
                ) from exc
            record = record_for_case(job, case_id)
            judgments.append(
                {
                    "case_id": case_id,
                    "response_sha256": response_sha256(record),
                    **response,
                }
            )
        print(
            f"absolute-quality judge={plan.judge_name} model={job.model_id} "
            f"case={case_id} index={index} total={len(job.case_ids)} score={response['score']}",
            flush=True,
        )
    summary = build_model_summary(plan, job, judgments)
    summary_path = job.output_path / "summary.json"
    summary_path.write_bytes(canonical_json_bytes(summary))
    validate_model_summary(plan, job, summary_path)


def execute_plan(plan: AbsolutePlan, agent_command: str) -> None:
    states = validate_output_state(plan)
    for job in plan.jobs:
        if states[job.model_id] == "complete":
            print(f"absolute-quality judge={plan.judge_name} model={job.model_id} status=skipped-complete")
            continue
        run_model_job(plan, job, agent_command)


def print_plan(plan: AbsolutePlan) -> None:
    for job in plan.jobs:
        print(
            f"plan judge={plan.judge_name} model={job.model_id} "
            f"calls={len(job.case_ids)} output={job.output_path}"
        )
    print(
        f"plan_total judge={plan.judge_name} models={len(plan.jobs)} "
        f"judge_calls={plan.judge_calls}"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("plan", "run"):
        child = subparsers.add_parser(command)
        child.add_argument("--judge", choices=sorted(CANONICAL_JUDGES), required=True)
        if command == "run":
            child.add_argument("--agent-command", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
    output_root = args.output_root if args.output_root.is_absolute() else repo_root / args.output_root
    try:
        plan = build_plan(repo_root, manifest_path, args.judge, output_root=output_root)
        print_plan(plan)
        if args.command == "run":
            execute_plan(plan, args.agent_command)
    except (MatrixError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
