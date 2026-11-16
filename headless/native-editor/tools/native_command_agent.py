#!/usr/bin/env python3
"""Long-running, read-only Command Center worker for one native Godot editor.

Credentials are supplied through environment variables and are never written to disk.
The worker invokes only the project's authenticated localhost bridge probe; it does
not accept shell commands, arbitrary scripts, file paths, or mutating actions.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = os.environ.get("COMMAND_CENTER_URL", "").rstrip("/")
TOKEN = os.environ.get("COMMAND_CENTER_DEVICE_TOKEN", "")
PROJECT = Path(os.environ.get("GODOT_PROJECT_PATH", ".")).resolve()
GODOT = os.environ.get("GODOT_BIN", "godot")
POLL_SECONDS = max(1.0, min(float(os.environ.get("POLL_SECONDS", "2")), 10.0))
ACTIONS = {
    "ping": "ping",
    "editor.get_state": "editor.get_state",
    "scene.get_tree": "scene.get_tree",
    "project.list_resources": "project.list_resources",
    "capture.editor_screenshot": "capture.editor_screenshot",
    "capture.desktop_screenshot": "capture.desktop_screenshot",
}


class AgentError(RuntimeError):
    pass


def request(method: str, path: str, payload: dict | None = None):
    if not API.startswith("https://"):
        raise AgentError("COMMAND_CENTER_URL must use HTTPS")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read(1_100_000)
            if len(raw) >= 1_100_000:
                raise AgentError("Command Center response exceeded the size limit")
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", "replace")
        raise AgentError(f"Command Center HTTP {exc.code}: {detail}") from exc


def execute(action: str, args: dict) -> dict:
    if action not in ACTIONS:
        raise AgentError("Action is not in the native read-only allowlist")
    if args:
        raise AgentError("This agent version accepts no command arguments")
    probe = PROJECT / "tools" / "headless_bridge" / "bridge_probe.gd"
    if not probe.is_file():
        raise AgentError(f"Bridge probe not found in project: {probe}")
    command = [
        GODOT, "--headless", "--path", str(PROJECT),
        "--script", "res://tools/headless_bridge/bridge_probe.gd",
        "--", ACTIONS[action],
    ]
    completed = subprocess.run(
        command, cwd=PROJECT, capture_output=True, text=True,
        timeout=25, check=False,
    )
    output = (completed.stdout + "\n" + completed.stderr)[-12000:]
    if completed.returncode != 0:
        raise AgentError(f"Local bridge probe failed ({completed.returncode}): {output}")
    marker = "BRIDGE_TEST_PASS "
    line = next((item for item in output.splitlines() if marker in item), None)
    if line is None:
        raise AgentError("Bridge probe exited without a structured success response")
    response = json.loads(line.split(marker, 1)[1])
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise AgentError("Local editor did not confirm the requested action")
    return {"bridge": response, "project_path": str(PROJECT), "godot_exit_code": 0}


def main() -> int:
    if not API or not TOKEN or not PROJECT.is_dir():
        print("Set COMMAND_CENTER_URL, COMMAND_CENTER_DEVICE_TOKEN and GODOT_PROJECT_PATH.", file=sys.stderr)
        return 2
    print("NATIVE_COMMAND_AGENT_READY", flush=True)
    while True:
        try:
            response = request("GET", "/v1/command-center/commands/next?target=native_editor")
            command = response.get("command")
            if not command:
                time.sleep(POLL_SECONDS)
                continue
            command_id = str(command.get("id", ""))
            action = str(command.get("action", ""))
            started = time.monotonic()
            try:
                result = execute(action, command.get("args") or {})
                ok = True
            except Exception as exc:
                result = {"error": str(exc)[:4000], "error_type": type(exc).__name__}
                ok = False
            duration_ms = min(3_600_000, int((time.monotonic() - started) * 1000))
            request(
                "POST",
                f"/v1/command-center/commands/{urllib.parse.quote(command_id, safe='')}/result",
                {"ok": ok, "result": result, "duration_ms": duration_ms},
            )
            print(json.dumps({"command_id": command_id, "action": action, "ok": ok}), flush=True)
        except KeyboardInterrupt:
            print("NATIVE_COMMAND_AGENT_STOPPED", flush=True)
            return 0
        except Exception as exc:
            print(f"NATIVE_AGENT_RETRY {type(exc).__name__}: {str(exc)[:500]}", file=sys.stderr, flush=True)
            time.sleep(min(15.0, POLL_SECONDS * 3))


if __name__ == "__main__":
    raise SystemExit(main())
