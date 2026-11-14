#!/usr/bin/env python3
"""Apply the built-in, read-only browser agent patch to Godot 4.7.2-stable.

This patches engine-owned Web Editor sources only. It never reads or writes an
imported game project. The patch is deliberately anchor-validated and fails closed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

HEADER_ANCHOR = "private:\n\tvoid _download_zip();"
CTOR_ANCHOR = 'WebToolsEditorPlugin::WebToolsEditorPlugin() {\n\tadd_tool_menu_item("Download Project Source", callable_mp(this, &WebToolsEditorPlugin::_download_zip));\n}'
INCLUDE_ANCHOR = '#include "editor/editor_node.h"'
EXTERN_ANCHOR = 'extern void godot_js_os_download_buffer(const uint8_t *p_buf, int p_buf_size, const char *p_name, const char *p_mime);\n}'
CPP_END_ANCHOR = 'DirAccess::remove_file_or_error(output_path);\n}'

HEADER_INSERT = """private:
\tvoid _download_zip();
\tvoid _process(double p_delta) override;"""

BRIDGE_BLOCK = r'''
// Built-in browser agent bridge. Requests are queued and consumed from _process(),
// so editor APIs are only touched on Godot's main thread.
#include "core/io/json.h"
#include "core/templates/vector.h"
#include "editor/editor_interface.h"
#include "scene/main/node.h"

static Vector<String> godot_web_agent_requests;

EM_JS(void, godot_web_agent_install, (), {
\tif (typeof window === "undefined" || typeof Module === "undefined") return;
\tconst pending = new Map();
\twindow.__godotEditorAgentPending = pending;
\twindow.__godotEditorAgent = {
\t\tprotocol: 1,
\t\tversion: "1.0.0",
\t\tgetCapabilities() {
\t\t\treturn {
\t\t\t\tprotocol: 1,
\t\t\t\tcommands: ["editor.list_capabilities", "editor.get_state", "scene.get_tree"]
\t\t\t};
\t\t},
\t\tdispatch(request) {
\t\t\treturn new Promise((resolve, reject) => {
\t\t\t\tif (!request || typeof request.id !== "string" || !request.id || request.id.length > 128 ||
\t\t\t\t\ttypeof request.command !== "string" || !request.command || request.command.length > 64 || pending.size >= 64 || (request.args != null && (typeof request.args !== "object" || Array.isArray(request.args) || Object.keys(request.args).length > 0))) {
\t\t\t\t\treject(new Error("Invalid agent request"));
\t\t\t\t\treturn;
\t\t\t\t}
\t\t\t\tif (pending.has(request.id)) {
\t\t\t\t\treject(new Error("Duplicate request id"));
\t\t\t\t\treturn;
\t\t\t\t}
\t\t\t\tconst payload = JSON.stringify({
\t\t\t\t\tid: request.id,
\t\t\t\t\tcommand: request.command,
\t\t\t\t\targs: {}
\t\t\t\t});
\t\t\t\tif (payload.length > 16384) { reject(new Error("Agent request exceeds the 16 KiB limit")); return; }
				const bytes = new TextEncoder().encode(payload);
				if (bytes.length > 16384) { reject(new Error("Agent request exceeds the 16 KiB limit")); return; }
\t\t\t\tconst ptr = Module._malloc(bytes.length + 1);
\t\t\t\tif (!ptr) {
\t\t\t\t\treject(new Error("Unable to allocate request buffer"));
\t\t\t\t\treturn;
\t\t\t\t}
\t\t\t\tModule.HEAPU8.set(bytes, ptr);
\t\t\t\tModule.HEAPU8[ptr + bytes.length] = 0;
\t\t\t\tpending.set(request.id, resolve);
\t\t\t\tModule._godot_web_agent_submit(ptr);
\t\t\t\tModule._free(ptr);
\t\t\t});
\t\t}
\t};
});

EM_JS(void, godot_web_agent_publish, (const char *p_json), {
\tif (typeof window === "undefined") return;
\tlet response;
\ttry { response = JSON.parse(UTF8ToString(p_json)); } catch (_) { return; }
\tconst pending = window.__godotEditorAgentPending;
\tif (!pending || typeof response.id !== "string") return;
\tconst resolve = pending.get(response.id);
\tif (!resolve) return;
\tpending.delete(response.id);
\tresolve(response);
});

extern "C" {
EMSCRIPTEN_KEEPALIVE void godot_web_agent_submit(const char *p_json) {
\tif (p_json == nullptr) return;
\tString request = String::utf8(p_json);
\tif (request.length() > 16384) return;
\tif (godot_web_agent_requests.size() >= 64) return;
	godot_web_agent_requests.push_back(request);
}
}

static Dictionary godot_web_agent_node_to_dict(Node *p_node, int &r_count, int p_depth) {
\tDictionary result;
\tresult["name"] = p_node->get_name();
\tresult["type"] = p_node->get_class();
\tresult["path"] = p_node->get_path();
\tArray children;
\tif (p_depth < 16 && r_count < 256) {
\t\tconst int child_count = MIN(p_node->get_child_count(false), 256 - r_count);
\t\tfor (int i = 0; i < child_count; i++) {
\t\t\tNode *child = p_node->get_child(i, false);
\t\t\tif (child == nullptr) continue;
\t\t\tr_count++;
\t\t\tchildren.push_back(godot_web_agent_node_to_dict(child, r_count, p_depth + 1));
\t\t}
\t}
\tresult["children"] = children;
\treturn result;
}
'''

PROCESS_BLOCK = r'''
void WebToolsEditorPlugin::_process(double p_delta) {
	UNUSED(p_delta);
\tif (godot_web_agent_requests.is_empty()) return;
\tVector<String> requests = godot_web_agent_requests;
\tgodot_web_agent_requests.clear();
\tfor (int i = 0; i < requests.size(); i++) {
\t\tVariant parsed = JSON::parse_string(requests[i]);
\t\tDictionary request = parsed.get_type() == Variant::DICTIONARY ? Dictionary(parsed) : Dictionary();
\t\tString id = request.get("id", "");
\t\tString command = request.get("command", "");
\t\tDictionary response;
\t\tresponse["id"] = id;
\t\tresponse["ok"] = false;
\t\tif (id.is_empty() || id.length() > 128) {
\t\t\tresponse["error"] = "INVALID_REQUEST";
\t\t\tresponse["message"] = "A bounded request id is required.";
\t\t} else if (command == "editor.list_capabilities") {
\t\t\tArray commands;
\t\t\tcommands.push_back("editor.list_capabilities");
\t\t\tcommands.push_back("editor.get_state");
\t\t\tcommands.push_back("scene.get_tree");
\t\t\tresponse["ok"] = true;
\t\t\tresponse["result"] = Dictionary();
\t\t\tDictionary result;
\t\t\tresult["protocol"] = 1;
\t\t\tresult["commands"] = commands;
\t\t\tresponse["result"] = result;
\t\t} else if (command == "editor.get_state") {
\t\t\tDictionary result;
\t\t\tNode *root = EditorInterface::get_singleton() ? EditorInterface::get_singleton()->get_edited_scene_root() : nullptr;
\t\t\tresult["editor_available"] = EditorInterface::get_singleton() != nullptr;
\t\t\tresult["has_scene"] = root != nullptr;
\t\t\tresult["scene_name"] = root ? String(root->get_name()) : String();
\t\t\tresult["scene_path"] = root ? root->get_scene_file_path() : String();
\t\t\tresponse["ok"] = true;
\t\t\tresponse["result"] = result;
\t\t} else if (command == "scene.get_tree") {
\t\t\tNode *root = EditorInterface::get_singleton() ? EditorInterface::get_singleton()->get_edited_scene_root() : nullptr;
\t\t\tif (root == nullptr) {
\t\t\t\tresponse["error"] = "NO_ACTIVE_SCENE";
\t\t\t\tresponse["message"] = "There is no active edited scene.";
\t\t\t} else {
\t\t\t\tint count = 1;
\t\t\t\tresponse["ok"] = true;
\t\t\t\tresponse["result"] = godot_web_agent_node_to_dict(root, count, 0);
\t\t\t}
\t\t} else {
\t\t\tresponse["error"] = "COMMAND_NOT_ALLOWED";
\t\t\tresponse["message"] = "The requested command is not in the built-in read-only allowlist.";
\t\t}
\t\tgodot_web_agent_publish(JSON::stringify(response).utf8().get_data());
\t}
}
'''

def patch(header: str, source: str) -> tuple[str, str]:
    if "__godotEditorAgent" in source or "godot_web_agent_submit" in source:
        raise ValueError("Agent patch already appears to be applied")
    if header.count(HEADER_ANCHOR) != 1:
        raise ValueError("Unexpected WebToolsEditorPlugin header anchor")
    if source.count(INCLUDE_ANCHOR) != 1 or source.count(EXTERN_ANCHOR) != 1:
        raise ValueError("Unexpected WebToolsEditorPlugin include/extern anchors")
    if source.count(CTOR_ANCHOR) != 1 or source.count(CPP_END_ANCHOR) != 1:
        raise ValueError("Unexpected WebToolsEditorPlugin constructor/end anchors")

    header = header.replace(HEADER_ANCHOR, HEADER_INSERT, 1)
    source = source.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + "\n", 1)
    source = source.replace(EXTERN_ANCHOR, EXTERN_ANCHOR + "\n" + BRIDGE_BLOCK.replace("\\t", "\t"), 1)
    source = source.replace(
        CTOR_ANCHOR,
        CTOR_ANCHOR[:-1] + "\n\tset_process(true);\n\tgodot_web_agent_install();\n}",
        1,
    )
    source = source.replace(CPP_END_ANCHOR, CPP_END_ANCHOR + "\n" + PROCESS_BLOCK.replace("\\t", "\t"), 1)
    return header, source

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot-source", required=True, type=Path)
    args = parser.parse_args()
    root = args.godot_source.resolve()
    header_path = root / "platform/web/editor/web_tools_editor_plugin.h"
    source_path = root / "platform/web/editor/web_tools_editor_plugin.cpp"
    if not header_path.is_file() or not source_path.is_file():
        raise SystemExit("Not a Godot source checkout: WebToolsEditorPlugin files are missing")
    header, source = patch(header_path.read_text(), source_path.read_text())
    header_path.write_text(header)
    source_path.write_text(source)
    print("Applied built-in read-only Web Editor Agent patch to engine sources.")
    print("No imported project files were accessed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
