#!/usr/bin/env python3
"""Transfer revisioned Godot project files between GitHub Actions and Render Relay.

The workflow supplies a short-lived agent_controller token obtained through GitHub
OIDC. This script never receives Neon credentials or direct Object Storage URLs.
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path, PurePosixPath
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parents[1])).resolve()
INBOX = ROOT / "bridge-inbox"
RESULT_PATH = ROOT / "bridge-result.json"
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_EXPORT_BYTES = 512 * 1024 * 1024
MAX_TOTAL_IMPORT_BYTES = 512 * 1024 * 1024


class BridgeError(RuntimeError):
    pass


def safe_project_path(value: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 1024:
        raise BridgeError("Project path is empty or too long")
    if value.startswith("/") or "\\" in value or "\x00" in value or ":" in value:
        raise BridgeError("Project path must be a relative POSIX path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise BridgeError("Project path contains an invalid segment")
    lowered = [part.lower() for part in parts]
    if any(part in {".git", ".godot"} for part in lowered):
        raise BridgeError("Git metadata and Godot cache files are not transferable")
    forbidden_names = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}
    forbidden_suffixes = (".pem", ".key", ".p8", ".asc", ".gpg", ".p12", ".pfx", ".keystore", ".jks", ".mobileprovision")
    name = lowered[-1]
    if name in forbidden_names or name.endswith(forbidden_suffixes) or name.endswith(".env") or name.startswith(".env."):
        raise BridgeError("Credential and signing files are not transferable")
    return value


def safe_inbox_file(value: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise BridgeError("Payload reference is invalid")
    candidate = (ROOT / value).resolve()
    if candidate != INBOX and INBOX not in candidate.parents:
        raise BridgeError("Payload reference escapes bridge-inbox")
    if not candidate.is_file():
        raise BridgeError("Payload file is missing")
    return candidate


def api_request(method: str, path: str, token: str, body: bytes | None = None,
                headers: dict[str, str] | None = None) -> bytes:
    base = os.environ.get("RELAY_BASE_URL", "").rstrip("/")
    if not base.startswith("https://"):
        raise BridgeError("RELAY_BASE_URL must use HTTPS")
    request_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(base + path, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", "replace")
        raise BridgeError(f"Relay returned HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise BridgeError(f"Relay request failed: {type(exc).__name__}") from exc


def api_json(method: str, path: str, token: str, body: dict | None = None) -> dict:
    raw = json.dumps(body, separators=(",", ":")).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if raw is not None else None
    response = api_request(method, path, token, raw, headers)
    try:
        return json.loads(response)
    except ValueError as exc:
        raise BridgeError("Relay returned invalid JSON") from exc


def project_manifest(project_id: str, token: str) -> dict:
    return api_json("GET", f"/v1/command-center/projects/{project_id}/manifest", token)


def export_project(request: dict, token: str) -> dict:
    project_id = request.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise BridgeError("project_id is required")
    manifest = project_manifest(project_id, token)
    files = manifest.get("files", [])
    if not isinstance(files, list) or len(files) > 10000:
        raise BridgeError("Project manifest has an invalid file list")

    export_root = ROOT / "bridge-export"
    files_root = export_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)
    total = 0
    exported = []
    for entry in files:
        path = safe_project_path(entry.get("path"))
        size = int(entry.get("byte_size", -1))
        if size < 0 or size > MAX_FILE_BYTES:
            raise BridgeError(f"Invalid file size in manifest: {path}")
        total += size
        if total > MAX_TOTAL_EXPORT_BYTES:
            raise BridgeError("Project export exceeds the 512 MiB safety limit")
        query = urllib.parse.urlencode({"path": path})
        raw = api_request(
            "GET",
            f"/v1/command-center/projects/{project_id}/files/content?{query}",
            token,
        )
        digest = hashlib.sha256(raw).hexdigest()
        if len(raw) != size or digest != entry.get("sha256"):
            raise BridgeError(f"Downloaded file failed size or SHA-256 verification: {path}")
        target = files_root.joinpath(*PurePosixPath(path).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        exported.append({"path": path, "byte_size": size, "sha256": digest,
                         "mime_type": entry.get("mime_type")})

    latest = project_manifest(project_id, token)
    if latest.get("head_revision") != manifest.get("head_revision"):
        raise BridgeError("Project changed during export; request a fresh snapshot")
    (export_root / "manifest.json").write_text(
        json.dumps({"project": manifest.get("project"),
                    "head_revision": manifest.get("head_revision"),
                    "files": exported}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    archive = ROOT / "bridge-export.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file in sorted(export_root.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(export_root).as_posix())
    return {"ok": True, "operation": "export", "project_id": project_id,
            "head_revision": manifest["head_revision"], "file_count": len(exported),
            "byte_size": total, "archive": "bridge-export.zip"}


def import_project(request: dict, token: str) -> dict:
    project_id = request.get("project_id")
    base_revision = request.get("base_revision")
    if not isinstance(project_id, str) or not project_id:
        raise BridgeError("project_id is required")
    if not isinstance(base_revision, int) or base_revision < 0:
        raise BridgeError("base_revision is required")
    current = project_manifest(project_id, token)
    if current.get("head_revision") != base_revision:
        raise BridgeError("Project revision changed since the agent exported it; no files were uploaded")

    files = request.get("files", [])
    deletes = request.get("deletes", [])
    if not isinstance(files, list) or not isinstance(deletes, list) or len(files) + len(deletes) > 500:
        raise BridgeError("Import batch must contain at most 500 operations")
    results = []
    total_import_bytes = 0
    for entry in files:
        path = safe_project_path(entry.get("path"))
        payload_parts = entry.get("payload_parts")
        if payload_parts is None:
            payload_parts = [entry.get("payload")]
        if not isinstance(payload_parts, list) or not payload_parts or len(payload_parts) > 256:
            raise BridgeError(f"Payload parts are invalid: {path}")
        encoded = "".join(
            "".join(safe_inbox_file(part).read_text(encoding="ascii").split())
            for part in payload_parts
        )
        try:
            data = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise BridgeError(f"Invalid Base64 payload for {path}") from exc
        if len(data) > MAX_FILE_BYTES or len(data) != int(entry.get("byte_size", -1)):
            raise BridgeError(f"Payload size does not match manifest: {path}")
        total_import_bytes += len(data)
        if total_import_bytes > MAX_TOTAL_IMPORT_BYTES:
            raise BridgeError("Import batch exceeds the 512 MiB safety limit")
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry.get("sha256"):
            raise BridgeError(f"Payload SHA-256 does not match manifest: {path}")
        query = urllib.parse.urlencode({"path": path})
        headers = {
            "Content-Type": entry.get("mime_type") or mimetypes.guess_type(path)[0] or "application/octet-stream",
            "X-File-SHA256": digest,
        }
        base_sha = entry.get("base_sha256")
        if base_sha is not None:
            if not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", base_sha):
                raise BridgeError(f"Invalid base SHA-256 for {path}")
            headers["X-Base-SHA256"] = base_sha
        response = api_request(
            "POST", f"/v1/command-center/projects/{project_id}/files?{query}",
            token, data, headers,
        )
        try:
            saved = json.loads(response)
        except ValueError as exc:
            raise BridgeError(f"Relay returned invalid upload response for {path}") from exc
        if saved.get("sha256") != digest:
            raise BridgeError(f"Relay stored a different SHA-256 for {path}")
        results.append({"path": path, "sha256": digest, "revision": saved.get("revision")})

    for entry in deletes:
        path = safe_project_path(entry.get("path"))
        base_sha = entry.get("base_sha256")
        if not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", base_sha):
            raise BridgeError(f"Delete operation is missing a valid base hash: {path}")
        query = urllib.parse.urlencode({"path": path})
        response = api_request(
            "POST", f"/v1/command-center/projects/{project_id}/files/delete?{query}",
            token, None, {"X-Base-SHA256": base_sha},
        )
        deleted = json.loads(response)
        results.append({"path": path, "deleted": deleted.get("deleted"),
                        "revision": deleted.get("revision")})

    latest = project_manifest(project_id, token)
    return {"ok": True, "operation": "import", "project_id": project_id,
            "base_revision": base_revision, "head_revision": latest.get("head_revision"),
            "operations": results}


def main() -> int:
    token = os.environ.get("RELAY_DEVICE_TOKEN", "")
    if not token:
        raise BridgeError("RELAY_DEVICE_TOKEN was not supplied by the workflow")
    request_path = INBOX / "request.json"
    if not request_path.is_file():
        raise BridgeError("bridge-inbox/request.json is missing")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    operation = request.get("operation")
    if operation == "export":
        result = export_project(request, token)
    elif operation == "import":
        result = import_project(request, token)
    else:
        raise BridgeError("operation must be export or import")
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        RESULT_PATH.write_text(json.dumps({
            "ok": False, "error": type(exc).__name__, "message": str(exc)
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"::error::{type(exc).__name__}: {exc}", file=sys.stderr)
        raise
