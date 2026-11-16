#!/usr/bin/env python3
"""Read-only integration probe for the native Headless Session Bridge."""
import json, os, shutil, socket, time
from pathlib import Path
roots=[Path.home()/".local/share/godot/app_userdata",Path.home()/".config/godot/app_userdata"]
registry=None
deadline=time.time()+35
while time.time()<deadline and registry is None:
    for root in roots:
        if root.exists():
            matches=list(root.glob("*/headless_bridge.json"))
            if matches:
                registry=max(matches,key=lambda p:p.stat().st_mtime); break
    if registry is None: time.sleep(.5)
if registry is None: raise SystemExit("bridge discovery registry was not created")
cfg=json.loads(registry.read_text())
def request(command,args=None):
    payload={"protocol":cfg["protocol"],"token":cfg["token"],"project_id":cfg["project_id"],"command":command}
    if args is not None: payload["args"]=args
    with socket.create_connection(("127.0.0.1",int(cfg["port"])),timeout=8) as peer:
        peer.sendall((json.dumps(payload)+"\n").encode()); peer.settimeout(8); data=b""
        while b"\n" not in data:
            part=peer.recv(65536)
            if not part: break
            data+=part
    if b"\n" not in data: raise RuntimeError("empty response: "+command)
    result=json.loads(data.split(b"\n",1)[0])
    if not result.get("ok",False): raise RuntimeError(f"{command}: {result}")
    return result
caps=request("editor.list_capabilities")
state=request("editor.get_state")
scene=request("scene.get_tree")
resources=request("project.list_resources")
assert caps["result"]["adapter"]=="godot_native_editor"
assert "capture.editor_screenshot" in caps["result"]["commands"]
assert state["result"]["active_scene"]=="res://scenes/main.tscn",state
assert scene["result"]["root"]["name"]=="VerdantValley",scene
assert any(p.endswith("player.gd") for p in resources["result"]["entries"])
focus=request("editor.focus_inspector",{"node_path":".","main_screen":"2D"})
shot=request("capture.editor_screenshot")
source=Path(shot["result"]["capture_path"])
out=Path(os.environ.get("BRIDGE_EVIDENCE_DIR","artifacts")); out.mkdir(parents=True,exist_ok=True)
shutil.copy2(source,out/"editor-bridge.png")
report={"editor_pid":cfg["editor_pid"],"project_id":cfg["project_id"],"adapter":caps["result"]["adapter"],"active_scene":state["result"]["active_scene"],"scene_root":scene["result"]["root"]["name"],"resource_count":len(resources["result"]["entries"]),"focus_2d":focus["result"],"screenshot":shot["result"],"commands_verified":["editor.list_capabilities","editor.get_state","scene.get_tree","project.list_resources","editor.focus_inspector","capture.editor_screenshot"]}
(out/"bridge-report.json").write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
