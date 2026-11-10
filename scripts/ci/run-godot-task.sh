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
fi

python3 - "$RESULTS_DIR/task.json" "$PROFILE" "$REQUEST_ID" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text())
data.update({"profile": sys.argv[2], "request_id": sys.argv[3], "status": "succeeded"})
path.write_text(json.dumps(data, indent=2) + "\n")
PY
echo "Godot task $REQUEST_ID ($PROFILE) completed successfully."
