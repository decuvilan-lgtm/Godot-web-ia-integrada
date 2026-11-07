#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_COMMIT="ed1daf0bf001b61586d9930840f2f1394092c079"
EXPECTED_URL="https://github.com/godotengine/godot.git"

ENTRY="$(git -C "${ROOT_DIR}" ls-tree HEAD engine/godot)"
if [[ -z "${ENTRY}" ]]; then
  echo "ERROR: engine/godot is not recorded as a Git submodule" >&2
  exit 1
fi

MODE="$(awk '{print $1}' <<< "${ENTRY}")"
TYPE="$(awk '{print $2}' <<< "${ENTRY}")"
SHA="$(awk '{print $3}' <<< "${ENTRY}")"
[[ "${MODE}" == "160000" && "${TYPE}" == "commit" ]] || {
  echo "ERROR: engine/godot is not a gitlink" >&2
  exit 1
}
[[ "${SHA}" == "${EXPECTED_COMMIT}" ]] || {
  echo "ERROR: unexpected Godot source commit: ${SHA}" >&2
  exit 1
}

URL="$(git -C "${ROOT_DIR}" config -f .gitmodules --get submodule.engine/godot.url)"
[[ "${URL}" == "${EXPECTED_URL}" ]] || {
  echo "ERROR: unexpected Godot submodule URL: ${URL}" >&2
  exit 1
}

echo "Godot source pin verified: ${SHA}"
