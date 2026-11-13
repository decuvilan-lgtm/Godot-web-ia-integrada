#!/usr/bin/env python3
"""Validate a narrowly-scoped browser inspection request from a GitHub issue."""
from __future__ import annotations
import json, re, sys
from pathlib import Path

TITLE_PREFIX = "[CHATGPT-BROWSER]"
TASK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
REPO_PROJECT_ALLOWLIST = {
    "gavilandavid89-pixel/Ajedrez-2c2": {"ajedrez_2c2_v161"},
    "decuvilan-lgtm/Godot-web-ia-integrada": {"examples/bridge-sandbox"},
}
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,120}$")
SHA_RE = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
PATH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,180}$")
ALLOWED_KEYS = {"protocol","task_id","action","repository","branch","commit_sha","project_path","wait_seconds","import_timeout_seconds"}

def prepare(event_path: Path, output_path: Path, result_path: Path) -> dict:
    event=json.loads(event_path.read_text(encoding="utf-8"))
    issue=event.get("issue") or {}
    if not str(issue.get("title") or "").startswith(TITLE_PREFIX):
        raise ValueError("Issue title is not a browser task.")
    body=issue.get("body")
    if not isinstance(body,str) or len(body.encode("utf-8"))>4096:
        raise ValueError("Task body is missing or exceeds 4096 bytes.")
    task=json.loads(body)
    if not isinstance(task,dict) or set(task)-ALLOWED_KEYS:
        raise ValueError("Task contains unsupported fields.")
    if task.get("protocol") != 1 or task.get("action") != "inspect_editor":
        raise ValueError("Unsupported browser task protocol or action.")
    task_id=task.get("task_id")
    if not isinstance(task_id,str) or not TASK_ID_RE.fullmatch(task_id):
        raise ValueError("task_id must contain 8-64 safe characters.")
    repo=task.get("repository")
    if repo not in REPO_PROJECT_ALLOWLIST:
        raise ValueError("Repository is not in the browser-worker allowlist.")
    branch=task.get("branch","main")
    if not isinstance(branch,str) or not BRANCH_RE.fullmatch(branch) or ".." in branch or branch.startswith("/") or branch.endswith("/"):
        raise ValueError("Invalid branch.")
    sha=task.get("commit_sha","")
    if sha and (not isinstance(sha,str) or not SHA_RE.fullmatch(sha)):
        raise ValueError("commit_sha must be a full Git commit SHA.")
    project=task.get("project_path","")
    if not isinstance(project,str) or not PATH_RE.fullmatch(project) or project.startswith("/") or ".." in project.split("/"):
        raise ValueError("Invalid project_path.")
    if branch != "main" or project not in REPO_PROJECT_ALLOWLIST[repo]:
        raise ValueError("Repository/project path is outside the browser-worker allowlist.")
    wait=task.get("wait_seconds",10)
    timeout=task.get("import_timeout_seconds",480)
    if type(wait) is not int or not 0<=wait<=120:
        raise ValueError("wait_seconds must be an integer from 0 to 120.")
    if type(timeout) is not int or not 60<=timeout<=600:
        raise ValueError("import_timeout_seconds must be an integer from 60 to 600.")
    values={"accepted":"true","task_id":task_id,"repository":repo,"branch":branch,"commit_sha":sha,
            "project_path":project,"wait_seconds":str(wait),"import_timeout_seconds":str(timeout)}
    result={"accepted":True,"task_id":task_id,"action":"inspect_editor","status":"accepted",
            "source_issue":issue.get("number"),"repository":repo,"branch":branch,"project_path":project}
    result_path.parent.mkdir(parents=True,exist_ok=True)
    result_path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    with output_path.open("a",encoding="utf-8") as out:
        for key,value in values.items():
            out.write(f"{key}={value}\n")
    return result

if __name__=="__main__":
    try:
        print(json.dumps(prepare(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]))))
    except Exception as exc:
        error=str(exc)[:300]
        Path(sys.argv[3]).parent.mkdir(parents=True,exist_ok=True)
        Path(sys.argv[3]).write_text(json.dumps({"accepted":False,"status":"rejected","error":error},indent=2)+"\n",encoding="utf-8")
        with Path(sys.argv[2]).open("a",encoding="utf-8") as out:
            out.write("accepted=false\nerror="+error.replace("\n"," ")+"\n")
        print(error,file=sys.stderr)
        sys.exit(2)
