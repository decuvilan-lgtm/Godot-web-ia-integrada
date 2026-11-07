@tool
extends EditorPlugin

const PROTOCOL_VERSION := 1
const MAX_FILES := 1000
const MAX_TREE_NODES := 500
const MAX_TREE_DEPTH := 32
const MAX_FILE_BYTES := 262144
const ALLOWED_TEXT_EXTENSIONS := [".gd", ".tscn", ".tres", ".godot", ".cfg", ".json", ".txt", ".md"]

var _peer: WebSocketPeer
var _token := ""
var _auth_sent := false
var _authenticated := false

var _dock: VBoxContainer
var _url_input: LineEdit
var _token_input: LineEdit
var _status_label: Label


func _enter_tree() -> void:
	_build_dock()
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)
	set_process(true)


func _exit_tree() -> void:
	_disconnect_bridge()
	if is_instance_valid(_dock):
		remove_control_from_docks(_dock)
		_dock.queue_free()


func _build_dock() -> void:
	_dock = VBoxContainer.new()
	_dock.name = "AI Bridge"
	_dock.custom_minimum_size = Vector2(240, 160)

	var heading := Label.new()
	heading.text = "Godot AI Bridge"
	_dock.add_child(heading)

	var url_label := Label.new()
	url_label.text = "Servidor seguro (wss://)"
	_dock.add_child(url_label)

	_url_input = LineEdit.new()
	_url_input.placeholder_text = "wss://godot-web-ia-relay.onrender.com/v1/editor/ID_DE_SESION"
	_url_input.clear_button_enabled = true
	_dock.add_child(_url_input)

	var token_label := Label.new()
	token_label.text = "Token de sesión (solo memoria)"
	_dock.add_child(token_label)

	_token_input = LineEdit.new()
	_token_input.secret = true
	_token_input.placeholder_text = "Token temporal"
	_dock.add_child(_token_input)

	var actions := HBoxContainer.new()
	_dock.add_child(actions)

	var connect_button := Button.new()
	connect_button.text = "Conectar"
	connect_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	connect_button.pressed.connect(_connect_bridge)
	actions.add_child(connect_button)

	var disconnect_button := Button.new()
	disconnect_button.text = "Desconectar"
	disconnect_button.pressed.connect(_disconnect_bridge)
	actions.add_child(disconnect_button)

	_status_label = Label.new()
	_status_label.text = "Desconectado"
	_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_dock.add_child(_status_label)

	var note := Label.new()
	note.text = "Modo inicial: inspección de solo lectura. El token no se guarda en el proyecto."
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_dock.add_child(note)


func _connect_bridge() -> void:
	_disconnect_bridge()

	var url := _url_input.text.strip_edges()
	_token = _token_input.text.strip_edges()

	if not url.begins_with("wss://"):
		_set_status("Se requiere una URL wss:// segura.")
		return
	if _token.is_empty():
		_set_status("Introduce el token temporal de sesión.")
		return

	_peer = WebSocketPeer.new()
	var error := _peer.connect_to_url(url)
	if error != OK:
		_peer = null
		_token = ""
		_set_status("No se pudo iniciar la conexión: %s" % error_string(error))
		return

	_auth_sent = false
	_authenticated = false
	_set_status("Conectando…")


func _disconnect_bridge() -> void:
	if _peer != null:
		_peer.close(1000, "User disconnected")
	_peer = null
	_token = ""
	_auth_sent = false
	_authenticated = false
	if is_instance_valid(_status_label):
		_set_status("Desconectado")


func _process(_delta: float) -> void:
	if _peer == null:
		return

	_peer.poll()
	var state := _peer.get_ready_state()

	if state == WebSocketPeer.STATE_OPEN and not _auth_sent:
		_send_packet({
			"type": "auth",
			"protocol": PROTOCOL_VERSION,
			"token": _token,
		})
		_auth_sent = true
		_set_status("Conectado al transporte; autenticando…")

	if state == WebSocketPeer.STATE_CLOSED:
		var reason := _peer.get_close_reason()
		var code := _peer.get_close_code()
		_peer = null
		_authenticated = false
		_auth_sent = false
		_token = ""
		_set_status("Conexión cerrada (%s): %s" % [code, reason])
		return

	while _peer != null and _peer.get_available_packet_count() > 0:
		var packet := _peer.get_packet()
		var message: Variant = JSON.parse_string(packet.get_string_from_utf8())
		if message is Dictionary:
			_handle_message(message)


func _handle_message(message: Dictionary) -> void:
	var message_type := str(message.get("type", ""))

	if message_type == "auth_ok":
		_authenticated = true
		_set_status("Autenticado · modo de solo lectura")
		return

	if message_type == "auth_error":
		_authenticated = false
		_set_status("Autenticación rechazada.")
		_disconnect_bridge()
		return

	if message_type != "request":
		return

	var request_id: Variant = message.get("id", "")
	var action := str(message.get("action", ""))
	var args: Variant = message.get("args", {})
	if typeof(args) != TYPE_DICTIONARY:
		args = {}

	if not _authenticated:
		_send_response(request_id, false, {}, "Not authenticated")
		return

	var result := _dispatch_read_only(action, args)
	_send_response(
		request_id,
		bool(result.get("ok", false)),
		result.get("data", {}),
		str(result.get("error", ""))
	)


func _dispatch_read_only(action: String, args: Dictionary) -> Dictionary:
	match action:
		"ping":
			return {"ok": true, "data": {"pong": true, "protocol": PROTOCOL_VERSION}}
		"project.get_state":
			return {"ok": true, "data": _get_project_state()}
		"project.list_files":
			return {"ok": true, "data": {"files": _list_project_files()}}
		"scene.inspect":
			return _inspect_current_scene()
		"script.read":
			return _read_project_text_file(str(args.get("path", "")))
		_:
			return {"ok": false, "error": "Action not allowed in read-only protocol v1"}


func _get_project_state() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	return {
		"project_name": str(ProjectSettings.get_setting("application/config/name", "")),
		"scene_open": root != null,
		"scene_name": str(root.name) if root != null else "",
		"scene_path": root.scene_file_path if root != null else "",
		"protocol": PROTOCOL_VERSION,
		"capabilities": ["ping", "project.get_state", "project.list_files", "scene.inspect", "script.read"],
	}


func _inspect_current_scene() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return {"ok": false, "error": "No scene is currently open"}
	var state := {"count": 0}
	var tree := _serialize_node(root, 0, state)
	return {
		"ok": true,
		"data": {
			"scene_path": root.scene_file_path,
			"node_count": state.count,
			"tree": tree,
		},
	}


func _serialize_node(node: Node, depth: int, state: Dictionary) -> Dictionary:
	state.count += 1
	var result := {
		"name": str(node.name),
		"class": node.get_class(),
		"path": str(node.get_path()),
		"children": [],
	}
	if depth >= MAX_TREE_DEPTH or state.count >= MAX_TREE_NODES:
		result["truncated"] = true
		return result

	var children: Array = []
	for child in node.get_children():
		if state.count >= MAX_TREE_NODES:
			result["truncated"] = true
			break
		children.append(_serialize_node(child, depth + 1, state))
	result["children"] = children
	return result


func _list_project_files() -> Array:
	var output: Array = []
	_collect_files("res://", output)
	output.sort()
	return output


func _collect_files(directory_path: String, output: Array) -> void:
	if output.size() >= MAX_FILES:
		return

	var directory := DirAccess.open(directory_path)
	if directory == null:
		return

	for file_name in directory.get_files():
		if output.size() >= MAX_FILES:
			return
		if file_name.ends_with(".import") or file_name.begins_with("."):
			continue
		output.append(directory_path.path_join(file_name))

	for directory_name in directory.get_directories():
		if output.size() >= MAX_FILES:
			return
		if directory_name.begins_with(".") or directory_name in [".godot", ".git", "node_modules"]:
			continue
		_collect_files(directory_path.path_join(directory_name), output)


func _read_project_text_file(path: String) -> Dictionary:
	if not path.begins_with("res://") or path.contains(".."):
		return {"ok": false, "error": "Only safe res:// paths are allowed"}

	var extension := path.get_extension().to_lower()
	if ("." + extension) not in ALLOWED_TEXT_EXTENSIONS:
		return {"ok": false, "error": "File extension is not allowed"}

	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {"ok": false, "error": "Unable to open file"}

	if file.get_length() > MAX_FILE_BYTES:
		return {"ok": false, "error": "File exceeds the read limit"}

	return {
		"ok": true,
		"data": {
			"path": path,
			"text": file.get_as_text(),
		},
	}


func _send_response(request_id: Variant, ok: bool, data: Variant, error: String) -> void:
	_send_packet({
		"type": "response",
		"id": request_id,
		"ok": ok,
		"data": data,
		"error": error,
	})


func _send_packet(payload: Dictionary) -> void:
	if _peer == null or _peer.get_ready_state() != WebSocketPeer.STATE_OPEN:
		return
	_peer.send_text(JSON.stringify(payload))


func _set_status(value: String) -> void:
	if is_instance_valid(_status_label):
		_status_label.text = value
