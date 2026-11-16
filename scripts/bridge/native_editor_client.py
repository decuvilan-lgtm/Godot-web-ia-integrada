"""Coordinate-free client for the native Godot editor session bridge.

This client runs on the same machine as the graphical Godot editor. It talks
only to the addon's loopback listener; it never opens a public port, launches
an editor, sends mouse/keyboard input, or executes arbitrary code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
DEFAULT_TIMEOUT_SECONDS = 18.0

# Keep this list aligned with the explicit dispatcher in plugin.gd.
ALLOWED_COMMANDS = frozenset({
    "editor.list_capabilities", "editor.get_state",
    "scene.get_tree", "scene.inspect_selection",
    "scene.add_node", "scene.set_node_properties",
    "scene.configure_collision_shape", "scene.assign_visual_resource",
    "scene.create_sprite_frames", "editor.open_scene",
    "editor.focus_inspector", "editor.inspect_undo_history",
    "editor.undo", "editor.redo", "editor.inspect_project_settings",
    "editor.inspect_editor_settings", "project.list_resources",
    "project.inspect_resource", "preview.get_status", "preview.start",
    "preview.stop", "capture.editor_screenshot",
    "capture.desktop_screenshot", "capture.start_editor_video",
    "capture.stop_editor_video", "capture.get_video_status",
    "capture.read_chunk",
})


def project_fingerprint(project_path: str | Path) -> str:
    """Match the native addon's SHA-256 fingerprint for an absolute project path."""
    resolved = str(Path(project_path).expanduser().resolve()).replace("\\", "/")
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()


def load_registry(registry_path: str | Path) -> dict[str, Any]:
    path = Path(registry_path).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read Godot bridge registry: {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Godot bridge registry must contain a JSON object")
    if data.get("protocol") != PROTOCOL_VERSION:
        raise RuntimeError("Godot bridge protocol version mismatch")
    if not isinstance(data.get("token"), str) or len(data["token"]) < 32:
        raise RuntimeError("Godot bridge registry has no valid session token")
    if not isinstance(data.get("project_id"), str) or len(data["project_id"]) != 64:
        raise RuntimeError("Godot bridge registry has no valid project fingerprint")
    port = data.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise RuntimeError("Godot bridge registry has an invalid port")
    # The addon is intentionally loopback-only. Never honor a host from registry.
    return data


def validate_command(command: str, args: dict[str, Any] | None) -> dict[str, Any]:
    if command not in ALLOWED_COMMANDS:
        raise ValueError(f"Unsupported native editor command: {command}")
    if args is None:
        return {}
    if not isinstance(args, dict):
        raise ValueError("Command args must be a JSON object")
    encoded = json.dumps(args, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_REQUEST_BYTES - 2048:
        raise ValueError("Command arguments exceed the 64 KiB protocol limit")
    return args


def execute_native_command(
    registry_path: str | Path,
    project_path: str | Path,
    command: str,
    args: dict[str, Any] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute one allowlisted semantic command against the already-open editor."""
    safe_args = validate_command(command, args)
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not 0.1 <= timeout_seconds <= 60:
        raise ValueError("timeout_seconds must be between 0.1 and 60")
    registry = load_registry(registry_path)
    expected_id = project_fingerprint(project_path)
    if registry["project_id"] != expected_id:
        raise RuntimeError("Discovered editor belongs to a different project")

    request = {
        "protocol": PROTOCOL_VERSION,
        "token": registry["token"],
        "project_id": expected_id,
        "command": command,
        "args": safe_args,
    }
    payload = (json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(payload) > MAX_REQUEST_BYTES:
        raise ValueError("Request exceeds the 64 KiB protocol limit")

    received = bytearray()
    with socket.create_connection(("127.0.0.1", registry["port"]), timeout=timeout_seconds) as peer:
        peer.settimeout(timeout_seconds)
        peer.sendall(payload)
        while b"\n" not in received:
            chunk = peer.recv(8192)
            if not chunk:
                raise RuntimeError("Godot editor closed the connection before responding")
            received.extend(chunk)
            if len(received) > MAX_RESPONSE_BYTES:
                raise RuntimeError("Godot editor response exceeded the 256 KiB limit")

    line = bytes(received).split(b"\n", 1)[0]
    try:
        response = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Godot editor returned an invalid JSON response") from exc
    if not isinstance(response, dict):
        raise RuntimeError("Godot editor response must be a JSON object")
    if response.get("project_id") != expected_id:
        raise RuntimeError("Godot editor response project fingerprint mismatch")
    if response.get("command") != command:
        raise RuntimeError("Godot editor response command mismatch")
    if not response.get("ok", False):
        raise RuntimeError(str(response.get("error", "Godot editor rejected the command")))
    return response


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a semantic command to an already-open native Godot editor.")
    parser.add_argument("--project", required=True, help="Absolute path to the Godot project currently open in the editor")
    parser.add_argument("--registry", required=True, help="Path to user://headless_bridge.json")
    parser.add_argument("--command", required=True, choices=sorted(ALLOWED_COMMANDS))
    parser.add_argument("--args", default="{}", help="JSON object with command arguments")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    options = parser.parse_args()
    try:
        args = json.loads(options.args)
        result = execute_native_command(options.registry, options.project, options.command, args, options.timeout)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(2, f"headless-native-client: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
