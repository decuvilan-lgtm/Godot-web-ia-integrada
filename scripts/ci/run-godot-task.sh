#!/usr/bin/env bash
set -euo pipefail

PROFILE="${GODOT_TASK_PROFILE:-engine_smoke}"
REQUEST_ID="${GODOT_TASK_REQUEST_ID:-manual-run}"
PROJECT_PATH="examples/bridge-sandbox"
GODOT_VERSION="4.7.2"
GODOT_BIN="/tmp/godot/Godot_v${GODOT_VERSION}-stable_linux.x86_64"
RESULTS_DIR="/tmp/godot-task-results"

case "$PROFILE" in
  engine_smoke|scene_audit_3d) ;;
  *) echo "Unsupported Godot task profile: $PROFILE" >&2; exit 2 ;;
esac

if [[ ! "$REQUEST_ID" =~ ^[A-Za-z0-9_-]{8,80}$ && "$REQUEST_ID" != "manual-run" ]]; then
  echo "Invalid task request ID" >&2
  exit 2
fi

mkdir -p "$RESULTS_DIR" /tmp/godot
printf '{"request_id":"%s","profile":"%s","status":"running"}\n' "$REQUEST_ID" "$PROFILE" > "$RESULTS_DIR/task.json"

curl --fail --location --retry 3 --retry-delay 2 \
  --output /tmp/godot-linux.zip \
  "https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}-stable/Godot_v${GODOT_VERSION}-stable_linux.x86_64.zip"
curl --fail --location --retry 3 --retry-delay 2 \
  --output /tmp/SHA512-SUMS.txt \
  "https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}-stable/SHA512-SUMS.txt"
expected="$(awk -v file="Godot_v${GODOT_VERSION}-stable_linux.x86_64.zip" '$2 == file { print $1 }' /tmp/SHA512-SUMS.txt)"
test -n "$expected"
printf '%s  /tmp/godot-linux.zip\n' "$expected" | sha512sum --check -
unzip -q /tmp/godot-linux.zip -d /tmp/godot
chmod +x "$GODOT_BIN"

if [[ ! -f "$PROJECT_PATH/project.godot" ]]; then
  echo "Godot project not found at the fixed sandbox path: $PROJECT_PATH" >&2
  exit 3
fi

set +e
timeout 120 "$GODOT_BIN" --headless --editor --path "$PROJECT_PATH" --quit \
  2>&1 | tee "$RESULTS_DIR/godot-import.log"
IMPORT_STATUS=${PIPESTATUS[0]}
set -e
if [[ "$IMPORT_STATUS" -ne 0 ]]; then
  echo "Godot import/editor validation failed with exit code $IMPORT_STATUS" >&2
  exit "$IMPORT_STATUS"
fi

if grep -E 'SCRIPT ERROR|Parse Error|Failed to load script' "$RESULTS_DIR/godot-import.log"; then
  echo "Godot reported a script or parse error." >&2
  exit 4
fi

if [[ "$PROFILE" == "scene_audit_3d" ]]; then
  set +e
  timeout 120 "$GODOT_BIN" --headless --path "$PROJECT_PATH" \
    --script "$PWD/scripts/ci/scene_audit.gd" \
    2>&1 | tee "$RESULTS_DIR/scene-audit.log"
  AUDIT_STATUS=${PIPESTATUS[0]}
  set -e
  if [[ "$AUDIT_STATUS" -ne 0 ]]; then
    echo "Scene audit failed with exit code $AUDIT_STATUS" >&2
    exit "$AUDIT_STATUS"
  fi
  if [[ ! -f "$RESULTS_DIR/scene-audit.json" ]]; then
    echo "Scene audit did not produce its JSON evidence." >&2
    exit 5
  fi
  python3 - "$RESULTS_DIR/scene-audit.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
summary = report.get("summary", {})
required = {
    "mesh_instance3d_count": 1,
    "camera3d_count": 1,
    "light3d_count": 1,
    "collision_shape3d_count": 2,
    "physics_body3d_count": 2,
    "animation_track_count": 1,
}
missing = [name for name, minimum in required.items() if summary.get(name, 0) < minimum]
if missing:
    raise SystemExit("3D evidence is incomplete: " + ", ".join(missing))
print("3D evidence assertions passed:", json.dumps({k: summary[k] for k in required}))
PY

  if ! command -v xvfb-run >/dev/null 2>&1; then
    echo "xvfb-run is required for deterministic 3D multi-view captures." >&2
    exit 6
  fi
  set +e
  timeout 180 xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 GODOT_SILENCE_ROOT_WARNING=1 \
    "$GODOT_BIN" --path "$PROJECT_PATH" --rendering-method gl_compatibility \
    --script "$PWD/scripts/ci/scene_capture_3d.gd" \
    2>&1 | tee "$RESULTS_DIR/scene-capture.log"
  CAPTURE_STATUS=${PIPESTATUS[0]}
  set -e
  if [[ "$CAPTURE_STATUS" -ne 0 ]]; then
    echo "3D multi-view capture failed with exit code $CAPTURE_STATUS" >&2
    exit "$CAPTURE_STATUS"
  fi
  if [[ ! -s "$RESULTS_DIR/multiview.json" ]]; then
    echo "3D multi-view capture did not produce its evidence manifest." >&2
    exit 7
  fi
  python3 - "$RESULTS_DIR/multiview.json" "$RESULTS_DIR/multiview" <<'PY'
import json, pathlib, struct, sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
root = pathlib.Path(sys.argv[2]).resolve()
captures = manifest.get("captures", [])
expected = manifest.get("captured_scene_count", 0) * manifest.get("view_count_per_scene", 0)
if expected < 1 or len(captures) != expected:
    raise SystemExit(f"Expected {expected} rendered views, found {len(captures)}")
for capture in captures:
    path = pathlib.Path(capture["image"]).resolve()
    if root not in path.parents or not path.is_file():
        raise SystemExit(f"Missing or out-of-directory image: {path.name}")
    data = path.read_bytes()
    if len(data) < 1024 or data[:8] != b"\\x89PNG\\r\\n\\x1a\\n":
        raise SystemExit(f"Invalid or suspiciously small PNG: {path.name}")
    width, height = struct.unpack(">II", data[16:24])
    if (width, height) != (1280, 720):
        raise SystemExit(f"Unexpected dimensions for {path.name}: {width}x{height}")
    if capture.get("bytes") != len(data):
        raise SystemExit(f"Byte-size manifest mismatch for {path.name}")
print(f"Rendered image evidence verified: {len(captures)} PNG views at 1280x720.")
PY
fi

python3 - "$RESULTS_DIR/task.json" "$PROFILE" "$REQUEST_ID" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text())
data.update({"profile": sys.argv[2], "request_id": sys.argv[3], "status": "succeeded"})
path.write_text(json.dumps(data, indent=2) + "\n")
PY
echo "Godot task $REQUEST_ID ($PROFILE) completed successfully."
