#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="4.7.2-stable"
ARCHIVE="Godot_v4.7.2-stable_linux.x86_64.zip"
URL="https://github.com/godotengine/godot/releases/download/4.7.2-stable/Godot_v4.7.2-stable_linux.x86_64.zip"
EXPECTED_SHA256="cadd3204e728a35d3f13adb7fd0d7902636b79f6b95c40c265eb73b6c35329e4"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${ROOT_DIR}/.build/native"
ARCHIVE_PATH="${WORK_DIR}/${ARCHIVE}"
PROJECT_DIR="${ROOT_DIR}/examples/bridge-sandbox"

mkdir -p "${WORK_DIR}"
curl --fail --location --retry 3 --retry-delay 2 --output "${ARCHIVE_PATH}" "${URL}"
echo "${EXPECTED_SHA256}  ${ARCHIVE_PATH}" | sha256sum --check -
unzip -q -o "${ARCHIVE_PATH}" -d "${WORK_DIR}"

GODOT_BIN="$(find "${WORK_DIR}" -maxdepth 2 -type f -name 'Godot_v4.7.2-stable_linux.x86_64' -print -quit)"
if [[ -z "${GODOT_BIN}" ]]; then
  echo "ERROR: Godot Linux binary not found in official archive" >&2
  find "${WORK_DIR}" -maxdepth 2 -type f -print >&2
  exit 1
fi

chmod +x "${GODOT_BIN}"
"${GODOT_BIN}" --headless --editor --path "${PROJECT_DIR}" --quit

echo "Godot ${VERSION} loaded the sandbox project and its enabled editor plugin."
