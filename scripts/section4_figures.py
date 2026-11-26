"""Draw the November 26 GPT-6.2 figures from the public tables in evals/RESULTS.md."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

from infographic_svg import circle, line, rect, svg_start, text, write_svg


DIRECTORY = "section4-read-record"
CARD = "overview.png"
MODELS = ("GPT-6.2 Sol", "GPT-6.2 Astra")
CONDITIONS = ("Original", "Updated")
STOP_CONDITIONS = ("Prior default", "Stop rule")
PANELS = {
    "50 cases, deterministic gate": ("Formal gate", "core", "objective"),
    "50 cases, adjudicated task outcome": ("Adjudicated outcome", "core", "semantic"),
    "File tasks, mutation and executable checks": ("File tasks", "lift", "objective"),
    "Canary variants, repository oracle": ("Canary oracle", "canary", "objective"),
    "Direct request, quotation and delegated criteria, exact file state": ("Authority controls", "authority", "objective"),
}
INK, MUTED, GRID = "#162838", "#475d6e", "#d4dfe5"
TEAL, AMBER, PURPLE, LOSS = "#176e65", "#efb665", "#73598d", "#ac4141"


class Reads(NamedTuple):
    correct: tuple[int, int]
    required: tuple[int, int]
    extra: int
    invalid: int
    calls: int
    tokens: int


class StopArm(NamedTuple):
    correct: tuple[int, int]
    required: tuple[int, int]
    requests: int
    extra: int
    cached_input: int
    uncached_input: int
    output: int

    @property
    def tokens(self) -> int:
        return self.cached_input + self.uncached_input + self.output


class Score(NamedTuple):
    previous: int
    updated: int
    total: int

    @property
    def delta(self) -> int:
        return self.updated - self.previous


def add_counts(*pairs: tuple[int, int]) -> tuple[int, int]:
    return sum(n for n, _ in pairs), sum(total for _, total in pairs)


class Study(NamedTuple):
    reads: dict[tuple[str, str], Reads]
    panels: dict[str, tuple[Score, Score]]
    stopping: dict[tuple[str, str], StopArm]

    def combined(self, condition: str) -> Reads:
        sol, astra = (self.reads[model, condition] for model in MODELS)
        return Reads(
            add_counts(sol.correct, astra.correct), add_counts(sol.required, astra.required),
            sol.extra + astra.extra, sol.invalid + astra.invalid, sol.calls + astra.calls, sol.tokens + astra.tokens,
        )


def first_table(section: str, heading: str) -> list[dict[str, str]]:
    """Read the first pipe table under this unique heading in the dated results section."""
    marker = f"\n### {heading}\n"
    if section.count(marker) != 1:
        raise ValueError(f"missing or duplicate results heading: {heading}")
    rows = []
    for source_line in section.split(marker, 1)[1].splitlines():
        if source_line.startswith("#"):
            break
        if source_line.startswith("|"):
            rows.append([cell.strip() for cell in source_line.strip().strip("|").split("|")])
        elif rows:
            break
    if len(rows) < 3:
        raise ValueError(f"missing results table: {heading}")
    return [dict(zip(rows[0], row, strict=True)) for row in rows[2:]]


def fraction(value: str) -> tuple[int, int]:
    count, total = map(int, value.split("/"))
    if not 0 <= count <= total or total == 0:
        raise ValueError(f"invalid pass count: {value}")
    return count, total


def score(value: str) -> Score:
    before, after = map(fraction, value.split("→"))
    if before[1] != after[1]:
        raise ValueError(f"unmatched denominators: {value}")
    return Score(before[0], after[0], before[1])


def stopping_arms(section: str) -> dict[tuple[str, str], StopArm]:
    arms = {}
    for row in first_table(section, "Stopping after an unavailable check"):
        key = (row["Model"], row["Description"])
        cached, uncached, output, total = (
            int(row[col].replace(",", "")) for col in ("Cached input", "Uncached input", "Output", "Total tokens")
        )
        arm = StopArm(fraction(row["Correct decisions"]), fraction(row["Required reads"]),
                      int(row["Model requests"]), int(row["Extra reads"]), cached, uncached, output)
        if (key in arms or arm.requests < arm.correct[1] or min(cached, uncached, output, arm.extra) < 0
                or total <= 0 or arm.tokens != total):
            raise ValueError(f"inconsistent stopping-rule row: {key}")
        arms[key] = arm
    if set(arms) != {(m, c) for m in MODELS for c in STOP_CONDITIONS}:
        raise ValueError("incomplete stopping-rule comparison")
    if len({(a.correct[1], a.required[1]) for a in arms.values()}) != 1:
        raise ValueError("unmatched stopping-rule sessions or required reads")
    return arms


def load_study(repo_root: Path) -> Study:
    report = (repo_root / "evals/RESULTS.md").read_text(encoding="utf-8")
    heading = "\n## 2026-11-26 — Section 4 and read_record on GPT-6.2\n"
    if report.count(heading) != 1:
        raise ValueError("missing or duplicate November 26 results section")
    section = report.split(heading, 1)[1].split("\n## ", 1)[0]
    reads = {}
    for r in first_table(section, "Selecting evidence with read_record"):
        key = (r["Model"], r["Description"])
        arm = Reads(
            fraction(r["Correct decisions"]), fraction(r["Required reads"]), int(r["Extra successful reads"]),
            int(r["Invalid requests"]), int(r["Total calls"]), int(r["Input + output tokens"].replace(",", "")),
        )
        if (key in reads or min(arm.extra, arm.invalid, arm.calls) < 0 or arm.tokens <= 0
                or arm.required[0] + arm.extra + arm.invalid != arm.calls):
            raise ValueError(f"inconsistent or duplicate read_record row: {key}")
        reads[key] = arm
    if set(reads) != {(m, c) for m in MODELS for c in CONDITIONS}:
        raise ValueError("incomplete read_record comparison")
    if len({arm.correct[1] for arm in reads.values()}) != 1 or any(
        reads[model, "Original"].required[1] != reads[model, "Updated"].required[1] for model in MODELS
    ):
        raise ValueError("unmatched acceptance cases or required reads")
    panels = {}
    for r in first_table(section, "Section 4 regression panels"):
        label, _, _ = PANELS[r["Panel"]]
        sol, astra = score(r["Sol previous → updated"]), score(r["Astra previous → updated"])
        if label in panels or sol.total != astra.total:
            raise ValueError(f"inconsistent or duplicate regression row: {label}")
        panels[label] = (sol, astra)
    if len(panels) != len(PANELS):
        raise ValueError("incomplete Section 4 comparison")
    return Study(reads, panels, stopping_arms(section))


def verify_archive(study: Study, archive: Path) -> None:
    def load(relative_path: str):
        return json.loads((archive / relative_path).read_text(encoding="utf-8"))

    cases = load("primary-final/cases.json")
    needed = sum(sum(case["required"].values()) for case in cases)
    groups = load("primary-final/summary.json")["groups"]
    for model in MODELS:
        slug = model.lower().replace(" ", "-")
        for condition, arm in zip(CONDITIONS, ("old", "new")):
            r = groups[slug][arm]
            observed = Reads((r["correct"], len(cases)), (needed - r["required_reads_missing"], needed),
                             r["unnecessary_reads"], r["invalid_reads"], r["calls"], r["input_tokens"] + r["output_tokens"])
            if observed != study.reads[model, condition]:
                raise ValueError(f"read_record table differs from the archive for {model}, {condition}")
    regression = load("regression/verified-main.json")["groups"]
    for label, suite, measure in PANELS.values():
        group = regression[suite]
        pairs = group["semantic_pairs" if measure == "semantic" else "pairs"]
        for model, published in zip(MODELS, study.panels[label]):
            r = group[measure][model.lower().replace(" ", "-")]
            if (published.previous, published.updated, published.total * len(MODELS)) != (r["old"], r["new"], pairs):
                raise ValueError(f"Section 4 table differs from the archive for {label}, {model}")


def verify_stopping_archive(study: Study, archive: Path) -> None:
    totals = json.loads((archive / "metrics.json").read_text(encoding="utf-8"))["by_model"]
    for model in MODELS:
        for condition, key in zip(STOP_CONDITIONS, ("current", "stop")):
            row = totals[model.lower().replace(" ", "-")][key]
            required = row["fixture_reads"] - row["extra_reads"] - row["invalid_attempts"]
            observed = StopArm((row["supported"], row["sessions"]), (required, required + row["missing_reads"]),
                               row["model_requests"], row["extra_reads"], row["cachedInputTokens"],
                               row["uncachedInputTokens"], row["outputTokens"])
            if observed != study.stopping[model, condition]:
                raise ValueError(f"stopping-rule table differs from the archive for {model}, {condition}")


def canvas(height: int, title: str, description: str) -> list[str]:
    return [
        *svg_start(960, height, title, description),
        rect(12, 12, 936, height - 24, "#ffffff", rx=12, stroke=GRID),
        '<style>.num{font-size:18px;font-weight:700;fill:#162838}.key{font-size:15px;fill:#475d6e}'
        '.light{font-size:15px;font-weight:700;fill:white}.dark{font-size:15px;font-weight:700;fill:#162838}'
        '.model{font-size:19px;font-weight:700;fill:#162838}</style>',
    ]


def counts(pair: tuple[int, int]) -> str:
    return f"{pair[0]}/{pair[1]}"


def render_reads(study: Study, path: Path) -> None:
    original, updated = map(study.combined, CONDITIONS)
    title = f"Extra successful reads fell from {original.extra} to {updated.extra}" if updated.extra < original.extra else "Extra successful reads by tool description"
    detail = ". ".join(
        f"{model} extra reads changed from {study.reads[model, 'Original'].extra} to {study.reads[model, 'Updated'].extra}"
        for model in MODELS
    )
    lines = canvas(444, title, f"{detail}. Stacked bars also show required reads and invalid requests.")
    cases = study.reads[MODELS[0], "Original"].correct[1]
    lines += [text(40, 61, title, "title"),
              text(40, 89, f"read_record  ·  GPT-6.2 medium  ·  {cases} acceptance cases per model  ·  Same Section 4 in both conditions", "key")]
    for x, color, label in [(220, TEAL, "Required"), (362, AMBER, "Extra successful"), (571, PURPLE, "Invalid request")]:
        lines += [rect(x, 111, 15, 15, color, rx=3), text(x + 23, 124, label, "key")]
    lines += [text(40, 153, "Model", "key"), text(125, 153, "Description", "key"),
              text(220, 153, "Tool calls", "key"), text(911, 153, "Total", "key", "end")]
    axis_x, axis_width = 220, 605
    step = max(1, (max(r.calls for r in study.reads.values()) + 4) // 5)
    unit = axis_width / (step * 5)
    for i in range(6):
        x = axis_x + i * step * unit
        lines += [line(x, 164, x, 321, GRID), text(x, 343, i * step, "key", "middle")]
    for index, model in enumerate(MODELS):
        start = 185 + 89 * index
        lines.append(text(40, start + 20, model.split()[-1], "model"))
        for offset, condition in enumerate(CONDITIONS):
            y = start + offset * 34
            row = study.reads[model, condition]
            lines += [text(125, y + 5, condition, "key"), text(911, y + 6, row.calls, "num", "end")]
            x = axis_x
            for value, color, style in [(row.required[0], TEAL, "light"), (row.extra, AMBER, "dark"), (row.invalid, PURPLE, "light")]:
                if value:
                    width = unit * value
                    lines += [rect(x, y - 12, width, 24, color, rx=0), text(x + width / 2, y + 5, value, style, "middle")]
                    x += width
    decisions = add_counts(original.correct, updated.correct)
    token_delta = (updated.tokens / original.tokens - 1) * 100
    lines += [line(40, 360, 920, 360, GRID),
              text(40, 387, f"{counts(decisions)} correct decisions. Required reads completed   {counts(original.required)} original, {counts(updated.required)} updated.", "dark"),
              text(40, 414, f"Input + output tokens   {original.tokens:,} → {updated.tokens:,}  ({token_delta:+.1f}%, cached input included once).", "key"), "</svg>"]
    write_svg(path, lines)


def render_stopping(study: Study, path: Path) -> None:
    rows = study.stopping
    description = ". ".join(
        f"{model}: {rows[model, 'Prior default'].requests} to {rows[model, 'Stop rule'].requests} model requests, "
        f"{rows[model, 'Prior default'].extra} to {rows[model, 'Stop rule'].extra} extra reads"
        for model in MODELS
    )
    title = "Stopping after an unavailable check"
    lines = canvas(415, title, description)
    sessions = rows[MODELS[0], STOP_CONDITIONS[0]].correct[1]
    lines += [text(40, 61, title, "title"),
              text(40, 89, f"GPT-6.2 medium  ·  Nine acceptance cases  ·  {sessions} sessions per model and description", "key"),
              text(40, 135, "Model", "key"), text(114, 135, "Description", "key"),
              text(250, 135, "Model requests", "model"), text(615, 135, "Extra record reads", "model")]
    max_requests = max(r.requests for r in rows.values())
    max_extra = max(1, max(r.extra for r in rows.values()))
    for index, model in enumerate(MODELS):
        y0 = 175 + 94 * index
        lines.append(text(40, y0 + 17, model.split()[-1], "model"))
        for i, (condition, color) in enumerate(zip(STOP_CONDITIONS, (MUTED, TEAL))):
            row = rows[model, condition]
            y = y0 + i * 31
            lines.append(text(114, y + 5, condition, "key"))
            for x, value, maximum, width in ((250, row.requests, max_requests, 272), (615, row.extra, max_extra, 240)):
                end = x + width * value / maximum
                if value:
                    lines.append(rect(x, y - 9, end - x, 18, color, rx=3))
                lines.append(text(end + 9, y + 5, value, "dark"))
    lines.append(line(40, 331, 920, 331, GRID))
    for i, model in enumerate(MODELS):
        prior, stop = (rows[model, c] for c in STOP_CONDITIONS)
        x = 40 + i * 454
        lines += [text(x, 358, f"{model.split()[-1]}  ·  Input + output tokens", "key"),
                  text(x, 387, f"{prior.tokens:,} → {stop.tokens:,}  ({(stop.tokens / prior.tokens - 1) * 100:+.1f}%)", "model")]
    write_svg(path, lines + ["</svg>"])


def render_regression(study: Study, path: Path) -> None:
    descriptions = [
        f"{model} passed {gate.previous} then {gate.updated} formal gates and {outcome.previous} then {outcome.updated} adjudicated tasks out of {gate.total}"
        for model, gate, outcome in zip(MODELS, study.panels["Formal gate"], study.panels["Adjudicated outcome"])
    ]
    lines = canvas(453, "Section 4 regression results", ". ".join(descriptions) + ". Bars show signed changes in passed cases.")
    lines += [text(40, 61, "Section 4 regression results", "title"),
              text(40, 89, "GPT-6.2 medium  ·  Previous and updated instructions  ·  One scored run per case, model and condition", "key"),
              text(40, 151, "Panel", "key")]
    columns = (321, 623)
    for model, x in zip(MODELS, columns):
        lines += [text(x, 128, model, "model"), text(x, 152, "Previous → updated", "key"),
                  text(x + 205, 152, "Δ passes", "key", "middle")]
    greatest = max(1, max(abs(s.delta) for scores in study.panels.values() for s in scores))
    for i, (label, scores) in enumerate(study.panels.items()):
        y = 185 + i * 45
        if i % 2 == 0:
            lines.append(rect(28, y - 19, 904, 38, "#f3f7f8", rx=3))
        lines.append(text(40, y + 5, label, "dark"))
        for x, s in zip(columns, scores):
            center = x + 205
            lines += [text(x, y + 5, f"{s.previous}/{s.total} → {s.updated}/{s.total}", "dark"),
                      line(center, y - 15, center, y + 15, "#94a6b1")]
            end = center + 58 * s.delta / greatest
            if s.delta:
                lines += [rect(min(center, end), y - 6, abs(end - center), 12, TEAL if s.delta > 0 else LOSS, rx=2),
                          text(end + (6 if s.delta > 0 else -6), y + 5, f"{s.delta:+d}", "key", "start" if s.delta > 0 else "end")]
            else:
                lines += [circle(center, y, 4, MUTED, stroke=MUTED, stroke_width=0), text(center + 10, y + 5, "0", "key")]
    lines += [line(40, 399, 920, 399, GRID),
              text(40, 426, "Bars show the change in passed cases. Targeted repeats and the explicit retention-key control are reported separately.", "key"),
              "</svg>"]
    write_svg(path, lines)


def render_card(study: Study, path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

    image = Image.new("RGB", (1200, 630), "#ffffff")
    draw = ImageDraw.Draw(image)
    # Pillow bundles this font. Use it for the share image even when host fonts differ.
    fonts = {size: ImageFont.load_default(size=size) for size in (16, 19, 21, 24, 28, 42, 64)}

    def label(x, y, value, size, *, color=INK, bold=False, anchor="la"):
        draw.text((x, y), str(value), font=fonts[size], fill=color, anchor=anchor,
                  stroke_width=int(bold), stroke_fill=color)

    label(48, 37, "GPT-6.2 evaluation results", 42, bold=True)
    label(1152, 50, "26 NOV 2026", 19, color=MUTED, anchor="ra")
    label(49, 101, "Paired tests on Sol and Astra at medium reasoning effort", 21, color=MUTED)
    draw.line((48, 153, 1152, 153), fill=GRID, width=2)
    draw.line((566, 183, 566, 531), fill=GRID, width=2)
    label(48, 181, "read_record stopping rule", 28, bold=True)
    prior, stop = ([study.stopping[m, condition] for m in MODELS] for condition in STOP_CONDITIONS)
    label(48, 226, f"Extra reads across {prior[0].correct[1]} sessions per model and version", 19, color=MUTED)
    label(48, 263, sum(r.extra for r in prior), 64, bold=True)
    draw.line((159, 306, 207, 306), fill=MUTED, width=3)
    draw.line([(194, 295), (207, 306), (194, 317)], fill=MUTED, width=3)
    label(228, 263, sum(r.extra for r in stop), 64, color=TEAL, bold=True)
    label(49, 352, "Prior default", 19, color=MUTED)
    label(228, 352, "Stop rule", 19, color=MUTED)
    for i, (model, a, b) in enumerate(zip(MODELS, prior, stop)):
        label(49, 407 + 37 * i, model, 21)
        label(284, 407 + 37 * i, f"{a.extra} to {b.extra}", 21, color=TEAL, bold=True)
    label(49, 503, f"Model requests   {sum(r.requests for r in prior)} to {sum(r.requests for r in stop)}", 19, color=MUTED)
    label(602, 181, "Section 4 wording", 28, bold=True)
    label(602, 226, "Cases passed, previous to updated", 21, color=MUTED)
    label(911, 278, "Sol", 19, bold=True, anchor="ma")
    label(1089, 278, "Astra", 19, bold=True, anchor="ma")
    for i, (name, scores) in enumerate(study.panels.items()):
        y = 318 + 41 * i
        label(602, y, f"{name} ({scores[0].total})", 19)
        for x, s in zip((911, 1089), scores):
            color = MUTED
            if s.delta:
                color = TEAL if s.delta > 0 else LOSS
            label(x, y, f"{s.previous} to {s.updated}", 21, color=color, anchor="ma")
    draw.line((48, 550, 1152, 550), fill=GRID, width=2)
    decisions = add_counts(*(r.correct for r in prior + stop))
    required_before = counts(add_counts(*(r.required for r in prior)))
    required_after = counts(add_counts(*(r.required for r in stop)))
    label(48, 575, f"Main comparison   {counts(decisions)} correct decisions   ·   Required reads   {required_before} prior, {required_after} with stop rule", 19)
    info = PngImagePlugin.PngInfo()
    info.add_text("Title", "GPT-6.2 evaluation of read_record and Section 4")
    info.add_text("Source", "evals/RESULTS.md, 2026-11-26")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, pnginfo=info)


def build(repo_root: Path, output_dir: Path) -> None:
    study = load_study(repo_root)
    archive = repo_root / ".eval-results/2026-11-26-section4-read-record"
    if archive.is_dir():
        verify_archive(study, archive)
    stop_archive = repo_root / ".eval-results/2026-11-26-read-record-unavailable-full"
    if stop_archive.is_dir():
        verify_stopping_archive(study, stop_archive)
    render_reads(study, output_dir / "initial-selection.svg")
    render_stopping(study, output_dir / "record-reads.svg")
    render_regression(study, output_dir / "section4-regression.svg")
    render_card(study, output_dir / CARD)
