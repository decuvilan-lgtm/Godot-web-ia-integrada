from __future__ import annotations

import asyncio
import hmac
import hashlib
import io
import json
import logging
import os
import re
import secrets
import subprocess
import time
import threading
import zipfile
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from visual_storage import BUCKET, storage_client
from project_profiles import MANIFEST_PATH, execute_profile_command, load_project_profile, resolve_repository_commit_sha

logger = logging.getLogger("godot_web_ia_persistent_sessions")
router = APIRouter(prefix="/v1/persistent-sessions", tags=["persistent-sessions"])

EDITOR_URL = os.environ.get(
    "GODOT_WEB_EDITOR_URL",
    "https://godot-web-ia-integrada-rt2l.onrender.com/",
).rstrip("/") + "/"
SESSION_TOKEN = os.environ.get("PERSISTENT_SESSION_TOKEN", "")
OIDC_AUDIENCE = os.environ.get("PERSISTENT_SESSION_OIDC_AUDIENCE", "godot-web-ia-relay")
OIDC_REPOSITORY = os.environ.get("PERSISTENT_SESSION_OIDC_REPOSITORY", "decuvilan-lgtm/Godot-web-ia-integrada")
OIDC_WORKFLOW = os.environ.get("PERSISTENT_SESSION_OIDC_WORKFLOW", ".github/workflows/persistent-session-smoke.yml")
# Only explicitly named workflows in this repository/ref may mint worker identities.
# The browser bridge is a second, separately allowlisted workflow; no branch-wide
# or arbitrary workflow identity is accepted.
OIDC_ADDITIONAL_WORKFLOWS = tuple(
    item.strip()
    for item in os.environ.get(
        "PERSISTENT_SESSION_OIDC_ADDITIONAL_WORKFLOWS",
        ".github/workflows/chatgpt-browser-bridge.yml,"
        ".github/workflows/persistent-session-operator.yml,"
        ".github/workflows/persistent-session-host.yml",
    ).split(",")
    if item.strip()
)
OIDC_REF = os.environ.get("PERSISTENT_SESSION_OIDC_REF", "refs/heads/main")
_oidc_jwks_client = None
_oidc_jwks_lock = threading.Lock()
# Default wall-clock lifetime; each session can override this when opened.
DEFAULT_SESSION_DURATION_SECONDS = max(60, min(86400, int(os.environ.get("PERSISTENT_SESSION_DEFAULT_DURATION_SECONDS", "600"))))
MIN_SESSION_DURATION_SECONDS = 60
MAX_SESSION_DURATION_SECONDS = 86400
# Idle cleanup must never pre-empt a session's explicitly selected maximum duration.
IDLE_TTL = max(MAX_SESSION_DURATION_SECONDS, int(os.environ.get("PERSISTENT_SESSION_IDLE_TTL_SECONDS", "86400")))
MAX_SESSIONS = max(1, int(os.environ.get("PERSISTENT_SESSION_MAX_COUNT", "2")))
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_SESSION_ARTIFACT_BYTES = 24 * 1024 * 1024
REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,128}$")

@dataclass
class PersistentSession:
    session_id: str
    repository: str
    branch: str
    project_path: str
    commit_sha: str | None = None
    max_duration_seconds: int = DEFAULT_SESSION_DURATION_SECONDS
    created_at: float | None = None
    loading_started_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    context: Any = None
    page: Any = None
    events: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, bytes] = field(default_factory=dict)
    completed_tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

_sessions: dict[str, PersistentSession] = {}
_browser: Any = None
_browser_lock = asyncio.Lock()
_reaper_task: asyncio.Task | None = None
_readiness_tasks: set[asyncio.Task] = set()

class OpenSessionRequest(BaseModel):
    repository: str = Field(min_length=3, max_length=140)
    branch: str = Field(default="main", min_length=1, max_length=128)
    project_path: str = Field(default="", max_length=240)
    commit_sha: str | None = Field(default=None, min_length=40, max_length=64)
    reuse_existing: bool = True
    reimport_existing: bool = False
    duration_seconds: int = Field(default=DEFAULT_SESSION_DURATION_SECONDS, ge=MIN_SESSION_DURATION_SECONDS, le=MAX_SESSION_DURATION_SECONDS)

class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=32)
    text: str | None = Field(default=None, max_length=5000)
    key: str | None = Field(default=None, max_length=32)
    x: float | None = Field(default=None, ge=0, le=10000)
    y: float | None = Field(default=None, ge=0, le=10000)
    end_x: float | None = Field(default=None, ge=0, le=10000)
    end_y: float | None = Field(default=None, ge=0, le=10000)
    delta_x: float = Field(default=0, ge=-10000, le=10000)
    delta_y: float = Field(default=0, ge=-10000, le=10000)
    button: str = Field(default="left", max_length=10)
    timeout_ms: int = Field(default=10000, ge=100, le=30000)

class CompleteTaskRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=100)
    summary: str = Field(default="", max_length=4000)
    result: dict[str, Any] = Field(default_factory=dict)

def _validate_github_oidc_claims(claims: dict[str, Any]) -> None:
    allowed_workflows = (OIDC_WORKFLOW, *OIDC_ADDITIONAL_WORKFLOWS)
    allowed_workflow_refs = {
        f"{OIDC_REPOSITORY}/{workflow}@{OIDC_REF}"
        for workflow in allowed_workflows
    }
    if (
        claims.get("repository") != OIDC_REPOSITORY
        or claims.get("ref") != OIDC_REF
        or claims.get("workflow_ref") not in allowed_workflow_refs
    ):
        raise ValueError("GitHub Actions identity is not allowed for persistent sessions")


def _verify_github_oidc_token(token: str) -> None:
    try:
        import jwt
    except ImportError:
        raise
    global _oidc_jwks_client
    if _oidc_jwks_client is None:
        with _oidc_jwks_lock:
            if _oidc_jwks_client is None:
                _oidc_jwks_client = jwt.PyJWKClient(
                    "https://token.actions.githubusercontent.com/.well-known/jwks",
                    cache_keys=True,
                )
    signing_key = _oidc_jwks_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=OIDC_AUDIENCE,
        issuer="https://token.actions.githubusercontent.com",
        options={"require": ["exp", "iat", "nbf", "sub"]},
    )
    _validate_github_oidc_claims(claims)


async def _authorize(value: str | None) -> None:
    if not value:
        raise HTTPException(status_code=401, detail="Authorization is required")
    supplied = value.removeprefix("Bearer ").strip()
    if len(supplied) > 16000:
        raise HTTPException(status_code=401, detail="Invalid authorization token")
    if SESSION_TOKEN and hmac.compare_digest(supplied, SESSION_TOKEN):
        return
    try:
        await run_in_threadpool(_verify_github_oidc_token, supplied)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Persistent-session authentication is not configured") from exc
    except Exception as exc:
        logger.info("Rejected persistent-session identity: %s", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid persistent-session identity") from exc

def _store_session_artifact(session: PersistentSession, name: str, data: bytes) -> None:
    current_size = sum(len(item) for item in session.artifacts.values())
    if len(data) > MAX_SESSION_ARTIFACT_BYTES or current_size + len(data) > MAX_SESSION_ARTIFACT_BYTES:
        raise HTTPException(status_code=413, detail="Session screenshot artifacts exceed the 24 MiB limit")
    session.artifacts[name] = data


def _touch(session: PersistentSession) -> None:
    session.last_activity = time.time()

def _session_remaining_seconds(session: PersistentSession, now: float | None = None) -> int | None:
    if session.created_at is None:
        return None
    current = time.time() if now is None else now
    return max(0, int(session.max_duration_seconds - (current - session.created_at)))


def _get_session(session_id: str) -> PersistentSession:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Persistent session not found")
    now = time.time()
    if session.created_at is not None and now - session.created_at >= session.max_duration_seconds:
        raise HTTPException(status_code=410, detail="Persistent session reached its configured maximum lifetime")
    if now - session.last_activity > IDLE_TTL:
        raise HTTPException(status_code=410, detail="Persistent session expired after inactivity")
    return session

async def _get_browser():
    """Return the single shared Chromium process.

    Chromium must be installed during the Render build. Installing it on the
    first request creates a large transient memory spike in the 512 MiB Free
    instance and can kill the API process while a task is running.
    """
    global _browser
    async with _browser_lock:
        if _browser is None or not _browser.is_connected():
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise HTTPException(status_code=503, detail="Playwright is not installed on this relay") from exc
            if not hasattr(_get_browser, "_playwright"):
                _get_browser._playwright = await async_playwright().start()
            launch_args = {
                "headless": True,
                "args": [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--disable-sync",
                    "--disable-translate",
                    "--disable-features=Translate,BackForwardCache,AcceptCHFrame,MediaRouter",
                    "--renderer-process-limit=1",
                    "--js-flags=--max-old-space-size=128",
                ],
            }
            try:
                _browser = await _get_browser._playwright.chromium.launch(**launch_args)
            except Exception as exc:
                logger.exception("Could not start preinstalled persistent Chromium")
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Persistent Chromium is unavailable. Install it during the Render build "
                        "with: python -m playwright install chromium"
                    ),
                ) from exc
        return _browser

async def _close_session(session: PersistentSession) -> None:
    try:
        if session.context is not None:
            await session.context.close()
    except Exception:
        logger.exception("Could not close expired browser context")
    _sessions.pop(session.session_id, None)


async def _wait_for_editor_ready(session: PersistentSession, expected_sha: str) -> None:
    """Mark a session ready only after the exact project revision and canvas exist."""
    started = time.monotonic()
    readiness: dict[str, Any] = {
        "phase": "waiting",
        "imported_sha": "",
        "expected_sha": expected_sha,
        "canvas_count": 0,
        "connector_error": "",
        "connector_bytes": 0,
        "connector_filename": "",
        "connector_start_button_disabled": None,
        "connector_start_button_text": "",
        "connector_zip_input_files": 0,
        "connector_buttons": [],
        "connector_inputs": [],
        "connector_body_text": "",
    }
    try:
        while time.monotonic() - started < 480:
            if session.page is None or session.page.is_closed():
                logger.error("Godot editor session %s closed before readiness: %s", session.session_id, readiness)
                await _close_session(session)
                return
            connector = await session.page.evaluate("() => window.__godotGithubConnectorStatus || null")
            canvas_count = await session.page.locator("canvas").count()
            readiness = {
                "phase": (connector or {}).get("phase", "unknown"),
                "imported_sha": (connector or {}).get("commitSha", ""),
                "expected_sha": expected_sha,
                "canvas_count": canvas_count,
                "connector_error": (connector or {}).get("error", ""),
                "connector_bytes": (connector or {}).get("bytes", 0),
                "connector_filename": (connector or {}).get("filename", ""),
                "connector_start_button_disabled": (connector or {}).get("startButtonDisabled"),
                "connector_start_button_text": (connector or {}).get("startButtonText", ""),
                "connector_zip_input_files": (connector or {}).get("zipInputFiles", 0),
                "connector_buttons": (connector or {}).get("buttons", []),
                "connector_inputs": (connector or {}).get("inputs", []),
                "connector_body_text": (connector or {}).get("bodyText", "")[:1200],
                "elapsed_seconds": round(time.monotonic() - started, 1),
            }
            if readiness["phase"] == "failed":
                session.events.append({"type": "session.editor_connector_failed", "at": time.time(), **readiness})
                logger.error("Godot editor connector failed for session %s: %s", session.session_id, readiness)
                await _close_session(session)
                return
            if readiness["phase"] == "started" and readiness["imported_sha"] == expected_sha and canvas_count >= 1:
                session.created_at = time.time()
                session.last_activity = session.created_at
                session.events.append({"type": "session.editor_ready", "at": session.created_at, **readiness})
                logger.info("Godot editor session %s is ready for %s", session.session_id, expected_sha)
                return
            await session.page.wait_for_timeout(5000)
        logger.error("Godot editor session %s did not become ready: %s", session.session_id, readiness)
    except Exception:
        logger.exception("Godot editor readiness monitor failed for session %s; last state: %s", session.session_id, readiness)
    await _close_session(session)


async def _expire_loop() -> None:
    while True:
        now = time.time()
        for session in list(_sessions.values()):
            loading_expired = session.created_at is None and now - session.loading_started_at > 480
            duration_expired = session.created_at is not None and now - session.created_at >= session.max_duration_seconds
            idle_expired = now - session.last_activity > IDLE_TTL
            if loading_expired or duration_expired or idle_expired:
                await _close_session(session)
        # Check frequently so the configured close is not delayed materially.
        await asyncio.sleep(5)

@router.on_event("startup")
async def start_session_reaper():
    global _reaper_task
    _reaper_task = asyncio.create_task(_expire_loop())

@router.on_event("shutdown")
async def stop_session_reaper():
    global _reaper_task
    task = _reaper_task
    _reaper_task = None
    if task:
        task.cancel()
    readiness_tasks = list(_readiness_tasks)
    for readiness_task in readiness_tasks:
        readiness_task.cancel()
    if readiness_tasks:
        await asyncio.gather(*readiness_tasks, return_exceptions=True)
    _readiness_tasks.clear()
    for session in list(_sessions.values()):
        await _close_session(session)
    global _browser
    if _browser is not None:
        await _browser.close()
        _browser = None
    playwright = getattr(_get_browser, "_playwright", None)
    if playwright is not None:
        await playwright.stop()

@router.get("")
async def list_persistent_sessions(authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    return {
        "sessions": [
            {
                "session_id": session.session_id,
                "repository": session.repository,
                "branch": session.branch,
                "project_path": session.project_path,
                "commit_sha": session.commit_sha,
                "created_at": session.created_at,
                "last_activity_at": session.last_activity,
                "expires_at": session.created_at + session.max_duration_seconds if session.created_at is not None else None,
                "max_duration_seconds": session.max_duration_seconds,
                "remaining_seconds": _session_remaining_seconds(session),
                "state": ("loading" if session.created_at is None else "open") if session.page is not None and not session.page.is_closed() else "disconnected",
            }
            for session in _sessions.values()
        ]
    }


def _editor_url_for(repository: str, branch: str, project_path: str, commit_sha: str | None) -> str:
    query = f"?repo={quote(repository, safe='/')}&branch={quote(branch, safe='')}"
    if project_path:
        query += f"&path={quote(project_path, safe='/')}"
    if commit_sha:
        query += f"&sha={quote(commit_sha, safe='')}"
    return EDITOR_URL + query


@router.post("")
async def open_persistent_session(body: OpenSessionRequest, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    if not REPO_RE.fullmatch(body.repository):
        raise HTTPException(status_code=400, detail="repository must be OWNER/REPOSITORY")
    if not BRANCH_RE.fullmatch(body.branch) or body.branch.startswith("/") or body.branch.endswith("/") or ".." in body.branch:
        raise HTTPException(status_code=400, detail="Invalid branch")
    if body.project_path and (
        body.project_path.startswith("/") or body.project_path.endswith("/")
        or "\\" in body.project_path
        or any(part in {"", ".", ".."} for part in body.project_path.split("/"))
    ):
        raise HTTPException(status_code=400, detail="Invalid project_path")
    if body.commit_sha and not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", body.commit_sha):
        raise HTTPException(status_code=400, detail="commit_sha must be a full 40- or 64-character hexadecimal Git object ID")
    effective_sha = body.commit_sha or await resolve_repository_commit_sha(body.repository, body.branch)
    now = time.time()
    for existing in list(_sessions.values()):
        loading_expired = existing.created_at is None and now - existing.loading_started_at > 480
        duration_expired = existing.created_at is not None and now - existing.created_at >= existing.max_duration_seconds
        if (existing.page is None or existing.page.is_closed()
                or loading_expired or duration_expired
                or now - existing.last_activity > IDLE_TTL):
            await _close_session(existing)
            continue
        same_project = (
            existing.repository == body.repository
            and existing.branch == body.branch
            and existing.project_path == body.project_path
            and existing.commit_sha == effective_sha
        )
        if body.reuse_existing and same_project:
            _touch(existing)
            existing.events.append({"type": "session.reused", "at": time.time(), "task_repository": body.repository})
            return {
                "session_id": existing.session_id,
                "state": "loading" if existing.created_at is None else "open",
                "ready": existing.created_at is not None,
                "editor_url": EDITOR_URL,
                "repository": existing.repository,
                "branch": existing.branch,
                "project_path": existing.project_path,
                "commit_sha": existing.commit_sha,
                "idle_ttl_seconds": IDLE_TTL,
                "max_duration_seconds": existing.max_duration_seconds,
                "expires_at": existing.created_at + existing.max_duration_seconds if existing.created_at is not None else None,
                "remaining_seconds": _session_remaining_seconds(existing),
                "reused": True,
                "reimported": False,
                "reused_for_follow_up_tasks": True,
                "note": "The existing browser and editor page were reused; the session remains open.",
            }
        if body.reuse_existing and body.reimport_existing and existing.repository == body.repository:
            if existing.created_at is None:
                raise HTTPException(status_code=409, detail="The existing editor session is still importing its project")
            previous = {
                "branch": existing.branch,
                "project_path": existing.project_path,
                "commit_sha": existing.commit_sha,
            }
            try:
                await existing.page.goto(
                    _editor_url_for(body.repository, body.branch, body.project_path, effective_sha),
                    wait_until="domcontentloaded",
                    timeout=90000,
                )
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Could not re-import project into the existing browser: {type(exc).__name__}") from exc
            existing.branch = body.branch
            existing.project_path = body.project_path
            existing.commit_sha = effective_sha
            existing.artifacts.clear()
            existing.events.append({
                "type": "session.reimported",
                "at": time.time(),
                "previous": previous,
                "repository": body.repository,
                "branch": body.branch,
                "project_path": body.project_path,
                "commit_sha": effective_sha,
            })
            _touch(existing)
            return {
                "session_id": existing.session_id,
                "state": "open",
                "editor_url": EDITOR_URL,
                "repository": existing.repository,
                "branch": existing.branch,
                "project_path": existing.project_path,
                "commit_sha": existing.commit_sha,
                "idle_ttl_seconds": IDLE_TTL,
                "max_duration_seconds": existing.max_duration_seconds,
                "expires_at": existing.created_at + existing.max_duration_seconds,
                "remaining_seconds": _session_remaining_seconds(existing),
                "reused": True,
                "reimported": True,
                "reused_for_follow_up_tasks": True,
                "note": "The same browser context was kept open and the selected project revision was re-imported.",
            }
        raise HTTPException(
            status_code=409,
            detail="An active persistent session already exists for a different project or revision. Reuse that project or close the session first.",
        )
    if len(_sessions) >= MAX_SESSIONS:
        raise HTTPException(status_code=429, detail="Persistent session capacity reached")
    browser = await _get_browser()
    session_id = secrets.token_urlsafe(18)
    session = PersistentSession(
        session_id=session_id,
        repository=body.repository,
        branch=body.branch,
        project_path=body.project_path,
        commit_sha=effective_sha,
        max_duration_seconds=body.duration_seconds,
    )
    try:
        # Keep the Web editor's raster surfaces modest on Render's 512 MiB
        # instance. The editor remains fully interactive; normalized point
        # controls continue to scale with the actual viewport.
        session.context = await browser.new_context(
            viewport={"width": 1024, "height": 640},
            device_scale_factor=1,
            accept_downloads=True,
        )
        session.page = await session.context.new_page()
        session.page.on(
            "console",
            lambda message: logger.warning(
                "Godot editor console error for session %s: %s", session_id, message.text[:1000]
            ) if message.type == "error" else None,
        )
        session.page.on(
            "pageerror",
            lambda error: logger.warning("Godot editor page error for session %s: %s", session_id, error),
        )
        await session.page.goto(_editor_url_for(body.repository, body.branch, body.project_path, effective_sha), wait_until="domcontentloaded", timeout=90000)

        session.events.append({
            "type": "session.opened",
            "at": time.time(),
            "editor_url": EDITOR_URL,
            "repository": body.repository,
            "branch": body.branch,
            "project_path": body.project_path,
            "commit_sha": effective_sha,
            "duration_seconds": body.duration_seconds,
        })
        session.loading_started_at = time.time()
        _sessions[session_id] = session
        readiness_task = asyncio.create_task(_wait_for_editor_ready(session, effective_sha))
        _readiness_tasks.add(readiness_task)
        readiness_task.add_done_callback(_readiness_tasks.discard)
    except HTTPException:
        await _close_session(session)
        raise
    except Exception as exc:
        await _close_session(session)
        logger.exception("Persistent editor session could not be opened")
        raise HTTPException(status_code=502, detail=f"Could not open deployed Godot Web editor: {type(exc).__name__}") from exc
    return {
        "session_id": session_id,
        "state": "loading",
        "ready": False,
        "editor_url": EDITOR_URL,
        "repository": body.repository,
        "branch": body.branch,
        "project_path": body.project_path,
        "commit_sha": effective_sha,
        "idle_ttl_seconds": IDLE_TTL,
        "max_duration_seconds": session.max_duration_seconds,
        "expires_at": None,
        "remaining_seconds": None,
        "reused": False,
        "reused_for_follow_up_tasks": True,
        "note": "The session is importing the selected project. Its configured lifetime starts only after the exact commit and editor canvas are confirmed.",
    }

@router.get("/{session_id}")
async def persistent_session_status(session_id: str, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    session = _get_session(session_id)
    _touch(session)
    return {
        "session_id": session_id,
        "state": ("loading" if session.created_at is None else "open") if session.page and not session.page.is_closed() else "disconnected",
        "ready": session.created_at is not None and session.page is not None and not session.page.is_closed(),
        "repository": session.repository,
        "branch": session.branch,
        "project_path": session.project_path,
        "commit_sha": session.commit_sha,
        "last_activity_at": session.last_activity,
        "created_at": session.created_at,
        "expires_at": session.created_at + session.max_duration_seconds if session.created_at is not None else None,
        "max_duration_seconds": session.max_duration_seconds,
        "remaining_seconds": _session_remaining_seconds(session),
        "idle_ttl_seconds": IDLE_TTL,
        "completed_tasks": list(session.completed_tasks.values()),
        "artifact_count": len(session.artifacts),
    }

@router.post("/{session_id}/heartbeat")
async def persistent_session_heartbeat(session_id: str, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    session = _get_session(session_id)
    _touch(session)
    return {"ok": True, "session_id": session_id, "idle_ttl_seconds": IDLE_TTL}

def _validate_mouse_point(page: Any, x: float | None, y: float | None) -> tuple[float, float]:
    if x is None or y is None:
        raise HTTPException(status_code=400, detail="Both x and y coordinates are required")
    viewport = page.viewport_size or {"width": 1024, "height": 640}
    if x >= viewport["width"] or y >= viewport["height"]:
        raise HTTPException(status_code=400, detail="Mouse coordinates are outside the editor viewport")
    return float(x), float(y)


def _assert_profile_matches_session(profile: dict[str, Any], session: PersistentSession) -> None:
    declared_path = profile["manifest"].get("project", {}).get("project_path")
    if declared_path is not None and declared_path != session.project_path:
        raise HTTPException(
            status_code=409,
            detail="Project-owned lab manifest targets a different project_path than the imported project",
        )


@router.get("/{session_id}/profile")
async def get_project_lab_profile(session_id: str, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    session = _get_session(session_id)
    profile = await load_project_profile(session.repository, session.commit_sha or session.branch)
    if profile is None:
        return {
            "available": False,
            "profile_status": "not_found",
            "manifest_path": MANIFEST_PATH,
            "repository": session.repository,
            "ref": session.commit_sha or session.branch,
            "note": "This repository revision has no project-owned Godot lab manifest. No global game-specific commands were substituted.",
        }
    _assert_profile_matches_session(profile, session)
    return {
        "available": True,
        "profile_status": profile["control_profile"]["verification"]["status"],
        "manifest_path": MANIFEST_PATH,
        "repository": session.repository,
        "ref": session.commit_sha or session.branch,
        "project": profile["manifest"]["project"],
        "control_profile": profile["manifest"]["control_profile"],
        "commands": profile["manifest"]["commands"],
        "controls": profile["control_profile"]["controls"],
    }


@router.post("/{session_id}/profiles/{command_name}/run")
async def run_project_lab_command(
    session_id: str,
    command_name: str,
    authorization: str | None = Header(default=None),
):
    await _authorize(authorization)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", command_name):
        raise HTTPException(status_code=400, detail="Invalid project-owned command name")
    session = _get_session(session_id)
    if session.created_at is None:
        raise HTTPException(status_code=409, detail="Godot Web project is still importing; wait until the session state is open")
    if session.page is None or session.page.is_closed():
        raise HTTPException(status_code=409, detail="Editor page is disconnected")
    profile = await load_project_profile(session.repository, session.commit_sha or session.branch, command_name=command_name)
    if profile is None:
        raise HTTPException(status_code=404, detail="This repository revision has no project-owned lab manifest")
    _assert_profile_matches_session(profile, session)
    if profile["control_profile"]["verification"]["status"] != "verified":
        raise HTTPException(status_code=409, detail="Project control profile has not been verified against this exact commit SHA")
    command_profile = profile["commands"].get(command_name)
    if command_profile is None or command_profile["verification"]["status"] != "verified":
        raise HTTPException(status_code=409, detail="Project command has not been verified against this exact commit SHA")
    async with session.lock:
        try:
            results = await asyncio.wait_for(
                execute_profile_command(session.page, profile, command_name, session.artifacts),
                timeout=120,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=504, detail="Project-owned command exceeded the 120-second execution limit") from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Project-owned lab command failed")
            raise HTTPException(status_code=502, detail=f"Project-owned command failed: {type(exc).__name__}") from exc
        session.events.append({
            "type": "project-profile.command.completed",
            "command": command_name,
            "at": time.time(),
            "step_count": len(results),
        })
        session.events = session.events[-1000:]
        _touch(session)
    return {
        "ok": True,
        "session_id": session_id,
        "repository": session.repository,
        "commit_sha": session.commit_sha,
        "command": command_name,
        "results": results,
        "session_kept_open": True,
    }


@router.post("/{session_id}/commands")
async def persistent_session_command(session_id: str, body: CommandRequest, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    session = _get_session(session_id)
    if session.created_at is None:
        raise HTTPException(status_code=409, detail="Godot Web project is still importing; wait until the session state is open")
    if session.page is None or session.page.is_closed():
        raise HTTPException(status_code=409, detail="Editor page is disconnected")
    async with session.lock:
        try:
            if body.command == "screenshot":
                image = await session.page.screenshot(full_page=False, timeout=body.timeout_ms)
                name = f"screenshot-{int(time.time() * 1000)}.png"
                _store_session_artifact(session, name, image)
                output: dict[str, Any] = {"artifact": name, "bytes": len(image)}
            elif body.command == "click_text":
                if not body.text:
                    raise HTTPException(status_code=400, detail="text is required")
                locator = session.page.get_by_text(body.text, exact=True).first
                await locator.click(timeout=body.timeout_ms)
                output = {"clicked_text": body.text}
            elif body.command == "press_key":
                allowed_keys = {
                    "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
                    "Escape", "Enter", "Tab", "Space", "Backspace", "Delete",
                    "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown",
                    "Control+s", "Control+Shift+s", "Control+z", "Control+y", "Control+a",
                    "Control+c", "Control+v", "Control+x", "Control+f", "Control+p",
                    "Shift+F10",
                }
                if body.key not in allowed_keys:
                    raise HTTPException(status_code=400, detail="Key is not in the safe allowlist")
                await session.page.keyboard.press(body.key)
                output = {"pressed_key": body.key}
            elif body.command == "click":
                x, y = _validate_mouse_point(session.page, body.x, body.y)
                if body.button not in {"left", "right", "middle"}:
                    raise HTTPException(status_code=400, detail="Mouse button is not allowed")
                await session.page.mouse.click(x, y, button=body.button)
                output = {"clicked": {"x": x, "y": y, "button": body.button}}
            elif body.command == "type_text":
                if not body.text:
                    raise HTTPException(status_code=400, detail="text is required")
                await session.page.keyboard.insert_text(body.text)
                output = {"typed_characters": len(body.text)}
            elif body.command == "scroll":
                x, y = _validate_mouse_point(session.page, body.x, body.y)
                if body.delta_x == 0 and body.delta_y == 0:
                    raise HTTPException(status_code=400, detail="A non-zero scroll delta is required")
                await session.page.mouse.move(x, y)
                await session.page.mouse.wheel(body.delta_x, body.delta_y)
                output = {"scrolled_at": {"x": x, "y": y}, "delta_x": body.delta_x, "delta_y": body.delta_y}
            elif body.command == "drag":
                x, y = _validate_mouse_point(session.page, body.x, body.y)
                end_x, end_y = _validate_mouse_point(session.page, body.end_x, body.end_y)
                if body.button not in {"left", "right", "middle"}:
                    raise HTTPException(status_code=400, detail="Mouse button is not allowed")
                await session.page.mouse.move(x, y)
                await session.page.mouse.down(button=body.button)
                try:
                    await session.page.mouse.move(end_x, end_y, steps=12)
                finally:
                    await session.page.mouse.up(button=body.button)
                output = {"dragged": {"from": [x, y], "to": [end_x, end_y], "button": body.button}}
            elif body.command == "inspect":
                output = {
                    "url": session.page.url,
                    "title": await session.page.title(),
                    "visible_text": (await session.page.locator("body").inner_text(timeout=body.timeout_ms))[:12000],
                    "canvas_count": await session.page.locator("canvas").count(),
                    "viewport_size": session.page.viewport_size,
                    "canvas_bounds": await session.page.locator("canvas").evaluate_all("(items) => items.slice(0, 12).map((item) => { const r = item.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; })"),
                    "connector_status": await session.page.evaluate("() => window.__godotGithubConnectorStatus || null"),
                }
            else:
                raise HTTPException(status_code=400, detail="Unsupported command")
        except HTTPException:
            raise
        except Exception as exc:
            session.events.append({"type": "command.failed", "command": body.command, "error": type(exc).__name__, "at": time.time()})
            raise HTTPException(status_code=502, detail=f"Browser command failed: {type(exc).__name__}") from exc
        session.events.append({"type": "command.completed", "command": body.command, "at": time.time(), "result": output})
        _touch(session)
        return {"ok": True, "session_id": session_id, "result": output, "session_kept_open": True}

@router.post("/{session_id}/tasks/complete")
async def complete_persistent_task(session_id: str, body: CompleteTaskRequest, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    session = _get_session(session_id)
    if session.created_at is None:
        raise HTTPException(status_code=409, detail="Godot Web project is still importing; wait until the session state is open")
    async with session.lock:
        if body.task_id in session.completed_tasks:
            return {**session.completed_tasks[body.task_id], "session_kept_open": True}
        if session.page is None or session.page.is_closed():
            raise HTTPException(status_code=409, detail="Editor page is disconnected")
        try:
            screenshot = await session.page.screenshot(full_page=False, timeout=20000)
            screenshot_name = f"task-{body.task_id[:40]}-final.png"
            _store_session_artifact(session, screenshot_name, screenshot)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Could not capture final editor state: {type(exc).__name__}") from exc
        manifest = {
            "task_id": body.task_id,
            "completed_at": time.time(),
            "repository": session.repository,
            "branch": session.branch,
            "project_path": session.project_path,
            "commit_sha": session.commit_sha,
            "summary": body.summary,
            "result": body.result,
            "editor_url": EDITOR_URL,
            "session_id": session.session_id,
            "session_remains_open": True,
            "artifacts": sorted(session.artifacts),
            "events": session.events[-500:],
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("task-result.json", manifest_bytes)
            for name, data in session.artifacts.items():
                archive.writestr(f"artifacts/{name}", data)
        payload = bundle.getvalue()
        if len(payload) > MAX_ARTIFACT_BYTES:
            raise HTTPException(status_code=413, detail="Task artifact bundle exceeds 32 MiB")
        artifact_id = secrets.token_urlsafe(18)
        object_key = _persistent_artifact_key(session.session_id, artifact_id)
        try:
            client = storage_client()
            await run_in_threadpool(
                client.put_object,
                Bucket=BUCKET,
                Key=object_key,
                Body=payload,
                ContentType="application/zip",
                Metadata={
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "task-id-sha256": hashlib.sha256(body.task_id.encode("utf-8")).hexdigest(),
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Could not persist completed task bundle in Neon Object Storage")
            raise HTTPException(status_code=503, detail="Task bundle could not be persisted in Neon Object Storage") from exc
        artifact_sha256 = hashlib.sha256(payload).hexdigest()
        result = {
            "task_id": body.task_id,
            "state": "completed",
            "artifact_id": artifact_id,
            "artifact_url": f"/v1/persistent-sessions/{session_id}/artifacts/{artifact_id}",
            "artifact_bytes": len(payload),
            "artifact_sha256": artifact_sha256,
            "session_kept_open": True,
            "session_id": session.session_id,
            "storage": "neon-object-storage",
            "object_key": object_key,
        }
        session.completed_tasks[body.task_id] = result
        session.artifacts.clear()
        session.events.append({"type": "task.completed", "task_id": body.task_id, "artifact_id": artifact_id, "at": time.time()})
        _touch(session)
        return result

def _persistent_artifact_key(session_id: str, artifact_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", artifact_id):
        raise HTTPException(status_code=400, detail="Invalid artifact ID")
    return f"persistent-sessions/{session_id}/{artifact_id}.zip"


@router.get("/{session_id}/artifacts/{artifact_id}")
async def download_persistent_artifact(session_id: str, artifact_id: str, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    key = _persistent_artifact_key(session_id, artifact_id)
    session = _sessions.get(session_id)
    try:
        client = storage_client()
        response = await run_in_threadpool(client.get_object, Bucket=BUCKET, Key=key)
        content_length = int(response.get("ContentLength", 0))
        if content_length < 1 or content_length > MAX_ARTIFACT_BYTES:
            raise HTTPException(status_code=404, detail="Artifact not found")
        body = response["Body"]
        try:
            payload = await run_in_threadpool(body.read, MAX_ARTIFACT_BYTES + 1)
        finally:
            await run_in_threadpool(body.close)
        if not payload or len(payload) > MAX_ARTIFACT_BYTES or len(payload) != content_length:
            raise HTTPException(status_code=404, detail="Artifact not found")
        expected_digest = str((response.get("Metadata") or {}).get("sha256", ""))
        if expected_digest and not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), expected_digest):
            raise HTTPException(status_code=502, detail="Persistent artifact integrity check failed")
    except HTTPException:
        raise
    except Exception as exc:
        logger.info("Persistent artifact unavailable for %s/%s: %s", session_id, artifact_id, type(exc).__name__)
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    if session is not None:
        _touch(session)
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="godot-task-{artifact_id}.zip"'},
    )

@router.delete("/{session_id}")
async def close_persistent_session(session_id: str, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    session = _get_session(session_id)
    await _close_session(session)
    return {"ok": True, "closed": True, "session_id": session_id}
