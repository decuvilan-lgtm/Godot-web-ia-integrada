"""Dispatch isolated Godot validation tasks to CircleCI first, GitHub Actions second.

Only fixed task profiles are accepted. No arbitrary shell commands, project paths,
branch names, or workflow names are exposed to the MCP caller.
"""
from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote

import httpx

CIRCLECI_API = "https://circleci.com/api/v2"
GITHUB_API = "https://api.github.com"
TASK_PROFILES = {"engine_smoke", "scene_audit_3d", "web_browser_audit"}
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
PIPELINE_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PROJECT_SLUG_RE = re.compile(r"^(gh|bb|circleci)/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class TaskDispatchError(RuntimeError):
    """A safe, user-displayable task dispatch or status error."""


def validate_task_profile(task_profile: str) -> str:
    if task_profile not in TASK_PROFILES:
        raise ValueError(f"task_profile must be one of: {', '.join(sorted(TASK_PROFILES))}")
    return task_profile


def validate_request_id(request_id: str) -> str:
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("request_id must contain 8–80 letters, numbers, underscores, or hyphens")
    return request_id


def _circleci_config(env: dict[str, str]) -> tuple[str, str] | None:
    token = env.get("CIRCLECI_TOKEN", "").strip()
    slug = env.get("CIRCLECI_PROJECT_SLUG", "").strip()
    if not token or not slug:
        return None
    if not PROJECT_SLUG_RE.fullmatch(slug):
        raise TaskDispatchError("CIRCLECI_PROJECT_SLUG must look like gh/organization/repository")
    return token, slug


def _github_config(env: dict[str, str]) -> tuple[str, str] | None:
    token = env.get("GITHUB_ACTIONS_TOKEN", "").strip()
    repository = env.get("GITHUB_ACTIONS_REPOSITORY", "decuvilan-lgtm/Godot-web-ia-integrada").strip()
    if not token:
        return None
    if not REPOSITORY_RE.fullmatch(repository):
        raise TaskDispatchError("GITHUB_ACTIONS_REPOSITORY must look like owner/repository")
    return token, repository


async def _circleci_trigger(
    token: str, slug: str, task_profile: str, request_id: str,
    transport: httpx.AsyncBaseTransport | None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(transport=transport, timeout=20.0) as client:
        response = await client.post(
            f"{CIRCLECI_API}/project/{quote(slug, safe='/')}/pipeline",
            headers={"Circle-Token": token, "Accept": "application/json"},
            json={
                "branch": "main",
                "parameters": {
                    "run_godot_task": True,
                    "task_profile": task_profile,
                    "request_id": request_id,
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
    pipeline_id = payload.get("id")
    if not isinstance(pipeline_id, str) or not PIPELINE_ID_RE.fullmatch(pipeline_id):
        raise TaskDispatchError("CircleCI accepted the request but returned no valid pipeline ID")
    return {
        "provider": "circleci",
        "execution_id": pipeline_id,
        "request_id": request_id,
        "task_profile": task_profile,
        "status": payload.get("state", "created"),
        "pipeline_number": payload.get("number"),
        "created_at": payload.get("created_at"),
        "fallback_used": False,
    }


async def _github_trigger(
    token: str, repository: str, task_profile: str, request_id: str,
    transport: httpx.AsyncBaseTransport | None,
) -> dict[str, Any]:
    owner, repo = repository.split("/", 1)
    async with httpx.AsyncClient(transport=transport, timeout=20.0) as client:
        response = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/actions/workflows/remote-godot-task.yml/dispatches",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "ref": "main",
                "inputs": {"task_profile": task_profile, "request_id": request_id},
            },
        )
        response.raise_for_status()
    return {
        "provider": "github_actions",
        "execution_id": None,
        "request_id": request_id,
        "task_profile": task_profile,
        "status": "dispatched",
        "fallback_used": True,
    }


async def dispatch_task(
    task_profile: str,
    request_id: str,
    *,
    env: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """CircleCI is primary. GitHub Actions is used only if CircleCI is absent/unavailable."""
    task_profile = validate_task_profile(task_profile)
    request_id = validate_request_id(request_id)
    settings = dict(os.environ if env is None else env)
    circleci = _circleci_config(settings)
    github = _github_config(settings)

    # The browser audit has a dedicated GitHub Actions job with pinned Playwright
    # and Chromium. Do not send it to the legacy CircleCI Godot-only executor.
    if task_profile == "web_browser_audit":
        if not github:
            raise TaskDispatchError("web_browser_audit requires the GitHub Actions dispatch credential")
        try:
            return await _github_trigger(*github, task_profile, request_id, transport)
        except httpx.HTTPError as exc:
            raise TaskDispatchError(
                f"GitHub Actions browser audit dispatch failed ({type(exc).__name__})"
            ) from exc

    circleci_error: str | None = None

    if circleci:
        try:
            return await _circleci_trigger(*circleci, task_profile, request_id, transport)
        except (httpx.HTTPError, TaskDispatchError) as exc:
            circleci_error = type(exc).__name__
    else:
        circleci_error = "CircleCI credentials or project slug are not configured"

    if github:
        try:
            result = await _github_trigger(*github, task_profile, request_id, transport)
            result["fallback_reason"] = circleci_error
            return result
        except httpx.HTTPError as exc:
            raise TaskDispatchError(
                f"CircleCI was unavailable ({circleci_error}); GitHub Actions fallback also failed ({type(exc).__name__})"
            ) from exc

    if circleci_error:
        raise TaskDispatchError(
            f"CircleCI is unavailable ({circleci_error}) and GitHub Actions fallback is not configured"
        )
    raise TaskDispatchError("No execution provider is configured")


def provider_status(*, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Report provider readiness without ever returning credential values."""
    settings = dict(os.environ if env is None else env)
    circle_token = bool(settings.get("CIRCLECI_TOKEN", "").strip())
    circle_slug = settings.get("CIRCLECI_PROJECT_SLUG", "").strip()
    github_token = bool(settings.get("GITHUB_ACTIONS_TOKEN", "").strip())
    github_repo = settings.get(
        "GITHUB_ACTIONS_REPOSITORY", "decuvilan-lgtm/Godot-web-ia-integrada"
    ).strip()
    circle_ready = circle_token and bool(PROJECT_SLUG_RE.fullmatch(circle_slug))
    github_ready = github_token and bool(REPOSITORY_RE.fullmatch(github_repo))
    return {
        "priority": ["circleci", "github_actions"],
        "ready": bool(circle_ready or github_ready),
        "primary": {
            "provider": "circleci",
            "configured": bool(circle_ready),
            "missing": [
                name for name, present in (
                    ("CIRCLECI_TOKEN", circle_token),
                    ("CIRCLECI_PROJECT_SLUG", bool(PROJECT_SLUG_RE.fullmatch(circle_slug))),
                ) if not present
            ],
            "project_slug": circle_slug if circle_ready else None,
        },
        "fallback": {
            "provider": "github_actions",
            "configured": bool(github_ready),
            "missing": [
                name for name, present in (
                    ("GITHUB_ACTIONS_TOKEN", github_token),
                    ("GITHUB_ACTIONS_REPOSITORY", bool(REPOSITORY_RE.fullmatch(github_repo))),
                ) if not present
            ],
            "repository": github_repo if github_ready else None,
        },
    }


async def circleci_task_status(
    pipeline_id: str,
    *,
    env: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    if not isinstance(pipeline_id, str) or not PIPELINE_ID_RE.fullmatch(pipeline_id):
        raise ValueError("execution_id must be a CircleCI pipeline UUID")
    settings = dict(os.environ if env is None else env)
    config = _circleci_config(settings)
    if not config:
        raise TaskDispatchError("CircleCI credentials or project slug are not configured")
    token, slug = config
    headers = {"Circle-Token": token, "Accept": "application/json"}
    workflows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(transport=transport, timeout=20.0) as client:
        pipeline_response = await client.get(
            f"{CIRCLECI_API}/pipeline/{pipeline_id}", headers=headers
        )
        pipeline_response.raise_for_status()
        pipeline = pipeline_response.json()
        workflows_response = await client.get(
            f"{CIRCLECI_API}/pipeline/{pipeline_id}/workflow", headers=headers
        )
        workflows_response.raise_for_status()
        workflow_items = workflows_response.json().get("items", [])
        for item in workflow_items[:10]:
            workflow = {
                "id": item.get("id"),
                "name": item.get("name"),
                "status": item.get("status"),
                "created_at": item.get("created_at"),
                "stopped_at": item.get("stopped_at"),
                "jobs": [],
            }
            workflow_id = item.get("id")
            if isinstance(workflow_id, str):
                try:
                    jobs_response = await client.get(
                        f"{CIRCLECI_API}/workflow/{workflow_id}/job", headers=headers
                    )
                    jobs_response.raise_for_status()
                    jobs = jobs_response.json().get("items", [])
                except httpx.HTTPError as exc:
                    workflow["jobs_error"] = type(exc).__name__
                    jobs = []
                for job in jobs[:25]:
                    job_data = {
                        "name": job.get("name"),
                        "status": job.get("status"),
                        "job_number": job.get("job_number"),
                        "started_at": job.get("started_at"),
                        "stopped_at": job.get("stopped_at"),
                        "artifacts": [],
                    }
                    job_number = job.get("job_number")
                    if isinstance(job_number, int):
                        try:
                            artifact_response = await client.get(
                                f"{CIRCLECI_API}/project/{quote(slug, safe='/')}/{job_number}/artifacts",
                                headers=headers,
                            )
                            artifact_response.raise_for_status()
                            job_data["artifacts"] = [
                                {
                                    "path": artifact.get("path"),
                                    "url": artifact.get("url"),
                                    "size": artifact.get("size"),
                                }
                                for artifact in artifact_response.json().get("items", [])[:50]
                            ]
                        except httpx.HTTPError as exc:
                            job_data["artifacts_error"] = type(exc).__name__
                    workflow["jobs"].append(job_data)
            workflows.append(workflow)
    return {
        "provider": "circleci",
        "execution_id": pipeline_id,
        "state": pipeline.get("state"),
        "number": pipeline.get("number"),
        "created_at": pipeline.get("created_at"),
        "workflows": workflows,
    }


async def github_task_status(
    request_id: str,
    *,
    env: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    request_id = validate_request_id(request_id)
    settings = dict(os.environ if env is None else env)
    config = _github_config(settings)
    if not config:
        raise TaskDispatchError("GitHub Actions fallback credentials are not configured")
    token, repository = config
    owner, repo = repository.split("/", 1)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(transport=transport, timeout=20.0) as client:
        response = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/actions/workflows/remote-godot-task.yml/runs",
            headers=headers,
            params={"branch": "main", "event": "workflow_dispatch", "per_page": 50},
        )
        response.raise_for_status()
        payload = response.json()
        expected_title = f"Godot task {request_id}"
        match = next(
            (run for run in payload.get("workflow_runs", [])
             if run.get("display_title") == expected_title),
            None,
        )
        if match is None:
            return {
                "provider": "github_actions",
                "request_id": request_id,
                "status": "not_visible_yet",
                "detail": "The workflow may still be initializing or may have expired from the recent-run window.",
            }
        artifact_data: list[dict[str, Any]] = []
        artifact_error = None
        try:
            artifact_response = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs/{match.get('id')}/artifacts",
                headers=headers,
                params={"per_page": 50},
            )
            artifact_response.raise_for_status()
            artifact_data = [
                {
                    "id": artifact.get("id"),
                    "name": artifact.get("name"),
                    "size_in_bytes": artifact.get("size_in_bytes"),
                    "expired": artifact.get("expired"),
                    "archive_download_url": artifact.get("archive_download_url"),
                }
                for artifact in artifact_response.json().get("artifacts", [])[:50]
            ]
        except httpx.HTTPError as exc:
            artifact_error = type(exc).__name__
    result = {
        "provider": "github_actions",
        "request_id": request_id,
        "execution_id": str(match.get("id")),
        "status": match.get("status"),
        "conclusion": match.get("conclusion"),
        "html_url": match.get("html_url"),
        "created_at": match.get("created_at"),
        "updated_at": match.get("updated_at"),
        "artifacts": artifact_data,
    }
    if artifact_error:
        result["artifacts_error"] = artifact_error
    return result

async def task_status(
    provider: str,
    execution_id: str | None,
    request_id: str,
    *,
    env: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    validate_request_id(request_id)
    if provider == "circleci":
        if not execution_id:
            raise ValueError("execution_id is required for CircleCI status")
        return await circleci_task_status(execution_id, env=env, transport=transport)
    if provider == "github_actions":
        return await github_task_status(request_id, env=env, transport=transport)
    raise ValueError("provider must be circleci or github_actions")
