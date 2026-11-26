"""SVG primitives shared by the evaluation figures."""

from __future__ import annotations

import html
from pathlib import Path


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


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


def write_svg(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
