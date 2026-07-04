import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "deepseek_eval_agent.py"


def load_agent():
    spec = importlib.util.spec_from_file_location("deepseek_eval_agent", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class DeepSeekEvalAgentTests(unittest.TestCase):
    def test_version(self):
        agent = load_agent()

        with redirect_stdout(io.StringIO()):
            self.assertEqual(agent.main(["--version"]), 0)

    def test_writes_structured_final_message(self):
        agent = load_agent()
        captured = {}

        final_payload = {
            "decision": "no_op",
            "risk_level": "low",
            "summary": "mock ok",
            "evidence": ["mocked deepseek"],
            "actions": [],
        }

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({"choices": [{"message": {"content": json.dumps(final_payload)}}]})

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "final-message.json"
            schema = REPO_ROOT / "evals" / "final-response.schema.json"
            with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=False):
                with mock.patch.object(agent.urllib.request, "urlopen", side_effect=fake_urlopen):
                    with mock.patch("sys.stdin", io.StringIO("Return a safe no-op response.")):
                        with redirect_stdout(io.StringIO()):
                            status = agent.main(
                                [
                                    "exec",
                                    "--model",
                                    "deepseek-v4-flash",
                                    "-c",
                                    'model_reasoning_effort="medium"',
                                    "--json",
                                    "--disable",
                                    "plugins",
                                    "--ephemeral",
                                    "--ignore-user-config",
                                    "--skip-git-repo-check",
                                    "--sandbox",
                                    "read-only",
                                    "--cd",
                                    tmp,
                                    "--output-schema",
                                    str(schema),
                                    "--output-last-message",
                                    str(output),
                                    "-",
                                ]
                            )

            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), final_payload)
            self.assertEqual(captured["url"], "https://api.deepseek.com/chat/completions")
            self.assertEqual(captured["body"]["model"], "deepseek-v4-flash")
            self.assertEqual(captured["body"]["response_format"], {"type": "json_object"})
            self.assertEqual(captured["body"]["thinking"], {"type": "disabled"})
            self.assertIn("JSON Schema", captured["body"]["messages"][0]["content"])
            self.assertEqual(captured["body"]["messages"][1]["content"], "Return a safe no-op response.")


if __name__ == "__main__":
    unittest.main()
