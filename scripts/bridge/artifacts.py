"""Integrity-checked artifact packaging and presigned-URL transfer for the A/B bridge.

This module deliberately knows nothing about credentials or storage providers. A trusted
control-plane endpoint issues short-lived HTTPS URLs; clients transfer bytes directly.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

PROTOCOL_VERSION = 1
MAX_COMPRESSED_BYTES = 64 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
ALLOWED_KINDS = {
    "context_bundle", "scene_tree", "inspector_dump", "screenshot",
    "video", "project_archive", "logs", "animation_frames", "command_result",
}


class ArtifactError(ValueError):
    """Invalid, oversized, or corrupted artifact."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_transfer_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ArtifactError("Artifact transfer requires a credential-free HTTPS URL")
    if parsed.fragment:
        raise ArtifactError("Artifact transfer URL must not contain a fragment")


def pack_json_artifact(
    payload: Any,
    *,
    session_id: str,
    kind: str = "context_bundle",
    artifact_id: str | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Serialize JSON deterministically, gzip it, and return bytes plus manifest."""
    if kind not in ALLOWED_KINDS:
        raise ArtifactError("Unsupported artifact kind")
    if not isinstance(session_id, str) or not session_id or len(session_id) > 128:
        raise ArtifactError("A bounded session_id is required")
    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError):
        # Existing browser session IDs may be human-readable; constrain their alphabet.
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", session_id):
            raise ArtifactError("Invalid session_id")
    artifact_id = artifact_id or str(uuid.uuid4())
    try:
        uuid.UUID(artifact_id)
    except (ValueError, AttributeError) as exc:
        raise ArtifactError("artifact_id must be a UUID") from exc

    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_UNCOMPRESSED_BYTES:
        raise ArtifactError("Uncompressed artifact exceeds the configured limit")
    packed = gzip.compress(raw, compresslevel=6, mtime=0)
    if len(packed) > MAX_COMPRESSED_BYTES:
        raise ArtifactError("Compressed artifact exceeds the configured limit")
    manifest = {
        "protocol_version": PROTOCOL_VERSION,
        "artifact_id": artifact_id,
        "session_id": session_id,
        "kind": kind,
        "content_type": "application/gzip",
        "encoding": "gzip",
        "size_bytes": len(packed),
        "uncompressed_size_bytes": len(raw),
        "sha256": _sha256(packed),
        "uncompressed_sha256": _sha256(raw),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return packed, manifest


def unpack_json_artifact(data: bytes, manifest: dict[str, Any]) -> Any:
    """Verify compressed and expanded sizes/hashes before decoding JSON."""
    if not isinstance(manifest, dict) or manifest.get("protocol_version") != PROTOCOL_VERSION:
        raise ArtifactError("Unsupported artifact manifest")
    if manifest.get("encoding") != "gzip" or manifest.get("content_type") != "application/gzip":
        raise ArtifactError("Unexpected artifact encoding or content type")
    if manifest.get("kind") not in ALLOWED_KINDS:
        raise ArtifactError("Unsupported artifact kind")
    compressed_size = manifest.get("size_bytes")
    expanded_size = manifest.get("uncompressed_size_bytes")
    if (not isinstance(compressed_size, int) or isinstance(compressed_size, bool)
            or not 0 <= compressed_size <= MAX_COMPRESSED_BYTES):
        raise ArtifactError("Invalid compressed size in manifest")
    if (not isinstance(expanded_size, int) or isinstance(expanded_size, bool)
            or not 0 <= expanded_size <= MAX_UNCOMPRESSED_BYTES):
        raise ArtifactError("Invalid expanded size in manifest")
    if not re.fullmatch(r"[a-f0-9]{64}", str(manifest.get("sha256", ""))):
        raise ArtifactError("Invalid compressed SHA-256 in manifest")
    if not re.fullmatch(r"[a-f0-9]{64}", str(manifest.get("uncompressed_sha256", ""))):
        raise ArtifactError("Invalid expanded SHA-256 in manifest")
    try:
        uuid.UUID(manifest.get("artifact_id", ""))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ArtifactError("Invalid artifact_id in manifest") from exc
    if len(data) != compressed_size:
        raise ArtifactError("Artifact byte length does not match its manifest")
    if _sha256(data) != manifest.get("sha256"):
        raise ArtifactError("Artifact SHA-256 mismatch")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as stream:
            raw = stream.read(MAX_UNCOMPRESSED_BYTES + 1)
    except (OSError, EOFError) as exc:
        raise ArtifactError("Artifact gzip stream is invalid") from exc
    if len(raw) > MAX_UNCOMPRESSED_BYTES or len(raw) != manifest.get("uncompressed_size_bytes"):
        raise ArtifactError("Expanded artifact size does not match its manifest")
    if _sha256(raw) != manifest.get("uncompressed_sha256"):
        raise ArtifactError("Expanded artifact SHA-256 mismatch")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactError("Artifact does not contain valid UTF-8 JSON") from exc


def upload_artifact(url: str, data: bytes, *, content_type: str = "application/gzip", timeout: int = 60) -> None:
    """PUT bytes to a short-lived presigned URL; never logs or returns the URL."""
    _validate_transfer_url(url)
    if len(data) > MAX_COMPRESSED_BYTES:
        raise ArtifactError("Artifact exceeds the upload limit")
    request = urllib.request.Request(
        url, data=data, method="PUT",
        headers={"Content-Type": content_type, "Content-Length": str(len(data))},
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status not in (200, 201, 204):
                raise ArtifactError(f"Artifact upload returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        raise ArtifactError(f"Artifact upload failed with HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ArtifactError("Artifact upload failed before completion") from exc


def download_artifact(url: str, manifest: dict[str, Any], *, timeout: int = 60) -> bytes:
    """GET and verify byte-level metadata; call unpack_json_artifact for JSON payloads."""
    _validate_transfer_url(url)
    expected = manifest.get("size_bytes") if isinstance(manifest, dict) else None
    if not isinstance(expected, int) or isinstance(expected, bool) or not 0 <= expected <= MAX_COMPRESSED_BYTES:
        raise ArtifactError("Invalid artifact size in manifest")
    request = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            data = response.read(MAX_COMPRESSED_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise ArtifactError(f"Artifact download failed with HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ArtifactError("Artifact download failed before completion") from exc
    if len(data) != expected or len(data) > MAX_COMPRESSED_BYTES:
        raise ArtifactError("Downloaded artifact length does not match its manifest")
    if _sha256(data) != manifest.get("sha256"):
        raise ArtifactError("Downloaded artifact SHA-256 mismatch")
    return data


def _control_request(api_base: str, token: str, path: str, payload: dict[str, Any], *, timeout: int = 20) -> dict[str, Any]:
    """Call the authenticated artifact control-plane API without exposing its bearer token."""
    _validate_transfer_url(api_base)
    parsed = urllib.parse.urlsplit(api_base)
    if parsed.query or parsed.path not in ("", "/") or not isinstance(path, str) or not path.startswith("/"):
        raise ArtifactError("Invalid artifact control-plane endpoint")
    if not isinstance(token, str) or not token or len(token) > 4096 or any(ch.isspace() for ch in token):
        raise ArtifactError("A valid device bearer token is required")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        api_base.rstrip("/") + path,
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ArtifactError("Artifact control response is too large")
    except urllib.error.HTTPError as exc:
        raise ArtifactError("Artifact control request failed with HTTP " + str(exc.code)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ArtifactError("Artifact control request failed before completion") from exc
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactError("Artifact control response is not valid JSON") from exc
    if not isinstance(result, dict):
        raise ArtifactError("Artifact control response must be a JSON object")
    return result


def upload_json_artifact(
    api_base: str,
    token: str,
    payload: Any,
    *,
    session_id: str,
    kind: str = "context_bundle",
    timeout: int = 60,
) -> dict[str, Any]:
    """Request a scoped upload URL, upload bytes, and finalize the manifest."""
    packed, manifest = pack_json_artifact(payload, session_id=session_id, kind=kind)
    authorization = _control_request(api_base, token, "/v1/artifacts/upload-url", {"manifest": manifest})
    upload_url = authorization.get("upload_url")
    returned_id = authorization.get("artifact_id")
    if not isinstance(upload_url, str) or returned_id != manifest["artifact_id"]:
        raise ArtifactError("Artifact API returned an invalid upload authorization")
    upload_artifact(upload_url, packed, content_type=manifest["content_type"], timeout=timeout)
    finalized = _control_request(
        api_base, token, "/v1/artifacts/finalize",
        {"artifact_id": manifest["artifact_id"], "sha256": manifest["sha256"]},
    )
    if finalized.get("status") != "ready" or finalized.get("artifact_id") != manifest["artifact_id"]:
        raise ArtifactError("Artifact API did not confirm successful finalization")
    return {"artifact_id": manifest["artifact_id"], "manifest": manifest}


def download_json_artifact(
    api_base: str,
    token: str,
    artifact_id: str,
    *,
    timeout: int = 60,
) -> Any:
    """Request a session-scoped download URL and verify the full artifact before decoding."""
    try:
        uuid.UUID(artifact_id)
    except (ValueError, AttributeError) as exc:
        raise ArtifactError("artifact_id must be a UUID") from exc
    authorization = _control_request(
        api_base, token, "/v1/artifacts/download-url", {"artifact_id": artifact_id},
    )
    manifest = authorization.get("manifest")
    download_url = authorization.get("download_url")
    if not isinstance(manifest, dict) or manifest.get("artifact_id") != artifact_id or not isinstance(download_url, str):
        raise ArtifactError("Artifact API returned an invalid download authorization")
    packed = download_artifact(download_url, manifest, timeout=timeout)
    return unpack_json_artifact(packed, manifest)



def request_github_actions_oidc_token(*, audience: str = "godot-abbridge") -> str:
    """Request a short-lived GitHub Actions OIDC JWT without logging its value."""
    request_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    request_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    parsed = urllib.parse.urlsplit(request_url)
    if (parsed.scheme != "https" or not parsed.hostname
            or not parsed.hostname.endswith(".actions.githubusercontent.com")
            or not request_token):
        raise ArtifactError("GitHub Actions OIDC identity is unavailable")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("audience", audience))
    url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), ""))
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + request_token})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read(128 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ArtifactError("GitHub Actions OIDC request failed") from exc
    if len(raw) > 128 * 1024:
        raise ArtifactError("GitHub Actions OIDC response is too large")
    try:
        value = json.loads(raw.decode("utf-8")).get("value")
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
        raise ArtifactError("GitHub Actions OIDC response is invalid") from exc
    if not isinstance(value, str) or not value or len(value) > 16_384:
        raise ArtifactError("GitHub Actions did not return an OIDC token")
    return value


def issue_transport_device_token(
    api_base: str,
    oidc_token: str,
    *,
    expected_kind: str,
) -> str:
    """Exchange a verified GitHub workflow identity for a two-hour device token."""
    if expected_kind not in {"web_editor", "agent_controller"}:
        raise ArtifactError("Unsupported expected device role")
    result = _control_request(api_base, oidc_token, "/v1/devices/issue", {})
    if result.get("device_kind") != expected_kind:
        raise ArtifactError("Device provisioning returned an unexpected role")
    token = result.get("device_token")
    if not isinstance(token, str) or len(token) < 32:
        raise ArtifactError("Device provisioning returned an invalid token")
    return token


def create_transport_session(api_base: str, token: str) -> dict[str, Any]:
    """Create a durable session from a web_editor or android_editor device."""
    result = _control_request(api_base, token, "/v1/sessions", {})
    if not isinstance(result.get("session_id"), str):
        raise ArtifactError("Session API returned an invalid session identifier")
    try:
        uuid.UUID(result["session_id"])
    except ValueError as exc:
        raise ArtifactError("Session API returned an invalid session identifier") from exc
    return result


def join_transport_session(api_base: str, token: str, session_id: str) -> dict[str, Any]:
    """Join a session from an agent_controller or android_editor device."""
    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError) as exc:
        raise ArtifactError("session_id must be a UUID") from exc
    result = _control_request(api_base, token, "/v1/sessions/join", {"session_id": session_id})
    if result.get("session_id") != session_id:
        raise ArtifactError("Session API joined a different session")
    return result


def heartbeat_transport_session(api_base: str, token: str, session_id: str) -> dict[str, Any]:
    """Refresh session activity and expiry for a participating device."""
    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError) as exc:
        raise ArtifactError("session_id must be a UUID") from exc
    result = _control_request(api_base, token, "/v1/sessions/heartbeat", {"session_id": session_id})
    if result.get("session_id") != session_id:
        raise ArtifactError("Session heartbeat refers to a different session")
    return result


def enqueue_transport_command(
    api_base: str,
    token: str,
    *,
    session_id: str,
    target: str,
    action: str,
    args: dict[str, Any],
    idempotency_key: str,
    priority: int = 0,
    ttl_seconds: int = 300,
) -> dict[str, Any]:
    """Persist a small A/B command; large context/results should be artifact references."""
    if not isinstance(args, dict):
        raise ArtifactError("Command args must be an object")
    result = _control_request(api_base, token, "/v1/commands/enqueue", {
        "session_id": session_id, "target": target, "action": action,
        "args": args, "idempotency_key": idempotency_key,
        "priority": priority, "ttl_seconds": ttl_seconds,
    })
    command = result.get("command")
    if not isinstance(command, dict) or not isinstance(command.get("id"), str):
        raise ArtifactError("Command API returned an invalid enqueue response")
    return command


def claim_transport_command(
    api_base: str,
    token: str,
    session_id: str,
    *,
    wait_ms: int = 10_000,
) -> dict[str, Any] | None:
    """Long-poll for one command; the server checks its durable queue every 250 ms."""
    if not isinstance(wait_ms, int) or isinstance(wait_ms, bool) or not 0 <= wait_ms <= 10_000:
        raise ArtifactError("wait_ms must be an integer between 0 and 10000")
    result = _control_request(
        api_base, token, "/v1/commands/claim",
        {"session_id": session_id, "wait_ms": wait_ms},
        timeout=20,
    )
    command = result.get("command")
    if command is not None and not isinstance(command, dict):
        raise ArtifactError("Command API returned an invalid claim response")
    return command


def start_transport_command(api_base: str, token: str, command_id: str) -> dict[str, Any]:
    result = _control_request(api_base, token, "/v1/commands/start", {"command_id": command_id})
    command = result.get("command")
    if not isinstance(command, dict) or command.get("id") != command_id:
        raise ArtifactError("Command API returned an invalid start response")
    return command


def renew_transport_command_lease(api_base: str, token: str, command_id: str) -> dict[str, Any]:
    result = _control_request(api_base, token, "/v1/commands/lease", {"command_id": command_id})
    command = result.get("command")
    if not isinstance(command, dict) or command.get("id") != command_id:
        raise ArtifactError("Command API returned an invalid lease response")
    return command


def complete_transport_command(
    api_base: str,
    token: str,
    command_id: str,
    *,
    ok: bool,
    result: dict[str, Any],
    duration_ms: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    response = _control_request(api_base, token, "/v1/commands/complete", {
        "command_id": command_id, "ok": ok, "result": result,
        "duration_ms": duration_ms, "error_code": error_code,
        "error_message": error_message,
    })
    if response.get("command_id") != command_id or response.get("status") not in {"succeeded", "failed"}:
        raise ArtifactError("Command API returned an invalid completion response")
    return response


def fetch_transport_command_result(api_base: str, token: str, command_id: str) -> dict[str, Any] | None:
    """Poll a command result visible only to the originating device."""
    try:
        uuid.UUID(command_id)
    except (ValueError, AttributeError) as exc:
        raise ArtifactError("command_id must be a UUID") from exc
    response = _control_request(api_base, token, "/v1/commands/result", {"command_id": command_id})
    if response.get("ready") is not True:
        return None
    if response.get("status") not in {"succeeded", "failed"} or not isinstance(response.get("result"), dict):
        raise ArtifactError("Command result API returned an invalid completed result")
    return response


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Presigned URLs are single-origin capabilities; redirects are never followed."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirect refused for signed URL", headers, fp)
