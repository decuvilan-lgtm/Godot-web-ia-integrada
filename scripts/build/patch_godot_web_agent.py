#!/usr/bin/env python3
"""Apply the built-in, bounded semantic browser agent patch to Godot 4.7.2-stable.

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
\tvoid _process_requests();"""

BRIDGE_BLOCK = r'''
// Built-in browser agent bridge. Requests are queued and consumed from _process(),
// so editor APIs are only touched on Godot's main thread.
#include "core/io/json.h"
#include "core/templates/vector.h"
#include "editor/editor_interface.h"
#include "editor/editor_undo_redo_manager.h"
#include "core/object/class_db.h"
#include "core/os/memory.h"
#include "scene/main/node.h"
#include "scene/main/timer.h"

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
\t\t\t\tcommands: ["editor.list_capabilities", "editor.get_state", "scene.get_tree", "scene.inspect_node", "scene.add_node"]
\t\t\t};
\t\t},
\t\tdispatch(request) {
\t\t\treturn new Promise((resolve, reject) => {
\t\t\t\tif (!request || typeof request.id !== "string" || !request.id || request.id.length > 128 ||
\t\t\t\t\ttypeof request.command !== "string" || !request.command || request.command.length > 64 || pending.size >= 64 || (request.args != null && (typeof request.args !== "object" || Array.isArray(request.args) || Object.keys(request.args).length > 3))) {
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
\t\t\t\t\targs: request.args || {}
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
\t\t\t\tconst timer = setTimeout(() => {
\t\t\t\t\tconst entry = pending.get(request.id);
\t\t\t\t\tif (!entry) return;
\t\t\t\t\tpending.delete(request.id);
\t\t\t\t\tentry.reject(new Error("Native agent request timed out"));
\t\t\t\t}, 8000);
\t\t\t\tpending.set(request.id, {resolve, reject, timer});
\t\t\t\ttry {
\t\t\t\t\tModule._godot_web_agent_submit(ptr);
\t\t\t\t} catch (error) {
\t\t\t\t\tclearTimeout(timer);
\t\t\t\t\tpending.delete(request.id);
\t\t\t\t\treject(error);
\t\t\t\t} finally {
\t\t\t\t\tModule._free(ptr);
\t\t\t\t}
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
\tconst entry = pending.get(response.id);
\tif (!entry) return;
\tpending.delete(response.id);
\tclearTimeout(entry.timer);
\tentry.resolve(response);
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

static Dictionary godot_web_agent_node_to_dict(Node *p_scene_root, Node *p_node, int &r_count, int p_depth) {
\tDictionary result;
\tresult["name"] = p_node->get_name();
\tresult["type"] = p_node->get_class();
\tresult["path"] = p_node == p_scene_root ? String(".") : String(p_scene_root->get_path_to(p_node));
\tArray children;
\tif (p_depth < 16 && r_count < 256) {
\t\tconst int child_count = MIN(p_node->get_child_count(false), 256 - r_count);
\t\tfor (int i = 0; i < child_count; i++) {
\t\t\tNode *child = p_node->get_child(i, false);
\t\t\tif (child == nullptr) continue;
\t\t\tr_count++;
\t\t\tchildren.push_back(godot_web_agent_node_to_dict(p_scene_root, child, r_count, p_depth + 1));
\t\t}
\t}
\tresult["children"] = children;
\treturn result;
}
'''

PROCESS_BLOCK = r'''
void WebToolsEditorPlugin::_process_requests() {
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
			commands.push_back("scene.inspect_node");
			commands.push_back("scene.add_node");
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
\t\t\t\tresponse["result"] = godot_web_agent_node_to_dict(root, root, count, 0);
\t\t\t}
		} else if (command == "scene.inspect_node") {
			Dictionary args = request.get("args", Dictionary());
			Variant path_value = args.get("path", ".");
			bool path_type_valid = path_value.get_type() == Variant::STRING;
			String path = path_value;
			bool path_valid = path_type_valid && args.size() == 1 && args.has("path") &&
				!path.is_empty() && path.length() <= 200 && !path.begins_with("/") &&
				path.find("..") == -1 && path.find("//") == -1;
			Node *root = EditorInterface::get_singleton() ? EditorInterface::get_singleton()->get_edited_scene_root() : nullptr;
			Node *target = path_valid && root ? (path == "." ? root : root->get_node_or_null(NodePath(path))) : nullptr;
			if (!path_valid) {
				response["error"] = "INVALID_INSPECT_PATH";
				response["message"] = "Node inspection requires a bounded path inside the active scene.";
			} else if (root == nullptr) {
				response["error"] = "NO_ACTIVE_SCENE";
				response["message"] = "There is no active edited scene.";
			} else if (target == nullptr || (target != root && !root->is_ancestor_of(target))) {
				response["error"] = "NODE_NOT_FOUND";
				response["message"] = "The requested node does not exist inside the active edited scene.";
			} else {
				List<PropertyInfo> property_list;
				target->get_property_list(&property_list);
				Array properties;
				int property_count = 0;
				for (const PropertyInfo &property : property_list) {
					if (!(property.usage & PROPERTY_USAGE_EDITOR)) {
						continue;
					}
					if (property_count >= 80) {
						break;
					}
					Dictionary item;
					item["name"] = String(property.name);
					item["type"] = int(property.type);
					item["value"] = String(target->get(property.name));
					properties.push_back(item);
					property_count++;
				}
				Dictionary result;
				result["name"] = target->get_name();
				result["type"] = target->get_class();
				result["path"] = path == "." ? String(".") : String(root->get_path_to(target));
				result["properties"] = properties;
				result["property_count"] = property_count;
				result["properties_truncated"] = property_count >= 80;
				response["ok"] = true;
				response["result"] = result;
			}
		} else if (command == "scene.add_node") {
			Dictionary args = request.get("args", Dictionary());
			Variant node_type_value = args.get("node_type", Variant());
			Variant node_name_value = args.get("node_name", Variant());
			Variant parent_path_value = args.get("parent_path", ".");
			bool argument_types_valid = node_type_value.get_type() == Variant::STRING &&
				node_name_value.get_type() == Variant::STRING &&
				parent_path_value.get_type() == Variant::STRING;
			String node_type = node_type_value;
			String node_name = node_name_value;
			String parent_path = parent_path_value;
			bool allowed_type = false;
			static const char *allowed_node_types[] = {
				"Node", "Node2D", "Sprite2D", "CharacterBody2D", "StaticBody2D",
				"Area2D", "CollisionShape2D", "Camera2D", "Marker2D", "CanvasLayer",
				"Control", "Label", "TextureRect", "AnimationPlayer", "Timer",
				"AudioStreamPlayer2D"
			};
			for (const char *allowed_type_name : allowed_node_types) {
				if (node_type == allowed_type_name) {
					allowed_type = true;
					break;
				}
			}
			bool args_valid = argument_types_valid && args.size() >= 2 && args.size() <= 3 &&
				args.has("node_type") && args.has("node_name") &&
				node_name.is_valid_identifier() && node_name.length() <= 48 &&
				parent_path.length() <= 200 && !parent_path.is_empty() &&
				!parent_path.begins_with("/") && parent_path.find("..") == -1 &&
				parent_path.find("//") == -1 &&
				(args.size() == 2 || (args.size() == 3 && args.has("parent_path")));
			if (!allowed_type || !args_valid) {
				response["error"] = "INVALID_NODE_REQUEST";
				response["message"] = "Node type, name, or parent path is outside the bounded creation allowlist.";
			} else {
				Node *root = EditorInterface::get_singleton() ? EditorInterface::get_singleton()->get_edited_scene_root() : nullptr;
				Node *parent = root ? (parent_path == "." ? root : root->get_node_or_null(NodePath(parent_path))) : nullptr;
				if (root == nullptr || parent == nullptr || (parent != root && !root->is_ancestor_of(parent))) {
					response["error"] = "INVALID_PARENT";
					response["message"] = "The requested parent is not inside the active edited scene.";
				} else if (parent->has_node(NodePath(node_name))) {
					response["error"] = "NODE_ALREADY_EXISTS";
					response["message"] = "A child with that name already exists.";
				} else {
					Object *instance = ClassDB::instantiate(node_type);
					Node *created = Object::cast_to<Node>(instance);
					if (created == nullptr) {
						if (instance != nullptr) {
							memdelete(instance);
						}
						response["error"] = "NODE_CREATION_FAILED";
						response["message"] = "Godot could not instantiate the requested node class.";
					} else {
						created->set_name(node_name);
						EditorUndoRedoManager *undo_redo = get_undo_redo();
						undo_redo->create_action("AI: Add " + node_type);
						undo_redo->add_do_method(parent, "add_child", created);
						undo_redo->add_do_method(created, "set_owner", root);
						undo_redo->add_undo_method(parent, "remove_child", created);
						undo_redo->add_do_reference(created);
						undo_redo->commit_action();
						Dictionary result;
						Dictionary created_info;
						created_info["name"] = node_name;
						created_info["type"] = node_type;
						created_info["path"] = root->get_path_to(created);
						result["created"] = created_info;
						result["undo_available"] = true;
						result["saved_automatically"] = false;
						response["ok"] = true;
						response["result"] = result;
					}
				}
			}
		} else {
			response["error"] = "COMMAND_NOT_ALLOWED";
			response["message"] = "The requested command is not in the built-in semantic allowlist.";
		}
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
        CTOR_ANCHOR[:-1] + "\n\t// Autostart defers Timer::start() until NOTIFICATION_READY, after this plugin enters the scene tree.\n\tTimer *agent_timer = memnew(Timer);\n\tagent_timer->set_wait_time(0.05);\n\tagent_timer->set_one_shot(false);\n\tagent_timer->connect(\"timeout\", callable_mp(this, &WebToolsEditorPlugin::_process_requests));\n\tagent_timer->set_autostart(true);\n\tadd_child(agent_timer);\n\tgodot_web_agent_install();\n}",
        1,
    )
    source = source.replace(CPP_END_ANCHOR, CPP_END_ANCHOR + "\n" + PROCESS_BLOCK.replace("\\t", "\t").rstrip(), 1)
    return header, source

def patch_web_compatibility(
    project_list: str,
    debugger_server: str,
    audio_driver: str,
    debug_adapter_server: str,
) -> tuple[str, str, str, str]:
    """Keep unsupported native thread/socket services out of the Web editor path."""
    scan_start = "\tscan_data->thread->start(_scan_thread, scan_data);"
    scan_replacement = """#if defined(WEB_ENABLED)
\t// Web builds may expose Thread as a non-startable stub. Run the bounded
\t// Project Manager scan synchronously rather than waiting on a thread that
\t// cannot exist in the browser runtime.
\t_scan_thread(scan_data);
#else
\tscan_data->thread->start(_scan_thread, scan_data);
#endif"""
    finish_wait = "\tscan_data->thread->wait_to_finish();"
    finish_replacement = """if (scan_data->thread->is_started()) {
\t\tscan_data->thread->wait_to_finish();
\t}"""
    tcp_register = '\tregister_protocol_handler("tcp://", EditorDebuggerServerTCP::create);'
    # Keep the TCP protocol factory registered on Web builds as well. The
    # Web TCP backend can reject listen() gracefully, but removing the factory
    # makes EditorDebuggerServer::create("tcp://") dereference a null function.
    tcp_replacement = tcp_register
    audio_start = """void AudioDriverWorklet::start(float *p_out_buf, int p_out_buf_size, float *p_in_buf, int p_in_buf_size) {
\tgodot_audio_worklet_start(p_in_buf, p_in_buf_size, p_out_buf, p_out_buf_size, state);
\tthread.start(_audio_thread_func, this);
}"""
    audio_start_replacement = """void AudioDriverWorklet::start(float *p_out_buf, int p_out_buf_size, float *p_in_buf, int p_in_buf_size) {
\t// A previous failed initialization may have called finish() before a worker existed.
\tquit = false;
\tgodot_audio_worklet_start(p_in_buf, p_in_buf_size, p_out_buf, p_out_buf_size, state);
\tthread.start(_audio_thread_func, this);
}"""
    audio_finish = """\tquit = true; // Ask thread to quit.
\tthread.wait_to_finish();"""
    audio_finish_replacement = """\tquit = true; // Ask thread to quit.
\tif (thread.is_started()) {
\t\tthread.wait_to_finish();
\t}"""
    dap_start = """void DebugAdapterServer::start() {
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
    dap_start_replacement = """void DebugAdapterServer::start() {
\tremote_port = (DebugAdapterServer::port_override > -1) ? DebugAdapterServer::port_override : (int)_EDITOR_GET("network/debug_adapter/remote_port");
#ifdef WEB_ENABLED
\tEditorNode::get_log()->add_message("--- External Debug Adapter is unavailable in Web builds because browser builds do not support native TCP sockets. ---", EditorLog::MSG_TYPE_EDITOR);
\treturn;
#else
\tconst Error status = protocol.start(remote_port, IPAddress("127.0.0.1"));
\tif (status != OK) {
\t\tEditorNode::get_log()->add_message("--- Failed to start Debug adapter server on port " + itos(remote_port) + ": " + error_names[status] + " ---", EditorLog::MSG_TYPE_EDITOR);
\t\treturn;
\t}
\tEditorNode::get_log()->add_message("--- Debug adapter server started on port " + itos(remote_port) + " ---", EditorLog::MSG_TYPE_EDITOR);
\tset_process_internal(true);
\tstarted = true;
#endif
}"""
    checks = (
        (project_list, scan_start, finish_wait, "ProjectList thread lifecycle"),
        (debugger_server, tcp_register, None, "debugger TCP registration"),
        (audio_driver, audio_start, audio_finish, "AudioWorklet thread lifecycle"),
        (debug_adapter_server, dap_start, None, "Debug Adapter startup"),
    )
    for source, first, second, label in checks:
        if source.count(first) != 1 or (second and source.count(second) != 1):
            raise ValueError(f"Unexpected {label} anchors")
    project_list = project_list.replace(scan_start, scan_replacement, 1)
    project_list = project_list.replace(finish_wait, finish_replacement, 1)
    debugger_server = debugger_server.replace(tcp_register, tcp_replacement, 1)
    audio_driver = audio_driver.replace(audio_start, audio_start_replacement, 1)
    audio_driver = audio_driver.replace(audio_finish, audio_finish_replacement, 1)
    debug_adapter_server = debug_adapter_server.replace(dap_start, dap_start_replacement, 1)
    return project_list, debugger_server, audio_driver, debug_adapter_server


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot-source", required=True, type=Path)
    args = parser.parse_args()
    root = args.godot_source.resolve()
    header_path = root / "platform/web/editor/web_tools_editor_plugin.h"
    source_path = root / "platform/web/editor/web_tools_editor_plugin.cpp"
    project_list_path = root / "editor/project_manager/project_list.cpp"
    debugger_path = root / "editor/debugger/editor_debugger_server.cpp"
    audio_path = root / "platform/web/audio_driver_web.cpp"
    debug_adapter_path = root / "editor/debugger/debug_adapter/debug_adapter_server.cpp"
    required_paths = (header_path, source_path, project_list_path, debugger_path, audio_path, debug_adapter_path)
    if not all(path.is_file() for path in required_paths):
        raise SystemExit("Not a Godot source checkout: one or more Web Editor patch targets are missing")
    header, source = patch(header_path.read_text(), source_path.read_text())
    project_list, debugger_server, audio_driver, debug_adapter_server = patch_web_compatibility(
        project_list_path.read_text(),
        debugger_path.read_text(),
        audio_path.read_text(),
        debug_adapter_path.read_text(),
    )
    header_path.write_text(header)
    source_path.write_text(source)
    project_list_path.write_text(project_list)
    debugger_path.write_text(debugger_server)
    audio_path.write_text(audio_driver)
    debug_adapter_path.write_text(debug_adapter_server)
    print("Applied built-in bounded semantic Web Editor Agent and Web compatibility patches to engine sources.")
    print("No imported project files were accessed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
