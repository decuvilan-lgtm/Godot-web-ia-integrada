from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "build" / "patch_godot_web_agent.py"
SPEC = importlib.util.spec_from_file_location("web_agent_patcher", MODULE_PATH)
PATCHER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(PATCHER)


HEADER = """class WebToolsEditorPlugin : public EditorPlugin {
\tGDCLASS(WebToolsEditorPlugin, EditorPlugin);

private:
\tvoid _download_zip();

public:
\tstatic void initialize();

\tWebToolsEditorPlugin();
};
"""

SOURCE = """#include "web_tools_editor_plugin.h"
#include "editor/editor_node.h"

extern "C" {
extern void godot_js_os_download_buffer(const uint8_t *p_buf, int p_buf_size, const char *p_name, const char *p_mime);
}

WebToolsEditorPlugin::WebToolsEditorPlugin() {
\tadd_tool_menu_item("Download Project Source", callable_mp(this, &WebToolsEditorPlugin::_download_zip));
}

void WebToolsEditorPlugin::_download_zip() {
\tDirAccess::remove_file_or_error(output_path);
}
"""


class WebAgentPatcherTests(unittest.TestCase):
    def test_patches_engine_plugin_and_exposes_only_read_only_commands(self):
        header, source = PATCHER.patch(HEADER, SOURCE)
        self.assertIn("void _process(double p_delta) override;", header)
        self.assertIn("godot_web_agent_install();", source)
        self.assertIn("godot_web_agent_submit", source)
        self.assertIn("editor.list_capabilities", source)
        self.assertIn("editor.get_state", source)
        self.assertIn("scene.get_tree", source)
        self.assertNotIn("GDScript", source)
        self.assertNotIn("execute_string", source)

    def test_patch_fails_closed_when_upstream_anchor_changes(self):
        with self.assertRaises(ValueError):
            PATCHER.patch(HEADER.replace("_download_zip", "_download_project"), SOURCE)

    def test_patch_rejects_double_application(self):
        patched_header, patched_source = PATCHER.patch(HEADER, SOURCE)
        with self.assertRaises(ValueError):
            PATCHER.patch(patched_header, patched_source)


if __name__ == "__main__":
    unittest.main()
