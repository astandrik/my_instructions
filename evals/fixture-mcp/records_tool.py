"""Serve the read_record tool for a synthetic work packet over MCP stdio."""

import argparse
import hashlib
import json
from pathlib import Path
import sys


EVALS_DIR = Path(__file__).resolve().parents[1]
SCHEMA = {
    "name": "read_record",
    "description": (
        "Read a named record in the supplied work packet. "
        "Start with the record that can establish the requested state. "
        "Read an additional record when it could change the answer, is needed "
        "to interpret another record, or the user requests it. "
        "When the supplied evidence already settles the question, answer directly. "
        "If a required check is unavailable and no remaining record can change "
        "the conclusion, answer immediately. "
        "Re-reading a job board returns the next available checkpoint, if any."
    ),
    "annotations": {"readOnlyHint": True},
    "inputSchema": {
        "type": "object",
        "properties": {"ref": {"type": "string", "description": "Record reference from the work packet."}},
        "required": ["ref"],
        "additionalProperties": False,
    },
}
EMPTY_RESULTS = {
    "ping": {},
    "resources/list": {"resources": []},
    "resources/templates/list": {"resourceTemplates": []},
    "prompts/list": {"prompts": []},
}


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def append(path, entry):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get(records, visits, ref):
    if not isinstance(ref, str) or ref not in records:
        return {"status": "unknown reference"}, True
    checkpoints = records[ref]
    index = visits.get(ref, 0)
    visits[ref] = index + 1
    return checkpoints[min(index, len(checkpoints) - 1)], False


def call(params, records, visits, folder):
    name = params.get("name")
    arguments = params.get("arguments", {})
    ref = arguments.get("ref") if isinstance(arguments, dict) else None
    if name == SCHEMA["name"]:
        answer, error = get(records, visits, ref)
    else:
        answer, error = {"status": "unknown operation"}, True
    text = pack(answer)
    append(folder / "observations.jsonl", {
        "tool": name,
        "ref": ref if isinstance(ref, str) and ref in records else "[unknown]",
        "args_sha": digest(pack(arguments)),
        "answer": answer,
        "sha": digest(text),
        "error": error,
    })
    return {"content": [{"type": "text", "text": text}], "isError": error}


def case_records(case_id):
    primary = json.loads((EVALS_DIR / "read-record-cases.json").read_text(encoding="utf-8"))
    controls = json.loads((EVALS_DIR / "section4-read-record-controls.json").read_text(encoding="utf-8"))
    for case in primary + controls["read_record"]:
        if case["id"] == case_id:
            return case["records"]
    raise ValueError(f"unknown read_record case: {case_id}")


def rpc_error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_request(request, folder, records, visits):
    if not isinstance(request, dict) or not isinstance(request.get("method"), str):
        return rpc_error(None, -32600, "invalid request")
    if "id" not in request:
        return None
    request_id = request["id"]
    method = request["method"]
    params = request.get("params", {})
    if not isinstance(params, dict):
        return rpc_error(request_id, -32602, "invalid params")
    if method == "initialize":
        if not isinstance(params.get("protocolVersion"), str):
            return rpc_error(request_id, -32602, "missing protocol version")
        result = {
            "protocolVersion": params["protocolVersion"],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "packet", "version": "1"},
        }
    elif method == "tools/list":
        append(folder / "schema.jsonl", {"sha": digest(pack(SCHEMA))})
        result = {"tools": [SCHEMA]}
    elif method == "tools/call":
        result = call(params, records, visits, folder)
    elif method in EMPTY_RESULTS:
        result = EMPTY_RESULTS[method]
    else:
        return rpc_error(request_id, -32601, "unsupported method")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve(folder, records=None):
    if records is None:
        records = json.loads((folder / "packet.json").read_text(encoding="utf-8"))
    if not isinstance(records, dict) or any(not isinstance(deck, list) or not deck for deck in records.values()):
        raise ValueError("a packet must map each reference to a non-empty list of checkpoints")
    folder.mkdir(parents=True, exist_ok=True)
    visits = {}
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response = rpc_error(None, -32700, "parse error")
        else:
            response = handle_request(request, folder, records, visits)
        if response is not None:
            print(json.dumps(response), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="packet and observation directory for this session")
    parser.add_argument("--case", help="use a checked-in acceptance or two-source case instead of packet.json")
    args = parser.parse_args()
    try:
        serve(args.folder, case_records(args.case) if args.case is not None else None)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"{parser.prog}: {exc}\n")
