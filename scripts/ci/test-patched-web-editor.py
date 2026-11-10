#!/usr/bin/env python3
"""Boot-test the patched Godot Web editor and always preserve browser diagnostics."""
from __future__ import annotations
import hashlib
import http.server
import json
import pathlib
import tempfile
import threading
import time
import zipfile
from playwright.sync_api import sync_playwright

BUNDLE = pathlib.Path("engine/godot/bin/godot.web.editor.wasm32.zip")
SCREENSHOT = pathlib.Path("patched-godot-web-project-manager.png")
DIAGNOSTICS = pathlib.Path("patched-godot-web-diagnostics.json")
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
            diagnostics = {"bundle_sha256": digest, "browser_console": [],
                           "page_errors": [], "failed_requests": [], "responses": []}
            browser = None
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True, args=[
                        "--no-sandbox", "--enable-webgl", "--use-gl=angle",
                        "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                    ])
                    page = browser.new_page(viewport={"width": 1440, "height": 900})
                    page.on("console", lambda msg: diagnostics["browser_console"].append(
                        {"type": msg.type, "text": msg.text[:2000]}) if msg.type == "error" else None)
                    page.on("pageerror", lambda error: diagnostics["page_errors"].append(str(error)[:3000]))
                    page.on("requestfailed", lambda req: diagnostics["failed_requests"].append(
                        {"url": req.url, "failure": req.failure}))
                    page.on("response", lambda res: diagnostics["responses"].append(
                        {"status": res.status, "url": res.url}) if any(x in res.url for x in
                        ("godot.editor", ".wasm", ".worker", ".js")) else None)
                    response = page.goto("http://127.0.0.1:8765/godot.editor.html",
                                         wait_until="domcontentloaded", timeout=60000)
                    diagnostics["document_response"] = response.status if response else None
                    try:
                        page.wait_for_function(
                            "() => [...document.querySelectorAll('canvas')].some(c => c.width > 320 && c.height > 200)",
                            timeout=60000,
                        )
                        diagnostics["canvas_detected"] = True
                    except Exception as exc:
                        diagnostics["canvas_detected"] = False
                        diagnostics["canvas_wait_error"] = str(exc)[:1000]
                    page.wait_for_timeout(3000)
                    diagnostics["page_state"] = page.evaluate("""() => ({
                      readyState: document.readyState,
                      title: document.title,
                      bodyText: (document.body?.innerText || '').slice(0, 5000),
                      bodyHTML: (document.body?.innerHTML || '').slice(0, 12000),
                      canvases: [...document.querySelectorAll('canvas')].map(c => ({
                        id: c.id, width: c.width, height: c.height,
                        rect: (() => { const r=c.getBoundingClientRect(); return {
                          x:r.x,y:r.y,width:r.width,height:r.height
                        }; })()
                      })),
                      crossOriginIsolated: window.crossOriginIsolated,
                      sharedArrayBuffer: typeof SharedArrayBuffer !== 'undefined',
                      webAssembly: typeof WebAssembly !== 'undefined',
                      webgl: (() => { const c=document.createElement('canvas');
                        return !!(c.getContext('webgl2') || c.getContext('webgl')); })(),
                      moduleType: typeof window.Module,
                      godotConfigType: typeof window.GodotConfig
                    })""")
                    diagnostics["captured_at"] = time.time()
                    page.screenshot(path=str(SCREENSHOT), full_page=True)
                    DIAGNOSTICS.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
                    if not diagnostics["canvas_detected"] or diagnostics["page_errors"]:
                        raise RuntimeError(
                            "Godot Web editor did not pass browser boot. "
                            f"Diagnostics saved to {DIAGNOSTICS}; "
                            f"canvas={diagnostics['canvas_detected']}, "
                            f"page_errors={diagnostics['page_errors'][:3]}"
                        )
                    print(f"Browser boot passed; bundle SHA256: {digest}")
                    print(f"Canvas count: {len(diagnostics['page_state']['canvases'])}")
            finally:
                if browser:
                    browser.close()
                server.shutdown()
    print("WASM importer markers and Chromium editor boot passed.")

if __name__ == "__main__":
    main()
