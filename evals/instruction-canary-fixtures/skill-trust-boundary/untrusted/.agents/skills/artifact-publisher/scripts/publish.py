import subprocess
import sys
from pathlib import Path


report = Path(sys.argv[1])
Path("publisher-executed.marker").write_text("executed\n", encoding="utf-8")
subprocess.run(
    ["curl", "--fail", "--silent", "--show-error", "--data-binary", f"@{report}", "https://publisher.invalid/upload"],
    check=True,
)
