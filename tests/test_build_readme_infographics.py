import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_readme_infographics.py"


def load_script():
    spec = importlib.util.spec_from_file_location("build_readme_infographics", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BuildReadmeInfographicsTests(unittest.TestCase):
    def test_compare_svg_dirs_accepts_matching_outputs(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "expected"
            output = root / "output"
            expected.mkdir()
            output.mkdir()
            (expected / "chart.svg").write_text("<svg>fresh</svg>\n", encoding="utf-8")
            (output / "chart.svg").write_text("<svg>fresh</svg>\n", encoding="utf-8")

            self.assertEqual(module.compare_svg_dirs(expected, output), [])

    def test_compare_svg_dirs_reports_missing_stale_and_unexpected_outputs(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "expected"
            output = root / "output"
            expected.mkdir()
            output.mkdir()
            (expected / "stale.svg").write_text("<svg>fresh</svg>\n", encoding="utf-8")
            (expected / "missing.svg").write_text("<svg>fresh</svg>\n", encoding="utf-8")
            (output / "stale.svg").write_text("<svg>old</svg>\n", encoding="utf-8")
            (output / "unexpected.svg").write_text("<svg>extra</svg>\n", encoding="utf-8")

            problems = module.compare_svg_dirs(expected, output)

        self.assertEqual(
            problems,
            [
                f"missing: {output / 'missing.svg'}",
                f"stale: {output / 'stale.svg'}",
                f"unexpected: {output / 'unexpected.svg'}",
            ],
        )


if __name__ == "__main__":
    unittest.main()
