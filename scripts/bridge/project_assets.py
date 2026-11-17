"""Inject generated art into the exact selected Godot project archive."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path


def inject_generated_project_assets(
    archive_bytes: bytes,
    project_path: str,
    generated_project: Path | str,
) -> bytes:
    """Overlay local generated assets into rootless or repository-root ZIP layouts."""
    if not project_path:
        return archive_bytes

    project = Path(generated_project)
    asset_root = project / "assets"
    generated = sorted(path for path in asset_root.rglob("*") if path.is_file()) if asset_root.is_dir() else []
    if not generated:
        return archive_bytes

    normalized_project = project_path.strip("/")
    with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as source:
        names = set(source.namelist())
        candidates = [
            ("", "project.godot"),
            (normalized_project + "/", normalized_project + "/project.godot"),
        ]
        roots = {name.split("/", 1)[0] for name in names if "/" in name}
        candidates.extend(
            (f"{root}/{normalized_project}/", f"{root}/{normalized_project}/project.godot")
            for root in roots
        )
        project_prefix = next((prefix for prefix, marker in candidates if marker in names), None)
        if project_prefix is None:
            raise ValueError(
                "The archive layout does not contain project.godot at the selected project path; "
                "refusing to inject assets into an ambiguous ZIP."
            )

        additions = []
        for file_path in generated:
            archive_path = project_prefix + file_path.relative_to(project).as_posix()
            if archive_path not in names:
                additions.append((archive_path, file_path))
        if not additions:
            print(f"PROJECT ASSET OVERLAY: archive already contains generated assets for {project_path}")
            return archive_bytes

        directory_entries = set()
        for archive_path, _file_path in additions:
            parent = archive_path.rsplit("/", 1)[0]
            while parent:
                entry = parent + "/"
                if entry not in names:
                    directory_entries.add(entry)
                if "/" not in parent:
                    break
                parent = parent.rsplit("/", 1)[0]

        print(
            "PROJECT ASSET OVERLAY: "
            f"layout_prefix={project_prefix!r}, adding {len(additions)} files and "
            f"{len(directory_entries)} directories for {project_path}"
        )
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                target.writestr(info, source.read(info.filename))
            for directory in sorted(directory_entries, key=lambda value: (value.count("/"), value)):
                target.writestr(directory, b"")
            for archive_path, file_path in additions:
                target.writestr(archive_path, file_path.read_bytes())
        return output.getvalue()
