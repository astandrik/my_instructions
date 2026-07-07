import importlib.util
import io
import json
import os
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


def readme_svg_references(module):
    return " ".join(f"docs/assets/readme/{name}" for name in module.REQUIRED_README_SVGS)


def artifact_reference(module, summary_path, key):
    return module.expected_artifact_snippets(summary_path)[key][0]


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

    def test_check_docs_accepts_matching_metric_text(self):
        module = load_script()
        metrics = module.PublishedMetrics(
            summary_passed=4,
            summary_total=4,
            case_count=2,
            baseline_passed=2,
            current_passed=2,
            current_wins=1,
            baseline_wins=1,
            ties=0,
            inconclusive=0,
            average_delta=1.0,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evals").mkdir()
            readme = root / "README.md"
            results = root / "evals" / "RESULTS.md"
            changelog = root / "evals" / "CHANGELOG.md"
            readme.write_text(
                "4/4 hard gates passed. current winning 1 quality comparisons, "
                "baseline winning 1, 0 ties, and average delta +1.00. "
                "This is partial v4.13 evidence. "
                "Grok v4.13 full rows are still pending. "
                f"{readme_svg_references(module)}",
                encoding="utf-8",
            )
            results.write_text(
                "This is partial v4.13 evidence, not a full all-model refresh.\n"
                "Grok v4.13 full rows are still pending.\n"
                "| Baseline `HEAD` | 2 / 2 | 0 |\n"
                "| Current worktree | 2 / 2 | 0 |\n"
                "| 2 pass/pass cases | 1 | 1 | 0 | +1.00 |\n",
                encoding="utf-8",
            )
            changelog.write_text(
                "This is partial v4.13 evidence, not a full all-model refresh.\n"
                "Grok v4.13 full rows are still pending.\n"
                "v11 full compare: 4 / 4 hard gates passed.\n"
                "current 1 wins, baseline 1 wins, 0 ties, average delta +1.00.\n",
                encoding="utf-8",
            )

            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(metrics, [readme.relative_to(root), results.relative_to(root), changelog.relative_to(root)])
            finally:
                os.chdir(cwd)

        self.assertEqual(problems, [])

    def test_missing_readme_svg_references_reports_unlinked_assets(self):
        module = load_script()
        text = "docs/assets/readme/instruction-lift.svg"

        missing = module.missing_readme_svg_references(text, ["instruction-lift.svg", "model-transfer.svg"])

        self.assertEqual(missing, ["model-transfer.svg"])

    def test_check_docs_reports_missing_readme_svg_reference(self):
        module = load_script()
        metrics = module.PublishedMetrics(
            summary_passed=4,
            summary_total=4,
            case_count=2,
            baseline_passed=2,
            current_passed=2,
            current_wins=1,
            baseline_wins=1,
            ties=0,
            inconclusive=0,
            average_delta=1.0,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text(
                "4/4 hard gates passed. current winning 1 quality comparisons, "
                "baseline winning 1, 0 ties, and average delta +1.00. "
                "This is partial v4.13 evidence. "
                "Grok v4.13 full rows are still pending.",
                encoding="utf-8",
            )
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(metrics, [readme.relative_to(root)])
            finally:
                os.chdir(cwd)

        self.assertTrue(any("missing README SVG reference" in problem for problem in problems))

    def test_check_docs_reports_missing_or_stale_metric_text(self):
        module = load_script()
        metrics = module.PublishedMetrics(
            summary_passed=4,
            summary_total=4,
            case_count=2,
            baseline_passed=2,
            current_passed=2,
            current_wins=1,
            baseline_wins=1,
            ties=0,
            inconclusive=0,
            average_delta=1.0,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text("4/4 hard gates passed. This is partial v4.13 evidence.", encoding="utf-8")
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(metrics, [readme.relative_to(root)])
            finally:
                os.chdir(cwd)

        self.assertIn("missing published metric/caveat snippet", problems[0])

    def test_check_docs_reports_missing_artifact_reference(self):
        module = load_script()
        metrics = module.PublishedMetrics(
            summary_passed=4,
            summary_total=4,
            case_count=2,
            baseline_passed=2,
            current_passed=2,
            current_wins=1,
            baseline_wins=1,
            ties=0,
            inconclusive=0,
            average_delta=1.0,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text(
                "4/4 hard gates passed. current winning 1 quality comparisons, "
                "baseline winning 1, 0 ties, and average delta +1.00. "
                "This is partial v4.13 evidence. "
                "Grok v4.13 full rows are still pending. "
                f"{readme_svg_references(module)}",
                encoding="utf-8",
            )
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(
                    metrics,
                    [readme.relative_to(root)],
                    {"README.md": [".eval-results/run-under-test/"]},
                )
            finally:
                os.chdir(cwd)

        self.assertTrue(any(".eval-results/run-under-test/" in problem for problem in problems))

    def test_check_docs_reports_missing_explicit_scope_caveat(self):
        module = load_script()
        metrics = module.PublishedMetrics(
            summary_passed=4,
            summary_total=4,
            case_count=2,
            baseline_passed=2,
            current_passed=2,
            current_wins=1,
            baseline_wins=1,
            ties=0,
            inconclusive=0,
            average_delta=1.0,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text(
                "4/4 hard gates passed. current winning 1 quality comparisons, "
                "baseline winning 1, 0 ties, and average delta +1.00. "
                "This is partial v4.13 evidence. "
                ".eval-results/run-under-test/ "
                f"{readme_svg_references(module)}",
                encoding="utf-8",
            )
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(
                    metrics,
                    [readme.relative_to(root)],
                    {"README.md": [".eval-results/run-under-test/"]},
                )
            finally:
                os.chdir(cwd)

        self.assertTrue(any("Grok v4.13 full rows are still pending" in problem for problem in problems))

    def test_check_docs_reports_forbidden_v413_all_model_overclaim(self):
        module = load_script()
        metrics = module.PublishedMetrics(
            summary_passed=4,
            summary_total=4,
            case_count=2,
            baseline_passed=2,
            current_passed=2,
            current_wins=1,
            baseline_wins=1,
            ties=0,
            inconclusive=0,
            average_delta=1.0,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text(
                "4/4 hard gates passed. current winning 1 quality comparisons, "
                "baseline winning 1, 0 ties, and average delta +1.00. "
                "This is partial v4.13 evidence. "
                "Grok v4.13 full rows are still pending. "
                "v4.13 all-model evidence is ready. "
                f"{readme_svg_references(module)}",
                encoding="utf-8",
            )
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(metrics, [readme.relative_to(root)])
            finally:
                os.chdir(cwd)

        self.assertIn("forbidden v4.13 publication overclaim", problems[-1])

    def test_check_docs_accepts_caveated_provider_hard_gate_snapshot(self):
        module = load_script()
        metrics = module.PublishedMetrics(
            summary_passed=4,
            summary_total=4,
            case_count=2,
            baseline_passed=2,
            current_passed=2,
            current_wins=1,
            baseline_wins=1,
            ties=0,
            inconclusive=0,
            average_delta=1.0,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text(
                "4/4 hard gates passed. current winning 1 quality comparisons, "
                "baseline winning 1, 0 ties, and average delta +1.00. "
                "This is partial v4.13 evidence. "
                "Grok v4.13 full rows are still pending. "
                "Fresh v4.13 provider hard-gate snapshot: external transfer is not uniformly positive; "
                "GLM quality pending; xAI/Grok policy-blocked. "
                "Source: .eval-results/refresh-under-test/ "
                f"{readme_svg_references(module)}",
                encoding="utf-8",
            )
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(metrics, [readme.relative_to(root)])
            finally:
                os.chdir(cwd)

        self.assertEqual(problems, [])

    def test_check_docs_accepts_mixed_provider_hard_gate_snapshot_caveat(self):
        module = load_script()
        metrics = module.PublishedMetrics(
            summary_passed=4,
            summary_total=4,
            case_count=2,
            baseline_passed=2,
            current_passed=2,
            current_wins=1,
            baseline_wins=1,
            ties=0,
            inconclusive=0,
            average_delta=1.0,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text(
                "4/4 hard gates passed. current winning 1 quality comparisons, "
                "baseline winning 1, 0 ties, and average delta +1.00. "
                "This is partial v4.13 evidence. "
                "Grok v4.13 full rows are still pending. "
                "Fresh v4.13 provider hard gate snapshot: mixed external transfer; "
                "GLM quality pending; xAI/Grok policy-blocked. "
                "Source: .eval-results/refresh-under-test/ "
                f"{readme_svg_references(module)}",
                encoding="utf-8",
            )
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(metrics, [readme.relative_to(root)])
            finally:
                os.chdir(cwd)

        self.assertEqual(problems, [])

    def test_check_docs_requires_provider_snapshot_caveats_in_same_section(self):
        module = load_script()
        metrics = module.PublishedMetrics(
            summary_passed=4,
            summary_total=4,
            case_count=2,
            baseline_passed=2,
            current_passed=2,
            current_wins=1,
            baseline_wins=1,
            ties=0,
            inconclusive=0,
            average_delta=1.0,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text(
                "4/4 hard gates passed. current winning 1 quality comparisons, "
                "baseline winning 1, 0 ties, and average delta +1.00. "
                "This is partial v4.13 evidence. "
                "Grok v4.13 full rows are still pending. "
                "Elsewhere: mixed external transfer; GLM quality pending; "
                "xAI/Grok policy-blocked. Source: .eval-results/refresh-under-test/\n\n"
                "Fresh v4.13 provider hard-gate snapshot is ready. "
                f"{readme_svg_references(module)}",
                encoding="utf-8",
            )
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(metrics, [readme.relative_to(root)])
            finally:
                os.chdir(cwd)

        self.assertTrue(any("must mark incomplete quality as pending" in problem for problem in problems))
        self.assertTrue(any("must mention policy-blocked provider rows" in problem for problem in problems))
        self.assertTrue(any("must reference a saved .eval-results artifact root" in problem for problem in problems))
        self.assertTrue(any("must describe external transfer as mixed or not uniformly positive" in problem for problem in problems))

    def test_check_docs_reports_uncaveated_provider_hard_gate_snapshot(self):
        module = load_script()
        metrics = module.PublishedMetrics(
            summary_passed=4,
            summary_total=4,
            case_count=2,
            baseline_passed=2,
            current_passed=2,
            current_wins=1,
            baseline_wins=1,
            ties=0,
            inconclusive=0,
            average_delta=1.0,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text(
                "4/4 hard gates passed. current winning 1 quality comparisons, "
                "baseline winning 1, 0 ties, and average delta +1.00. "
                "This is partial v4.13 evidence. "
                "Grok v4.13 full rows are still pending. "
                "Fresh v4.13 provider hard-gate snapshot is ready. "
                f"{readme_svg_references(module)}",
                encoding="utf-8",
            )
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(metrics, [readme.relative_to(root)])
            finally:
                os.chdir(cwd)

        self.assertTrue(any("must mark incomplete quality as pending" in problem for problem in problems))
        self.assertTrue(any("must mention policy-blocked provider rows" in problem for problem in problems))
        self.assertTrue(any("must reference a saved .eval-results artifact root" in problem for problem in problems))
        self.assertTrue(any("must describe external transfer as mixed or not uniformly positive" in problem for problem in problems))

    def test_check_docs_reports_uncaveated_provider_hard_gate_snapshot_without_hyphen(self):
        module = load_script()
        metrics = module.PublishedMetrics(
            summary_passed=4,
            summary_total=4,
            case_count=2,
            baseline_passed=2,
            current_passed=2,
            current_wins=1,
            baseline_wins=1,
            ties=0,
            inconclusive=0,
            average_delta=1.0,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text(
                "4/4 hard gates passed. current winning 1 quality comparisons, "
                "baseline winning 1, 0 ties, and average delta +1.00. "
                "This is partial v4.13 evidence. "
                "Grok v4.13 full rows are still pending. "
                "Fresh v4.13 provider hard gate snapshot is ready. "
                f"{readme_svg_references(module)}",
                encoding="utf-8",
            )
            cwd = Path.cwd()
            try:
                os.chdir(root)
                problems = module.check_docs(metrics, [readme.relative_to(root)])
            finally:
                os.chdir(cwd)

        self.assertTrue(any("must mark incomplete quality as pending" in problem for problem in problems))
        self.assertTrue(any("must mention policy-blocked provider rows" in problem for problem in problems))
        self.assertTrue(any("must reference a saved .eval-results artifact root" in problem for problem in problems))
        self.assertTrue(any("must describe external transfer as mixed or not uniformly positive" in problem for problem in problems))

    def test_forbidden_scope_overclaims_reports_variant_phrases(self):
        module = load_script()

        claims = module.forbidden_scope_overclaims(
            "The v4.13 evidence across all models is ready. "
            "External provider rows were re-run after v4.13. "
            "The v4.13 all model comparison is done. "
            "All models v4.13 evidence is ready. "
            "This is an all-model quality improvement. "
            "The current instructions improved every tested model. "
            "This improves all tested models. "
            "External models improved. "
            "External providers improved. "
            "This improves all providers. "
            "GLM quality improved. "
            "Z.ai quality improvement is proven. "
            "Quality improved for DeepSeek non-thinking."
        )

        self.assertTrue(any("v4.13 evidence across all models" in claim for claim in claims))
        self.assertTrue(any("external provider rows were re-run after v4.13" in claim for claim in claims))
        self.assertTrue(any("v4.13 all model comparison" in claim for claim in claims))
        self.assertTrue(any("all models v4.13 evidence" in claim for claim in claims))
        self.assertTrue(any("all-model quality improvement" in claim for claim in claims))
        self.assertTrue(any("improved every tested model" in claim for claim in claims))
        self.assertTrue(any("improves all tested models" in claim for claim in claims))
        self.assertTrue(any("external models improved" in claim for claim in claims))
        self.assertTrue(any("external providers improved" in claim for claim in claims))
        self.assertTrue(any("improves all providers" in claim for claim in claims))
        self.assertTrue(any("glm quality improved" in claim for claim in claims))
        self.assertTrue(any("z.ai quality improvement" in claim for claim in claims))
        self.assertTrue(any("quality improved for deepseek non-thinking" in claim for claim in claims))

    def test_forbidden_scope_overclaims_allows_negative_caveats(self):
        module = load_script()

        claims = module.forbidden_scope_overclaims(
            "This is partial v4.13 evidence, not a full all-model refresh. "
            "External transfer is not uniformly positive; Grok v4.13 full rows are still pending."
        )

        self.assertEqual(claims, [])

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
                "<text>The v4.13 evidence across all models is ready.</text></svg>\n",
                encoding="utf-8",
            )

            problems = module.check_svg_scope(svg_dir, ["chart.svg"])

        self.assertTrue(any("forbidden v4.13 publication overclaim" in problem for problem in problems))

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

    def test_main_success_output_mentions_publication_scope_checks(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = root / "summary.json"
            quality = root / "quality.json"
            summary.write_text(json.dumps(summary_fixture()), encoding="utf-8")
            quality.write_text(json.dumps(quality_fixture()), encoding="utf-8")
            (root / "evals").mkdir()
            readme = root / "README.md"
            results = root / "evals" / "RESULTS.md"
            changelog = root / "evals" / "CHANGELOG.md"
            readme.write_text(
                "4/4 hard gates passed. current winning 1 quality comparisons, "
                "baseline winning 1, 0 ties, and average delta +1.00. "
                "This is partial v4.13 evidence. "
                "Grok v4.13 full rows are still pending. "
                f"{artifact_reference(module, summary, 'README.md')} "
                f"{readme_svg_references(module)}",
                encoding="utf-8",
            )
            results.write_text(
                "This is partial v4.13 evidence, not a full all-model refresh.\n"
                "Grok v4.13 full rows are still pending.\n"
                f"{artifact_reference(module, summary, 'evals/RESULTS.md')}\n"
                "| Baseline `HEAD` | 2 / 2 | 0 |\n"
                "| Current worktree | 2 / 2 | 0 |\n"
                "| 2 pass/pass cases | 1 | 1 | 0 | +1.00 |\n",
                encoding="utf-8",
            )
            changelog.write_text(
                "This is partial v4.13 evidence, not a full all-model refresh.\n"
                "Grok v4.13 full rows are still pending.\n"
                f"{artifact_reference(module, summary, 'evals/CHANGELOG.md')}\n"
                "v11 full compare: 4 / 4 hard gates passed.\n"
                "current 1 wins, baseline 1 wins, 0 ties, average delta +1.00.\n",
                encoding="utf-8",
            )
            svg_dir = root / "svg"
            svg_dir.mkdir()
            for name in module.REQUIRED_README_SVGS:
                (svg_dir / name).write_text(
                    f"<svg><text>{module.EXPECTED_SVG_SCOPE}</text></svg>\n",
                    encoding="utf-8",
                )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = module.main(
                    [
                        "--summary",
                        str(summary),
                        "--quality",
                        str(quality),
                        "--doc",
                        str(readme),
                        "--doc",
                        str(results),
                        "--doc",
                        str(changelog),
                        "--svg-dir",
                        str(svg_dir),
                    ]
                )

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("published eval publication guard ok:", output)
        self.assertIn("docs=3", output)
        self.assertIn("svgs=9", output)
        self.assertIn("scope=checked", output)

    def test_main_failure_output_mentions_publication_guard(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = root / "summary.json"
            quality = root / "quality.json"
            summary.write_text(json.dumps(summary_fixture()), encoding="utf-8")
            quality.write_text(json.dumps(quality_fixture()), encoding="utf-8")
            (root / "evals").mkdir()
            readme = root / "README.md"
            results = root / "evals" / "RESULTS.md"
            changelog = root / "evals" / "CHANGELOG.md"
            readme.write_text(
                "4/4 hard gates passed. current winning 1 quality comparisons, "
                "baseline winning 1, 0 ties, and average delta +1.00. "
                "This is partial v4.13 evidence. "
                "Grok v4.13 full rows are still pending. "
                f"{artifact_reference(module, summary, 'README.md')} "
                f"{readme_svg_references(module)}",
                encoding="utf-8",
            )
            results.write_text(
                "This is partial v4.13 evidence, not a full all-model refresh.\n"
                "Grok v4.13 full rows are still pending.\n"
                f"{artifact_reference(module, summary, 'evals/RESULTS.md')}\n"
                "| Baseline `HEAD` | 2 / 2 | 0 |\n"
                "| Current worktree | 2 / 2 | 0 |\n"
                "| 2 pass/pass cases | 1 | 1 | 0 | +1.00 |\n",
                encoding="utf-8",
            )
            changelog.write_text(
                "This is partial v4.13 evidence, not a full all-model refresh.\n"
                "Grok v4.13 full rows are still pending.\n"
                f"{artifact_reference(module, summary, 'evals/CHANGELOG.md')}\n"
                "v11 full compare: 4 / 4 hard gates passed.\n"
                "current 1 wins, baseline 1 wins, 0 ties, average delta +1.00.\n",
                encoding="utf-8",
            )
            svg_dir = root / "svg"
            svg_dir.mkdir()

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                rc = module.main(
                    [
                        "--summary",
                        str(summary),
                        "--quality",
                        str(quality),
                        "--doc",
                        str(readme),
                        "--doc",
                        str(results),
                        "--doc",
                        str(changelog),
                        "--svg-dir",
                        str(svg_dir),
                    ]
                )

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
        self.assertIn("eval metrics, docs caveats, and README SVG scope", help_text)


if __name__ == "__main__":
    unittest.main()
