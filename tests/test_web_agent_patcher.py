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
    def test_patches_engine_plugin_and_exposes_bounded_semantic_commands(self):
        header, source = PATCHER.patch(HEADER, SOURCE)
        self.assertIn("void _process_requests();", header)
        self.assertIn("godot_web_agent_install();", source)
        self.assertIn("agent_timer->connect", source)
        self.assertIn("agent_timer->set_autostart(true);", source)
        self.assertNotIn("agent_timer->start();", source)
        self.assertLess(source.index("agent_timer->set_autostart(true);"), source.index("add_child(agent_timer);"))
        self.assertIn("WebToolsEditorPlugin::_process_requests", source)
        self.assertIn("godot_web_agent_submit", source)
        self.assertIn("editor.list_capabilities", source)
        self.assertIn("editor.get_state", source)
        self.assertIn("scene.get_tree", source)
        self.assertIn("scene.add_node", source)
        self.assertIn("EditorUndoRedoManager *undo_redo = get_undo_redo();", source)
        self.assertIn("undo_redo->create_action", source)
        self.assertIn("undo_redo->add_do_reference(created)", source)
        self.assertIn("allowed_node_types", source)
        self.assertIn("node_name.is_valid_identifier()", source)
        self.assertIn("saved_automatically", source)
        self.assertIn("r_count < 256", source)
        self.assertIn("p_depth < 16", source)
        self.assertIn("payload.length > 16384", source)
        self.assertIn("entry.reject(new Error(\"Native agent request timed out\"))", source)
        self.assertIn("pending.delete(request.id)", source)
        self.assertIn("clearTimeout(entry.timer)", source)
        self.assertNotIn(chr(92) + "tif", source)
        self.assertNotIn("GDScript", source)
        self.assertNotIn("execute_string", source)
        self.assertNotIn("run_shell", source)

    def test_web_compatibility_avoids_unstartable_threads_and_tcp_listener(self):
        project_list = """\tscan_data->thread->start(_scan_thread, scan_data);
\tscan_data->thread->wait_to_finish();"""
        debugger = """\tregister_protocol_handler("tcp://", EditorDebuggerServerTCP::create);"""
        audio = """void AudioDriverWorklet::start(float *p_out_buf, int p_out_buf_size, float *p_in_buf, int p_in_buf_size) {
\tgodot_audio_worklet_start(p_in_buf, p_in_buf_size, p_out_buf, p_out_buf_size, state);
\tthread.start(_audio_thread_func, this);
}
void AudioDriverWorklet::finish_driver() {
\tquit = true; // Ask thread to quit.
\tthread.wait_to_finish();
}"""
        dap = """void DebugAdapterServer::start() {
\tremote_port = (DebugAdapterServer::port_override > -1) ? DebugAdapterServer::port_override : (int)_EDITOR_GET("network/debug_adapter/remote_port");
\tconst Error status = protocol.start(remote_port, IPAddress("127.0.0.1"));
\tif (status != OK) {
\t\tEditorNode::get_log()->add_message("--- Failed to start Debug adapter server on port " + itos(remote_port) + ": " + error_names[status] + " ---", EditorLog::MSG_TYPE_EDITOR);
\t\treturn;
\t}
\tEditorNode::get_log()->add_message("--- Debug adapter server started on port " + itos(remote_port) + " ---", EditorLog::MSG_TYPE_EDITOR);
\tset_process_internal(true);
\tstarted = true;
}"""
        patched_projects, patched_debugger, patched_audio, patched_dap = PATCHER.patch_web_compatibility(project_list, debugger, audio, dap)
        self.assertIn("#if defined(WEB_ENABLED)", patched_projects)
        self.assertIn("_scan_thread(scan_data);", patched_projects)
        self.assertIn("if (scan_data->thread->is_started())", patched_projects)
        self.assertIn('register_protocol_handler("tcp://", EditorDebuggerServerTCP::create);', patched_debugger)
        self.assertNotIn("#if !defined(WEB_ENABLED)", patched_debugger)
        self.assertIn("quit = false;", patched_audio)
        self.assertIn("if (thread.is_started())", patched_audio)
        self.assertIn("#ifdef WEB_ENABLED", patched_dap)
        self.assertIn("native TCP sockets", patched_dap)

    def test_patch_fails_closed_when_upstream_anchor_changes(self):
        with self.assertRaises(ValueError):
            PATCHER.patch(HEADER.replace("_download_zip", "_download_project"), SOURCE)

    def test_patch_rejects_double_application(self):
        patched_header, patched_source = PATCHER.patch(HEADER, SOURCE)
        with self.assertRaises(ValueError):
            PATCHER.patch(patched_header, patched_source)


if __name__ == "__main__":
    unittest.main()
