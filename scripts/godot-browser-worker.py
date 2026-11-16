#!/usr/bin/env python3
"""Real Godot Web browser worker running only inside a GitHub Actions job."""
from __future__ import annotations
import base64, hashlib, io, json, os, re, shutil, tempfile, threading, time, urllib.parse, urllib.request, zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright
from bridge.browser_command_loop import run_command_loop
from bridge.semantic_controller import execute_semantic_command

RELAY_URL=os.environ.get("RELAY_URL","https://godot-web-ia-relay.onrender.com").rstrip("/")
EDITOR_URL=os.environ.get("EDITOR_URL","https://godot-web-ia-integrada-rt2l.onrender.com/")
REPOSITORY=os.environ["REPOSITORY"]; BRANCH=os.environ.get("BRANCH","main")
PROJECT_PATH=os.environ.get("PROJECT_PATH",""); REQUESTED_SHA=os.environ.get("COMMIT_SHA","").lower()
WAIT_SECONDS=int(os.environ.get("WAIT_SECONDS","10")); IMPORT_TIMEOUT=int(os.environ.get("IMPORT_TIMEOUT_SECONDS","480"))
RUN_ID=os.environ.get("GITHUB_RUN_ID",str(int(time.time()))); ATTEMPT=os.environ.get("GITHUB_RUN_ATTEMPT","1")
OUT=Path("artifacts"); OUT.mkdir(exist_ok=True)


class IsolatedEditorHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def do_GET(self):
        parsed=urllib.parse.urlsplit(self.path)
        parts=parsed.path.split("/")
        if parsed.path.startswith("/v1/github/"):
            if len(parts)!=6 or parts[1:3]!=["v1","github"] or parts[5]!="archive":
                self.send_error(404)
                return
            target=RELAY_URL+self.path
            request=urllib.request.Request(target,headers={
                "Accept":"application/zip, application/json",
                "User-Agent":"Godot-Web-Local-Archive-Proxy",
                "Cache-Control":"no-store",
            })
            try:
                with urllib.request.urlopen(request,timeout=90) as response:
                    body=response.read(128*1024*1024+1)
                    if len(body)>128*1024*1024:
                        self.send_error(413,"GitHub project archive exceeds 128 MiB")
                        return
                    self.send_response(response.status)
                    for header in ("Content-Type","X-GitHub-Ref","X-GitHub-Commit-SHA","Cache-Control"):
                        if response.headers.get(header):
                            self.send_header(header,response.headers[header])
                    self.send_header("Content-Length",str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
            except urllib.error.HTTPError as exc:
                detail=exc.read(4096)
                self.send_response(exc.code)
                self.send_header("Content-Type","application/json")
                self.send_header("Content-Length",str(len(detail)))
                self.end_headers()
                self.wfile.write(detail)
            except Exception as exc:
                self.send_error(502,str(exc)[:200])
            return
        super().do_GET()


def start_local_editor(directory):
    editor_dir=Path(directory).resolve()
    required=("index.html","godot.editor.js","godot.editor.wasm","service.worker.js")
    missing=[name for name in required if not (editor_dir/name).is_file()]
    if missing:
        raise RuntimeError("Local custom Godot editor is incomplete: "+", ".join(missing))
    handler=lambda *args,**kwargs:IsolatedEditorHandler(*args,directory=str(editor_dir),**kwargs)
    server=ThreadingHTTPServer(("127.0.0.1",0),handler)
    server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    return server,thread,f"http://127.0.0.1:{server.server_port}/"


def prepare_extension(source_dir, target_dir, origin):
    target_dir.mkdir(parents=True,exist_ok=True)
    for name in ("page-bridge.js","content.js"):
        shutil.copy2(source_dir/name,target_dir/name)
    manifest=json.loads((source_dir/"manifest.json").read_text(encoding="utf-8"))
    match=origin+"/*"
    manifest["host_permissions"]=[match]
    for item in manifest.get("content_scripts",[]):
        item["matches"]=[match]
    (target_dir/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")

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

def post_host_ready_comment(repo, issue_number, token, session_id, sha, inspection):
    """Publish a readiness marker so Workflow B never races the import."""
    if not issue_number or not token:
        return
    body="<!-- godot-browser-host-ready -->\\n"+json.dumps({
        "session_id":session_id,
        "commit_sha":sha,
        "visual_status":inspection.get("visual_validation",{}).get("status"),
        "scene_title":inspection.get("visual_validation",{}).get("scene_title"),
        "visible_canvases":inspection.get("visual_surface",{}).get("canvases",[]),
    },ensure_ascii=False)
    payload=json.dumps({"body":body}).encode()
    req=urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues/{int(issue_number)}/comments",
        data=payload,method="POST",headers={
            "Authorization":"Bearer "+token,
            "Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
            "Content-Type":"application/json",
            "User-Agent":"Godot-Web-IA-Browser-Host",
        })
    with urllib.request.urlopen(req,timeout=30) as response:
        response.read()


def oidc_token():
    url=os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]+"&audience=godot-web-ia-relay"
    req=urllib.request.Request(url,headers={"Authorization":"Bearer "+os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with urllib.request.urlopen(req,timeout=30) as res: return json.loads(res.read())["value"]

def oidc_claim_summary(token):
    """Return only non-secret identity claims for safe diagnostics."""
    try:
        payload=token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims=json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        return {key:claims.get(key) for key in ("repository","ref","workflow_ref","aud","iss","sub")}
    except Exception:
        return {"claims":"unavailable"}

def relay_oidc_preflight():
    # Wake a suspended Free relay before minting the short-lived OIDC token.
    relay_request(RELAY_URL+"/health",timeout=30,retry_seconds=360)
    token=oidc_token()
    claims=oidc_claim_summary(token)
    try:
        raw=relay_request(
            RELAY_URL+"/v1/persistent-sessions",
            headers={"Authorization":"Bearer "+token},
            timeout=30,
            retry_seconds=15,
        )
        sessions=json.loads(raw).get("sessions",[])
        return {"ok":True,"active_sessions":len(sessions),"claims":claims}
    except urllib.error.HTTPError as exc:
        detail=exc.read().decode("utf-8","replace")[:400]
        raise RuntimeError(
            f"Relay OIDC preflight rejected identity: HTTP {exc.code}: {detail}; claims={json.dumps(claims,ensure_ascii=False)}"
        ) from exc

def resolve_sha():
    if REQUESTED_SHA: sha=REQUESTED_SHA
    else:
        branch=urllib.parse.quote(BRANCH,safe="")
        req=urllib.request.Request(f"https://api.github.com/repos/{REPOSITORY}/branches/{branch}",headers={"Accept":"application/vnd.github+json","Authorization":"Bearer "+os.environ.get("GITHUB_TOKEN",""),"X-GitHub-Api-Version":"2022-11-28"})
        with urllib.request.urlopen(req,timeout=30) as res: sha=json.loads(res.read())["commit"]["sha"].lower()
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})",sha): raise ValueError("Expected a full Git commit SHA")
    return sha

def main():
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}",REPOSITORY): raise ValueError("Invalid repository")
    if not 60<=IMPORT_TIMEOUT<=600: raise ValueError("IMPORT_TIMEOUT_SECONDS must be 60-600")
    sha=resolve_sha(); session_id=os.environ.get("BROWSER_SESSION_ID", f"gha-{RUN_ID}-{ATTEMPT}"); task_id=f"github-actions-{RUN_ID}-{ATTEMPT}"
    bridge_repository=os.environ.get("BRIDGE_REPOSITORY") or os.environ.get("GITHUB_REPOSITORY") or "decuvilan-lgtm/Godot-web-ia-integrada"
    oidc_preflight=relay_oidc_preflight()
    editor_server=None
    local_editor_dir=os.environ.get("LOCAL_EDITOR_DIR","").strip()
    if local_editor_dir:
        editor_server,editor_server_thread,editor_base_url=start_local_editor(local_editor_dir)
    else:
        editor_base_url=EDITOR_URL
    url=editor_base_url.rstrip("/")+"/?"+urllib.parse.urlencode({"repo":REPOSITORY,"branch":BRANCH,"path":PROJECT_PATH,"sha":sha})
    errors=[]; page_errors=[]; failed=[]; events=[]; inspection={}; readiness={"phase":"not_started","canvas_count":0}; failure=None; browser_ready=False
    shot=OUT/"editor-final.png"; started=time.time()
    # Keep the browser process alive through evidence upload; the runner owns its lifetime.
    p = sync_playwright().start()
    if True:
        extension_source=Path(__file__).resolve().parent.parent/"browser-extension"
        if not (extension_source/"manifest.json").is_file():
            raise FileNotFoundError("Godot Controller extension manifest is missing")
        extension_dir=Path(tempfile.mkdtemp(prefix="godot-actions-extension-"))
        parsed_editor_url=urllib.parse.urlparse(editor_base_url)
        editor_origin=f"{parsed_editor_url.scheme}://{parsed_editor_url.netloc}"
        prepare_extension(extension_source,extension_dir,editor_origin)
        profile_dir=tempfile.mkdtemp(prefix="godot-actions-chromium-")
        context=p.chromium.launch_persistent_context(
            profile_dir,
            channel="chromium",
            headless=True,
            args=[
                "--no-sandbox","--disable-dev-shm-usage","--disable-gpu",
                "--disable-extensions-except="+str(extension_dir),
                "--load-extension="+str(extension_dir),
                "--disable-background-networking","--disable-default-apps","--disable-sync",
                "--disable-features=Translate,BackForwardCache,AcceptCHFrame,MediaRouter",
            ],
            viewport={"width":1365,"height":768},
            device_scale_factor=1,
            accept_downloads=True,
        )
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
                browser_ready=True
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
                        inspection["project_manager_warning"]="Godot remained in Project Manager after the Install action; B can still inspect and interact with this page"
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
                post_host_ready_comment(bridge_repository, os.environ.get("SESSION_ISSUE_NUMBER"), os.environ.get("GITHUB_TOKEN", ""), session_id, sha, inspection)
            try:
                semantic_probe=execute_semantic_command(page,"editor.list_capabilities",timeout_ms=12000)
                inspection["semantic_controller_probe"]={
                    "status":"adapter_response" if semantic_probe.get("ok") else semantic_probe.get("error","unknown"),
                    "result":semantic_probe,
                }
            except Exception as exc:
                inspection["semantic_controller_probe"]={
                    "status":"probe_exception",
                    "error":f"{type(exc).__name__}: {str(exc)[:300]}",
                }
            inspection["controller_runtime"]=page.evaluate("""() => ({
                adapter_present: !!(window.__godotEditorAgent && typeof window.__godotEditorAgent.dispatch === "function"),
                adapter_protocol: window.__godotEditorAgent ? window.__godotEditorAgent.protocol ?? null : null,
                adapter_version: window.__godotEditorAgent ? window.__godotEditorAgent.version ?? null : null,
                capabilities_present: !!(window.__godotEditorAgent && typeof window.__godotEditorAgent.getCapabilities === "function"),
                pending_requests: window.__godotEditorAgentPending ? window.__godotEditorAgentPending.size : null
            })""")
            probe_result=inspection.get("semantic_controller_probe",{}).get("result",{})
            if not probe_result.get("ok"):
                inspection["semantic_controller_probe"]["warning"]="Built-in Godot editor semantic adapter did not pass its capability probe; basic browser inspection remains available"
            page.screenshot(path=str(shot),full_page=False,timeout=30000)
            # Keep this real Chromium session available for a short, bounded command window.
            if browser_ready and not page.is_closed():
                command_session=run_command_loop(
                    page, bridge_repository, os.environ.get("SESSION_ISSUE_NUMBER"),
                    os.environ.get("GITHUB_TOKEN", ""), session_id, OUT,
                    duration_seconds=int(os.environ.get("BROWSER_COMMAND_WINDOW_SECONDS", "180")),
                )
            else:
                command_session={"status":"skipped","reason":"The exact project revision and editor canvas were not confirmed"}
            inspection["command_session"]=command_session
        except Exception as exc:
            failure=f"{type(exc).__name__}: {str(exc)[:1000]}"
            try: page.screenshot(path=str(shot),full_page=False,timeout=15000)
            except Exception: pass
        finally:
            # Do not close Chromium here: keep the editor alive through the evidence round-trip.
            pass
    manifest={"schema_version":1,"worker_backend":"github-actions-hosted-runner","browser_lifetime":"single-workflow-job","session_reconstruction":"fresh-browser-import-at-exact-sha","task_id":task_id,"completed_at":time.time(),"repository":REPOSITORY,"bridge_repository":bridge_repository,"oidc_preflight":oidc_preflight,"branch":BRANCH,"project_path":PROJECT_PATH,"commit_sha":sha,"editor_url":url,"session_id":session_id,"summary":"Godot Web import and visual inspection on runner-owned Chromium","result":{"ok":failure is None,"failure":failure,"readiness":readiness,"inspection":inspection,"console_errors":errors[-100:],"page_errors":page_errors[-100:],"failed_requests":failed[-100:]},"events":events[-500:],"checkpoint":{"repository":REPOSITORY,"branch":BRANCH,"project_path":PROJECT_PATH,"commit_sha":sha,"editor_url":url,"viewport":{"width":1365,"height":768},"storage_state_saved":False,"reconstruction_mode":"fresh-browser-import"},"artifacts":[name for name in ("editor-install-dialog.png","editor-final.png","browser-command-log.json") if (OUT/name).exists()]+sorted(p.name for p in OUT.glob("command-*.png") if p.is_file())}
    (OUT/"task-result.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    bundle=OUT/"godot-browser-worker-task.zip"
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as z:
        z.write(OUT/"task-result.json","task-result.json")
        for artifact_name in manifest["artifacts"]:
            z.write(OUT/artifact_name,"artifacts/"+artifact_name)
    payload=bundle.read_bytes()
    if len(payload)>32*1024*1024: raise ValueError("Evidence bundle exceeds 32 MiB")
    if os.environ.get("SKIP_RELAY_ARTIFACT_UPLOAD","").lower() in {"1","true","yes"}:
        (OUT/"worker-summary.json").write_text(json.dumps({
            "backend":"GitHub Actions hosted runner",
            "session_id":session_id,
            "browser_session_scope":"this workflow job only",
            "artifact_storage":"GitHub Actions workflow artifact",
            "import_ok":failure is None,
            "failure":failure,
        },indent=2),encoding="utf-8")
        if failure:
            raise RuntimeError(failure)
        return
    digest=hashlib.sha256(payload).hexdigest()
    upload_url=f"{RELAY_URL}/v1/persistent-sessions/worker-artifacts/{session_id}"
    upload_headers={"Authorization":"Bearer "+oidc_token(),"Content-Type":"application/zip","X-Artifact-SHA256":digest}
    try:
        uploaded=json.loads(relay_request(upload_url,method="POST",headers=upload_headers,data=payload,timeout=90,retry_seconds=360))
    except urllib.error.HTTPError as exc:
        detail=exc.read().decode("utf-8","replace")[:500]
        (OUT/"relay-upload-error.json").write_text(json.dumps({"stage":"artifact_upload","http_status":exc.code,"detail":detail,"oidc_claims":oidc_claim_summary(upload_headers["Authorization"].removeprefix("Bearer "))},indent=2),encoding="utf-8")
        raise RuntimeError(f"Relay artifact upload rejected: HTTP {exc.code}: {detail}") from exc
    (OUT/"worker-upload.json").write_text(json.dumps(uploaded,indent=2),encoding="utf-8")
    download_headers={"Authorization":"Bearer "+oidc_token()}
    recovered=relay_request(RELAY_URL+uploaded["artifact_url"],headers=download_headers,timeout=90,retry_seconds=180)
    if hashlib.sha256(recovered).hexdigest()!=uploaded["artifact_sha256"]: raise RuntimeError("Neon evidence round-trip SHA-256 mismatch")
    with zipfile.ZipFile(io.BytesIO(recovered)) as z:
        if z.testzip(): raise RuntimeError("Persisted evidence ZIP failed integrity check")
    (OUT/"worker-summary.json").write_text(json.dumps({"backend":"GitHub Actions hosted runner","session_id":session_id,"artifact_id":uploaded["artifact_id"],"artifact_sha256":uploaded["artifact_sha256"],"storage":"Neon Object Storage","browser_session_scope":"this workflow job only","reconstruction":"new job reopens exact repository SHA","import_ok":failure is None},indent=2),encoding="utf-8")
    if failure: raise RuntimeError(failure)

if __name__=="__main__": main()
