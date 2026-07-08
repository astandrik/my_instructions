#!/usr/bin/env python3
"""Build README SVG and social-card infographics from saved 50-case eval artifacts."""

from __future__ import annotations

import argparse
import html
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = Path("docs/assets/readme")
DEFAULT_SOCIAL_IMAGE = Path("docs/assets/social/instruction-quality-lift-linkedin.png")
CASE_FILE = Path("evals/cases.jsonl")
PUBLIC_ROOT = Path(".eval-results/refresh-2026-07-08-50-case-public-v1")
PROVIDER_ROOT_V1 = Path(".eval-results/refresh-2026-07-08-50-case-v1")
PROVIDER_ROOT_V2 = Path(".eval-results/refresh-2026-07-08-50-case-v2")
QUALITY_ROOT = Path(".eval-results/refresh-2026-07-08-50-case-quality-v1")
SNAPSHOT_SCOPE = (
    "Scope: 50-case saved hard-gate and quality snapshot; "
    "all-model reference rows included."
)
SOCIAL_PNG_METADATA = {
    "instruction_snapshot_cases": "50",
    "instruction_snapshot_scope": SNAPSHOT_SCOPE,
    "instruction_snapshot_quality_root": str(QUALITY_ROOT),
    "generated_by": "scripts/build_readme_infographics.py",
}

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
CURRENT_FILL = "#bfdbfe"
BASELINE_FILL = "#fecdd3"
TIE_FILL = "#fef3c7"
INCONCLUSIVE_FILL = "#f1f5f9"

MODELS = [
    {
        "label": "GPT-5.5",
        "short": "GPT",
        "color": "#2563eb",
        "current": PUBLIC_ROOT / "current-gpt55/current/summary.json",
        "empty": PUBLIC_ROOT / "empty-gpt55/empty/summary.json",
        "quality": QUALITY_ROOT
        / "empty-vs-current-gpt55/GPT-5.5-empty-saved-model-quality/model-quality-summary.json",
        "note": "anchor row",
    },
    {
        "label": "GLM-5.2",
        "short": "GLM",
        "color": "#16a34a",
        "current": PROVIDER_ROOT_V2 / "current-glm-5.2/current/summary.json",
        "empty": PROVIDER_ROOT_V2 / "empty-glm-5.2/empty/summary.json",
        "quality": QUALITY_ROOT
        / "empty-vs-current-glm-5.2/GLM-5.2-empty-saved-model-quality/model-quality-summary.json",
        "note": "closest external row",
    },
    {
        "label": "Grok 4.3",
        "short": "Grok 4.3",
        "color": "#ea580c",
        "current": PROVIDER_ROOT_V1 / "current-grok-4.3/current/summary.json",
        "empty": PROVIDER_ROOT_V1 / "empty-grok-4.3/empty/summary.json",
        "quality": QUALITY_ROOT
        / "empty-vs-current-grok-4.3/Grok-4.3-empty-saved-model-quality/model-quality-summary.json",
        "note": "ADI failed in full run",
    },
    {
        "label": "Grok Build 0.1",
        "short": "Grok Build",
        "color": "#7c3aed",
        "current": PROVIDER_ROOT_V1 / "current-grok-build-0.1/current/summary.json",
        "empty": PROVIDER_ROOT_V1 / "empty-grok-build-0.1/empty/summary.json",
        "quality": QUALITY_ROOT
        / "empty-vs-current-grok-build-0.1/Grok-Build-0.1-empty-saved-model-quality/model-quality-summary.json",
        "note": "adapter row",
    },
    {
        "label": "DeepSeek V4 Flash",
        "short": "DeepSeek",
        "color": "#0891b2",
        "current": PUBLIC_ROOT / "current-deepseek-v4-flash/current/summary.json",
        "empty": PROVIDER_ROOT_V1 / "empty-deepseek-v4-flash/empty/summary.json",
        "quality": QUALITY_ROOT
        / "empty-vs-current-deepseek-v4-flash/DeepSeek-V4-Flash-empty-saved-model-quality/model-quality-summary.json",
        "note": "non-thinking",
    },
    {
        "label": "DeepSeek V4 thinking",
        "short": "DS thinking",
        "color": "#0f766e",
        "current": PROVIDER_ROOT_V1 / "current-deepseek-v4-flash-thinking/current/summary.json",
        "empty": PROVIDER_ROOT_V1 / "empty-deepseek-v4-flash-thinking/empty/summary.json",
        "quality": QUALITY_ROOT
        / "empty-vs-current-deepseek-v4-flash-thinking/DeepSeek-V4-Flash-thinking-empty-saved-model-quality/model-quality-summary.json",
        "note": "thinking mode",
    },
]

GPT_EXTERNAL_QUALITY = (
    QUALITY_ROOT / "gpt-vs-external-current/GPT-5.5-saved-model-quality/model-quality-summary.json"
)

REFERENCE_QUALITY_SUMMARIES = [
    {
        "reference": "OpenHands",
        "short": "OH",
        "color": OPENHANDS,
        "quality": QUALITY_ROOT
        / "quality-reference-openhands-vs-current-all-models-full-v1/Reference-OpenHands-saved-model-quality/model-quality-summary.json",
    },
    {
        "reference": "Claude/Fable",
        "short": "Fable",
        "color": FABLE,
        "quality": QUALITY_ROOT
        / "quality-reference-claude-fable-vs-current-all-models-full-v1/Reference-Fable-saved-model-quality/model-quality-summary.json",
    },
]

REFERENCE_MODEL_LABELS = {
    "GPT-5.5-current": ("GPT", "#2563eb"),
    "GLM-5.2-current": ("GLM", "#16a34a"),
    "Grok-4.3-current": ("Grok 4.3", "#ea580c"),
    "Grok-Build-0.1-current": ("Grok Build", "#7c3aed"),
    "DeepSeek-V4-Flash-current": ("DeepSeek", "#0891b2"),
    "DeepSeek-V4-Flash-thinking-current": ("DS thinking", "#0f766e"),
}


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


def rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def load_font(size: int, *, bold: bool = False) -> Any:
    from PIL import ImageFont

    candidates = [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def fit_font(draw: Any, value: str, size: int, max_width: int, *, bold: bool = False, min_size: int = 12) -> Any:
    while size > min_size:
        font = load_font(size, bold=bold)
        bbox = draw.textbbox((0, 0), value, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= 1
    return load_font(min_size, bold=bold)


def social_metric_card(draw: Any, x: int, y: int, width: int, title: str, value: str, caption: str, fill: str) -> None:
    draw.rounded_rectangle((x, y, x + width, y + 128), radius=22, fill=rgb(fill))
    draw.text((x + 30, y + 22), title, font=load_font(24, bold=True), fill=rgb(INK))
    draw.text((x + 30, y + 55), value, font=load_font(44, bold=True), fill=rgb(INK))
    draw.text((x + 30, y + 100), caption, font=load_font(18), fill=rgb(MUTED))


def render_social_card_png(repo_root: Path, path: Path) -> None:
    from PIL import Image, ImageDraw, PngImagePlugin

    rows = model_rows(repo_root)
    order = ["GPT", "GLM", "Grok Build", "Grok 4.3", "DeepSeek", "DS thinking"]
    rows = sorted(rows, key=lambda row: order.index(row["short"]) if row["short"] in order else 99)
    avg_current = sum(row["current_score"] for row in rows) / len(rows)
    avg_empty = sum(row["empty_score"] for row in rows) / len(rows)
    current_wins = sum(row["quality_current_wins"] for row in rows)
    empty_wins = sum(row["quality_empty_wins"] for row in rows)
    ties = sum(row["quality_ties"] for row in rows)
    inconclusive = sum(row["quality_inconclusive"] for row in rows)
    hard_gate_lift = sum(row["pass_delta"] for row in rows)

    width, height = 1600, 900
    image = Image.new("RGB", (width, height), rgb("#f8fafc"))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((36, 36, 1564, 864), radius=24, fill=rgb("#ffffff"), outline=rgb("#dbe3ef"), width=1)

    draw.text((80, 78), "50-case instruction eval snapshot", font=load_font(26, bold=True), fill=rgb("#475569"))
    title = "Instructions lift quality vs empty baselines"
    draw.text((80, 112), title, font=fit_font(draw, title, 58, 1440, bold=True), fill=rgb(INK))
    draw.text(
        (80, 184),
        "Current instruction bundle compared with empty bundle across six tested model rows.",
        font=load_font(28),
        fill=rgb("#475569"),
    )

    social_metric_card(draw, 80, 250, 320, "Avg quality score", f"{avg_current:.1f} vs {avg_empty:.1f}", "current vs empty, /100", "#dcfce7")
    social_metric_card(draw, 435, 250, 320, "Head-to-head wins", f"{current_wins} vs {empty_wins}", "current better vs empty better", "#dbeafe")
    social_metric_card(draw, 790, 250, 320, "Hard-gate lift", f"+{hard_gate_lift}", "passed cases across models", "#fef3c7")

    panel_x, panel_y, panel_w, panel_h = 80, 408, 1440, 410
    draw.rounded_rectangle((panel_x, panel_y, panel_x + panel_w, panel_y + panel_h), radius=20, fill=rgb("#ffffff"), outline=rgb("#dbe3ef"), width=1)
    draw.text((108, 424), "Average judge score by model", font=load_font(25, bold=True), fill=rgb(INK))
    draw.ellipse((948, 426, 964, 442), fill=rgb("#94a3b8"))
    draw.text((976, 422), "empty bundle", font=load_font(16, bold=True), fill=rgb(MUTED))
    draw.ellipse((1118, 426, 1134, 442), fill=rgb(CURRENT))
    draw.text((1146, 422), "current instructions", font=load_font(16, bold=True), fill=rgb(MUTED))

    axis_x, axis_w = 420, 545
    for tick in [0, 25, 50, 75, 100]:
        x = axis_x + int(axis_w * pct(tick, 100))
        draw.line((x, 472, x, 788), fill=rgb("#e5e7eb"), width=1)
        draw.text((x - 8, 448), str(tick), font=load_font(17, bold=True), fill=rgb(MUTED))

    for index, row in enumerate(rows):
        y = 490 + index * 56
        if index % 2 == 1:
            draw.rounded_rectangle((96, y - 22, 1504, y + 36), radius=12, fill=rgb("#f8fafc"))
        draw.text((108, y - 4), row["label"], font=load_font(24, bold=True), fill=rgb(INK))
        empty_w = int(axis_w * pct(row["empty_score"], 100))
        current_w = int(axis_w * pct(row["current_score"], 100))
        draw.rounded_rectangle((axis_x, y - 14, axis_x + axis_w, y - 2), radius=6, fill=rgb("#eef2f7"))
        draw.rounded_rectangle((axis_x, y - 14, axis_x + empty_w, y - 2), radius=6, fill=rgb("#94a3b8"))
        draw.rounded_rectangle((axis_x, y + 12, axis_x + axis_w, y + 25), radius=7, fill=rgb("#eef2f7"))
        draw.rounded_rectangle((axis_x, y + 12, axis_x + current_w, y + 25), radius=7, fill=rgb(row["color"]))

        draw.text((988, y - 20), f"{row['empty_score']:.1f}", font=load_font(20, bold=True), fill=rgb("#334155"))
        draw.text((1058, y - 20), "wins", font=load_font(16, bold=True), fill=rgb(MUTED))
        draw.text((1154, y - 20), "hard gates", font=load_font(16, bold=True), fill=rgb(MUTED))
        draw.text((988, y + 8), f"{row['current_score']:.1f}", font=load_font(20, bold=True), fill=rgb("#334155"))
        draw.text((1058, y + 8), f"{row['quality_current_wins']} vs {row['quality_empty_wins']}", font=load_font(20, bold=True), fill=rgb("#334155"))
        draw.text((1154, y + 8), f"{row['empty_passed']} -> {row['current_passed']}", font=load_font(20, bold=True), fill=rgb("#334155"))
        draw.rounded_rectangle((1314, y - 13, 1418, y + 24), radius=18, fill=rgb("#dcfce7"))
        draw.text((1326, y - 9), f"{row['quality_delta']:+.1f}", font=load_font(26, bold=True), fill=rgb(INK))

    footer_text = (
        "Source: saved empty-vs-current quality aggregates, 50 cases. "
        f"Wins are head-to-head judge choices; ties {ties}, inconclusive {inconclusive}."
    )
    draw.text((80, 838), footer_text, font=load_font(17, bold=True), fill=rgb(MUTED))

    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = PngImagePlugin.PngInfo()
    for key, value in SOCIAL_PNG_METADATA.items():
        metadata.add_text(key, value)
    image.save(path, pnginfo=metadata)


def resolve_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def compact_model_label(model: str) -> str:
    return {"Grok Build": "GB", "Grok 4.3": "G4", "DeepSeek": "DS", "DS thinking": "DSt"}.get(model, model)


def short_score(value: float) -> str:
    rounded = round(value)
    return "0" if rounded == 0 else f"{rounded:+d}"


def summary_counts(repo_root: Path, rel_path: Path) -> dict[str, Any]:
    data = read_json(resolve_path(repo_root, rel_path))
    results = data["results"]
    return {
        "passed": int(data.get("passed", sum(1 for item in results if item["passed"]))),
        "failed": int(data.get("failed", sum(1 for item in results if not item["passed"]))),
        "total": int(data.get("total", len(results))),
        "agent": sum(1 for item in results if item.get("failure_type") == "agent"),
        "results": results,
    }


def quality_pair(repo_root: Path, rel_path: Path) -> dict[str, Any]:
    data = read_json(resolve_path(repo_root, rel_path))
    pair = data["pairs"][0]
    return {
        "aggregate": pair["aggregate"],
        "pair_path": Path(pair["quality_json"]),
        "candidate_label": pair["candidate_label"],
        "baseline_label": data["baseline_label"],
    }


def quality_pairs(repo_root: Path, rel_path: Path) -> list[dict[str, Any]]:
    data = read_json(resolve_path(repo_root, rel_path))
    return [
        {
            "aggregate": pair["aggregate"],
            "pair_path": Path(pair["quality_json"]),
            "candidate_label": pair["candidate_label"],
            "baseline_label": data["baseline_label"],
        }
        for pair in data["pairs"]
    ]


def aggregate_quality_json(repo_root: Path, rel_path: Path) -> dict[str, Any]:
    data = read_json(resolve_path(repo_root, rel_path))
    winners = {"current": 0, "baseline": 0, "tie": 0, "inconclusive": 0}
    sources: dict[str, int] = {}
    confidence: dict[str, int] = {}
    deltas: list[float] = []
    for item in data["comparisons"]:
        quality = item["quality"]
        winner = quality.get("winner", "inconclusive")
        winners[winner if winner in winners else "inconclusive"] += 1
        source = quality.get("source", "unknown")
        sources[source] = sources.get(source, 0) + 1
        conf = quality.get("confidence", "unknown")
        confidence[conf] = confidence.get(conf, 0) + 1
        delta = quality.get("delta")
        if isinstance(delta, (int, float)):
            deltas.append(float(delta))
    return {
        "total": len(data["comparisons"]),
        "winners": winners,
        "sources": sources,
        "confidence": confidence,
        "average_delta": round(sum(deltas) / len(deltas), 1) if deltas else 0.0,
        "pair_path": resolve_path(repo_root, rel_path),
    }


def model_rows(repo_root: Path) -> list[dict[str, Any]]:
    rows = []
    for model in MODELS:
        current = summary_counts(repo_root, model["current"])
        empty = summary_counts(repo_root, model["empty"])
        quality = quality_pair(repo_root, model["quality"])
        aggregate = quality["aggregate"]
        winners = aggregate["winners"]
        rows.append(
            {
                **model,
                "current_passed": current["passed"],
                "current_failed": current["failed"],
                "empty_passed": empty["passed"],
                "empty_failed": empty["failed"],
                "total": current["total"],
                "agent": current["agent"],
                "empty_agent": empty["agent"],
                "pass_delta": current["passed"] - empty["passed"],
                "quality_current_wins": winners["current"],
                "quality_empty_wins": winners["baseline"],
                "quality_ties": winners["tie"],
                "quality_inconclusive": winners.get("inconclusive", 0),
                "quality_delta": aggregate["average_delta"],
                "current_score": aggregate["average_current_score"],
                "empty_score": aggregate["average_baseline_score"],
                "judge_calls": aggregate["sources"].get("llm_judge", 0),
                "hard_gate_shortcuts": aggregate["sources"].get("hard_gate", 0),
                "pair_path": quality["pair_path"],
                "results": current["results"],
            }
        )
    return rows


def gpt_external_rows(repo_root: Path) -> list[dict[str, Any]]:
    label_map = {
        "GLM-5.2": ("GLM", "#16a34a"),
        "Grok-4.3": ("Grok 4.3", "#ea580c"),
        "Grok-Build-0.1": ("Grok Build", "#7c3aed"),
        "DeepSeek-V4-Flash": ("DeepSeek", "#0891b2"),
        "DeepSeek-V4-Flash-thinking": ("DS thinking", "#0f766e"),
    }
    rows = []
    for pair in quality_pairs(repo_root, GPT_EXTERNAL_QUALITY):
        aggregate = pair["aggregate"]
        winners = aggregate["winners"]
        label, color = label_map.get(pair["candidate_label"], (pair["candidate_label"], "#334155"))
        rows.append(
            {
                "label": label,
                "candidate_label": pair["candidate_label"],
                "color": color,
                "hard_passed": aggregate["candidate_passed"],
                "gpt_passed": aggregate["baseline_passed"],
                "total": aggregate["total"],
                "wins": winners["current"],
                "gpt_wins": winners["baseline"],
                "ties": winners["tie"],
                "inconclusive": winners.get("inconclusive", 0),
                "delta": aggregate["average_delta"],
                "score": aggregate["average_current_score"],
                "gpt_score": aggregate["average_baseline_score"],
                "judge_calls": aggregate["sources"].get("llm_judge", 0),
                "hard_gate_shortcuts": aggregate["sources"].get("hard_gate", 0),
                "pair_path": pair["pair_path"],
            }
        )
    order = ["GLM", "Grok 4.3", "Grok Build", "DeepSeek", "DS thinking"]
    return sorted(rows, key=lambda row: order.index(row["label"]) if row["label"] in order else 999)


def reference_rows(repo_root: Path) -> list[dict[str, Any]]:
    rows = []
    for ref in REFERENCE_QUALITY_SUMMARIES:
        for pair in quality_pairs(repo_root, ref["quality"]):
            aggregate = pair["aggregate"]
            winners = aggregate["winners"]
            model_label, model_color = REFERENCE_MODEL_LABELS.get(pair["candidate_label"], (pair["candidate_label"], "#334155"))
            rows.append(
                {
                    **ref,
                    "model": model_label,
                    "model_color": model_color,
                    "candidate_label": pair["candidate_label"],
                    "label": f"{ref['short']}/{model_label}",
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
                    "pair_path": pair["pair_path"],
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


def render_hard_gates_50(repo_root: Path, output_dir: Path) -> None:
    rows = model_rows(repo_root)
    width = 1120
    height = 430
    lines = svg_start(
        width,
        height,
        "50-case hard-gate snapshot",
        "Hard-gate pass counts for the current 50-case instruction eval suite.",
    )
    lines.extend(panel(32, 28, 1056, 374))
    lines.append(text(56, 68, "50-case hard-gate snapshot", "title"))
    lines.append(text(56, 94, "Current eval contract after Agent Data Injection coverage; saved quality rows are available separately.", "subtitle"))
    lines.append(text(56, 132, "Model / runner", "axis"))
    lines.append(text(340, 132, "Current instructed", "axis"))
    lines.append(text(682, 132, "Empty bundle", "axis"))
    lines.append(text(934, 132, "Notes", "axis"))
    for index, row in enumerate(rows):
        y = 168 + index * 44
        lines.append(text(56, y, row["label"], "label"))
        lines.append(rect(340, y - 12, 300, 16, "#e2e8f0", rx=8))
        lines.append(rect(340, y - 12, 300 * pct(row["current_passed"], row["total"]), 16, row["color"], rx=8))
        lines.append(text(652, y + 1, f"{row['current_passed']}/{row['total']}", "value"))
        lines.append(rect(682, y - 12, 300, 16, "#e2e8f0", rx=8))
        lines.append(rect(682, y - 12, 300 * pct(row["empty_passed"], row["total"]), 16, "#94a3b8", rx=8))
        lines.append(text(994, y + 1, f"{row['empty_passed']}/{row['total']}", "value"))
        lines.append(text(934, y + 24, row["note"], "small"))
    lines.extend(footer(width, 414, "Source: .eval-results/refresh-2026-07-08-50-case-* summaries."))
    lines.append("</svg>")
    write_svg(output_dir / "hard-gates-50.svg", lines)


def render_instruction_lift(repo_root: Path, output_dir: Path) -> None:
    rows = model_rows(repo_root)
    external = gpt_external_rows(repo_root)
    references = reference_rows(repo_root)
    gpt = next(row for row in rows if row["short"] == "GPT")
    glm_gap = next(row for row in external if row["label"] == "GLM")
    width = 1120
    height = 560
    lines = svg_start(
        width,
        height,
        "50-case instruction eval overview",
        "Headline answers from the 50-case hard-gate, saved quality, and GPT reference snapshots.",
    )
    lines.append(text(40, 56, "50-case instruction eval overview", "title"))
    lines.append(text(40, 84, "Read left to right: current-vs-empty lift, external model gap, GPT reference contrast, and scope caveat.", "subtitle"))
    card_w = 248
    cards = [
        (
            40,
            "GPT clears hard gates",
            f"{gpt['current_passed']}/{gpt['total']} current vs {gpt['empty_passed']}/{gpt['total']} empty",
            f"quality split {gpt['quality_current_wins']}/{gpt['quality_ties']}/{gpt['quality_empty_wins']}, avg {gpt['quality_delta']:+.1f}",
            CURRENT,
        ),
        (
            310,
            "Instruction lift transfers",
            f"{sum(1 for row in rows if row['pass_delta'] > 0)}/{len(rows)} models improve hard gates",
            f"saved quality deltas all positive; GLM +{next(row for row in rows if row['short'] == 'GLM')['quality_delta']:.1f}",
            GOOD,
        ),
        (
            580,
            "External gap remains",
            f"GLM gap vs GPT {glm_gap['delta']:+.1f}",
            f"GLM split {glm_gap['wins']}/{glm_gap['ties']}/{glm_gap['gpt_wins']}; others trail heavily",
            TIE,
        ),
        (
            850,
            "References now all-model",
            f"{sum(row['current_wins'] for row in references)} current wins across {sum(row['total'] for row in references)} compares",
            "two references x six runners",
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
    lines.append(text(72, 374, "The 50-case refresh is publication-ready for hard gates, current-vs-empty saved quality, and all-model reference comparisons.", "value"))
    lines.append(text(72, 402, "Reference rows are observed saved-output comparisons for two reference bundles across six runners.", "value"))
    lines.append(text(72, 430, "Treat external transfer as mixed: instructions lift every tested model versus empty, but GPT remains the quality anchor.", "value"))
    lines.extend(footer(width, 532, "Source: 2026-07-08 50-case saved summaries and OpenAI/Codex quality judge."))
    lines.append("</svg>")
    write_svg(output_dir / "instruction-lift.svg", lines)


def render_empty_current_lift(repo_root: Path, output_dir: Path) -> None:
    rows = model_rows(repo_root)
    order = {"GPT": 0, "GLM": 1, "DeepSeek": 2, "DS thinking": 3, "Grok 4.3": 4, "Grok Build": 5}
    rows = sorted(rows, key=lambda row: order.get(row["short"], 99))
    width = 1120
    height = 650
    axis_x = 260
    axis_w = 520
    right_x = 794
    lines = svg_start(
        width,
        height,
        "50-case instruction lift across models",
        "Hard-gate and saved quality lift from empty bundle to current instructions.",
    )
    lines.append(text(40, 56, "Instruction lift across models", "title"))
    lines.append(text(40, 84, "50 cases. Hard-gate passes and saved quality improve for every tested current-vs-empty row.", "subtitle"))
    lines.extend(panel(40, 110, 1040, 430))
    lines.append(text(72, 144, "Model", "axis"))
    lines.append(text(axis_x, 144, "Hard-gate passes out of 50", "axis"))
    lines.append(text(right_x, 144, "Pass lift", "axis"))
    lines.append(text(994, 144, "Quality delta", "axis"))
    for tick in [0, 10, 20, 30, 40, 50]:
        x = axis_x + axis_w * pct(tick, 50)
        lines.append(line(x, 176, x, 506, "#e5e7eb"))
        lines.append(text(x, 166, tick, "axis", anchor="middle"))
    for index, row in enumerate(rows):
        y = 204 + index * 58
        if index % 2 == 0:
            lines.append(rect(64, y - 30, 990, 48, "#f8fafc", rx=0))
        empty_y = y - 14
        current_y = y + 4
        lines.append(text(72, y + 4, row["label"], "label"))
        lines.append(rect(axis_x, empty_y, axis_w, 11, "#eef2f7", rx=6))
        lines.append(rect(axis_x, empty_y, axis_w * pct(row["empty_passed"], 50), 11, "#94a3b8", rx=6))
        lines.append(rect(axis_x, current_y, axis_w, 13, "#eef2f7", rx=7))
        lines.append(rect(axis_x, current_y, axis_w * pct(row["current_passed"], 50), 13, row["color"], rx=7))
        lines.append(text(right_x, y - 8, f"empty {row['empty_passed']}/50", "small"))
        lines.append(text(right_x, y + 12, f"current {row['current_passed']}/50", "value"))
        lines.append(rect(892, y - 18, 56, 28, "#d1fae5", rx=14))
        lines.append(text(920, y + 1, f"+{row['pass_delta']}", "value", anchor="middle"))
        lines.append(text(994, y + 1, f"{row['quality_delta']:+.1f}", "value"))
    legend_y = 575
    lines.append(circle(78, legend_y, 7, "#94a3b8"))
    lines.append(text(94, legend_y + 4, "Empty bundle", "axis"))
    lines.append(circle(204, legend_y, 7, CURRENT))
    lines.append(text(220, legend_y + 4, "Current instructions", "axis"))
    lines.append(text(72, 610, "Quality delta is current score minus empty score from saved model-quality summaries.", "small"))
    lines.extend(footer(width, 632, "Source: 50-case current/empty summaries plus saved empty-vs-current quality aggregates."))
    lines.append("</svg>")
    write_svg(output_dir / "empty-current-lift.svg", lines)


def render_model_gap(repo_root: Path, output_dir: Path) -> None:
    rows = gpt_external_rows(repo_root)
    width = 1120
    height = 620
    axis_x = 292
    axis_w = 620
    lines = svg_start(
        width,
        height,
        "External model gap versus GPT on 50 cases",
        "OpenAI/Codex judge comparison of external saved current outputs against GPT current outputs.",
    )
    lines.append(text(40, 56, "External model gap versus GPT", "title"))
    lines.append(text(40, 84, "Delta is external-model score minus GPT score on current instructions; closer to zero is better.", "subtitle"))
    lines.extend(panel(40, 112, 1040, 400))
    lines.append(text(72, 148, "Model", "axis"))
    lines.append(text(axis_x, 148, "Average quality delta versus GPT", "axis"))
    lines.append(text(926, 148, "Quality split", "axis"))
    for tick in [-50, -40, -30, -20, -10, 0]:
        x = axis_x + axis_w * pct(tick + 50, 50)
        lines.append(line(x, 176, x, 444, "#e5e7eb"))
        lines.append(text(x, 166, tick, "axis", anchor="middle"))
    zero_x = axis_x + axis_w
    lines.append(line(zero_x, 170, zero_x, 456, "#94a3b8"))
    for index, row in enumerate(rows):
        y = 214 + index * 56
        if index % 2 == 0:
            lines.append(rect(64, y - 30, 990, 50, "#f8fafc", rx=0))
        lines.append(text(72, y - 3, row["label"], "label"))
        lines.append(text(72, y + 17, f"hard gates {row['hard_passed']}/50", "small"))
        delta = row["delta"]
        x = axis_x + axis_w * pct(delta + 50, 50)
        lines.append(rect(axis_x, y - 14, axis_w, 10, TRACK, rx=5))
        lines.append(rect(x, y - 20, max(zero_x - x, 0), 22, "#dbeafe", rx=4))
        lines.append(circle(x, y - 9, 8, row["color"]))
        lines.append(text(x, y - 28, f"{delta:+.1f}", "value", anchor="middle"))
        lines.append(text(926, y - 7, f"{row['wins']}/{row['ties']}/{row['gpt_wins']}", "value"))
        lines.append(text(926, y + 13, "external / tie / GPT", "small"))
    legend_y = 550
    lines.append(circle(78, legend_y, 7, CURRENT))
    lines.append(text(94, legend_y + 4, "external model", "axis"))
    lines.append(text(244, legend_y + 4, "Zero is parity with GPT; all current external rows remain below GPT on average.", "axis"))
    lines.extend(footer(width, 598, "Source: gpt-vs-external-current saved quality summary."))
    lines.append("</svg>")
    write_svg(output_dir / "model-gap.svg", lines)


def render_model_transfer(repo_root: Path, output_dir: Path) -> None:
    rows = model_rows(repo_root)
    width = 1280
    height = 610
    axis_x = 292
    axis_w = 760
    lines = svg_start(
        width,
        height,
        "50-case hard-gate transfer",
        "Hard-gate passes out of 50 for empty and current instruction bundles.",
    )
    lines.append(text(40, 56, "Hard-gate passes by model and instruction bundle", "title"))
    lines.append(text(40, 84, "Dot positions show passed eval cases out of 50. This chart is current-vs-empty, not reference-prompt coverage.", "subtitle"))
    lines.extend(panel(40, 118, 1200, 360))
    for tick in [0, 10, 20, 30, 40, 50]:
        x = axis_x + axis_w * pct(tick, 50)
        lines.append(line(x, 156, x, 430, "#e5e7eb"))
        lines.append(text(x, 146, tick, "axis", anchor="middle"))
    lines.append(line(axis_x, 156, axis_x + axis_w, 156, "#94a3b8"))
    for index, row in enumerate(rows):
        y = 192 + index * 43
        if index % 2 == 0:
            lines.append(rect(64, y - 22, 1140, 38, "#f8fafc", rx=0))
        lines.append(text(72, y + 5, row["label"], "label"))
        empty_x = axis_x + axis_w * pct(row["empty_passed"], 50)
        current_x = axis_x + axis_w * pct(row["current_passed"], 50)
        lines.append(line(empty_x, y, current_x, y, "#94a3b8"))
        lines.append(circle(empty_x, y, 7, "#94a3b8"))
        lines.append(circle(current_x, y, 8, row["color"]))
        lines.append(text(empty_x, y + 24, row["empty_passed"], "axis", anchor="middle"))
        lines.append(text(current_x, y - 14, row["current_passed"], "value", anchor="middle"))
        lines.append(text(1080, y + 5, f"{row['quality_current_wins']}/{row['quality_ties']}/{row['quality_empty_wins']} quality", "small"))
    legend_y = 516
    lines.append(circle(78, legend_y, 7, "#94a3b8"))
    lines.append(text(94, legend_y + 4, "empty", "axis"))
    lines.append(circle(170, legend_y, 7, CURRENT))
    lines.append(text(186, legend_y + 4, "current", "axis"))
    lines.append(text(330, legend_y + 4, "Right-side text is current/tie/empty quality split.", "axis"))
    lines.extend(footer(width, 588, "Source: 50-case current/empty summaries and saved empty-vs-current quality reports."))
    lines.append("</svg>")
    write_svg(output_dir / "model-transfer.svg", lines)


def render_reference_prompts(repo_root: Path, output_dir: Path) -> None:
    rows = reference_rows(repo_root)
    width = 1280
    height = 690
    lines = svg_start(
        width,
        height,
        "Current instructions versus reference bundles",
        "OpenHands and Claude/Fable baselines compared with all saved current runners on 50 cases.",
    )
    lines.append(text(40, 56, "Current vs reference instruction bundles", "title"))
    lines.append(text(40, 84, "Rows are saved comparisons: current runner vs reference bundle. Positive delta favors current.", "subtitle"))
    lines.extend(panel(40, 112, 1200, 470))
    lines.append(text(72, 150, "Reference", "axis"))
    lines.append(text(190, 150, "Runner", "axis"))
    lines.append(text(386, 150, "Hard gates", "axis"))
    lines.append(text(570, 150, "Current / tie / reference / inconclusive", "axis"))
    lines.append(text(1060, 150, "Avg delta", "axis", anchor="middle"))
    for index, row in enumerate(rows):
        y = 182 + index * 31
        if index % 2 == 0:
            lines.append(rect(64, y - 18, 1140, 28, "#f8fafc", rx=0))
        lines.append(text(72, y + 1, row["reference"], "small"))
        lines.append(text(190, y + 1, row["model"], "label"))
        lines.append(text(386, y + 1, f"{row['current_passed']}/50 vs {row['reference_passed']}/50", "value"))
        draw_segments(
            lines,
            570,
            y - 14,
            320,
            18,
            row["total"],
            [(row["current_wins"], CURRENT), (row["ties"], TIE), (row["reference_wins"], BASELINE), (row["inconclusive"], INCONCLUSIVE)],
        )
        lines.append(text(906, y + 1, f"{row['current_wins']}/{row['ties']}/{row['reference_wins']}/{row['inconclusive']}", "value"))
        lines.append(text(1060, y + 1, f"{row['delta']:+.1f}", "value", anchor="middle"))
    lines.append(text(72, 624, "Grok Build rows include observed adapter/provider agent failures from the saved run; they are not smoothed.", "label"))
    lines.extend(footer(width, 666, "Source: all-model OpenHands/Fable 50-case saved-quality summaries."))
    lines.append("</svg>")
    write_svg(output_dir / "reference-prompts.svg", lines)


def comparison_record_sides(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline = item["baseline"]
    current = item.get("candidate") or item.get("current")
    if current is None:
        raise ValueError(f"comparison item has no candidate/current side: {item.get('case_id')}")
    return baseline, current


def pass_pass_counts(pair_path: Path) -> dict[str, Any]:
    data = read_json(pair_path)
    counts = {"current": 0, "baseline": 0, "tie": 0, "inconclusive": 0}
    total = 0
    deltas: list[float] = []
    for item in data["comparisons"]:
        baseline, current = comparison_record_sides(item)
        if not (baseline["passed"] and current["passed"]):
            continue
        total += 1
        quality = item["quality"]
        winner = quality.get("winner", "inconclusive")
        counts[winner if winner in counts else "inconclusive"] += 1
        if isinstance(quality.get("delta"), (int, float)):
            deltas.append(float(quality["delta"]))
    return {"total": total, "counts": counts, "avg_delta": round(sum(deltas) / len(deltas), 1) if deltas else 0.0}


def render_quality_only_comparisons(repo_root: Path, output_dir: Path) -> None:
    lift_rows = [{"label": row["short"], **pass_pass_counts(row["pair_path"])} for row in model_rows(repo_root)]
    gap_rows = [{"label": row["label"], **pass_pass_counts(row["pair_path"])} for row in gpt_external_rows(repo_root)]
    ref_rows = [{"label": row["short"], **pass_pass_counts(row["pair_path"])} for row in reference_rows(repo_root)]
    width = 1360
    height = 720
    lines = svg_start(
        width,
        height,
        "Quality-only comparisons after hard gates pass",
        "Only cases where both sides passed deterministic hard gates are included.",
    )
    lines.append(text(40, 56, "Quality-only small multiples", "title"))
    lines.append(text(40, 84, "Hard failures are excluded. Triplets are left wins / ties / right wins, with n=pass/pass overlap.", "subtitle"))
    panels = [
        (40, "Current vs empty", lift_rows, "current / tie / empty"),
        (460, "External model vs GPT", gap_rows, "external / tie / GPT"),
        (880, "Current vs references", ref_rows, "current / tie / reference"),
    ]
    for x, title, rows, legend in panels:
        lines.extend(panel(x, 116, 390, 450))
        lines.append(text(x + 32, 152, title, "label"))
        for index, row in enumerate(rows):
            counts = row["counts"]
            y = 188 + index * (54 if len(rows) <= 5 else 30)
            lines.append(text(x + 32, y + 14, row["label"], "label"))
            draw_segments(lines, x + 150, y, 132, 18, max(row["total"], 1), [(counts["current"], CURRENT), (counts["tie"], TIE), (counts["baseline"], BASELINE)])
            lines.append(text(x + 296, y + 14, f"{counts['current']}/{counts['tie']}/{counts['baseline']}", "value"))
            if len(rows) <= 8:
                lines.append(text(x + 150, y + 40, f"n={row['total']}, avg {row['avg_delta']:+.1f}", "small"))
            else:
                lines.append(text(x + 150, y + 30, f"n={row['total']}, avg {row['avg_delta']:+.1f}", "small"))
        lines.append(text(x + 32, 530, legend, "axis"))
    lines.append(text(72, 625, "Use this chart for quality-only reads; hard-gate misses are shown in the other charts and still matter.", "label"))
    lines.extend(footer(width, 692, "Source: saved quality reports filtered to both sides passed."))
    lines.append("</svg>")
    write_svg(output_dir / "quality-only-comparisons.svg", lines)


def winner_fill(winner: str) -> str:
    if winner == "current":
        return CURRENT_FILL
    if winner == "baseline":
        return BASELINE_FILL
    if winner == "tie":
        return TIE_FILL
    return INCONCLUSIVE_FILL


def delta_text(entry: dict[str, Any]) -> str:
    delta = entry.get("delta")
    if isinstance(delta, (int, float)):
        rounded = round(delta)
        return "0" if rounded == 0 else f"{rounded:+d}"
    return "I"


def pair_delta_map(pair_path: Path, *, passed_only: bool = True) -> dict[str, dict[str, Any]]:
    data = read_json(pair_path)
    values = {}
    for item in data["comparisons"]:
        baseline, current = comparison_record_sides(item)
        if passed_only and not (baseline["passed"] and current["passed"]):
            continue
        quality = item["quality"]
        delta = quality.get("delta")
        values[item["case_id"]] = {
            "winner": quality.get("winner", "inconclusive"),
            "delta": delta if isinstance(delta, (int, float)) else None,
        }
    return values


def reference_case_columns(repo_root: Path) -> list[dict[str, Any]]:
    return [{"label": row["short"], "values": pair_delta_map(row["pair_path"])} for row in reference_rows(repo_root)]


def case_detail_columns(repo_root: Path) -> list[dict[str, Any]]:
    rows = []
    gpt = next(row for row in model_rows(repo_root) if row["short"] == "GPT")
    rows.append({"label": "GPT/E", "values": pair_delta_map(gpt["pair_path"])})
    for row in gpt_external_rows(repo_root):
        rows.append({"label": compact_model_label(row["label"]), "values": pair_delta_map(row["pair_path"])})
    for row in reference_rows(repo_root):
        rows.append({"label": row["short"], "values": pair_delta_map(row["pair_path"])})
    return rows


def select_case_ids(columns: list[dict[str, Any]], limit: int) -> list[str]:
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

    return sorted(case_ids, key=lambda case_id: (-metrics(case_id)[0], -metrics(case_id)[3], case_id))[:limit]


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


def render_case_detail_comparisons(repo_root: Path, output_dir: Path) -> None:
    columns = case_detail_columns(repo_root)
    case_ids = select_case_ids(columns, 18)
    width = 1900
    row_height = 30
    height = 280 + len(case_ids) * row_height + 76
    lines = svg_start(
        width,
        height,
        "Case-level quality deltas",
        "Signed pass/pass judge score deltas for high-signal 50-case eval rows.",
    )
    lines.append(text(40, 56, "Case-level quality deltas", "title"))
    lines.append(text(40, 84, "Each cell is left-side score minus baseline score after both hard gates pass; blanks are excluded, not zero.", "subtitle"))
    lines.extend(panel(40, 116, 1820, height - 184))
    table_x = 72
    case_width = 430
    cell_width = 76
    header_y = 154
    lines.append(text(table_x, header_y, "Case", "axis"))
    for index, column in enumerate(columns):
        x = table_x + case_width + index * cell_width + cell_width / 2
        summary = column_delta_summary(column)
        lines.append(text(x, header_y, column["label"], "axis", anchor="middle"))
        lines.append(text(x, header_y + 16, f"+{summary['positive']} -{summary['negative']}", "axis", anchor="middle"))
        lines.append(text(x, header_y + 31, f"avg {summary['average']:+.1f}", "axis", anchor="middle"))
    for row_index, case_id in enumerate(case_ids):
        y = 216 + row_index * row_height
        if row_index % 2 == 0:
            lines.append(rect(table_x - 8, y - 18, 1740, row_height, "#f8fafc", rx=0))
        lines.append(text(table_x, y, case_id, "small"))
        for col_index, column in enumerate(columns):
            x = table_x + case_width + col_index * cell_width + 8
            entry = column["values"].get(case_id)
            if entry is None:
                lines.append(rect(x, y - 18, cell_width - 16, 21, "#ffffff", rx=5, stroke="#f1f5f9"))
                continue
            lines.append(rect(x, y - 18, cell_width - 16, 21, winner_fill(entry.get("winner", "inconclusive")), rx=5, stroke="#e5e7eb"))
            lines.append(text(x + (cell_width - 16) / 2, y - 3, delta_text(entry), "cell", anchor="middle"))
    legend_y = height - 76
    for x, label, color in [(72, "+ left side", CURRENT_FILL), (210, "- baseline", BASELINE_FILL), (340, "0 tie", TIE_FILL), (426, "blank no pass/pass", "#ffffff")]:
        lines.append(rect(x, legend_y - 14, 18, 18, color, rx=4, stroke="#e5e7eb"))
        lines.append(text(x + 26, legend_y, label, "axis"))
    lines.extend(footer(width, height - 32, "Source: selected 50-case saved quality pair reports."))
    lines.append("</svg>")
    write_svg(output_dir / "case-detail-comparisons.svg", lines)


def render_quality_only_case_matrix(repo_root: Path, output_dir: Path) -> None:
    columns = reference_case_columns(repo_root)
    case_ids = select_case_ids(columns, 24)
    width = 1640
    row_height = 28
    height = 230 + len(case_ids) * row_height + 100
    lines = svg_start(
        width,
        height,
        "All-model current versus reference case matrix",
        "Pass/pass judge score deltas for current runners versus OpenHands and Claude/Fable.",
    )
    lines.append(text(40, 56, "All-model reference quality delta matrix", "title"))
    lines.append(text(40, 84, "Each cell is current score minus reference score after both hard gates pass. + favors current, - favors reference.", "subtitle"))
    lines.extend(panel(40, 116, 1560, height - 190))
    table_x = 72
    case_width = 470
    cell_width = 84
    header_y = 154
    lines.append(text(table_x, header_y, "Case", "axis"))
    for index, column in enumerate(columns):
        x = table_x + case_width + index * cell_width + cell_width / 2
        lines.append(text(x, header_y, column["label"], "axis", anchor="middle"))
    for row_index, case_id in enumerate(case_ids):
        y = 194 + row_index * row_height
        if row_index % 2 == 0:
            lines.append(rect(table_x - 8, y - 17, 1480, row_height, "#f8fafc", rx=0))
        lines.append(text(table_x, y, case_id, "small"))
        for col_index, column in enumerate(columns):
            x = table_x + case_width + col_index * cell_width + 8
            entry = column["values"].get(case_id)
            if entry is None:
                lines.append(rect(x, y - 17, cell_width - 16, 20, "#ffffff", rx=5, stroke="#f1f5f9"))
                continue
            lines.append(rect(x, y - 17, cell_width - 16, 20, winner_fill(entry.get("winner", "inconclusive")), rx=5, stroke="#e5e7eb"))
            lines.append(text(x + (cell_width - 16) / 2, y - 3, delta_text(entry), "cell", anchor="middle"))
    legend_y = height - 72
    for x, label, color in [(72, "+ current", CURRENT_FILL), (184, "- reference", BASELINE_FILL), (320, "0 tie", TIE_FILL), (396, "blank no pass/pass", "#ffffff")]:
        lines.append(rect(x, legend_y - 14, 18, 18, color, rx=4, stroke="#e5e7eb"))
        lines.append(text(x + 26, legend_y, label, "axis"))
    lines.extend(footer(width, height - 34, "Source: all-model OpenHands/Fable 50-case quality reports."))
    lines.append("</svg>")
    write_svg(output_dir / "quality-only-case-matrix.svg", lines)


def render_coverage_watchlist(repo_root: Path, output_dir: Path) -> None:
    current_by_model = []
    for row in model_rows(repo_root):
        current_by_model.append((row["short"], {item["case_id"]: item for item in row["results"]}))
    case_ids = list(next(iter(current_by_model))[1])
    rows = []
    for case_id in case_ids:
        passers = [short for short, result_map in current_by_model if result_map[case_id]["passed"]]
        rows.append({"case": case_id, "passed": len(passers), "passers": passers})
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
    lines.append(text(40, 84, "The weakest 50-case rows are where model transfer is still limited, even with current instructions.", "subtitle"))
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
    lines.append(text(72, 650, "Use this as the concrete backlog; it is not a request to add always-on instruction text.", "label"))
    lines.extend(footer(width, 676, "Source: current summaries across GPT, GLM, Grok, Grok Build, DeepSeek, and DeepSeek thinking."))
    lines.append("</svg>")
    write_svg(output_dir / "coverage-watchlist.svg", lines)


def build_all(repo_root: Path, output_dir: Path, social_image: Path = DEFAULT_SOCIAL_IMAGE) -> None:
    output_dir = resolve_path(repo_root, output_dir)
    social_image = resolve_path(repo_root, social_image)
    render_hard_gates_50(repo_root, output_dir)
    render_instruction_lift(repo_root, output_dir)
    render_empty_current_lift(repo_root, output_dir)
    render_model_gap(repo_root, output_dir)
    render_model_transfer(repo_root, output_dir)
    render_reference_prompts(repo_root, output_dir)
    render_quality_only_comparisons(repo_root, output_dir)
    render_case_detail_comparisons(repo_root, output_dir)
    render_quality_only_case_matrix(repo_root, output_dir)
    render_coverage_watchlist(repo_root, output_dir)
    render_social_card_png(repo_root, social_image)


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


def compare_file(expected_path: Path, output_path: Path) -> list[str]:
    if not output_path.exists():
        return [f"missing: {output_path}"]
    if expected_path.read_bytes() != output_path.read_bytes():
        return [f"stale: {output_path}"]
    return []


def check_all(repo_root: Path, output_dir: Path, social_image: Path = DEFAULT_SOCIAL_IMAGE) -> list[str]:
    output_dir = resolve_path(repo_root, output_dir)
    social_image = resolve_path(repo_root, social_image)
    with tempfile.TemporaryDirectory(prefix="readme-infographics-check-") as tmp:
        expected_dir = Path(tmp) / "readme"
        expected_social = Path(tmp) / "social" / social_image.name
        build_all(repo_root, expected_dir, expected_social)
        problems = compare_svg_dirs(expected_dir, output_dir)
        problems.extend(compare_file(expected_social, social_image))
        return problems


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for generated README SVGs.")
    parser.add_argument("--social-image", default=str(DEFAULT_SOCIAL_IMAGE), help="Generated social-card PNG path.")
    parser.add_argument("--check", action="store_true", help="Verify generated README SVGs and social PNG are fresh without updating them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    output_dir = Path(args.output_dir)
    social_image = Path(args.social_image)
    if args.check:
        problems = check_all(repo_root, output_dir, social_image)
        if problems:
            print("README infographics are not fresh:", file=sys.stderr)
            for problem in problems:
                print(f"- {problem}", file=sys.stderr)
            print("Regenerate with the same arguments without --check.", file=sys.stderr)
            return 1
        print(f"readme infographics fresh: {output_dir}; social image fresh: {social_image}")
        return 0

    build_all(repo_root, output_dir, social_image)
    print(f"wrote {output_dir} and {social_image}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
