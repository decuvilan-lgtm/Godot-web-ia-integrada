@tool
extends EditorPlugin

const PROTOCOL := 1
const MAX_TREE_NODES := 1000
const MAX_TREE_DEPTH := 12

var _adapter: JavaScriptObject
var _dispatch_callback: JavaScriptObject
var _capabilities_callback: JavaScriptObject
var _window: JavaScriptObject


func _enter_tree() -> void:
	if not OS.has_feature("web"):
		return
	_window = JavaScriptBridge.get_interface("window")
	_adapter = JavaScriptBridge.create_object("Object")
	_dispatch_callback = JavaScriptBridge.create_callback(_dispatch)
	_capabilities_callback = JavaScriptBridge.create_callback(_get_capabilities)
	_adapter.set("protocol", PROTOCOL)
	_adapter.set("version", "godot-editor-agent/1.0.0")
	_adapter.set("dispatch", _dispatch_callback)
	_adapter.set("getCapabilities", _capabilities_callback)
	_window.set("__godotEditorAgent", _adapter)


func _exit_tree() -> void:
	if _window != null:
		var current = _window.get("__godotEditorAgent")
		if current == _adapter:
			_window.set("__godotEditorAgent", null)
	_adapter = null
	_dispatch_callback = null
	_capabilities_callback = null
	_window = null


func _get_capabilities(_arguments: Array) -> Array:
	return [
		"editor.get_state",
		"editor.list_capabilities",
		"scene.get_tree"
	]


func _dispatch(arguments: Array) -> Dictionary:
	if arguments.is_empty() or not arguments[0] is Dictionary:
		return _error("INVALID_REQUEST", "Expected one request object.")

	var request: Dictionary = arguments[0]
	var action := str(request.get("command", ""))
	var args: Variant = request.get("args", {})
	if not args is Dictionary:
		return _error("INVALID_ARGUMENTS", "Arguments must be an object.")
	if not args.is_empty():
		return _error("INVALID_ARGUMENTS", "This adapter version accepts no arguments.")

	match action:
		"editor.get_state":
			return {"ok": true, "action": action, "data": _editor_state()}
		"editor.list_capabilities":
			return {"ok": true, "action": action, "data": _get_capabilities([])}
		"scene.get_tree":
			return {"ok": true, "action": action, "data": _scene_tree()}
		_:
			return _error("COMMAND_NOT_ALLOWED", "The requested editor operation is not enabled.")


func _editor_state() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	var selected: Array[String] = []
	var selection := EditorInterface.get_selection()
	if selection != null:
		for node in selection.get_selected_nodes():
			if is_instance_valid(node):
				selected.append(str(root.get_path_to(node)) if root != null else str(node.get_path()))

	return {
		"engine_version": Engine.get_version_info(),
		"project_path": ProjectSettings.globalize_path("res://"),
		"edited_scene": root.scene_file_path if root != null else "",
		"edited_root_name": str(root.name) if root != null else "",
		"selected_nodes": selected,
		"open_scenes": Array(EditorInterface.get_open_scenes()),
		"scene_open": root != null
	}


func _scene_tree() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return {"available": false, "reason": "No scene is currently open.", "nodes": []}

	var budget := [0]
	var serialized := _serialize_node(root, 0, budget)
	return {
		"available": true,
		"scene_path": root.scene_file_path,
		"node_count": budget[0],
		"truncated": budget[0] >= MAX_TREE_NODES,
		"root": serialized
	}


func _serialize_node(node: Node, depth: int, budget: Array) -> Dictionary:
	budget[0] += 1
	var item := {
		"name": str(node.name),
		"type": node.get_class(),
		"path": str(node.get_path()),
		"groups": _string_array(node.get_groups()),
		"children": []
	}
	if depth >= MAX_TREE_DEPTH or budget[0] >= MAX_TREE_NODES:
		item["truncated"] = node.get_child_count() > 0
		return item

	var children: Array[Dictionary] = []
	for child in node.get_children():
		if budget[0] >= MAX_TREE_NODES:
			item["truncated"] = true
			break
		children.append(_serialize_node(child, depth + 1, budget))
	item["children"] = children
	return item


func _string_array(values: Array) -> Array[String]:
	var result: Array[String] = []
	for value in values:
		result.append(str(value))
	return result


func _error(code: String, message: String) -> Dictionary:
	return {"ok": false, "error": code, "message": message}
