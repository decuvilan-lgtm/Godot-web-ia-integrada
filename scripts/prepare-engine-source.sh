#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_DIR="${ROOT_DIR}/engine/godot"
PATCH_DIR="${ROOT_DIR}/patches/godot"

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required" >&2
  exit 1
fi

git -C "${ROOT_DIR}" submodule update --init --depth 1 engine/godot

if [[ ! -f "${ENGINE_DIR}/SConstruct" ]]; then
  echo "ERROR: Godot source checkout is incomplete" >&2
  exit 1
fi

if [[ -d "${PATCH_DIR}" ]]; then
  while IFS= read -r patch; do
    [[ -n "${patch}" ]] || continue
    echo "Checking patch: ${patch#"${ROOT_DIR}/"}"
    git -C "${ENGINE_DIR}" apply --check "${patch}"
    git -C "${ENGINE_DIR}" apply "${patch}"
  done < <(find "${PATCH_DIR}" -maxdepth 1 -type f -name '*.patch' -print | sort)
fi

python3 "${ROOT_DIR}/scripts/apply-web-github-import.py"

echo "Godot source ready at ${ENGINE_DIR} (public GitHub import patch applied)"
