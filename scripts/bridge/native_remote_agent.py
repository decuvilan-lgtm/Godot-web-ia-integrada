"""Outbound HTTPS agent connecting a local Godot editor to the relay.

Run this on the same computer as the graphical Godot editor. The editor addon
continues listening only on 127.0.0.1; this process polls the relay over HTTPS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import signal
import sys
import time
from pathlib import Path

import httpx

from native_editor_client import execute_native_command, project_fingerprint

MAX_RESULT_BYTES = 240 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect an already-open native Godot editor to the remote headless operator.")
    parser.add_argument("--project", required=True, help="Absolute path to the Godot project open in the editor")
    parser.add_argument("--registry", required=True, help="Absolute path to user://headless_bridge.json")
    parser.add_argument("--relay", required=True, help="Relay base URL, e.g. https://your-relay.onrender.com")
    parser.add_argument("--control-token", required=True, help="NATIVE_REMOTE_CONTROL_TOKEN configured on the relay")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    options = parser.parse_args()
    if not options.relay.startswith("https://"):
        parser.error("Remote agent requires HTTPS; plain HTTP is refused")
    if not 0.2 <= options.poll_seconds <= 10:
        parser.error("--poll-seconds must be between 0.2 and 10")

    project = Path(options.project).expanduser().resolve()
    registry_path = Path(options.registry).expanduser().resolve()
    project_id = project_fingerprint(project)
    headers = {"Authorization": "Bearer " + options.control_token}
    stopped = False

    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    with httpx.Client(base_url=options.relay.rstrip("/"), timeout=15.0, headers=headers) as client:
        enrollment = client.post("/v1/native-remote/sessions", json={
            "project_id": project_id, "project_path": str(project)
        })
        enrollment.raise_for_status()
        session = enrollment.json()
        session_id = session["session_id"]
        agent_token = session["agent_token"]
        agent_headers = {"Authorization": "Bearer " + agent_token}
        print(f"NATIVE_AGENT_CONNECTED session={session_id} project_id={project_id}", flush=True)
        try:
            while not stopped:
                try:
                    response = client.get(
                        f"/v1/native-remote/sessions/{session_id}/next",
                        headers=agent_headers, timeout=10.0
                    )
                    response.raise_for_status()
                    packet = response.json().get("command")
                    if not packet:
                        continue
                    command_id = str(packet.get("command_id", ""))
                    command = str(packet.get("command", ""))
                    args = packet.get("args", {})
                    try:
                        result = execute_native_command(
                            registry_path, project, command, args, timeout_seconds=25.0
                        )
                        payload = {
                            "command_id": command_id, "ok": True,
                            "result": result.get("result", {}), "error": ""
                        }
                    except Exception as exc:
                        payload = {
                            "command_id": command_id, "ok": False,
                            "result": {}, "error": str(exc)[:1000]
                        }
                    if len(json.dumps(payload["result"], ensure_ascii=False).encode()) > MAX_RESULT_BYTES:
                        payload = {"command_id": command_id, "ok": False, "result": {},
                                   "error": "Native result exceeded the relay size limit"}
                    submitted = client.post(
                        f"/v1/native-remote/sessions/{session_id}/results",
                        headers=agent_headers, json=payload
                    )
                    submitted.raise_for_status()
                    print(f"NATIVE_COMMAND_RESULT command={command} ok={payload['ok']}", flush=True)
                except (httpx.HTTPError, OSError) as exc:
                    print(f"NATIVE_AGENT_RETRY error={type(exc).__name__}", file=sys.stderr, flush=True)
                    time.sleep(min(5.0, options.poll_seconds * 2))
        finally:
            try:
                client.delete(f"/v1/native-remote/sessions/{session_id}")
            except httpx.HTTPError:
                pass
        print("NATIVE_AGENT_STOPPED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
