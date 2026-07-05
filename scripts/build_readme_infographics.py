#!/usr/bin/env python3
"""Build README SVG infographics from saved instruction-eval artifacts."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


DEFAULT_REFRESH_ROOT = Path(".eval-results/refresh-2026-07-05-49-case-v1")
DEFAULT_OUTPUT_DIR = Path("docs/assets/readme")

CASE_FILE = Path("evals/cases.jsonl")

MODELS = [
    {
        "label": "GPT-5.5",
        "short": "GPT",
        "current": "current-gpt55/current/summary.json",
        "empty": "empty-gpt55/empty/summary.json",
        "lift_quality": "quality-empty-vs-current-gpt55/GPT-5.5-empty-saved-model-quality/model-quality-summary.json",
        "color": "#2563eb",
    },
    {
        "label": "GLM-5.2",
        "short": "GLM",
        "current": "merged/current-glm-5.2-merged/summary.json",
        "empty": "merged/empty-glm-5.2-merged/summary.json",
        "lift_quality": "quality-empty-vs-current-glm-5.2/GLM-5.2-empty-saved-model-quality/model-quality-summary.json",
        "color": "#16a34a",
    },
    {
        "label": "Grok Build 0.1",
        "short": "Grok Build",
        "current": "merged/current-grok-build-0.1-merged/summary.json",
        "empty": "merged/empty-grok-build-0.1-merged/summary.json",
        "lift_quality": "quality-empty-vs-current-grok-build-0.1/Grok-Build-0.1-empty-saved-model-quality/model-quality-summary.json",
        "color": "#7c3aed",
    },
    {
        "label": "DeepSeek V4 Flash",
        "short": "DeepSeek",
        "current": "current-deepseek-v4-flash/current/summary.json",
        "empty": "empty-deepseek-v4-flash/empty/summary.json",
        "lift_quality": "quality-empty-vs-current-deepseek-v4-flash/DeepSeek-V4-Flash-empty-saved-model-quality/model-quality-summary.json",
        "color": "#0891b2",
    },
    {
        "label": "Grok 4.3",
        "short": "Grok 4.3",
        "current": "current-grok-4.3/current/summary.json",
        "empty": "empty-grok-4.3/empty/summary.json",
        "lift_quality": "quality-empty-vs-current-grok-4.3/Grok-4.3-empty-saved-model-quality/model-quality-summary.json",
        "color": "#ea580c",
    },
    {
        "label": "DeepSeek V4 thinking",
        "short": "DS thinking",
        "current": "current-deepseek-v4-flash-thinking/current/summary.json",
        "empty": "empty-deepseek-v4-flash-thinking/empty/summary.json",
        "lift_quality": "quality-empty-vs-current-deepseek-v4-flash-thinking/DeepSeek-V4-Flash-thinking-empty-saved-model-quality/model-quality-summary.json",
        "color": "#0f766e",
    },
]

GPT_EXTERNAL_QUALITY = "quality-gpt55-vs-external-current/GPT-5.5-current-saved-model-quality/model-quality-summary.json"

REFERENCE_QUALITY = [
    {
        "label": "OpenHands AGENTS.md",
        "short": "OpenHands",
        "path": "compare-openhands-gpt55-quality/compare-reference-openhands-agents-current/quality.json",
    },
    {
        "label": "Claude/Fable prompt",
        "short": "Fable",
        "path": "compare-claude-fable-gpt55-quality/compare-reference-claude-fable-5-current/quality.json",
    },
]

INK = "#0f172a"
MUTED = "#64748b"
SUBTLE = "#e2e8f0"
TRACK = "#f1f5f9"
PANEL = "#ffffff"
BORDER = "#cbd5e1"
EMPTY = "#94a3b8"
CURRENT = "#2563eb"
REFERENCE = "#7c3aed"
TIE = "#f59e0b"
INCONCLUSIVE = "#cbd5e1"
DANGER = "#dc2626"


def read_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"missing artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"missing case file: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def pct(value: float, total: float) -> float:
    return 0 if total == 0 else value / total


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def svg_start(width: int, height: int, title: str, desc: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f"<title id=\"title\">{esc(title)}</title>",
        f"<desc id=\"desc\">{esc(desc)}</desc>",
        "<style>",
        "text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}",
        ".title{font-size:30px;font-weight:700;fill:#0f172a}",
        ".subtitle{font-size:15px;fill:#64748b}",
        ".label{font-size:14px;font-weight:600;fill:#0f172a}",
        ".small{font-size:12px;fill:#64748b}",
        ".value{font-size:13px;font-weight:700;fill:#0f172a}",
        ".pill{font-size:12px;font-weight:700;fill:#0f172a}",
        ".axis{font-size:11px;fill:#64748b}",
        "</style>",
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="0" fill="#f8fafc"/>',
    ]


def write_svg(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def text(x: float, y: float, value: object, cls: str = "label", anchor: str | None = None) -> str:
    anchor_attr = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}"{anchor_attr}>{esc(value)}</text>'


def rect(x: float, y: float, width: float, height: float, fill: str, rx: float = 6, stroke: str | None = None) -> str:
    stroke_attr = f' stroke="{stroke}"' if stroke else ""
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(width, 0):.1f}" height="{height:.1f}" rx="{rx:.1f}" fill="{fill}"{stroke_attr}/>'


def line(x1: float, y1: float, x2: float, y2: float, color: str = SUBTLE) -> str:
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="1"/>'


def panel(x: float, y: float, width: float, height: float) -> list[str]:
    return [
        rect(x, y, width, height, PANEL, rx=12, stroke=BORDER),
    ]


def pill(x: float, y: float, value: object, fill: str = "#dbeafe", width: float = 58) -> list[str]:
    return [
        rect(x, y, width, 24, fill, rx=12),
        text(x + width / 2, y + 16, value, "pill", anchor="middle"),
    ]


def footer(width: int, y: float, source: str) -> list[str]:
    return [
        line(32, y - 18, width - 32, y - 18, "#e5e7eb"),
        text(32, y, source, "small"),
        text(width - 32, y, "Generated by scripts/build_readme_infographics.py", "small", anchor="end"),
    ]


def load_summary(refresh_root: Path, rel_path: str) -> dict[str, Any]:
    data = read_json(refresh_root / rel_path)
    return {
        "passed": int(data["passed"]),
        "failed": int(data["failed"]),
        "total": int(data["total"]),
        "results": data["results"],
    }


def model_rows(refresh_root: Path) -> list[dict[str, Any]]:
    rows = []
    for model in MODELS:
        current_summary = load_summary(refresh_root, model["current"])
        empty_summary = load_summary(refresh_root, model["empty"])
        quality = read_json(refresh_root / model["lift_quality"])
        aggregate = quality["pairs"][0]["aggregate"]
        rows.append(
            {
                **model,
                "current_passed": current_summary["passed"],
                "empty_passed": empty_summary["passed"],
                "total": current_summary["total"],
                "lift": current_summary["passed"] - empty_summary["passed"],
                "quality_delta": aggregate["average_delta"],
                "current_score": aggregate["average_current_score"],
                "empty_score": aggregate["average_baseline_score"],
                "current_results": current_summary["results"],
                "empty_results": empty_summary["results"],
            }
        )
    return rows


def gpt_external_rows(refresh_root: Path) -> list[dict[str, Any]]:
    data = read_json(refresh_root / GPT_EXTERNAL_QUALITY)
    labels = {
        "Grok-4.3-current": "Grok 4.3",
        "Grok-Build-0.1-current": "Grok Build",
        "DeepSeek-V4-Flash-current": "DeepSeek",
        "DeepSeek-V4-Flash-thinking-current": "DS thinking",
        "GLM-5.2-current": "GLM-5.2",
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
                "ties": winners["tie"],
                "gpt_wins": winners["baseline"],
                "inconclusive": winners["inconclusive"],
                "avg_score": aggregate["average_current_score"],
                "delta": aggregate["average_delta"],
            }
        )
    return rows


def model_quality_pair_paths(refresh_root: Path, prefix: str) -> list[Path]:
    return sorted(refresh_root.glob(f"{prefix}/*-saved-model-quality/pairs/*/quality.json"))


def pass_pass_counts(comparisons: list[dict[str, Any]], *, current_key: str = "candidate") -> dict[str, Any]:
    both_passed = [
        comparison
        for comparison in comparisons
        if comparison["baseline"]["passed"] and comparison[current_key]["passed"]
    ]
    winners = {"current": 0, "baseline": 0, "tie": 0, "inconclusive": 0}
    current_scores: list[float] = []
    baseline_scores: list[float] = []
    for comparison in both_passed:
        quality = comparison.get("quality") or {}
        winner = quality.get("winner")
        if winner in winners:
            winners[winner] += 1
        if isinstance(quality.get("current_score"), (int, float)):
            current_scores.append(float(quality["current_score"]))
        if isinstance(quality.get("baseline_score"), (int, float)):
            baseline_scores.append(float(quality["baseline_score"]))
    avg_current = round(sum(current_scores) / len(current_scores), 1) if current_scores else 0
    avg_baseline = round(sum(baseline_scores) / len(baseline_scores), 1) if baseline_scores else 0
    return {
        "total": len(both_passed),
        "winners": winners,
        "avg_current": avg_current,
        "avg_baseline": avg_baseline,
        "avg_delta": round(avg_current - avg_baseline, 1),
    }


def pass_pass_current_empty_rows(refresh_root: Path) -> list[dict[str, Any]]:
    labels = {
        "GPT-5.5-current": "GPT",
        "GLM-5.2-current": "GLM",
        "Grok-Build-0.1-current": "Grok Build",
        "DeepSeek-V4-Flash-current": "DeepSeek",
        "Grok-4.3-current": "Grok 4.3",
        "DeepSeek-V4-Flash-thinking-current": "DS thinking",
    }
    order = ["GPT", "GLM", "Grok Build", "DeepSeek", "Grok 4.3", "DS thinking"]
    rows = []
    for path in model_quality_pair_paths(refresh_root, "quality-empty-vs-current-*"):
        data = read_json(path)
        counts = pass_pass_counts(data["comparisons"])
        rows.append({"label": labels.get(data["candidate_label"], data["candidate_label"]), **counts})
    return sorted(rows, key=lambda row: order.index(row["label"]) if row["label"] in order else 999)


def pass_pass_gpt_external_rows(refresh_root: Path) -> list[dict[str, Any]]:
    labels = {
        "Grok-4.3-current": "Grok 4.3",
        "Grok-Build-0.1-current": "Grok Build",
        "DeepSeek-V4-Flash-current": "DeepSeek",
        "DeepSeek-V4-Flash-thinking-current": "DS thinking",
        "GLM-5.2-current": "GLM",
    }
    order = ["GLM", "Grok Build", "DeepSeek", "Grok 4.3", "DS thinking"]
    rows = []
    pair_root = refresh_root / "quality-gpt55-vs-external-current/GPT-5.5-current-saved-model-quality/pairs"
    for path in sorted(pair_root.glob("*/quality.json")):
        data = read_json(path)
        counts = pass_pass_counts(data["comparisons"])
        rows.append({"label": labels.get(data["candidate_label"], data["candidate_label"]), **counts})
    return sorted(rows, key=lambda row: order.index(row["label"]) if row["label"] in order else 999)


def pass_pass_reference_rows(refresh_root: Path) -> list[dict[str, Any]]:
    rows = []
    for item in REFERENCE_QUALITY:
        data = read_json(refresh_root / item["path"])
        counts = pass_pass_counts(data["comparisons"], current_key="current")
        rows.append({"label": item["short"], **counts})
    return rows


def find_pair_report(refresh_root: Path, prefix: str, candidate_label: str) -> Path:
    for path in model_quality_pair_paths(refresh_root, prefix):
        data = read_json(path)
        if data.get("candidate_label") == candidate_label:
            return path
    raise SystemExit(f"missing quality pair for {candidate_label} under {prefix}")


def pass_pass_case_results(path: Path, *, current_key: str = "candidate") -> dict[str, dict[str, Any]]:
    data = read_json(path)
    results: dict[str, dict[str, Any]] = {}
    for comparison in data["comparisons"]:
        if not (comparison["baseline"]["passed"] and comparison[current_key]["passed"]):
            continue
        quality = comparison.get("quality") or {}
        baseline_score = quality.get("baseline_score")
        current_score = quality.get("current_score")
        delta = (
            current_score - baseline_score
            if isinstance(baseline_score, (int, float)) and isinstance(current_score, (int, float))
            else None
        )
        results[comparison["case_id"]] = {
            "winner": quality.get("winner", ""),
            "delta": delta,
            "baseline_score": baseline_score,
            "current_score": current_score,
        }
    return results


def reference_rows(refresh_root: Path) -> list[dict[str, Any]]:
    rows = []
    for item in REFERENCE_QUALITY:
        data = read_json(refresh_root / item["path"])
        comparisons = data["comparisons"]
        winners = {"current": 0, "baseline": 0, "tie": 0, "inconclusive": 0}
        current_scores: list[float] = []
        reference_scores: list[float] = []
        current_passed = 0
        reference_passed = 0
        for comparison in comparisons:
            current_passed += int(bool(comparison["current"]["passed"]))
            reference_passed += int(bool(comparison["baseline"]["passed"]))
            quality = comparison.get("quality") or {}
            winner = quality.get("winner")
            if winner in winners:
                winners[winner] += 1
            if isinstance(quality.get("current_score"), (int, float)):
                current_scores.append(float(quality["current_score"]))
            if isinstance(quality.get("baseline_score"), (int, float)):
                reference_scores.append(float(quality["baseline_score"]))
        avg_current = round(sum(current_scores) / len(current_scores), 1)
        avg_reference = round(sum(reference_scores) / len(reference_scores), 1)
        rows.append(
            {
                **item,
                "total": len(comparisons),
                "current_passed": current_passed,
                "reference_passed": reference_passed,
                "wins": winners,
                "avg_current": avg_current,
                "avg_reference": avg_reference,
                "avg_delta": round(avg_current - avg_reference, 1),
                "comparisons": comparisons,
            }
        )
    return rows


def draw_scale(lines: list[str], x: float, y: float, width: float, total: int, labels: list[int]) -> None:
    for value in labels:
        position = x + width * pct(value, total)
        lines.append(line(position, y, position, y + 390, "#e5e7eb"))
        lines.append(text(position, y - 8, value, "axis", anchor="middle"))


def render_instruction_lift(refresh_root: Path, output_dir: Path) -> None:
    rows = model_rows(refresh_root)
    width = 1120
    height = 640
    lines = svg_start(
        width,
        height,
        "Instruction lift across models",
        "Current instructions versus empty instruction bundle on the 49-case eval suite.",
    )
    lines.append(text(40, 56, "Instruction lift across models", "title"))
    lines.append(text(40, 84, "49 cases. Hard-gate passes improve for every tested model; quality deltas stay strongly positive.", "subtitle"))
    lines.extend(panel(40, 110, 1040, 430))
    lines.append(text(72, 145, "Model", "axis"))
    lines.append(text(260, 145, "Hard-gate passes out of 49", "axis"))
    lines.append(text(1010, 145, "Quality delta", "axis", anchor="middle"))
    draw_scale(lines, 260, 172, 520, 49, [0, 10, 20, 30, 40, 49])

    for index, row in enumerate(rows):
        y = 185 + index * 56
        lines.append(text(72, y + 18, row["label"], "label"))
        lines.append(rect(260, y, 520, 12, TRACK, rx=6))
        lines.append(rect(260, y, 520 * pct(row["empty_passed"], row["total"]), 12, EMPTY, rx=6))
        lines.append(rect(260, y + 18, 520, 14, TRACK, rx=7))
        lines.append(rect(260, y + 18, 520 * pct(row["current_passed"], row["total"]), 14, row["color"], rx=7))
        lines.append(text(794, y + 10, f"empty {row['empty_passed']}/49", "small"))
        lines.append(text(794, y + 30, f"current {row['current_passed']}/49", "value"))
        lines.extend(pill(890, y + 6, f"+{row['lift']}", "#dcfce7", width=54))
        delta = row["quality_delta"]
        lines.append(text(1010, y + 23, f"+{delta:.1f}", "value", anchor="middle"))

    lines.append(rect(70, 568, 16, 10, EMPTY, rx=5))
    lines.append(text(94, 577, "Empty bundle", "small"))
    lines.append(rect(194, 568, 16, 10, CURRENT, rx=5))
    lines.append(text(218, 577, "Current instructions", "small"))
    lines.extend(footer(width, 612, "Source: 49-case refresh summaries and current-vs-empty quality aggregates"))
    lines.append("</svg>")
    write_svg(output_dir / "instruction-lift.svg", lines)


def render_model_transfer(refresh_root: Path, output_dir: Path) -> None:
    rows = model_rows(refresh_root)
    external = gpt_external_rows(refresh_root)
    width = 1120
    height = 660
    lines = svg_start(
        width,
        height,
        "Cross-model transfer on current instructions",
        "Hard-gate coverage and quality wins for external models against GPT-5.5.",
    )
    lines.append(text(40, 56, "Cross-model transfer", "title"))
    lines.append(text(40, 84, "GLM is the only external model close to GPT on hard gates and pass/pass quality.", "subtitle"))

    lines.extend(panel(40, 112, 505, 455))
    lines.append(text(72, 148, "Current hard gates", "label"))
    lines.append(text(72, 170, "Bars show passed cases out of 49.", "small"))
    for index, row in enumerate(rows):
        y = 205 + index * 52
        lines.append(text(72, y + 14, row["short"], "label"))
        lines.append(rect(190, y, 270, 16, TRACK, rx=8))
        lines.append(rect(190, y, 270 * pct(row["current_passed"], row["total"]), 16, row["color"], rx=8))
        lines.append(text(478, y + 13, f"{row['current_passed']}/49", "value"))

    lines.extend(panel(575, 112, 505, 455))
    lines.append(text(607, 148, "External quality vs GPT-5.5", "label"))
    lines.append(text(607, 170, "Candidate wins / ties / GPT wins / inconclusive.", "small"))
    legend_x = 607
    for label, color, offset in [("candidate", "#16a34a", 0), ("tie", TIE, 95), ("GPT", "#334155", 145), ("inconclusive", INCONCLUSIVE, 195)]:
        lines.append(rect(legend_x + offset, 188, 12, 12, color, rx=3))
        lines.append(text(legend_x + offset + 18, 199, label, "axis"))

    for index, row in enumerate(external):
        y = 230 + index * 62
        lines.append(text(607, y + 16, row["label"], "label"))
        x = 735
        bar_width = 255
        segments = [
            (row["wins"], "#16a34a"),
            (row["ties"], TIE),
            (row["gpt_wins"], "#334155"),
            (row["inconclusive"], INCONCLUSIVE),
        ]
        cursor = x
        for value, color in segments:
            segment_width = bar_width * pct(value, row["total"])
            if segment_width > 0:
                lines.append(rect(cursor, y, segment_width, 18, color, rx=4))
            cursor += segment_width
        lines.append(rect(x, y, bar_width, 18, "none", rx=4, stroke="#e5e7eb"))
        lines.append(text(1008, y + 14, f"{row['wins']}/{row['ties']}/{row['gpt_wins']}", "value"))
        lines.append(text(735, y + 39, f"avg {row['avg_score']:.1f}, delta {row['delta']:.1f}", "small"))

    lines.extend(pill(72, 518, "GPT 42/49", "#dbeafe", width=86))
    lines.extend(pill(172, 518, "GLM 41/49", "#dcfce7", width=86))
    lines.append(text(282, 535, "Grok Build is improved but still far behind GPT on quality wins.", "small"))
    lines.extend(footer(width, 630, "Source: GPT-vs-external model-quality-summary.json"))
    lines.append("</svg>")
    write_svg(output_dir / "model-transfer.svg", lines)


def render_reference_prompts(refresh_root: Path, output_dir: Path) -> None:
    rows = reference_rows(refresh_root)
    width = 1120
    height = 560
    lines = svg_start(
        width,
        height,
        "Reference prompt comparison",
        "Current instruction bundle compared with OpenHands and Claude/Fable reference prompts.",
    )
    lines.append(text(40, 56, "Reference prompt comparison", "title"))
    lines.append(text(40, 84, "Current keeps the aggregate edge, while references identify targeted watchlist cases.", "subtitle"))

    for index, row in enumerate(rows):
        x = 40 + index * 540
        y = 118
        lines.extend(panel(x, y, 500, 330))
        lines.append(text(x + 30, y + 42, row["label"], "label"))
        lines.append(text(x + 30, y + 66, f"Hard gates: current {row['current_passed']}/49 vs reference {row['reference_passed']}/49", "small"))
        bar_x = x + 30
        bar_y = y + 92
        bar_width = 355
        lines.append(rect(bar_x, bar_y, bar_width, 16, TRACK, rx=8))
        lines.append(rect(bar_x, bar_y, bar_width * pct(row["reference_passed"], 49), 16, REFERENCE, rx=8))
        lines.append(text(bar_x + bar_width + 18, bar_y + 13, f"ref {row['reference_passed']}", "value"))
        lines.append(rect(bar_x, bar_y + 28, bar_width, 16, TRACK, rx=8))
        lines.append(rect(bar_x, bar_y + 28, bar_width * pct(row["current_passed"], 49), 16, CURRENT, rx=8))
        lines.append(text(bar_x + bar_width + 18, bar_y + 41, f"cur {row['current_passed']}", "value"))

        lines.append(text(x + 30, y + 174, "Quality outcomes", "label"))
        wins = row["wins"]
        segments = [
            (wins["current"], CURRENT, "current"),
            (wins["tie"], TIE, "tie"),
            (wins["baseline"], REFERENCE, "reference"),
            (wins["inconclusive"], INCONCLUSIVE, "inconclusive"),
        ]
        cursor = bar_x
        for value, color, _label in segments:
            segment_width = bar_width * pct(value, row["total"])
            if segment_width > 0:
                lines.append(rect(cursor, y + 195, segment_width, 22, color, rx=5))
            cursor += segment_width
        lines.append(rect(bar_x, y + 195, bar_width, 22, "none", rx=5, stroke="#e5e7eb"))
        lines.append(text(x + 30, y + 248, f"current wins {wins['current']}", "small"))
        lines.append(text(x + 155, y + 248, f"ties {wins['tie']}", "small"))
        lines.append(text(x + 225, y + 248, f"reference wins {wins['baseline']}", "small"))
        lines.append(text(x + 370, y + 248, f"inconclusive {wins['inconclusive']}", "small"))
        lines.extend(pill(x + 30, y + 280, f"avg delta +{row['avg_delta']:.1f}", "#dcfce7", width=116))
        if row["short"] == "OpenHands":
            note = "Reference win: skill-invocation-trigger-controls"
        else:
            note = "Reference win: characterization-test-before-fix"
        lines.append(text(x + 165, y + 297, note, "small"))

    lines.extend(footer(width, 528, "Source: reference quality.json comparison artifacts"))
    lines.append("</svg>")
    write_svg(output_dir / "reference-prompts.svg", lines)


def draw_outcome_bar(
    lines: list[str],
    *,
    x: float,
    y: float,
    width: float,
    total: int,
    current: int,
    tie: int,
    baseline: int,
    current_color: str = CURRENT,
    baseline_color: str = REFERENCE,
) -> None:
    segments = [
        (current, current_color),
        (tie, TIE),
        (baseline, baseline_color),
    ]
    cursor = x
    for value, color in segments:
        segment_width = width * pct(value, total)
        if segment_width > 0:
            lines.append(rect(cursor, y, segment_width, 18, color, rx=4))
        cursor += segment_width
    lines.append(rect(x, y, width, 18, "none", rx=4, stroke="#e5e7eb"))


def render_quality_only_comparisons(refresh_root: Path, output_dir: Path) -> None:
    current_empty = pass_pass_current_empty_rows(refresh_root)
    gpt_external = pass_pass_gpt_external_rows(refresh_root)
    references = pass_pass_reference_rows(refresh_root)
    width = 1120
    height = 720
    lines = svg_start(
        width,
        height,
        "Quality-only comparisons after hard gates pass",
        "Only pass/pass cases are included, so the bars compare judged response quality rather than deterministic failures.",
    )
    lines.append(text(40, 56, "Quality-only comparisons", "title"))
    lines.append(text(40, 84, "Only cases where both sides passed deterministic hard gates. Bars show judged quality wins and ties.", "subtitle"))

    lines.extend(panel(40, 116, 500, 500))
    lines.append(text(72, 152, "Current vs empty", "label"))
    lines.append(text(72, 174, "Among pass/pass cases, current usually wins on quality.", "small"))
    lines.append(rect(72, 193, 12, 12, CURRENT, rx=3))
    lines.append(text(90, 204, "current", "axis"))
    lines.append(rect(156, 193, 12, 12, TIE, rx=3))
    lines.append(text(174, 204, "tie", "axis"))
    lines.append(rect(212, 193, 12, 12, EMPTY, rx=3))
    lines.append(text(230, 204, "empty", "axis"))
    for index, row in enumerate(current_empty):
        y = 232 + index * 56
        winners = row["winners"]
        lines.append(text(72, y + 15, row["label"], "label"))
        draw_outcome_bar(
            lines,
            x=190,
            y=y,
            width=215,
            total=row["total"],
            current=winners["current"],
            tie=winners["tie"],
            baseline=winners["baseline"],
            baseline_color=EMPTY,
        )
        lines.append(text(422, y + 14, f"{winners['current']}/{winners['tie']}/{winners['baseline']}", "value"))
        lines.append(text(190, y + 38, f"{row['total']} pass/pass, avg delta {row['avg_delta']:+.1f}", "small"))

    lines.extend(panel(580, 116, 500, 300))
    lines.append(text(612, 152, "External models vs GPT-5.5", "label"))
    lines.append(text(612, 174, "Candidate / tie / GPT wins, pass/pass only.", "small"))
    lines.append(rect(612, 193, 12, 12, "#16a34a", rx=3))
    lines.append(text(630, 204, "candidate", "axis"))
    lines.append(rect(706, 193, 12, 12, TIE, rx=3))
    lines.append(text(724, 204, "tie", "axis"))
    lines.append(rect(756, 193, 12, 12, "#334155", rx=3))
    lines.append(text(774, 204, "GPT", "axis"))
    for index, row in enumerate(gpt_external):
        y = 232 + index * 36
        winners = row["winners"]
        lines.append(text(612, y + 14, row["label"], "label"))
        draw_outcome_bar(
            lines,
            x=716,
            y=y,
            width=205,
            total=row["total"],
            current=winners["current"],
            tie=winners["tie"],
            baseline=winners["baseline"],
            current_color="#16a34a",
            baseline_color="#334155",
        )
        lines.append(text(938, y + 14, f"{winners['current']}/{winners['tie']}/{winners['baseline']}", "value"))
        lines.append(text(998, y + 14, f"n={row['total']}", "small"))

    lines.extend(panel(580, 446, 500, 170))
    lines.append(text(612, 482, "Reference prompts vs current", "label"))
    lines.append(text(612, 504, "Current / tie / reference wins, pass/pass only.", "small"))
    for index, row in enumerate(references):
        y = 532 + index * 46
        winners = row["winners"]
        lines.append(text(612, y + 14, row["label"], "label"))
        draw_outcome_bar(
            lines,
            x=728,
            y=y,
            width=205,
            total=row["total"],
            current=winners["current"],
            tie=winners["tie"],
            baseline=winners["baseline"],
            baseline_color=REFERENCE,
        )
        lines.append(text(950, y + 14, f"{winners['current']}/{winners['tie']}/{winners['baseline']}", "value"))
        lines.append(text(1004, y + 14, f"n={row['total']}", "small"))

    lines.append(text(72, 648, "Read each triplet as left-side wins / ties / right-side wins. Hard-gate failures are excluded.", "label"))
    lines.extend(footer(width, 690, "Source: saved quality.json pair reports filtered to both sides passed"))
    lines.append("</svg>")
    write_svg(output_dir / "quality-only-comparisons.svg", lines)


def cell_fill(winner: str) -> str:
    if winner == "current":
        return "#dbeafe"
    if winner == "baseline":
        return "#ede9fe"
    if winner == "tie":
        return "#fef3c7"
    return "#f8fafc"


def cell_text(item: dict[str, Any] | None) -> str:
    if item is None:
        return ""
    if item.get("winner") == "tie":
        return "T"
    delta = item.get("delta")
    if isinstance(delta, (int, float)):
        return f"{delta:+.0f}"
    return str(item.get("winner", ""))


def render_quality_only_case_matrix(refresh_root: Path, output_dir: Path) -> None:
    cases = read_jsonl(CASE_FILE)
    columns = [
        {
            "header": "GPT/empty",
            "caption": "GPT current minus empty",
            "results": pass_pass_case_results(
                find_pair_report(refresh_root, "quality-empty-vs-current-gpt55", "GPT-5.5-current")
            ),
        },
        {
            "header": "GLM/empty",
            "caption": "GLM current minus empty",
            "results": pass_pass_case_results(
                find_pair_report(refresh_root, "quality-empty-vs-current-glm-5.2", "GLM-5.2-current")
            ),
        },
        {
            "header": "GLM/GPT",
            "caption": "GLM minus GPT",
            "results": pass_pass_case_results(
                find_pair_report(
                    refresh_root,
                    "quality-gpt55-vs-external-current",
                    "GLM-5.2-current",
                )
            ),
        },
        {
            "header": "GrokB/GPT",
            "caption": "Grok Build minus GPT",
            "results": pass_pass_case_results(
                find_pair_report(
                    refresh_root,
                    "quality-gpt55-vs-external-current",
                    "Grok-Build-0.1-current",
                )
            ),
        },
        {
            "header": "Cur/OH",
            "caption": "Current minus OpenHands",
            "results": pass_pass_case_results(
                refresh_root
                / "compare-openhands-gpt55-quality/compare-reference-openhands-agents-current/quality.json",
                current_key="current",
            ),
        },
        {
            "header": "Cur/Fable",
            "caption": "Current minus Fable",
            "results": pass_pass_case_results(
                refresh_root
                / "compare-claude-fable-gpt55-quality/compare-reference-claude-fable-5-current/quality.json",
                current_key="current",
            ),
        },
    ]
    visible_cases = [
        case
        for case in cases
        if any(case["id"] in column["results"] for column in columns)
    ]
    row_height = 24
    width = 1120
    height = 190 + len(visible_cases) * row_height + 118
    lines = svg_start(
        width,
        height,
        "Case-level quality-only matrix",
        "Per-case quality judge deltas for selected pass/pass comparisons.",
    )
    lines.append(text(40, 56, "Case-level quality-only matrix", "title"))
    lines.append(text(40, 84, "Per-case judge deltas. Only pass/pass comparisons are shown; blanks mean a hard gate failed on at least one side.", "subtitle"))
    lines.extend(panel(40, 112, 1040, height - 178))

    legend_y = 144
    lines.append(rect(72, legend_y - 12, 14, 14, "#dbeafe", rx=3))
    lines.append(text(94, legend_y, "left side wins", "axis"))
    lines.append(rect(188, legend_y - 12, 14, 14, "#fef3c7", rx=3))
    lines.append(text(210, legend_y, "tie", "axis"))
    lines.append(rect(254, legend_y - 12, 14, 14, "#ede9fe", rx=3))
    lines.append(text(276, legend_y, "right side wins", "axis"))
    lines.append(text(1012, legend_y, f"{len(visible_cases)} concrete cases", "small", anchor="end"))
    lines.append(text(72, 168, "Columns are left minus right: GPT/empty, GLM/empty, GLM/GPT, Grok Build/GPT, Current/OpenHands, Current/Fable.", "small"))

    table_x = 72
    case_width = 438
    cell_width = 84
    header_y = 198
    lines.append(text(table_x, header_y, "Case", "axis"))
    for index, column in enumerate(columns):
        x = table_x + case_width + index * cell_width
        lines.append(text(x + cell_width / 2, header_y, column["header"], "axis", anchor="middle"))

    start_y = 224
    for index, case in enumerate(visible_cases):
        y = start_y + index * row_height
        if index % 2 == 0:
            lines.append(rect(table_x - 8, y - 15, 982, row_height, "#f8fafc", rx=0))
        lines.append(text(table_x, y, case["id"], "small"))
        for col_index, column in enumerate(columns):
            x = table_x + case_width + col_index * cell_width
            item = column["results"].get(case["id"])
            fill = cell_fill(item["winner"]) if item else "#ffffff"
            stroke = "#e5e7eb" if item else "#f1f5f9"
            lines.append(rect(x + 8, y - 15, cell_width - 16, 18, fill, rx=5, stroke=stroke))
            value = cell_text(item)
            if value:
                lines.append(text(x + cell_width / 2, y - 2, value, "value", anchor="middle"))

    lines.append(text(72, height - 84, "Cell value is current/candidate score minus baseline score. Positive values favor the left side in the column header.", "label"))
    lines.extend(footer(width, height - 40, "Source: selected quality.json pair reports filtered to both sides passed"))
    lines.append("</svg>")
    write_svg(output_dir / "quality-only-case-matrix.svg", lines)


def result_map(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["case_id"]): item for item in records}


def render_coverage_watchlist(refresh_root: Path, output_dir: Path) -> None:
    cases = read_jsonl(CASE_FILE)
    case_ids = [case["id"] for case in cases]
    new_ids = case_ids[-6:]
    old_ids = case_ids[:-6]
    rows = model_rows(refresh_root)
    width = 1120
    height = 650
    lines = svg_start(
        width,
        height,
        "49-case coverage watchlist",
        "Old 43-case coverage remains strong, while the six new strict cases expose unresolved gaps.",
    )
    lines.append(text(40, 56, "49-case coverage watchlist", "title"))
    lines.append(text(40, 84, "The headline score mixes a strong old suite with a new strict watchlist. Keep them visually separated.", "subtitle"))

    lines.extend(panel(40, 116, 610, 420))
    lines.append(text(72, 152, "Current pass split", "label"))
    lines.append(text(262, 152, "Original 43 cases", "axis"))
    lines.append(text(510, 152, "New strict 6", "axis"))
    for index, row in enumerate(rows):
        current = result_map(row["current_results"])
        old_passed = sum(1 for case_id in old_ids if current[case_id]["passed"])
        new_passed = sum(1 for case_id in new_ids if current[case_id]["passed"])
        y = 188 + index * 52
        lines.append(text(72, y + 14, row["short"], "label"))
        lines.append(rect(220, y, 250, 16, TRACK, rx=8))
        lines.append(rect(220, y, 250 * pct(old_passed, len(old_ids)), 16, row["color"], rx=8))
        lines.append(text(482, y + 13, f"{old_passed}/43", "value"))
        lines.append(rect(550, y, 58, 16, TRACK, rx=8))
        fill = row["color"] if new_passed else DANGER
        lines.append(rect(550, y, 58 * pct(max(new_passed, 0.15), len(new_ids)), 16, fill, rx=8))
        lines.append(text(618, y + 13, f"{new_passed}/6", "value"))

    lines.extend(panel(680, 116, 400, 420))
    lines.append(text(712, 152, "What the new cases found", "label"))
    bullets = [
        ("skill-invocation-trigger-controls", "OpenHands hard-gate win; GLM passes"),
        ("characterization-test-before-fix", "Fable hard-gate win"),
        ("context-file-overhead-budget", "both-fail watchlist"),
        ("adr-violation-evidence", "both-fail watchlist"),
        ("architecture-traceability-link-recovery", "both-fail watchlist"),
        ("tool-output-prompt-injection-utility-security", "both-fail watchlist"),
    ]
    for index, (case_id, note) in enumerate(bullets):
        y = 190 + index * 48
        color = "#fee2e2" if "both-fail" in note else "#fef3c7"
        lines.append(rect(712, y - 18, 336, 34, color, rx=8))
        lines.append(text(728, y - 2, case_id, "value"))
        lines.append(text(728, y + 15, note, "small"))

    lines.append(text(72, 570, "Read this as: old coverage still holds; new strict cases are a focused improvement backlog.", "label"))
    lines.extend(footer(width, 620, "Source: evals/cases.jsonl plus 49-case current summaries and reference quality artifacts"))
    lines.append("</svg>")
    write_svg(output_dir / "coverage-watchlist.svg", lines)


def build_all(repo_root: Path, refresh_root: Path, output_dir: Path) -> None:
    if not refresh_root.is_absolute():
        refresh_root = repo_root / refresh_root
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    render_instruction_lift(refresh_root, output_dir)
    render_model_transfer(refresh_root, output_dir)
    render_reference_prompts(refresh_root, output_dir)
    render_quality_only_comparisons(refresh_root, output_dir)
    render_quality_only_case_matrix(refresh_root, output_dir)
    render_coverage_watchlist(refresh_root, output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-root", default=str(DEFAULT_REFRESH_ROOT), help="Saved 49-case refresh artifact root.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for generated README SVGs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    build_all(repo_root, Path(args.refresh_root), Path(args.output_dir))
    print(f"wrote {Path(args.output_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
