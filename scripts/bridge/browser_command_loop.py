#!/usr/bin/env python3
"""Bounded, allowlisted command loop for an already-open Godot Web page."""
from __future__ import annotations
import base64, json, math, os, re, time, urllib.request
from pathlib import Path
try:
    from .semantic_controller import execute_semantic_command
    from .artifacts import (
        claim_transport_command, start_transport_command, heartbeat_transport_session,
        complete_transport_command, upload_json_artifact,
    )
except ImportError:  # Support unittest discovery with scripts/bridge as the start directory.
    from semantic_controller import execute_semantic_command
    from artifacts import (
        claim_transport_command, start_transport_command, heartbeat_transport_session,
        complete_transport_command, upload_json_artifact,
    )

API="https://api.github.com"
TRUSTED_ACTORS={"decuvilan-lgtm","github-actions[bot]"}
MAX_TEXT=500
POLL_SECONDS=4.0  # Keep the 60-minute worst-case session below GitHub's 1,000 requests/hour token budget.
SEMANTIC_ACTIONS={"editor.get_state":set(),"editor.list_capabilities":set(),"scene.get_tree":set(),"scene.inspect_node":{"path"},"scene.add_node":{"node_type","node_name","parent_path"},"scene.set_property":{"path","property","value"}}
ALLOWED_KEYS={"F5","F6","F8","w","a","s","d","e","f","W","A","S","D","E","F","Escape","Enter","Tab","Space","Backspace","Delete","ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Shift+Tab","Control+A","Control+Z","Control+Y","Control+S"}

def _api(url, token, method="GET", payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(url,data=data,method=method,headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "Content-Type":"application/json",
        "User-Agent":"Godot-Web-IA-Browser-Bridge",
    })
    with urllib.request.urlopen(req,timeout=25) as response:
        raw=response.read()
        return json.loads(raw) if raw else {}

def _post_result(repo, issue, token, command_id, result):
    body="<!-- godot-browser-result -->\n"+json.dumps({
        "protocol":1,"command_id":command_id,"result":result
    },ensure_ascii=False)
    _api(f"{API}/repos/{repo}/issues/{issue}/comments",token,"POST",{"body":body})

def _valid_unit(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and 0<=value<=1

def _validate(command, session_id, last_seq):
    allowed_fields={"protocol","session_id","seq","action","text","placeholder","seconds","x","y","points","duration_ms","key","delta_x","delta_y","editor_action","args","include_image","scope"}
    if not isinstance(command,dict) or set(command)-allowed_fields:
        raise ValueError("Unsupported command shape")
    if command.get("protocol")!=1 or command.get("session_id")!=session_id:
        raise ValueError("Protocol or session mismatch")
    seq=command.get("seq")
    if not isinstance(seq,int) or isinstance(seq,bool) or seq<=last_seq:
        raise ValueError("Sequence must be a new increasing integer")
    action=command.get("action")
    if action not in {"status","screenshot","click_text","fill_placeholder","wait","assert_text","canvas_click","canvas_drag","canvas_scroll","press_key","type_text","semantic_command","run_game","game_view","game_click","game_input","stop"}:
        raise ValueError("Action is not allowlisted")
    text=command.get("text")
    placeholder=command.get("placeholder")
    if action in {"click_text","assert_text","type_text"} and (not isinstance(text,str) or not text or len(text)>MAX_TEXT):
        raise ValueError("text is required and limited to 500 characters")
    if action=="fill_placeholder" and (not isinstance(placeholder,str) or not placeholder or len(placeholder)>MAX_TEXT or not isinstance(text,str) or len(text)>MAX_TEXT):
        raise ValueError("fill_placeholder needs a bounded placeholder and text")
    seconds=command.get("seconds",1)
    if action=="wait" and (not isinstance(seconds,int) or isinstance(seconds,bool) or not 0<=seconds<=20):
        raise ValueError("wait seconds must be 0-20")
    if action in {"canvas_click","game_click"} and not (_valid_unit(command.get("x")) and _valid_unit(command.get("y"))):
        raise ValueError("canvas_click x and y must be normalized numbers from 0 to 1")
    if action=="screenshot":
        include_image=command.get("include_image",False)
        scope=command.get("scope","page")
        if not isinstance(include_image,bool) or scope not in {"page","canvas"}:
            raise ValueError("screenshot include_image must be boolean and scope must be page or canvas")
    if action=="canvas_scroll":
        if not (_valid_unit(command.get("x")) and _valid_unit(command.get("y"))):
            raise ValueError("canvas_scroll x and y must be normalized numbers from 0 to 1")
        delta_x=command.get("delta_x",0); delta_y=command.get("delta_y",0)
        if any(not isinstance(value,int) or isinstance(value,bool) or not -1200<=value<=1200 for value in (delta_x,delta_y)) or (delta_x==0 and delta_y==0):
            raise ValueError("canvas_scroll deltas must be integers between -1200 and 1200 and not both zero")
    if action=="canvas_drag":
        points=command.get("points")
        if not isinstance(points,list) or not 2<=len(points)<=64:
            raise ValueError("canvas_drag needs 2-64 normalized [x,y] points")
        if any(not isinstance(point,(list,tuple)) or len(point)!=2 or not _valid_unit(point[0]) or not _valid_unit(point[1]) for point in points):
            raise ValueError("every canvas_drag point must contain normalized x and y values from 0 to 1")
        duration=command.get("duration_ms",250)
        if not isinstance(duration,int) or isinstance(duration,bool) or not 50<=duration<=5000:
            raise ValueError("canvas_drag duration_ms must be 50-5000")
    if action=="semantic_command":
        editor_action=command.get("editor_action")
        args=command.get("args",{})
        if editor_action not in SEMANTIC_ACTIONS or not isinstance(args,dict) or set(args)-SEMANTIC_ACTIONS[editor_action]:
            raise ValueError("semantic_command arguments do not match the action allowlist")
        if editor_action=="scene.inspect_node":
            path=args.get("path")
            if set(args)!={"path"} or not isinstance(path,str) or not path or len(path)>200:
                raise ValueError("scene.inspect_node requires one bounded relative path")
            if path.startswith("/") or ".." in path.split("/") or "//" in path:
                raise ValueError("scene.inspect_node path must stay inside the active scene root")
        if editor_action=="scene.set_property":
            if set(args)!={"path","property","value"}:
                raise ValueError("scene.set_property requires path, property, and value")
            path=args["path"]; prop=args["property"]; value=args["value"]
            if not isinstance(path,str) or not path or len(path)>200 or path.startswith("/") or ".." in path.split("/") or "//" in path:
                raise ValueError("scene.set_property path must stay inside the active scene root")
            if not isinstance(prop,str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}",prop):
                raise ValueError("scene.set_property property must be a bounded identifier")
            if prop=="script": raise ValueError("Script assignment is not exposed through the semantic property editor")
            if isinstance(value,bool) or value is None:
                pass
            elif isinstance(value,(int,float)):
                if isinstance(value,float) and not math.isfinite(value):
                    raise ValueError("Property numbers must be finite")
                if abs(value)>1_000_000_000:
                    raise ValueError("Property number exceeds safe range")
            elif isinstance(value,str):
                if len(value)>512: raise ValueError("Property strings are limited to 512 characters")
            elif isinstance(value,list):
                if not 2<=len(value)<=4 or any(not isinstance(v,(int,float)) or isinstance(v,bool) or (isinstance(v,float) and not math.isfinite(v)) or abs(v)>1_000_000_000 for v in value):
                    raise ValueError("Property arrays must contain 2-4 finite numeric components")
            elif isinstance(value,dict):
                resource_path=value.get("resource_path")
                if set(value)!={"resource_path"} or not isinstance(resource_path,str) or not resource_path.startswith("res://") or len(resource_path)>512 or ".." in resource_path.split("/") or "\\" in resource_path:
                    raise ValueError("Object properties accept only bounded res:// resource paths")
            else:
                raise ValueError("Unsupported Inspector property value shape")
        if editor_action=="scene.add_node":
            if not {"node_type","node_name"}.issubset(args):
                raise ValueError("scene.add_node requires node_type and node_name")
            if any(not isinstance(value,str) or not value or len(value)>200 for value in args.values()):
                raise ValueError("scene.add_node arguments must be bounded strings")
            if args["node_type"] not in {"Node","Node2D","Sprite2D","AnimatedSprite2D","Polygon2D","Line2D","CharacterBody2D","RigidBody2D","StaticBody2D","Area2D","CollisionShape2D","CollisionPolygon2D","RayCast2D","VisibleOnScreenNotifier2D","Camera2D","Marker2D","Path2D","PathFollow2D","TileMapLayer","Parallax2D","RemoteTransform2D","CanvasLayer","Control","Label","RichTextLabel","TextureRect","ColorRect","Panel","Button","TextureButton","ProgressBar","VBoxContainer","HBoxContainer","GridContainer","MarginContainer","CenterContainer","SubViewport","SubViewportContainer","AnimationPlayer","AnimationTree","Timer","AudioStreamPlayer","AudioStreamPlayer2D"}:
                raise ValueError("Node type is not allowlisted")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,47}",args["node_name"]):
                raise ValueError("Node name is not a valid identifier")
            if "parent_path" in args and (args["parent_path"].startswith("/") or ".." in args["parent_path"].split("/") or "//" in args["parent_path"]):
                raise ValueError("Parent path must stay inside the edited scene root")
    if action in {"press_key","game_input"} and command.get("key") not in ALLOWED_KEYS:
        raise ValueError("Key is not in the browser editing/game input allowlist")
    if action=="game_input":
        duration=command.get("duration_ms",150)
        if not isinstance(duration,int) or isinstance(duration,bool) or not 50<=duration<=5000:
            raise ValueError("game_input duration_ms must be 50-5000")
    if action=="press_key" and command.get("key") not in ALLOWED_KEYS:
        raise ValueError("Key is not in the browser editing allowlist")
    return seq,action

def _visible_canvases(page):
    result=[]
    canvases=page.locator("canvas")
    for index in range(min(canvases.count(),8)):
        box=canvases.nth(index).bounding_box()
        if box and box["width"]>=100 and box["height"]>=100:
            result.append({"index":index,"x":round(box["x"],1),"y":round(box["y"],1),"width":round(box["width"],1),"height":round(box["height"],1)})
    return result

def _largest_visible_canvas(page):
    candidates=_visible_canvases(page)
    if not candidates:
        raise ValueError("No visible editor canvas was found")
    return max(candidates,key=lambda item:item["width"]*item["height"])

def _visible_canvases_across_frames(page):
    result=[]
    for frame_index, frame in enumerate(page.frames):
        canvases=frame.locator("canvas")
        for index in range(min(canvases.count(),8)):
            box=canvases.nth(index).bounding_box()
            if box and box["width"]>=100 and box["height"]>=100:
                result.append({"frame_index":frame_index,"index":index,"x":round(box["x"],1),"y":round(box["y"],1),"width":round(box["width"],1),"height":round(box["height"],1)})
    return result


def _largest_game_canvas(page):
    candidates=_visible_canvases_across_frames(page)
    if not candidates:
        raise ValueError("No visible game-preview canvas was found after opening the Game view")
    return max(candidates,key=lambda item:item["width"]*item["height"])


def _canvas_coordinates(canvas,x,y):
    return canvas["x"]+x*canvas["width"],canvas["y"]+y*canvas["height"]

def _bounded_duration_seconds(value):
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("duration_seconds must be an integer")
    return max(0, min(value, 3600))


def _ordered_comments(items):
    return sorted(items, key=lambda item: int(item.get("id", 0)))


def _fetch_new_comments(comments_url, token, last_comment_id):
    page = 1
    fresh = []
    while True:
        batch = _api(f"{comments_url}&page={page}", token)
        if not isinstance(batch, list) or not batch:
            break
        fresh.extend(item for item in batch if int(item.get("id", 0)) > last_comment_id)
        if any(int(item.get("id", 0)) <= last_comment_id for item in batch) or len(batch) < 100:
            break
        page += 1
    return _ordered_comments(fresh)


def run_command_loop(page, repo, issue_number, token, session_id, out_dir, duration_seconds=180):
    neon_api = os.environ.get("AB_API_URL", "").strip()
    neon_token = os.environ.get("AB_DEVICE_TOKEN", "").strip()
    neon_mode = bool(neon_api and neon_token)
    if neon_mode:
        try:
            import uuid
            uuid.UUID(session_id)
        except (ValueError, TypeError, AttributeError):
            return {"enabled":False,"reason":"Neon transport requires a database session UUID"}
    elif not token or not issue_number:
        return {"enabled":False,"reason":"Missing issue-scoped GitHub token or issue number"}
    duration_seconds = _bounded_duration_seconds(duration_seconds)
    started_at = time.monotonic()
    deadline = started_at + duration_seconds
    issue=int(issue_number) if issue_number else None
    last_comment_id=0
    last_seq=0
    processed=0
    stopped=False
    last_transport_heartbeat=0.0
    log=[]
    comments_url=(f"{API}/repos/{repo}/issues/{issue}/comments?per_page=100&sort=created&direction=desc" if issue else None)
    while time.monotonic()<deadline and not stopped:
        try:
            if neon_mode:
                now=time.monotonic()
                if now-last_transport_heartbeat>=20.0:
                    heartbeat_transport_session(neon_api, neon_token, session_id)
                    last_transport_heartbeat=now
                claimed = claim_transport_command(neon_api, neon_token, session_id, wait_ms=10_000)
                comments = []
                if claimed:
                    command_id = claimed["id"]
                    start_transport_command(neon_api, neon_token, command_id)
                    command_payload = {
                        **(claimed.get("args") or {}),
                        "protocol": 1, "session_id": session_id,
                        "seq": last_seq + 1, "action": claimed["action"],
                    }
                    comments = [{
                        "id": last_seq + 1,
                        "user": {"login": "github-actions[bot]"},
                        "body": json.dumps(command_payload, ensure_ascii=False),
                        "command_id": command_id,
                    }]
            else:
                comments=_fetch_new_comments(comments_url,token,last_comment_id)
            for item in comments:
                comment_id=int(item.get("id",0))
                if comment_id<=last_comment_id:
                    continue
                last_comment_id=max(last_comment_id,comment_id)
                if item.get("user",{}).get("login") not in TRUSTED_ACTORS:
                    continue
                body=(item.get("body") or "").strip()
                if not body.startswith("{") or not body.endswith("}"):
                    continue
                command_started=time.monotonic()
                try:
                    command=json.loads(body)
                    seq,action=_validate(command,session_id,last_seq)
                    last_seq=seq
                    if action=="status":
                        result={"title":page.title(),"url":page.url,"visible_text":page.locator("body").inner_text(timeout=5000)[:3000],"viewport_size":page.viewport_size,"visible_canvases":_visible_canvases(page)}
                    elif action=="screenshot":
                        path=Path(out_dir)/f"command-{seq:03d}.png"
                        page.screenshot(path=str(path),full_page=False,timeout=15000)
                        result={"screenshot":path.name,"title":page.title()}
                        if command.get("include_image",False):
                            scope=command.get("scope","page")
                            if scope=="canvas":
                                canvas=_largest_game_canvas(page)
                                clip={"x":max(0,canvas["x"]),"y":max(0,canvas["y"]),"width":canvas["width"],"height":canvas["height"]}
                                image_bytes=page.screenshot(type="jpeg",quality=24,clip=clip,timeout=15000)
                                if len(image_bytes)>42000:
                                    image_bytes=page.screenshot(type="jpeg",quality=10,clip=clip,timeout=15000)
                            else:
                                image_bytes=page.screenshot(type="jpeg",quality=12,full_page=False,timeout=15000)
                                if len(image_bytes)>42000:
                                    image_bytes=page.screenshot(type="jpeg",quality=5,full_page=False,timeout=15000)
                            if len(image_bytes)<=42000:
                                result["image_mime_type"]="image/jpeg"
                                result["image_base64"]=base64.b64encode(image_bytes).decode("ascii")
                                result["image_scope"]=scope
                            else:
                                result["inline_image_omitted"]="Compressed image exceeded the safe issue-comment size; full PNG remains in Workflow A evidence."
                    elif action=="click_text":
                        locator=page.get_by_text(command["text"],exact=True)
                        if locator.count()<1: raise ValueError("Exact visible text was not found")
                        locator.first.click(timeout=10000)
                        page.wait_for_timeout(500)
                        result={"clicked":command["text"],"title":page.title()}
                    elif action=="fill_placeholder":
                        locator=page.get_by_placeholder(command["placeholder"],exact=True)
                        if locator.count()<1: raise ValueError("Exact placeholder was not found")
                        locator.first.fill(command["text"],timeout=10000)
                        result={"filled":command["placeholder"]}
                    elif action=="canvas_click":
                        canvas=_largest_visible_canvas(page)
                        point=_canvas_coordinates(canvas,command["x"],command["y"])
                        page.mouse.click(*point)
                        result={"canvas_index":canvas["index"],"normalized_point":{"x":command["x"],"y":command["y"]}}
                    elif action=="run_game":
                        editor_tab=page.get_by_text("Editor",exact=True)
                        if editor_tab.count():
                            editor_tab.first.click(timeout=10000)
                            page.wait_for_timeout(500)
                        editor_canvas=page.locator("#editor-canvas")
                        if editor_canvas.count() and editor_canvas.first.is_visible():
                            editor_canvas.first.focus()
                        else:
                            canvas=_largest_visible_canvas(page)
                            point=_canvas_coordinates(canvas,0.5,0.5)
                            page.mouse.click(*point)
                        page.keyboard.press("F6")
                        page.wait_for_timeout(2000)
                        result={"run_command":"F6","title":page.title(),"url":page.url}
                    elif action=="game_view":
                        game_tab=page.get_by_text("Game",exact=True)
                        if game_tab.count()<1:
                            raise ValueError("The Godot Web Game tab is not visible")
                        game_tab.first.click(timeout=10000)
                        page.wait_for_timeout(1200)
                        canvases=_visible_canvases_across_frames(page)
                        result={"game_tab_opened":True,"preview_detected":bool(canvases),"visible_game_canvases":canvases,"title":page.title()}
                    elif action=="game_click":
                        canvas=_largest_game_canvas(page)
                        point=_canvas_coordinates(canvas,command["x"],command["y"])
                        page.mouse.click(*point)
                        result={"frame_index":canvas["frame_index"],"canvas_index":canvas["index"],"normalized_point":{"x":command["x"],"y":command["y"]}}
                    elif action=="game_input":
                        canvas=_largest_game_canvas(page)
                        point=_canvas_coordinates(canvas,0.5,0.5)
                        page.mouse.click(*point)
                        key=command["key"]
                        page.keyboard.down(key)
                        try:
                            time.sleep(command.get("duration_ms",150)/1000.0)
                        finally:
                            page.keyboard.up(key)
                        result={"frame_index":canvas["frame_index"],"canvas_index":canvas["index"],"key":key,"duration_ms":command.get("duration_ms",150),"released":True}
                    elif action=="canvas_drag":
                        canvas=_largest_visible_canvas(page)
                        points=[_canvas_coordinates(canvas,x,y) for x,y in command["points"]]
                        page.mouse.move(*points[0])
                        page.mouse.down()
                        try:
                            delay=max(0,command.get("duration_ms",250)//(len(points)-1))
                            for point in points[1:]:
                                page.mouse.move(*point,steps=4)
                                if delay: page.wait_for_timeout(delay)
                        finally:
                            page.mouse.up()
                        result={"canvas_index":canvas["index"],"point_count":len(points),"duration_ms":command.get("duration_ms",250)}
                    elif action=="canvas_scroll":
                        canvas=_largest_visible_canvas(page)
                        point=_canvas_coordinates(canvas,command["x"],command["y"])
                        page.mouse.move(*point)
                        page.mouse.wheel(command.get("delta_x",0),command.get("delta_y",0))
                        result={"canvas_index":canvas["index"],"delta_x":command.get("delta_x",0),"delta_y":command.get("delta_y",0)}
                    elif action=="press_key":
                        page.keyboard.press(command["key"])
                        result={"pressed":command["key"]}
                    elif action=="type_text":
                        page.keyboard.type(command["text"],delay=5)
                        result={"typed_characters":len(command["text"])}
                    elif action=="wait":
                        page.wait_for_timeout(command.get("seconds",1)*1000)
                        result={"waited_seconds":command.get("seconds",1)}
                    elif action=="assert_text":
                        found=page.get_by_text(command["text"],exact=True).count()>0
                        result={"text":command["text"],"found":found}
                        if not found: raise ValueError("Expected text was not found")
                    elif action=="semantic_command":
                        editor_action=command["editor_action"]
                        semantic_result=execute_semantic_command(page,editor_action,command.get("args",{}),timeout_ms=12000)
                        result={"editor_action":editor_action,**semantic_result}
                    else:
                        stopped=True
                        result={"stopped":True}
                    result["bridge_timing"]={"a_processing_ms":round((time.monotonic()-command_started)*1000,2)}
                    processed+=1
                    command_ok=not (action=="semantic_command" and result.get("ok") is False)
                    log.append({"comment_id":comment_id,"seq":seq,"action":action,"ok":command_ok,"result":result})
                    if neon_mode:
                        result_payload = {"ok": command_ok, **result}
                        if len(json.dumps(result_payload, ensure_ascii=False).encode("utf-8")) > 24000:
                            artifact = upload_json_artifact(
                                neon_api, neon_token, result_payload,
                                session_id=session_id, kind="command_result",
                            )
                            result_payload = {"artifact_id": artifact["artifact_id"], "manifest": artifact["manifest"]}
                        complete_transport_command(
                            neon_api, neon_token, item["command_id"], ok=command_ok,
                            result=result_payload,
                            duration_ms=int((time.monotonic()-command_started)*1000),
                        )
                    else:
                        _post_result(repo,issue,token,comment_id,{"ok":command_ok,**result})
                except Exception as exc:
                    error={"ok":False,"error":f"{type(exc).__name__}: {str(exc)[:400]}","bridge_timing":{"a_processing_ms":round((time.monotonic()-command_started)*1000,2)}}
                    log.append({"comment_id":comment_id,"ok":False,"error":error["error"]})
                    try:
                        if neon_mode:
                            complete_transport_command(
                                neon_api, neon_token, item["command_id"], ok=False,
                                result={"error": error["error"]},
                                duration_ms=int((time.monotonic()-command_started)*1000),
                                error_code=type(exc).__name__,
                                error_message=str(exc)[:400],
                            )
                        else:
                            _post_result(repo,issue,token,comment_id,error)
                    except Exception:
                        pass
        except Exception as exc:
            log.append({"poll_error":f"{type(exc).__name__}: {str(exc)[:300]}"})
        remaining = max(0, deadline - time.monotonic())
        if remaining and not neon_mode:
            # Neon mode already waited inside the bounded long-poll claim request.
            # Preserve the slower cadence only for the legacy GitHub fallback.
            time.sleep(min(POLL_SECONDS, remaining))
    Path(out_dir,"browser-command-log.json").write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding="utf-8")
    return {"enabled":True,"processed_commands":processed,"last_sequence":last_seq,"stopped_by_command":stopped,"duration_seconds":int(max(0,time.monotonic()-started_at)),"log_file":"browser-command-log.json"}
