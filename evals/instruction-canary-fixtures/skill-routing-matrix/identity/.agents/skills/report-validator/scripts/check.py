import json
import sys
from pathlib import Path


value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
valid = bool(value.get("title")) and bool(value.get("items"))
print("VALID_REPORT" if valid else "INVALID_REPORT")
raise SystemExit(0 if valid else 1)
