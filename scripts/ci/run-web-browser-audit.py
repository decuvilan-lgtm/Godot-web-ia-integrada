#!/usr/bin/env python3
"""Open the deployed Godot Web editor in real Chromium and capture bounded evidence.

The target is intentionally fixed. Workflow inputs cannot supply URLs, paths, or
browser flags. This is a visual smoke test of the published editor page, not proof
that a project is paired or that the Godot Command Center is operational.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

EDITOR_URL = "https://godot-web-ia-integrada-rt2l.onrender.com"
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
RESULTS = pathlib.Path("/tmp/godot-task-results")
MAX_CAPTURE_BYTES = 20 * 1024 * 1024


def main() -> int:
    request_id = os.environ.get("GODOT_TASK_REQUEST_ID", "manual-run")
    if request_id != "manual-run" and not REQUEST_ID_RE.fullmatch(request_id):
        raise SystemExit("Invalid task request ID")

    RESULTS.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_responses: list[dict[str, object]] = []
    captures: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--enable-webgl",
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
            is_mobile=False,
            ignore_https_errors=False,
        )
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.on("console", lambda message: console_errors.append(message.text[:500]) if message.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)[:1000]))
        page.on(
            "response",
            lambda response: failed_responses.append({
                "status": response.status,
                "url": response.url[:500],
            }) if response.status >= 500 else None,
        )

        response = page.goto(EDITOR_URL, wait_until="domcontentloaded", timeout=120_000)
        if response is None or response.status >= 400:
            raise RuntimeError(f"Editor navigation failed: HTTP {response.status if response else 'no response'}")

        # The published editor first shows a limitations dialog and a separate
        # launch button. Dismissing the notice alone does not start the editor.
        notice_button = page.get_by_role("button", name=re.compile(r"OK\s*-\s*Don't Show Again", re.I))
        notice_button.wait_for(state="visible", timeout=60_000)
        notice_button.click()

        start_button = page.get_by_role("button", name=re.compile(r"Start Godot Editor", re.I))
        start_button.wait_for(state="visible", timeout=60_000)
        start_button.click()

        # The editor's boot can take time because the published web bundle is large.
        # Require the launch control to disappear, then allow the UI to settle.
        start_button.wait_for(state="hidden", timeout=180_000)
        page.wait_for_function(
            "() => [...document.querySelectorAll('canvas')].some(c => c.width > 320 && c.height > 200)",
            timeout=60_000,
        )
        page.wait_for_timeout(15_000)

        def save_capture(name: str, viewport: dict[str, int], mobile: bool) -> None:
            page.set_viewport_size(viewport)
            page.wait_for_timeout(1_000)
            path = RESULTS / name
            page.screenshot(path=str(path), full_page=True, animations="disabled")
            size = path.stat().st_size
            if size < 1024 or size > MAX_CAPTURE_BYTES:
                raise RuntimeError(f"Screenshot size outside safe bounds: {name} ({size} bytes)")
            captures.append({
                "file": name,
                "viewport": viewport,
                "mobile_viewport_emulation": mobile,
                "bytes": size,
                "width": viewport["width"],
                "height": viewport["height"],
            })

        title = page.title()
        canvas_count = page.locator("canvas").count()
        editor_started = start_button.is_hidden()
        if not editor_started:
            raise RuntimeError("Godot editor launch button is still visible; editor did not start")
        save_capture("web-editor-desktop.png", {"width": 1440, "height": 900}, False)
        save_capture("web-editor-mobile-viewport.png", {"width": 390, "height": 844}, True)

        browser.close()

    report = {
        "request_id": request_id,
        "profile": "web_browser_audit",
        "status": "succeeded" if not page_errors and not failed_responses else "completed_with_warnings",
        "target": EDITOR_URL,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "page_title": title,
        "canvas_count": canvas_count,
        "editor_started": editor_started,
        "captures": captures,
        "page_errors": page_errors[:30],
        "http_5xx_responses": failed_responses[:30],
        "console_errors": console_errors[:30],
        "notes": [
            "Chromium dismissed the startup notice, launched Godot Editor, and captured the real browser viewport.",
            "Mobile capture uses viewport emulation, not a physical Android device.",
            "This audit does not prove editor pairing, project import, command execution, or private asset retrieval.",
        ],
    }
    (RESULTS / "web-browser-audit.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    if page_errors or failed_responses:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
