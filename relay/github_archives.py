"""Bounded, public-only GitHub archive proxy for the Godot Web import flow.

The browser never receives a GitHub token. Only owner/repository names are accepted;
the upstream host and branch are fixed to codeload.github.com and main.
"""
from __future__ import annotations

import asyncio
import re
import tempfile
from collections.abc import Iterator

import httpx
from fastapi import APIRouter, HTTPException
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

router = APIRouter(prefix="/v1/github", tags=["github-import"])

OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$")
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
CHUNK_BYTES = 256 * 1024
_DOWNLOADS = asyncio.Semaphore(2)


def archive_url(owner: str, repository: str) -> str:
    if not OWNER_RE.fullmatch(owner) or not REPO_RE.fullmatch(repository):
        raise HTTPException(status_code=422, detail="Invalid public GitHub owner/repository")
    if repository in {".", ".."}:
        raise HTTPException(status_code=422, detail="Invalid repository name")
    return f"https://codeload.github.com/{owner}/{repository}/zip/refs/heads/main"


def _file_chunks(file_obj) -> Iterator[bytes]:
    while True:
        chunk = file_obj.read(CHUNK_BYTES)
        if not chunk:
            break
        yield chunk


@router.get("/{owner}/{repository}/archive")
async def public_repository_archive(owner: str, repository: str):
    """Return the ZIP snapshot of a public repository's main branch."""
    url = archive_url(owner, repository)
    archive = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")

    try:
        async with _DOWNLOADS:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(30.0, connect=10.0),
                headers={"User-Agent": "Godot-Web-IA-Repository-Importer", "Accept": "application/zip"},
            ) as client:
                async with client.stream("GET", url) as upstream:
                    if upstream.status_code == 404:
                        raise HTTPException(status_code=404, detail="Public repository or main branch not found")
                    if upstream.status_code == 403:
                        raise HTTPException(status_code=429, detail="GitHub temporarily refused the archive request")
                    if upstream.status_code != 200:
                        raise HTTPException(status_code=502, detail="GitHub archive service returned an unexpected status")
                    if upstream.url.host != "codeload.github.com":
                        raise HTTPException(status_code=502, detail="GitHub archive redirected to an unexpected host")

                    declared_size = upstream.headers.get("content-length")
                    if declared_size:
                        try:
                            if int(declared_size) > MAX_ARCHIVE_BYTES:
                                raise HTTPException(status_code=413, detail="Repository archive exceeds the 128 MiB import limit")
                        except ValueError as exc:
                            raise HTTPException(status_code=502, detail="GitHub returned an invalid archive size") from exc

                    total = 0
                    async for chunk in upstream.aiter_bytes(CHUNK_BYTES):
                        total += len(chunk)
                        if total > MAX_ARCHIVE_BYTES:
                            raise HTTPException(status_code=413, detail="Repository archive exceeds the 128 MiB import limit")
                        archive.write(chunk)

        archive.seek(0)
        if archive.read(4) != b"PK" + bytes((3, 4)):
            raise HTTPException(status_code=502, detail="GitHub response was not a valid ZIP archive")
        archive.seek(0)
        safe_name = f"{owner}-{repository}-main.zip"
        return StreamingResponse(
            _file_chunks(archive),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}"',
                "Cache-Control": "no-store, max-age=0",
                "X-Content-Type-Options": "nosniff",
                "X-GitHub-Repository": f"{owner}/{repository}",
                "X-GitHub-Ref": "main",
            },
            background=BackgroundTask(archive.close),
        )
    except HTTPException:
        archive.close()
        raise
    except httpx.TimeoutException as exc:
        archive.close()
        raise HTTPException(status_code=504, detail="GitHub archive request timed out") from exc
    except httpx.HTTPError as exc:
        archive.close()
        raise HTTPException(status_code=502, detail="Could not retrieve the GitHub archive") from exc
    except Exception:
        archive.close()
        raise
