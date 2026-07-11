import importlib.util
import re
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_readme_infographics.py"
LEGACY_CAVEAT = (
    "Legacy pre-blinding snapshot: primary prompts exposed case id/scenario metadata "
    "(prompt contamination)."
)
LEGACY_SCOPE = (
    "Scope: legacy pre-blinding snapshot, 50 cases; primary prompts exposed case id/scenario metadata; "
    "all-model reference rows included."
)
BLINDED_HARD_GATE_SCOPE = (
    "Scope: blinded With instructions v4.13 vs Empty instructions hard gates, "
    "50 cases, 6 model/runner rows; no reference rows. Pre-semantic-alternative scorer snapshot."
)
BLINDED_DUAL_ORDER_SCOPE = (
    "Scope: blinded With instructions v4.13 vs Empty instructions dual-order quality, "
    "50 cases, 6 model/runner rows; fixed gpt-5.6-sol-medium judge; "
    "order-sensitive verdicts are separate; no reference rows. Pre-semantic-alternative scorer snapshot."
)
SIX_MODEL_IDS = [
    "gpt-5.6-sol",
    "gpt-5.5",
    "glm-5.2",
    "grok-4.3",
    "deepseek-v4-flash",
    "deepseek-v4-flash-thinking",
]
BLINDED_QUALITY_ROOT = Path(
    ".eval-results/blinded-50-case-v1/dual-order-quality-v2"
)
EXPECTED_README_SVGS = {
    "coverage-watchlist.svg",
    "empty-current-lift.svg",
    "hard-gates-50.svg",
    "quality-only-comparisons.svg",
    "model-quality-absolute.svg",
    "model-quality-common-cases.svg",
    "model-quality-judge-audit.svg",
}
OBSOLETE_README_SVGS = {
    "case-detail-comparisons.svg",
    "instruction-lift.svg",
    "model-gap.svg",
    "model-transfer.svg",
    "quality-only-case-matrix.svg",
    "reference-prompts.svg",
}
OBSOLETE_SOCIAL_SVG = "instruction-quality-lift-linkedin.svg"
SAME_MODEL_JUDGE_CAVEAT = (
    "The GPT-5.6 Sol row uses the same model family as the fixed quality judge; "
    "this is instruction-lift evidence, not a cross-model leaderboard."
)
GROK_BUILD_EXCLUSION_CAVEAT = (
    "Grok Build is excluded because repeated transport failures prevented a clean primary pair."
)


def load_script():
    spec = importlib.util.spec_from_file_location("build_readme_infographics", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def six_publication_rows():
    labels = [
        ("GPT-5.6 Sol medium", "Sol", "#4f46e5"),
        ("GPT-5.5", "GPT", "#2563eb"),
        ("GLM-5.2", "GLM", "#16a34a"),
        ("Grok 4.3", "G4", "#ea580c"),
        ("DeepSeek V4 Flash", "DS", "#0891b2"),
        ("DeepSeek V4 Flash thinking", "DS-T", "#0f766e"),
    ]
    quality_scores = [
        (60.40, 39.59),
        (68.02, 47.05),
        (56.62, 16.54),
        (43.15, 5.89),
        (35.26, 9.07),
        (40.51, 9.31),
    ]
    rows = []
    for index, (label, short, color) in enumerate(labels):
        current_passed = 35 - index
        empty_passed = 25 - index
        current_score, empty_score = quality_scores[index]
        rows.append(
            {
                "model_id": SIX_MODEL_IDS[index],
                "label": label,
                "short": short,
                "color": color,
                "note": "blinded row",
                "current_passed": current_passed,
                "current_failed": 50 - current_passed,
                "empty_passed": empty_passed,
                "empty_failed": 50 - empty_passed,
                "total": 50,
                "pass_delta": current_passed - empty_passed,
                "execution_failures": 0,
                "agent": 0,
                "empty_agent": 0,
                "results": [
                    {"case_id": f"case-{case_index:02d}", "passed": case_index < current_passed}
                    for case_index in range(50)
                ],
                "dual_order_winners": {
                    "current": 21,
                    "baseline": 3,
                    "tie": 3,
                    "inconclusive": 17,
                    "order_sensitive": 6,
                },
                "scores": {
                    "all_cases": {
                        "cases": 50,
                        "baseline": empty_score,
                        "current": current_score,
                        "delta": round(current_score - empty_score, 2),
                    }
                },
                "same_model_judge": SIX_MODEL_IDS[index] == "gpt-5.6-sol",
            }
        )
    return rows


def absolute_quality_fixture():
    labels = {
        "gpt-5.6-sol": ("GPT-5.6 Sol medium", "primary", 33, 98.15),
        "gpt-5.5": ("GPT-5.5", "historical", 35, 96.86),
        "glm-5.2": ("GLM-5.2", "external", 29, 95.45),
        "grok-4.3": ("Grok 4.3", "external", 25, 86.36),
        "deepseek-v4-flash": ("DeepSeek V4 Flash", "external", 18, 81.56),
        "deepseek-v4-flash-thinking": (
            "DeepSeek V4 Flash thinking",
            "external",
            23,
            88.87,
        ),
    }
    models = [
        {
            "model_id": model_id,
            "model_label": labels[model_id][0],
            "role": labels[model_id][1],
            "hard_gate_passed": labels[model_id][2],
            "hard_gate_total": 50,
            "hard_gate_pass_rate": labels[model_id][2] / 50,
            "mean_absolute_score": labels[model_id][3],
            "dimension_scores": {},
        }
        for model_id in SIX_MODEL_IDS
    ]
    comparisons = []
    for a_index, model_a in enumerate(SIX_MODEL_IDS):
        for b_index in range(a_index + 1, len(SIX_MODEL_IDS)):
            model_b = SIX_MODEL_IDS[b_index]
            overlap = 30 - len(comparisons)
            comparisons.append(
                {
                    "model_a_id": model_a,
                    "model_b_id": model_b,
                    "overlap": overlap,
                    "mean_model_a_score": 98.0 - a_index,
                    "mean_model_b_score": 97.0 - b_index,
                    "mean_delta_b_minus_a": round((97.0 - b_index) - (98.0 - a_index), 2),
                    "direction": model_a,
                    "a_higher": max(overlap - 5, 0),
                    "equal": min(2, overlap),
                    "b_higher": min(3, max(overlap - 2, 0)),
                    "cases": [],
                }
            )
    return {
        "methodology": "single_response_absolute_scoring",
        "judge": {"key": "sol", "preset": "gpt-5.6-sol-medium"},
        "total_judgments": 163,
        "models": models,
        "common_case_comparisons": comparisons,
    }


def absolute_audit_fixture():
    quality = absolute_quality_fixture()
    return {
        "methodology": "single_response_absolute_scoring_judge_audit",
        "models": [
            {
                "model_id": row["model_id"],
                "model_label": row["model_label"],
                "role": row["role"],
                "sol_mean_score": row["mean_absolute_score"],
                "terra_mean_score": row["mean_absolute_score"] - 1,
                "terra_minus_sol_mean_score": -1.0,
            }
            for row in quality["models"]
        ],
        "common_case_comparisons": [
            {
                "model_a_id": row["model_a_id"],
                "model_b_id": row["model_b_id"],
                "overlap": row["overlap"],
                "sol_direction": row["direction"],
                "terra_direction": row["direction"],
                "changed_case_directions": 1,
                "judge_sensitive": False,
            }
            for row in quality["common_case_comparisons"]
        ],
    }


class BuildReadmeInfographicsTests(unittest.TestCase):
    def test_blinded_model_manifest_has_exact_six_row_order_and_v2_quality_root(self):
        module = load_script()

        self.assertTrue(
            hasattr(module, "BLINDED_MODELS"),
            "generator must expose the blinded six-row publication manifest",
        )
        self.assertEqual(
            [row["model_id"] for row in module.BLINDED_MODELS],
            SIX_MODEL_IDS,
        )
        self.assertEqual(module.BLINDED_QUALITY_ROOT, BLINDED_QUALITY_ROOT)
        manifest_text = "\n".join(str(value) for row in module.BLINDED_MODELS for value in row.values())
        self.assertNotIn("grok-build-0.1", manifest_text)
        self.assertNotIn("blinded-all-models-50-case-v2", manifest_text)
        self.assertNotIn("blinded-all-models-50-case-v3", manifest_text)

    def test_hard_gate_renderer_uses_primary_rows_without_quality(self):
        module = load_script()
        rows = six_publication_rows()

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(module, "load_primary_rows", return_value=rows, create=True),
            mock.patch.object(
                module,
                "load_dual_order_rows",
                side_effect=AssertionError("hard-gate renderer loaded quality"),
                create=True,
            ),
            mock.patch.object(
                module,
                "model_rows",
                side_effect=AssertionError("hard-gate renderer used the legacy quality-coupled loader"),
            ),
        ):
            output_dir = Path(tmp)
            module.render_hard_gates_50(Path.cwd(), output_dir)
            self.assertTrue((output_dir / "hard-gates-50.svg").exists())

    def test_coverage_watchlist_uses_primary_rows_without_quality(self):
        module = load_script()
        rows = six_publication_rows()

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(module, "load_primary_rows", return_value=rows, create=True),
            mock.patch.object(
                module,
                "load_dual_order_rows",
                side_effect=AssertionError("coverage watchlist loaded quality"),
                create=True,
            ),
            mock.patch.object(
                module,
                "model_rows",
                side_effect=AssertionError("coverage watchlist used the legacy quality-coupled loader"),
            ),
        ):
            output_dir = Path(tmp)
            module.render_coverage_watchlist(Path.cwd(), output_dir)
            self.assertTrue((output_dir / "coverage-watchlist.svg").exists())

    def test_dual_order_lift_renders_five_winner_buckets_and_same_model_caveat(self):
        module = load_script()
        rows = six_publication_rows()

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(module, "load_publication_rows", return_value=rows, create=True),
            mock.patch.object(module, "model_rows", return_value=rows),
        ):
            output_dir = Path(tmp)
            module.render_empty_current_lift(Path.cwd(), output_dir)
            svg = (output_dir / "empty-current-lift.svg").read_text(encoding="utf-8")

        for bucket_label in [
            "with instructions v4.13",
            "empty instructions",
            "tie",
            "order-sensitive",
            "inconclusive",
        ]:
            with self.subTest(bucket=bucket_label):
                self.assertIn(bucket_label, svg.casefold())
        self.assertIn(SAME_MODEL_JUDGE_CAVEAT, svg)
        self.assertIn(GROK_BUILD_EXCLUSION_CAVEAT, svg)

    def test_dual_order_lift_reserves_long_label_column_without_moving_value_columns(self):
        module = load_script()

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(module, "load_publication_rows", return_value=six_publication_rows()),
        ):
            output_dir = Path(tmp)
            module.render_empty_current_lift(Path.cwd(), output_dir)
            svg = (output_dir / "empty-current-lift.svg").read_text(encoding="utf-8")

        self.assertIn('width="1360" height="744" viewBox="0 0 1360 744"', svg)
        self.assertIn(
            '<text x="72.0" y="458.0" class="label">DeepSeek V4 Flash thinking</text>',
            svg,
        )
        track = re.search(
            r'<rect x="([0-9.]+)" y="180\.0" width="([0-9.]+)" '
            r'height="11\.0" rx="6\.0" fill="#eef2f7"/>',
            svg,
        )
        self.assertIsNotNone(track)
        axis_x = float(track.group(1))
        axis_width = float(track.group(2))
        self.assertGreaterEqual(axis_x, 330)
        self.assertLessEqual(axis_x + axis_width, 550)
        self.assertIn('<text x="570.0" y="144.0" class="axis">Empty -&gt; v4.13</text>', svg)
        self.assertIn('<text x="760.0" y="144.0" class="axis">Dual-order quality verdicts</text>', svg)

    def test_quality_only_renderer_uses_canonical_dual_order_scores_as_paired_progress_bars(self):
        module = load_script()
        rows = six_publication_rows()

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(module, "load_publication_rows", return_value=rows),
            mock.patch.object(
                module,
                "model_rows",
                side_effect=AssertionError("quality progress bars used legacy quality inputs"),
            ),
        ):
            output_dir = Path(tmp)
            module.render_quality_only_comparisons(Path.cwd(), output_dir)
            svg = (output_dir / "quality-only-comparisons.svg").read_text(
                encoding="utf-8"
        )

        self.assertIn("Dual-order quality scores: With instructions v4.13 vs Empty instructions", svg)
        self.assertEqual(len(re.findall(r'<rect [^>]*fill="#be123c"', svg)), 6)
        self.assertEqual(len(re.findall(r'<rect [^>]*fill="#2563eb"', svg)), 6)
        for row in rows:
            score = row["scores"]["all_cases"]
            expected = (
                f"{score['baseline']:.2f} -&gt; {score['current']:.2f} "
                f"({score['delta']:+.2f})"
            )
            with self.subTest(model=row["model_id"]):
                self.assertIn(row["label"], svg)
                self.assertIn(expected, svg)
        self.assertIn(module.BLINDED_DUAL_ORDER_SCOPE, svg)
        self.assertIn(SAME_MODEL_JUDGE_CAVEAT, svg)
        self.assertIn(GROK_BUILD_EXCLUSION_CAVEAT, svg)
        for stale_label in ("OpenHands", "Fable", "External model vs GPT"):
            self.assertNotIn(stale_label, svg)

    def test_absolute_quality_renderer_keeps_progress_bars_and_primary_first(self):
        module = load_script()
        quality = absolute_quality_fixture()
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(module, "load_absolute_quality", return_value=quality, create=True),
        ):
            output_dir = Path(tmp)
            module.render_model_absolute_quality(Path.cwd(), output_dir)
            svg = (output_dir / "model-quality-absolute.svg").read_text(encoding="utf-8")

        self.assertIn("Absolute response quality", svg)
        self.assertIn("Hard gate and Sol absolute score", svg)
        self.assertEqual(len(re.findall(r'<rect [^>]*fill="#2563eb"', svg)), 6)
        self.assertEqual(len(re.findall(r'<rect [^>]*fill="#16a34a"', svg)), 6)
        self.assertLess(svg.index("GPT-5.6 Sol medium"), svg.index("GPT-5.5"))
        self.assertIn("quality among hard-gate-passed responses", svg)
        self.assertIn(module.ABSOLUTE_QUALITY_SCOPE, svg)

    def test_common_case_renderer_draws_all_15_derived_comparisons(self):
        module = load_script()
        quality = absolute_quality_fixture()
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(module, "load_absolute_quality", return_value=quality, create=True),
        ):
            output_dir = Path(tmp)
            module.render_model_common_case_quality(Path.cwd(), output_dir)
            svg = (output_dir / "model-quality-common-cases.svg").read_text(encoding="utf-8")

        self.assertIn("Common-case model quality", svg)
        self.assertEqual(svg.count('data-comparison-row="true"'), 15)
        self.assertIn("derived from saved absolute scores", svg)
        self.assertIn("overlap n", svg)
        self.assertIn(module.ABSOLUTE_QUALITY_SCOPE, svg)

    def test_judge_audit_renderer_shows_paired_bars_and_stability_counts(self):
        module = load_script()
        audit = absolute_audit_fixture()
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(module, "load_absolute_judge_audit", return_value=audit, create=True),
        ):
            output_dir = Path(tmp)
            module.render_model_quality_judge_audit(Path.cwd(), output_dir)
            svg = (output_dir / "model-quality-judge-audit.svg").read_text(encoding="utf-8")

        self.assertIn("Sol vs Terra judge audit", svg)
        self.assertEqual(len(re.findall(r'<rect [^>]*fill="#4f46e5"', svg)), 6)
        self.assertEqual(len(re.findall(r'<rect [^>]*fill="#ea580c"', svg)), 6)
        self.assertIn("15/15 aggregate pair directions stable", svg)
        self.assertIn("15/345 pair-case directions changed", svg)
        self.assertIn(module.ABSOLUTE_JUDGE_AUDIT_SCOPE, svg)

    def test_build_all_emits_exact_seven_readme_svgs(self):
        module = load_script()
        renderer_outputs = {
            "render_hard_gates_50": "hard-gates-50.svg",
            "render_instruction_lift": "instruction-lift.svg",
            "render_empty_current_lift": "empty-current-lift.svg",
            "render_model_gap": "model-gap.svg",
            "render_model_transfer": "model-transfer.svg",
            "render_reference_prompts": "reference-prompts.svg",
            "render_quality_only_comparisons": "quality-only-comparisons.svg",
            "render_model_absolute_quality": "model-quality-absolute.svg",
            "render_model_common_case_quality": "model-quality-common-cases.svg",
            "render_model_quality_judge_audit": "model-quality-judge-audit.svg",
            "render_case_detail_comparisons": "case-detail-comparisons.svg",
            "render_quality_only_case_matrix": "quality-only-case-matrix.svg",
            "render_coverage_watchlist": "coverage-watchlist.svg",
        }

        def svg_writer(name):
            def write(_repo_root, output_dir):
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / name).write_text("<svg/>\n", encoding="utf-8")

            return write

        def png_writer(_repo_root, path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"png")

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            output_dir = root / "readme"
            social_image = root / "social" / "card.png"
            for function_name, output_name in renderer_outputs.items():
                stack.enter_context(
                    mock.patch.object(
                        module,
                        function_name,
                        side_effect=svg_writer(output_name),
                        create=True,
                    )
                )
            stack.enter_context(
                mock.patch.object(module, "render_social_card_png", side_effect=png_writer)
            )

            module.build_all(root, output_dir, social_image)
            actual = {path.name for path in output_dir.glob("*.svg")}

        self.assertEqual(actual, EXPECTED_README_SVGS)

    def test_build_all_removes_only_approved_obsolete_assets_and_converges(self):
        module = load_script()

        def svg_writer(name):
            def write(_repo_root, output_dir):
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / name).write_text("<svg>fresh</svg>\n", encoding="utf-8")

            return write

        def png_writer(_repo_root, path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fresh-png")

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            output_dir = root / "readme"
            social_dir = root / "social"
            social_image = social_dir / "instruction-quality-lift-linkedin.png"
            output_dir.mkdir()
            social_dir.mkdir()
            obsolete_paths = [output_dir / name for name in OBSOLETE_README_SVGS]
            obsolete_paths.append(social_dir / OBSOLETE_SOCIAL_SVG)
            for path in obsolete_paths:
                path.write_text("obsolete\n", encoding="utf-8")
            preserved_paths = [
                output_dir / "unrelated-extra.svg",
                output_dir / "notes.txt",
                social_dir / "unrelated-social.svg",
            ]
            for path in preserved_paths:
                path.write_text("preserve\n", encoding="utf-8")

            for function_name, output_name in {
                "render_hard_gates_50": "hard-gates-50.svg",
                "render_empty_current_lift": "empty-current-lift.svg",
                "render_quality_only_comparisons": "quality-only-comparisons.svg",
                "render_model_absolute_quality": "model-quality-absolute.svg",
                "render_model_common_case_quality": "model-quality-common-cases.svg",
                "render_model_quality_judge_audit": "model-quality-judge-audit.svg",
                "render_coverage_watchlist": "coverage-watchlist.svg",
            }.items():
                stack.enter_context(
                    mock.patch.object(
                        module,
                        function_name,
                        side_effect=svg_writer(output_name),
                    )
                )
            stack.enter_context(
                mock.patch.object(module, "render_social_card_png", side_effect=png_writer)
            )

            module.build_all(root, output_dir, social_image)

            self.assertTrue(all(not path.exists() for path in obsolete_paths))
            self.assertTrue(
                all((output_dir / name).is_file() for name in EXPECTED_README_SVGS)
            )
            self.assertEqual(social_image.read_bytes(), b"fresh-png")
            self.assertTrue(
                all(
                    path.read_text(encoding="utf-8") == "preserve\n"
                    for path in preserved_paths
                )
            )

    def test_snapshot_scope_labels_legacy_pre_blinding_prompt_contamination(self):
        module = load_script()

        self.assertEqual(module.SNAPSHOT_SCOPE, LEGACY_SCOPE)
        self.assertIn(LEGACY_SCOPE, "\n".join(module.footer(1120, 600, "Source: fixture.")))
        self.assertEqual(
            module.SOCIAL_PNG_METADATA["instruction_snapshot_scope"],
            module.BLINDED_DUAL_ORDER_SCOPE,
        )

    def test_current_publication_scopes_mark_pre_semantic_alternative_scorer_snapshot(self):
        module = load_script()
        caveat = "Pre-semantic-alternative scorer snapshot."

        self.assertEqual(module.PRE_SEMANTIC_SCORER_SCOPE, caveat)
        for scope in [
            module.BLINDED_HARD_GATE_SCOPE,
            module.BLINDED_DUAL_ORDER_SCOPE,
            module.SOCIAL_PNG_METADATA["instruction_snapshot_scope"],
        ]:
            self.assertIn(caveat, scope)
        for scope in [module.ABSOLUTE_QUALITY_SCOPE, module.ABSOLUTE_JUDGE_AUDIT_SCOPE]:
            self.assertNotIn(caveat, scope)
            self.assertIn("current-only", scope)
            self.assertIn("v4.14 behavior", scope)
            self.assertIn("163", scope)
        self.assertEqual(module.SOCIAL_PNG_METADATA["instruction_snapshot_models"], "6")
        self.assertEqual(
            module.SOCIAL_PNG_METADATA["instruction_snapshot_aggregation"],
            "dual_order_consensus",
        )
        self.assertEqual(
            module.SOCIAL_PNG_METADATA["instruction_snapshot_judge"],
            "gpt-5.6-sol-medium",
        )

    def test_social_card_uses_six_publication_rows_and_exclusion_caveat_without_legacy_scores(self):
        module = load_script()
        rows = six_publication_rows()

        class FakeImage:
            def save(self, *_args, **_kwargs):
                return None

        class FakeDraw:
            def __init__(self):
                self.text_values = []

            def text(self, _position, value, **_kwargs):
                self.text_values.append(value)

            def rounded_rectangle(self, *_args, **_kwargs):
                return None

            def ellipse(self, *_args, **_kwargs):
                return None

            def line(self, *_args, **_kwargs):
                return None

        fake_draw = FakeDraw()
        with (
            mock.patch.object(module, "load_publication_rows", return_value=rows),
            mock.patch.object(
                module,
                "model_rows",
                side_effect=AssertionError("social card used legacy quality-coupled rows"),
            ),
            mock.patch.object(module, "load_font", return_value=None),
            mock.patch.object(module, "fit_font", return_value=None),
            mock.patch("PIL.Image.new", return_value=FakeImage()),
            mock.patch("PIL.ImageDraw.Draw", return_value=fake_draw),
        ):
            module.render_social_card_png(Path.cwd(), Path("unused-social.png"))

        visible_text = "\n".join(str(value) for value in fake_draw.text_values)
        for row in rows:
            self.assertIn(row["label"], visible_text)
        for expected in [
            "Hard gates",
            "Dual-order consensus",
            "With instructions v4.13",
            "Empty instructions",
            "tie",
            "order-sensitive",
            "inconclusive",
            SAME_MODEL_JUDGE_CAVEAT,
            GROK_BUILD_EXCLUSION_CAVEAT,
            "Six within-runner instruction comparisons",
        ]:
            self.assertIn(expected.casefold(), visible_text.casefold())
        self.assertNotIn("Grok Build 0.1", visible_text)
        for legacy_score_claim in ["Avg quality score", "Average judge score", "Quality delta", "/100"]:
            self.assertNotIn(legacy_score_claim.casefold(), visible_text.casefold())

    def test_social_card_places_table_and_footer_inside_safe_vertical_bands(self):
        module = load_script()

        class FakeImage:
            def save(self, *_args, **_kwargs):
                return None

        class FakeDraw:
            def __init__(self):
                self.rectangles = []
                self.text_calls = []

            def text(self, position, value, **kwargs):
                self.text_calls.append((position, value, kwargs))

            def rounded_rectangle(self, box, **_kwargs):
                self.rectangles.append(box)

        fake_draw = FakeDraw()
        with (
            mock.patch.object(module, "load_publication_rows", return_value=six_publication_rows()),
            mock.patch.object(module, "load_font", return_value=None),
            mock.patch.object(module, "fit_font", return_value=None),
            mock.patch("PIL.Image.new", return_value=FakeImage()),
            mock.patch("PIL.ImageDraw.Draw", return_value=fake_draw),
        ):
            module.render_social_card_png(Path.cwd(), Path("unused-social.png"))

        outer_card = next(box for box in fake_draw.rectangles if box[:2] == (36, 36))
        metric_cards = [box for box in fake_draw.rectangles if box[1] == 250]
        table_panel = next(
            box for box in fake_draw.rectangles if box[0] == 80 and box[2] == 1520
        )
        text_positions = {value: position for position, value, _kwargs in fake_draw.text_calls}
        first_caveat_y = text_positions[SAME_MODEL_JUDGE_CAVEAT][1]
        second_caveat_y = text_positions[GROK_BUILD_EXCLUSION_CAVEAT][1]
        source_y = text_positions[
            "Source: blinded primary summaries and canonical dual-order consensus artifacts; no reference rows."
        ][1]

        self.assertLess(max(box[3] for box in metric_cards), table_panel[1])
        self.assertLess(table_panel[3], first_caveat_y)
        self.assertLess(first_caveat_y, second_caveat_y)
        self.assertLess(second_caveat_y, source_y)
        self.assertLessEqual(source_y + 18, outer_card[3] - 12)

    def test_coverage_watchlist_keeps_backlog_label_clear_of_scope_footer(self):
        module = load_script()
        rows = [
            {
                "short": "GPT",
                "results": [{"case_id": f"case-{index:02d}", "passed": True} for index in range(18)],
            }
        ]

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(module, "model_rows", return_value=rows):
            output_dir = Path(tmp)
            module.render_coverage_watchlist(Path.cwd(), output_dir)
            svg = (output_dir / "coverage-watchlist.svg").read_text(encoding="utf-8")

        label_match = re.search(r'<text x="72\.0" y="([0-9.]+)" class="label">Use this as the concrete backlog;', svg)
        scope_match = re.search(r'<text x="32\.0" y="([0-9.]+)" class="small">Scope:', svg)
        self.assertIsNotNone(label_match)
        self.assertIsNotNone(scope_match)
        label_y = float(label_match.group(1))
        scope_y = float(scope_match.group(1))
        self.assertGreaterEqual(scope_y - label_y, 24)

    def test_compare_svg_dirs_accepts_matching_outputs(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "expected"
            output = root / "output"
            expected.mkdir()
            output.mkdir()
            (expected / "chart.svg").write_text("<svg>fresh</svg>\n", encoding="utf-8")
            (output / "chart.svg").write_text("<svg>fresh</svg>\n", encoding="utf-8")

            self.assertEqual(module.compare_svg_dirs(expected, output), [])

    def test_compare_svg_dirs_reports_missing_stale_and_unexpected_outputs(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "expected"
            output = root / "output"
            expected.mkdir()
            output.mkdir()
            (expected / "stale.svg").write_text("<svg>fresh</svg>\n", encoding="utf-8")
            (expected / "missing.svg").write_text("<svg>fresh</svg>\n", encoding="utf-8")
            (output / "stale.svg").write_text("<svg>old</svg>\n", encoding="utf-8")
            (output / "unexpected.svg").write_text("<svg>extra</svg>\n", encoding="utf-8")

            problems = module.compare_svg_dirs(expected, output)

        self.assertEqual(
            problems,
            [
                f"missing: {output / 'missing.svg'}",
                f"stale: {output / 'stale.svg'}",
                f"unexpected: {output / 'unexpected.svg'}",
            ],
        )


if __name__ == "__main__":
    unittest.main()
