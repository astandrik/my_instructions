#!/usr/bin/env python3
"""Build README SVG infographics from saved instruction-eval artifacts."""

from __future__ import annotations

import argparse
import html
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_REFRESH_ROOT = Path(".eval-results/refresh-2026-07-05-v4.12-49-case-v1")
DEFAULT_EMPTY_ROOT = Path(".eval-results/refresh-2026-07-05-49-case-v1")
DEFAULT_V413_GPT_ROOT = Path(".eval-results/v4.13-final-gpt55-full-49-v11")
DEFAULT_V413_EXTERNAL_ROOT = Path(".eval-results/refresh-2026-07-07-v4.13-all-model-v1")
DEFAULT_CANONICAL_QUALITY_ROOT = Path(".eval-results/openai-canonical-judge-2026-07-07-v1")
DEFAULT_OUTPUT_DIR = Path("docs/assets/readme")
CASE_FILE = Path("evals/cases.jsonl")
SNAPSHOT_SCOPE = "Scope: v4.13 OpenAI-judged GPT/GLM/DeepSeek saved outputs; Grok/reference/no-instruction charts use labeled v4.12 saved snapshots."

INK = "#111827"
MUTED = "#64748b"
PANEL = "#ffffff"
BORDER = "#cbd5e1"
TRACK = "#f1f5f9"
CURRENT = "#2563eb"
BASELINE = "#be123c"
OPENHANDS = "#059669"
FABLE = "#db2777"
TIE = "#f59e0b"
INCONCLUSIVE = "#cbd5e1"
GOOD = "#16a34a"
WARN = "#dc2626"
GPT = "#334155"
CURRENT_FILL = "#bfdbfe"
BASELINE_FILL = "#fecdd3"
TIE_FILL = "#fef3c7"
INCONCLUSIVE_FILL = "#f1f5f9"

MODELS = [
    {
        "label": "GPT-5.5",
        "short": "GPT",
        "current": "current-gpt55/current/summary.json",
        "empty": "empty-gpt55/empty/summary.json",
        "prev_quality": "quality-prev-current-vs-new-current-gpt55/GPT-5.5-old-current-saved-model-quality/model-quality-summary.json",
        "empty_quality": "quality-empty-vs-current-gpt55/GPT-5.5-empty-saved-model-quality/model-quality-summary.json",
        "color": "#2563eb",
    },
    {
        "label": "GLM-5.2",
        "short": "GLM",
        "current": "merged/current-glm-5.2-merged/summary.json",
        "empty": "merged/empty-glm-5.2-merged/summary.json",
        "prev_quality": "quality-prev-current-vs-new-current-external/GLM-5.2-old-current-saved-model-quality/model-quality-summary.json",
        "empty_quality": "quality-empty-vs-current-glm-5.2/GLM-5.2-empty-saved-model-quality/model-quality-summary.json",
        "color": "#16a34a",
    },
    {
        "label": "Grok Build 0.1",
        "short": "Grok Build",
        "current": "merged/current-grok-build-0.1-merged/summary.json",
        "empty": "merged/empty-grok-build-0.1-merged/summary.json",
        "prev_quality": "quality-prev-current-vs-new-current-external/Grok-Build-0.1-old-current-saved-model-quality/model-quality-summary.json",
        "empty_quality": "quality-empty-vs-current-grok-build-0.1/Grok-Build-0.1-empty-saved-model-quality/model-quality-summary.json",
        "color": "#7c3aed",
    },
    {
        "label": "Grok 4.3",
        "short": "Grok 4.3",
        "current": "current-grok-4.3/current/summary.json",
        "empty": "empty-grok-4.3/empty/summary.json",
        "prev_quality": "quality-prev-current-vs-new-current-external/Grok-4.3-old-current-saved-model-quality/model-quality-summary.json",
        "empty_quality": "quality-empty-vs-current-grok-4.3/Grok-4.3-empty-saved-model-quality/model-quality-summary.json",
        "color": "#ea580c",
    },
    {
        "label": "DeepSeek V4 Flash",
        "short": "DeepSeek",
        "current": "current-deepseek-v4-flash/current/summary.json",
        "empty": "empty-deepseek-v4-flash/empty/summary.json",
        "prev_quality": "quality-prev-current-vs-new-current-external/DeepSeek-V4-Flash-old-current-saved-model-quality/model-quality-summary.json",
        "empty_quality": "quality-empty-vs-current-deepseek-v4-flash/DeepSeek-V4-Flash-empty-saved-model-quality/model-quality-summary.json",
        "color": "#0891b2",
    },
    {
        "label": "DeepSeek V4 thinking",
        "short": "DS thinking",
        "current": "current-deepseek-v4-flash-thinking/current/summary.json",
        "empty": "empty-deepseek-v4-flash-thinking/empty/summary.json",
        "prev_quality": "quality-prev-current-vs-new-current-external/DeepSeek-V4-Flash-thinking-old-current-saved-model-quality/model-quality-summary.json",
        "empty_quality": "quality-empty-vs-current-deepseek-v4-flash-thinking/DeepSeek-V4-Flash-thinking-empty-saved-model-quality/model-quality-summary.json",
        "color": "#0f766e",
    },
]

V413_MODELS = [
    {
        "label": "GPT-5.5",
        "short": "GPT",
        "previous": ("gpt", "split/compare-HEAD-current/baseline-HEAD/summary.json"),
        "current": ("gpt", "split/compare-HEAD-current/current/summary.json"),
        "prev_quality": "gpt/previous-saved-model-quality/model-quality-summary.json",
        "color": "#2563eb",
    },
    {
        "label": "GLM-5.2",
        "short": "GLM",
        "previous": ("external", "split/glm-5.2-absolute-v2/baseline-origin-main/summary.json"),
        "current": ("external", "split/glm-5.2-absolute-v2/current/summary.json"),
        "prev_quality": "glm/previous-saved-model-quality/model-quality-summary.json",
        "color": "#16a34a",
    },
    {
        "label": "DeepSeek V4 Flash",
        "short": "DeepSeek",
        "previous": ("external", "split/deepseek-v4-flash-absolute-v1/baseline-origin-main/summary.json"),
        "current": ("external", "split/deepseek-v4-flash-absolute-v1/current/summary.json"),
        "prev_quality": "deepseek/previous-saved-model-quality/model-quality-summary.json",
        "color": "#0891b2",
    },
    {
        "label": "DeepSeek V4 thinking",
        "short": "DS thinking",
        "previous": ("external", "split/deepseek-v4-flash-thinking-absolute-v1/baseline-origin-main/summary.json"),
        "current": ("external", "split/deepseek-v4-flash-thinking-absolute-v1/current/summary.json"),
        "prev_quality": "deepseek-thinking/previous-saved-model-quality/model-quality-summary.json",
        "color": "#0f766e",
    },
]

GPT_VS_EXTERNAL_CURRENT_QUALITY = "gpt-vs-external-current/gpt-current-saved-model-quality/model-quality-summary.json"
GPT_VS_EXTERNAL_PREVIOUS_QUALITY = "gpt-vs-external-previous/gpt-previous-saved-model-quality/model-quality-summary.json"

GPT_EXTERNAL_QUALITY = "quality-gpt55-vs-external-new-current/GPT-5.5-new-current-saved-model-quality/model-quality-summary.json"

REFERENCES = [
    {
        "model": "GPT-5.5",
        "short": "GPT",
        "reference": "OpenHands",
        "summary": "reference-openhands-gpt55/reference-openhands-agents/summary.json",
        "quality": "quality-reference-openhands-vs-current-gpt55/OpenHands-GPT-5.5-saved-model-quality/model-quality-summary.json",
    },
    {
        "model": "GPT-5.5",
        "short": "GPT",
        "reference": "Fable",
        "summary": "reference-claude-fable-gpt55/reference-claude-fable-5/summary.json",
        "quality": "quality-reference-claude-fable-vs-current-gpt55/Claude-Fable-GPT-5.5-saved-model-quality/model-quality-summary.json",
    },
    {
        "model": "GLM-5.2",
        "short": "GLM",
        "reference": "OpenHands",
        "summary": "reference-openhands-glm-5.2-zai/reference-openhands-agents/summary.json",
        "quality": "quality-reference-openhands-vs-current-glm-5.2/OpenHands-GLM-5.2-saved-model-quality/model-quality-summary.json",
    },
    {
        "model": "GLM-5.2",
        "short": "GLM",
        "reference": "Fable",
        "summary": "reference-claude-fable-glm-5.2-zai/reference-claude-fable-5/summary.json",
        "quality": "quality-reference-claude-fable-vs-current-glm-5.2/Claude-Fable-GLM-5.2-saved-model-quality/model-quality-summary.json",
    },
    {
        "model": "Grok Build 0.1",
        "short": "Grok Build",
        "reference": "OpenHands",
        "summary": "merged/reference-openhands-grok-build-0.1-merged/summary.json",
        "quality": "quality-reference-openhands-vs-current-grok-build-0.1/OpenHands-Grok-Build-0.1-saved-model-quality/model-quality-summary.json",
        "caveat": "2 provider residuals",
    },
    {
        "model": "Grok Build 0.1",
        "short": "Grok Build",
        "reference": "Fable",
        "summary": "merged/reference-claude-fable-grok-build-0.1-merged/summary.json",
        "quality": "quality-reference-claude-fable-vs-current-grok-build-0.1/Claude-Fable-Grok-Build-0.1-saved-model-quality/model-quality-summary.json",
        "caveat": "4 provider residuals",
    },
    {
        "model": "Grok 4.3",
        "short": "Grok 4.3",
        "reference": "OpenHands",
        "summary": "reference-openhands-grok-4.3-xai/reference-openhands-agents/summary.json",
        "quality": "quality-reference-openhands-vs-current-grok-4.3/OpenHands-Grok-4.3-saved-model-quality/model-quality-summary.json",
    },
    {
        "model": "Grok 4.3",
        "short": "Grok 4.3",
        "reference": "Fable",
        "summary": "reference-claude-fable-grok-4.3-xai/reference-claude-fable-5/summary.json",
        "quality": "quality-reference-claude-fable-vs-current-grok-4.3/Claude-Fable-Grok-4.3-saved-model-quality/model-quality-summary.json",
    },
    {
        "model": "DeepSeek V4 Flash",
        "short": "DeepSeek",
        "reference": "OpenHands",
        "summary": "reference-openhands-deepseek-v4-flash/reference-openhands-agents/summary.json",
        "quality": "quality-reference-openhands-vs-current-deepseek-v4-flash/OpenHands-DeepSeek-V4-Flash-saved-model-quality/model-quality-summary.json",
    },
    {
        "model": "DeepSeek V4 Flash",
        "short": "DeepSeek",
        "reference": "Fable",
        "summary": "reference-claude-fable-deepseek-v4-flash/reference-claude-fable-5/summary.json",
        "quality": "quality-reference-claude-fable-vs-current-deepseek-v4-flash/Claude-Fable-DeepSeek-V4-Flash-saved-model-quality/model-quality-summary.json",
    },
    {
        "model": "DeepSeek V4 thinking",
        "short": "DS thinking",
        "reference": "OpenHands",
        "summary": "reference-openhands-deepseek-v4-flash-thinking/reference-openhands-agents/summary.json",
        "quality": "quality-reference-openhands-vs-current-deepseek-v4-flash-thinking/OpenHands-DeepSeek-V4-Flash-thinking-saved-model-quality/model-quality-summary.json",
    },
    {
        "model": "DeepSeek V4 thinking",
        "short": "DS thinking",
        "reference": "Fable",
        "summary": "reference-claude-fable-deepseek-v4-flash-thinking/reference-claude-fable-5/summary.json",
        "quality": "quality-reference-claude-fable-vs-current-deepseek-v4-flash-thinking/Claude-Fable-DeepSeek-V4-Flash-thinking-saved-model-quality/model-quality-summary.json",
    },
]


def read_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"missing artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"missing case file: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def pct(value: float, total: float) -> float:
    return 0 if total == 0 else value / total


def svg_start(width: int, height: int, title: str, desc: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{esc(title)}</title>',
        f'<desc id="desc">{esc(desc)}</desc>',
        "<style>",
        "text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;letter-spacing:0}",
        ".title{font-size:30px;font-weight:700;fill:#111827}",
        ".subtitle{font-size:15px;fill:#64748b}",
        ".label{font-size:14px;font-weight:700;fill:#111827}",
        ".small{font-size:12px;fill:#64748b}",
        ".value{font-size:13px;font-weight:700;fill:#111827}",
        ".axis{font-size:11px;fill:#64748b}",
        ".cell{font-size:11px;font-weight:700;fill:#111827}",
        "</style>",
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f8fafc"/>',
    ]


def text(x: float, y: float, value: object, cls: str = "label", anchor: str | None = None) -> str:
    anchor_attr = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}"{anchor_attr}>{esc(value)}</text>'


def rect(x: float, y: float, width: float, height: float, fill: str, rx: float = 6, stroke: str | None = None) -> str:
    stroke_attr = f' stroke="{stroke}"' if stroke else ""
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(width, 0):.1f}" height="{height:.1f}" rx="{rx:.1f}" fill="{fill}"{stroke_attr}/>'


def line(x1: float, y1: float, x2: float, y2: float, color: str = "#e5e7eb") -> str:
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="1"/>'


def circle(cx: float, cy: float, radius: float, fill: str, stroke: str = "#ffffff", stroke_width: float = 2) -> str:
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width:.1f}"/>'


def panel(x: float, y: float, width: float, height: float) -> list[str]:
    return [rect(x, y, width, height, PANEL, rx=10, stroke=BORDER)]


def footer(width: int, y: float, source: str) -> list[str]:
    return [
        line(32, y - 30, width - 32, y - 30),
        text(32, y - 12, SNAPSHOT_SCOPE, "small"),
        text(32, y, source, "small"),
        text(width - 32, y, "Generated by scripts/build_readme_infographics.py", "small", anchor="end"),
    ]


def write_svg(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def compact_model_label(model: str) -> str:
    return {"Grok Build": "GB", "Grok 4.3": "G4", "DeepSeek": "DS", "DS thinking": "DSt"}.get(model, model)


def compact_reference_label(reference: str) -> str:
    return "OH" if reference == "OpenHands" else "F"


def short_score(value: float) -> str:
    rounded = round(value)
    return "0" if rounded == 0 else f"{rounded:+d}"


def quality_summary(refresh_root: Path, rel_path: str) -> dict[str, Any]:
    data = read_json(refresh_root / rel_path)
    pair = data["pairs"][0]
    aggregate = pair["aggregate"]
    return {
        "aggregate": aggregate,
        "pair_path": Path(pair["quality_json"]),
        "baseline_label": data["baseline_label"],
        "candidate_label": pair["candidate_label"],
    }


def quality_summary_with_fallback(primary_root: Path, fallback_root: Path, rel_path: str) -> tuple[dict[str, Any], str]:
    if (primary_root / rel_path).exists():
        return quality_summary(primary_root, rel_path), "same refresh"
    return quality_summary(fallback_root, rel_path), "reused quality"


def summary_counts(refresh_root: Path, rel_path: str) -> dict[str, int]:
    data = read_json(refresh_root / rel_path)
    return {
        "passed": int(data["passed"]),
        "failed": int(data["failed"]),
        "total": int(data["total"]),
        "agent": sum(1 for item in data["results"] if item["failure_type"] == "agent"),
    }


def summary_counts_with_fallback(primary_root: Path, fallback_root: Path, rel_path: str) -> tuple[dict[str, int], str]:
    if (primary_root / rel_path).exists():
        return summary_counts(primary_root, rel_path), "same refresh"
    return summary_counts(fallback_root, rel_path), "reused empty"


def v413_source_root(source: str, gpt_root: Path, external_root: Path) -> Path:
    if source == "gpt":
        return gpt_root
    if source == "external":
        return external_root
    raise ValueError(f"unknown v4.13 source root: {source}")


def v413_summary_counts(gpt_root: Path, external_root: Path, source_path: tuple[str, str]) -> dict[str, int]:
    source, rel_path = source_path
    return summary_counts(v413_source_root(source, gpt_root, external_root), rel_path)


def v413_model_rows(gpt_root: Path, external_root: Path, quality_root: Path) -> list[dict[str, Any]]:
    rows = []
    for model in V413_MODELS:
        previous = v413_summary_counts(gpt_root, external_root, model["previous"])
        current = v413_summary_counts(gpt_root, external_root, model["current"])
        quality = quality_summary(quality_root, model["prev_quality"])
        aggregate = quality["aggregate"]
        rows.append(
            {
                **model,
                "total": aggregate["total"],
                "previous_passed": previous["passed"],
                "current_passed": current["passed"],
                "pass_delta": current["passed"] - previous["passed"],
                "wins": aggregate["winners"]["current"],
                "losses": aggregate["winners"]["baseline"],
                "ties": aggregate["winners"]["tie"],
                "inconclusive": aggregate["winners"]["inconclusive"],
                "quality_delta": aggregate["average_delta"],
                "candidate_score": aggregate["average_current_score"],
                "baseline_score": aggregate["average_baseline_score"],
                "judge_calls": aggregate["sources"].get("llm_judge", 0),
                "hard_gate_shortcuts": aggregate["sources"].get("hard_gate", 0),
                "pair_path": quality["pair_path"],
            }
        )
    return rows


def v413_gpt_external_rows(quality_root: Path, rel_path: str, prefix: str) -> list[dict[str, Any]]:
    data = read_json(quality_root / rel_path)
    labels = {
        f"{prefix}-glm": "GLM",
        f"{prefix}-deepseek": "DeepSeek",
        f"{prefix}-deepseek-thinking": "DS thinking",
    }
    rows = []
    for pair in data["pairs"]:
        aggregate = pair["aggregate"]
        winners = aggregate["winners"]
        rows.append(
            {
                "label": labels.get(pair["candidate_label"], pair["candidate_label"]),
                "candidate_label": pair["candidate_label"],
                "hard_passed": aggregate["candidate_passed"],
                "total": aggregate["total"],
                "wins": winners["current"],
                "gpt_wins": winners["baseline"],
                "ties": winners["tie"],
                "inconclusive": winners["inconclusive"],
                "delta": aggregate["average_delta"],
                "score": aggregate["average_current_score"],
                "judge_calls": aggregate["sources"].get("llm_judge", 0),
                "hard_gate_shortcuts": aggregate["sources"].get("hard_gate", 0),
                "pair_path": Path(pair["quality_json"]),
            }
        )
    order = ["GLM", "DeepSeek", "DS thinking"]
    return sorted(rows, key=lambda row: order.index(row["label"]) if row["label"] in order else 999)


def v413_model_gap_rows(quality_root: Path) -> list[dict[str, Any]]:
    previous = {row["label"]: row for row in v413_gpt_external_rows(quality_root, GPT_VS_EXTERNAL_PREVIOUS_QUALITY, "previous")}
    current = {row["label"]: row for row in v413_gpt_external_rows(quality_root, GPT_VS_EXTERNAL_CURRENT_QUALITY, "current")}
    rows = []
    for label in ["GLM", "DeepSeek", "DS thinking"]:
        prev_row = previous[label]
        current_row = current[label]
        rows.append(
            {
                "label": label,
                "previous": prev_row,
                "current": current_row,
                "gap_change": current_row["delta"] - prev_row["delta"],
                "pass_change": current_row["hard_passed"] - prev_row["hard_passed"],
            }
        )
    return rows


def model_rows(refresh_root: Path, empty_root: Path) -> list[dict[str, Any]]:
    rows = []
    for model in MODELS:
        current = summary_counts(refresh_root, model["current"])
        empty, empty_source = summary_counts_with_fallback(refresh_root, empty_root, model["empty"])
        quality = quality_summary(refresh_root, model["prev_quality"])
        empty_quality, empty_quality_source = quality_summary_with_fallback(refresh_root, empty_root, model["empty_quality"])
        aggregate = quality["aggregate"]
        empty_quality_aggregate = empty_quality["aggregate"]
        rows.append(
            {
                **model,
                "total": aggregate["total"],
                "current_passed": current["passed"],
                "old_passed": aggregate["baseline_passed"],
                "new_passed": aggregate["candidate_passed"],
                "pass_delta": aggregate["candidate_passed"] - aggregate["baseline_passed"],
                "wins": aggregate["winners"]["current"],
                "losses": aggregate["winners"]["baseline"],
                "ties": aggregate["winners"]["tie"],
                "inconclusive": aggregate["winners"]["inconclusive"],
                "quality_delta": aggregate["average_delta"],
                "agent": current["agent"],
                "empty_passed": empty["passed"],
                "empty_agent": empty["agent"],
                "empty_source": empty_source,
                "empty_delta": current["passed"] - empty["passed"],
                "empty_quality_delta": empty_quality_aggregate["average_delta"],
                "empty_quality_source": empty_quality_source,
            }
        )
    return rows


def gpt_external_rows(refresh_root: Path) -> list[dict[str, Any]]:
    data = read_json(refresh_root / GPT_EXTERNAL_QUALITY)
    labels = {
        "Grok-4.3-new-current": "Grok 4.3",
        "Grok-Build-0.1-new-current": "Grok Build",
        "DeepSeek-V4-Flash-new-current": "DeepSeek",
        "DeepSeek-V4-Flash-thinking-new-current": "DS thinking",
        "GLM-5.2-new-current": "GLM",
    }
    rows = []
    for pair in data["pairs"]:
        aggregate = pair["aggregate"]
        winners = aggregate["winners"]
        rows.append(
            {
                "label": labels.get(pair["candidate_label"], pair["candidate_label"]),
                "hard_passed": aggregate["candidate_passed"],
                "total": aggregate["total"],
                "wins": winners["current"],
                "gpt_wins": winners["baseline"],
                "ties": winners["tie"],
                "inconclusive": winners["inconclusive"],
                "delta": aggregate["average_delta"],
                "score": aggregate["average_current_score"],
            }
        )
    order = ["GLM", "Grok Build", "Grok 4.3", "DeepSeek", "DS thinking"]
    return sorted(rows, key=lambda row: order.index(row["label"]) if row["label"] in order else 999)


def reference_rows(refresh_root: Path) -> list[dict[str, Any]]:
    rows = []
    for item in REFERENCES:
        summary = summary_counts(refresh_root, item["summary"])
        quality = quality_summary(refresh_root, item["quality"])
        aggregate = quality["aggregate"]
        winners = aggregate["winners"]
        rows.append(
            {
                **item,
                "reference_passed": summary["passed"],
                "reference_agent": summary["agent"],
                "current_passed": aggregate["candidate_passed"],
                "total": aggregate["total"],
                "current_wins": winners["current"],
                "reference_wins": winners["baseline"],
                "ties": winners["tie"],
                "inconclusive": winners["inconclusive"],
                "delta": aggregate["average_delta"],
                "pair_path": quality["pair_path"],
            }
        )
    return rows


def draw_segments(
    lines: list[str],
    x: float,
    y: float,
    width: float,
    height: float,
    total: int,
    segments: list[tuple[int, str]],
) -> None:
    cursor = x
    for value, color in segments:
        segment_width = width * pct(value, total)
        if segment_width > 0:
            lines.append(rect(cursor, y, segment_width, height, color, rx=4))
        cursor += segment_width
    lines.append(rect(x, y, width, height, "none", rx=4, stroke="#e5e7eb"))


def render_instruction_lift(
    gpt_root: Path,
    external_root: Path,
    quality_root: Path,
    refresh_root: Path,
    output_dir: Path,
) -> None:
    rows = v413_model_rows(gpt_root, external_root, quality_root)
    references = reference_rows(refresh_root)
    gaps = v413_model_gap_rows(quality_root)
    gpt = next(row for row in rows if row["short"] == "GPT")
    non_gpt = [row for row in rows if row["short"] != "GPT"]
    glm_gap = next(row for row in gaps if row["label"] == "GLM")
    width = 1120
    height = 560
    lines = svg_start(
        width,
        height,
        "Instruction eval overview",
        "Headline answers across fresh v4.13 GPT/GLM/DeepSeek rows plus saved v4.12 context.",
    )
    lines.append(text(40, 56, "Instruction eval overview", "title"))
    lines.append(text(40, 84, "Read left to right: v4.13 improvement, external transfer, model gap, and reference-prompt context.", "subtitle"))
    card_w = 248
    cards = [
        (
            40,
            "GPT quality improved",
            f"{gpt['previous_passed']} -> {gpt['current_passed']} hard gates",
            f"quality {gpt['wins']}/{gpt['ties']}/{gpt['losses']}, avg {gpt['quality_delta']:+.1f}",
            CURRENT,
        ),
        (
            310,
            "External transfer mixed",
            f"{sum(1 for row in non_gpt if row['pass_delta'] > 0)}/{len(non_gpt)} hard-gate lifts",
            "GLM slight up; DS up; DSt down",
            WARN,
        ),
        (
            580,
            "Model gap vs GPT",
            f"GLM current gap {glm_gap['current']['delta']:+.1f}",
            f"gap {glm_gap['gap_change']:+.1f}; DS gaps still large",
            TIE,
        ),
        (
            850,
            "Reference context",
            f"{sum(1 for row in references if row['delta'] > 0)}/{len(references)} aggregate pairs",
            "saved v4.12 cases expose regressions",
            BASELINE,
        ),
    ]
    for x, title, primary, secondary, color in cards:
        lines.extend(panel(x, 122, card_w, 150))
        lines.append(rect(x + 24, 146, 38, 8, color, rx=4))
        lines.append(text(x + 24, 180, title, "label"))
        lines.append(text(x + 24, 214, primary, "value"))
        lines.append(text(x + 24, 242, secondary, "small"))
    lines.extend(panel(40, 304, 1040, 150))
    lines.append(text(72, 342, "Bottom line", "label"))
    lines.append(text(72, 374, f"GPT is the cleanest v4.13 win: {gpt['current_passed']}/49 hard gates and {gpt['wins']}/{gpt['ties']}/{gpt['losses']} quality split versus previous.", "value"))
    lines.append(text(72, 402, "GLM stays close but not better than GPT; DeepSeek Flash improves from previous, while DeepSeek thinking regresses.", "value"))
    lines.append(text(72, 430, "Grok v4.13 full rows are not included here; existing Grok charts are saved v4.12 empty/current context only.", "value"))
    lines.extend(footer(width, 532, "Source: v4.13 saved summaries, OpenAI/Codex saved-quality judge, and labeled v4.12 reference context"))
    lines.append("</svg>")
    write_svg(output_dir / "instruction-lift.svg", lines)


def render_empty_current_lift(refresh_root: Path, empty_root: Path, output_dir: Path) -> None:
    rows = model_rows(refresh_root, empty_root)
    order = {"GPT": 0, "GLM": 1, "Grok Build": 2, "DeepSeek": 3, "Grok 4.3": 4, "DS thinking": 5}
    rows = sorted(rows, key=lambda row: order.get(row["short"], 99))
    width = 1120
    height = 650
    axis_x = 260
    axis_w = 520
    right_x = 794
    lines = svg_start(
        width,
        height,
        "Instruction lift across models",
        "Hard-gate lift from empty bundle to current instructions across tested models.",
    )
    lines.append(text(40, 56, "Instruction lift across models", "title"))
    lines.append(text(40, 84, "49 cases. Hard-gate passes improve for every tested model; quality deltas use latest saved empty-vs-current aggregates.", "subtitle"))
    lines.extend(panel(40, 110, 1040, 430))
    lines.append(text(72, 144, "Model", "axis"))
    lines.append(text(axis_x, 144, "Hard-gate passes out of 49", "axis"))
    lines.append(text(right_x, 144, "Pass lift", "axis"))
    lines.append(text(994, 144, "Quality delta*", "axis"))
    for tick in [0, 10, 20, 30, 40, 49]:
        x = axis_x + axis_w * pct(tick, 49)
        lines.append(line(x, 176, x, 506, "#e5e7eb"))
        lines.append(text(x, 166, tick, "axis", anchor="middle"))
    for index, row in enumerate(rows):
        y = 204 + index * 58
        if index % 2 == 0:
            lines.append(rect(64, y - 30, 990, 48, "#f8fafc", rx=0))
        empty_y = y - 14
        current_y = y + 4
        empty_passed = row["empty_passed"]
        current_passed = row["current_passed"]
        pass_delta = current_passed - empty_passed
        lines.append(text(72, y + 4, row["label"], "label"))
        lines.append(rect(axis_x, empty_y, axis_w, 11, "#eef2f7", rx=6))
        lines.append(rect(axis_x, empty_y, axis_w * pct(empty_passed, 49), 11, "#94a3b8", rx=6))
        lines.append(rect(axis_x, current_y, axis_w, 13, "#eef2f7", rx=7))
        lines.append(rect(axis_x, current_y, axis_w * pct(current_passed, 49), 13, row["color"], rx=7))
        lines.append(text(right_x, y - 8, f"empty {empty_passed}/49", "small"))
        lines.append(text(right_x, y + 12, f"current {current_passed}/49", "value"))
        lines.append(rect(892, y - 18, 56, 28, "#d1fae5", rx=14))
        lines.append(text(920, y + 1, f"+{pass_delta}", "value", anchor="middle"))
        lines.append(text(994, y + 1, f"{row['empty_quality_delta']:+.1f}", "value"))
    legend_y = 575
    lines.append(circle(78, legend_y, 7, "#94a3b8"))
    lines.append(text(94, legend_y + 4, "Empty bundle", "axis"))
    lines.append(circle(204, legend_y, 7, CURRENT))
    lines.append(text(220, legend_y + 4, "Current instructions", "axis"))
    lines.append(text(72, 610, "*Quality delta is the latest saved empty-vs-current judge aggregate; hard gates use the v4.12 current refresh plus latest available empty baselines.", "small"))
    lines.extend(footer(width, 632, "Source: v4.12 current summaries, latest empty summaries, and saved empty-vs-current quality aggregates"))
    lines.append("</svg>")
    write_svg(output_dir / "empty-current-lift.svg", lines)


def render_model_gap(quality_root: Path, output_dir: Path) -> None:
    rows = v413_model_gap_rows(quality_root)
    width = 1120
    height = 570
    axis_x = 292
    axis_w = 620
    lines = svg_start(
        width,
        height,
        "External model gap versus GPT",
        "OpenAI/Codex judge comparison of external saved outputs against GPT on previous and current instructions.",
    )
    lines.append(text(40, 56, "External model gap versus GPT", "title"))
    lines.append(text(40, 84, "Same judge, same 49 cases. Delta is external-model score minus GPT score; closer to zero is better for transfer.", "subtitle"))
    lines.extend(panel(40, 112, 1040, 360))
    lines.append(text(72, 148, "Model", "axis"))
    lines.append(text(axis_x, 148, "Average quality delta versus GPT", "axis"))
    lines.append(text(926, 148, "Quality split", "axis"))
    for tick in [-60, -40, -20, 0]:
        x = axis_x + axis_w * pct(tick + 60, 60)
        lines.append(line(x, 176, x, 394, "#e5e7eb"))
        lines.append(text(x, 166, tick, "axis", anchor="middle"))
    zero_x = axis_x + axis_w
    lines.append(line(zero_x, 170, zero_x, 406, "#94a3b8"))
    for index, row in enumerate(rows):
        y = 214 + index * 78
        if index % 2 == 0:
            lines.append(rect(64, y - 38, 990, 64, "#f8fafc", rx=0))
        lines.append(text(72, y - 8, row["label"], "label"))
        lines.append(text(72, y + 14, f"hard gates {row['previous']['hard_passed']} -> {row['current']['hard_passed']}", "small"))
        previous_delta = row["previous"]["delta"]
        current_delta = row["current"]["delta"]
        previous_x = axis_x + axis_w * pct(previous_delta + 60, 60)
        current_x = axis_x + axis_w * pct(current_delta + 60, 60)
        lines.append(rect(axis_x, y - 18, axis_w, 10, TRACK, rx=5))
        lines.append(line(previous_x, y - 28, current_x, y - 28, "#94a3b8"))
        lines.append(circle(previous_x, y - 28, 7, "#94a3b8"))
        lines.append(circle(current_x, y - 28, 8, CURRENT))
        lines.append(text(previous_x, y - 42, f"{previous_delta:+.1f}", "axis", anchor="middle"))
        lines.append(text(current_x, y - 2, f"{current_delta:+.1f}", "value", anchor="middle"))
        change_color = GOOD if row["gap_change"] > 0 else WARN if row["gap_change"] < 0 else TIE
        lines.append(rect(692, y - 30, 70, 28, change_color, rx=14))
        lines.append(text(727, y - 11, f"{row['gap_change']:+.1f}", "value", anchor="middle"))
        current = row["current"]
        lines.append(text(926, y - 18, f"current {current['wins']}/{current['ties']}/{current['gpt_wins']}", "value"))
        lines.append(text(926, y + 4, "external / tie / GPT", "small"))
    legend_y = 510
    lines.append(circle(78, legend_y, 7, "#94a3b8"))
    lines.append(text(94, legend_y + 4, "previous instructions", "axis"))
    lines.append(circle(244, legend_y, 7, CURRENT))
    lines.append(text(260, legend_y + 4, "current instructions", "axis"))
    lines.append(text(444, legend_y + 4, "Gap-change chip: positive means the external model moved closer to GPT.", "axis"))
    lines.extend(footer(width, 548, "Source: v4.13 GPT-vs-external saved-quality summaries judged by OpenAI/Codex"))
    lines.append("</svg>")
    write_svg(output_dir / "model-gap.svg", lines)


def render_model_transfer(refresh_root: Path, empty_root: Path, output_dir: Path) -> None:
    rows = model_rows(refresh_root, empty_root)
    references = reference_rows(refresh_root)
    ref_passes = {(row["short"], row["reference"]): row["reference_passed"] for row in references}
    width = 1280
    height = 650
    axis_x = 292
    axis_w = 760
    lines = svg_start(
        width,
        height,
        "Instruction bundles by model",
        "Hard-gate passes out of 49 for empty, previous current, v4.12 current, and reference instruction bundles.",
    )
    lines.append(text(40, 56, "Hard-gate passes by model and instruction bundle", "title"))
    lines.append(text(40, 84, "Dot positions show passed eval cases out of 49. Empty baselines are latest available; reused rows are marked.", "subtitle"))
    lines.extend(panel(40, 118, 1200, 410))
    for tick in [0, 10, 20, 30, 40, 49]:
        x = axis_x + axis_w * pct(tick, 49)
        lines.append(line(x, 156, x, 478, "#e5e7eb"))
        lines.append(text(x, 146, tick, "axis", anchor="middle"))
    lines.append(line(axis_x, 156, axis_x + axis_w, 156, "#94a3b8"))
    legend = [("empty", "#94a3b8"), ("previous current", "#f59e0b"), ("v4.12 current", CURRENT), ("OpenHands", OPENHANDS), ("Fable", FABLE)]
    for index, (label, color) in enumerate(legend):
        x = 72 + index * 165
        lines.append(circle(x, 556, 7, color))
        lines.append(text(x + 14, 560, label, "axis"))
    for index, row in enumerate(rows):
        y = 192 + index * 48
        if index % 2 == 0:
            lines.append(rect(64, y - 22, 1140, 42, "#f8fafc", rx=0))
        lines.append(text(72, y + 5, row["label"], "label"))
        values = [
            ("empty", row["empty_passed"], "#94a3b8"),
            ("previous", row["old_passed"], "#f59e0b"),
            ("current", row["new_passed"], CURRENT),
            ("OpenHands", ref_passes.get((row["short"], "OpenHands")), OPENHANDS),
            ("Fable", ref_passes.get((row["short"], "Fable")), FABLE),
        ]
        for offset, (label, value, color) in enumerate(values):
            if value is None:
                continue
            x = axis_x + axis_w * pct(value, 49)
            lines.append(circle(x, y, 7, color))
            lines.append(text(x, y + 24 + (offset % 2) * 12, value, "axis", anchor="middle"))
        if row["empty_source"] != "same refresh":
            lines.append(text(1080, y + 5, "empty reused", "small"))
    lines.append(text(72, 604, "This is the main pass/fail context: it restores the no-instructions comparison without rerunning empty for every model.", "label"))
    lines.extend(footer(width, 626, "Source: current v4.12 refresh plus latest available empty/reference summaries"))
    lines.append("</svg>")
    write_svg(output_dir / "model-transfer.svg", lines)


def render_reference_prompts(refresh_root: Path, output_dir: Path) -> None:
    rows = reference_rows(refresh_root)
    width = 1120
    height = 850
    lines = svg_start(
        width,
        height,
        "Current instructions versus reference instruction bundles",
        "OpenHands and Claude/Fable baselines compared with our current instructions on each model.",
    )
    lines.append(text(40, 56, "Current vs reference instruction bundles", "title"))
    lines.append(text(40, 84, "Our current bundle wins aggregate quality for every measured model/reference pair, with concrete caveats.", "subtitle"))
    lines.extend(panel(40, 112, 1040, 650))
    lines.append(text(72, 150, "Model / reference", "axis"))
    lines.append(text(300, 150, "Hard gates", "axis"))
    lines.append(text(500, 150, "Current / tie / reference / inconclusive", "axis"))
    lines.append(text(932, 150, "Delta", "axis", anchor="middle"))
    for index, row in enumerate(rows):
        y = 184 + index * 47
        lines.append(text(72, y + 14, f"{row['short']} vs {row['reference']}", "label"))
        lines.append(text(300, y + 14, f"{row['current_passed']}/49 vs {row['reference_passed']}/49", "value"))
        draw_segments(
            lines,
            500,
            y,
            320,
            18,
            row["total"],
            [(row["current_wins"], CURRENT), (row["ties"], TIE), (row["reference_wins"], BASELINE), (row["inconclusive"], INCONCLUSIVE)],
        )
        lines.append(text(835, y + 14, f"{row['current_wins']}/{row['ties']}/{row['reference_wins']}/{row['inconclusive']}", "value"))
        lines.append(text(932, y + 14, f"{row['delta']:+.1f}", "value", anchor="middle"))
        if row.get("caveat"):
            lines.append(text(970, y + 14, row["caveat"], "small"))
    lines.append(rect(72, 794, 12, 12, CURRENT, rx=3))
    lines.append(text(92, 805, "current wins", "axis"))
    lines.append(rect(176, 794, 12, 12, BASELINE, rx=3))
    lines.append(text(196, 805, "reference wins", "axis"))
    lines.append(rect(306, 794, 12, 12, INCONCLUSIVE, rx=3))
    lines.append(text(326, 805, "fail/fail or residual", "axis"))
    lines.extend(footer(width, 824, "Source: current-vs-reference saved quality summaries"))
    lines.append("</svg>")
    write_svg(output_dir / "reference-prompts.svg", lines)


def pass_pass_counts(pair_path: Path) -> dict[str, Any]:
    data = read_json(pair_path)
    counts = {"current": 0, "baseline": 0, "tie": 0, "inconclusive": 0}
    total = 0
    deltas: list[float] = []
    for item in data["comparisons"]:
        if not (item["baseline"]["passed"] and item["candidate"]["passed"]):
            continue
        total += 1
        quality = item["quality"]
        winner = quality.get("winner")
        if winner in counts:
            counts[winner] += 1
        if isinstance(quality.get("delta"), (int, float)):
            deltas.append(float(quality["delta"]))
    return {"total": total, "counts": counts, "avg_delta": round(sum(deltas) / len(deltas), 1) if deltas else 0.0}


def render_quality_only_comparisons(
    refresh_root: Path,
    gpt_root: Path,
    external_root: Path,
    quality_root: Path,
    output_dir: Path,
) -> None:
    prev_rows = []
    for row in v413_model_rows(gpt_root, external_root, quality_root):
        prev_rows.append({"label": row["short"], **pass_pass_counts(row["pair_path"])})
    gap_rows = []
    for row in v413_model_gap_rows(quality_root):
        gap_rows.append({"label": f"{row['label']} cur", **pass_pass_counts(row["current"]["pair_path"])})
        gap_rows.append({"label": f"{row['label']} prev", **pass_pass_counts(row["previous"]["pair_path"])})
    ref_rows = []
    for row in reference_rows(refresh_root):
        ref_rows.append({"label": f"{row['short']}/{compact_reference_label(row['reference'])}", **pass_pass_counts(row["pair_path"])})
    width = 1360
    height = 790
    lines = svg_start(
        width,
        height,
        "Quality-only comparisons after hard gates pass",
        "Only cases where both sides passed deterministic hard gates are included.",
    )
    lines.append(text(40, 56, "Quality-only small multiples", "title"))
    lines.append(text(40, 84, "Hard failures are excluded. Triplets are left wins / ties / right wins, with n=pass/pass overlap.", "subtitle"))
    lines.extend(panel(40, 116, 390, 540))
    lines.append(text(72, 152, "v4.13 current vs previous", "label"))
    for index, row in enumerate(prev_rows):
        counts = row["counts"]
        y = 188 + index * 62
        lines.append(text(72, y + 14, row["label"], "label"))
        draw_segments(lines, 178, y, 150, 18, row["total"], [(counts["current"], GOOD), (counts["tie"], TIE), (counts["baseline"], BASELINE)])
        lines.append(text(344, y + 14, f"{counts['current']}/{counts['tie']}/{counts['baseline']}", "value"))
        lines.append(text(190, y + 40, f"n={row['total']}, avg delta {row['avg_delta']:+.1f}", "small"))
    lines.extend(panel(460, 116, 390, 540))
    lines.append(text(492, 152, "External model vs GPT", "label"))
    for index, row in enumerate(gap_rows):
        counts = row["counts"]
        y = 184 + index * 62
        lines.append(text(492, y + 14, row["label"], "label"))
        draw_segments(lines, 614, y, 132, 18, max(row["total"], 1), [(counts["current"], CURRENT), (counts["tie"], TIE), (counts["baseline"], BASELINE)])
        lines.append(text(762, y + 14, f"{counts['current']}/{counts['tie']}/{counts['baseline']}", "value"))
        lines.append(text(614, y + 40, f"n={row['total']}, avg delta {row['avg_delta']:+.1f}", "small"))
    lines.extend(panel(880, 116, 440, 540))
    lines.append(text(912, 152, "Current vs references (v4.12 saved)", "label"))
    for index, row in enumerate(ref_rows):
        counts = row["counts"]
        y = 184 + index * 38
        lines.append(text(912, y + 14, row["label"], "label"))
        draw_segments(lines, 1048, y, 150, 18, max(row["total"], 1), [(counts["current"], CURRENT), (counts["tie"], TIE), (counts["baseline"], BASELINE)])
        lines.append(text(1214, y + 14, f"{counts['current']}/{counts['tie']}/{counts['baseline']}", "value"))
        lines.append(text(1270, y + 14, f"n={row['total']}", "small"))
    lines.append(text(72, 692, "Triplet meaning changes by panel: current/previous, external/GPT, and current/reference. Use the title before comparing colors.", "label"))
    lines.extend(footer(width, 758, "Source: OpenAI/Codex saved-quality reports filtered to both sides passed; references are saved v4.12 context"))
    lines.append("</svg>")
    write_svg(output_dir / "quality-only-comparisons.svg", lines)


def case_winner_matrix(refresh_root: Path) -> tuple[list[str], list[dict[str, Any]]]:
    rows = reference_rows(refresh_root)
    outcomes: dict[str, dict[str, dict[str, Any]]] = {}
    baseline_win_counts: dict[str, int] = {}

    for row in rows:
        model_short = compact_model_label(row["short"])
        ref_short = compact_reference_label(row["reference"])
        col = f"{model_short}/{ref_short}"
        pair = read_json(row["pair_path"])
        for item in pair["comparisons"]:
            if not (item["baseline"]["passed"] and item["candidate"]["passed"]):
                continue
            case_id = item["case_id"]
            quality = item["quality"]
            winner = quality.get("winner", "inconclusive")
            delta = quality.get("delta")
            outcomes.setdefault(case_id, {})[col] = {
                "winner": winner,
                "delta": delta if isinstance(delta, (int, float)) else None,
            }
            if winner == "baseline":
                baseline_win_counts[case_id] = baseline_win_counts.get(case_id, 0) + 1
    columns = [f"{compact_model_label(row['short'])}/{compact_reference_label(row['reference'])}" for row in rows]
    selected = sorted(outcomes, key=lambda case_id: (-baseline_win_counts.get(case_id, 0), case_id))[:20]
    return columns, [{"case": case_id, "values": outcomes[case_id], "reference_wins": baseline_win_counts.get(case_id, 0)} for case_id in selected]


def winner_fill(winner: str) -> str:
    if winner == "current":
        return CURRENT_FILL
    if winner == "baseline":
        return BASELINE_FILL
    if winner == "tie":
        return TIE_FILL
    return INCONCLUSIVE_FILL


def winner_text(winner: str) -> str:
    return {"current": "C", "baseline": "R", "tie": "T", "inconclusive": "I"}.get(winner, "")


def delta_text(entry: dict[str, Any]) -> str:
    delta = entry.get("delta")
    if isinstance(delta, (int, float)):
        rounded = round(delta)
        return "0" if rounded == 0 else f"{rounded:+d}"
    return "I"


def pair_delta_map(pair_path: Path) -> dict[str, dict[str, Any]]:
    data = read_json(pair_path)
    values = {}
    for item in data["comparisons"]:
        if not (item["baseline"]["passed"] and item["candidate"]["passed"]):
            continue
        quality = item["quality"]
        delta = quality.get("delta")
        values[item["case_id"]] = {
            "winner": quality.get("winner", "inconclusive"),
            "delta": delta if isinstance(delta, (int, float)) else None,
        }
    return values


def gpt_external_case_columns(refresh_root: Path) -> list[dict[str, Any]]:
    data = read_json(refresh_root / GPT_EXTERNAL_QUALITY)
    labels = {
        "Grok-4.3-new-current": "G4",
        "Grok-Build-0.1-new-current": "GB",
        "DeepSeek-V4-Flash-new-current": "DS",
        "DeepSeek-V4-Flash-thinking-new-current": "DSt",
        "GLM-5.2-new-current": "GLM",
    }
    order = ["GLM", "GB", "G4", "DS", "DSt"]
    columns = []
    for pair in data["pairs"]:
        label = labels.get(pair["candidate_label"], pair["candidate_label"])
        columns.append({"label": label, "values": pair_delta_map(Path(pair["quality_json"]))})
    return sorted(columns, key=lambda column: order.index(column["label"]) if column["label"] in order else 999)


def v413_prev_current_case_columns(gpt_root: Path, external_root: Path, quality_root: Path) -> list[dict[str, Any]]:
    columns = []
    for row in v413_model_rows(gpt_root, external_root, quality_root):
        columns.append({"label": compact_model_label(row["short"]), "values": pair_delta_map(row["pair_path"])})
    return columns


def v413_gpt_external_case_columns(quality_root: Path, rel_path: str, prefix: str) -> list[dict[str, Any]]:
    rows = v413_gpt_external_rows(quality_root, rel_path, prefix)
    return [
        {"label": compact_model_label(row["label"]), "values": pair_delta_map(row["pair_path"])}
        for row in rows
    ]


def prev_current_case_columns(refresh_root: Path, empty_root: Path) -> list[dict[str, Any]]:
    columns = []
    for row in model_rows(refresh_root, empty_root):
        quality = quality_summary(refresh_root, row["prev_quality"])
        columns.append({"label": compact_model_label(row["short"]), "values": pair_delta_map(quality["pair_path"])})
    return columns


def reference_case_columns(refresh_root: Path) -> list[dict[str, Any]]:
    columns = []
    for row in reference_rows(refresh_root):
        label = f"{compact_model_label(row['short'])}/{compact_reference_label(row['reference'])}"
        columns.append({"label": label, "values": pair_delta_map(row["pair_path"])})
    return columns


def select_case_ids(columns: list[dict[str, Any]], limit: int, mode: str) -> list[str]:
    case_ids = sorted({case_id for column in columns for case_id in column["values"]})

    def metrics(case_id: str) -> tuple[int, int, float, float]:
        deltas = [
            entry["delta"]
            for column in columns
            if (entry := column["values"].get(case_id)) is not None and isinstance(entry.get("delta"), (int, float))
        ]
        if not deltas:
            return (0, 0, 0.0, 0.0)
        return (
            sum(1 for delta in deltas if delta < 0),
            sum(1 for delta in deltas if delta > 0),
            min(deltas),
            max(abs(delta) for delta in deltas),
        )

    if mode == "external":
        return sorted(case_ids, key=lambda case_id: (-metrics(case_id)[1], -metrics(case_id)[3], case_id))[:limit]
    return sorted(case_ids, key=lambda case_id: (-metrics(case_id)[0], metrics(case_id)[2], -metrics(case_id)[3], case_id))[:limit]


def delta_counts(columns: list[dict[str, Any]], case_ids: list[str]) -> dict[str, int]:
    counts = {"positive": 0, "negative": 0, "tie": 0, "blank": 0}
    for case_id in case_ids:
        for column in columns:
            entry = column["values"].get(case_id)
            if entry is None:
                counts["blank"] += 1
                continue
            delta = entry.get("delta")
            if not isinstance(delta, (int, float)) or round(delta) == 0:
                counts["tie"] += 1
            elif delta > 0:
                counts["positive"] += 1
            else:
                counts["negative"] += 1
    return counts


def comparison_chip(lines: list[str], x: float, y: float, label: str, value: int, fill: str) -> None:
    lines.append(rect(x, y - 17, 108, 24, fill, rx=12, stroke="#e5e7eb"))
    lines.append(text(x + 12, y, f"{label} {value}", "axis"))


def column_delta_summary(column: dict[str, Any]) -> dict[str, Any]:
    deltas = [
        entry["delta"]
        for entry in column["values"].values()
        if isinstance(entry.get("delta"), (int, float))
    ]
    return {
        "positive": sum(1 for delta in deltas if delta > 0),
        "negative": sum(1 for delta in deltas if delta < 0),
        "tie": sum(1 for delta in deltas if round(delta) == 0),
        "average": sum(deltas) / len(deltas) if deltas else 0.0,
    }


def render_explained_delta_table(
    lines: list[str],
    x: float,
    y: float,
    width: float,
    title: str,
    formula: str,
    interpretation: str,
    positive_label: str,
    negative_label: str,
    columns: list[dict[str, Any]],
    case_ids: list[str],
    cell_width: float,
) -> float:
    row_height = 28
    case_width = width - cell_width * len(columns) - 44
    height = 224 + len(case_ids) * row_height
    counts = delta_counts(columns, case_ids)
    lines.extend(panel(x, y, width, height))
    lines.append(text(x + 24, y + 36, title, "label"))
    lines.append(text(x + 24, y + 60, f"Formula: {formula}", "value"))
    lines.append(text(x + 24, y + 82, interpretation, "small"))
    lines.append(text(x + 24, y + 104, "Column mini-summary uses all pass/pass cases. Rows below are selected watchlist cases, so they are intentionally not representative.", "small"))
    legend_y = y + 132
    legend = [
        (x + 24, f"+ {positive_label}", CURRENT_FILL),
        (x + 178, f"- {negative_label}", BASELINE_FILL),
        (x + 332, "0 tie", TIE_FILL),
        (x + 430, "blank no pass/pass", "#ffffff"),
    ]
    for lx, label, fill in legend:
        lines.append(rect(lx, legend_y - 14, 18, 18, fill, rx=4, stroke="#e5e7eb"))
        lines.append(text(lx + 26, legend_y, label, "axis"))
    comparison_chip(lines, x + width - 472, legend_y, "selected +", counts["positive"], CURRENT_FILL)
    comparison_chip(lines, x + width - 354, legend_y, "selected -", counts["negative"], BASELINE_FILL)
    comparison_chip(lines, x + width - 236, legend_y, "selected 0", counts["tie"], TIE_FILL)
    comparison_chip(lines, x + width - 118, legend_y, "blank", counts["blank"], "#ffffff")

    header_y = y + 166
    lines.append(text(x + 24, header_y, "Case", "axis"))
    for index, column in enumerate(columns):
        cx = x + 24 + case_width + index * cell_width + cell_width / 2
        summary = column_delta_summary(column)
        lines.append(text(cx, header_y, column["label"], "axis", anchor="middle"))
        lines.append(text(cx, header_y + 16, f"+{summary['positive']} -{summary['negative']}", "axis", anchor="middle"))
        lines.append(text(cx, header_y + 31, f"avg {summary['average']:+.1f}", "axis", anchor="middle"))
    for row_index, case_id in enumerate(case_ids):
        cy = y + 220 + row_index * row_height
        if row_index % 2 == 0:
            lines.append(rect(x + 16, cy - 16, width - 32, row_height, "#f8fafc", rx=0))
        lines.append(text(x + 24, cy, case_id, "small"))
        for col_index, column in enumerate(columns):
            entry = column["values"].get(case_id)
            cx = x + 24 + case_width + col_index * cell_width + 7
            if entry is None:
                lines.append(rect(cx, cy - 16, cell_width - 14, 19, "#ffffff", rx=5, stroke="#f1f5f9"))
                continue
            lines.append(rect(cx, cy - 16, cell_width - 14, 19, winner_fill(entry.get("winner", "inconclusive")), rx=5, stroke="#e5e7eb"))
            lines.append(text(cx + (cell_width - 14) / 2, cy - 2, delta_text(entry), "cell", anchor="middle"))
    return height


def render_case_detail_comparisons(
    refresh_root: Path,
    gpt_root: Path,
    external_root: Path,
    quality_root: Path,
    output_dir: Path,
) -> None:
    prev_columns = v413_prev_current_case_columns(gpt_root, external_root, quality_root)
    current_gap_columns = v413_gpt_external_case_columns(quality_root, GPT_VS_EXTERNAL_CURRENT_QUALITY, "current")
    previous_gap_columns = v413_gpt_external_case_columns(quality_root, GPT_VS_EXTERNAL_PREVIOUS_QUALITY, "previous")
    reference_columns = reference_case_columns(refresh_root)
    prev_cases = select_case_ids(prev_columns, 10, "regression")
    current_gap_cases = select_case_ids(current_gap_columns, 8, "regression")
    previous_gap_cases = select_case_ids(previous_gap_columns, 8, "regression")
    reference_cases = select_case_ids(reference_columns, 8, "regression")
    width = 1400
    y = 136
    blocks = [
        (
            "v4.13 current vs previous instructions",
            "current score - previous score",
            "Read this as instruction-change impact on the same model. Red cells are concrete regressions versus the previous instructions.",
            "current better",
            "previous better",
            prev_columns,
            prev_cases,
            86,
        ),
        (
            "External models vs GPT on current instructions",
            "external-model score - GPT score",
            "Read this as current-instruction model gap. Red cells mean GPT's answer was better; blue cells mean the external model beat GPT.",
            "external better",
            "GPT better",
            current_gap_columns,
            current_gap_cases,
            96,
        ),
        (
            "External models vs GPT on previous instructions",
            "external-model score - GPT score",
            "Read this as the previous-instruction model gap, so current/previous gap movement can be compared case by case.",
            "external better",
            "GPT better",
            previous_gap_columns,
            previous_gap_cases,
            96,
        ),
        (
            "Current instructions vs reference bundles (v4.12 saved)",
            "current-instructions score - reference-bundle score",
            "Read this as saved reference context, not fresh v4.13 provider evidence. Red cells are reference wins worth inspecting.",
            "current better",
            "reference better",
            reference_columns,
            reference_cases,
            58,
        ),
    ]
    heights = [224 + len(cases) * 28 for _, _, _, _, _, _, cases, _ in blocks]
    height = int(180 + sum(heights) + 28 * (len(blocks) - 1) + 50)
    lines = svg_start(
        width,
        height,
        "Case-level quality deltas",
        "Signed pass/pass judge score deltas for concrete high-signal eval cases.",
    )
    lines.append(text(40, 56, "Case-level quality deltas", "title"))
    lines.append(text(40, 84, "Every number is a judge-score delta on a concrete eval case after both hard gates pass.", "subtitle"))
    lines.append(text(40, 106, "Positive and negative colors are explained separately in each block; blanks are excluded quality comparisons, not zeros.", "small"))
    for title, formula, interpretation, positive_label, negative_label, columns, cases, cell_width in blocks:
        block_height = render_explained_delta_table(
            lines,
            40,
            y,
            1320,
            title,
            formula,
            interpretation,
            positive_label,
            negative_label,
            columns,
            cases,
            cell_width,
        )
        y += block_height + 28
    lines.extend(footer(width, height - 32, "Source: saved quality pair reports filtered to both sides passed"))
    lines.append("</svg>")
    write_svg(output_dir / "case-detail-comparisons.svg", lines)


def render_quality_only_case_matrix(refresh_root: Path, output_dir: Path) -> None:
    columns, rows = case_winner_matrix(refresh_root)
    width = 1280
    row_height = 28
    height = 230 + len(rows) * row_height + 100
    lines = svg_start(
        width,
        height,
        "Case-level current versus reference matrix",
        "Pass/pass judge score deltas for concrete current versus reference instruction cases.",
    )
    lines.append(text(40, 56, "Case-level quality delta matrix", "title"))
    lines.append(text(40, 84, "Each cell is current score minus reference score after both hard gates pass. + favors current, - favors reference, blank=no pass/pass.", "subtitle"))
    lines.append(text(40, 104, "OH=OpenHands, F=Claude/Fable, GB=Grok Build, G4=Grok 4.3, DS=DeepSeek, DSt=DS thinking.", "small"))
    lines.extend(panel(40, 116, 1200, height - 190))
    table_x = 72
    case_width = 370
    cell_width = 62
    header_y = 154
    lines.append(text(table_x, header_y, "Case", "axis"))
    for index, column in enumerate(columns):
        x = table_x + case_width + index * cell_width + cell_width / 2
        lines.append(text(x, header_y, column, "axis", anchor="middle"))
    for row_index, row in enumerate(rows):
        y = 194 + row_index * row_height
        if row_index % 2 == 0:
            lines.append(rect(table_x - 8, y - 17, 1138, row_height, "#f8fafc", rx=0))
        lines.append(text(table_x, y, row["case"], "small"))
        for col_index, column in enumerate(columns):
            x = table_x + case_width + col_index * cell_width + 8
            entry = row["values"].get(column)
            if entry is None:
                lines.append(rect(x, y - 17, cell_width - 16, 20, "#ffffff", rx=5, stroke="#f1f5f9"))
                continue
            winner = entry.get("winner", "inconclusive")
            lines.append(rect(x, y - 17, cell_width - 16, 20, winner_fill(winner), rx=5, stroke="#e5e7eb"))
            lines.append(text(x + (cell_width - 16) / 2, y - 3, delta_text(entry), "cell", anchor="middle"))
    legend_y = height - 72
    for x, label, color in [(72, "+ current", CURRENT_FILL), (184, "- reference", BASELINE_FILL), (320, "0 tie", TIE_FILL), (396, "I inconclusive", INCONCLUSIVE_FILL), (520, "blank no pass/pass", "#ffffff")]:
        lines.append(rect(x, legend_y - 14, 18, 18, color, rx=4, stroke="#e5e7eb"))
        lines.append(text(x + 26, legend_y, label, "axis"))
    lines.extend(footer(width, height - 34, "Source: all current-vs-reference quality pair reports"))
    lines.append("</svg>")
    write_svg(output_dir / "quality-only-case-matrix.svg", lines)


def render_coverage_watchlist(refresh_root: Path, output_dir: Path) -> None:
    cases = read_jsonl(CASE_FILE)
    current_by_model = []
    for model in MODELS:
        data = read_json(refresh_root / model["current"])
        current_by_model.append((model["short"], {item["case_id"]: item for item in data["results"]}))
    rows = []
    for case in cases:
        passers = [short for short, result_map in current_by_model if result_map[case["id"]]["passed"]]
        rows.append({"case": case["id"], "passed": len(passers), "passers": passers})
    rows = sorted(rows, key=lambda row: (row["passed"], row["case"]))[:18]
    width = 1120
    height = 700
    lines = svg_start(
        width,
        height,
        "Current instruction weak spots by concrete case",
        "Cases with the fewest current-model hard-gate passes across the six tested models.",
    )
    lines.append(text(40, 56, "Current weak spots by case", "title"))
    lines.append(text(40, 84, "The weakest cases are where model transfer is still limited, even after v4.12 improvements.", "subtitle"))
    lines.extend(panel(40, 116, 1040, 500))
    lines.append(text(72, 152, "Case", "axis"))
    lines.append(text(590, 152, "Current models passing out of 6", "axis"))
    for index, row in enumerate(rows):
        y = 188 + index * 24
        if index % 2 == 0:
            lines.append(rect(64, y - 16, 970, 24, "#f8fafc", rx=0))
        lines.append(text(72, y, row["case"], "small"))
        lines.append(rect(590, y - 14, 220, 14, TRACK, rx=7))
        fill = WARN if row["passed"] <= 1 else "#f97316" if row["passed"] <= 2 else GOOD
        lines.append(rect(590, y - 14, 220 * pct(row["passed"], 6), 14, fill, rx=7))
        lines.append(text(826, y - 2, f"{row['passed']}/6", "value"))
        lines.append(text(878, y - 2, ", ".join(row["passers"]) if row["passers"] else "none", "small"))
    lines.append(text(72, 650, "Use this as the concrete backlog: improving these cases should be checked across non-GPT models, not only GPT.", "label"))
    lines.extend(footer(width, 676, "Source: current summaries across GPT, GLM, Grok, Grok Build, DeepSeek, and DeepSeek thinking"))
    lines.append("</svg>")
    write_svg(output_dir / "coverage-watchlist.svg", lines)


def build_all(
    repo_root: Path,
    refresh_root: Path,
    empty_root: Path,
    v413_gpt_root: Path,
    v413_external_root: Path,
    canonical_quality_root: Path,
    output_dir: Path,
) -> None:
    refresh_root = resolve_path(repo_root, refresh_root)
    empty_root = resolve_path(repo_root, empty_root)
    v413_gpt_root = resolve_path(repo_root, v413_gpt_root)
    v413_external_root = resolve_path(repo_root, v413_external_root)
    canonical_quality_root = resolve_path(repo_root, canonical_quality_root)
    output_dir = resolve_path(repo_root, output_dir)
    render_instruction_lift(v413_gpt_root, v413_external_root, canonical_quality_root, refresh_root, output_dir)
    render_empty_current_lift(refresh_root, empty_root, output_dir)
    render_model_gap(canonical_quality_root, output_dir)
    render_model_transfer(refresh_root, empty_root, output_dir)
    render_reference_prompts(refresh_root, output_dir)
    render_quality_only_comparisons(refresh_root, v413_gpt_root, v413_external_root, canonical_quality_root, output_dir)
    render_case_detail_comparisons(refresh_root, v413_gpt_root, v413_external_root, canonical_quality_root, output_dir)
    render_quality_only_case_matrix(refresh_root, output_dir)
    render_coverage_watchlist(refresh_root, output_dir)


def compare_svg_dirs(expected_dir: Path, output_dir: Path) -> list[str]:
    expected = {path.name: path for path in expected_dir.glob("*.svg")}
    actual = {path.name: path for path in output_dir.glob("*.svg")}
    problems = []

    for name in sorted(expected.keys() - actual.keys()):
        problems.append(f"missing: {output_dir / name}")
    for name in sorted(expected.keys() & actual.keys()):
        if expected[name].read_text(encoding="utf-8") != actual[name].read_text(encoding="utf-8"):
            problems.append(f"stale: {output_dir / name}")
    for name in sorted(actual.keys() - expected.keys()):
        problems.append(f"unexpected: {output_dir / name}")
    return problems


def check_all(
    repo_root: Path,
    refresh_root: Path,
    empty_root: Path,
    v413_gpt_root: Path,
    v413_external_root: Path,
    canonical_quality_root: Path,
    output_dir: Path,
) -> list[str]:
    output_dir = resolve_path(repo_root, output_dir)
    with tempfile.TemporaryDirectory(prefix="readme-infographics-check-") as tmp:
        expected_dir = Path(tmp) / "readme"
        build_all(repo_root, refresh_root, empty_root, v413_gpt_root, v413_external_root, canonical_quality_root, expected_dir)
        return compare_svg_dirs(expected_dir, output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-root", default=str(DEFAULT_REFRESH_ROOT), help="Saved refresh artifact root.")
    parser.add_argument("--empty-root", default=str(DEFAULT_EMPTY_ROOT), help="Fallback root for reused empty-baseline artifacts.")
    parser.add_argument("--v413-gpt-root", default=str(DEFAULT_V413_GPT_ROOT), help="Saved GPT v4.13 artifact root.")
    parser.add_argument("--v413-external-root", default=str(DEFAULT_V413_EXTERNAL_ROOT), help="Saved GLM/DeepSeek v4.13 artifact root.")
    parser.add_argument("--canonical-quality-root", default=str(DEFAULT_CANONICAL_QUALITY_ROOT), help="OpenAI/Codex saved-quality artifact root.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for generated README SVGs.")
    parser.add_argument("--check", action="store_true", help="Verify generated README SVGs are fresh without updating them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    if args.check:
        problems = check_all(
            repo_root,
            Path(args.refresh_root),
            Path(args.empty_root),
            Path(args.v413_gpt_root),
            Path(args.v413_external_root),
            Path(args.canonical_quality_root),
            Path(args.output_dir),
        )
        if problems:
            print("README infographics are not fresh:", file=sys.stderr)
            for problem in problems:
                print(f"- {problem}", file=sys.stderr)
            print("Regenerate with the same arguments without --check.", file=sys.stderr)
            return 1
        print(f"readme infographics fresh: {Path(args.output_dir)}")
        return 0

    build_all(
        repo_root,
        Path(args.refresh_root),
        Path(args.empty_root),
        Path(args.v413_gpt_root),
        Path(args.v413_external_root),
        Path(args.canonical_quality_root),
        Path(args.output_dir),
    )
    print(f"wrote {Path(args.output_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
