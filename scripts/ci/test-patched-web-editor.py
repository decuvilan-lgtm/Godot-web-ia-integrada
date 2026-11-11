#!/usr/bin/env python3
"""Boot-test Godot Web and exercise the native public-GitHub project import flow."""
from __future__ import annotations
import hashlib
import http.server
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from playwright.sync_api import sync_playwright

BUNDLE = pathlib.Path("engine/godot/bin/godot.web.editor.wasm32.zip")
SCREENSHOT = pathlib.Path("patched-godot-web-project-manager.png")
IMPORT_SCREENSHOT = pathlib.Path("patched-godot-web-github-import.png")
DIAGNOSTICS = pathlib.Path("patched-godot-web-diagnostics.json")
TEST_REPOSITORY = "MCMLXXXV/godot-minimal-template"
EXPECTED_PROJECT_TEXT = ("godot minimal project template", "godot-minimal-template")
# Only assert stable UI markers in the compiled artifact. Diagnostic wording is
# intentionally tested against source by the patcher unit tests, not WASM: changing
# an error message must never prevent Chromium from reaching the real import test.
REQUIRED = (
    b"Import from GitHub",
    b"Enter a public GitHub repository URL or owner/repository.",
    b"Invalid repository. Use https://github.com/owner/repository.",
)

class IsolatedHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        super().end_headers()

def canvas_text(page) -> str:
    if not shutil.which("tesseract"):
        raise RuntimeError("tesseract-ocr is required to verify text rendered inside Godot's canvas")
    image = pathlib.Path("godot-project-manager-ocr.png")
    page.screenshot(path=str(image), full_page=True)
    result = subprocess.run(
        ["tesseract", str(image), "stdout", "--psm", "11"],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.lower()

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
            diagnostics = {
                "bundle_sha256": digest, "browser_console": [], "page_errors": [],
                "failed_requests": [], "responses": [], "startup_actions": [],
                "github_import": {"repository": TEST_REPOSITORY, "attempted": False, "passed": False},
            }
            relay_log = pathlib.Path("github-import-relay.log").open("w", encoding="utf-8")
            relay_env = os.environ.copy()
            relay_env["ALLOWED_ORIGINS"] = "http://127.0.0.1:8765"
            relay_env["RELAY_LEGACY_BRIDGE_ENABLED"] = "false"
            relay = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8766"],
                cwd="relay", env=relay_env, stdout=relay_log, stderr=subprocess.STDOUT,
            )
            try:
                relay_ready = False
                for _ in range(60):
                    try:
                        with urllib.request.urlopen("http://127.0.0.1:8766/health", timeout=2) as health:
                            relay_ready = health.status == 200
                        if relay_ready:
                            break
                    except Exception:
                        time.sleep(1)
                if not relay_ready:
                    raise RuntimeError("Local GitHub import Relay did not become healthy; inspect github-import-relay.log")
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True, args=[
                        "--no-sandbox", "--enable-webgl", "--use-gl=angle",
                        "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                    ])
                    try:
                        page = browser.new_page(viewport={"width": 1440, "height": 900})
                        page.on("console", lambda msg: diagnostics["browser_console"].append(
                            {"type": msg.type, "text": msg.text[:2000]}) if msg.type == "error" else None)
                        page.on("pageerror", lambda error: diagnostics["page_errors"].append(str(error)[:3000]))
                        page.on("requestfailed", lambda req: diagnostics["failed_requests"].append(
                            {"url": req.url, "failure": req.failure}))
                        page.on("response", lambda res: diagnostics["responses"].append(
                            {"status": res.status, "url": res.url}) if any(x in res.url for x in
                            ("godot.editor", ".wasm", ".worker", ".js", "api.github.com", "127.0.0.1:8766")) else None)

                        response = page.goto("http://127.0.0.1:8765/godot.editor.html",
                                             wait_until="domcontentloaded", timeout=60000)
                        diagnostics["document_response"] = response.status if response else None
                        if response is None or response.status >= 400:
                            raise RuntimeError("Compiled Godot HTML did not load")

                        dismiss = page.locator("#welcome-modal-dismiss")
                        if dismiss.is_visible():
                            dismiss.click()
                            diagnostics["startup_actions"].append("dismissed welcome modal")
                        start = page.locator("#startButton")
                        start.wait_for(state="visible", timeout=15000)
                        if start.is_disabled():
                            raise RuntimeError("Godot Start button is disabled; inspect missing browser features")
                        start.click()
                        diagnostics["startup_actions"].append("clicked Start Godot Editor")

                        page.wait_for_function("""() => {
                          const c = document.querySelector('#editor-canvas');
                          return c && c.width > 320 && c.height > 200 &&
                            c.getBoundingClientRect().width > 320 &&
                            c.getBoundingClientRect().height > 200;
                        }""", timeout=240000)
                        diagnostics["canvas_detected"] = True
                        page.wait_for_timeout(5000)
                        diagnostics["page_state"] = page.evaluate("""() => ({
                          readyState: document.readyState, title: document.title,
                          canvases: [...document.querySelectorAll('canvas')].map(c => ({
                            id:c.id,width:c.width,height:c.height
                          })),
                          crossOriginIsolated: window.crossOriginIsolated,
                          sharedArrayBuffer: typeof SharedArrayBuffer !== 'undefined',
                          webAssembly: typeof WebAssembly !== 'undefined',
                          webgl: (()=>{const c=document.createElement('canvas');
                            return !!(c.getContext('webgl2')||c.getContext('webgl'));})()
                        })""")
                        page.screenshot(path=str(SCREENSHOT), full_page=True)
                        if diagnostics["page_errors"]:
                            raise RuntimeError(f"Browser boot produced JS errors: {diagnostics['page_errors'][:3]}")
                        print(f"Browser boot passed; bundle SHA256: {digest}")

                        # Godot renders Project Manager controls into its canvas, so this
                        # interaction intentionally uses real pointer/keyboard input.
                        page.mouse.click(215, 98)  # GitHub button in the Project Manager toolbar.
                        page.wait_for_timeout(900)
                        page.screenshot(path=str(IMPORT_SCREENSHOT), full_page=True)
                        diagnostics["github_import"]["dialog_opened"] = True
                        # The native LineEdit is focused by the importer. Verify visible input before submit.
                        page.keyboard.type(TEST_REPOSITORY, delay=12)
                        page.wait_for_timeout(300)
                        page.screenshot(path=str(IMPORT_SCREENSHOT), full_page=True)
                        input_text = canvas_text(page)
                        normalized_input = "".join(ch for ch in input_text if ch.isalnum())
                        diagnostics["github_import"]["input_visible"] = (
                            "mcmlxxxv" in normalized_input and "godotminimaltemplate" in normalized_input
                        )
                        if not diagnostics["github_import"]["input_visible"]:
                            diagnostics["github_import"]["ocr_input_text"] = input_text[:2000]
                            raise RuntimeError(
                                "GitHub dialog opened, but repository text was not visible in its input field."
                            )
                        page.keyboard.press("Enter")  # registered LineEdit submission triggers Download.
                        diagnostics["github_import"]["attempted"] = True
                        diagnostics["github_import"]["input"] = TEST_REPOSITORY

                        deadline = time.monotonic() + 150
                        observed = ""
                        while time.monotonic() < deadline:
                            page.wait_for_timeout(2500)
                            observed = canvas_text(page)
                            if any(term in observed for term in EXPECTED_PROJECT_TEXT):
                                diagnostics["github_import"]["passed"] = True
                                break
                            if diagnostics["page_errors"]:
                                break
                        diagnostics["github_import"]["ocr_text"] = observed[:4000]
                        diagnostics["github_import"]["responses"] = [
                            item for item in diagnostics["responses"]
                            if "127.0.0.1:8766/v1/github/import/" in item["url"]
                        ]
                        page.screenshot(path=str(SCREENSHOT), full_page=True)
                        if not diagnostics["github_import"]["passed"]:
                            raise RuntimeError(
                                "GitHub import was triggered but the imported project did not appear "
                                "in the Project Manager before timeout. Inspect GitHub import screenshot "
                                "and OCR diagnostics."
                            )
                        if not any(item["status"] == 200 for item in diagnostics["github_import"]["responses"]):
                            raise RuntimeError("Project appeared but no successful Relay archive response was recorded")
                        print(f"GitHub repository import passed: {TEST_REPOSITORY}")
                    finally:
                        browser.close()
            except Exception as exc:
                diagnostics["test_error"] = str(exc)[:3000]
                raise
            finally:
                relay.terminate()
                try:
                    relay.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    relay.kill()
                    relay.wait(timeout=5)
                relay_log.close()
                diagnostics["captured_at"] = time.time()
                DIAGNOSTICS.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
                server.shutdown()
    print("WASM markers, Chromium boot, and real GitHub project import passed.")

if __name__ == "__main__":
    main()
