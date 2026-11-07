#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLIC_DIR="${ROOT_DIR}/public"
PORT="8765"
BASE_URL="http://127.0.0.1:${PORT}"
LOG_FILE="$(mktemp)"
SERVER_PID=""

cleanup() {
  if [[ -n "${SERVER_PID}" ]]; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  rm -f "${LOG_FILE}"
}
trap cleanup EXIT

WASM_FILE="$(find "${PUBLIC_DIR}" -type f -name '*.wasm' -print -quit)"
JS_FILE="$(find "${PUBLIC_DIR}" -type f -name '*.js' -print -quit)"
[[ -n "${WASM_FILE}" && -n "${JS_FILE}" ]] || {
  echo "ERROR: required WebAssembly or JavaScript asset missing" >&2
  exit 1
}

WASM_PATH="${WASM_FILE#"${PUBLIC_DIR}/"}"
JS_PATH="${JS_FILE#"${PUBLIC_DIR}/"}"

python3 -m http.server "${PORT}" --bind 127.0.0.1 --directory "${PUBLIC_DIR}" >"${LOG_FILE}" 2>&1 &
SERVER_PID="$!"

for attempt in $(seq 1 30); do
  if curl --fail --silent "${BASE_URL}/" -o /dev/null; then
    break
  fi
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    cat "${LOG_FILE}" >&2
    echo "ERROR: static server exited during startup" >&2
    exit 1
  fi
  sleep 1
done

curl --fail --silent "${BASE_URL}/" -o /dev/null
curl --fail --silent "${BASE_URL}/${WASM_PATH}" -o /dev/null
curl --fail --silent "${BASE_URL}/${JS_PATH}" -o /dev/null

echo "Starting 180-second HTTP stability observation"
START="$(date +%s)"
CHECKS=0
while (( "$(date +%s)" - START < 180 )); do
  curl --fail --silent "${BASE_URL}/" -o /dev/null
  curl --fail --silent "${BASE_URL}/${WASM_PATH}" -o /dev/null
  curl --fail --silent "${BASE_URL}/${JS_PATH}" -o /dev/null
  CHECKS=$((CHECKS + 1))
  ELAPSED=$(( $(date +%s) - START ))
  echo "HTTP stability check ${CHECKS}: ${ELAPSED}s elapsed"
  kill -0 "${SERVER_PID}"
  sleep 10
done

echo "HTTP stability observation passed: ${CHECKS} rounds over at least 180 seconds"
