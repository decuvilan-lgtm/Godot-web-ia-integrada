#!/usr/bin/env python3
"""Launch the built Godot Web Editor in Chromium, import a clean project, and probe its agent."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
import threading
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from diagnostics.classifier import classify_event, link_continuation_events, redact_sensitive_payload, summarize_events
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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--editor-zip", type=Path)
    source.add_argument("--editor-dir", type=Path)
    parser.add_argument("--entrypoint", default="godot.editor.html")
    parser.add_argument("--project-dir", type=Path, default=REPO_ROOT / "tests/fixtures/diagnostics-godot-project")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--screenshot", type=Path, default=Path("artifacts/browser-smoke.png"))
    parser.add_argument("--diagnostics", type=Path, default=Path("artifacts/browser-smoke-diagnostics.json"))
    args = parser.parse_args()

    if args.editor_zip and not args.editor_zip.is_file():
        raise SystemExit(f"Editor archive does not exist: {args.editor_zip}")
    if args.editor_dir and not args.editor_dir.is_dir():
        raise SystemExit(f"Editor directory does not exist: {args.editor_dir}")
    if args.entrypoint.startswith("/") or ".." in Path(args.entrypoint.split("?", 1)[0]).parts:
        raise SystemExit("--entrypoint must be a relative path inside the editor directory")
    if not 30 <= args.timeout_seconds <= 900:
        raise SystemExit("--timeout-seconds must be 30-900")
    project_dir = args.project_dir.resolve()
    if not project_dir.is_dir():
        raise SystemExit(f"Project directory does not exist: {project_dir}")

    original_digest = project_digest(project_dir)
    # Preserve every browser console event, including log/warning messages.
    # Chromium's message type is transport metadata, not necessarily the
    # originating engine's severity (Godot prefixes its own severity).
    console_events: list[dict[str, object]] = []
    errors: list[str] = []
    page_errors: list[str] = []
    request_failures: list[str] = []
    http_errors: list[str] = []
    worker_urls: list[str] = []
    raw_diagnostic_events: list[dict[str, object]] = []
    current_diagnostic_context = "godot_web_editor_runtime"

    def record_diagnostic(message: str, transport_type: str, source_hint: str, location=None) -> None:
        nonlocal current_diagnostic_context
        # Browser console APIs may deliver a multiline Godot stack trace as one
        # message. Split it into ordered records so each "at:" frame is classified
        # and linked to the preceding root error.
        for line in str(message).splitlines():
            if not line.strip():
                continue
            if "PROJECT_DIAG_BEGIN" in line:
                current_diagnostic_context = "godot_project_runtime"
            raw_diagnostic_events.append({
                "message": line,
                "transport_type": transport_type,
                "source_hint": source_hint,
                "timestamp_ns": time.time_ns(),
                "location": location,
                "context": current_diagnostic_context,
            })
            if "PROJECT_DIAG_END" in line:
                current_diagnostic_context = "godot_web_editor_runtime"

    def build_diagnostic_report() -> dict[str, object]:
        classified = [
            classify_event(
                str(raw_event["message"]),
                transport_type=str(raw_event["transport_type"]),
                source_hint=str(raw_event["source_hint"]),
                context=str(raw_event.get("context") or "godot_web_editor_runtime"),
                timestamp=str(raw_event["timestamp_ns"]),
                location=raw_event["location"] if isinstance(raw_event["location"], dict) else None,
            )
            for raw_event in raw_diagnostic_events
        ]
        classified = link_continuation_events(classified)
        summary = summarize_events(classified)
        severities = summary["severity_counts"]
        if severities.get("fatal", 0) or severities.get("error", 0):
            health_status = "degraded"
        elif severities.get("warning", 0) and summary["unknown_events"]:
            health_status = "warnings_and_unclassified"
        elif severities.get("warning", 0):
            health_status = "warnings"
        elif summary["unknown_events"]:
            health_status = "unclassified"
        else:
            health_status = "clean"
        return {
            "health_status": health_status,
            "raw_events": raw_diagnostic_events,
            "classification": summary,
        }

    result: dict[str, object] = {}

    with tempfile.TemporaryDirectory(prefix="godot-agent-browser-") as temp:
        root = Path(temp)
        if args.editor_dir:
            editor_root = args.editor_dir.resolve()
        else:
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
        origin = f"http://127.0.0.1:{server.server_port}"
        extension_dir = root / "extension"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        context = None
        page = None

        try:
            prepare_extension(REPO_ROOT / "browser-extension", extension_dir, origin)
            thread.start()
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    str(root / "chromium-profile"),
                    channel="chromium",
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--enable-webgl",
                        "--enable-unsafe-swiftshader",
                        "--use-gl=angle",
                        "--use-angle=swiftshader",
                        "--disable-extensions-except=" + str(extension_dir),
                        "--load-extension=" + str(extension_dir),
                    ],
                    viewport={"width": 1365, "height": 768},
                    device_scale_factor=1,
                )
                page = context.new_page()

                def record_console_message(msg) -> None:
                    entry = {
                        "transport_type": msg.type,
                        "text": msg.text,
                        "location": msg.location,
                        "timestamp_ns": time.time_ns(),
                    }
                    console_events.append(entry)
                    record_diagnostic(msg.text, msg.type, "browser_console", msg.location)
                    if msg.type == "error":
                        errors.append(msg.text[:1000])

                page.on("console", record_console_message)

                def record_page_error(error) -> None:
                    message = str(error)
                    page_errors.append(message[:1000])
                    record_diagnostic(message, "error", "javascript")

                def record_request_failure(request) -> None:
                    message = f"{request.method} {request.url}: {request.failure}"
                    request_failures.append(message)
                    record_diagnostic(message, "error", "network", {"url": request.url})

                def record_http_response(response) -> None:
                    if response.status >= 400:
                        message = f"HTTP {response.status} {response.url}"
                        http_errors.append(message)
                        record_diagnostic(message, "error", "http", {"url": response.url, "status": response.status})

                page.on("pageerror", record_page_error)
                page.on("requestfailed", record_request_failure)
                page.on("response", record_http_response)
                page.on("worker", lambda worker: worker_urls.append(worker.url))

                response = page.goto(origin + "/" + args.entrypoint, wait_until="domcontentloaded", timeout=90000)
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

                # Wait for the actual Godot startup cycle, not merely for the HTML shell.
                page.wait_for_function(
                    "() => getComputedStyle(document.querySelector('#status-indeterminate')).display !== 'none'",
                    timeout=30000,
                )
                page.wait_for_function(
                    "() => getComputedStyle(document.querySelector('#status-indeterminate')).display === 'none'",
                    timeout=args.timeout_seconds * 1000,
                )
                if page.locator("#status-notice").is_visible():
                    notice = page.locator("#status-notice").inner_text()
                    raise RuntimeError("Godot reported an editor startup error: " + notice)
                page.wait_for_function(
                    "() => { const c = document.querySelector('#editor-canvas'); return !!c && c.width > 0 && c.height > 0; }",
                    timeout=30000,
                )
                # The dropped ZIP opens ProjectDialog in Project Manager. Its focused
                # Project Path LineEdit submits the default valid install path on Enter.
                page.wait_for_timeout(2500)
                page.locator("#editor-canvas").focus()
                page.keyboard.press("Enter")

                try:
                    page.wait_for_function(
                        "() => !!(window.__godotEditorAgent && typeof window.__godotEditorAgent.dispatch === 'function')",
                        timeout=args.timeout_seconds * 1000,
                    )
                except Exception as exc:
                    diagnostics = page.evaluate("""() => {
                        const visible = (selector) => {
                            const element = document.querySelector(selector);
                            if (!element) return null;
                            const rect = element.getBoundingClientRect();
                            const style = getComputedStyle(element);
                            return {
                                text: (element.innerText || element.textContent || "").slice(0, 5000),
                                display: style.display,
                                visibility: style.visibility,
                                disabled: "disabled" in element ? element.disabled : null,
                                width: Math.round(rect.width),
                                height: Math.round(rect.height)
                            };
                        };
                        return {
                            url: location.href,
                            ready_state: document.readyState,
                            title: document.title,
                            body_text: (document.body?.innerText || "").slice(0, 12000),
                            cross_origin_isolated: self.crossOriginIsolated,
                            shared_array_buffer: typeof SharedArrayBuffer,
                            engine_constructor: typeof Engine,
                            adapter_present: !!window.__godotEditorAgent,
                            canvases: [...document.querySelectorAll("canvas")].map(c => ({
                                id: c.id, width: c.width, height: c.height,
                                visible_width: Math.round(c.getBoundingClientRect().width),
                                visible_height: Math.round(c.getBoundingClientRect().height)
                            })),
                            start_button: visible("#startButton"),
                            status_notice: visible("#status-notice"),
                            status_progress: visible("#status-progress"),
                            status_indeterminate: visible("#status-indeterminate"),
                            editor_tab: visible("#btn-tab-editor"),
                            loader_tab: visible("#btn-tab-loader"),
                            tabs: visible("#tabs-buttons"),
                            service_worker_controller: !!navigator.serviceWorker?.controller,
                            performance_resources: performance.getEntriesByType("resource")
                                .filter(r => /wasm|worker|[.]js(?:$|[?])/i.test(r.name))
                                .slice(-30).map(r => ({name: r.name, duration: Math.round(r.duration), transfer_size: r.transferSize}))
                        };
                    }""")
                    diagnostics["console_errors"] = errors[-50:]
                    diagnostics["diagnostic_report"] = build_diagnostic_report()
                    diagnostics["page_errors"] = page_errors[-50:]
                    diagnostics["request_failures"] = request_failures[-50:]
                    diagnostics["http_errors"] = http_errors[-50:]
                    diagnostics["workers"] = worker_urls[-30:]
                    diagnostics["wait_error"] = str(exc)
                    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                    args.diagnostics.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        page.screenshot(path=str(args.screenshot), full_page=False, timeout=30000)
                        diagnostics["screenshot"] = str(args.screenshot)
                    except Exception as screenshot_error:
                        diagnostics["screenshot_error"] = str(screenshot_error)
                    diagnostics, report_redactions = redact_sensitive_payload(diagnostics)
                    diagnostics["report_redactions_applied"] = report_redactions
                    args.diagnostics.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
                    print("BROWSER_SMOKE_DIAGNOSTICS=" + json.dumps(diagnostics, indent=2), flush=True)
                    raise RuntimeError(
                        "Native adapter did not appear within "
                        f"{args.timeout_seconds}s. Browser diagnostics were saved to {args.diagnostics}"
                    ) from exc
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
                        diagnostics = page.evaluate("""() => ({
                            url: location.href,
                            title: document.title,
                            body_text: (document.body?.innerText || "").slice(0, 10000),
                            adapter_present: !!window.__godotEditorAgent,
                            adapter_protocol: window.__godotEditorAgent?.protocol ?? null,
                            adapter_capabilities: window.__godotEditorAgent?.getCapabilities?.() ?? null,
                            native_pending_count: window.__godotEditorAgentPending?.size ?? -1,
                            native_pending_ids: window.__godotEditorAgentPending
                                ? [...window.__godotEditorAgentPending.keys()] : [],
                            canvases: [...document.querySelectorAll("canvas")].map(c => ({
                                id: c.id, width: c.width, height: c.height,
                                visible_width: Math.round(c.getBoundingClientRect().width),
                                visible_height: Math.round(c.getBoundingClientRect().height)
                            })),
                            editor_tab: (() => {
                                const e = document.querySelector("#btn-tab-editor");
                                return e ? {disabled: e.disabled, text: e.innerText} : null;
                            })(),
                            status_notice: document.querySelector("#status-notice")?.innerText ?? "",
                            service_worker_controller: !!navigator.serviceWorker?.controller
                        })""")
                        diagnostics["failed_command"] = command
                        diagnostics["probe_result"] = probe
                        diagnostics["console_errors"] = errors[-50:]
                        diagnostics["diagnostic_report"] = build_diagnostic_report()
                        diagnostics["page_errors"] = page_errors[-50:]
                        diagnostics["request_failures"] = request_failures[-50:]
                        diagnostics["http_errors"] = http_errors[-50:]
                        diagnostics["workers"] = worker_urls[-30:]
                        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                        args.diagnostics.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            page.screenshot(path=str(args.screenshot), full_page=False, timeout=30000)
                            diagnostics["screenshot"] = str(args.screenshot)
                        except Exception as screenshot_error:
                            diagnostics["screenshot_error"] = str(screenshot_error)
                        diagnostics, report_redactions = redact_sensitive_payload(diagnostics)
                        diagnostics["report_redactions_applied"] = report_redactions
                        args.diagnostics.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
                        print("BROWSER_SMOKE_DIAGNOSTICS=" + json.dumps(diagnostics, indent=2), flush=True)
                        raise RuntimeError(
                            f"Extension semantic command failed ({command}): {json.dumps(probe)}"
                        )
                    probes[command] = probe

                state = probes["editor.get_state"].get("result", {})
                if state.get("editor_available") is not True:
                    raise RuntimeError("Godot EditorInterface was not available: " + json.dumps(probes["editor.get_state"]))

                pending = page.evaluate("() => window.__godotEditorAgentPending?.size ?? -1")
                if pending != 0:
                    raise RuntimeError(f"Native agent leaked pending requests: {pending}")

                # Fail fast if any of the previously observed Web editor startup regressions return.
                startup_regressions = [
                    str(event.get("text", ""))
                    for event in console_events
                    if (
                        'Parameter "create_fn" is null' in str(event.get("text", ""))
                        or "Attempt of waiting to finish on a thread that was never started." in str(event.get("text", ""))
                        or (
                            "ERR_CANT_CREATE" in str(event.get("text", ""))
                            and ("DebugAdapter" in str(event.get("text", "")) or "TCPServer" in str(event.get("text", "")))
                        )
                    )
                ]
                if startup_regressions:
                    raise RuntimeError("Known Godot Web startup regressions returned: " + json.dumps(startup_regressions))

                # Run a dedicated fixture that emits one deliberate project-runtime
                # error. This verifies that game diagnostics are captured separately
                # from editor startup and browser transport failures.
                page.locator("#editor-canvas").focus()
                page.keyboard.press("F6")
                runtime_deadline = time.monotonic() + 30
                while time.monotonic() < runtime_deadline:
                    if any("PROJECT_DIAG_END" in str(event.get("text", "")) for event in console_events):
                        break
                    page.wait_for_timeout(100)
                project_marker_events = [
                    event for event in console_events
                    if "PROJECT_DIAG_BEGIN" in str(event.get("text", ""))
                    or "PROJECT_DIAG_END" in str(event.get("text", ""))
                ]
                project_error_events = [
                    event for event in raw_diagnostic_events
                    if event.get("context") == "godot_project_runtime"
                    and "PROJECT_DIAG_FIXTURE" in str(event.get("message", ""))
                ]
                marker_texts = [str(event.get("text", "")) for event in project_marker_events]
                markers_are_complete = (
                    len(marker_texts) == 2
                    and "PROJECT_DIAG_BEGIN" in marker_texts[0]
                    and "PROJECT_DIAG_END" in marker_texts[1]
                )
                if not markers_are_complete or len(project_error_events) != 1:
                    raise RuntimeError(
                        "Project runtime diagnostic probe did not capture exactly one intentional error: "
                        + json.dumps({
                            "markers": project_marker_events,
                        "source_locations": project_source_locations,
                        "project_error_count": len(project_runtime_errors),
                            "markers_are_complete": markers_are_complete,
                            "project_errors": project_error_events,
                            "recent_console": console_events[-30:],
                        })
                    )

                final_digest = project_digest(project_dir)
                if final_digest != original_digest:
                    raise RuntimeError("The source project changed during browser import.")

                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(args.screenshot), full_page=False)
                diagnostic_report = build_diagnostic_report()
                classified_project_errors = [
                    event for event in diagnostic_report["classification"]["events"]
                    if event.get("context") == "godot_project_runtime"
                    and "PROJECT_DIAG_FIXTURE" in str(event.get("original_message", ""))
                ]
                project_source_locations = [
                    location
                    for event in classified_project_errors
                    for location in event.get("godot_source_locations", [])
                ]
                project_runtime_errors = [
                    event for event in diagnostic_report["classification"]["events"]
                    if event.get("context") == "godot_project_runtime"
                    and event.get("declared_severity") in {"fatal", "error"}
                ]
                actual_locations = {
                    (location.get("path"), location.get("line"))
                    for location in project_source_locations
                }
                expected_locations = {("res://main.gd", 5), ("res://main.gd", 6)}
                if (
                    len(classified_project_errors) != 1
                    or len(project_runtime_errors) != 1
                    or not expected_locations.issubset(actual_locations)
                ):
                    raise RuntimeError(
                        "Project runtime trace was not fully correlated to res://main.gd:5-6: "
                        + json.dumps({
                            "classified_errors": classified_project_errors,
                            "project_runtime_errors": project_runtime_errors,
                            "source_locations": project_source_locations,
                            "raw_project_events": [event for event in raw_diagnostic_events if event.get("context") == "godot_project_runtime"],
                        })
                    )
                denied_write_probe = page.evaluate("""async () => await window.__godotEditorAgent.dispatch({
                    id: "smoke-read-only-deny",
                    command: "editor.execute_script",
                    args: {}
                })""")
                if denied_write_probe.get("ok") is not False or denied_write_probe.get("error") != "COMMAND_NOT_ALLOWED":
                    raise RuntimeError("The built-in agent did not reject a non-allowlisted write command: " + json.dumps(denied_write_probe))
                pending_after_denial = page.evaluate("() => window.__godotEditorAgentPending?.size ?? -1")
                if pending_after_denial != 0:
                    raise RuntimeError(f"Native agent leaked pending requests after denied command: {pending_after_denial}")
                result = {
                    "ok": True,
                    "editor_url": origin + "/" + args.entrypoint,
                    "project": str(project_dir.relative_to(REPO_ROOT)),
                    "source_project_sha256_before": original_digest,
                    "source_project_sha256_after": final_digest,
                    "source_project_unchanged": True,
                    "runtime": runtime,
                    "semantic_probes": probes,
                    "pending_requests_after_probes": pending,
                    "pending_requests_after_denial": pending_after_denial,
                    "read_only_rejection_probe": denied_write_probe,
                    "startup_regressions": startup_regressions,
                    "project_runtime_probe": {
                        "ok": True,
                        "intentional_error_count": len(project_error_events),
                        "events": project_error_events,
                        "markers": project_marker_events,
                    },
                    "console_errors": errors[-30:],
                    "console_events_raw": console_events,
                    "diagnostics": diagnostic_report,
                    "page_errors": page_errors[-30:],
                    "request_failures": request_failures[-30:],
                    "http_errors": http_errors[-30:],
                    "workers": worker_urls[-20:],
                    "note": "The built editor imported a clean project, exposed the native read-only adapter, and answered through the Chromium extension relay. This does not yet validate the deployed Render wrapper.",
                }
                result, report_redactions = redact_sensitive_payload(result)
                result["report_redactions_applied"] = report_redactions
                print(json.dumps(result, indent=2))
                args.diagnostics.parent.mkdir(parents=True, exist_ok=True)
                args.diagnostics.write_text(json.dumps(result, indent=2), encoding="utf-8")
        except Exception as exc:
            failure_diagnostics = {
                "ok": False,
                "failure": f"{type(exc).__name__}: {str(exc)[:2000]}",
                "console_events_raw": console_events[-200:],
                "raw_diagnostic_events": raw_diagnostic_events[-500:],
                "diagnostics": build_diagnostic_report(),
                "page_errors": page_errors[-100:],
                "request_failures": request_failures[-100:],
                "http_errors": http_errors[-100:],
                "workers": worker_urls[-50:],
            }
            if page is not None:
                try:
                    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(args.screenshot), full_page=False, timeout=10000)
                    failure_diagnostics["screenshot"] = str(args.screenshot)
                except Exception as screenshot_error:
                    failure_diagnostics["screenshot_error"] = str(screenshot_error)
            failure_diagnostics, report_redactions = redact_sensitive_payload(failure_diagnostics)
            failure_diagnostics["report_redactions_applied"] = report_redactions
            args.diagnostics.parent.mkdir(parents=True, exist_ok=True)
            args.diagnostics.write_text(json.dumps(failure_diagnostics, indent=2), encoding="utf-8")
            print("BROWSER_SMOKE_FAILURE_DIAGNOSTICS=" + json.dumps(failure_diagnostics, indent=2), flush=True)
            raise
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            if thread.is_alive():
                server.shutdown()
                thread.join(timeout=5)
            server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
