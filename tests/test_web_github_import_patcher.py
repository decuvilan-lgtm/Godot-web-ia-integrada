from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "scripts" / "apply-web-github-import.py"


class WebGithubImportPatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = self.root / "engine" / "godot" / "editor" / "project_manager"
        source.mkdir(parents=True)
        (source / "project_manager.h").write_text(
            "class HFlowContainer;\nclass LineEdit;\n"
            "ProjectDialog *project_dialog = nullptr;\n"
            "\tvoid _import_project();\n\tvoid _new_project();\n",
            encoding="utf-8",
        )
        (source / "project_manager.cpp").write_text(
            '#include "scene/gui/separator.h"\n#include "scene/main/scene_tree.h"\n'
            "void ProjectManager::_import_project() {\n"
            "\tproject_dialog->set_mode(ProjectDialog::MODE_IMPORT);\n"
            "\tproject_dialog->ask_for_path_and_show();\n"
            "}\n\nvoid ProjectManager::_new_project() {\n}\n"
            "\t\t\thb->add_child(import_btn);\n\n\t\t\tscan_btn = memnew(Button);\n",
            encoding="utf-8",
        )
        # The patcher resolves engine/godot relative to its own path.
        self.script = self.root / "scripts" / PATCHER.name
        self.script.parent.mkdir()
        shutil.copy2(PATCHER, self.script)

    def tearDown(self):
        self.temp.cleanup()

    def run_patcher(self):
        return subprocess.run(
            [sys.executable, str(self.script)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_adds_github_import_to_project_manager(self):
        result = self.run_patcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        header = (self.root / "engine/godot/editor/project_manager/project_manager.h").read_text()
        source = (self.root / "engine/godot/editor/project_manager/project_manager.cpp").read_text()
        self.assertIn("HTTPRequest *github_http_request", header)
        self.assertIn("_github_download_completed", header)
        self.assertIn("https://godot-web-ia-relay.onrender.com/v1/github/import/", source)
        self.assertNotIn("api.github.com/repos/", source)
        self.assertIn("set_body_size_limit(64 * 1024 * 1024)", source)
        # Web HTTPClient reports unknown response lengths; do not use HTTPRequest's
        # download-to-file path, which removes successful unknown-length downloads.
        self.assertNotIn("set_download_file(github_zip_path)", source)
        self.assertIn("zip_file->store_buffer(p_body.ptr(), p_body.size())", source)
        self.assertIn("request result %d, HTTP %d", source)
        self.assertIn('github_import_btn->set_text(TTRC("GitHub"))', source)
        self.assertIn("_install_project(github_zip_path, github_repo_name)", source)

    def test_fails_closed_when_upstream_anchor_changes(self):
        header = self.root / "engine/godot/editor/project_manager/project_manager.h"
        header.write_text("class HFlowContainer;\nclass ChangedLineEdit;\n", encoding="utf-8")
        result = self.run_patcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected exactly one patch anchor", result.stderr)


if __name__ == "__main__":
    unittest.main()
