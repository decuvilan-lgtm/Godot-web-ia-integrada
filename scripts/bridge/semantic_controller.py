"""Semantic, coordinate-free client for the Chromium Godot Controller extension."""
from __future__ import annotations

import secrets
from typing import Any

CHANNEL = "GODOT_CONTROLLER_BRIDGE_V1"
ACTIONS = {
    "editor.get_state": set(),
    "editor.list_capabilities": set(),
    "editor.open_panel": {"panel"},
    "scene.open": {"scene_path"},
    "scene.select_node": {"node_path"},
    "node.get_inspector": {"node_path"},
}
PANELS = {"scene", "filesystem", "inspector", "output", "debugger", "history", "import"}


def _validate(action: str, args: dict[str, Any]) -> None:
    if action not in ACTIONS:
        raise ValueError(f"Unsupported semantic editor action: {action}")
    if not isinstance(args, dict) or set(args) - ACTIONS[action]:
        raise ValueError("Invalid arguments for semantic editor action")
    for key, value in args.items():
        if not isinstance(value, str) or not value or len(value) > 500:
            raise ValueError(f"{key} must be a non-empty string of at most 500 characters")
    if action == "editor.open_panel" and args.get("panel") not in PANELS:
        raise ValueError("Unsupported editor panel")


def execute_semantic_command(page: Any, action: str, args: dict[str, Any] | None = None,
                             timeout_ms: int = 10000) -> dict[str, Any]:
    """Send one allowlisted semantic command through the extension in this Actions tab.

    This function does not click, move the mouse, press keys, or use coordinates.
    It returns an explicit error if the extension or Godot editor adapter is absent.
    """
    payload = args or {}
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
