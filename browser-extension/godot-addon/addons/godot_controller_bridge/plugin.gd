@tool
extends EditorPlugin

const PROTOCOL_VERSION := 1
const MAX_TREE_NODES := 500
const MAX_PROPERTIES := 120
const MAIN_SCREENS := ["2D", "3D", "Script", "AssetLib"]

var _dispatch_callback: JavaScriptObject
var _window: JavaScriptObject
var _bridge_installed := false


func _enter_tree() -> void:
	if not OS.has_feature("web"):
		push_warning("Godot Controller Bridge only activates inside the Godot Web editor.")
		return
	_window = JavaScriptBridge.get_interface("window")
	if _window == null:
		push_warning("Godot Controller Bridge could not access the browser window.")
		return
	_dispatch_callback = JavaScriptBridge.create_callback(_on_dispatch)
	_window.__godotEditorAgentDispatch = _dispatch_callback
	JavaScriptBridge.eval("""
	(() => {
		const pending = new Map();
		window.__godotEditorAgentResolve = (id, json) => {
			const resolve = pending.get(id);
			if (!resolve) return;
			pending.delete(id);
			try { resolve(JSON.parse(json)); }
			catch (_) { resolve({ok:false, error:"INVALID_EDITOR_RESPONSE"}); }
		};
		window.__godotEditorAgent = {
			protocol: 1,
			version: "0.1.0",
			execute(command) {
				return new Promise((resolve) => {
					const id = "godot-editor-" + Date.now() + "-" + Math.random().toString(36).slice(2);
					pending.set(id, resolve);
					try {
						window.__godotEditorAgentDispatch(id, JSON.stringify(command));
					} catch (error) {
						pending.delete(id);
						resolve({ok:false, error:"EDITOR_DISPATCH_FAILED", message:String(error).slice(0,300)});
					}
				});
			}
		};
	})();
	""", true)
	_bridge_installed = true


func _exit_tree() -> void:
	if _bridge_installed and _window != null:
		JavaScriptBridge.eval("""
		if (window.__godotEditorAgent) {
			delete window.__godotEditorAgent;
			delete window.__godotEditorAgentResolve;
			delete window.__godotEditorAgentDispatch;
		}
		""", true)
	_bridge_installed = false
	_dispatch_callback = null
	_window = null


func _on_dispatch(args: Array) -> void:
	if args.size() != 2:
		return
	var request_id := str(args[0])
	var command_json := str(args[1])
	var parsed = JSON.parse_string(command_json)
	var result: Dictionary
	if not parsed is Dictionary:
		result = _failure("INVALID_COMMAND", "Command must be a JSON object.")
	else:
		result = _execute(parsed)
	if _window != null:
		_window.__godotEditorAgentResolve(request_id, JSON.stringify(result))


func _execute(command: Dictionary) -> Dictionary:
	var action := str(command.get("action", ""))
	match action:
		"editor.list_capabilities":
			return {
				"ok": true,
				"protocol": PROTOCOL_VERSION,
				"version": "0.1.0",
				"actions": [
					"editor.get_state",
					"editor.list_capabilities",
					"editor.open_panel",
					"scene.open",
					"scene.select_node",
					"node.get_inspector"
				],
				"main_screens": MAIN_SCREENS
			}
		"editor.get_state":
			return _get_editor_state()
		"editor.open_panel":
			return _open_main_screen(command)
		"scene.open":
			return _open_scene(command)
		"scene.select_node":
			return _select_node(command)
		"node.get_inspector":
			return _get_node_inspector(command)
		_:
			return _failure("COMMAND_NOT_ALLOWED", "The requested editor action is not supported.")


func _get_editor_state() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	var selected_paths: Array[String] = []
	var selection := EditorInterface.get_selection()
	if selection != null:
		for node in selection.get_selected_nodes():
			if is_instance_valid(node):
				selected_paths.append(str(root.get_path_to(node)) if root != null else str(node.get_path()))
	var scene_path := ""
	if root != null:
		scene_path = root.scene_file_path
	return {
		"ok": true,
		"editor": "Godot Web",
		"main_screen": _get_main_screen_name(),
		"scene_path": scene_path,
		"scene_root": root.name if root != null else "",
		"selected_nodes": selected_paths,
		"unsaved_scenes": Array(EditorInterface.get_unsaved_scenes()),
		"is_playing": EditorInterface.is_playing_scene(),
		"tree": _serialize_tree(root)
	}


func _get_main_screen_name() -> String:
	for screen in MAIN_SCREENS:
		if EditorInterface.get_editor_main_screen() != null:
			# The editor API does not expose a getter for the active main-screen tab.
			# Return an explicit unknown value rather than inferring from pixels.
			return "unknown"
	return "unknown"


func _serialize_tree(root: Node) -> Array:
	var output: Array = []
	if root == null:
		return output
	var stack: Array[Dictionary] = [{"node": root, "path": NodePath(".")}]
	while not stack.is_empty() and output.size() < MAX_TREE_NODES:
		var item: Dictionary = stack.pop_back()
		var node: Node = item.node
		var path: NodePath = item.path
		output.append({
			"name": str(node.name),
			"type": node.get_class(),
			"path": str(path)
		})
		var children := node.get_children()
		for index in range(children.size() - 1, -1, -1):
			var child: Node = children[index]
			var child_path := NodePath(str(path).path_join(str(child.name)))
			stack.append({"node": child, "path": child_path})
	return output


func _open_main_screen(command: Dictionary) -> Dictionary:
	var screen := str(command.get("panel", ""))
	if not MAIN_SCREENS.has(screen):
		return _failure("INVALID_PANEL", "Supported main screens: 2D, 3D, Script, AssetLib.")
	EditorInterface.set_main_screen_editor(screen)
	return {"ok": true, "panel": screen}


func _open_scene(command: Dictionary) -> Dictionary:
	var path := str(command.get("scene_path", ""))
	if not _valid_project_path(path) or not path.ends_with(".tscn"):
		return _failure("INVALID_SCENE_PATH", "Expected a project-local res:// .tscn path.")
	if not FileAccess.file_exists(path):
		return _failure("SCENE_NOT_FOUND", "The requested scene does not exist.")
	EditorInterface.open_scene_from_path(path)
	return {"ok": true, "scene_path": path, "accepted": true}


func _select_node(command: Dictionary) -> Dictionary:
	var path := str(command.get("node_path", ""))
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _failure("NO_ACTIVE_SCENE", "There is no open scene.")
	var node := root.get_node_or_null(NodePath(path))
	if node == null:
		return _failure("NODE_NOT_FOUND", "The node path does not exist in the active scene.")
	var selection := EditorInterface.get_selection()
	selection.clear()
	selection.add_node(node)
	EditorInterface.edit_node(node)
	return {"ok": true, "node_path": str(root.get_path_to(node)), "node_name": str(node.name)}


func _get_node_inspector(command: Dictionary) -> Dictionary:
	var path := str(command.get("node_path", ""))
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _failure("NO_ACTIVE_SCENE", "There is no open scene.")
	var node: Node = root if path in ["", "."] else root.get_node_or_null(NodePath(path))
	if node == null:
		return _failure("NODE_NOT_FOUND", "The node path does not exist in the active scene.")
	var properties: Array = []
	for property in node.get_property_list():
		if properties.size() >= MAX_PROPERTIES:
			break
		var usage := int(property.get("usage", 0))
		if (usage & PROPERTY_USAGE_EDITOR) == 0:
			continue
		var property_name := str(property.get("name", ""))
		properties.append({
			"name": property_name,
			"type": int(property.get("type", TYPE_NIL)),
			"value": _safe_value(node.get(property_name))
		})
	EditorInterface.inspect_object(node)
	return {"ok": true, "node_path": str(root.get_path_to(node)), "node_type": node.get_class(), "properties": properties}


func _safe_value(value: Variant) -> Variant:
	match typeof(value):
		TYPE_NIL, TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_STRING:
			return value
		TYPE_VECTOR2, TYPE_VECTOR2I, TYPE_VECTOR3, TYPE_VECTOR3I, TYPE_VECTOR4, TYPE_VECTOR4I, TYPE_RECT2, TYPE_COLOR:
			return str(value)
		TYPE_STRING_NAME, TYPE_NODE_PATH:
			return str(value)
		_:
			return "<" + type_string(typeof(value)) + ">"


func _valid_project_path(path: String) -> bool:
	if not path.begins_with("res://") or path.length() > 500:
		return false
	if path.contains("..") or path.contains("\\") or path.contains("\u0000"):
		return false
	return true


func _failure(code: String, message: String) -> Dictionary:
	return {"ok": false, "error": code, "message": message}
