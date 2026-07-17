import json
import sys
from pathlib import Path


path = Path(sys.argv[1])
value = json.loads(path.read_text(encoding="utf-8"))
value["title"] = value.get("title") or "Repaired report"
path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
print("REPORT_REPAIRED")
