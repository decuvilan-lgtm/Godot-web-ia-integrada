#!/usr/bin/env python3
"""Validate a narrowly-scoped ChatGPT task submitted as a GitHub issue."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TITLE_PREFIX = "[CHATGPT-BRIDGE]"
TASK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
ALLOWED_ACTIONS = {"ping", "engine_smoke", "scene_audit_3d"}
ALLOWED_KEYS = {"protocol", "task_id", "action"}


def prepare(event_path: Path, output_path: Path, result_path: Path) -> dict:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    issue = event.get("issue") or {}
    title = str(issue.get("title") or "")
    if not title.startswith(TITLE_PREFIX):
        raise ValueError("Issue title is not a ChatGPT Bridge task.")

    body = issue.get("body")
    if not isinstance(body, str) or len(body.encode("utf-8")) > 4096:
        raise ValueError("Task body is missing or exceeds 4096 bytes.")
    try:
        task = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("Issue body must contain a plain JSON object.") from exc

    if not isinstance(task, dict) or set(task) - ALLOWED_KEYS:
        raise ValueError("Task must be an object containing only protocol, task_id and action.")
    if task.get("protocol") != 1:
        raise ValueError("Unsupported bridge protocol version.")
    task_id = task.get("task_id")
    if not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id):
        raise ValueError("task_id must contain 8-64 safe characters.")
    action = task.get("action")
    if action not in ALLOWED_ACTIONS:
        raise ValueError("Action is not allowlisted.")

    accepted = {"accepted": True, "task_id": task_id, "action": action}
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps({
        **accepted,
        "status": "accepted",
        "source_issue": issue.get("number"),
    }, indent=2) + "\n", encoding="utf-8")
    with output_path.open("a", encoding="utf-8") as out:
        out.write("accepted=true\n")
        out.write(f"task_id={task_id}\n")
        out.write(f"action={action}\n")
    return accepted


if __name__ == "__main__":
    try:
        data = prepare(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
        print(json.dumps(data))
    except Exception as exc:
        error = str(exc)[:300]
        Path(sys.argv[3]).parent.mkdir(parents=True, exist_ok=True)
        Path(sys.argv[3]).write_text(json.dumps({
            "accepted": False, "status": "rejected", "error": error
        }, indent=2) + "\n", encoding="utf-8")
        with Path(sys.argv[2]).open("a", encoding="utf-8") as out:
            out.write("accepted=false\n")
            out.write("error=" + error.replace("\n", " ") + "\n")
        print(error, file=sys.stderr)
        sys.exit(2)
