# GitHub import in the Web Project Manager

## Goal

Port the public-repository import experience already present in the user's modified Android Godot editor into the Godot Web Project Manager. The Web build uses the familiar flow: choose **GitHub**, paste a public GitHub repository URL (or `owner/repository`), download its archive, then hand it to Godot's native `_install_project()` importer. This is an engine Project Manager feature, not a separate website or a second project-sync implementation.

Android source of truth:
- [Modified Godot Android repository](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado)
- [Android GitHub import patch](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/blob/main/scripts/apply_github_import_patch.py)

## Implementation

- `scripts/apply-web-github-import.py`: anchor-checked port of the Android Project Manager patch, targeting the pinned Godot source.
- `scripts/prepare-engine-source.sh`: initializes the pinned engine source and applies the patch.
- `scripts/ci/test-patched-web-editor.py`: end-to-end Chromium smoke test. It boots the compiled Web editor, clicks the native GitHub button, enters a public test repository, submits the download, and verifies that the imported project appears in the Project Manager using OCR against the rendered canvas.
- `tests/test_web_github_import_patcher.py`: static patcher checks, including fail-closed checks for changed upstream anchors.
- `.github/workflows/compile-patched-web-editor.yml`: reproducible Emscripten/SCons build plus Chromium import test and diagnostic artifacts.

## Run the end-to-end test locally

After building the patched Web editor and installing the test dependencies (Playwright Chromium and Tesseract OCR), run:

```bash
python scripts/ci/test-patched-web-editor.py
```

The test uses the small public fixture repository `MCMLXXXV/godot-minimal-template`. It does not run the downloaded project's scripts. It saves:
- `patched-godot-web-project-manager.png`
- `patched-godot-web-github-import.png`
- `patched-godot-web-diagnostics.json`

GitHub Actions installs Tesseract, compiles the patched editor, and runs this command automatically. A successful compile alone is not a successful import test: the workflow must pass the final Chromium step too.

## Build and deployment boundary

The source-built patched editor is validated in Chromium by CI. The production Web build/deployment must not be switched to this artifact until its publishing path is deliberately updated and the deployed bundle is independently verified. Do not claim that a production deployment contains the GitHub button based only on a successful source build.

## Scope and safety

- Public GitHub repositories only; no tokens or private-repository credentials.
- Input is restricted to GitHub repository owner/name values; arbitrary hosts are not accepted.
- Import is a download-and-install action. The CI fixture is not executed as part of the import test.
- Keep the existing Neon Shared Projects layer for subsequent Web/Android synchronization. GitHub import and project synchronization are separate operations.
- Keep the Android repository and its build workflow as the user's editor source of truth; this branch changes only the Web integration repository.
