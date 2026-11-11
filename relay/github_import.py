"""Safe, bounded proxy for importing public GitHub repository archives.

The Web editor cannot read GitHub's codeload redirect because of browser CORS.
This server-side route fetches only public GitHub repositories and returns the
archive to the native Project Manager. It never accepts arbitrary URLs.
"""
from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import Response

router = APIRouter(prefix="/v1/github", tags=["github-import"])

OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
RATE_WINDOW_SECONDS = 600
RATE_LIMIT = 8
_rate_events: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = asyncio.Lock()
_download_slots = asyncio.Semaphore(3)
_GITHUB_API = "https://api.github.com"
_ALLOWED_ARCHIVE_HOST = "codeload.github.com"


def _validate_repository(owner: str, repo: str) -> tuple[str, str]:
    if not OWNER_RE.fullmatch(owner) or not REPO_RE.fullmatch(repo) or repo in {".", ".."}:
        raise HTTPException(status_code=422, detail="Invalid GitHub owner or repository name")
    return owner, repo.removesuffix(".git")


async def _check_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    async with _rate_lock:
        events = _rate_events[client_ip]
        while events and now - events[0] > RATE_WINDOW_SECONDS:
            events.popleft()
        if len(events) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail="GitHub import rate limit exceeded; try again later")
        events.append(now)


async def _download_archive(owner: str, repo: str) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Godot-Web-IA-GitHub-Importer",
    }
    timeout = httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        metadata = await client.get(f"{_GITHUB_API}/repos/{owner}/{repo}", headers=headers)
        if metadata.status_code == 404:
            raise HTTPException(status_code=404, detail="GitHub repository not found or not public")
        if metadata.status_code == 403:
            raise HTTPException(status_code=429, detail="GitHub API rate limit reached; try again later")
        if metadata.status_code != 200:
            raise HTTPException(status_code=502, detail="GitHub could not verify the public repository")
        try:
            details = metadata.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="GitHub returned invalid repository metadata") from exc
        if details.get("private") is not False:
            raise HTTPException(status_code=404, detail="Only public GitHub repositories can be imported")
        if details.get("disabled") is True:
            raise HTTPException(status_code=422, detail="This GitHub repository is disabled")

        archive = await client.get(f"{_GITHUB_API}/repos/{owner}/{repo}/zipball", headers=headers)
        if archive.status_code not in {301, 302, 303, 307, 308}:
            raise HTTPException(status_code=502, detail="GitHub did not provide a repository archive redirect")
        location = archive.headers.get("location", "")
        parsed = urlparse(location)
        if parsed.scheme != "https" or parsed.hostname != _ALLOWED_ARCHIVE_HOST or parsed.username or parsed.password:
            raise HTTPException(status_code=502, detail="GitHub returned an unexpected archive host")

        async with client.stream("GET", location, headers={"User-Agent": headers["User-Agent"]}) as response:
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="GitHub repository archive is unavailable")
            if response.status_code != 200:
                raise HTTPException(status_code=502, detail="GitHub archive download failed")
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > MAX_ARCHIVE_BYTES:
                        raise HTTPException(status_code=413, detail="GitHub archive exceeds the 64 MiB import limit")
                except ValueError:
                    raise HTTPException(status_code=502, detail="GitHub returned an invalid archive size")
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise HTTPException(status_code=413, detail="GitHub archive exceeds the 64 MiB import limit")
                chunks.append(chunk)
            if total == 0:
                raise HTTPException(status_code=502, detail="GitHub returned an empty archive")
            return b"".join(chunks)


@router.get("/import/{owner}/{repo}")
async def import_public_repository(owner: str, repo: str, request: Request):
    owner, repo = _validate_repository(owner, repo)
    client_ip = request.client.host if request.client else "unknown"
    await _check_rate_limit(client_ip)
    if _download_slots.locked():
        raise HTTPException(status_code=503, detail="GitHub import service is busy; try again shortly")
    async with _download_slots:
        archive = await _download_archive(owner, repo)
    return Response(
        content=archive,
        media_type="application/zip",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": 'attachment; filename="github-project.zip"',
            "X-GitHub-Repository": f"{owner}/{repo}",
        },
    )
