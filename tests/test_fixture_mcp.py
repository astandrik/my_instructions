"""Wire contract of the read-only Sol/Astra evaluation fixture."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SERVER = Path(__file__).resolve().parents[1] / "evals" / "fixture-mcp" / "server.py"


class FixtureToolTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.checkout, self.installation, self.ledger = (
            Path(tmp.name) / name for name in ("checkout", "installation", "ledger")
        )
        for directory in (self.checkout, self.installation, self.ledger):
            directory.mkdir()

    def exchange(self, *requests):
        messages = [
            {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "fixture-test", "version": "1"},
            }},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
        ]
        messages.extend(
            {"jsonrpc": "2.0", "id": i, "method": method, "params": params}
            for i, (method, params) in enumerate(requests, 1)
        )
        result = subprocess.run(
            [sys.executable, "-I", "-B", SERVER, self.checkout, self.installation, self.ledger],
            input="".join(json.dumps(message) + "\n" for message in messages),
            text=True, capture_output=True, check=True, timeout=10,
        )
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([r["id"] for r in replies], list(range(len(requests) + 1)))
        self.assertIn("tools", replies[0]["result"]["capabilities"])
        return [reply["result"] for reply in replies[1:]]

    def test_listing_advises_when_to_verify_only_on_run_tests(self):
        listing, = self.exchange(("tools/list", {}))
        tools = {tool["name"]: tool for tool in listing["tools"]}
        self.assertEqual(set(tools), {"list_files", "read_file", "run_tests", "run_example"})
        self.assertIn("if its result could change the recommendation or the user requested execution",
                      tools["run_tests"]["description"])
        self.assertIn("cite it and identify the check for implementation", tools["run_tests"]["description"])
        self.assertNotIn("recommendation", tools["run_example"]["description"])
        self.assertEqual(tools["run_tests"]["inputSchema"]["properties"], {})

    def test_installed_test_and_recorded_example_report_their_own_results(self):
        adapter = "def convert(profile, value):\n    return value.strip() if profile == 'trim' else value\n"
        (self.checkout / "adapter.py").write_text(adapter)
        (self.installation / "example_adapter.py").write_text(adapter)
        (self.checkout / "suite.json").write_text('{"revision":"r2","target":"focused"}')
        (self.checkout / "sample.json").write_text(
            '{"revision":"r1","component_profile":"trim","input":" x "}'
        )
        (self.installation / "probe.json").write_text('{"runtime_file":"mode","expected":"x"}')
        binding = self.installation / "mode"
        call_test = ("tools/call", {"name": "run_tests", "arguments": {}})
        call_example = ("tools/call", {"name": "run_example", "arguments": {}})

        def observed(reply):
            self.assertFalse(reply["isError"])
            return json.loads(reply["content"][0]["text"])

        blocked, = self.exchange(call_test)
        self.assertEqual(observed(blocked)["phase"], "setup")
        binding.write_text("verbatim")
        failed, example = map(observed, self.exchange(call_test, call_example))
        self.assertEqual((failed["exit"], failed["revision"], failed["observed"]), (1, "r2", " x "))
        self.assertEqual((example["exit"], example["revision"], example["observed"]), (0, "r1", "x"))
        binding.write_text("trim")
        success, = self.exchange(call_test)
        self.assertEqual(observed(success)["phase"], "product-pass")
        (self.checkout / "suite.json").write_text('{"revision":"r2","target":null}')
        missing, = self.exchange(call_test)
        self.assertEqual((observed(missing)["exit"], observed(missing)["phase"]), (69, "no-target"))
