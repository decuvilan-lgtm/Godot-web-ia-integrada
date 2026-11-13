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

def relay_request(url, *, method="GET", headers=None, data=None, timeout=90, retry_seconds=360):
    """Retry only transient startup/deploy failures while Render rolls out the API."""
    deadline=time.monotonic()+retry_seconds
    delay=5
    last_error=None
    while True:
        request=urllib.request.Request(url,data=data,method=method,headers=headers or {})
        try:
            with urllib.request.urlopen(request,timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in {404,502,503,504}:
                raise
            last_error=exc
        except urllib.error.URLError as exc:
            last_error=exc
        if time.monotonic()>=deadline:
            raise RuntimeError(f"Relay did not become ready within {retry_seconds}s: {last_error}") from last_error
        time.sleep(min(delay, max(1,deadline-time.monotonic())))
        delay=min(delay+5,25)

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
            if not(readiness["phase"]=="started" and readiness["imported_sha"]==sha and readiness["canvas_count"]>=1):
                failure="Exact project SHA was not confirmed before import timeout"
            else:
                # The published web app has separate Loader, Editor and Game tabs.
                # Import completion leaves Loader selected; explicitly open Editor
                # before judging the project's visual state.
                editor_tab=page.get_by_text("Editor",exact=True)
                if editor_tab.count():
                    editor_tab.first.click(timeout=10000)
                    page.wait_for_timeout(15000)
                    inspection["editor_tab_action"]="clicked Editor tab and waited for the Godot editor surface"
                else:
                    inspection["editor_tab_action"]="Editor tab text was not found"
                if "Project Manager" in page.title():
                    page.screenshot(path=str(OUT/"editor-install-dialog.png"),full_page=False,timeout=30000)
                    install_button=page.get_by_role("button",name=re.compile("Install",re.I))
                    if install_button.count():
                        install_button.first.click(timeout=10000)
                    else:
                        viewport=page.viewport_size or {"width":1365,"height":768}
                        page.mouse.click(viewport["width"]*0.554,viewport["height"]*0.641)
                    install_deadline=time.monotonic()+120
                    while time.monotonic()<install_deadline and "Project Manager" in page.title():
                        page.wait_for_timeout(3000)
                    inspection["install_dialog_action"]="attempted Godot Install action"
                    inspection["post_install_title"]=page.title()
                    if "Project Manager" in page.title():
                        failure="Godot remained in Project Manager after the project Install action"
                inspection["visual_surface"]=page.evaluate("""() => {
                    const visible = el => {
                        const r=el.getBoundingClientRect(), s=getComputedStyle(el);
                        return r.width>100&&r.height>100&&s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity)>0;
                    };
                    const canvases=[...document.querySelectorAll('canvas')].map((c,i)=> {
                        const r=c.getBoundingClientRect();
                        return {index:i,width:c.width,height:c.height,css_width:Math.round(r.width),css_height:Math.round(r.height),visible:visible(c)};
                    });
                    const iframes=[...document.querySelectorAll('iframe')].map((f,i)=> {
                        const r=f.getBoundingClientRect();
                        return {index:i,src:f.src,width:Math.round(r.width),height:Math.round(r.height),visible:visible(f)};
                    });
                    return {canvases,iframes,body_text:document.body.innerText.slice(0,12000),title:document.title};
                }""")
                surface=inspection["visual_surface"]
                visible_surface=any(c["visible"] for c in surface["canvases"]) or any(f["visible"] for f in surface["iframes"])
                title=surface.get("title","")
                # Godot draws its native dock labels inside the WebGL canvas, so
                # DOM text alone cannot prove the editor opened. A scene filename
                # in the document title plus a visible render surface is stronger
                # evidence; it still does not prove that the game runs.
                scene_title=bool(re.search(r"[^/\\]+\.tscn\s+-",title,re.I))
                editor_visible=visible_surface and scene_title
                resource_errors=[e for e in errors if "Cannot open file" in e or "Failed loading resource" in e or "Parse Error" in e]
                inspection["visual_validation"]={
                    "status":"editor_scene_open" if editor_visible else ("surface_detected" if visible_surface else "no_visible_godot_surface"),
                    "editor_surface_visible":visible_surface,
                    "scene_filename_in_title":scene_title,
                    "scene_title":title if scene_title else None,
                    "project_resource_errors_detected":bool(resource_errors),
                    "project_resource_errors":resource_errors[-30:],
                    "manual_review_required":True,
                    "gameplay_verified":False,
                    "note":"A visible Godot scene editor is not proof that the game runs; project resource errors are reported separately."
                }
            page.screenshot(path=str(shot),full_page=False,timeout=30000)
        except Exception as exc:
            failure=f"{type(exc).__name__}: {str(exc)[:1000]}"
            try: page.screenshot(path=str(shot),full_page=False,timeout=15000)
            except Exception: pass
        finally:
            # Do not close Chromium here: keep the editor alive through the evidence round-trip.
            pass
    manifest={"schema_version":1,"worker_backend":"github-actions-hosted-runner","browser_lifetime":"single-workflow-job","session_reconstruction":"fresh-browser-import-at-exact-sha","task_id":task_id,"completed_at":time.time(),"repository":REPOSITORY,"branch":BRANCH,"project_path":PROJECT_PATH,"commit_sha":sha,"editor_url":url,"session_id":session_id,"summary":"Godot Web import and visual inspection on runner-owned Chromium","result":{"ok":failure is None,"failure":failure,"readiness":readiness,"inspection":inspection,"console_errors":errors[-100:],"page_errors":page_errors[-100:],"failed_requests":failed[-100:]},"events":events[-500:],"checkpoint":{"repository":REPOSITORY,"branch":BRANCH,"project_path":PROJECT_PATH,"commit_sha":sha,"editor_url":url,"viewport":{"width":1365,"height":768},"storage_state_saved":False,"reconstruction_mode":"fresh-browser-import"},"artifacts":[name for name in ("editor-install-dialog.png","editor-final.png") if (OUT/name).exists()]}
    (OUT/"task-result.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    bundle=OUT/"godot-browser-worker-task.zip"
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as z:
        z.write(OUT/"task-result.json","task-result.json")
        for artifact_name in manifest["artifacts"]:
            z.write(OUT/artifact_name,"artifacts/"+artifact_name)
    payload=bundle.read_bytes()
    if len(payload)>32*1024*1024: raise ValueError("Evidence bundle exceeds 32 MiB")
    digest=hashlib.sha256(payload).hexdigest()
    upload_url=f"{RELAY_URL}/v1/persistent-sessions/worker-artifacts/{session_id}"
    upload_headers={"Authorization":"Bearer "+oidc_token(),"Content-Type":"application/zip","X-Artifact-SHA256":digest}
    uploaded=json.loads(relay_request(upload_url,method="POST",headers=upload_headers,data=payload,timeout=90,retry_seconds=360))
    (OUT/"worker-upload.json").write_text(json.dumps(uploaded,indent=2),encoding="utf-8")
    download_headers={"Authorization":"Bearer "+oidc_token()}
    recovered=relay_request(RELAY_URL+uploaded["artifact_url"],headers=download_headers,timeout=90,retry_seconds=180)
    if hashlib.sha256(recovered).hexdigest()!=uploaded["artifact_sha256"]: raise RuntimeError("Neon evidence round-trip SHA-256 mismatch")
    with zipfile.ZipFile(io.BytesIO(recovered)) as z:
        if z.testzip(): raise RuntimeError("Persisted evidence ZIP failed integrity check")
    (OUT/"worker-summary.json").write_text(json.dumps({"backend":"GitHub Actions hosted runner","session_id":session_id,"artifact_id":uploaded["artifact_id"],"artifact_sha256":uploaded["artifact_sha256"],"storage":"Neon Object Storage","browser_session_scope":"this workflow job only","reconstruction":"new job reopens exact repository SHA","import_ok":failure is None},indent=2),encoding="utf-8")
    if failure: raise RuntimeError(failure)

if __name__=="__main__": main()
