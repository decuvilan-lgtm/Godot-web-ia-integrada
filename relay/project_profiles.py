"""Repository-owned, data-only Godot lab profiles.

Profiles are fetched from the exact project revision and may only express a small
allowlist of browser interactions. They are never executed as Python, shell, or JS.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException

MANIFEST_PATH = "godot-lab/lab-manifest.json"
MAX_JSON_BYTES = 128 * 1024
MAX_COMMANDS = 20
MAX_STEPS = 40
MAX_WAIT_MS = 5_000
MAX_TOTAL_DELAY_MS = 20_000
MAX_HOLD_MS = 2_000
MAX_SESSION_ARTIFACT_BYTES = 24 * 1024 * 1024
KEY_RE = re.compile(r"^(?:[A-Z0-9]|Arrow(?:Left|Right|Up|Down)|Enter|Escape|Space|Tab|Backspace|Delete|Home|End|PageUp|PageDown|F(?:[1-9]|1[0-2]))$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,37}/[A-Za-z0-9][A-Za-z0-9._-]{0,98}$")


def _relative_profile_path(value: Any, *, prefix: str) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise ValueError("Profile file paths must be relative")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Profile file path contains an unsafe segment")
    if not value.endswith(".json"):
        raise ValueError("Profile data files must be JSON")
    return prefix + value


def validate_manifest(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Unsupported lab manifest schema_version")
    control_profile = _relative_profile_path(data.get("control_profile", "control-profile.json"), prefix="godot-lab/")
    raw_commands = data.get("commands")
    if not isinstance(raw_commands, list) or not 1 <= len(raw_commands) <= MAX_COMMANDS:
        raise ValueError("Manifest commands must contain 1 to 100 entries")
    commands: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in raw_commands:
        if not isinstance(entry, dict):
            raise ValueError("Each command entry must be an object")
        name = entry.get("name")
        if not isinstance(name, str) or not SLUG_RE.fullmatch(name) or name in seen:
            raise ValueError("Command names must be unique safe slugs")
        file_path = _relative_profile_path(entry.get("file"), prefix="godot-lab/")
        if not file_path.startswith("godot-lab/commands/"):
            raise ValueError("Command files must live under godot-lab/commands/")
        seen.add(name)
        commands.append({"name": name, "file": file_path, "description": str(entry.get("description", ""))[:240]})
    project = data.get("project", {})
    if not isinstance(project, dict):
        raise ValueError("Manifest project metadata must be an object")
    project_name = project.get("name", "")
    project_path = project.get("project_path")
    if not isinstance(project_name, str) or len(project_name) > 120:
        raise ValueError("Manifest project name is invalid")
    if not isinstance(project_path, str) or (
        project_path != "" and (
            project_path.startswith("/")
            or project_path.endswith("/")
            or "\\" in project_path
            or any(part in {"", ".", ".."} for part in project_path.split("/"))
        )
    ):
        raise ValueError("Manifest project_path is required and must be a safe relative path (or empty for repository root)")
    return {
        "schema_version": 1,
        "project": {"name": project_name, "project_path": project_path},
        "control_profile": control_profile,
        "commands": commands,
    }


def validate_verification(data: Any, *, expected_commit_sha: str | None = None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Profile verification metadata is required")
    status = data.get("status")
    if status not in {"pending", "verified", "obsolete"}:
        raise ValueError("Profile verification status must be pending, verified, or obsolete")
    commit_sha = data.get("commit_sha")
    if commit_sha is not None and (
        not isinstance(commit_sha, str)
        or not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", commit_sha)
    ):
        raise ValueError("Profile verification commit_sha must be a full Git SHA or null")
    if status == "verified" and commit_sha is None:
        raise ValueError("A verified profile must record the exact commit SHA it was tested against")
    if status == "verified" and expected_commit_sha and commit_sha.lower() != expected_commit_sha.lower():
        status = "obsolete"
    return {"status": status, "commit_sha": commit_sha.lower() if commit_sha else None}


def validate_control_profile(data: Any, *, expected_commit_sha: str | None = None) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Unsupported control profile schema_version")
    verification = validate_verification(data.get("verification"), expected_commit_sha=expected_commit_sha)
    controls = data.get("controls")
    if not isinstance(controls, dict) or len(controls) > 100:
        raise ValueError("Control profile must contain at most 100 controls")
    validated: dict[str, dict[str, Any]] = {}
    for name, control in controls.items():
        if not isinstance(name, str) or not SLUG_RE.fullmatch(name) or not isinstance(control, dict):
            raise ValueError("Control names and definitions are invalid")
        kind = control.get("type")
        if kind == "key":
            key = control.get("key")
            if not isinstance(key, str) or not KEY_RE.fullmatch(key):
                raise ValueError(f"Control {name} has a key outside the safe allowlist")
            validated[name] = {"type": "key", "key": key}
        elif kind == "text":
            label = control.get("text")
            if not isinstance(label, str) or not label.strip() or len(label) > 120:
                raise ValueError(f"Control {name} has invalid visible text")
            validated[name] = {"type": "text", "text": label}
        elif kind == "point":
            x, y = control.get("x"), control.get("y")
            if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not 0 <= x <= 1 or not 0 <= y <= 1:
                raise ValueError(f"Control {name} must use normalized viewport coordinates")
            validated[name] = {"type": "point", "x": float(x), "y": float(y)}
        else:
            raise ValueError(f"Control {name} uses an unsupported type")
    return {"schema_version": 1, "verification": verification, "controls": validated}


def validate_command(data: Any, *, expected_name: str, controls: dict[str, Any], expected_commit_sha: str | None = None) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Unsupported command schema_version")
    if data.get("name") != expected_name:
        raise ValueError("Command file name does not match its manifest entry")
    verification = validate_verification(data.get("verification"), expected_commit_sha=expected_commit_sha)
    steps = data.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError("Command must contain 1 to 80 steps")
    validated_steps: list[dict[str, Any]] = []
    total_delay_ms = 0
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"Step {index} must be an object")
        op = step.get("op")
        if not isinstance(op, str):
            raise ValueError(f"Step {index} operation must be a string")
        if op == "wait":
            ms = step.get("ms")
            if isinstance(ms, bool) or not isinstance(ms, int) or not 0 <= ms <= MAX_WAIT_MS:
                raise ValueError(f"Step {index} has an invalid wait duration")
            total_delay_ms += ms
            validated_steps.append({"op": op, "ms": ms})
        elif op in {"inspect", "screenshot", "assert_canvas"}:
            validated_steps.append({"op": op})
        elif op == "tap_control":
            control = step.get("control")
            if not isinstance(control, str) or control not in controls:
                raise ValueError(f"Step {index} references an unknown control")
            validated_steps.append({"op": op, "control": control})
        elif op == "hold_control":
            control = step.get("control")
            duration = step.get("duration_ms")
            if not isinstance(control, str) or control not in controls or controls[control]["type"] != "key":
                raise ValueError(f"Step {index} can only hold a key control")
            if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= MAX_HOLD_MS:
                raise ValueError(f"Step {index} has an invalid hold duration")
            total_delay_ms += duration
            validated_steps.append({"op": op, "control": control, "duration_ms": duration})
        elif op == "click_text":
            label = step.get("text")
            if not isinstance(label, str) or not label.strip() or len(label) > 120:
                raise ValueError(f"Step {index} has invalid click text")
            validated_steps.append({"op": op, "text": label})
        elif op == "press_key":
            key = step.get("key")
            if not isinstance(key, str) or not KEY_RE.fullmatch(key):
                raise ValueError(f"Step {index} uses a key outside the safe allowlist")
            validated_steps.append({"op": op, "key": key})
        elif op == "assert_text":
            label = step.get("text")
            if not isinstance(label, str) or not label.strip() or len(label) > 300:
                raise ValueError(f"Step {index} has invalid assertion text")
            validated_steps.append({"op": op, "text": label})
        else:
            raise ValueError(f"Step {index} uses unsupported operation {op!r}")
        if total_delay_ms > MAX_TOTAL_DELAY_MS:
            raise ValueError("Command exceeds the total wait/hold time budget")
    return {"schema_version": 1, "name": expected_name, "verification": verification, "steps": validated_steps}


async def _fetch_json(client: httpx.AsyncClient, url: str) -> Any | None:
    async with client.stream("GET", url) as response:
        if response.status_code == 404:
            return None
        response.raise_for_status()
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > MAX_JSON_BYTES:
            raise ValueError("Project profile file exceeds the size limit")
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > MAX_JSON_BYTES:
                raise ValueError("Project profile file exceeds the size limit")
        return json.loads(bytes(content))


async def resolve_repository_commit_sha(repository: str, branch: str) -> str:
    if not REPO_RE.fullmatch(repository) or not branch or len(branch) > 128 or ".." in branch:
        raise HTTPException(status_code=400, detail="Invalid repository or branch for SHA resolution")
    owner, repo = repository.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{repo}/branches/{quote(branch, safe='')}"
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers={"Accept": "application/vnd.github+json", "User-Agent": "godot-web-ia-relay"}) as client:
            response = await client.get(url)
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="GitHub branch was not found")
            response.raise_for_status()
            data = response.json()
        sha = str(data.get("commit", {}).get("sha") or "").lower()
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", sha):
            raise ValueError("GitHub branch response did not contain a full commit SHA")
        return sha
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Could not resolve immutable Git commit SHA: {type(exc).__name__}") from exc


async def load_project_profile(repository: str, ref: str, command_name: str | None = None) -> dict[str, Any] | None:
    if not REPO_RE.fullmatch(repository):
        raise HTTPException(status_code=400, detail="Invalid repository for project profile")
    if not ref or len(ref) > 128 or ".." in ref:
        raise HTTPException(status_code=400, detail="Invalid project revision for profile lookup")
    owner, repo = repository.split("/", 1)
    base = f"https://raw.githubusercontent.com/{owner}/{repo}/{quote(ref, safe='/')}/"
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            raw_manifest = await _fetch_json(client, base + MANIFEST_PATH)
            if raw_manifest is None:
                return None
            manifest = validate_manifest(raw_manifest)
            raw_controls = await _fetch_json(client, base + manifest["control_profile"])
            if raw_controls is None:
                raise ValueError("Manifest control profile file was not found")
            control_profile = validate_control_profile(raw_controls, expected_commit_sha=ref)
            commands: dict[str, dict[str, Any]] = {}
            if command_name is not None:
                entry = next((item for item in manifest["commands"] if item["name"] == command_name), None)
                if entry is None:
                    raise HTTPException(status_code=404, detail="Project-owned command was not found in the manifest")
                raw_command = await _fetch_json(client, base + entry["file"])
                if raw_command is None:
                    raise ValueError(f"Command file {entry['name']} was not found")
                commands[entry["name"]] = validate_command(
                    raw_command,
                    expected_name=entry["name"],
                    controls=control_profile["controls"],
                    expected_commit_sha=ref,
                )
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Project-owned lab profile is invalid or unavailable: {type(exc).__name__}") from exc
    return {
        "manifest": manifest,
        "control_profile": control_profile,
        "commands": commands,
    }


async def execute_profile_command(page: Any, profile: dict[str, Any], command_name: str, artifacts: dict[str, bytes]) -> list[dict[str, Any]]:
    command = profile["commands"].get(command_name)
    if command is None:
        raise HTTPException(status_code=404, detail="Project-owned command was not found")
    controls = profile["control_profile"]["controls"]
    results: list[dict[str, Any]] = []
    held_keys: set[str] = set()
    try:
        for index, step in enumerate(command["steps"]):
            op = step["op"]
            output: dict[str, Any] = {}
            if op == "wait":
                await asyncio.sleep(step["ms"] / 1000)
                output = {"waited_ms": step["ms"]}
            elif op == "inspect":
                output = {
                    "url": page.url,
                    "title": await page.title(),
                    "visible_text": (await page.locator("body").inner_text(timeout=20000))[:12000],
                    "canvas_count": await page.locator("canvas").count(),
                    "connector_status": await page.evaluate("() => window.__godotGithubConnectorStatus || null"),
                }
            elif op == "screenshot":
                name = f"profile-{command_name}-{index}-{int(time.time() * 1000)}.png"
                data = await page.screenshot(full_page=False, timeout=20000)
                current_size = sum(len(item) for item in artifacts.values())
                if len(data) > MAX_SESSION_ARTIFACT_BYTES or current_size + len(data) > MAX_SESSION_ARTIFACT_BYTES:
                    raise HTTPException(status_code=413, detail="Project-owned profile exceeded the session artifact size limit")
                artifacts[name] = data
                output = {"artifact": name, "bytes": len(data)}
            elif op == "tap_control":
                control = controls[step["control"]]
                if control["type"] == "key":
                    await page.keyboard.press(control["key"])
                    output = {"control": step["control"], "pressed_key": control["key"]}
                elif control["type"] == "text":
                    await page.get_by_text(control["text"], exact=True).first.click(timeout=5000)
                    output = {"control": step["control"], "clicked_text": control["text"]}
                else:
                    viewport = await page.evaluate("() => ({width: window.innerWidth, height: window.innerHeight})")
                    x = max(0, min(viewport["width"] - 1, round(control["x"] * viewport["width"])))
                    y = max(0, min(viewport["height"] - 1, round(control["y"] * viewport["height"])))
                    await page.mouse.click(x, y)
                    output = {"control": step["control"], "clicked_normalized_point": [control["x"], control["y"]]}
            elif op == "hold_control":
                key = controls[step["control"]]["key"]
                await page.keyboard.down(key)
                held_keys.add(key)
                try:
                    await asyncio.sleep(step["duration_ms"] / 1000)
                finally:
                    await page.keyboard.up(key)
                    held_keys.discard(key)
                output = {"control": step["control"], "held_key": key, "duration_ms": step["duration_ms"]}
            elif op == "click_text":
                await page.get_by_text(step["text"], exact=True).first.click(timeout=15000)
                output = {"clicked_text": step["text"]}
            elif op == "press_key":
                await page.keyboard.press(step["key"])
                output = {"pressed_key": step["key"]}
            elif op == "assert_text":
                visible = await page.locator("body").inner_text(timeout=20000)
                if step["text"] not in visible:
                    raise HTTPException(status_code=409, detail=f"Expected visible text was not found: {step['text']}")
                output = {"asserted_text": step["text"]}
            elif op == "assert_canvas":
                count = await page.locator("canvas").count()
                if count < 1:
                    raise HTTPException(status_code=409, detail="Expected a visible canvas but none was found")
                output = {"canvas_count": count}
            results.append({"step": index, "op": op, "result": output})
    finally:
        for key in held_keys:
            try:
                await page.keyboard.up(key)
            except Exception:
                pass
    return results
