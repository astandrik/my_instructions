#!/usr/bin/env python3
"""OpenAI-compatible xAI adapter for instruction evals.

This is intentionally not a general Codex replacement. It implements the small
CLI contract used by scripts/run_instruction_evals.py: read a prompt, call xAI
with a JSON schema, write the final message, and exit with a useful status.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


VERSION = "xai-eval-agent 0.1"
DEFAULT_BASE_URL = "https://api.x.ai/v1"
DEFAULT_TIMEOUT_SECONDS = 300
MAX_ATTEMPTS = 4
RETRY_DELAYS_SECONDS = (1, 2, 4)


def parse_args(argv: list[str]) -> argparse.Namespace:
    if argv and argv[0] == "exec":
        argv = argv[1:]
    parser = argparse.ArgumentParser(description="Run a single xAI structured-output eval turn.")
    parser.add_argument("--version", action="store_true", help="Print adapter version and exit.")
    parser.add_argument("--model", default="grok-4.3", help="xAI model slug.")
    parser.add_argument("-c", "--config", action="append", default=[], help="Ignored Codex-style config override.")
    parser.add_argument("--json", action="store_true", help="Emit minimal JSONL progress events.")
    parser.add_argument("--disable", action="append", default=[], help="Ignored Codex-style feature disable.")
    parser.add_argument("--ephemeral", action="store_true", help="Ignored Codex compatibility flag.")
    parser.add_argument("--ignore-user-config", action="store_true", help="Ignored Codex compatibility flag.")
    parser.add_argument("--skip-git-repo-check", action="store_true", help="Ignored Codex compatibility flag.")
    parser.add_argument("--sandbox", help="Ignored Codex compatibility flag.")
    parser.add_argument("--cd", help="Ignored Codex compatibility flag.")
    parser.add_argument("--output-schema", help="JSON Schema file for the final response.")
    parser.add_argument("--output-last-message", help="File where the final response should be written.")
    parser.add_argument("prompt", nargs="*", help="Prompt text or '-' to read stdin.")
    return parser.parse_args(argv)


def emit_event(enabled: bool, payload: dict[str, Any]) -> None:
    if enabled:
        print(json.dumps(payload, sort_keys=True), flush=True)


def prompt_from_args(prompt_args: list[str]) -> str:
    if prompt_args and prompt_args[0] == "exec":
        prompt_args = prompt_args[1:]
    prompt_parts = [part for part in prompt_args if part != "-"]
    prompt = " ".join(prompt_parts).strip()
    if "-" in prompt_args:
        stdin_prompt = sys.stdin.read()
        if prompt and stdin_prompt:
            return f"{prompt}\n\n<stdin>\n{stdin_prompt}\n</stdin>"
        return stdin_prompt or prompt
    return prompt


def schema_name(path: Path) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", path.stem).strip("_")
    return name or "eval_response"


def build_request_body(*, model: str, prompt: str, schema_path: Path | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Return only a JSON object matching the supplied schema. Do not wrap it in Markdown.",
            },
            {"role": "user", "content": prompt},
        ],
    }
    if schema_path is not None:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name(schema_path),
                "schema": schema,
                "strict": True,
            },
        }
    return body


def extract_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("xAI response does not contain choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ValueError("xAI response choice does not contain message")
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = [item.get("text", "") for item in content if isinstance(item, dict)]
        return "\n".join(text for text in texts if text).strip()
    raise ValueError("xAI response message does not contain text content")


def call_xai(body: dict[str, Any]) -> dict[str, Any]:
    raw_max_attempts = os.environ.get("XAI_MAX_ATTEMPTS", "1")
    try:
        max_attempts = int(raw_max_attempts)
    except ValueError:
        raise ValueError("XAI_MAX_ATTEMPTS must be an integer from 1 through 4") from None
    if not 1 <= max_attempts <= MAX_ATTEMPTS:
        raise ValueError("XAI_MAX_ATTEMPTS must be an integer from 1 through 4")

    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not set")
    base_url = os.environ.get("XAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    timeout = float(os.environ.get("XAI_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except http.client.RemoteDisconnected as exc:
            if attempt == max_attempts:
                raise
            print(
                f"xAI retry attempt {attempt + 1}/{max_attempts} after {type(exc).__name__}",
                file=sys.stderr,
            )
            time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])

    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.version:
        print(VERSION)
        return 0
    if not args.output_last_message:
        print("--output-last-message is required", file=sys.stderr)
        return 2

    output_last_message = Path(args.output_last_message)
    schema_path = Path(args.output_schema) if args.output_schema else None
    prompt = prompt_from_args(args.prompt)
    if not prompt.strip():
        print("prompt is empty", file=sys.stderr)
        return 2

    try:
        emit_event(args.json, {"type": "thread.started", "thread_id": "xai-eval-agent"})
        body = build_request_body(model=args.model, prompt=prompt, schema_path=schema_path)
        response = call_xai(body)
        content = extract_content(response)
        json.loads(content)
        output_last_message.parent.mkdir(parents=True, exist_ok=True)
        output_last_message.write_text(content + "\n", encoding="utf-8")
        emit_event(args.json, {"type": "turn.completed", "model": args.model})
        return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"xAI HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"xAI adapter failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
