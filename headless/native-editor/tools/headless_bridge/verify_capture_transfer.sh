#!/usr/bin/env bash
set -euo pipefail
GODOT="$1"
PROJECT="$2"
PROBE="res://tools/headless_bridge/bridge_probe.gd"
run_probe() {
  "$GODOT" --headless --path "$PROJECT" --script "$PROBE" -- "$@"
}
read_path() {
  sed -n 's/^BRIDGE_TEST_PASS //p' "$1" | tail -n 1 | jq -r "$2"
}
transfer_file() {
  local source_path="$1"
  local destination_path="$2"
  local original_path="$3"
  local total_size offset chunk_args chunk_response chunk_json chunk_bytes
  cp "$source_path" "$original_path"
  total_size=$(stat -c%s "$source_path")
  offset=0
  : > "$destination_path"
  while [ "$offset" -lt "$total_size" ]; do
    chunk_args=$(jq -cn --arg path "$source_path" --argjson offset "$offset" '{path:$path,offset:$offset,length:48000}')
    chunk_response=$(run_probe read_capture_chunk "$chunk_args")
    chunk_json=$(printf '%s\n' "$chunk_response" | sed -n 's/^BRIDGE_TEST_PASS //p' | tail -n 1)
    [ -n "$chunk_json" ]
    printf '%s\n' "$chunk_json" | jq -r '.result.data' | tr -d '\r\n ' | base64 -d >> "$destination_path"
    chunk_bytes=$(printf '%s\n' "$chunk_json" | jq -r '.result.bytes_read | floor')
    [ "$chunk_bytes" -gt 0 ]
    offset=$((offset + chunk_bytes))
  done
}
SCREENSHOT_PATH=$(read_path artifacts/screenshot-response.json '.result.capture_path')
VIDEO_PATH=$(read_path artifacts/video-response.json '.result.video_path')
transfer_file "$SCREENSHOT_PATH" artifacts/editor-window.transferred.png artifacts/editor-window.original.png
cmp artifacts/editor-window.original.png artifacts/editor-window.transferred.png
file artifacts/editor-window.transferred.png | grep -q 'PNG image data'
echo "FRESH_PROJECT_SCREENSHOT_TRANSFER_EXACT_MATCH_PASS"
transfer_file "$VIDEO_PATH" artifacts/editor-video.transferred.mp4 artifacts/editor-video.original.mp4
cmp artifacts/editor-video.original.mp4 artifacts/editor-video.transferred.mp4
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=noprint_wrappers=1 artifacts/editor-video.transferred.mp4 | grep -q h264
echo "FRESH_PROJECT_VIDEO_TRANSFER_EXACT_MATCH_PASS"
