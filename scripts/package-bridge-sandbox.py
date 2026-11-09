#!/usr/bin/env python3
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parents[1]
source = root / "examples" / "bridge-sandbox"
output = root / "public" / "bridge-sandbox.zip"

if not (source / "project.godot").is_file():
    raise SystemExit("ERROR: sandbox project.godot is missing")

output.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(output, "w", ZIP_DEFLATED, compresslevel=8) as archive:
    for path in sorted(source.rglob("*")):
        if path.is_file():
            archive.write(path, Path("bridge-sandbox") / path.relative_to(source))

with ZipFile(output) as archive:
    names = set(archive.namelist())
    required = {
        "bridge-sandbox/project.godot",
        "bridge-sandbox/addons/godot_ai_bridge/plugin.cfg",
        "bridge-sandbox/addons/godot_ai_bridge/plugin.gd",
        "bridge-sandbox/addons/godot_project_sync/plugin.cfg",
        "bridge-sandbox/addons/godot_project_sync/plugin.gd",
        "bridge-sandbox/scenes/main.tscn",
    }
    missing = required - names
    if missing:
        raise SystemExit("ERROR: sandbox package is incomplete: " + ", ".join(sorted(missing)))

project_settings = (source / "project.godot").read_text(encoding="utf-8")
if "res://addons/godot_project_sync/plugin.cfg" not in project_settings:
    raise SystemExit("ERROR: shared project sync plugin is not enabled in the sandbox project")

print(f"Sandbox package ready: {output} ({output.stat().st_size} bytes)")
