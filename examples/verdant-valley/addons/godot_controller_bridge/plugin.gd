@tool
extends EditorPlugin

const PROTOCOL := 1
const MAX_TREE_NODES := 1000
const MAX_TREE_DEPTH := 12
const ALLOWED_NODE_TYPES := [
	"Node", "Node2D", "Sprite2D", "CharacterBody2D", "StaticBody2D",
	"Area2D", "CollisionShape2D", "Camera2D", "Marker2D", "CanvasLayer",
	"Control", "Label", "TextureRect", "AnimationPlayer", "Timer",
	"AudioStreamPlayer2D"
]

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
		"scene.get_tree",
		"scene.add_node"
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
		"scene.add_node":
			return _add_node(args)
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

func _add_node(args: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _error("NO_OPEN_SCENE", "Open a scene before adding nodes.")

	var node_type := str(args.get("node_type", ""))
	var node_name := str(args.get("node_name", ""))
	var parent_path := str(args.get("parent_path", "."))
	if node_type not in ALLOWED_NODE_TYPES:
		return _error("NODE_TYPE_NOT_ALLOWED", "This node type is not in the safe creation list.")
	if not node_name.is_valid_identifier() or node_name.length() > 48:
		return _error("INVALID_NODE_NAME", "Node names must be valid identifiers of at most 48 characters.")
	if parent_path.is_empty() or parent_path.length() > 200 or parent_path.begins_with("/"):
		return _error("INVALID_PARENT_PATH", "Parent path must be a bounded path relative to the edited scene.")
	var parent: Node = root if parent_path == "." else root.get_node_or_null(NodePath(parent_path))
	if parent == null or not root.is_ancestor_of(parent) and parent != root:
		return _error("INVALID_PARENT_PATH", "The requested parent is not inside the edited scene.")
	if parent.has_node(NodePath(node_name)):
		return _error("NODE_ALREADY_EXISTS", "A child with that name already exists.")

	var created := ClassDB.instantiate(node_type) as Node
	if created == null:
		return _error("NODE_CREATION_FAILED", "Godot could not instantiate the requested node class.")
	created.name = node_name
	var undo_redo := get_undo_redo()
	undo_redo.create_action("AI: Add " + node_type)
	undo_redo.add_do_method(parent, "add_child", created)
	undo_redo.add_do_method(created, "set_owner", root)
	undo_redo.add_undo_method(parent, "remove_child", created)
	undo_redo.add_undo_reference(created)
	undo_redo.commit_action()

	var selection := EditorInterface.get_selection()
	if selection != null:
		selection.clear()
		selection.add_node(created)
	return {
		"ok": true,
		"action": "scene.add_node",
		"created": {"name": node_name, "type": node_type, "path": str(root.get_path_to(created))},
		"undo_available": true,
		"saved_automatically": false
	}
