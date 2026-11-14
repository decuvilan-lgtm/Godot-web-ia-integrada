"""Inject the lab-owned editor bridge into a temporary Godot Web import ZIP.

The source GitHub repository is never changed. Only the archive response consumed
by the current Actions Chromium page is overlaid in memory.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path, PurePosixPath
import hashlib
import re
import zipfile

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
PLUGIN_RELATIVE = "addons/godot_controller_bridge"
PLUGIN_RES_PATH = "res://addons/godot_controller_bridge/plugin.cfg"


def _safe_zip_name(name: str) -> str:
    normalized = name.replace(chr(92), "/")
    parts = normalized.rstrip("/").split("/")
    if normalized.startswith("/") or chr(92) in name or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Unsafe path in project archive: {name[:160]}")
    return normalized

def _enable_plugin(project_text: str) -> str:
    if "\x00" in project_text:
        raise ValueError("project.godot contains a NUL byte")
    section = re.search(r"(?ms)^\[editor_plugins\][ \t]*\r?\n?(.*?)(?=^\[|\Z)", project_text)
    if section is None:
        suffix = "" if not project_text or project_text.endswith("\n") else "\n"
        return project_text + suffix + f"\n[editor_plugins]\nenabled=PackedStringArray(\"{PLUGIN_RES_PATH}\")\n"

    body = section.group(1)
    enabled = re.search(r"(?ms)^([ \t]*enabled[ \t]*=[ \t]*)PackedStringArray\((.*?)\)[ \t]*$", body)
    if enabled:
        values = enabled.group(2)
        if PLUGIN_RES_PATH in values:
            return project_text
        updated = values.rstrip()
        updated = updated + (", " if updated else "") + f'"{PLUGIN_RES_PATH}"'
        new_body = body[:enabled.start(2)] + updated + body[enabled.end(2):]
    else:
        if re.search(r"(?m)^[ \t]*enabled[ \t]*=", body):
            raise ValueError("project.godot editor_plugins/enabled is not a PackedStringArray")
        separator = "" if not body or body.endswith("\n") else "\n"
        new_body = body + separator + f'enabled=PackedStringArray("{PLUGIN_RES_PATH}")\n'
    return project_text[:section.start(1)] + new_body + project_text[section.end(1):]


def apply_controller_overlay(archive_bytes: bytes, addon_source: Path) -> tuple[bytes, dict]:
    """Return a transformed ZIP and a safe audit summary; never writes to disk."""
    if not isinstance(archive_bytes, bytes) or not archive_bytes or len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError("Project ZIP is empty or exceeds the 128 MiB overlay limit")
    addon_source = Path(addon_source)
    required = ("plugin.cfg", "plugin.gd")
    addon_files: dict[str, bytes] = {}
    for filename in required:
        path = addon_source / filename
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Controller add-on source is incomplete: {filename}")
        addon_files[f"{PLUGIN_RELATIVE}/{filename}"] = path.read_bytes()
    if any(not content for content in addon_files.values()):
        raise ValueError("Controller add-on source contains an empty file")

    source_sha = hashlib.sha256(archive_bytes).hexdigest()
    try:
        source = zipfile.ZipFile(BytesIO(archive_bytes), "r")
    except zipfile.BadZipFile as exc:
        raise ValueError("GitHub project response is not a valid ZIP archive") from exc

    with source:
        infos = source.infolist()
        seen: set[str] = set()
        project_entries: list[zipfile.ZipInfo] = []
        for info in infos:
            name = _safe_zip_name(info.filename.rstrip("/")) if info.filename.rstrip("/") else ""
            if not name:
                continue
            if name in seen:
                raise ValueError(f"Duplicate path in project archive: {name[:160]}")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError(f"Symlinks are not accepted in project archives: {name[:160]}")
            seen.add(name)
            if not info.is_dir() and PurePosixPath(name).name == "project.godot":
                project_entries.append(info)
        if len(project_entries) != 1:
            raise ValueError("Expected exactly one project.godot in the selected Godot project ZIP")

        project_info = project_entries[0]
        project_name = _safe_zip_name(project_info.filename)
        project_dir = str(PurePosixPath(project_name).parent)
        if project_dir == ".":
            project_dir = ""
        target_prefix = project_dir + "/" if project_dir else ""
        project_text = source.read(project_info).decode("utf-8-sig")
        patched_project = _enable_plugin(project_text).encode("utf-8")

        for relative, content in addon_files.items():
            existing_name = target_prefix + relative
            if existing_name in seen:
                if source.read(existing_name) != content:
                    raise ValueError("Project already contains a different Godot Controller Bridge; refusing to overwrite it")

        output = BytesIO()
        added: list[str] = []
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
            for info in infos:
                name = info.filename.rstrip("/")
                if not name:
                    target.writestr(info, b"")
                    continue
                safe_name = _safe_zip_name(name)
                if safe_name == project_name:
                    target.writestr(info, patched_project)
                else:
                    target.writestr(info, source.read(info))
            for relative, content in addon_files.items():
                archive_name = target_prefix + relative
                if archive_name not in seen:
                    target.writestr(archive_name, content)
                    added.append(archive_name)

        result = output.getvalue()
        if len(result) > MAX_ARCHIVE_BYTES:
            raise ValueError("Overlaid project ZIP exceeds the 128 MiB import limit")
        return result, {
            "applied": True,
            "project_file": project_name,
            "plugin_path": PLUGIN_RES_PATH,
            "added_files": added,
            "source_archive_sha256": source_sha,
            "overlaid_archive_sha256": hashlib.sha256(result).hexdigest(),
            "source_repository_modified": False,
        }
