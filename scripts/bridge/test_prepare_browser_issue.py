import json
import tempfile
import unittest
from pathlib import Path

from prepare_browser_issue import prepare

SOURCE_REPO="gavilandavid89-pixel/Ajedrez-2c2"
LAB_REPO="decuvilan-lgtm/Godot-web-ia-integrada"

class PrepareBrowserIssueTests(unittest.TestCase):
    def run_task(self, repository, project_path, branch="main"):
        temp=tempfile.TemporaryDirectory()
        root=Path(temp.name)
        event=root/"event.json"
        output=root/"output.txt"
        result=root/"result.json"
        task={
            "protocol":1,
            "task_id":"browser-sandbox-test-01",
            "action":"inspect_editor",
            "repository":repository,
            "branch":branch,
            "commit_sha":"a"*40,
            "project_path":project_path,
            "wait_seconds":5,
            "import_timeout_seconds":180,
        }
        event.write_text(json.dumps({"issue":{"title":"[CHATGPT-BROWSER] test","body":json.dumps(task),"number":43}}),encoding="utf-8")
        return temp,event,output,result

    def test_accepts_read_only_source_project(self):
        temp,event,output,result=self.run_task(SOURCE_REPO,"ajedrez_2c2_v161")
        with temp:
            accepted=prepare(event,output,result)
            self.assertTrue(accepted["accepted"])
            self.assertIn(f"repository={SOURCE_REPO}",output.read_text())

    def test_accepts_only_lab_sandbox_project(self):
        temp,event,output,result=self.run_task(LAB_REPO,"examples/bridge-sandbox")
        with temp:
            accepted=prepare(event,output,result)
            self.assertTrue(accepted["accepted"])
            self.assertIn("project_path=examples/bridge-sandbox",output.read_text())

    def test_rejects_other_lab_project_paths(self):
        temp,event,output,result=self.run_task(LAB_REPO,"relay")
        with temp:
            with self.assertRaises(ValueError):
                prepare(event,output,result)

    def test_rejects_unknown_repository(self):
        temp,event,output,result=self.run_task("owner/other-game","project")
        with temp:
            with self.assertRaises(ValueError):
                prepare(event,output,result)

    def test_rejects_non_main_branch(self):
        temp,event,output,result=self.run_task(LAB_REPO,"examples/bridge-sandbox",branch="feature/test")
        with temp:
            with self.assertRaises(ValueError):
                prepare(event,output,result)

if __name__=="__main__":
    unittest.main()
