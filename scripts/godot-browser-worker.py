#!/usr/bin/env python3
"""Real Godot Web browser worker running only inside a GitHub Actions job."""
from __future__ import annotations
import hashlib, io, json, os, re, time, urllib.parse, urllib.request, zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright

RELAY_URL=os.environ.get("RELAY_URL","https://godot-web-ia-relay.onrender.com").rstrip("/")
EDITOR_URL=os.environ.get("EDITOR_URL","https://godot-web-ia-integrada-rt2l.onrender.com/")
REPOSITORY=os.environ["REPOSITORY"]; BRANCH=os.environ.get("BRANCH","main")
PROJECT_PATH=os.environ.get("PROJECT_PATH",""); REQUESTED_SHA=os.environ.get("COMMIT_SHA","").lower()
WAIT_SECONDS=int(os.environ.get("WAIT_SECONDS","10")); IMPORT_TIMEOUT=int(os.environ.get("IMPORT_TIMEOUT_SECONDS","480"))
RUN_ID=os.environ.get("GITHUB_RUN_ID",str(int(time.time()))); ATTEMPT=os.environ.get("GITHUB_RUN_ATTEMPT","1")
OUT=Path("artifacts"); OUT.mkdir(exist_ok=True)

def oidc_token():
    url=os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]+"&audience=godot-web-ia-relay"
    req=urllib.request.Request(url,headers={"Authorization":"Bearer "+os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with urllib.request.urlopen(req,timeout=30) as res: return json.loads(res.read())["value"]

def resolve_sha():
    if REQUESTED_SHA: sha=REQUESTED_SHA
    else:
        branch=urllib.parse.quote(BRANCH,safe="")
        req=urllib.request.Request(f"https://api.github.com/repos/{REPOSITORY}/branches/{branch}",headers={"Accept":"application/vnd.github+json"})
        with urllib.request.urlopen(req,timeout=30) as res: sha=json.loads(res.read())["commit"]["sha"].lower()
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})",sha): raise ValueError("Expected a full Git commit SHA")
    return sha

def main():
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}",REPOSITORY): raise ValueError("Invalid repository")
    if not 60<=IMPORT_TIMEOUT<=600: raise ValueError("IMPORT_TIMEOUT_SECONDS must be 60-600")
    sha=resolve_sha(); session_id=f"gha-{RUN_ID}-{ATTEMPT}"; task_id=f"github-actions-{RUN_ID}-{ATTEMPT}"
    url=EDITOR_URL.rstrip("/")+"/?"+urllib.parse.urlencode({"repo":REPOSITORY,"branch":BRANCH,"path":PROJECT_PATH,"sha":sha})
    errors=[]; page_errors=[]; failed=[]; events=[]; inspection={}; readiness={"phase":"not_started","canvas_count":0}; failure=None
    shot=OUT/"editor-final.png"; started=time.time()
    # Keep the browser process alive through evidence upload; the runner owns its lifetime.
    p = sync_playwright().start()
    if True:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--disable-extensions","--disable-background-networking","--disable-default-apps","--disable-sync","--disable-features=Translate,BackForwardCache,AcceptCHFrame,MediaRouter"])
        context=browser.new_context(viewport={"width":1365,"height":768},device_scale_factor=1,accept_downloads=True)
        page=context.new_page()
        page.on("console",lambda m: errors.append(m.text[:2000]) if m.type=="error" else None)
        page.on("pageerror",lambda e: page_errors.append(str(e)[:2000]))
        page.on("requestfailed",lambda r: failed.append({"url":r.url[:500],"error":str(r.failure)[:500]}))
        try:
            page.goto(url,wait_until="domcontentloaded",timeout=90000)
            if WAIT_SECONDS: page.wait_for_timeout(min(max(WAIT_SECONDS,0),120)*1000)
            deadline=time.monotonic()+IMPORT_TIMEOUT; poll=0
            while time.monotonic()<deadline:
                connector=page.evaluate("() => window.__godotGithubConnectorStatus || null")
                canvases=page.locator("canvas").count(); poll+=1
                readiness={"phase":(connector or {}).get("phase","unknown"),"imported_sha":(connector or {}).get("commitSha",""),"expected_sha":sha,"canvas_count":canvases,"poll_count":poll,"elapsed_seconds":round(time.time()-started,1)}
                events.append({"type":"import.poll",**readiness})
                if readiness["phase"]=="started" and readiness["imported_sha"]==sha and canvases>=1: break
                page.wait_for_timeout(5000)
            inspection={"url":page.url,"title":page.title(),"visible_text":page.locator("body").inner_text(timeout=20000)[:12000],"canvas_count":page.locator("canvas").count(),"connector_status":page.evaluate("() => window.__godotGithubConnectorStatus || null")}
            page.screenshot(path=str(shot),full_page=False,timeout=30000)
            if not(readiness["phase"]=="started" and readiness["imported_sha"]==sha and readiness["canvas_count"]>=1): failure="Exact project SHA was not confirmed before import timeout"
        except Exception as exc:
            failure=f"{type(exc).__name__}: {str(exc)[:1000]}"
            try: page.screenshot(path=str(shot),full_page=False,timeout=15000)
            except Exception: pass
        finally:
            # Do not close Chromium here: keep the editor alive through the evidence round-trip.
            pass
    manifest={"schema_version":1,"worker_backend":"github-actions-hosted-runner","browser_lifetime":"single-workflow-job","session_reconstruction":"fresh-browser-import-at-exact-sha","task_id":task_id,"completed_at":time.time(),"repository":REPOSITORY,"branch":BRANCH,"project_path":PROJECT_PATH,"commit_sha":sha,"editor_url":url,"session_id":session_id,"summary":"Godot Web import and visual inspection on runner-owned Chromium","result":{"ok":failure is None,"failure":failure,"readiness":readiness,"inspection":inspection,"console_errors":errors[-100:],"page_errors":page_errors[-100:],"failed_requests":failed[-100:]},"events":events[-500:],"checkpoint":{"repository":REPOSITORY,"branch":BRANCH,"project_path":PROJECT_PATH,"commit_sha":sha,"editor_url":url,"viewport":{"width":1365,"height":768},"storage_state_saved":False,"reconstruction_mode":"fresh-browser-import"},"artifacts":["editor-final.png"] if shot.exists() else []}
    (OUT/"task-result.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    bundle=OUT/"godot-browser-worker-task.zip"
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as z:
        z.write(OUT/"task-result.json","task-result.json")
        if shot.exists(): z.write(shot,"artifacts/editor-final.png")
    payload=bundle.read_bytes()
    if len(payload)>32*1024*1024: raise ValueError("Evidence bundle exceeds 32 MiB")
    digest=hashlib.sha256(payload).hexdigest()
    req=urllib.request.Request(f"{RELAY_URL}/v1/persistent-sessions/worker-artifacts/{session_id}",data=payload,method="POST",headers={"Authorization":"Bearer "+oidc_token(),"Content-Type":"application/zip","X-Artifact-SHA256":digest})
    with urllib.request.urlopen(req,timeout=90) as res: uploaded=json.loads(res.read())
    (OUT/"worker-upload.json").write_text(json.dumps(uploaded,indent=2),encoding="utf-8")
    get=urllib.request.Request(RELAY_URL+uploaded["artifact_url"],headers={"Authorization":"Bearer "+oidc_token()})
    with urllib.request.urlopen(get,timeout=90) as res: recovered=res.read(32*1024*1024+1)
    if hashlib.sha256(recovered).hexdigest()!=uploaded["artifact_sha256"]: raise RuntimeError("Neon evidence round-trip SHA-256 mismatch")
    with zipfile.ZipFile(io.BytesIO(recovered)) as z:
        if z.testzip(): raise RuntimeError("Persisted evidence ZIP failed integrity check")
    (OUT/"worker-summary.json").write_text(json.dumps({"backend":"GitHub Actions hosted runner","session_id":session_id,"artifact_id":uploaded["artifact_id"],"artifact_sha256":uploaded["artifact_sha256"],"storage":"Neon Object Storage","browser_session_scope":"this workflow job only","reconstruction":"new job reopens exact repository SHA","import_ok":failure is None},indent=2),encoding="utf-8")
    if failure: raise RuntimeError(failure)

if __name__=="__main__": main()
