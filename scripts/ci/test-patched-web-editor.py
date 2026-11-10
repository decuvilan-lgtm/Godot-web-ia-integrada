#!/usr/bin/env python3
"""Smoke-test the compiled, patched Godot Web editor in real Chromium.

This checks the generated bundle, starts it with the isolation headers required
by WebAssembly threads, waits for the actual editor canvas, and saves evidence.
It does not claim that a GitHub import was completed.
"""
from __future__ import annotations
import hashlib
import http.server
import pathlib
import tempfile
import threading
import zipfile
from playwright.sync_api import sync_playwright

BUNDLE = pathlib.Path("engine/godot/bin/godot.web.editor.wasm32.zip")
REQUIRED = (
    b"Import from GitHub",
    b"Enter a public GitHub repository URL or owner/repository.",
    b"Invalid repository. Use https://github.com/owner/repository.",
    b"GitHub download failed (HTTP %d).",
)

class IsolatedHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        super().end_headers()

def main():
    if not BUNDLE.is_file():
        raise SystemExit(f"Missing compiled bundle: {BUNDLE}")
    digest = hashlib.sha256(BUNDLE.read_bytes()).hexdigest()
    with zipfile.ZipFile(BUNDLE) as archive:
        names = set(archive.namelist())
        needed = {"godot.editor.html", "godot.editor.js", "godot.editor.wasm"}
        if not needed <= names:
            raise SystemExit(f"Bundle is missing required files: {sorted(needed - names)}")
        wasm = archive.read("godot.editor.wasm")
        missing = [item.decode() for item in REQUIRED if item not in wasm]
        if missing:
            raise SystemExit(f"Patched importer strings missing from WASM: {missing}")
        with tempfile.TemporaryDirectory(prefix="patched-godot-web-") as temp:
            archive.extractall(temp)
            handler = lambda *args, **kwargs: IsolatedHandler(*args, directory=temp, **kwargs)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 8765), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            errors = []
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True, args=[
                        "--no-sandbox", "--enable-webgl", "--use-gl=angle",
                        "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                    ])
                    page = browser.new_page(viewport={"width": 1440, "height": 900})
                    page.on("pageerror", lambda error: errors.append(str(error)[:1000]))
                    response = page.goto("http://127.0.0.1:8765/godot.editor.html",
                                         wait_until="domcontentloaded", timeout=120000)
                    if response is None or response.status >= 400:
                        raise RuntimeError("Could not load compiled Godot Web editor")
                    page.wait_for_function(
                        "() => [...document.querySelectorAll('canvas')].some(c => c.width > 320 && c.height > 200)",
                        timeout=240000,
                    )
                    page.wait_for_timeout(10000)
                    page.screenshot(path="patched-godot-web-project-manager.png",
                                    full_page=True, animations="disabled")
                    if errors:
                        raise RuntimeError(f"Browser page errors: {errors[:10]}")
                    print(f"Browser boot passed; bundle SHA256: {digest}")
                    print(f"Canvas count: {page.locator('canvas').count()}")
                    browser.close()
            finally:
                server.shutdown()
    print("WASM importer markers and Chromium editor boot passed.")

if __name__ == "__main__":
    main()
