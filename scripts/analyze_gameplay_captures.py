#!/usr/bin/env python3
"""Compare before/after gameplay screenshots without claiming causal input success."""
import json
import sys
from pathlib import Path
from PIL import Image, ImageChops, ImageStat

def compare(before_path, after_path, threshold=12):
    with Image.open(before_path).convert("RGB") as before, Image.open(after_path).convert("RGB") as after:
        if before.size != after.size:
            after = after.resize(before.size)
        diff = ImageChops.difference(before, after)
        stat = ImageStat.Stat(diff)
        mean_absolute_difference = sum(stat.mean) / 3
        histogram = diff.convert("L").histogram()
        total = sum(histogram)
        changed = sum(histogram[threshold + 1:])
        return {
            "before": str(before_path),
            "after": str(after_path),
            "width": before.width,
            "height": before.height,
            "mean_absolute_pixel_difference": round(mean_absolute_difference, 4),
            "changed_pixel_fraction": round(changed / total, 6) if total else 0,
            "threshold": threshold,
            "interpretation": "visual_change_detected" if changed / total > 0.005 else "no_significant_visual_change"
        }

def analyze(directory):
    directory = Path(directory)
    pairs = {}
    for path in directory.glob("gameplay-frame-*-before-action-*.png"):
        key = path.name.split("-before-action-")[-1].removesuffix(".png")
        pairs.setdefault(key, {})["before"] = path
    for path in directory.glob("gameplay-frame-*-after-action-*.png"):
        key = path.name.split("-after-action-")[-1].removesuffix(".png")
        pairs.setdefault(key, {})["after"] = path
    results = []
    for key in sorted(pairs):
        pair = pairs[key]
        if "before" in pair and "after" in pair:
            result = compare(pair["before"], pair["after"])
            result["action_index"] = int(key)
            result["causality"] = "not_established"
            results.append(result)
    return {
        "format": "gameplay-visual-diff",
        "version": 1,
        "comparison_count": len(results),
        "comparisons": results,
        "limitations": "A visual difference may come from animation, timers, camera movement, or other game activity. It does not prove the requested input caused the change."
    }

if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "artifacts"
    output = analyze(folder)
    Path(folder, "gameplay-visual-diff.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
