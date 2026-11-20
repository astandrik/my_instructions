"""Run one prepared fixture check in a child interpreter; exit codes are part of the result."""
import json
from pathlib import Path
import runpy
import sys


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check(checkout, installation, operation):
    manifest_path = checkout / "suite.json"
    if not manifest_path.exists():
        if operation == "example":
            return 69, {"phase": "no-example", "message": "No component example is registered"}
        if any(checkout.glob("tests/**/test*.py")):
            raise ValueError("Missing suite.json for a checkout containing tests")
        return 69, {"phase": "no-target", "message": "No local test target in the supplied fixture"}

    manifest = load(manifest_path)
    sample = load(checkout / "sample.json")
    if operation == "example":
        convert = runpy.run_path(str(installation / "example_adapter.py"))["convert"]
        profile = sample["component_profile"]
        return 0, {
            "phase": "component", "revision": sample["revision"], "profile": profile,
            "input": sample["input"], "observed": convert(profile, sample["input"]),
        }

    record = {"revision": manifest["revision"]}
    if manifest["target"] is None:
        return 69, {**record, "phase": "no-target", "message": "No focused target is registered in suite.json"}
    probe = load(installation / "probe.json")
    binding = (installation / probe["runtime_file"]).resolve()
    if installation not in binding.parents:
        raise ValueError("Runtime binding must be inside the fixture installation")
    try:
        profile = binding.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return 78, {**record, "phase": "setup", "message": f"FileNotFoundError: {binding.name} missing before adapter startup"}

    observed = runpy.run_path(str(checkout / "adapter.py"))["convert"](profile, sample["input"])
    record.update(profile=profile, input=sample["input"], observed=observed, expected=probe["expected"])
    if observed != probe["expected"]:
        return 1, {**record, "phase": "product-assertion", "message": "installed adapter output differs from the published contract"}
    return 0, {**record, "phase": "product-pass"}


if __name__ == "__main__":
    exit_code, result = check(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3])
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(exit_code)
