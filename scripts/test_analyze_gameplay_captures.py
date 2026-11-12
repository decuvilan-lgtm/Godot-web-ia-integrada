import tempfile
import unittest
from pathlib import Path
from PIL import Image
from scripts.analyze_gameplay_captures import analyze

class GameplayCaptureDiffTests(unittest.TestCase):
    def test_detects_visual_change_but_not_causality(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            Image.new("RGB", (20, 20), "black").save(folder / "gameplay-frame-001-before-action-000.png")
            Image.new("RGB", (20, 20), "white").save(folder / "gameplay-frame-002-after-action-000.png")
            result = analyze(folder)
            self.assertEqual(result["comparison_count"], 1)
            self.assertEqual(result["comparisons"][0]["interpretation"], "visual_change_detected")
            self.assertEqual(result["comparisons"][0]["causality"], "not_established")

    def test_no_pairs_returns_empty_result(self):
        with tempfile.TemporaryDirectory() as temp:
            result = analyze(Path(temp))
            self.assertEqual(result["comparison_count"], 0)

if __name__ == "__main__":
    unittest.main()
