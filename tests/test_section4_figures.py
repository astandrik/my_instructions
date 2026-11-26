import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_readme_infographics.py"
SOURCE = ROOT / "evals/RESULTS.md"
OUTPUT = Path("docs/assets/readme/section4-read-record")
sys.path.insert(0, str(SCRIPT.parent))
import section4_figures


class Section4FigureTests(unittest.TestCase):
    def test_published_figures_match_their_controlled_comparisons(self):
        study = section4_figures.load_study(ROOT)
        original, updated = map(study.combined, ("Original", "Updated"))
        self.assertEqual((original.extra, updated.extra), (28, 5))
        self.assertEqual(original.correct, updated.correct)
        self.assertEqual(original.correct, (18, 18))
        self.assertEqual(original.required, updated.required)
        self.assertEqual(original.required, (12, 12))
        self.assertEqual((original.tokens, updated.tokens), (1_025_116, 1_053_107))
        self.assertEqual(tuple(s.delta for s in study.panels["Formal gate"]), (2, -4))
        self.assertEqual(tuple(s.delta for s in study.panels["Adjudicated outcome"]), (1, 0))
        self.assertEqual(tuple(s.delta for s in study.panels["Canary oracle"]), (1, -1))

        for name in ("record-reads.svg", "section4-regression.svg"):
            root = ET.parse(ROOT / OUTPUT / name).getroot()
            self.assertEqual(root.attrib["aria-labelledby"], "title desc")
            self.assertTrue(root.find("{*}title").text)
            self.assertTrue(root.find("{*}desc").text)
            self.assertIn(f"../{OUTPUT}/{name}", SOURCE.read_text(encoding="utf-8"))
        with Image.open(ROOT / OUTPUT / "overview.png") as card:
            self.assertEqual(card.size, (1200, 630))
            self.assertIn("evals/RESULTS.md", card.info["Source"])
        self.assertIn(str(OUTPUT / "overview.png"), (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_clean_checkout_build_and_check_detect_changes_in_both_experiments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evals").mkdir()
            source = root / "evals/RESULTS.md"
            published = SOURCE.read_text(encoding="utf-8")
            source.write_text(published, encoding="utf-8")
            command = [sys.executable, "-B", str(SCRIPT), "--section4-only"]
            subprocess.run(command, cwd=root, check=True, capture_output=True)
            subprocess.run(command + ["--check"], cwd=root, check=True, capture_output=True)
            self.assertFalse((root / ".eval-results").exists())

            changed = published.replace("| 2 | 1 | 9 | 589,442 |", "| 3 | 1 | 10 | 589,442 |")
            changed = changed.replace("22/50 → 18/50", "22/50 → 20/50")
            source.write_text(changed, encoding="utf-8")
            check = subprocess.run(command + ["--check"], cwd=root, text=True, capture_output=True)
            self.assertEqual(check.returncode, 1)
            for name in ("record-reads.svg", "section4-regression.svg", "overview.png"):
                self.assertIn("stale:", check.stderr)
                self.assertIn(name, check.stderr)
            subprocess.run(command, cwd=root, check=True, capture_output=True)
            self.assertIn("from 28 to 6", (root / OUTPUT / "record-reads.svg").read_text(encoding="utf-8"))
            self.assertIn("22/50 → 20/50", (root / OUTPUT / "section4-regression.svg").read_text(encoding="utf-8"))
            subprocess.run(command + ["--check"], cwd=root, check=True, capture_output=True)

    def test_inconsistent_record_counts_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evals").mkdir()
            bad = SOURCE.read_text(encoding="utf-8").replace("| 2 | 1 | 9 | 589,442 |", "| 3 | 1 | 9 | 589,442 |")
            (root / "evals/RESULTS.md").write_text(bad, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inconsistent"):
                section4_figures.load_study(root)
