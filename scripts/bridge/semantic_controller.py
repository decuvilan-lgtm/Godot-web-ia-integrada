"""Semantic, coordinate-free client for the Chromium Godot Controller extension."""
from __future__ import annotations

import math
import re
import secrets
from typing import Any

CHANNEL = "GODOT_CONTROLLER_BRIDGE_V1"
ACTIONS = {
    "editor.get_state": set(),
    "editor.list_capabilities": set(),
    "scene.get_tree": set(),
    "scene.inspect_node": {"path"},
    "scene.add_node": {"node_type", "node_name", "parent_path"},
    "scene.set_property": {"path", "property", "value"},
}


def _validate(action: str, args: dict[str, Any]) -> None:
    if action not in ACTIONS:
        raise ValueError(f"Unsupported semantic editor action: {action}")
    if not isinstance(args, dict) or set(args) - ACTIONS[action]:
        raise ValueError("Invalid arguments for semantic editor action")
    if action == "scene.inspect_node":
        path = args.get("path")
        if set(args) != {"path"} or not isinstance(path, str) or not path or len(path) > 200:
            raise ValueError("scene.inspect_node requires one bounded relative path")
        if path.startswith("/") or ".." in path.split("/") or "//" in path:
            raise ValueError("scene.inspect_node path must stay inside the active scene root")
        return
    if action == "scene.set_property":
        if set(args) != {"path", "property", "value"}:
            raise ValueError("scene.set_property requires path, property, and value")
        path = args["path"]
        property_name = args["property"]
        if not isinstance(path, str) or not path or len(path) > 200:
            raise ValueError("scene.set_property path must be a bounded relative path")
        if path.startswith("/") or ".." in path.split("/") or "//" in path:
            raise ValueError("scene.set_property path must stay inside the active scene root")
        if not isinstance(property_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", property_name):
            raise ValueError("scene.set_property property must be a bounded identifier")
        if property_name == "script":
            raise ValueError("Script assignment is not exposed through the semantic property editor")
        value = args["value"]
        if isinstance(value, bool) or value is None:
            pass
        elif isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Property numbers must be finite")
            if abs(value) > 1_000_000_000:
                raise ValueError("Property numbers exceed the safe range")
        elif isinstance(value, str):
            if len(value) > 512:
                raise ValueError("Property strings are limited to 512 characters")
        elif isinstance(value, list):
            if not 2 <= len(value) <= 4 or any(
                not isinstance(item, (int, float)) or isinstance(item, bool)
                or (isinstance(item, float) and not math.isfinite(item))
                or abs(item) > 1_000_000_000
                for item in value
            ):
                raise ValueError("Property arrays must contain 2-4 finite numeric vector/color components")
        elif isinstance(value, dict):
            resource_path = value.get("resource_path")
            if set(value) != {"resource_path"} or not isinstance(resource_path, str):
                raise ValueError("Object properties accept only a resource_path reference")
            if not resource_path.startswith("res://") or len(resource_path) > 512 or ".." in resource_path.split("/") or "\\" in resource_path:
                raise ValueError("Resource paths must stay inside res://")
        else:
            raise ValueError("Property value must be a JSON primitive, numeric vector/color array, or resource_path object")
        return
    if action != "scene.add_node":
        if args:
            raise ValueError("Read-only editor queries do not accept arguments")
        return
    if not {"node_type", "node_name"}.issubset(args):
        raise ValueError("scene.add_node requires node_type and node_name")
    limits = {"node_type": 64, "node_name": 48, "parent_path": 200}
    for key, value in args.items():
        if not isinstance(value, str) or not value or len(value) > limits[key]:
            raise ValueError(f"{key} must be a non-empty bounded string")
    allowed_types = {
        "Node", "Node2D", "Sprite2D", "AnimatedSprite2D", "Polygon2D", "Line2D",
        "CharacterBody2D", "RigidBody2D", "StaticBody2D", "Area2D", "CollisionShape2D",
        "CollisionPolygon2D", "RayCast2D", "VisibleOnScreenNotifier2D", "Camera2D", "Marker2D",
        "Path2D", "PathFollow2D", "TileMapLayer", "Parallax2D", "RemoteTransform2D",
        "CanvasLayer", "Control", "Label", "RichTextLabel", "TextureRect",
        "ColorRect", "Panel", "Button", "TextureButton", "ProgressBar", "VBoxContainer",
        "HBoxContainer", "GridContainer", "MarginContainer", "CenterContainer",
        "SubViewport", "SubViewportContainer", "AnimationPlayer", "AnimationTree", "Timer",
        "AudioStreamPlayer", "AudioStreamPlayer2D",
    }
    if args["node_type"] not in allowed_types:
        raise ValueError("node_type is not allowlisted")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,47}", args["node_name"]):
        raise ValueError("node_name must be a valid bounded identifier")
    if "parent_path" in args and (
        args["parent_path"].startswith("/")
        or ".." in args["parent_path"].split("/")
        or "//" in args["parent_path"]
    ):
        raise ValueError("parent_path must stay inside the edited scene root")


def execute_semantic_command(page: Any, action: str, args: dict[str, Any] | None = None,
                             timeout_ms: int = 10000) -> dict[str, Any]:
    """Send one allowlisted semantic command through the extension in this Actions tab.

    This function does not click, move the mouse, press keys, or use coordinates.
    It returns an explicit error if the extension or Godot editor adapter is absent.
    """
    payload = {} if args is None else args
    _validate(action, payload)
    if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or not 100 <= timeout_ms <= 30000:
        raise ValueError("timeout_ms must be between 100 and 30000")
    request_id = "gha-" + secrets.token_hex(12)
    return page.evaluate(
        """async ({channel, requestId, command, timeoutMs}) => {
          return await new Promise(resolve => {
            let settled = false;
            const finish = value => {
              if (settled) return;
              settled = true;
              clearTimeout(timer);
              window.removeEventListener("message", onMessage);
              resolve(value);
            };
            const onMessage = event => {
              if (event.source !== window || event.origin !== location.origin) return;
              const data = event.data;
              if (!data || data.channel !== channel || data.direction !== "host-response" ||
                  data.request_id !== requestId) return;
              finish(data.result);
            };
            const timer = setTimeout(() => finish({
              ok: false, error: "HOST_TIMEOUT",
              message: "No semantic response arrived from the Chromium extension."
            }), timeoutMs);
            window.addEventListener("message", onMessage);
            window.postMessage({
              channel, direction: "host-command", request_id: requestId, command
            }, location.origin);
          });
        }""",
        {
            "channel": CHANNEL,
            "requestId": request_id,
            "command": {"action": action, **payload},
            "timeoutMs": timeout_ms,
        },
    )
