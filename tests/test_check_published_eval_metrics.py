import importlib.util
import io
import json
import os
import zlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_published_eval_metrics.py"


def load_script():
    spec = importlib.util.spec_from_file_location("check_published_eval_metrics", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def summary_fixture():
    return {
        "passed": 4,
        "failed": 0,
        "results": [
            {"case_id": "case-a", "label": "baseline-HEAD", "passed": True},
            {"case_id": "case-a", "label": "current", "passed": True},
            {"case_id": "case-b", "label": "baseline-HEAD", "passed": True},
            {"case_id": "case-b", "label": "current", "passed": True},
        ],
    }


def quality_fixture():
    return {
        "comparisons": [
            {"case_id": "case-a", "quality": {"winner": "current", "delta": 3}},
            {"case_id": "case-b", "quality": {"winner": "baseline", "delta": -1}},
        ]
    }


def snapshot_fixture(module):
    model_rows = [
        ("GPT-5.5", "GPT/Codex", 2, 1, 2, 28.4),
        ("GLM-5.2", "GLM-5.2", 2, 1, 2, 62.9),
        ("Grok 4.3", "Grok 4.3", 1, 0, 2, 56.4),
        ("Grok Build 0.1", "Grok Build 0.1", 1, 0, 2, 42.6),
        ("DeepSeek V4 Flash", "DeepSeek V4 Flash", 1, 0, 2, 52.9),
        ("DeepSeek V4 thinking", "DeepSeek V4 thinking", 1, 0, 2, 52.9),
    ]
    return module.SnapshotMetrics(
        case_count=2,
        model_rows=[
            {
                "label": label,
                "readme_label": readme_label,
                "current_passed": current,
                "empty_passed": empty,
                "total": total,
                "quality_delta": quality_delta,
                "current_wins": 1,
                "baseline_wins": 0,
                "ties": 1,
                "inconclusive": 0,
            }
            for label, readme_label, current, empty, total, quality_delta in model_rows
        ],
        external_rows=[],
        reference_rows=[
            {
                "label": "OpenHands `AGENTS.md`",
                "candidate_label": "GPT-5.5-current",
                "current_passed": 2,
                "reference_passed": 1,
                "total": 2,
                "current_wins": 1,
                "reference_wins": 0,
                "ties": 1,
                "inconclusive": 0,
                "delta": 27.2,
                "current_score": 95.9,
                "reference_score": 68.8,
                "judge_calls": 1,
                "hard_gate_shortcuts": 1,
            },
            {
                "label": "OpenHands `AGENTS.md`",
                "candidate_label": "GLM-5.2-current",
                "current_passed": 2,
                "reference_passed": 1,
                "total": 2,
                "current_wins": 1,
                "reference_wins": 0,
                "ties": 1,
                "inconclusive": 0,
                "delta": 16.3,
                "current_score": 84.7,
                "reference_score": 68.4,
                "judge_calls": 1,
                "hard_gate_shortcuts": 1,
            },
            {
                "label": "Claude/Fable prompt",
                "candidate_label": "GPT-5.5-current",
                "current_passed": 2,
                "reference_passed": 1,
                "total": 2,
                "current_wins": 1,
                "reference_wins": 0,
                "ties": 1,
                "inconclusive": 0,
                "delta": 23.9,
                "current_score": 94.5,
                "reference_score": 70.5,
                "judge_calls": 1,
                "hard_gate_shortcuts": 1,
            },
            {
                "label": "Claude/Fable prompt",
                "candidate_label": "GLM-5.2-current",
                "current_passed": 2,
                "reference_passed": 1,
                "total": 2,
                "current_wins": 1,
                "reference_wins": 0,
                "ties": 1,
                "inconclusive": 0,
                "delta": 17.9,
                "current_score": 87.9,
                "reference_score": 70.0,
                "judge_calls": 1,
                "hard_gate_shortcuts": 1,
            },
        ],
    )


def readme_svg_references(module):
    return " ".join(f"docs/assets/readme/{name}" for name in module.REQUIRED_README_SVGS)


def png_chunk(kind, payload):
    return len(payload).to_bytes(4, "big") + kind + payload + zlib.crc32(kind + payload).to_bytes(4, "big")


def write_text_png(path, metadata):
    path.parent.mkdir(parents=True, exist_ok=True)
    ihdr = (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 2, 0, 0, 0])
    idat = zlib.compress(b"\x00\xff\xff\xff")
    chunks = [png_chunk(b"IHDR", ihdr)]
    for key, value in metadata.items():
        chunks.append(png_chunk(b"tEXt", key.encode("latin-1") + b"\0" + value.encode("latin-1")))
    chunks.append(png_chunk(b"IDAT", idat))
    chunks.append(png_chunk(b"IEND", b""))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"".join(chunks))


def write_social_png(root, module, metadata=None):
    write_text_png(root / module.DEFAULT_SOCIAL_IMAGE, metadata or module.EXPECTED_SOCIAL_PNG_METADATA)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def write_summary(path, label, passed, total=2):
    results = []
    for index in range(total):
        results.append(
            {
                "case_id": f"case-{index}",
                "label": label,
                "passed": index < passed,
                "failure_type": "none" if index < passed else "behavior",
            }
        )
    write_json(path, {"passed": passed, "failed": total - passed, "total": total, "results": results})


def write_quality_summary(path, candidate_label, candidate_passed, baseline_passed, average_delta):
    write_json(
        path,
        {
            "baseline_label": "empty",
            "label": "saved-model-quality",
            "pairs": [
                {
                    "candidate_label": candidate_label,
                    "aggregate": {
                        "average_baseline_score": 20.0,
                        "average_current_score": 20.0 + average_delta,
                        "average_delta": average_delta,
                        "baseline_passed": baseline_passed,
                        "candidate_passed": candidate_passed,
                        "confidence": {"high": 2},
                        "sources": {"llm_judge": 1, "hard_gate": 1},
                        "total": 2,
                        "winners": {"baseline": 0, "current": 1, "inconclusive": 0, "tie": 1},
                    },
                    "quality_json": str(path.parent / "quality.json"),
                }
            ],
        },
    )


def write_reference_quality_summary(path, baseline_label):
    write_json(
        path,
        {
            "baseline_label": baseline_label,
            "label": f"{baseline_label}-saved-model-quality",
            "pairs": [
                {
                    "candidate_label": "GPT-5.5-current",
                    "aggregate": {
                        "average_baseline_score": 70.0,
                        "average_current_score": 95.0,
                        "average_delta": 25.0,
                        "baseline_passed": 1,
                        "candidate_passed": 2,
                        "sources": {"llm_judge": 1, "hard_gate": 1},
                        "total": 2,
                        "winners": {"baseline": 0, "current": 1, "inconclusive": 0, "tie": 1},
                    },
                    "quality_json": str(path.parent / "pairs/GPT-5.5-current/quality.json"),
                },
                {
                    "candidate_label": "GLM-5.2-current",
                    "aggregate": {
                        "average_baseline_score": 68.0,
                        "average_current_score": 84.0,
                        "average_delta": 16.0,
                        "baseline_passed": 1,
                        "candidate_passed": 2,
                        "sources": {"llm_judge": 1, "hard_gate": 1},
                        "total": 2,
                        "winners": {"baseline": 0, "current": 1, "inconclusive": 0, "tie": 1},
                    },
                    "quality_json": str(path.parent / "pairs/GLM-5.2-current/quality.json"),
                },
            ],
        },
    )


def write_snapshot_artifacts(root, module):
    (root / "evals").mkdir(parents=True)
    (root / module.CASE_FILE).write_text(
        "\n".join(json.dumps({"id": f"case-{index}"}) for index in range(2)) + "\n",
        encoding="utf-8",
    )
    rows = {
        "GPT-5.5": (2, 1, 28.4),
        "GLM-5.2": (2, 1, 62.9),
        "Grok 4.3": (1, 0, 56.4),
        "Grok Build 0.1": (1, 0, 42.6),
        "DeepSeek V4 Flash": (1, 0, 52.9),
        "DeepSeek V4 thinking": (1, 0, 52.9),
    }
    for item in module.MODEL_ARTIFACTS:
        current_passed, empty_passed, quality_delta = rows[item["label"]]
        write_summary(root / item["current"], "current", current_passed)
        write_summary(root / item["empty"], "empty", empty_passed)
        write_quality_summary(root / item["quality"], item["label"], current_passed, empty_passed, quality_delta)
    write_json(
        root / module.GPT_EXTERNAL_QUALITY,
        {
            "baseline_label": "GPT-5.5",
            "label": "GPT-5.5-saved-model-quality",
            "pairs": [
                {
                    "candidate_label": "GLM-5.2",
                    "aggregate": {
                        "average_baseline_score": 90.0,
                        "average_current_score": 80.0,
                        "average_delta": -10.0,
                        "baseline_passed": 2,
                        "candidate_passed": 2,
                        "confidence": {"high": 2},
                        "sources": {"llm_judge": 2},
                        "total": 2,
                        "winners": {"baseline": 1, "current": 1, "inconclusive": 0, "tie": 0},
                    },
                    "quality_json": str(root / module.QUALITY_ROOT / "gpt-vs-external-current/pairs/glm/quality.json"),
                }
            ],
        },
    )
    for item in module.REFERENCE_QUALITY_SUMMARIES:
        write_reference_quality_summary(root / item["quality"], item["label"])


def write_matching_docs(root, module, snapshot):
    snippets = module.expected_doc_snippets(snapshot)
    readme = root / "README.md"
    results = root / "evals" / "RESULTS.md"
    quality_cases = root / "evals" / "PROMPT_QUALITY_CASES.md"
    changelog = root / "evals" / "CHANGELOG.md"
    readme.write_text(" ".join(snippets["README.md"]) + " " + readme_svg_references(module), encoding="utf-8")
    results.write_text("\n".join(snippets["evals/RESULTS.md"]) + "\n", encoding="utf-8")
    quality_cases.write_text("\n".join(snippets["evals/PROMPT_QUALITY_CASES.md"]) + "\n", encoding="utf-8")
    changelog.write_text("\n".join(snippets["evals/CHANGELOG.md"]) + "\n", encoding="utf-8")


class CheckPublishedEvalMetricsTests(unittest.TestCase):
    def test_summarize_artifacts_computes_metric_snapshot(self):
        module = load_script()

        metrics = module.summarize_artifacts(
            summary_fixture(),
            quality_fixture(),
            summary_path=Path("summary.json"),
            quality_path=Path("quality.json"),
        )

        self.assertEqual(metrics.summary_passed, 4)
        self.assertEqual(metrics.summary_total, 4)
        self.assertEqual(metrics.case_count, 2)
        self.assertEqual(metrics.baseline_passed, 2)
        self.assertEqual(metrics.current_passed, 2)
        self.assertEqual(metrics.current_wins, 1)
        self.assertEqual(metrics.baseline_wins, 1)
        self.assertEqual(metrics.average_delta_text, "+1.00")

    def test_summarize_artifacts_rejects_missing_summary_side(self):
        module = load_script()
        summary = summary_fixture()
        summary["results"] = summary["results"][:-1]
        summary["passed"] = 3

        with self.assertRaisesRegex(ValueError, "missing summary label"):
            module.summarize_artifacts(
                summary,
                quality_fixture(),
                summary_path=Path("summary.json"),
                quality_path=Path("quality.json"),
            )

    def test_summarize_artifacts_rejects_duplicate_summary_label(self):
        module = load_script()
        summary = summary_fixture()
        summary["results"][-1]["case_id"] = "case-a"

        with self.assertRaisesRegex(ValueError, "duplicate summary label"):
            module.summarize_artifacts(
                summary,
                quality_fixture(),
                summary_path=Path("summary.json"),
                quality_path=Path("quality.json"),
            )

    def test_summarize_artifacts_rejects_summary_quality_case_mismatch(self):
        module = load_script()
        quality = quality_fixture()
        quality["comparisons"][-1]["case_id"] = "case-c"

        with self.assertRaisesRegex(ValueError, "case_id mismatch"):
            module.summarize_artifacts(
                summary_fixture(),
                quality,
                summary_path=Path("summary.json"),
                quality_path=Path("quality.json"),
            )

    def test_summarize_artifacts_rejects_duplicate_quality_case_id(self):
        module = load_script()
        quality = quality_fixture()
        quality["comparisons"][-1]["case_id"] = "case-a"

        with self.assertRaisesRegex(ValueError, "duplicate comparison case_id"):
            module.summarize_artifacts(
                summary_fixture(),
                quality,
                summary_path=Path("summary.json"),
                quality_path=Path("quality.json"),
            )

    def test_check_docs_accepts_matching_50_case_text(self):
        module = load_script()
        snapshot = snapshot_fixture(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evals").mkdir()
            write_matching_docs(root, module, snapshot)
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(
                    snapshot,
                    [
                        Path("README.md"),
                        Path("evals/RESULTS.md"),
                        Path("evals/PROMPT_QUALITY_CASES.md"),
                        Path("evals/CHANGELOG.md"),
                    ],
                )
            finally:
                os.chdir(cwd)

        self.assertEqual(problems, [])

    def test_check_docs_reports_stale_quality_pending_text(self):
        module = load_script()
        snapshot = snapshot_fixture(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evals").mkdir()
            write_matching_docs(root, module, snapshot)
            readme = root / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + " 50-case saved quality evidence is still pending.", encoding="utf-8")
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(snapshot, [Path("README.md")])
            finally:
                os.chdir(cwd)

        self.assertTrue(any("forbidden 50-case publication overclaim/stale caveat" in problem for problem in problems))

    def test_missing_readme_svg_references_reports_unlinked_assets(self):
        module = load_script()
        text = "docs/assets/readme/instruction-lift.svg"

        missing = module.missing_readme_svg_references(text, ["instruction-lift.svg", "model-transfer.svg"])

        self.assertEqual(missing, ["model-transfer.svg"])

    def test_forbidden_publication_overclaims_reports_variant_phrases(self):
        module = load_script()

        claims = module.forbidden_publication_overclaims(
            "This is a hard-gate-only 50-case snapshot. "
            "The complete 50-case reference refresh is ready. "
            "External reference rows are complete. "
            "GPT reference rows only; external reference rows remain pending. "
            "This is an all-model quality improvement. "
            "The current instructions improved every tested model."
        )

        self.assertTrue(any("hard-gate-only 50-case snapshot" in claim for claim in claims))
        self.assertTrue(any("complete 50-case reference refresh" in claim for claim in claims))
        self.assertTrue(any("external reference rows are complete" in claim for claim in claims))
        self.assertTrue(any("external reference rows remain pending" in claim for claim in claims))
        self.assertTrue(any("all-model quality improvement" in claim for claim in claims))
        self.assertTrue(any("improved every tested model" in claim for claim in claims))

    def test_forbidden_publication_overclaims_reports_pending_reference_caveat(self):
        module = load_script()

        claims = module.forbidden_publication_overclaims(
            "This is a 50-case saved quality snapshot. "
            "GPT reference rows are complete; external reference rows remain pending."
        )

        self.assertTrue(any("external reference rows remain pending" in claim for claim in claims))

    def test_check_svg_scope_accepts_scoped_svg_files(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp)
            (svg_dir / "chart.svg").write_text(
                f"<svg><text>{module.EXPECTED_SVG_SCOPE}</text></svg>\n",
                encoding="utf-8",
            )

            self.assertEqual(module.check_svg_scope(svg_dir, ["chart.svg"]), [])

    def test_check_svg_scope_reports_missing_scope_footer(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp)
            (svg_dir / "chart.svg").write_text("<svg><text>No scope</text></svg>\n", encoding="utf-8")

            problems = module.check_svg_scope(svg_dir, ["chart.svg"])

        self.assertIn("missing SVG scope footer", problems[0])

    def test_check_svg_scope_reports_forbidden_publication_overclaim(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp)
            (svg_dir / "chart.svg").write_text(
                f"<svg><text>{module.EXPECTED_SVG_SCOPE}</text>"
                "<text>The complete 50-case reference refresh is ready.</text></svg>\n",
                encoding="utf-8",
            )

            problems = module.check_svg_scope(svg_dir, ["chart.svg"])

        self.assertTrue(any("forbidden 50-case publication overclaim" in problem for problem in problems))

    def test_check_svg_scope_reports_missing_required_svg(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            svg_dir = Path(tmp)
            (svg_dir / "other.svg").write_text(
                f"<svg><text>{module.EXPECTED_SVG_SCOPE}</text></svg>\n",
                encoding="utf-8",
            )

            problems = module.check_svg_scope(svg_dir, ["required.svg"])

        self.assertIn("missing required README SVG", problems[0])

    def test_check_social_png_accepts_expected_metadata(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "social.png"
            write_text_png(path, module.EXPECTED_SOCIAL_PNG_METADATA)

            self.assertEqual(module.check_social_png(path), [])

    def test_check_social_png_reports_stale_metadata(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "social.png"
            metadata = dict(module.EXPECTED_SOCIAL_PNG_METADATA)
            metadata["instruction_snapshot_cases"] = "49"
            write_text_png(path, metadata)

            problems = module.check_social_png(path)

        self.assertTrue(any("instruction_snapshot_cases" in problem for problem in problems))

    def test_main_success_output_mentions_publication_scope_checks(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_snapshot_artifacts(root, module)
            snapshot = module.load_snapshot_metrics(root)
            write_matching_docs(root, module, snapshot)
            write_social_png(root, module)
            svg_dir = root / "svg"
            svg_dir.mkdir()
            for name in module.REQUIRED_README_SVGS:
                (svg_dir / name).write_text(
                    f"<svg><text>{module.EXPECTED_SVG_SCOPE}</text></svg>\n",
                    encoding="utf-8",
                )

            stdout = io.StringIO()
            cwd = Path.cwd()
            try:
                os.chdir(root)
                with redirect_stdout(stdout):
                    rc = module.main(["--svg-dir", str(svg_dir)])
            finally:
                os.chdir(cwd)

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("published 50-case eval publication guard ok:", output)
        self.assertIn("cases=2", output)
        self.assertIn("docs=4", output)
        self.assertIn("svgs=10", output)
        self.assertIn("social=checked", output)
        self.assertIn("scope=checked", output)

    def test_main_failure_output_mentions_publication_guard(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_snapshot_artifacts(root, module)
            snapshot = module.load_snapshot_metrics(root)
            write_matching_docs(root, module, snapshot)
            write_social_png(root, module)
            svg_dir = root / "svg"
            svg_dir.mkdir()

            stderr = io.StringIO()
            cwd = Path.cwd()
            try:
                os.chdir(root)
                with redirect_stderr(stderr):
                    rc = module.main(["--svg-dir", str(svg_dir)])
            finally:
                os.chdir(cwd)

        self.assertEqual(rc, 1)
        output = stderr.getvalue()
        self.assertIn("published eval publication guard failed:", output)
        self.assertIn("no SVG files found", output)

    def test_cli_description_mentions_docs_and_svg_scope(self):
        module = load_script()
        stdout = io.StringIO()

        with self.assertRaises(SystemExit) as raised:
            with redirect_stdout(stdout):
                module.parse_args(["--help"])

        self.assertEqual(raised.exception.code, 0)
        help_text = stdout.getvalue()
        self.assertIn(
            "50-case eval metrics, docs caveats, README SVG scope, and social PNG metadata",
            " ".join(help_text.split()),
        )


if __name__ == "__main__":
    unittest.main()
