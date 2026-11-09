#!/usr/bin/env python3
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import sys

ROOT = Path(__file__).resolve().parents[1] / "public"
ENTRY = ROOT / "index.html"

class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ("src", "href"):
            value = attrs.get(key)
            if not value:
                continue
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc or value.startswith(("#", "data:", "blob:")):
                continue
            path = parsed.path
            if path:
                self.paths.append(path)

def fail(message):
    print(f"VERIFY ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)

if not ENTRY.is_file() or ENTRY.stat().st_size == 0:
    fail("public/index.html is missing or empty")

sandbox_zip = ROOT / "bridge-sandbox.zip"
if not sandbox_zip.is_file() or sandbox_zip.stat().st_size == 0:
    fail("bridge-sandbox.zip is missing or empty")

from zipfile import ZipFile
with ZipFile(sandbox_zip) as archive:
    required = {
        "bridge-sandbox/project.godot",
        "bridge-sandbox/addons/godot_ai_bridge/plugin.gd",
        "bridge-sandbox/addons/godot_project_sync/plugin.cfg",
        "bridge-sandbox/addons/godot_project_sync/plugin.gd",
        "bridge-sandbox/scenes/main.tscn",
    }
    missing_sandbox_files = required - set(archive.namelist())
    if missing_sandbox_files:
        fail("sandbox package is missing: " + ", ".join(sorted(missing_sandbox_files)))
    project_text = archive.read("bridge-sandbox/project.godot").decode("utf-8")
    if "res://addons/godot_project_sync/plugin.cfg" not in project_text:
        fail("shared project sync plugin is not enabled in the sandbox project")

wasm = list(ROOT.rglob("*.wasm"))
js = list(ROOT.rglob("*.js"))
if not wasm:
    fail("no WebAssembly module was found")
if not js:
    fail("no JavaScript runtime was found")

html_text = ENTRY.read_text(encoding="utf-8", errors="replace")
if 'name="viewport"' not in html_text.lower():
    fail("mobile viewport metadata is missing")

parser = AssetParser()
parser.feed(ENTRY.read_text(encoding="utf-8", errors="replace"))

missing = []
for asset in parser.paths:
    candidate = (ROOT / asset.lstrip("/")).resolve()
    if not candidate.is_relative_to(ROOT.resolve()):
        fail(f"entry point references a path outside the published directory: {asset}")
    if not candidate.exists():
        missing.append(asset)

if missing:
    fail("missing local HTML assets: " + ", ".join(sorted(set(missing))))

print(f"Verified entry point: {ENTRY}")
print(f"WebAssembly modules: {len(wasm)}")
print(f"JavaScript files: {len(js)}")
print(f"Local HTML references checked: {len(parser.paths)}")
print("Static bundle structure: OK")
