import http.client
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "xai_eval_agent.py"


def load_agent():
    spec = importlib.util.spec_from_file_location("xai_eval_agent", SCRIPT_PATH)
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


class XaiEvalAgentTests(unittest.TestCase):
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
            "evidence": ["mocked xai"],
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
            with mock.patch.dict(
                os.environ,
                {"XAI_API_KEY": "test-key", "XAI_MAX_ATTEMPTS": "1"},
                clear=False,
            ):
                with mock.patch.object(agent.urllib.request, "urlopen", side_effect=fake_urlopen):
                    with mock.patch("sys.stdin", io.StringIO("Return a safe no-op response.")):
                        with redirect_stdout(io.StringIO()):
                            status = agent.main(
                                [
                                    "exec",
                                    "--model",
                                    "grok-4.3",
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
            self.assertEqual(captured["url"], "https://api.x.ai/v1/chat/completions")
            self.assertEqual(captured["body"]["model"], "grok-4.3")
            self.assertEqual(captured["body"]["response_format"]["type"], "json_schema")
            self.assertEqual(captured["body"]["response_format"]["json_schema"]["name"], "final_response_schema")
            self.assertEqual(captured["body"]["response_format"]["json_schema"]["schema"]["required"][0], "decision")

    def test_default_remote_disconnect_is_not_retried(self):
        agent = load_agent()

        with mock.patch.dict(os.environ, {"XAI_API_KEY": "test-key"}, clear=True):
            with mock.patch.object(
                agent.urllib.request,
                "urlopen",
                side_effect=http.client.RemoteDisconnected("closed"),
            ) as urlopen:
                with mock.patch("time.sleep") as sleep:
                    with self.assertRaises(http.client.RemoteDisconnected):
                        agent.call_xai({"prompt": "test"})

        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()

    def test_retries_remote_disconnect_with_bounded_delays(self):
        agent = load_agent()
        body = {"prompt": "private prompt marker"}
        response_payload = {"choices": [{"message": {"content": "{}"}}]}
        outcomes = [
            http.client.RemoteDisconnected("first close"),
            http.client.RemoteDisconnected("second close"),
            http.client.RemoteDisconnected("third close"),
            FakeResponse(response_payload),
        ]
        stderr = io.StringIO()

        with mock.patch.dict(
            os.environ,
            {"XAI_API_KEY": "private-key-marker", "XAI_MAX_ATTEMPTS": "4"},
            clear=True,
        ):
            with mock.patch.object(agent.urllib.request, "urlopen", side_effect=outcomes) as urlopen:
                with mock.patch("time.sleep") as sleep:
                    with redirect_stderr(stderr):
                        try:
                            result = agent.call_xai(body)
                        except http.client.RemoteDisconnected:
                            self.fail("call_xai did not retry RemoteDisconnected")

        self.assertEqual(result, response_payload)
        self.assertEqual(urlopen.call_count, 4)
        self.assertEqual(sleep.call_args_list, [mock.call(1), mock.call(2), mock.call(4)])
        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual(
            [request.full_url for request in requests],
            ["https://api.x.ai/v1/chat/completions"] * 4,
        )
        self.assertEqual([request.data for request in requests], [requests[0].data] * 4)
        self.assertEqual(
            stderr.getvalue().splitlines(),
            [
                "xAI retry attempt 2/4 after RemoteDisconnected",
                "xAI retry attempt 3/4 after RemoteDisconnected",
                "xAI retry attempt 4/4 after RemoteDisconnected",
            ],
        )
        self.assertNotIn("private-key-marker", stderr.getvalue())
        self.assertNotIn("private prompt marker", stderr.getvalue())

    def test_stops_after_max_remote_disconnect_attempts(self):
        agent = load_agent()
        outcomes = [http.client.RemoteDisconnected(f"close {attempt}") for attempt in range(1, 5)]

        with mock.patch.dict(
            os.environ,
            {"XAI_API_KEY": "test-key", "XAI_MAX_ATTEMPTS": "4"},
            clear=True,
        ):
            with mock.patch.object(agent.urllib.request, "urlopen", side_effect=outcomes) as urlopen:
                with mock.patch("time.sleep") as sleep:
                    with redirect_stderr(io.StringIO()):
                        with self.assertRaises(http.client.RemoteDisconnected):
                            agent.call_xai({"prompt": "test"})

        self.assertEqual(urlopen.call_count, 4)
        self.assertEqual(sleep.call_args_list, [mock.call(1), mock.call(2), mock.call(4)])

    def test_does_not_retry_http_error(self):
        agent = load_agent()
        error = agent.urllib.error.HTTPError(
            "https://api.x.ai/v1/chat/completions",
            503,
            "Service Unavailable",
            None,
            io.BytesIO(b"unavailable"),
        )
        self.addCleanup(error.close)

        with mock.patch.dict(
            os.environ,
            {"XAI_API_KEY": "test-key", "XAI_MAX_ATTEMPTS": "4"},
            clear=True,
        ):
            with mock.patch.object(agent.urllib.request, "urlopen", side_effect=error) as urlopen:
                with mock.patch("time.sleep") as sleep:
                    with self.assertRaises(agent.urllib.error.HTTPError):
                        agent.call_xai({"prompt": "test"})

        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()

    def test_does_not_retry_other_exceptions(self):
        agent = load_agent()

        with mock.patch.dict(
            os.environ,
            {"XAI_API_KEY": "test-key", "XAI_MAX_ATTEMPTS": "4"},
            clear=True,
        ):
            with mock.patch.object(
                agent.urllib.request,
                "urlopen",
                side_effect=TimeoutError("timed out"),
            ) as urlopen:
                with mock.patch("time.sleep") as sleep:
                    with self.assertRaises(TimeoutError):
                        agent.call_xai({"prompt": "test"})

        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()

    def test_rejects_invalid_max_attempts_before_request(self):
        agent = load_agent()

        for value in ["", "not-an-integer", "1.5", "0", "5", "-1"]:
            with self.subTest(value=value):
                with mock.patch.dict(
                    os.environ,
                    {"XAI_API_KEY": "test-key", "XAI_MAX_ATTEMPTS": value},
                    clear=True,
                ):
                    with mock.patch.object(
                        agent.urllib.request,
                        "urlopen",
                        return_value=FakeResponse({}),
                    ) as urlopen:
                        with self.assertRaises(ValueError):
                            agent.call_xai({"prompt": "test"})

                urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
