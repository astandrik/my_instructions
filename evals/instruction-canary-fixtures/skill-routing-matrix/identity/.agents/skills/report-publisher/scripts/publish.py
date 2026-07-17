from pathlib import Path


Path("report-published.marker").write_text("published\n", encoding="utf-8")
print("REPORT_PUBLISHED")
