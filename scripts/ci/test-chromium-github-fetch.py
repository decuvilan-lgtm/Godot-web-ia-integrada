#!/usr/bin/env python3
"""Isolated Chromium diagnostic for the GitHub ZIP download used by the Web editor."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

REPOSITORY = "MCMLXXXV/godot-minimal-template"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/zipball"
META_URL = f"https://api.github.com/repos/{REPOSITORY}"
result = {"repository": REPOSITORY, "api_url": API_URL, "browser": {}, "direct_http": {}}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page()
    page.on("console", lambda msg: result.setdefault("console", []).append({"type": msg.type, "text": msg.text}))
    page.on("requestfailed", lambda req: result.setdefault("failed_requests", []).append({"url": req.url, "failure": req.failure}))
    page.goto("data:text/html,<html><body>Chromium isolated GitHub fetch test</body></html>")
    result["browser"]["version"] = browser.version
    result["browser"]["runtime"] = page.evaluate("""async ({metaUrl, zipUrl}) => {
      const out = {};
      for (const [key, url] of [['metadata', metaUrl], ['zipball', zipUrl]]) {
        try {
          const response = await fetch(url, {redirect: 'follow'});
          out[key] = {ok: response.ok, status: response.status, url: response.url,
                      type: response.type, contentType: response.headers.get('content-type')};
          if (key === 'metadata' && response.ok) {
            const json = await response.json();
            out[key].full_name = json.full_name;
          } else if (key === 'zipball' && response.ok) {
            const blob = await response.blob();
            out[key].bytes = blob.size;
          }
        } catch (error) {
          out[key] = {error: String(error)};
        }
      }
      return out;
    }""", {"metaUrl": META_URL, "zipUrl": API_URL})
    browser.close()

    request = p.request.new_context(extra_http_headers={"Accept": "application/vnd.github+json"})
    for key, url in [("metadata", META_URL), ("zipball", API_URL)]:
        try:
            response = request.get(url, timeout=60000)
            result["direct_http"][key] = {"status": response.status, "url": response.url,
                                           "content_type": response.headers.get("content-type"),
                                           "bytes": len(response.body())}
        except Exception as error:
            result["direct_http"][key] = {"error": str(error)}
    request.dispose()

Path("chromium-isolated-diagnostics.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
if not result["browser"].get("version"):
    raise SystemExit("Chromium did not launch successfully")
if result["direct_http"].get("metadata", {}).get("status") != 200:
    raise SystemExit("Runner could not reach GitHub repository metadata")
if result["direct_http"].get("zipball", {}).get("status") != 200 or not result["direct_http"].get("zipball", {}).get("bytes"):
    raise SystemExit("Runner could not download the public GitHub archive")
print("Chromium runtime passed. GitHub browser CORS behavior is recorded for diagnosis; server-side HTTP download passed.")
