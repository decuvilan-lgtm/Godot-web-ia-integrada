"""Integrity-checked artifact packaging and presigned-URL transfer for the A/B bridge.

This module deliberately knows nothing about credentials or storage providers. A trusted
control-plane endpoint issues short-lived HTTPS URLs; clients transfer bytes directly.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
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
        import re
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
    if len(data) > MAX_COMPRESSED_BYTES or len(data) != manifest.get("size_bytes"):
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Presigned URLs are single-origin capabilities; redirects are never followed."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirect refused for signed URL", headers, fp)
