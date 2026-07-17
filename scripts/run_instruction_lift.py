#!/usr/bin/env python3
"""Run a prompt-neutral current/previous/empty instruction-lift holdout."""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


DEFAULT_CASES = Path("evals/instruction-lift-cases.jsonl")
DEFAULT_PRESETS = Path("evals/model-presets.json")
DEFAULT_SCHEMA = Path("evals/instruction-lift-response.schema.json")
DEFAULT_OUTPUT_DIR = Path(".eval-results/gpt56-instruction-lift-holdout-v1")
DEFAULT_PREVIOUS_REF = "643cd27"
DEFAULT_PRESET = "gpt-5.6-sol-medium"
INSTRUCTION_PATH = Path("CRITICAL_INSTRUCTIONS.md")
LEGACY_APPENDIX_PATH = Path("ADVANCED_PATTERNS_REFERENCE.md")
BUNDLES = ("current", "previous", "empty")
BUNDLE_ONLY_PATHS = {
    str(INSTRUCTION_PATH),
    str(DEFAULT_SCHEMA),
    "final-message.json",
}
SEMANTIC_FIXTURE_CATEGORIES = {
    "positive",
    "negative",
    "plausible_wrong",
    "wrong_behavior",
    "keyword_only",
    "reward_hacking",
}
VERDICTS = {"pass", "fail", "ambiguous"}
CASE_FAMILIES = {"changed_rule", "control"}
MUTATION_MODES = {"required", "forbidden", "optional"}
REQUIRED_CASE_FIELDS = {
    "id",
    "family",
    "prompt",
    "anti_hardcoding_prompt",
    "fixture_dir",
    "expected_behavior",
    "forbidden_behavior",
    "rubric",
    "mutation_contract",
    "semantic_fixtures",
    "v413_trace",
}
PRIVATE_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9_-])sk-(?:proj-|live-|test-)?[A-Za-z0-9_-]{12,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


class ValidationError(Exception):
    """Raised when holdout inputs or artifacts violate the frozen contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def file_sha256(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot hash file {path}: {exc}") from exc
    return sha256_bytes(raw)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_json_sha256(value: Any) -> str:
    return sha256_text(canonical_json(value))


def verify_artifact_hash(path: Path, expected_sha256: str, label: str) -> None:
    if not path.is_file():
        raise ValidationError(f"missing frozen artifact: {label}: {path}")
    if file_sha256(path) != expected_sha256:
        raise ValidationError(f"frozen artifact drift: {label}")


def write_json(path: Path, value: Any) -> None:
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"cannot write strict JSON {path}: {exc}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read JSON {path}: {exc}") from exc


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValidationError(f"cannot read JSONL {path}: {exc}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValidationError(f"{path}:{line_number}: each row must be an object")
        rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    try:
        serialized = "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for row in rows
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"cannot write strict JSONL {path}: {exc}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialized, encoding="utf-8")


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    return value


def require_string_list(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValidationError(f"{label} must be a {'possibly empty ' if allow_empty else 'non-empty '}list of strings")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValidationError(f"{label} must contain only non-empty strings")
    return value


def validate_private_content(value: Any, label: str) -> None:
    rendered = canonical_json(value)
    for pattern in PRIVATE_PATTERNS:
        if pattern.search(rendered):
            raise ValidationError(f"{label} contains private credential-like content")


def validate_fixture_tree(repo_root: Path, case_id: str, raw_fixture_dir: str) -> Path:
    relative = Path(raw_fixture_dir)
    expected_prefix = Path("evals/instruction-lift-fixtures") / case_id
    if relative.is_absolute() or ".." in relative.parts or relative != expected_prefix:
        raise ValidationError(f"{case_id}: fixture_dir must be {expected_prefix}")
    fixture_dir = repo_root / relative
    if not fixture_dir.is_dir():
        raise ValidationError(f"{case_id}: fixture_dir does not exist: {relative}")
    files = [path for path in fixture_dir.rglob("*") if path.is_file()]
    if not files:
        raise ValidationError(f"{case_id}: fixture_dir must contain at least one file")
    for path in fixture_dir.rglob("*"):
        if path.is_symlink():
            raise ValidationError(f"{case_id}: fixture tree must not contain symlinks: {path}")
        if path.name in {".env", "CRITICAL_INSTRUCTIONS.md", DEFAULT_SCHEMA.name}:
            raise ValidationError(f"{case_id}: forbidden fixture filename: {path.name}")
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            validate_private_content(text, f"{case_id}:{path.relative_to(fixture_dir)}")
    return fixture_dir


def validate_case(repo_root: Path, case: dict[str, Any]) -> None:
    unknown = set(case) - REQUIRED_CASE_FIELDS
    missing = REQUIRED_CASE_FIELDS - set(case)
    case_id = str(case.get("id", "<unknown>"))
    if unknown:
        raise ValidationError(f"{case_id}: unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        raise ValidationError(f"{case_id}: missing fields: {', '.join(sorted(missing))}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", case_id):
        raise ValidationError(f"{case_id}: id must use lowercase letters, digits, and hyphens")
    if case["family"] not in CASE_FAMILIES:
        raise ValidationError(f"{case_id}: family must be changed_rule or control")
    prompt = require_string(case["prompt"], f"{case_id}.prompt")
    anti_prompt = require_string(case["anti_hardcoding_prompt"], f"{case_id}.anti_hardcoding_prompt")
    if prompt.strip() == anti_prompt.strip():
        raise ValidationError(f"{case_id}: anti_hardcoding_prompt must paraphrase the primary prompt")
    if case_id in prompt or case_id in anti_prompt:
        raise ValidationError(f"{case_id}: prompts must not expose the case id")
    validate_fixture_tree(repo_root, case_id, require_string(case["fixture_dir"], f"{case_id}.fixture_dir"))
    require_string_list(case["expected_behavior"], f"{case_id}.expected_behavior")
    require_string_list(case["forbidden_behavior"], f"{case_id}.forbidden_behavior")
    require_string(case["rubric"], f"{case_id}.rubric")
    if case["family"] == "changed_rule":
        require_string(case["v413_trace"], f"{case_id}.v413_trace")
    elif not isinstance(case["v413_trace"], str):
        raise ValidationError(f"{case_id}.v413_trace must be a string")
    mutation = case["mutation_contract"]
    if not isinstance(mutation, dict) or set(mutation) != {"mode", "required_paths", "forbidden_paths"}:
        raise ValidationError(f"{case_id}.mutation_contract has invalid fields")
    if mutation["mode"] not in MUTATION_MODES:
        raise ValidationError(f"{case_id}.mutation_contract.mode is invalid")
    require_string_list(mutation["required_paths"], f"{case_id}.required_paths", allow_empty=True)
    require_string_list(mutation["forbidden_paths"], f"{case_id}.forbidden_paths", allow_empty=True)
    if mutation["mode"] == "required" and not mutation["required_paths"]:
        raise ValidationError(f"{case_id}: required mutation needs required_paths")
    fixtures = case["semantic_fixtures"]
    if not isinstance(fixtures, dict) or set(fixtures) != SEMANTIC_FIXTURE_CATEGORIES:
        raise ValidationError(
            f"{case_id}: semantic_fixtures must contain {', '.join(sorted(SEMANTIC_FIXTURE_CATEGORIES))}"
        )
    flattened: list[str] = []
    for category in sorted(SEMANTIC_FIXTURE_CATEGORIES):
        values = require_string_list(fixtures[category], f"{case_id}.semantic_fixtures.{category}")
        if category == "positive" and len(values) != 2:
            raise ValidationError(f"{case_id}: positive fixtures must contain compact and natural examples")
        flattened.extend(values)
    if len(flattened) != len(set(flattened)):
        raise ValidationError(f"{case_id}: semantic fixture responses must be unique")
    validate_private_content(case, case_id)


def load_and_validate_cases(repo_root: Path, path: Path = DEFAULT_CASES) -> list[dict[str, Any]]:
    resolved = path if path.is_absolute() else repo_root / path
    cases = read_jsonl(resolved)
    if len(cases) != 8:
        raise ValidationError(f"holdout catalog must contain exactly 8 cases, got {len(cases)}")
    seen: set[str] = set()
    for case in cases:
        validate_case(repo_root, case)
        if case["id"] in seen:
            raise ValidationError(f"duplicate case id: {case['id']}")
        seen.add(case["id"])
    family_counts = Counter(case["family"] for case in cases)
    if family_counts != Counter({"changed_rule": 6, "control": 2}):
        raise ValidationError(f"holdout catalog must contain 6 changed_rule and 2 control cases, got {dict(family_counts)}")
    return cases


def validate_response_schema(path: Path) -> None:
    schema = read_json(path)
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise ValidationError("instruction-lift response schema must be a closed object")
    if schema.get("required") != ["final_response"] or set(schema.get("properties", {})) != {"final_response"}:
        raise ValidationError("instruction-lift response schema must contain only required final_response")


def git_show(repo_root: Path, ref: str, path: Path, *, required: bool) -> str | None:
    completed = subprocess.run(
        ["git", "show", f"{ref}:{path.as_posix()}"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode == 0:
        return completed.stdout
    if required:
        raise ValidationError(f"cannot load {path} from {ref}: {completed.stderr.strip()}")
    return None


def load_previous_instructions(repo_root: Path, ref: str = DEFAULT_PREVIOUS_REF) -> str:
    primary = git_show(repo_root, ref, INSTRUCTION_PATH, required=True)
    assert primary is not None
    contents = [primary.rstrip()]
    appendix = git_show(repo_root, ref, LEGACY_APPENDIX_PATH, required=False)
    if appendix and appendix.strip():
        contents.append(
            f"<!-- Legacy appendix from {LEGACY_APPENDIX_PATH} in {ref}, merged for single-file comparison. -->\n\n"
            + appendix.strip()
        )
    return "\n\n".join(contents) + "\n"


def instruction_contents(repo_root: Path, bundle: str, previous_ref: str) -> str:
    if bundle == "current":
        return (repo_root / INSTRUCTION_PATH).read_text(encoding="utf-8")
    if bundle == "previous":
        return load_previous_instructions(repo_root, previous_ref)
    if bundle == "empty":
        return ""
    raise ValidationError(f"unknown bundle: {bundle}")


def materialize_workspace(
    repo_root: Path,
    case: dict[str, Any],
    *,
    bundle: str,
    previous_ref: str,
    destination: Path,
) -> None:
    fixture_dir = repo_root / case["fixture_dir"]
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copytree(fixture_dir, destination, dirs_exist_ok=True)
    instruction_target = destination / INSTRUCTION_PATH
    instruction_target.parent.mkdir(parents=True, exist_ok=True)
    instruction_target.write_text(instruction_contents(repo_root, bundle, previous_ref), encoding="utf-8")
    schema_target = destination / DEFAULT_SCHEMA
    schema_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo_root / DEFAULT_SCHEMA, schema_target)


def build_neutral_prompt(instructions: str, case: dict[str, Any]) -> str:
    return (
        "Apply the instruction text to the user task.\n\n"
        "<instruction_text>\n"
        f"{instructions}"
        "</instruction_text>\n\n"
        "<user_task>\n"
        f"{case['prompt'].strip()}\n"
        "</user_task>\n"
    )


def make_cell(case_id: str, bundle: str, repetition: int) -> dict[str, Any]:
    identity = f"{case_id}:{bundle}:{repetition}"
    return {
        "cell_id": f"C-{sha256_text('cell:' + identity)[:12]}",
        "sample_id": f"S-{sha256_text('sample:' + identity)[:12]}",
        "case_id": case_id,
        "bundle": bundle,
        "repetition": repetition,
    }


def build_call_matrix(cases: list[dict[str, Any]], repetitions: int = 3) -> list[dict[str, Any]]:
    if repetitions < 1:
        raise ValidationError("repetitions must be positive")
    return [
        make_cell(case["id"], bundle, repetition)
        for case in cases
        for bundle in BUNDLES
        for repetition in range(1, repetitions + 1)
    ]


def snapshot_tree(root: Path, ignored_paths: set[str] | None = None) -> dict[str, dict[str, Any]]:
    ignored = ignored_paths or set()
    snapshot: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in ignored or relative.startswith(".git/") or "__pycache__" in path.parts:
            continue
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8") if len(raw) <= 1024 * 1024 else None
        except UnicodeDecodeError:
            text = None
        snapshot[relative] = {"sha256": sha256_bytes(raw), "size": len(raw), "text": text}
    return snapshot


def fixture_set_sha256(repo_root: Path, cases: list[dict[str, Any]]) -> str:
    payload = []
    for case in sorted(cases, key=lambda item: item["id"]):
        fixture_root = repo_root / case["fixture_dir"]
        files = snapshot_tree(fixture_root)
        payload.append(
            {
                "case_id": case["id"],
                "files": {
                    path: {"sha256": metadata["sha256"], "size": metadata["size"]}
                    for path, metadata in sorted(files.items())
                },
            }
        )
    return canonical_json_sha256(payload)


def diff_tree_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[str]]:
    before_paths = set(before)
    after_paths = set(after)
    return {
        "created": sorted(after_paths - before_paths),
        "changed": sorted(path for path in before_paths & after_paths if before[path]["sha256"] != after[path]["sha256"]),
        "deleted": sorted(before_paths - after_paths),
    }


def workspace_diff_details(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    delta = diff_tree_snapshots(before, after)
    details: dict[str, Any] = {**delta, "files": {}}
    for path in [*delta["created"], *delta["changed"], *delta["deleted"]]:
        old = before.get(path)
        new = after.get(path)
        entry = {
            "before_sha256": old["sha256"] if old else None,
            "after_sha256": new["sha256"] if new else None,
            "before_size": old["size"] if old else None,
            "after_size": new["size"] if new else None,
        }
        if (old is None or old.get("text") is not None) and (new is None or new.get("text") is not None):
            entry["unified_diff"] = "".join(
                difflib.unified_diff(
                    (old.get("text", "") if old else "").splitlines(keepends=True),
                    (new.get("text", "") if new else "").splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
        details["files"][path] = entry
    return details


def mutation_diagnostic(contract: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    mutated = set(delta["created"] + delta["changed"] + delta["deleted"])
    required_missing = sorted(path for path in contract["required_paths"] if path not in mutated)
    forbidden_hit = sorted(
        path for path in mutated if any(fnmatch.fnmatch(path, pattern) for pattern in contract["forbidden_paths"])
    )
    mode = contract["mode"]
    passed = not required_missing and not forbidden_hit
    if mode == "required":
        passed = passed and bool(mutated)
    elif mode == "forbidden":
        passed = passed and not mutated
    return {
        "passed": passed,
        "mode": mode,
        "mutated_paths": sorted(mutated),
        "required_missing": required_missing,
        "forbidden_hit": forbidden_hit,
    }


def parse_final_response(raw: str) -> str:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"agent final response is not JSON: {exc}") from exc
    if not isinstance(value, dict) or set(value) != {"final_response"}:
        raise ValidationError("agent final response must contain only final_response")
    return require_string(value["final_response"], "final_response")


def build_codex_command(
    agent_command: str,
    *,
    model: str,
    reasoning_effort: str,
    service_tier: str | None,
    workspace: Path,
    schema_path: Path,
    output_path: Path,
) -> list[str]:
    command = shlex.split(agent_command)
    if not command:
        raise ValidationError("agent command must not be empty")
    command.extend(["--model", model, "-c", f'model_reasoning_effort="{reasoning_effort}"'])
    if service_tier:
        command.extend(["-c", f'service_tier="{service_tier}"'])
    command.extend(
        [
            "-c",
            "mcp_servers={}",
            "--json",
            "--disable",
            "plugins",
            "--ephemeral",
            "--ignore-user-config",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "--cd",
            str(workspace),
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            "-",
        ]
    )
    return command


def execute_with_transport_replacement(
    executor: Callable[[int], dict[str, Any]],
) -> list[dict[str, Any]]:
    attempts = [executor(1)]
    first = attempts[0]
    if first.get("status") == "agent_failure" and first.get("failure_type") in {"agent", "transport"}:
        attempts.append(executor(2))
    return attempts


def build_fixture_health_packet(cases: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    mapping: dict[str, Any] = {"schema_version": 1, "samples": {}}
    for case in cases:
        for category in sorted(SEMANTIC_FIXTURE_CATEGORIES):
            expected_verdict = "pass" if category == "positive" else "fail"
            for index, response in enumerate(case["semantic_fixtures"][category], 1):
                identity = f"fixture:{case['id']}:{category}:{index}"
                sample_id = f"F-{sha256_text(identity)[:12]}"
                response_sha256 = sha256_text(response)
                samples.append(
                    {
                        "sample_id": sample_id,
                        "response_sha256": response_sha256,
                        "user_prompt": case["prompt"],
                        "expected_behavior": case["expected_behavior"],
                        "forbidden_behavior": case["forbidden_behavior"],
                        "rubric": case["rubric"],
                        "mutation_contract": case["mutation_contract"],
                        "response": response,
                    }
                )
                mapping["samples"][sample_id] = {
                    "case_id": case["id"],
                    "category": category,
                    "index": index,
                    "response_sha256": response_sha256,
                    "expected_verdict": expected_verdict,
                }
    samples.sort(key=lambda item: item["sample_id"])
    return {"schema_version": 1, "methodology": "single_agent_exploratory", "samples": samples}, mapping


def validate_fixture_adjudications(rows: list[dict[str, Any]], mapping: dict[str, Any]) -> None:
    expected = mapping.get("samples", {})
    actual_ids = [row.get("sample_id") for row in rows]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected):
        raise ValidationError("fixture adjudications must cover every sample exactly once")
    for row in rows:
        sample = expected[row["sample_id"]]
        if row.get("response_sha256") != sample["response_sha256"]:
            raise ValidationError(f"fixture response hash mismatch: {row['sample_id']}")
        if row.get("verdict") != sample["expected_verdict"]:
            raise ValidationError(f"fixture health miss: {row['sample_id']}")


def build_blind_packets(
    cases: list[dict[str, Any]], records: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cases_by_id = {case["id"]: case for case in cases}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    mapping: dict[str, Any] = {"schema_version": 1, "samples": {}, "packets": {}}
    for record in records:
        grouped[record["case_id"]].append(record)
    packets = []
    for case_id in sorted(grouped):
        case = cases_by_id[case_id]
        packet_id = f"P-{sha256_text('packet:' + case_id)[:12]}"
        responses = []
        for record in sorted(grouped[case_id], key=lambda item: item["response_sha256"]):
            responses.append(
                {
                    "sample_id": record["sample_id"],
                    "response_sha256": record["response_sha256"],
                    "final_response": record["final_response"],
                }
            )
            mapping["samples"][record["sample_id"]] = {
                "case_id": case_id,
                "bundle": record["bundle"],
                "repetition": record["repetition"],
                "response_sha256": record["response_sha256"],
                "mutation_diagnostic": record["mutation_diagnostic"],
            }
        mapping["packets"][packet_id] = {"case_id": case_id}
        packets.append(
            {
                "schema_version": 1,
                "packet_id": packet_id,
                "methodology": "single_agent_exploratory",
                "independent": False,
                "publication_grade": False,
                "user_prompt": case["prompt"],
                "expected_behavior": case["expected_behavior"],
                "forbidden_behavior": case["forbidden_behavior"],
                "rubric": case["rubric"],
                "mutation_contract": case["mutation_contract"],
                "responses": responses,
            }
        )
    return packets, mapping


def build_expansion_plan(rows: list[dict[str, Any]], expand_to: int = 5) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row["case_id"]][row["bundle"]].append(row)
    expansion: list[dict[str, Any]] = []
    for case_id, by_bundle in sorted(grouped.items()):
        repetitions = max(row["repetition"] for values in by_bundle.values() for row in values)
        if repetitions >= expand_to:
            continue
        pass_counts = {bundle: sum(row["verdict"] == "pass" for row in by_bundle.get(bundle, [])) for bundle in BUNDLES}
        has_variance = any(len({row["verdict"] for row in by_bundle.get(bundle, [])}) > 1 for bundle in BUNDLES)
        has_ambiguous = any(row["verdict"] == "ambiguous" for values in by_bundle.values() for row in values)
        if len(set(pass_counts.values())) > 1 or has_variance or has_ambiguous:
            for bundle in BUNDLES:
                for repetition in range(repetitions + 1, expand_to + 1):
                    expansion.append(make_cell(case_id, bundle, repetition))
    return expansion


def classify_case_decision(
    pass_counts: dict[str, int],
    *,
    repetitions: int,
    current_defects: list[str],
    has_static_trace: bool,
) -> dict[str, str]:
    current = pass_counts.get("current", 0)
    previous = pass_counts.get("previous", 0)
    empty = pass_counts.get("empty", 0)
    repeated_defect = max(Counter(item for item in current_defects if item).values(), default=0) >= 2
    previous_delta = previous - current
    if repetitions < 5 and abs(previous_delta) >= 1:
        version_result = "inconclusive_pending_expansion"
    elif previous_delta >= 2 and repeated_defect and has_static_trace:
        version_result = "probable_v414_regression"
    elif previous_delta <= -2:
        version_result = "probable_v414_improvement"
    elif abs(previous_delta) <= 1:
        version_result = "no_detectable_change"
    else:
        version_result = "inconclusive"
    if repetitions < 5 and abs(current - empty) >= 1:
        instruction_result = "inconclusive_pending_expansion"
    else:
        instruction_result = "instruction_lift" if current - empty >= 2 else "not_demonstrated"
    return {"v414_vs_v413": version_result, "instruction_lift": instruction_result}


def resolve_repo_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def validate_manifest_integrity(manifest: dict[str, Any]) -> None:
    try:
        call_plan = manifest["call_plan"]
        primary = call_plan["primary"]
        if canonical_json_sha256(primary) != call_plan["sha256"]:
            raise ValidationError("primary call plan hash mismatch")
        cell_ids = [cell["cell_id"] for cell in primary]
        sample_ids = [cell["sample_id"] for cell in primary]
        if len(cell_ids) != len(set(cell_ids)) or len(sample_ids) != len(set(sample_ids)):
            raise ValidationError("primary call plan identifiers must be unique")
        if "expansion" in call_plan:
            expansion = call_plan["expansion"]
            if canonical_json_sha256(expansion) != call_plan.get("expansion_sha256"):
                raise ValidationError("expansion call plan hash mismatch")
        for bundle in BUNDLES:
            bundle_record = manifest["bundles"][bundle]
            if sha256_text(bundle_record["contents"]) != bundle_record["sha256"]:
                raise ValidationError(f"instruction bundle hash mismatch: {bundle}")
    except (KeyError, TypeError) as exc:
        raise ValidationError(f"malformed instruction-lift manifest: {exc}") from exc


def load_presets(path: Path) -> dict[str, dict[str, Any]]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValidationError("presets file must contain an object")
    return value


def git_value(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo_root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode != 0:
        raise ValidationError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def probe_agent_version(agent_command: str) -> str:
    executable = shlex.split(agent_command)
    if not executable:
        raise ValidationError("agent command must not be empty")
    completed = subprocess.run([executable[0], "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode != 0:
        raise ValidationError(f"agent version probe failed: {completed.stderr.strip()}")
    return (completed.stdout.strip() or completed.stderr.strip()).splitlines()[-1]


def validate_frozen_inputs(repo_root: Path, manifest: dict[str, Any]) -> None:
    validate_manifest_integrity(manifest)
    inputs = manifest["inputs"]
    for label, raw_path in inputs["frozen_files"].items():
        path = repo_root / raw_path["path"]
        if file_sha256(path) != raw_path["sha256"]:
            raise ValidationError(f"frozen input drift: {label}")
    if load_previous_instructions(repo_root, manifest["bundles"]["previous"]["ref"]) != manifest["bundles"]["previous"]["contents"]:
        raise ValidationError("previous instruction bundle drift")
    cases_path = repo_root / inputs["holdout_cases"]["path"]
    schema_path = repo_root / inputs["response_schema"]["path"]
    runner_path = repo_root / inputs["holdout_runner"]["path"]
    if file_sha256(cases_path) != inputs["holdout_cases"]["sha256"]:
        raise ValidationError("holdout catalog drift")
    if file_sha256(schema_path) != inputs["response_schema"]["sha256"]:
        raise ValidationError("holdout response schema drift")
    if file_sha256(runner_path) != inputs["holdout_runner"]["sha256"]:
        raise ValidationError("holdout runner drift")
    cases = load_and_validate_cases(repo_root, cases_path)
    if fixture_set_sha256(repo_root, cases) != inputs["fixture_set_sha256"]:
        raise ValidationError("holdout fixture bytes drift")
    prompt_hash = sha256_text(build_neutral_prompt("{INSTRUCTIONS}", {"prompt": "{USER_TASK}"}))
    if prompt_hash != inputs["prompt_template_sha256"]:
        raise ValidationError("holdout prompt template drift")


def command_validate(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    cases = load_and_validate_cases(repo_root, Path(args.cases))
    validate_response_schema(resolve_repo_path(repo_root, Path(args.schema)))
    previous = load_previous_instructions(repo_root, args.previous_ref)
    print(
        f"instruction-lift validation ok cases={len(cases)} changed_rule=6 controls=2 "
        f"semantic_fixtures={sum(sum(len(values) for values in case['semantic_fixtures'].values()) for case in cases)} "
        f"previous_sha256={sha256_text(previous)}"
    )
    return 0


def command_plan(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    cases_path = resolve_repo_path(repo_root, Path(args.cases))
    schema_path = resolve_repo_path(repo_root, Path(args.schema))
    presets_path = resolve_repo_path(repo_root, Path(args.presets))
    cases = load_and_validate_cases(repo_root, cases_path)
    validate_response_schema(schema_path)
    if args.jobs != 1:
        raise ValidationError("instruction-lift primary calls must use --jobs 1")
    presets = load_presets(presets_path)
    if args.preset not in presets:
        raise ValidationError(f"unknown preset: {args.preset}")
    preset = presets[args.preset]
    previous = load_previous_instructions(repo_root, args.previous_ref)
    current = (repo_root / INSTRUCTION_PATH).read_text(encoding="utf-8")
    output_dir = resolve_repo_path(repo_root, Path(args.output_dir))
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        raise ValidationError(f"refusing to overwrite existing plan: {manifest_path}")
    cells = build_call_matrix(cases, args.repetitions)
    fixture_packet, fixture_mapping = build_fixture_health_packet(cases)
    manifest = {
        "schema_version": 1,
        "status": "planned",
        "methodology": "single_agent_exploratory",
        "independent": False,
        "publication_grade": False,
        "created_utc": utc_now(),
        "repo": {
            "root": str(repo_root),
            "head": git_value(repo_root, "rev-parse", "HEAD"),
            "branch": git_value(repo_root, "branch", "--show-current"),
            "status_short": git_value(repo_root, "status", "--short").splitlines(),
        },
        "inputs": {
            "frozen_files": {
                "instructions": {"path": str(INSTRUCTION_PATH), "sha256": file_sha256(repo_root / INSTRUCTION_PATH)},
                "presets": {"path": str(presets_path.relative_to(repo_root)), "sha256": file_sha256(presets_path)},
            },
            "holdout_cases": {"path": str(cases_path.relative_to(repo_root)), "sha256": file_sha256(cases_path)},
            "response_schema": {"path": str(schema_path.relative_to(repo_root)), "sha256": file_sha256(schema_path)},
            "holdout_runner": {
                "path": str(Path(__file__).resolve().relative_to(repo_root)),
                "sha256": file_sha256(Path(__file__).resolve()),
            },
            "fixture_set_sha256": fixture_set_sha256(repo_root, cases),
            "prompt_template_sha256": sha256_text(build_neutral_prompt("{INSTRUCTIONS}", {"prompt": "{USER_TASK}"})),
        },
        "bundles": {
            "current": {"sha256": sha256_text(current), "contents": current},
            "previous": {"ref": args.previous_ref, "sha256": sha256_text(previous), "contents": previous},
            "empty": {"sha256": sha256_text(""), "contents": ""},
        },
        "runtime": {
            "agent_command": args.agent_command,
            "agent_version": probe_agent_version(args.agent_command),
            "preset": args.preset,
            "resolved_preset": preset,
            "jobs": 1,
            "timeout_seconds": args.case_timeout_seconds,
            "quality_judge": False,
            "max_transport_replacements_per_cell": 1,
        },
        "call_plan": {"initial_repetitions": args.repetitions, "primary": cells, "sha256": canonical_json_sha256(cells)},
        "progress": {"complete": 0, "incomplete": 0, "model_calls": 0},
    }
    fixture_packet_path = output_dir / "fixture-health-packet.json"
    fixture_mapping_path = output_dir / "fixture-health-mapping.json"
    write_json(fixture_packet_path, fixture_packet)
    write_json(fixture_mapping_path, fixture_mapping)
    manifest["fixture_health"] = {
        "packet": {"path": fixture_packet_path.name, "sha256": file_sha256(fixture_packet_path)},
        "mapping": {"path": fixture_mapping_path.name, "sha256": file_sha256(fixture_mapping_path)},
        "samples": len(fixture_packet["samples"]),
    }
    write_json(manifest_path, manifest)
    print(f"planned cells={len(cells)} manifest={manifest_path}")
    return 0


def run_attempt(
    repo_root: Path,
    case: dict[str, Any],
    cell: dict[str, Any],
    manifest: dict[str, Any],
    output_dir: Path,
    attempt: int,
) -> dict[str, Any]:
    attempt_dir = output_dir / "primary" / cell["cell_id"] / f"attempt-{attempt}"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="instruction-lift-") as tmp:
        workspace = Path(tmp) / "workspace"
        materialize_workspace(
            repo_root,
            case,
            bundle=cell["bundle"],
            previous_ref=manifest["bundles"]["previous"]["ref"],
            destination=workspace,
        )
        before = snapshot_tree(workspace, ignored_paths=BUNDLE_ONLY_PATHS)
        final_path = workspace / "final-message.json"
        prompt = build_neutral_prompt(manifest["bundles"][cell["bundle"]]["contents"], case)
        preset = manifest["runtime"]["resolved_preset"]
        command = build_codex_command(
            manifest["runtime"]["agent_command"],
            model=preset["model"],
            reasoning_effort=preset["reasoning_effort"],
            service_tier=preset.get("service_tier"),
            workspace=workspace,
            schema_path=workspace / DEFAULT_SCHEMA,
            output_path=final_path,
        )
        timed_out = False
        try:
            completed = subprocess.run(
                command,
                cwd=repo_root,
                text=True,
                input=prompt,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=manifest["runtime"]["timeout_seconds"],
            )
            returncode = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode = 124
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        after = snapshot_tree(workspace, ignored_paths=BUNDLE_ONLY_PATHS)
        delta = workspace_diff_details(before, after)
        (attempt_dir / "events.jsonl").write_text(stdout, encoding="utf-8")
        (attempt_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
        write_json(attempt_dir / "workspace-diff.json", delta)
        raw_final = final_path.read_text(encoding="utf-8") if final_path.exists() else ""
        if raw_final:
            (attempt_dir / "final-message.json").write_text(raw_final, encoding="utf-8")
        base = {
            "attempt": attempt,
            "returncode": returncode,
            "timed_out": timed_out,
            "command": command,
            "prompt_sha256": sha256_text(prompt),
            "workspace_diff": delta,
            "mutation_diagnostic": mutation_diagnostic(case["mutation_contract"], delta),
        }
        if returncode != 0 or not raw_final:
            return {**base, "status": "agent_failure", "failure_type": "transport"}
        try:
            final_response = parse_final_response(raw_final)
        except ValidationError as exc:
            return {**base, "status": "agent_failure", "failure_type": "transport", "parse_error": str(exc)}
        return {
            **base,
            "status": "complete",
            "failure_type": None,
            "final_response": final_response,
            "response_sha256": sha256_text(final_response),
        }


def update_manifest_progress(manifest_path: Path, manifest: dict[str, Any], output_dir: Path) -> None:
    records = [read_json(path) for path in (output_dir / "primary").glob("*/record.json")]
    manifest["progress"] = {
        "complete": sum(record.get("status") == "complete" for record in records),
        "incomplete": sum(record.get("status") != "complete" for record in records),
        "model_calls": sum(len(record.get("attempts", [])) for record in records),
        "updated_utc": utc_now(),
    }
    planned_total = len(manifest["call_plan"]["primary"]) + len(manifest["call_plan"].get("expansion", []))
    if manifest["progress"]["complete"] == planned_total:
        manifest["status"] = "expansion_complete" if manifest["call_plan"].get("expansion") else "primary_complete"
    write_json(manifest_path, manifest)


def command_run(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    output_dir = resolve_repo_path(repo_root, Path(args.output_dir))
    manifest_path = output_dir / "manifest.json"
    manifest = read_json(manifest_path)
    validate_frozen_inputs(repo_root, manifest)
    for label in ["packet", "mapping"]:
        artifact = manifest["fixture_health"][label]
        verify_artifact_hash(output_dir / artifact["path"], artifact["sha256"], f"fixture health {label}")
    cases = load_and_validate_cases(repo_root, Path(manifest["inputs"]["holdout_cases"]["path"]))
    cases_by_id = {case["id"]: case for case in cases}
    fixture_rows = read_jsonl(resolve_repo_path(repo_root, Path(args.fixture_adjudications)))
    validate_fixture_adjudications(fixture_rows, read_json(output_dir / "fixture-health-mapping.json"))
    cells = list(manifest["call_plan"]["primary"])
    if args.include_expansion:
        if "expansion" not in manifest["call_plan"]:
            raise ValidationError("no frozen expansion plan is available")
        expansion_artifact = manifest["call_plan"]["expansion_artifact"]
        verify_artifact_hash(
            output_dir / expansion_artifact["path"],
            expansion_artifact["sha256"],
            "expansion plan",
        )
        cells.extend(manifest["call_plan"]["expansion"])
    for index, cell in enumerate(cells, 1):
        record_path = output_dir / "primary" / cell["cell_id"] / "record.json"
        if record_path.exists() and read_json(record_path).get("status") == "complete":
            continue
        print(f"primary index={index}/{len(cells)} cell={cell['cell_id']}", flush=True)
        attempts = execute_with_transport_replacement(
            lambda attempt: run_attempt(repo_root, cases_by_id[cell["case_id"]], cell, manifest, output_dir, attempt)
        )
        final = attempts[-1]
        record = {
            "schema_version": 1,
            **cell,
            "status": final["status"],
            "failure_type": final.get("failure_type"),
            "final_response": final.get("final_response"),
            "response_sha256": final.get("response_sha256"),
            "mutation_diagnostic": final["mutation_diagnostic"],
            "attempts": attempts,
        }
        write_json(record_path, record)
        update_manifest_progress(manifest_path, manifest, output_dir)
        if record["status"] != "complete":
            print(f"failure_type=agent cell={cell['cell_id']} attempts={len(attempts)}", file=sys.stderr)
            return 3
    return 0


def load_complete_records(output_dir: Path, expected_cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = [read_json(path) for path in sorted((output_dir / "primary").glob("*/record.json"))]
    expected_ids = {cell["cell_id"] for cell in expected_cells}
    actual_ids = {record.get("cell_id") for record in records}
    if actual_ids != expected_ids:
        raise ValidationError("primary record set does not match the frozen call plan")
    if not records or any(record.get("status") != "complete" for record in records):
        raise ValidationError("packetize requires complete primary records")
    return records


def command_packetize(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    output_dir = resolve_repo_path(repo_root, Path(args.output_dir))
    manifest_path = output_dir / "manifest.json"
    manifest = read_json(manifest_path)
    validate_frozen_inputs(repo_root, manifest)
    cases = load_and_validate_cases(repo_root, Path(manifest["inputs"]["holdout_cases"]["path"]))
    expected_cells = list(manifest["call_plan"]["primary"])
    if "expansion" in manifest["call_plan"]:
        expected_cells.extend(manifest["call_plan"]["expansion"])
    records = load_complete_records(output_dir, expected_cells)
    packets, mapping = build_blind_packets(cases, records)
    packet_dir = output_dir / "review-packets"
    for packet in packets:
        write_json(packet_dir / f"{packet['packet_id']}.json", packet)
    mapping_path = output_dir / "private-review-mapping.json"
    write_json(mapping_path, mapping)
    manifest["review_artifacts"] = {
        "mapping": {"path": mapping_path.name, "sha256": file_sha256(mapping_path)},
        "packets_sha256": canonical_json_sha256(packets),
        "packet_count": len(packets),
        "response_count": len(records),
    }
    manifest["status"] = "awaiting_semantic_review"
    write_json(manifest_path, manifest)
    print(f"packetized packets={len(packets)} responses={len(records)}")
    return 0


def validate_response_adjudications(rows: list[dict[str, Any]], mapping: dict[str, Any]) -> list[dict[str, Any]]:
    expected = mapping["samples"]
    actual_ids = [row.get("sample_id") for row in rows]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected):
        raise ValidationError("response adjudications must cover every sample exactly once")
    unblinded = []
    for row in rows:
        sample = expected[row["sample_id"]]
        if row.get("response_sha256") != sample["response_sha256"]:
            raise ValidationError(f"response hash mismatch: {row['sample_id']}")
        if row.get("verdict") not in VERDICTS:
            raise ValidationError(f"invalid verdict: {row['sample_id']}")
        unblinded.append({**row, **sample})
    return unblinded


def command_summarize(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    output_dir = resolve_repo_path(repo_root, Path(args.output_dir))
    manifest_path = output_dir / "manifest.json"
    manifest = read_json(manifest_path)
    validate_frozen_inputs(repo_root, manifest)
    mapping_artifact = manifest.get("review_artifacts", {}).get("mapping")
    if not mapping_artifact:
        raise ValidationError("packetize must freeze review artifacts before summarize")
    mapping_path = output_dir / mapping_artifact["path"]
    verify_artifact_hash(mapping_path, mapping_artifact["sha256"], "private review mapping")
    cases = load_and_validate_cases(repo_root, Path(manifest["inputs"]["holdout_cases"]["path"]))
    cases_by_id = {case["id"]: case for case in cases}
    rows = read_jsonl(resolve_repo_path(repo_root, Path(args.adjudications)))
    unblinded = validate_response_adjudications(rows, read_json(mapping_path))
    expansion = build_expansion_plan(unblinded, expand_to=5)
    expansion_path = output_dir / "expansion-plan.json"
    existing_expansion = manifest["call_plan"].get("expansion")
    if existing_expansion is None:
        write_json(expansion_path, {"schema_version": 1, "cells": expansion})
        manifest["call_plan"]["expansion"] = expansion
        manifest["call_plan"]["expansion_sha256"] = canonical_json_sha256(expansion)
        manifest["call_plan"]["expansion_artifact"] = {
            "path": expansion_path.name,
            "sha256": file_sha256(expansion_path),
        }
    elif expansion and expansion != existing_expansion:
        raise ValidationError("recomputed expansion plan differs from the frozen expansion")
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in unblinded:
        by_case[row["case_id"]].append(row)
    results = {}
    for case_id, case_rows in sorted(by_case.items()):
        pass_counts = {
            bundle: sum(row["verdict"] == "pass" for row in case_rows if row["bundle"] == bundle)
            for bundle in BUNDLES
        }
        repetitions = max(row["repetition"] for row in case_rows)
        current_defects = [
            str(row.get("material_defect", ""))
            for row in case_rows
            if row["bundle"] == "current" and row["verdict"] != "pass"
        ]
        results[case_id] = {
            "pass_counts": pass_counts,
            "repetitions": repetitions,
            "decision": classify_case_decision(
                pass_counts,
                repetitions=repetitions,
                current_defects=current_defects,
                has_static_trace=bool(cases_by_id[case_id]["v413_trace"]),
            ),
        }
    bundle_totals = {
        bundle: sum(row["verdict"] == "pass" for row in unblinded if row["bundle"] == bundle) for bundle in BUNDLES
    }
    objective_diagnostics = {
        bundle: {
            "total": sum(row["bundle"] == bundle for row in unblinded),
            "passed": sum(
                row["bundle"] == bundle and row["mutation_diagnostic"]["passed"] for row in unblinded
            ),
        }
        for bundle in BUNDLES
    }
    global_result = (
        "holdout_not_discriminating"
        if not expansion and len(set(bundle_totals.values())) == 1
        else "semantic_difference_observed"
    )
    summary = {
        "schema_version": 1,
        "methodology": "single_agent_exploratory",
        "independent": False,
        "publication_grade": False,
        "bundle_totals": bundle_totals,
        "objective_diagnostics": objective_diagnostics,
        "global_result": global_result,
        "cases": results,
        "expansion_cells": len(expansion),
    }
    write_json(output_dir / "semantic-summary.json", summary)
    manifest["semantic_summary"] = {
        "path": "semantic-summary.json",
        "sha256": file_sha256(output_dir / "semantic-summary.json"),
        "adjudications_sha256": file_sha256(resolve_repo_path(repo_root, Path(args.adjudications))),
    }
    manifest["status"] = "expansion_required" if expansion else "semantic_complete"
    write_json(manifest_path, manifest)
    print(f"summarized responses={len(unblinded)} expansion_cells={len(expansion)} result={global_result}")
    return 0


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--presets", default=str(DEFAULT_PRESETS))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--previous-ref", default=DEFAULT_PREVIOUS_REF)

    plan = subparsers.add_parser("plan")
    plan.add_argument("--previous-ref", default=DEFAULT_PREVIOUS_REF)
    plan.add_argument("--repetitions", type=positive_int, default=3)
    plan.add_argument("--agent-command", required=True)
    plan.add_argument("--preset", default=DEFAULT_PRESET)
    plan.add_argument("--jobs", type=positive_int, default=1)
    plan.add_argument("--case-timeout-seconds", type=positive_int, default=900)
    plan.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))

    run = subparsers.add_parser("run")
    run.add_argument("--fixture-adjudications", required=True)
    run.add_argument("--include-expansion", action="store_true")
    run.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))

    packetize = subparsers.add_parser("packetize")
    packetize.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))

    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("--adjudications", required=True)
    summarize.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return {
            "validate": command_validate,
            "plan": command_plan,
            "run": command_run,
            "packetize": command_packetize,
            "summarize": command_summarize,
        }[args.command](args)
    except ValidationError as exc:
        print(f"failure_type=harness error={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
