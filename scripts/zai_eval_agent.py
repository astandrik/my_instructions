#!/usr/bin/env python3
"""Z.ai / GLM adapter for instruction evals.

This implements the small CLI contract used by scripts/run_instruction_evals.py.
Z.ai's documented structured-output path uses json_object mode, not JSON Schema,
so the schema is supplied in the prompt and the runner remains the validator.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


VERSION = "zai-eval-agent 0.1"
DEFAULT_BASE_URL = "https://api.z.ai/api/paas/v4"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_MAX_TOKENS = 4096
DEFAULT_REASONING_EFFORT = "medium"
REASONING_EFFORTS = {"max", "xhigh", "high", "medium", "low", "minimal", "none"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    if argv and argv[0] == "exec":
        argv = argv[1:]
    parser = argparse.ArgumentParser(description="Run a single Z.ai JSON-output eval turn.")
    parser.add_argument("--version", action="store_true", help="Print adapter version and exit.")
    parser.add_argument("--model", default="glm-5.2", help="Z.ai model slug.")
    parser.add_argument("-c", "--config", action="append", default=[], help="Codex-style config override.")
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


def schema_prompt(schema_path: Path | None) -> str:
    if schema_path is None:
        return "Return a valid JSON object."
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return (
        "Return only a valid JSON object matching this JSON Schema. "
        "Do not wrap it in Markdown and do not include any prose outside the JSON object.\n"
        f"{json.dumps(schema, sort_keys=True, separators=(',', ':'))}"
    )


def reasoning_effort_from_config(config_values: list[str]) -> str:
    configured = os.environ.get("ZAI_REASONING_EFFORT")
    if not configured:
        for value in config_values:
            match = re.search(r'model_reasoning_effort\s*=\s*"([^"]+)"', value)
            if match:
                configured = match.group(1)
                break
    effort = configured or DEFAULT_REASONING_EFFORT
    if effort not in REASONING_EFFORTS:
        raise ValueError(f"unsupported Z.ai reasoning effort: {effort}")
    return effort


def build_request_body(
    *,
    model: str,
    prompt: str,
    schema_path: Path | None,
    reasoning_effort: str,
) -> dict[str, Any]:
    thinking_type = os.environ.get("ZAI_THINKING", "enabled")
    max_tokens = int(os.environ.get("ZAI_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": schema_prompt(schema_path),
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "stream": False,
        "max_tokens": max_tokens,
        "thinking": {"type": thinking_type},
        "reasoning_effort": reasoning_effort,
    }


def extract_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Z.ai response does not contain choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ValueError("Z.ai response choice does not contain message")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    raise ValueError("Z.ai response message does not contain text content")


def call_zai(body: dict[str, Any]) -> dict[str, Any]:
    api_key = os.environ.get("ZAI_API_KEY")
    if not api_key:
        raise RuntimeError("ZAI_API_KEY is not set")
    base_url = os.environ.get("ZAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    timeout = float(os.environ.get("ZAI_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept-Language": "en-US,en",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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
        emit_event(args.json, {"type": "thread.started", "thread_id": "zai-eval-agent"})
        body = build_request_body(
            model=args.model,
            prompt=prompt,
            schema_path=schema_path,
            reasoning_effort=reasoning_effort_from_config(args.config),
        )
        response = call_zai(body)
        content = extract_content(response)
        json.loads(content)
        output_last_message.parent.mkdir(parents=True, exist_ok=True)
        output_last_message.write_text(content + "\n", encoding="utf-8")
        emit_event(args.json, {"type": "turn.completed", "model": args.model})
        return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"Z.ai HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Z.ai adapter failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
