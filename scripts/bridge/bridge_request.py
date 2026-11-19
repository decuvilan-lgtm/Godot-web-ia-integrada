"""One-request transport adapter for the persistent A browser session.

This process does not reason about tasks or choose actions. It forwards the exact
operator-supplied command to A and returns A's response unchanged (except for
transport metadata and verified artifact expansion).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

from scripts.bridge.artifacts import (
    download_json_artifact,
    enqueue_transport_command,
    fetch_transport_command_result,
    issue_transport_device_token,
    join_transport_session,
    request_github_actions_oidc_token,
)

REQUEST_PATH = Path(".session-operator-request.json")
RESULT_PATH = Path("operator-result.json")
API_URL = os.environ["AB_API_URL"].strip()


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> int:
    if not REQUEST_PATH.is_file():
        fail("Bridge request file is missing")
    request = json.loads(REQUEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(request, dict):
        fail("Bridge request must be a JSON object")

    repository = os.environ.get("GITHUB_REPOSITORY", "")
    branch = os.environ.get("GITHUB_REF_NAME", "")
    if request.get("repository") != repository:
        fail("Bridge request repository mismatch")
    if branch != "test/verdant-valley-development-benchmark" or request.get("branch") != branch:
        fail("Bridge is restricted to the authorized test branch")

    request_id = request.get("request_id")
    session_id = request.get("transport_session_id")
    command = request.get("command")
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_id):
        fail("request_id must be a bounded identifier")
    try:
        uuid.UUID(session_id)
    except (ValueError, TypeError, AttributeError):
        fail("transport_session_id must be the UUID supplied by the operator")
    if not isinstance(command, dict) or set(command) - {"action", "args"}:
        fail("command must contain only action and args")
    action = command.get("action")
    args = command.get("args", {})
    if not isinstance(action, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", action):
        fail("command.action must be a bounded action identifier")
    if not isinstance(args, dict) or len(json.dumps(args, ensure_ascii=False).encode("utf-8")) > 64 * 1024:
        fail("command.args must be a bounded JSON object")

    timeout_seconds = request.get("timeout_seconds", 240)
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or not 15 <= timeout_seconds <= 900:
        fail("timeout_seconds must be between 15 and 900")

    # B only authenticates, joins, forwards, waits for the matching response, and relays it.
    oidc = request_github_actions_oidc_token()
    token = issue_transport_device_token(API_URL, oidc, expected_kind="agent_controller")
    join_transport_session(API_URL, token, session_id)
    created = enqueue_transport_command(
        API_URL,
        token,
        session_id=session_id,
        target="web_editor",
        action=action,
        args=args,
        idempotency_key=request_id,
        ttl_seconds=min(timeout_seconds, 300),
    )
    command_id = created["id"]
    deadline = time.monotonic() + timeout_seconds
    polls = 0
    response = None
    while time.monotonic() < deadline:
        polls += 1
        response = fetch_transport_command_result(API_URL, token, command_id)
        if response is not None:
            break
        time.sleep(0.5)
    if response is None:
        fail("Timed out waiting for A's response; command remains unverified")

    result = response["result"]
    if isinstance(result, dict) and isinstance(result.get("artifact_id"), str):
        result = download_json_artifact(API_URL, token, result["artifact_id"])

    payload = {
        "bridge": "transport-only",
        "request_id": request_id,
        "command_id": command_id,
        "transport_status": response["status"],
        "poll_count": polls,
        "a_result": result,
    }
    RESULT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if response["status"] == "succeeded" else 2


if __name__ == "__main__":
    sys.exit(main())
