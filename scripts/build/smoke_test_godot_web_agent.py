#!/usr/bin/env python3
"""Launch the built Godot Web Editor in Chromium, import a clean project, and probe its agent."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import threading
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from bridge.semantic_controller import execute_semantic_command


class IsolatedHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def project_digest(project_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in project_dir.rglob("*") if p.is_file()):
        relative = path.relative_to(project_dir)
        if any(part in {".git", ".godot"} for part in relative.parts):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def package_project(project_dir: Path, archive_path: Path) -> None:
    if not (project_dir / "project.godot").is_file():
        raise RuntimeError(f"Not a Godot project: {project_dir}")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(project_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(project_dir)
            if any(part in {".git", ".godot"} for part in relative.parts):
                continue
            archive.write(path, relative.as_posix())


def prepare_extension(source_dir: Path, target_dir: Path, origin: str) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in ("page-bridge.js", "content.js"):
        shutil.copy2(source_dir / name, target_dir / name)
    manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
    match = origin + "/*"
    manifest["host_permissions"] = [match]
    for item in manifest.get("content_scripts", []):
        item["matches"] = [match]
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--editor-zip", required=True, type=Path)
    parser.add_argument("--project-dir", type=Path, default=REPO_ROOT / "tests/fixtures/nested-godot-project")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--screenshot", type=Path, default=Path("artifacts/browser-smoke.png"))
    args = parser.parse_args()

    if not args.editor_zip.is_file():
        raise SystemExit(f"Editor archive does not exist: {args.editor_zip}")
    if not 30 <= args.timeout_seconds <= 300:
        raise SystemExit("--timeout-seconds must be 30-300")
    project_dir = args.project_dir.resolve()
    if not project_dir.is_dir():
        raise SystemExit(f"Project directory does not exist: {project_dir}")

    original_digest = project_digest(project_dir)
    errors: list[str] = []
    page_errors: list[str] = []
    result: dict[str, object] = {}

    with tempfile.TemporaryDirectory(prefix="godot-agent-browser-") as temp:
        root = Path(temp)
        editor_root = root / "editor"
        editor_root.mkdir()
        with zipfile.ZipFile(args.editor_zip) as archive:
            bad = archive.testzip()
            if bad:
                raise RuntimeError(f"Corrupt editor ZIP member: {bad}")
            archive.extractall(editor_root)

        required = ("godot.editor.html", "godot.editor.js", "godot.editor.wasm", "service.worker.js")
        missing = [name for name in required if not (editor_root / name).is_file()]
        if missing:
            raise RuntimeError("Missing editor files: " + ", ".join(missing))

        project_zip = root / "bridge-sandbox.zip"
        package_project(project_dir, project_zip)

        handler = lambda *a, **kw: IsolatedHandler(*a, directory=str(editor_root), **kw)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        extension_dir = root / "extension"
        prepare_extension(REPO_ROOT / "browser-extension", extension_dir, origin)

        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    str(root / "chromium-profile"),
                    channel="chromium",
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--enable-webgl",
                        "--use-gl=angle",
                        "--use-angle=swiftshader",
                        "--disable-extensions-except=" + str(extension_dir),
                        "--load-extension=" + str(extension_dir),
                    ],
                    viewport={"width": 1365, "height": 768},
                    device_scale_factor=1,
                )
                page = context.new_page()
                page.on("console", lambda msg: errors.append(msg.text[:1000]) if msg.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)[:1000]))

                response = page.goto(origin + "/godot.editor.html", wait_until="domcontentloaded", timeout=90000)
                if response is None or response.status != 200:
                    raise RuntimeError(f"Editor HTML failed to load: {response.status if response else 'no response'}")

                page.locator("#zip-file").set_input_files(str(project_zip))
                page.locator("#startButton").wait_for(state="visible", timeout=30000)
                welcome_dismiss = page.locator("#welcome-modal-dismiss")
                if welcome_dismiss.is_visible():
                    welcome_dismiss.click(timeout=10000)
                try:
                    page.wait_for_function(
                        "() => !!document.querySelector('#startButton') && !document.querySelector('#startButton').disabled",
                        timeout=30000,
                    )
                except Exception as exc:
                    missing = page.locator("#welcome-modal-missing-list").inner_text() if page.locator("#welcome-modal-missing-list").count() else ""
                    isolation = page.evaluate("() => ({isolated: self.crossOriginIsolated, sharedArrayBuffer: typeof SharedArrayBuffer})")
                    raise RuntimeError(
                        "Godot disabled Start because required browser features are missing: "
                        + json.dumps({"missing": missing, **isolation})
                    ) from exc
                page.locator("#startButton").click(timeout=30000)

                page.wait_for_function(
                    "() => !!(window.__godotEditorAgent && typeof window.__godotEditorAgent.dispatch === 'function')",
                    timeout=args.timeout_seconds * 1000,
                )
                page.locator("#btn-tab-editor").wait_for(state="visible", timeout=30000)
                if page.locator("#btn-tab-editor").is_enabled():
                    page.locator("#btn-tab-editor").click(timeout=10000)
                    page.wait_for_timeout(3000)

                runtime = page.evaluate("""() => ({
                    title: document.title,
                    cross_origin_isolated: self.crossOriginIsolated,
                    shared_array_buffer: typeof SharedArrayBuffer,
                    canvases: [...document.querySelectorAll('canvas')].map(c => ({
                        id: c.id, width: c.width, height: c.height,
                        visible_width: Math.round(c.getBoundingClientRect().width),
                        visible_height: Math.round(c.getBoundingClientRect().height)
                    })),
                    adapter_protocol: window.__godotEditorAgent.protocol,
                    adapter_version: window.__godotEditorAgent.version,
                    capabilities: window.__godotEditorAgent.getCapabilities()
                })""")
                if not runtime["cross_origin_isolated"] or runtime["shared_array_buffer"] != "function":
                    raise RuntimeError("Threaded WebAssembly prerequisites are missing: " + json.dumps(runtime))
                if runtime["capabilities"].get("protocol") != 1:
                    raise RuntimeError("Unexpected native agent protocol: " + json.dumps(runtime["capabilities"]))

                probes = {}
                for command in ("editor.list_capabilities", "editor.get_state", "scene.get_tree"):
                    probe = execute_semantic_command(page, command, timeout_ms=15000)
                    if not probe.get("ok") and not (
                        command == "scene.get_tree" and probe.get("error") == "NO_ACTIVE_SCENE"
                    ):
                        raise RuntimeError(f"Extension semantic command failed ({command}): {json.dumps(probe)}")
                    probes[command] = probe

                state = probes["editor.get_state"].get("result", {})
                if state.get("editor_available") is not True:
                    raise RuntimeError("Godot EditorInterface was not available: " + json.dumps(probes["editor.get_state"]))

                pending = page.evaluate("() => window.__godotEditorAgentPending?.size ?? -1")
                if pending != 0:
                    raise RuntimeError(f"Native agent leaked pending requests: {pending}")

                final_digest = project_digest(project_dir)
                if final_digest != original_digest:
                    raise RuntimeError("The source project changed during browser import.")

                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(args.screenshot), full_page=False)
                result = {
                    "ok": True,
                    "editor_url": origin + "/godot.editor.html",
                    "project": str(project_dir.relative_to(REPO_ROOT)),
                    "source_project_sha256_before": original_digest,
                    "source_project_sha256_after": final_digest,
                    "source_project_unchanged": True,
                    "runtime": runtime,
                    "semantic_probes": probes,
                    "pending_requests_after_probes": pending,
                    "console_errors": errors[-30:],
                    "page_errors": page_errors[-30:],
                    "note": "The built editor imported a clean project, exposed the native read-only adapter, and answered through the Chromium extension relay. This does not yet validate the deployed Render wrapper.",
                }
                print(json.dumps(result, indent=2))
                context.close()
        finally:
            server.shutdown()
            server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
