#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="4.7.2-stable"
ARCHIVE="Godot_v4.7.2-stable_web_editor.zip"
URL="https://github.com/godotengine/godot/releases/download/4.7.2-stable/Godot_v4.7.2-stable_web_editor.zip"
EXPECTED_SHA256="5e6904f3b8b6ac642a3ad3893396427c3a31581e5345a3fdc93b3c64575232a4"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${ROOT_DIR}/.build"
PUBLIC_DIR="${ROOT_DIR}/public"
ARCHIVE_PATH="${WORK_DIR}/${ARCHIVE}"

command -v curl >/dev/null 2>&1 || { echo "ERROR: curl is required" >&2; exit 1; }
command -v unzip >/dev/null 2>&1 || { echo "ERROR: unzip is required" >&2; exit 1; }
command -v sha256sum >/dev/null 2>&1 || { echo "ERROR: sha256sum is required" >&2; exit 1; }

echo "Preparing Godot Web Editor ${VERSION}"
rm -rf "${WORK_DIR}" "${PUBLIC_DIR}"
mkdir -p "${WORK_DIR}/unpacked" "${PUBLIC_DIR}"

curl --fail --location --retry 3 --retry-delay 2 \
  --output "${ARCHIVE_PATH}" "${URL}"

echo "${EXPECTED_SHA256}  ${ARCHIVE_PATH}" | sha256sum --check -

unzip -q "${ARCHIVE_PATH}" -d "${WORK_DIR}/unpacked"

EDITOR_HTML="$(find "${WORK_DIR}/unpacked" -type f -name 'index.html' -print -quit)"
if [[ -z "${EDITOR_HTML}" ]]; then
  echo "ERROR: the official archive contains no index.html entry point" >&2
  find "${WORK_DIR}/unpacked" -maxdepth 3 -type f -print >&2
  exit 1
fi

EDITOR_DIR="$(dirname "${EDITOR_HTML}")"
cp -a "${EDITOR_DIR}/." "${PUBLIC_DIR}/"

if [[ ! -f "${PUBLIC_DIR}/index.html" ]]; then
  ENTRY_NAME="$(basename "${EDITOR_HTML}")"
  cp "${PUBLIC_DIR}/${ENTRY_NAME}" "${PUBLIC_DIR}/index.html"
fi

python3 "${ROOT_DIR}/scripts/test_patch_web_shell.py"
python3 "${ROOT_DIR}/scripts/patch-web-shell.py"
python3 "${ROOT_DIR}/scripts/package-bridge-sandbox.py"

test -s "${PUBLIC_DIR}/index.html"
test "$(find "${PUBLIC_DIR}" -type f | wc -l)" -gt 1

echo "Build ready: $(find "${PUBLIC_DIR}" -type f | wc -l) files"
echo "Editor entry: public/index.html"
