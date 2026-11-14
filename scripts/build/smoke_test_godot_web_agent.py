#!/usr/bin/env python3
"""Launch the built Godot Web Editor in real Chromium and probe its native agent."""
from __future__ import annotations

import argparse
import json
import mimetypes
import tempfile
import threading
import time
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


class IsolatedHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--editor-zip", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--screenshot", type=Path, default=Path("artifacts/browser-smoke.png"))
    args = parser.parse_args()

    if not args.editor_zip.is_file():
        raise SystemExit(f"Editor archive does not exist: {args.editor_zip}")
    if not 30 <= args.timeout_seconds <= 300:
        raise SystemExit("--timeout-seconds must be 30-300")

    with tempfile.TemporaryDirectory(prefix="godot-agent-browser-") as temp:
        root = Path(temp)
        with zipfile.ZipFile(args.editor_zip) as archive:
            bad = archive.testzip()
            if bad:
                raise RuntimeError(f"Corrupt editor ZIP member: {bad}")
            archive.extractall(root)

        required = (
            "godot.editor.html",
            "godot.editor.js",
            "godot.editor.wasm",
            "service.worker.js",
        )
        missing = [name for name in required if not (root / name).is_file()]
        if missing:
            raise RuntimeError("Missing editor files: " + ", ".join(missing))

        handler = lambda *a, **kw: IsolatedHandler(*a, directory=str(root), **kw)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/godot.editor.html"
        errors: list[str] = []
        page_errors: list[str] = []
        result: dict[str, object] = {}

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--enable-webgl",
                        "--use-gl=angle",
                        "--use-angle=swiftshader",
                    ],
                )
                page = browser.new_page(viewport={"width": 1365, "height": 768})
                page.on("console", lambda msg: errors.append(msg.text[:1000]) if msg.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)[:1000]))
                response = page.goto(url, wait_until="domcontentloaded", timeout=90000)
                if response is None or response.status != 200:
                    raise RuntimeError(f"Editor HTML failed to load: {response.status if response else 'no response'}")

                page.wait_for_function(
                    "() => !!(window.__godotEditorAgent && typeof window.__godotEditorAgent.dispatch === 'function')",
                    timeout=args.timeout_seconds * 1000,
                )

                runtime = page.evaluate("""() => ({
                    title: document.title,
                    cross_origin_isolated: self.crossOriginIsolated,
                    shared_array_buffer: typeof SharedArrayBuffer,
                    wasm_threads: typeof SharedArrayBuffer === 'function',
                    canvases: [...document.querySelectorAll('canvas')].map(c => ({
                        width: c.width, height: c.height,
                        visible_width: Math.round(c.getBoundingClientRect().width),
                        visible_height: Math.round(c.getBoundingClientRect().height)
                    })),
                    adapter_protocol: window.__godotEditorAgent.protocol,
                    adapter_version: window.__godotEditorAgent.version,
                    capabilities: window.__godotEditorAgent.getCapabilities()
                })""")
                if not runtime["cross_origin_isolated"] or not runtime["wasm_threads"]:
                    raise RuntimeError("Threaded WebAssembly prerequisites are missing: " + json.dumps(runtime))

                capabilities = runtime["capabilities"]
                if capabilities.get("protocol") != 1:
                    raise RuntimeError("Unexpected native agent protocol: " + json.dumps(capabilities))

                probes = {}
                for command in ("editor.list_capabilities", "editor.get_state"):
                    request_id = "chromium-smoke-" + command
                    probe = page.evaluate(
                        """async ({command, id}) => await Promise.race([
                            window.__godotEditorAgent.dispatch({id, command, args: {}}),
                            new Promise(resolve => setTimeout(() => resolve({timeout: true}), 15000))
                        ])""",
                        {"command": command, "id": request_id},
                    )
                    if probe.get("timeout") or probe.get("ok") is not True or probe.get("id") != request_id:
                        raise RuntimeError(f"Native command failed ({command}): {json.dumps(probe)}")
                    probes[command] = probe

                # With no project loaded, NO_ACTIVE_SCENE is the expected bounded response.
                tree_probe = page.evaluate(
                    """async () => await Promise.race([
                        window.__godotEditorAgent.dispatch({
                            id: "chromium-smoke-scene-tree",
                            command: "scene.get_tree",
                            args: {}
                        }),
                        new Promise(resolve => setTimeout(() => resolve({timeout: true}), 15000))
                    ])"""
                )
                if tree_probe.get("timeout") or tree_probe.get("id") != "chromium-smoke-scene-tree":
                    raise RuntimeError("Scene-tree request did not return a correlated response: " + json.dumps(tree_probe))
                if tree_probe.get("ok") is not True and tree_probe.get("error") != "NO_ACTIVE_SCENE":
                    raise RuntimeError("Unexpected scene-tree response: " + json.dumps(tree_probe))
                probes["scene.get_tree"] = tree_probe

                pending = page.evaluate("() => window.__godotEditorAgentPending?.size ?? -1")
                if pending != 0:
                    raise RuntimeError(f"Native agent leaked pending requests: {pending}")

                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(args.screenshot), full_page=False)
                result = {
                    "ok": True,
                    "url": url,
                    "runtime": runtime,
                    "probes": probes,
                    "pending_requests_after_probes": pending,
                    "console_errors": errors[-30:],
                    "page_errors": page_errors[-30:],
                    "note": "This smoke test validates the editor shell and native read-only bridge. A real imported project is validated separately.",
                }
                browser.close()
        finally:
            server.shutdown()
            server.server_close()

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
