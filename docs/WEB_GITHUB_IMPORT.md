# GitHub import in the Web Project Manager

## Goal

Port the public-repository import experience already present in the user's modified Android Godot editor into the Godot Web Project Manager. The Web build must use the same familiar flow: choose **GitHub**, paste a public repository URL (or `owner/repository`), download its archive, then hand it to Godot's native `_install_project()` importer. This is an engine Project Manager feature, not a separate website or a second project-sync implementation.

Android source of truth:
- [Modified Godot Android repository](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado)
- [Android GitHub import patch](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/blob/main/scripts/apply_github_import_patch.py)

## What this branch contains

- `scripts/apply-web-github-import.py`: an anchor-checked port of the Android Project Manager patch, targeting the pinned Godot 4.7.2 source submodule.
- `scripts/prepare-engine-source.sh`: invokes that patch after initializing the pinned engine source.
- `tests/test_web_github_import_patcher.py`: verifies the expected C++ declarations, request callback, GitHub URL and native project-install handoff; it also verifies that changed upstream anchors fail closed.

The patch adds a GitHub button and dialog to the Project Manager. It uses Godot's HTTPRequest and native project archive installer; it does not introduce another editor add-on or touch the user's Android project.

## Important build boundary

The current production Web build script still downloads the official prebuilt Web Editor archive. A C++ Project Manager patch cannot affect that prebuilt binary. The patcher is therefore source-side groundwork until the Web build pipeline compiles the pinned Godot source with the Web editor target and publishes that tested artifact. Do not claim the production Web editor has the GitHub button until that source build has passed and the published bundle has been visually verified in Chromium.

The next implementation stage is to add a reproducible Emscripten/SCons source-build job, compile the patched Web editor, run the existing Chromium audit against the actual Project Manager, then switch deployment only after parity and bundle checks pass.

## Scope and safety

- Public GitHub repositories only; no tokens or private-repository credentials.
- GitHub URLs are parsed into exactly an owner and repository name; arbitrary hosts are not accepted.
- Import is a download-and-install action. It does not execute project scripts as a build step.
- Keep the existing Neon Shared Projects layer for subsequent Web/Android synchronization. GitHub import and project synchronization are separate operations.
- Keep the Android repository and its build workflow as the user's editor source of truth; this branch changes only the Web integration repository.
