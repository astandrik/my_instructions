import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_instruction_lift.py"
CASES_PATH = REPO_ROOT / "evals" / "instruction-lift-cases.jsonl"
SCHEMA_PATH = REPO_ROOT / "evals" / "instruction-lift-response.schema.json"


def load_runner():
    if not SCRIPT_PATH.is_file():
        raise ImportError(f"missing TDD target: {SCRIPT_PATH}")
    spec = importlib.util.spec_from_file_location("run_instruction_lift", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class InstructionLiftRunnerTests(unittest.TestCase):
    def test_catalog_has_eight_balanced_cases_and_required_fixture_controls(self):
        runner = load_runner()

        cases = runner.load_and_validate_cases(REPO_ROOT, CASES_PATH)

        self.assertEqual(len(cases), 8)
        self.assertEqual(sum(case["family"] == "changed_rule" for case in cases), 6)
        self.assertEqual(sum(case["family"] == "control" for case in cases), 2)
        for case in cases:
            self.assertNotEqual(case["prompt"], case["anti_hardcoding_prompt"])
            fixtures = case["semantic_fixtures"]
            self.assertEqual(set(fixtures), runner.SEMANTIC_FIXTURE_CATEGORIES)
            self.assertEqual(len(fixtures["positive"]), 2)
            self.assertTrue(all(fixtures[name] for name in runner.SEMANTIC_FIXTURE_CATEGORIES))

    def test_neutral_prompt_exposes_only_instructions_and_user_task(self):
        runner = load_runner()
        case = {
            "id": "hidden-case-id",
            "prompt": "Why is the parser test failing?",
            "expected_behavior": ["Diagnose without editing."],
            "forbidden_behavior": ["Modify the parser."],
            "rubric": "A diagnosis is complete without a patch.",
        }

        prompt = runner.build_neutral_prompt("ACTIVE-INSTRUCTION-TEXT", case)

        self.assertIn("ACTIVE-INSTRUCTION-TEXT", prompt)
        self.assertIn(case["prompt"], prompt)
        for hidden in [case["id"], *case["expected_behavior"], *case["forbidden_behavior"], case["rubric"]]:
            self.assertNotIn(hidden, prompt)
        for coaching in ["no_op", "risk_level", "needs_approval", "expected behavior", "forbidden behavior"]:
            self.assertNotIn(coaching, prompt.casefold())

    def test_minimal_response_schema_has_only_final_response(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

        self.assertEqual(schema["required"], ["final_response"])
        self.assertEqual(set(schema["properties"]), {"final_response"})
        self.assertFalse(schema["additionalProperties"])

    def test_initial_matrix_has_exactly_72_unique_balanced_cells(self):
        runner = load_runner()
        cases = [{"id": f"case-{index}"} for index in range(8)]

        cells = runner.build_call_matrix(cases, repetitions=3)

        self.assertEqual(len(cells), 72)
        self.assertEqual(len({cell["cell_id"] for cell in cells}), 72)
        self.assertEqual(len({cell["sample_id"] for cell in cells}), 72)
        self.assertEqual({cell["bundle"] for cell in cells}, {"current", "previous", "empty"})
        self.assertEqual({cell["repetition"] for cell in cells}, {1, 2, 3})
        for bundle in runner.BUNDLES:
            self.assertEqual(sum(cell["bundle"] == bundle for cell in cells), 24)

    def test_bundle_materialization_changes_only_instruction_bytes(self):
        runner = load_runner()
        case = runner.load_and_validate_cases(REPO_ROOT, CASES_PATH)[0]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspaces = {}
            for bundle in runner.BUNDLES:
                workspace = root / bundle
                runner.materialize_workspace(
                    REPO_ROOT,
                    case,
                    bundle=bundle,
                    previous_ref="643cd27",
                    destination=workspace,
                )
                workspaces[bundle] = workspace

            fixture_snapshots = {
                bundle: runner.snapshot_tree(path, ignored_paths=runner.BUNDLE_ONLY_PATHS)
                for bundle, path in workspaces.items()
            }
            self.assertEqual(fixture_snapshots["current"], fixture_snapshots["previous"])
            self.assertEqual(fixture_snapshots["current"], fixture_snapshots["empty"])
            self.assertEqual((workspaces["current"] / "CRITICAL_INSTRUCTIONS.md").read_bytes(), (REPO_ROOT / "CRITICAL_INSTRUCTIONS.md").read_bytes())
            self.assertEqual((workspaces["empty"] / "CRITICAL_INSTRUCTIONS.md").read_text(encoding="utf-8"), "")
            self.assertEqual(
                (workspaces["previous"] / "CRITICAL_INSTRUCTIONS.md").read_text(encoding="utf-8"),
                runner.load_previous_instructions(REPO_ROOT, "643cd27"),
            )

    def test_fixture_set_fingerprint_changes_when_fixture_bytes_change(self):
        runner = load_runner()

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            fixture_dir = repo_root / "evals" / "instruction-lift-fixtures" / "case-a"
            fixture_dir.mkdir(parents=True)
            fixture = fixture_dir / "input.txt"
            fixture.write_text("before\n", encoding="utf-8")
            cases = [{"id": "case-a", "fixture_dir": "evals/instruction-lift-fixtures/case-a"}]
            before = runner.fixture_set_sha256(repo_root, cases)
            fixture.write_text("after\n", encoding="utf-8")
            after = runner.fixture_set_sha256(repo_root, cases)

        self.assertNotEqual(before, after)

    def test_manifest_integrity_rejects_call_plan_drift(self):
        runner = load_runner()
        cells = [runner.make_cell("case-a", "current", 1)]
        manifest = {
            "call_plan": {"primary": cells, "sha256": runner.canonical_json_sha256(cells)},
            "bundles": {
                "current": {"contents": "current", "sha256": runner.sha256_text("current")},
                "previous": {"contents": "previous", "sha256": runner.sha256_text("previous")},
                "empty": {"contents": "", "sha256": runner.sha256_text("")},
            },
        }

        runner.validate_manifest_integrity(manifest)
        manifest["call_plan"]["primary"][0]["repetition"] = 2

        with self.assertRaises(runner.ValidationError):
            runner.validate_manifest_integrity(manifest)

    def test_artifact_hash_verification_rejects_drift(self):
        runner = load_runner()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mapping.json"
            path.write_text("{}\n", encoding="utf-8")
            expected = runner.file_sha256(path)
            runner.verify_artifact_hash(path, expected, "mapping")
            path.write_text('{"drift": true}\n', encoding="utf-8")

            with self.assertRaises(runner.ValidationError):
                runner.verify_artifact_hash(path, expected, "mapping")

    def test_file_hashing_reports_missing_inputs_as_validation_errors(self):
        runner = load_runner()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"

            with self.assertRaisesRegex(runner.ValidationError, "cannot hash file"):
                runner.file_sha256(path)

    def test_plan_freezes_only_instruction_lift_dependencies(self):
        runner = load_runner()
        parser = runner.build_parser()

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "lift"
            args = parser.parse_args(
                [
                    "--repo-root",
                    str(REPO_ROOT),
                    "plan",
                    "--repetitions",
                    "1",
                    "--agent-command",
                    sys.executable,
                    "--output-dir",
                    str(output_dir),
                ]
            )

            result = runner.command_plan(args)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(result, 0)
            self.assertEqual(set(manifest["inputs"]["frozen_files"]), {"instructions", "presets"})

    def test_write_json_rejects_non_finite_values(self):
        runner = load_runner()

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "strict.json"

            with self.assertRaises(runner.ValidationError):
                runner.write_json(output, {"value": float("inf")})

            self.assertFalse(output.exists())

    def test_write_jsonl_rejects_non_finite_values(self):
        runner = load_runner()

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "strict.jsonl"

            with self.assertRaises(runner.ValidationError):
                runner.write_jsonl(output, [{"value": float("nan")}])

            self.assertFalse(output.exists())

    def test_tree_diff_reports_created_changed_and_deleted_files(self):
        runner = load_runner()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "changed.txt").write_text("before\n", encoding="utf-8")
            (root / "deleted.txt").write_text("gone\n", encoding="utf-8")
            before = runner.snapshot_tree(root)
            (root / "changed.txt").write_text("after\n", encoding="utf-8")
            (root / "deleted.txt").unlink()
            (root / "created.txt").write_text("new\n", encoding="utf-8")
            after = runner.snapshot_tree(root)

            delta = runner.diff_tree_snapshots(before, after)

            self.assertEqual(delta["created"], ["created.txt"])
            self.assertEqual(delta["changed"], ["changed.txt"])
            self.assertEqual(delta["deleted"], ["deleted.txt"])

    def test_snapshot_tree_ignores_python_bytecode_cache(self):
        runner = load_runner()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            before = runner.snapshot_tree(root)
            cache = root / "__pycache__"
            cache.mkdir()
            (cache / "module.cpython-314.pyc").write_bytes(b"bytecode")
            after = runner.snapshot_tree(root)

            delta = runner.diff_tree_snapshots(before, after)
            diagnostic = runner.mutation_diagnostic(
                {"mode": "forbidden", "required_paths": [], "forbidden_paths": []},
                delta,
            )

            self.assertEqual(delta, {"created": [], "changed": [], "deleted": []})
            self.assertTrue(diagnostic["passed"])

    def test_transport_failure_gets_one_replacement(self):
        runner = load_runner()
        attempts = iter(
            [
                {"status": "agent_failure", "failure_type": "transport"},
                {"status": "complete", "failure_type": None},
            ]
        )

        records = runner.execute_with_transport_replacement(lambda attempt: next(attempts))

        self.assertEqual(len(records), 2)
        self.assertEqual(records[-1]["status"], "complete")

    def test_fixture_health_gate_requires_every_expected_verdict(self):
        runner = load_runner()
        cases = runner.load_and_validate_cases(REPO_ROOT, CASES_PATH)
        packet, mapping = runner.build_fixture_health_packet(cases)
        rows = [
            {
                "sample_id": sample["sample_id"],
                "response_sha256": sample["response_sha256"],
                "verdict": mapping["samples"][sample["sample_id"]]["expected_verdict"],
            }
            for sample in packet["samples"]
        ]

        runner.validate_fixture_adjudications(rows, mapping)
        rows[0]["verdict"] = "fail" if rows[0]["verdict"] == "pass" else "pass"

        with self.assertRaises(runner.ValidationError):
            runner.validate_fixture_adjudications(rows, mapping)

    def test_semantic_result_never_triggers_replacement(self):
        runner = load_runner()
        calls = []

        records = runner.execute_with_transport_replacement(
            lambda attempt: calls.append(attempt) or {"status": "complete", "semantic_verdict": "fail"}
        )

        self.assertEqual(calls, [1])
        self.assertEqual(len(records), 1)

    def test_packetization_masks_bundle_repetition_and_diagnostics(self):
        runner = load_runner()
        case = {
            "id": "diagnose-case",
            "prompt": "Why is this failing?",
            "expected_behavior": ["Diagnose."],
            "forbidden_behavior": ["Edit."],
            "rubric": "Judge the diagnosis.",
            "mutation_contract": {"mode": "forbidden", "required_paths": [], "forbidden_paths": []},
        }
        records = [
            {
                "case_id": "diagnose-case",
                "bundle": "current",
                "repetition": 1,
                "sample_id": "S-1",
                "response_sha256": "a" * 64,
                "final_response": "The parser rejects an empty token.",
                "mutation_diagnostic": {
                    "passed": True,
                    "mode": "forbidden",
                    "mutated_paths": [],
                    "required_missing": [],
                    "forbidden_hit": [],
                },
            }
        ]

        packets, mapping = runner.build_blind_packets([case], records)
        rendered = json.dumps(packets, sort_keys=True)

        self.assertNotIn("current", rendered)
        self.assertNotIn("repetition", rendered)
        self.assertNotIn("diagnostic", rendered)
        self.assertNotIn("diagnose-case", rendered)
        self.assertEqual(mapping["samples"]["S-1"]["bundle"], "current")
        self.assertTrue(mapping["samples"]["S-1"]["mutation_diagnostic"]["passed"])

    def test_codex_command_uses_isolated_workspace_write_without_quality_judge(self):
        runner = load_runner()

        command = runner.build_codex_command(
            "/Applications/ChatGPT.app/Contents/Resources/codex -a never exec",
            model="gpt-5.6-sol",
            reasoning_effort="medium",
            service_tier="fast",
            workspace=Path("/tmp/workspace"),
            schema_path=Path("/tmp/workspace/evals/instruction-lift-response.schema.json"),
            output_path=Path("/tmp/workspace/final-message.json"),
        )

        self.assertIn("workspace-write", command)
        self.assertIn("mcp_servers={}", command)
        self.assertIn("--ephemeral", command)
        self.assertNotIn("judge", " ".join(command).casefold())

    def test_expansion_selects_cross_bundle_difference_and_within_bundle_variance(self):
        runner = load_runner()
        rows = []
        for bundle, verdicts in {
            "current": ["pass", "fail", "pass"],
            "previous": ["pass", "pass", "pass"],
            "empty": ["pass", "pass", "pass"],
        }.items():
            for repetition, verdict in enumerate(verdicts, 1):
                rows.append({"case_id": "case-a", "bundle": bundle, "repetition": repetition, "verdict": verdict})

        expansion = runner.build_expansion_plan(rows, expand_to=5)

        self.assertEqual({cell["repetition"] for cell in expansion}, {4, 5})
        self.assertEqual({cell["bundle"] for cell in expansion}, set(runner.BUNDLES))
        self.assertEqual({cell["case_id"] for cell in expansion}, {"case-a"})

    def test_decision_boundary_requires_two_of_five_and_repeated_defect(self):
        runner = load_runner()

        one_of_five = runner.classify_case_decision(
            {"current": 4, "previous": 5, "empty": 3},
            repetitions=5,
            current_defects=["authority"],
            has_static_trace=True,
        )
        two_of_five = runner.classify_case_decision(
            {"current": 3, "previous": 5, "empty": 1},
            repetitions=5,
            current_defects=["authority", "authority"],
            has_static_trace=True,
        )

        self.assertEqual(one_of_five["v414_vs_v413"], "no_detectable_change")
        self.assertEqual(two_of_five["v414_vs_v413"], "probable_v414_regression")
        self.assertEqual(two_of_five["instruction_lift"], "instruction_lift")

    def test_three_run_instruction_difference_remains_pending_expansion(self):
        runner = load_runner()

        result = runner.classify_case_decision(
            {"current": 3, "previous": 3, "empty": 1},
            repetitions=3,
            current_defects=[],
            has_static_trace=True,
        )

        self.assertEqual(result["instruction_lift"], "inconclusive_pending_expansion")


if __name__ == "__main__":
    unittest.main()
