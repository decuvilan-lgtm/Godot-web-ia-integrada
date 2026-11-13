#!/usr/bin/env python3
"""Bounded, allowlisted command loop for an already-open Godot Web page."""
from __future__ import annotations
import json, os, re, time, urllib.request
from pathlib import Path

API="https://api.github.com"
TRUSTED_ACTORS={"decuvilan-lgtm"}
MAX_TEXT=500
POLL_SECONDS=5
ALLOWED_KEYS={"Escape","Enter","Tab","Space","Backspace","Delete","ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Shift+Tab","Control+A","Control+Z","Control+Y","Control+S"}

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
    allowed_fields={"protocol","session_id","seq","action","text","placeholder","seconds","x","y","points","duration_ms","key","delta_x","delta_y"}
    if not isinstance(command,dict) or set(command)-allowed_fields:
        raise ValueError("Unsupported command shape")
    if command.get("protocol")!=1 or command.get("session_id")!=session_id:
        raise ValueError("Protocol or session mismatch")
    seq=command.get("seq")
    if not isinstance(seq,int) or isinstance(seq,bool) or seq<=last_seq:
        raise ValueError("Sequence must be a new increasing integer")
    action=command.get("action")
    if action not in {"status","screenshot","click_text","fill_placeholder","wait","assert_text","canvas_click","canvas_drag","canvas_scroll","press_key","type_text","stop"}:
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
    if action=="canvas_click" and not (_valid_unit(command.get("x")) and _valid_unit(command.get("y"))):
        raise ValueError("canvas_click x and y must be normalized numbers from 0 to 1")
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

def _canvas_coordinates(canvas,x,y):
    return canvas["x"]+x*canvas["width"],canvas["y"]+y*canvas["height"]

def run_command_loop(page, repo, issue_number, token, session_id, out_dir, duration_seconds=180):
    if not token or not issue_number:
        return {"enabled":False,"reason":"Missing issue-scoped GitHub token or issue number"}
    issue=int(issue_number)
    deadline=time.monotonic()+max(600,min(int(duration_seconds),600))
    last_comment_id=0
    last_seq=0
    processed=0
    stopped=False
    log=[]
    comments_url=f"{API}/repos/{repo}/issues/{issue}/comments?per_page=100&sort=created&direction=asc"
    while time.monotonic()<deadline and not stopped:
        try:
            comments=_api(comments_url,token)
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
                    else:
                        stopped=True
                        result={"stopped":True}
                    processed+=1
                    log.append({"comment_id":comment_id,"seq":seq,"action":action,"ok":True,"result":result})
                    _post_result(repo,issue,token,comment_id,{"ok":True,**result})
                except Exception as exc:
                    error={"ok":False,"error":f"{type(exc).__name__}: {str(exc)[:400]}"}
                    log.append({"comment_id":comment_id,"ok":False,"error":error["error"]})
                    try: _post_result(repo,issue,token,comment_id,error)
                    except Exception: pass
        except Exception as exc:
            log.append({"poll_error":f"{type(exc).__name__}: {str(exc)[:300]}"})
        time.sleep(POLL_SECONDS)
    Path(out_dir,"browser-command-log.json").write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding="utf-8")
    return {"enabled":True,"processed_commands":processed,"last_sequence":last_seq,"stopped_by_command":stopped,"duration_seconds":int(max(0,duration_seconds-(deadline-time.monotonic()))),"log_file":"browser-command-log.json"}
