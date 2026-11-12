"""Bounded public GitHub archive proxy for root and nested Godot projects."""
from __future__ import annotations

import asyncio
import re
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Query
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

router = APIRouter(prefix="/v1/github", tags=["github-import"])

OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,128}$")
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_PROJECT_BYTES = 256 * 1024 * 1024
CHUNK_BYTES = 256 * 1024
_DOWNLOADS = asyncio.Semaphore(2)


def validate_branch(branch: str) -> str:
    value = str(branch or "").strip()
    parts = value.split("/")
    if (
        not BRANCH_RE.fullmatch(value)
        or value.startswith("/")
        or value.endswith("/")
        or "//" in value
        or any(part in {"", ".", ".."} for part in parts)
        or value.endswith(".")
        or "@{" in value
        or any(char in value for char in ("~", "^", ":", "?", "*", "[", "\\", " "))
    ):
        raise HTTPException(status_code=422, detail="Invalid Git branch name")
    return value


def validate_project_path(project_path: str) -> str:
    value = str(project_path or "").strip().strip("/")
    if not value:
        return ""
    if len(value) > 240 or "\\" in value or "\x00" in value:
        raise HTTPException(status_code=422, detail="Invalid project subdirectory")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise HTTPException(status_code=422, detail="Invalid project subdirectory")
    return value


def archive_url(owner: str, repository: str, branch: str = "main") -> str:
    if not OWNER_RE.fullmatch(owner) or not REPO_RE.fullmatch(repository):
        raise HTTPException(status_code=422, detail="Invalid public GitHub owner/repository")
    if repository in {".", ".."}:
        raise HTTPException(status_code=422, detail="Invalid repository name")
    ref = validate_branch(branch)
    return f"https://codeload.github.com/{owner}/{repository}/zip/refs/heads/{quote(ref, safe='/')}"


async def resolve_default_branch(client: httpx.AsyncClient, owner: str, repository: str) -> str:
    response = await client.get(f"https://api.github.com/repos/{owner}/{repository}")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Public GitHub repository not found")
    if response.status_code == 403:
        raise HTTPException(status_code=429, detail="GitHub API rate limit reached")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="GitHub repository metadata request failed")
    try:
        metadata = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="GitHub returned invalid repository metadata") from exc
    if metadata.get("private") is not False:
        raise HTTPException(status_code=404, detail="Only public GitHub repositories can be imported")
    return validate_branch(str(metadata.get("default_branch") or ""))


def _file_chunks(file_obj) -> Iterator[bytes]:
    while True:
        chunk = file_obj.read(CHUNK_BYTES)
        if not chunk:
            break
        yield chunk


def _select_project_subdirectory(archive, project_path: str):
    """Repackage a selected repository subfolder so project.godot is at ZIP root."""
    try:
        source = zipfile.ZipFile(archive, "r")
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=502, detail="GitHub response was not a valid ZIP archive") from exc

    with source:
        files = [item for item in source.infolist() if not item.is_dir()]
        roots = {item.filename.split("/", 1)[0] for item in source.infolist() if "/" in item.filename}
        if len(roots) != 1:
            raise HTTPException(status_code=502, detail="GitHub archive has an unexpected directory layout")
        root = next(iter(roots))
        prefix = root + (f"/{project_path}/" if project_path else "/")
        selected = []
        total_uncompressed = 0
        found_project = False

        for item in files:
            name = item.filename.replace("\\", "/")
            if name.startswith("/") or any(part == ".." for part in PurePosixPath(name).parts):
                raise HTTPException(status_code=502, detail="GitHub archive contains an unsafe path")
            if not name.startswith(prefix):
                continue
            relative = name[len(prefix):]
            if not relative or relative.startswith("/") or any(part in {"", ".", ".."} for part in PurePosixPath(relative).parts):
                raise HTTPException(status_code=502, detail="GitHub archive contains an unsafe project path")
            mode = (item.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                continue
            total_uncompressed += item.file_size
            if total_uncompressed > MAX_PROJECT_BYTES:
                raise HTTPException(status_code=413, detail="Selected Godot project exceeds the 256 MiB unpacked import limit")
            found_project = found_project or relative == "project.godot"
            selected.append((item, relative))

        if not found_project:
            location = f"{project_path}/project.godot" if project_path else "project.godot at repository root"
            raise HTTPException(status_code=422, detail=f"Could not find {location} in the selected GitHub branch")

        output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
        try:
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
                for original, relative in selected:
                    info = zipfile.ZipInfo(relative, date_time=original.date_time)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = original.external_attr
                    info.create_system = original.create_system
                    target.writestr(info, source.read(original.filename))
            output.seek(0, 2)
            if output.tell() > MAX_ARCHIVE_BYTES:
                raise HTTPException(status_code=413, detail="Selected Godot project archive exceeds the 128 MiB import limit")
            output.seek(0)
            return output
        except Exception:
            output.close()
            raise


@router.get("/{owner}/{repository}/archive")
async def public_repository_archive(
    owner: str,
    repository: str,
    branch: str | None = Query(default=None, max_length=128),
    path: str = Query(default="", max_length=240),
):
    """Return a public repository ZIP; branch defaults to the repository's default branch."""
    if not OWNER_RE.fullmatch(owner) or not REPO_RE.fullmatch(repository) or repository in {".", ".."}:
        raise HTTPException(status_code=422, detail="Invalid public GitHub owner/repository")
    project_path = validate_project_path(path)
    archive = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")

    try:
        async with _DOWNLOADS:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(30.0, connect=10.0),
                headers={"User-Agent": "Godot-Web-IA-Repository-Importer", "Accept": "application/zip"},
            ) as client:
                selected_branch = validate_branch(branch) if branch else await resolve_default_branch(client, owner, repository)
                url = archive_url(owner, repository, selected_branch)
                async with client.stream("GET", url) as upstream:
                    if upstream.status_code == 404:
                        raise HTTPException(status_code=404, detail="Public repository or selected branch not found")
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
        if project_path:
            selected = _select_project_subdirectory(archive, project_path)
            archive.close()
            archive = selected
        else:
            # Root projects must be explicit; a nested project must use the path query.
            checked = _select_project_subdirectory(archive, "")
            checked.close()
            archive.seek(0)

        branch_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", selected_branch).strip(".-") or "branch"
        safe_name = f"{owner}-{repository}-{branch_slug}.zip"
        return StreamingResponse(
            _file_chunks(archive),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}"',
                "Cache-Control": "no-store, max-age=0",
                "X-Content-Type-Options": "nosniff",
                "X-GitHub-Repository": f"{owner}/{repository}",
                "X-GitHub-Ref": selected_branch,
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
