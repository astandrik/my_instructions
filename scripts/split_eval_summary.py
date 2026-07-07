#!/usr/bin/env python3
"""Split a combined instruction-eval summary.json by result label."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_instruction_evals as evals


def read_summary(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise evals.ValidationError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise evals.ValidationError(f"{path}: summary must be an object")
    results = parsed.get("results")
    if not isinstance(results, list):
        raise evals.ValidationError(f"{path}: summary results must be a list")
    for record in results:
        if not isinstance(record, dict):
            raise evals.ValidationError(f"{path}: summary result must be an object")
        if not isinstance(record.get("case_id"), str):
            raise evals.ValidationError(f"{path}: summary result requires string case_id")
        if not isinstance(record.get("label"), str) or not record["label"]:
            raise evals.ValidationError(f"{path}: summary result requires non-empty string label")
    return parsed


def ordered_labels(results: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for record in results:
        label = record["label"]
        if label not in seen:
            seen.add(label)
            labels.append(label)
    return labels


def split_summary(summary: dict[str, Any], labels: list[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    results = summary["results"]
    selected = labels or ordered_labels(results)
    split: dict[str, list[dict[str, Any]]] = {}
    for label in selected:
        records = [dict(record) for record in results if record["label"] == label]
        if not records:
            raise evals.ValidationError(f"summary has no records for label: {label}")
        split[label] = records
    return split


def write_split_summaries(split: dict[str, list[dict[str, Any]]], output_dir: Path) -> dict[str, Path]:
    written: dict[str, Path] = {}
    for label, records in split.items():
        evals.write_summary(output_dir, label, records)
        written[label] = output_dir / evals.safe_label(label) / "summary.json"
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split an instruction eval summary.json by label.")
    parser.add_argument("--input", required=True, help="Combined summary.json from run_instruction_evals.py compare.")
    parser.add_argument("--output-dir", required=True, help="Directory where per-label summaries will be written.")
    parser.add_argument(
        "--label",
        action="append",
        help="Label to extract. Repeatable. Defaults to every label present in order of first appearance.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = read_summary(Path(args.input))
        split = split_summary(summary, args.label)
        written = write_split_summaries(split, Path(args.output_dir))
    except (evals.ValidationError, OSError) as exc:
        print(f"failure_type=harness error={exc}", file=sys.stderr)
        return 2
    for label, path in written.items():
        print(f"{label}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
