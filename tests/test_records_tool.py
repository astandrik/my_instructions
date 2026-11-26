import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


EVALS = Path(__file__).resolve().parents[1] / "evals"
SERVER = EVALS / "fixture-mcp" / "records_tool.py"
# Fingerprint advertised by the winning condition in the November 26 evaluation.
EVALUATED_SCHEMA_SHA = "659ac912153afffea28a1e0ab3907bba5dc9dde442cb762791f96317f2b7b572"


def fingerprint(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def exchange(folder, requests, *options):
    messages = [json.dumps({"jsonrpc": "2.0", **request}, ensure_ascii=False) for request in requests]
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(SERVER), str(folder), *options],
        input="\n".join(messages) + "\n", text=True, capture_output=True, check=True, timeout=10,
    )
    return [json.loads(line) for line in result.stdout.splitlines()]


def read_request(request_id, ref):
    return {"id": request_id, "method": "tools/call", "params": {"name": "read_record", "arguments": {"ref": ref}}}


def entries(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class RecordFixtureTests(unittest.TestCase):
    def test_plain_server_advertises_the_evaluated_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "packet.json").write_text("{}", encoding="utf-8")
            initialize, discovery = exchange(folder, [
                {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"method": "notifications/initialized"},
                {"id": 2, "method": "tools/list"},
            ])
            self.assertEqual(initialize["result"]["protocolVersion"], "2025-06-18")
            self.assertEqual(initialize["result"]["serverInfo"]["name"], "packet")
            (schema,) = discovery["result"]["tools"]
            self.assertEqual(schema["name"], "read_record")
            self.assertEqual(fingerprint(schema), EVALUATED_SCHEMA_SHA)
            self.assertEqual(entries(folder / "schema.jsonl"), [{"sha": EVALUATED_SCHEMA_SHA}])
            self.assertFalse((folder / "observations.jsonl").exists())

    def test_packet_checkpoints_and_observation_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            running, done, other = {"stage": "в пути"}, {"stage": "готово"}, {"count": 4}
            packet = folder / "packet.json"
            packet.write_text(json.dumps({"job": [running, done], "count": [other]}), encoding="utf-8")
            original = packet.read_bytes()
            refs = ["job", "count", "absent", [], "job", "job"]
            expected = [running, other, {"status": "unknown reference"}, {"status": "unknown reference"}, done, done]
            replies = exchange(folder, [read_request(i, ref) for i, ref in enumerate(refs)])
            self.assertEqual([r["id"] for r in replies], list(range(len(refs))))
            self.assertEqual([json.loads(r["result"]["content"][0]["text"]) for r in replies], expected)
            self.assertEqual([r["result"]["isError"] for r in replies], [False, False, True, True, False, False])
            rows = entries(folder / "observations.jsonl")
            self.assertEqual([r["answer"] for r in rows], expected)
            self.assertEqual([r["ref"] for r in rows], ["job", "count", "[unknown]", "[unknown]", "job", "job"])
            self.assertEqual([r["sha"] for r in rows], [fingerprint(value) for value in expected])
            self.assertEqual([r["args_sha"] for r in rows], [fingerprint({"ref": ref}) for ref in refs])
            self.assertEqual([r["error"] for r in rows], [r["result"]["isError"] for r in replies])
            (restarted,) = exchange(folder, [read_request(10, "job")])
            self.assertEqual(json.loads(restarted["result"]["content"][0]["text"]), running)
            self.assertEqual(len(entries(folder / "observations.jsonl")), len(refs) + 1)
            self.assertEqual(packet.read_bytes(), original)

    def test_checked_in_cases_expose_only_their_records(self):
        primary = json.loads((EVALS / "read-record-cases.json").read_text(encoding="utf-8"))
        controls = json.loads((EVALS / "section4-read-record-controls.json").read_text(encoding="utf-8"))
        cases = primary + controls["read_record"]
        self.assertEqual((len(primary), len(controls["read_record"])), (9, 2))
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        for case in cases:
            with self.subTest(case=case["id"]), tempfile.TemporaryDirectory() as tmp:
                requests = [{"id": "discovery", "method": "tools/list"}]
                expected = []
                for ref, checkpoints in case["records"].items():
                    for checkpoint in checkpoints:
                        requests.append(read_request(len(requests), ref))
                        expected.append(checkpoint)
                requests.append(read_request(len(requests), "expected"))
                discovery, *replies = exchange(Path(tmp) / "ledger", requests, "--case", case["id"])
                (schema,) = discovery["result"]["tools"]
                self.assertEqual(fingerprint(schema), EVALUATED_SCHEMA_SHA)
                self.assertEqual([json.loads(r["result"]["content"][0]["text"]) for r in replies[:-1]], expected)
                self.assertTrue(all(not r["result"]["isError"] for r in replies[:-1]))
                self.assertTrue(replies[-1]["result"]["isError"])

    def test_invalid_rpc_params_leave_the_next_checkpoint_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "packet.json").write_text('{"job":[{"step":1},{"step":2}]}', encoding="utf-8")
            invalid_call, invalid_init, first_read = exchange(folder, [
                {"id": 1, "method": "tools/call", "params": []},
                {"id": 2, "method": "initialize", "params": {}},
                read_request(3, "job"),
            ])
            self.assertEqual([invalid_call["error"]["code"], invalid_init["error"]["code"]], [-32602, -32602])
            self.assertEqual(json.loads(first_read["result"]["content"][0]["text"]), {"step": 1})
            self.assertEqual(len(entries(folder / "observations.jsonl")), 1)
