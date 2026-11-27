"""Serve the adopted read-only fixture tools over newline-delimited MCP stdio."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
TOOLS = json.loads((HERE / "tools.json").read_text(encoding="utf-8"))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def append(path, record):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def invoke(checkout, installation, name, args):
    if name == "list_files":
        return {"files": sorted(str(p.relative_to(checkout)) for p in checkout.rglob("*") if p.is_file())}
    if name == "read_file":
        path = (checkout / args["path"]).resolve()
        if checkout not in path.parents or not path.is_file():
            raise ValueError("No such fixture file")
        return {"path": str(path.relative_to(checkout)), "text": path.read_text(encoding="utf-8")}
    if name not in ("run_tests", "run_example"):
        raise ValueError("Unknown fixture tool")
    if args:
        raise ValueError("This tool takes no arguments")
    operation = "installed" if name == "run_tests" else "example"
    process = subprocess.run(
        [sys.executable, "-B", "-I", "-S", HERE / "check.py", checkout, installation, operation],
        cwd=checkout, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, capture_output=True, text=True, timeout=10,
    )
    return {"exit": process.returncode, **json.loads(process.stdout)}


def serve(checkout, installation, ledger):
    for line in sys.stdin:
        request = json.loads(line)
        if "id" not in request:
            continue
        response = {"jsonrpc": "2.0", "id": request["id"]}
        method = request["method"]
        if method == "initialize":
            response["result"] = {
                "protocolVersion": request["params"]["protocolVersion"],
                "capabilities": {"tools": {}}, "serverInfo": {"name": "fixture", "version": "1"},
            }
        elif method == "tools/list":
            response["result"] = {"tools": TOOLS}
            catalog = json.dumps(TOOLS, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            append(ledger / "schemas.jsonl", {"sha256": digest(catalog)})
        elif method == "tools/call":
            params = request["params"]
            name, args = params["name"], params.get("arguments", {})
            try:
                value = invoke(checkout, installation, name, args)
                error = False
            except (KeyError, TypeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
                value, error = {"error": str(exc)}, True
            text = json.dumps(value, ensure_ascii=False)
            append(ledger / "actions.jsonl", {
                "tool": name, "args": args, "result": value if name in ("run_tests", "run_example") or error else None,
                "result_sha256": digest(text), "error": error,
            })
            response["result"] = {"content": [{"type": "text", "text": text}], "isError": error}
        elif method == "ping":
            response["result"] = {}
        elif method in ("resources/list", "resources/templates/list", "prompts/list"):
            field = {"resources/list": "resources", "resources/templates/list": "resourceTemplates", "prompts/list": "prompts"}[method]
            response["result"] = {field: []}
        else:
            response["error"] = {"code": -32601, "message": "Unsupported method"}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("checkout", "installation", "ledger"):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    serve(args.checkout.resolve(), args.installation.resolve(), args.ledger.resolve())
