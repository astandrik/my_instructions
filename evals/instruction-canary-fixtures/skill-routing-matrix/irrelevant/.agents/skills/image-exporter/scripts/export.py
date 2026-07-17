from pathlib import Path


Path("image-exported.marker").write_text("exported\n", encoding="utf-8")
print("IMAGE_EXPORTED")
