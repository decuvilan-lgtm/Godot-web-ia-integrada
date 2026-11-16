@tool
extends EditorPlugin

const BRIDGE_PORT := 48765
const REGISTRY_PATH := "user://headless_bridge.json"
const PROTOCOL_VERSION := 1
const CONNECTION_IDLE_TIMEOUT_MS := 5000
const SCENE_OPEN_TIMEOUT_MS := 10000

var _server: TCPServer
var _clients: Array[Dictionary] = []
var _pending_scene_opens: Array[Dictionary] = []
var _token := ""
var _project_id := ""
var _registry_absolute_path := ""
var _status_label: Label
var _marker_label: Label
var _panel: VBoxContainer
var _last_activity_msec := 0
var _video_recording: Dictionary = {}
var _last_video_result: Dictionary = {}
var _capture_sequence := 0


func _enter_tree() -> void:
	_project_id = ProjectSettings.globalize_path("res://").simplify_path().sha256_text()
	_token = Crypto.new().generate_random_bytes(32).hex_encode()
	_registry_absolute_path = ProjectSettings.globalize_path(REGISTRY_PATH)

	_panel = VBoxContainer.new()
	_panel.name = "HeadlessBridge"
	_panel.custom_minimum_size = Vector2(260, 110)
	var heading := Label.new()
	heading.text = "HEADLESS SESSION BRIDGE"
	_panel.add_child(heading)
	_status_label = Label.new()
	_status_label.text = "Estado: esperando operador"
	_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_panel.add_child(_status_label)
	_marker_label = Label.new()
	_marker_label.text = ""
	_marker_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_panel.add_child(_marker_label)
	var hint := Label.new()
	hint.text = "Órdenes permitidas: ping, marcadores, escenas, inspección, recursos y nodos."
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_panel.add_child(hint)
	add_control_to_bottom_panel(_panel, "Headless Bridge")
	make_bottom_panel_item_visible(_panel)

	_server = TCPServer.new()
	var error := _server.listen(BRIDGE_PORT, "127.0.0.1")
	if error != OK:
		_status_label.text = "Error al abrir puerto: %s" % error
		push_error("Headless bridge could not listen on 127.0.0.1:%d" % BRIDGE_PORT)
		return

	set_process(true)
	call_deferred("_announce_when_ready")


func _exit_tree() -> void:
	set_process(false)
	if _server != null:
		_server.stop()
	for client in _clients:
		var peer: StreamPeerTCP = client["peer"]
		if peer.get_status() == StreamPeerTCP.STATUS_CONNECTED:
			peer.disconnect_from_host()
	_clients.clear()
	_remove_own_registry()
	if _panel != null and is_instance_valid(_panel):
		remove_control_from_bottom_panel(_panel)
		_panel.queue_free()


func _process(_delta: float) -> void:
	if _server == null:
		return

	# Accept every pending local client. The persistent heartbeat operator and
	# short-lived command clients no longer compete for a single socket.
	while _server.is_connection_available():
		var peer := _server.take_connection()
		_clients.append({
			"peer": peer,
			"buffer": "",
			"last_activity_msec": Time.get_ticks_msec()
		})

	for index in range(_clients.size() - 1, -1, -1):
		var client: Dictionary = _clients[index]
		var peer: StreamPeerTCP = client["peer"]
		peer.poll()
		if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
			_remove_client(index)
			continue

		var available := peer.get_available_bytes()
		if available <= 0:
			if Time.get_ticks_msec() - int(client["last_activity_msec"]) > CONNECTION_IDLE_TIMEOUT_MS and not _has_pending_scene_open(peer):
				peer.disconnect_from_host()
				_remove_client(index)
			continue

		client["last_activity_msec"] = Time.get_ticks_msec()
		var packet := peer.get_data(available)
		if packet[0] != OK:
			_remove_client(index)
			continue
		client["buffer"] = str(client["buffer"]) + packet[1].get_string_from_utf8()
		if str(client["buffer"]).length() > 65536:
			peer.disconnect_from_host()
			_remove_client(index)
			continue

		while str(client["buffer"]).contains("\n"):
			var buffer_text := str(client["buffer"])
			var split_at := buffer_text.find("\n")
			var line := buffer_text.substr(0, split_at).strip_edges()
			client["buffer"] = buffer_text.substr(split_at + 1)
			if not line.is_empty():
				_handle_request(peer, line)
		_clients[index] = client

	_poll_pending_scene_opens()
	_process_video_recording()


func _has_pending_scene_open(peer: StreamPeerTCP) -> bool:
	for pending in _pending_scene_opens:
		if pending.get("peer") == peer:
			return true
	return false


func _poll_pending_scene_opens() -> void:
	for index in range(_pending_scene_opens.size() - 1, -1, -1):
		var pending: Dictionary = _pending_scene_opens[index]
		var peer: StreamPeerTCP = pending["peer"]
		if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
			_pending_scene_opens.remove_at(index)
			continue

		var requested_path := str(pending["scene_path"])
		var root := EditorInterface.get_edited_scene_root()
		if root != null and root.scene_file_path == requested_path:
			_send_response(peer, {
				"ok": true,
				"command": str(pending.get("command", "open_scene")),
				"project_id": _project_id,
				"editor_pid": OS.get_process_id(),
				"result": {"ok": true, "scene_path": requested_path, "opened": true}
			})
			_pending_scene_opens.remove_at(index)
			continue

		if Time.get_ticks_msec() >= int(pending["deadline_msec"]):
			_send_response(peer, {
				"ok": false,
				"command": str(pending.get("command", "open_scene")),
				"project_id": _project_id,
				"editor_pid": OS.get_process_id(),
				"error": "scene_open_timeout",
				"result": {"ok": false, "scene_path": requested_path, "opened": false}
			})
			_pending_scene_opens.remove_at(index)


func _remove_client(index: int) -> void:
	if index < 0 or index >= _clients.size():
		return
	_clients.remove_at(index)
	if _clients.is_empty():
		_status_label.text = "Estado: esperando operador"


func _handle_request(peer: StreamPeerTCP, line: String) -> void:
	var parsed: Variant = JSON.parse_string(line)
	if not parsed is Dictionary:
		_send_response(peer, {"ok": false, "error": "invalid_json"})
		return
	var request: Dictionary = parsed
	if int(request.get("protocol", -1)) != PROTOCOL_VERSION:
		_send_response(peer, {"ok": false, "error": "protocol_mismatch"})
		return
	if str(request.get("token", "")) != _token:
		_send_response(peer, {"ok": false, "error": "unauthorized"})
		return
	if str(request.get("project_id", "")) != _project_id:
		_send_response(peer, {"ok": false, "error": "wrong_project"})
		return

	var command := str(request.get("command", ""))
	var response := {"ok": true, "command": command, "project_id": _project_id, "editor_pid": OS.get_process_id()}
	match command:
		"editor.list_capabilities":
			response["result"] = {
				"ok": true,
				"adapter": "godot_native_editor",
				"protocol": PROTOCOL_VERSION,
				"project_id": _project_id,
				"commands": [
					"editor.list_capabilities", "editor.get_state",
					"scene.get_tree", "scene.inspect_selection",
					"scene.add_node", "scene.set_node_properties", "scene.configure_collision_shape",
					"scene.assign_visual_resource", "scene.create_sprite_frames",
					"editor.open_scene", "editor.focus_inspector", "editor.inspect_undo_history",
					"editor.undo", "editor.redo", "editor.inspect_project_settings", "editor.inspect_editor_settings",
					"project.list_resources", "project.inspect_resource", "preview.get_status",
					"preview.start", "preview.stop", "capture.editor_screenshot",
					"capture.desktop_screenshot", "capture.start_editor_video", "capture.stop_editor_video", "capture.get_video_status", "capture.read_chunk"
				],
				"legacy_commands": [
					"ping", "inspect_scene", "inspect_selection", "add_node",
					"set_node_properties", "list_project_resources", "preview_status",
					"start_preview", "stop_preview", "capture_editor_screenshot"
				],
				"mutations_require_explicit_commands": true,
				"automatic_save": false
			}
		"editor.get_state":
			var active_root := EditorInterface.get_edited_scene_root()
			response["result"] = {
				"ok": true,
				"adapter": "godot_native_editor",
				"project_id": _project_id,
				"project_path": ProjectSettings.globalize_path("res://").simplify_path(),
				"editor_pid": OS.get_process_id(),
				"active_scene": active_root.scene_file_path if active_root != null else "",
				"preview": _preview_status()
			}
		"scene.get_tree":
			var semantic_tree_result := _inspect_edited_scene()
			response["ok"] = bool(semantic_tree_result.get("ok", false))
			response["result"] = semantic_tree_result
		"scene.inspect_selection":
			var semantic_selection_result := _inspect_editor_selection()
			response["ok"] = bool(semantic_selection_result.get("ok", false))
			response["result"] = semantic_selection_result
		"scene.add_node":
			var semantic_add_result := _add_node_to_edited_scene(request.get("args", {}))
			response["ok"] = bool(semantic_add_result.get("ok", false))
			response["result"] = semantic_add_result
		"scene.set_node_properties":
			var semantic_property_result := _set_node_properties(request.get("args", {}))
			response["ok"] = bool(semantic_property_result.get("ok", false))
			response["result"] = semantic_property_result
		"project.list_resources":
			var semantic_resources_result := _list_project_resources()
			response["ok"] = bool(semantic_resources_result.get("ok", false))
			response["result"] = semantic_resources_result
		"preview.get_status":
			var semantic_preview_status := _preview_status()
			response["ok"] = bool(semantic_preview_status.get("ok", false))
			response["result"] = semantic_preview_status
		"preview.start":
			var semantic_preview_start := _start_preview(request.get("args", {}))
			response["ok"] = bool(semantic_preview_start.get("ok", false))
			response["result"] = semantic_preview_start
		"preview.stop":
			var semantic_preview_stop := _stop_preview()
			response["ok"] = bool(semantic_preview_stop.get("ok", false))
			response["result"] = semantic_preview_stop
		"capture.editor_screenshot":
			var semantic_capture := _capture_editor_screenshot()
			response["ok"] = bool(semantic_capture.get("ok", false))
			response["result"] = semantic_capture
		"scene.configure_collision_shape":
			var semantic_shape_result := _configure_collision_shape(request.get("args", {}))
			response["ok"] = bool(semantic_shape_result.get("ok", false))
			response["result"] = semantic_shape_result
		"scene.assign_visual_resource":
			var semantic_visual_result := _assign_visual_resource(request.get("args", {}))
			response["ok"] = bool(semantic_visual_result.get("ok", false))
			response["result"] = semantic_visual_result
		"scene.create_sprite_frames":
			var semantic_frames_result := _create_sprite_frames(request.get("args", {}))
			response["ok"] = bool(semantic_frames_result.get("ok", false))
			response["result"] = semantic_frames_result
		"project.inspect_resource":
			var semantic_resource_result := _inspect_project_resource(request.get("args", {}))
			response["ok"] = bool(semantic_resource_result.get("ok", false))
			response["result"] = semantic_resource_result
		"editor.open_scene":
			var semantic_open_result := _open_project_scene(request.get("args", {}))
			if not bool(semantic_open_result.get("ok", false)):
				response["ok"] = false
				response["result"] = semantic_open_result
			elif bool(semantic_open_result.get("pending", false)):
				_pending_scene_opens.append({
					"peer": peer,
					"command": command,
					"scene_path": str(semantic_open_result.get("scene_path", "")),
					"deadline_msec": Time.get_ticks_msec() + SCENE_OPEN_TIMEOUT_MS
				})
				return
		"editor.focus_inspector":
			var semantic_focus_result := _focus_inspector(request.get("args", {}))
			response["ok"] = bool(semantic_focus_result.get("ok", false))
			response["result"] = semantic_focus_result
		"editor.inspect_undo_history":
			var semantic_history_result := _inspect_undo_history()
			response["ok"] = bool(semantic_history_result.get("ok", false))
			response["result"] = semantic_history_result
		"editor.undo":
			var semantic_undo_result := _run_bridge_undo_redo("undo")
			response["ok"] = bool(semantic_undo_result.get("ok", false))
			response["result"] = semantic_undo_result
		"editor.redo":
			var semantic_redo_result := _run_bridge_undo_redo("redo")
			response["ok"] = bool(semantic_redo_result.get("ok", false))
			response["result"] = semantic_redo_result
		"editor.inspect_project_settings":
			var semantic_project_settings := _inspect_project_settings()
			response["ok"] = bool(semantic_project_settings.get("ok", false))
			response["result"] = semantic_project_settings
		"editor.inspect_editor_settings":
			var semantic_editor_settings := _inspect_editor_settings()
			response["ok"] = bool(semantic_editor_settings.get("ok", false))
			response["result"] = semantic_editor_settings
		"capture.desktop_screenshot":
			var semantic_desktop_capture := _capture_desktop_screenshot()
			response["ok"] = bool(semantic_desktop_capture.get("ok", false))
			response["result"] = semantic_desktop_capture
		"capture.start_editor_video":
			var semantic_video_start := _start_editor_video(request.get("args", {}))
			response["ok"] = bool(semantic_video_start.get("ok", false))
			response["result"] = semantic_video_start
		"capture.stop_editor_video":
			var semantic_video_stop := _stop_editor_video()
			response["ok"] = bool(semantic_video_stop.get("ok", false))
			response["result"] = semantic_video_stop
		"capture.get_video_status":
			response["result"] = _get_editor_video_status()
		"capture.read_chunk":
			var semantic_chunk := _read_capture_chunk(request.get("args", {}))
			response["ok"] = bool(semantic_chunk.get("ok", false))
			response["result"] = semantic_chunk
		"ping":
			_status_label.text = "Estado: conectado (%d clientes)" % _clients.size()
			response["status"] = "alive"
		"show_test_marker":
			_marker_label.text = "PRUEBA HEADLESS 001 — CAMBIO RECIBIDO"
			_status_label.text = "Estado: orden recibida"
			response["status"] = "marker_visible"
		"clear_test_marker":
			_marker_label.text = ""
			_status_label.text = "Estado: cambio temporal revertido"
			response["status"] = "marker_cleared"
		"preview_status":
			var preview_status_result := _preview_status()
			response["ok"] = bool(preview_status_result.get("ok", false))
			response["result"] = preview_status_result
		"start_preview":
			var preview_start_result := _start_preview(request.get("args", {}))
			response["ok"] = bool(preview_start_result.get("ok", false))
			response["result"] = preview_start_result
		"stop_preview":
			var preview_stop_result := _stop_preview()
			response["ok"] = bool(preview_stop_result.get("ok", false))
			response["result"] = preview_stop_result
		"open_scene":
			var open_result := _open_project_scene(request.get("args", {}))
			if not bool(open_result.get("ok", false)):
				response["ok"] = false
				response["result"] = open_result
			elif bool(open_result.get("pending", false)):
				_pending_scene_opens.append({
					"peer": peer,
					"command": command,
					"scene_path": str(open_result.get("scene_path", "")),
					"deadline_msec": Time.get_ticks_msec() + SCENE_OPEN_TIMEOUT_MS
				})
				return
		"read_capture_chunk":
			var chunk_result := _read_capture_chunk(request.get("args", {}))
			response["ok"] = bool(chunk_result.get("ok", false))
			response["result"] = chunk_result
		"capture_editor_screenshot":
			var capture_result := _capture_editor_screenshot()
			response["ok"] = bool(capture_result.get("ok", false))
			response["result"] = capture_result
		"capture_desktop_screenshot":
			var desktop_capture_result := _capture_desktop_screenshot()
			response["ok"] = bool(desktop_capture_result.get("ok", false))
			response["result"] = desktop_capture_result
		"start_editor_video":
			var video_start_result := _start_editor_video(request.get("args", {}))
			response["ok"] = bool(video_start_result.get("ok", false))
			response["result"] = video_start_result
		"get_editor_video_status":
			var video_status_result := _get_editor_video_status()
			response["result"] = video_status_result
		"stop_editor_video":
			var video_stop_result := _stop_editor_video()
			response["ok"] = bool(video_stop_result.get("ok", false))
			response["result"] = video_stop_result
		"inspect_scene":
			var inspect_result := _inspect_edited_scene()
			response["ok"] = bool(inspect_result.get("ok", false))
			response["result"] = inspect_result
		"inspect_selection":
			var selection_result := _inspect_editor_selection()
			response["ok"] = bool(selection_result.get("ok", false))
			response["result"] = selection_result
		"focus_inspector":
			var focus_result := _focus_inspector(request.get("args", {}))
			response["ok"] = bool(focus_result.get("ok", false))
			response["result"] = focus_result
		"inspect_undo_history":
			var undo_result := _inspect_undo_history()
			response["ok"] = bool(undo_result.get("ok", false))
			response["result"] = undo_result
		"undo_bridge_action":
			var undo_action_result := _run_bridge_undo_redo("undo")
			response["ok"] = bool(undo_action_result.get("ok", false))
			response["result"] = undo_action_result
		"redo_bridge_action":
			var redo_action_result := _run_bridge_undo_redo("redo")
			response["ok"] = bool(redo_action_result.get("ok", false))
			response["result"] = redo_action_result
		"inspect_project_settings":
			var settings_result := _inspect_project_settings()
			response["ok"] = bool(settings_result.get("ok", false))
			response["result"] = settings_result
		"inspect_editor_settings":
			var editor_settings_result := _inspect_editor_settings()
			response["ok"] = bool(editor_settings_result.get("ok", false))
			response["result"] = editor_settings_result
		"inspect_resource":
			var resource_result := _inspect_project_resource(request.get("args", {}))
			response["ok"] = bool(resource_result.get("ok", false))
			response["result"] = resource_result
		"list_project_resources":
			var resources_result := _list_project_resources()
			response["ok"] = bool(resources_result.get("ok", false))
			response["result"] = resources_result
		"add_node":
			var result := _add_node_to_edited_scene(request.get("args", {}))
			response["ok"] = bool(result.get("ok", false))
			response["result"] = result
		"set_node_properties":
			var property_result := _set_node_properties(request.get("args", {}))
			response["ok"] = bool(property_result.get("ok", false))
			response["result"] = property_result
		"configure_collision_shape":
			var shape_result := _configure_collision_shape(request.get("args", {}))
			response["ok"] = bool(shape_result.get("ok", false))
			response["result"] = shape_result
		"create_sprite_frames":
			var frames_result := _create_sprite_frames(request.get("args", {}))
			response["ok"] = bool(frames_result.get("ok", false))
			response["result"] = frames_result
		"assign_visual_resource":
			var visual_result := _assign_visual_resource(request.get("args", {}))
			response["ok"] = bool(visual_result.get("ok", false))
			response["result"] = visual_result
		_:
			response = {"ok": false, "error": "command_not_allowed"}
	_send_response(peer, response)


func _send_response(peer: StreamPeerTCP, payload: Dictionary) -> void:
	if peer != null and peer.get_status() == StreamPeerTCP.STATUS_CONNECTED:
		peer.put_data((JSON.stringify(payload) + "\n").to_utf8_buffer())


func _write_registry() -> void:
	var file := FileAccess.open(REGISTRY_PATH, FileAccess.WRITE)
	if file == null:
		push_error("Headless bridge could not write discovery registry.")
		return
	file.store_string(JSON.stringify({
		"protocol": PROTOCOL_VERSION,
		"port": BRIDGE_PORT,
		"token": _token,
		"project_id": _project_id,
		"project_path": ProjectSettings.globalize_path("res://").simplify_path(),
		"editor_pid": OS.get_process_id()
	}))
	file.close()


func _remove_own_registry() -> void:
	if not FileAccess.file_exists(REGISTRY_PATH):
		return
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(REGISTRY_PATH))
	if data is Dictionary and str(data.get("token", "")) == _token:
		DirAccess.remove_absolute(_registry_absolute_path)


func _announce_when_ready() -> void:
	await get_tree().create_timer(2.5).timeout
	if is_inside_tree() and _server != null and _server.is_listening():
		_write_registry()


const ALLOWED_NODE_TYPES := [
	"Node2D", "Control", "Sprite2D", "AnimatedSprite2D", "Label",
	"RichTextLabel", "ColorRect", "Panel", "Button", "TextureRect",
	"Marker2D", "Area2D", "StaticBody2D", "CharacterBody2D",
	"RigidBody2D", "AnimatableBody2D", "CollisionShape2D",
	"CollisionPolygon2D", "RayCast2D", "ShapeCast2D"
]
const MAX_INSPECTED_NODES := 200
const MAX_RESOURCE_ENTRIES := 300


func _inspect_project_resource(raw_args: Variant) -> Dictionary:
	if not raw_args is Dictionary:
		return {"ok": false, "error": "invalid_arguments"}
	var resource_path := str(raw_args.get("path", ""))
	if not resource_path.begins_with("res://") or resource_path.contains("..") or resource_path.contains("\\"):
		return {"ok": false, "error": "invalid_resource_path"}
	if not ResourceLoader.exists(resource_path):
		return {"ok": false, "error": "resource_not_found", "path": resource_path}
	var resource: Resource = ResourceLoader.load(resource_path)
	if resource == null:
		return {"ok": false, "error": "resource_load_failed", "path": resource_path}
	return {
		"ok": true,
		"path": resource_path,
		"type": resource.get_class(),
		"resource_name": resource.resource_name,
		"resource_local_to_scene": resource.resource_local_to_scene,
		"inspector": _inspect_object_inspector(resource)
	}


const MAX_PROJECT_SETTINGS := 250
const PROJECT_SETTING_PREFIXES := [
	"application/", "display/", "rendering/", "physics/",
	"input/", "input_devices/", "audio/", "gui/"
]


func _inspect_project_settings() -> Dictionary:
	var entries: Array[Dictionary] = []
	var truncated := false
	for info in ProjectSettings.get_property_list():
		var setting_name := str(info.get("name", ""))
		var include_setting := false
		for prefix in PROJECT_SETTING_PREFIXES:
			if setting_name.begins_with(prefix):
				include_setting = true
				break
		if not include_setting:
			continue
		var usage := int(info.get("usage", 0))
		if (usage & PROPERTY_USAGE_SECRET) != 0 or (usage & PROPERTY_USAGE_INTERNAL) != 0:
			continue
		if entries.size() >= MAX_PROJECT_SETTINGS:
			truncated = true
			break
		var value: Variant = ProjectSettings.get_setting(setting_name)
		entries.append({
			"name": setting_name,
			"type": type_string(int(info.get("type", TYPE_NIL))),
			"hint": int(info.get("hint", PROPERTY_HINT_NONE)),
			"hint_string": _bounded_inspector_string(str(info.get("hint_string", ""))),
			"usage": usage,
			"editable": (usage & PROPERTY_USAGE_READ_ONLY) == 0,
			"value": _serialize_inspector_value(value)
		})
	return {
		"ok": true,
		"settings": entries,
		"count": entries.size(),
		"truncated": truncated,
		"scope": PROJECT_SETTING_PREFIXES
	}


const MAX_EDITOR_SETTINGS := 180
const EDITOR_SETTING_PREFIXES := [
	"interface/", "text_editor/", "docks/", "filesystem/"
]


func _inspect_editor_settings() -> Dictionary:
	var editor_settings := EditorInterface.get_editor_settings()
	if editor_settings == null:
		return {"ok": false, "error": "editor_settings_unavailable"}
	var entries: Array[Dictionary] = []
	var truncated := false
	for info in editor_settings.get_property_list():
		var setting_name := str(info.get("name", ""))
		var include_setting := false
		for prefix in EDITOR_SETTING_PREFIXES:
			if setting_name.begins_with(prefix):
				include_setting = true
				break
		if not include_setting:
			continue
		var usage := int(info.get("usage", 0))
		if (usage & PROPERTY_USAGE_SECRET) != 0 or (usage & PROPERTY_USAGE_INTERNAL) != 0:
			continue
		if entries.size() >= MAX_EDITOR_SETTINGS:
			truncated = true
			break
		var value: Variant = editor_settings.get_setting(setting_name)
		entries.append({
			"name": setting_name,
			"type": type_string(int(info.get("type", TYPE_NIL))),
			"hint": int(info.get("hint", PROPERTY_HINT_NONE)),
			"hint_string": _bounded_inspector_string(str(info.get("hint_string", ""))),
			"usage": usage,
			"editable": (usage & PROPERTY_USAGE_READ_ONLY) == 0,
			"value": _serialize_inspector_value(value)
		})
	return {
		"ok": true,
		"settings": entries,
		"count": entries.size(),
		"truncated": truncated,
		"scope": EDITOR_SETTING_PREFIXES,
		"warning": "These preferences belong to the editor installation, not the project."
	}


func _inspect_undo_history() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return {"ok": false, "error": "no_edited_scene"}
	var manager := EditorInterface.get_editor_undo_redo()
	if manager == null:
		return {"ok": false, "error": "undo_manager_unavailable"}
	var history_id := manager.get_object_history_id(root)
	var history: UndoRedo = manager.get_history_undo_redo(history_id)
	if history == null:
		return {"ok": false, "error": "scene_undo_history_unavailable"}
	return {
		"ok": true,
		"history_id": history_id,
		"history_count": history.get_history_count(),
		"has_undo": history.has_undo(),
		"has_redo": history.has_redo(),
		"current_action": history.get_current_action(),
		"current_action_name": history.get_current_action_name(),
		"version": history.get_version()
	}


func _run_bridge_undo_redo(direction: String) -> Dictionary:
	if direction not in ["undo", "redo"]:
		return {"ok": false, "error": "invalid_undo_redo_direction"}
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return {"ok": false, "error": "no_edited_scene"}
	var manager := EditorInterface.get_editor_undo_redo()
	if manager == null:
		return {"ok": false, "error": "undo_manager_unavailable"}
	var history_id := manager.get_object_history_id(root)
	var history: UndoRedo = manager.get_history_undo_redo(history_id)
	if history == null:
		return {"ok": false, "error": "scene_undo_history_unavailable"}
	var action_index := int(history.get_current_action())
	if direction == "undo":
		if not history.has_undo():
			return {"ok": false, "error": "nothing_to_undo"}
	else:
		if not history.has_redo():
			return {"ok": false, "error": "nothing_to_redo"}
		action_index += 1
	if action_index < 0 or action_index >= history.get_history_count():
		return {"ok": false, "error": "undo_action_index_invalid"}
	var action_name := history.get_action_name(action_index)
	if not action_name.begins_with("Headless Bridge:"):
		return {"ok": false, "error": "action_not_owned_by_bridge", "action_name": action_name, "direction": direction}
	var version_before := history.get_version()
	if direction == "undo":
		history.undo()
	else:
		history.redo()
	return {
		"ok": true,
		"direction": direction,
		"action_name": action_name,
		"history_id": history_id,
		"version_before": version_before,
		"version_after": history.get_version(),
		"has_undo": history.has_undo(),
		"has_redo": history.has_redo(),
		"current_action": history.get_current_action(),
		"current_action_name": history.get_current_action_name()
	}


func _focus_inspector(raw_args: Variant) -> Dictionary:
	if not raw_args is Dictionary:
		return {"ok": false, "error": "invalid_args"}
	var args: Dictionary = raw_args
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return {"ok": false, "error": "no_edited_scene"}
	var node_path := str(args.get("node_path", "."))
	if node_path.begins_with("/") or node_path == ".." or node_path.contains("../") or node_path.contains("/.."):
		return {"ok": false, "error": "invalid_node_path"}
	var node: Node = root if node_path.is_empty() or node_path == "." else root.get_node_or_null(NodePath(node_path))
	if node == null:
		return {"ok": false, "error": "node_not_found"}
	var main_screen := str(args.get("main_screen", ""))
	if not main_screen.is_empty():
		if main_screen not in ["2D", "3D", "Script", "AssetLib"]:
			return {"ok": false, "error": "main_screen_not_allowed"}
		EditorInterface.set_main_screen_editor(main_screen)
	var editor_selection := EditorInterface.get_selection()
	if editor_selection == null:
		return {"ok": false, "error": "editor_selection_unavailable"}
	EditorInterface.distraction_free_mode = false
	editor_selection.clear()
	editor_selection.add_node(node)
	EditorInterface.inspect_object(node)
	var inspector := EditorInterface.get_inspector()
	if inspector == null:
		return {"ok": false, "error": "editor_inspector_unavailable"}
	var current: Node = inspector
	var dock_name := ""
	var dock_visible := false
	var dock_size := Vector2.ZERO
	var dock_rect := Rect2()
	var ancestors: Array[Dictionary] = []
	while current != null:
		var ancestor := {"name": str(current.name), "type": current.get_class()}
		if current is Control:
			ancestor["visible"] = current.visible
			ancestor["visible_in_tree"] = current.is_visible_in_tree()
			ancestor["size"] = {"x": current.size.x, "y": current.size.y}
		ancestors.append(ancestor)
		if current.has_method("make_visible"):
			current.call("make_visible")
			dock_name = str(current.name)
			dock_visible = current.is_visible_in_tree()
			if current is Control:
				dock_size = current.size
				dock_rect = current.get_global_rect()
			break
		current = current.get_parent()
	var base_control := EditorInterface.get_base_control()
	var inspector_window := inspector.get_window()
	return {
		"ok": true,
		"node_path": str(root.get_path_to(node)),
		"node_type": node.get_class(),
		"main_screen": main_screen,
		"distraction_free_mode": EditorInterface.distraction_free_mode,
		"base_size": {"x": base_control.size.x, "y": base_control.size.y},
		"base_global_rect": {"x": base_control.get_global_rect().position.x, "y": base_control.get_global_rect().position.y, "width": base_control.get_global_rect().size.x, "height": base_control.get_global_rect().size.y},
		"inspector_global_rect": {"x": inspector.get_global_rect().position.x, "y": inspector.get_global_rect().position.y, "width": inspector.get_global_rect().size.x, "height": inspector.get_global_rect().size.y},
		"dock_global_rect": {"x": dock_rect.position.x, "y": dock_rect.position.y, "width": dock_rect.size.x, "height": dock_rect.size.y},
		"multi_window_enabled": EditorInterface.is_multi_window_enabled(),
		"inspector_window_title": inspector_window.title,
		"inspector_window_visible": inspector_window.visible,
		"inspector_window_position": {"x": inspector_window.position.x, "y": inspector_window.position.y},
		"inspector_window_size": {"x": inspector_window.size.x, "y": inspector_window.size.y},
		"inspector_visible": inspector.is_visible_in_tree(),
		"inspector_size": {"x": inspector.size.x, "y": inspector.size.y},
		"inspector_dock": dock_name,
		"dock_visible": dock_visible,
		"dock_size": {"x": dock_size.x, "y": dock_size.y},
		"ancestors": ancestors
	}


func _inspect_editor_selection() -> Dictionary:
	var editor_selection := EditorInterface.get_selection()
	if editor_selection == null:
		return {"ok": false, "error": "editor_selection_unavailable"}
	var selected_nodes: Array = editor_selection.get_selected_nodes()
	var entries: Array[Dictionary] = []
	for node in selected_nodes:
		if not is_instance_valid(node):
			continue
		entries.append({
			"name": str(node.name),
			"type": node.get_class(),
			"path": str(node.get_path()),
			"inspector": _inspect_object_inspector(node)
		})
	return {
		"ok": true,
		"selected_count": entries.size(),
		"selection": entries
	}


func _inspect_edited_scene() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return {"ok": false, "error": "no_edited_scene"}
	var budget := {"remaining": MAX_INSPECTED_NODES}
	return {
		"ok": true,
		"scene_path": root.scene_file_path,
		"root": _serialize_node(root, root, 0, budget),
		"truncated": int(budget["remaining"]) <= 0
	}


func _serialize_node(node: Node, scene_root: Node, depth: int, budget: Dictionary) -> Dictionary:
	if int(budget["remaining"]) <= 0:
		return {"truncated": true}
	budget["remaining"] = int(budget["remaining"]) - 1
	var result := {
		"name": str(node.name),
		"type": node.get_class(),
		# "path" is stable within the edited scene; runtime_path is diagnostic
		# context from the editor's own scene tree and must not be used as an edit target.
		"path": str(scene_root.get_path_to(node)),
		"runtime_path": str(node.get_path()),
		"groups": _get_group_names(node),
		"child_count": node.get_child_count(),
		"properties": _inspect_node_properties(node),
		# Dynamic Inspector metadata is read-only discovery. Editing remains
		# restricted to explicit, typed commands with undo support.
		"inspector": _inspect_object_inspector(node),
		"children": []
	}
	if depth >= 8:
		result["truncated"] = node.get_child_count() > 0
		return result
	var children: Array = []
	for child in node.get_children():
		if int(budget["remaining"]) <= 0:
			break
		children.append(_serialize_node(child, scene_root, depth + 1, budget))
	result["children"] = children
	if children.size() < node.get_child_count():
		result["truncated"] = true
	return result


func _inspect_node_properties(node: Node) -> Dictionary:
	# Deliberately expose a typed, bounded property schema rather than every
	# Object property. This gives the operator enough information to reason
	# about transforms and 2D collision setup without leaking editor internals.
	var properties: Dictionary = {}
	if node is Node2D:
		var node_2d := node as Node2D
		properties["position"] = _vector2_to_json(node_2d.position)
		properties["rotation_degrees"] = node_2d.rotation_degrees
		properties["scale"] = _vector2_to_json(node_2d.scale)
		properties["z_index"] = node_2d.z_index
		properties["visible"] = node_2d.visible
	if node is CollisionObject2D:
		var collision_object := node as CollisionObject2D
		properties["collision_layer"] = collision_object.collision_layer
		properties["collision_mask"] = collision_object.collision_mask
		properties["input_pickable"] = collision_object.input_pickable
	if node is Area2D:
		var area := node as Area2D
		properties["monitoring"] = area.monitoring
		properties["monitorable"] = area.monitorable
	if node is CharacterBody2D:
		var character_body := node as CharacterBody2D
		properties["velocity"] = _vector2_to_json(character_body.velocity)
		properties["up_direction"] = _vector2_to_json(character_body.up_direction)
		properties["motion_mode"] = character_body.motion_mode
		properties["floor_max_angle"] = character_body.floor_max_angle
	if node is RayCast2D:
		var ray_cast := node as RayCast2D
		properties["enabled"] = ray_cast.enabled
		properties["target_position"] = _vector2_to_json(ray_cast.target_position)
		properties["collide_with_areas"] = ray_cast.collide_with_areas
		properties["collide_with_bodies"] = ray_cast.collide_with_bodies
	if node is ShapeCast2D:
		var shape_cast := node as ShapeCast2D
		properties["enabled"] = shape_cast.enabled
		properties["target_position"] = _vector2_to_json(shape_cast.target_position)
		properties["collide_with_areas"] = shape_cast.collide_with_areas
		properties["collide_with_bodies"] = shape_cast.collide_with_bodies
		properties["shape"] = _inspect_shape_resource(shape_cast.shape)
	if node is CollisionPolygon2D:
		var collision_polygon := node as CollisionPolygon2D
		properties["disabled"] = collision_polygon.disabled
		properties["polygon_point_count"] = collision_polygon.polygon.size()
	if node is CollisionShape2D:
		var collision_shape := node as CollisionShape2D
		properties["disabled"] = collision_shape.disabled
		properties["one_way_collision"] = collision_shape.one_way_collision
		properties["shape"] = _inspect_shape_resource(collision_shape.shape)
	return properties


const MAX_INSPECTOR_PROPERTIES := 120
const MAX_INSPECTOR_STRING_LENGTH := 512
const INSPECTOR_EXCLUDED_USAGE := PROPERTY_USAGE_INTERNAL | PROPERTY_USAGE_SECRET


func _inspect_object_inspector(object: Object) -> Dictionary:
	var properties: Array[Dictionary] = []
	var property_list := object.get_property_list()
	var truncated := false
	for info in property_list:
		var usage := int(info.get("usage", 0))
		var property_name := str(info.get("name", ""))
		if property_name.is_empty() or (usage & INSPECTOR_EXCLUDED_USAGE) != 0:
			continue
		# Keep editor-visible fields and script variables. Do not expose
		# storage-only implementation details or internal engine state.
		if (usage & PROPERTY_USAGE_EDITOR) == 0 and (usage & PROPERTY_USAGE_SCRIPT_VARIABLE) == 0:
			continue
		if (usage & PROPERTY_USAGE_CATEGORY) != 0 or (usage & PROPERTY_USAGE_GROUP) != 0 or (usage & PROPERTY_USAGE_SUBGROUP) != 0:
			properties.append({
				"name": property_name,
				"kind": "section",
				"usage": usage
			})
			continue
		if properties.size() >= MAX_INSPECTOR_PROPERTIES:
			truncated = true
			break
		var property_type := int(info.get("type", TYPE_NIL))
		var entry := {
			"name": property_name,
			"type": type_string(property_type),
			"type_id": property_type,
			"hint": int(info.get("hint", PROPERTY_HINT_NONE)),
			"hint_string": _bounded_inspector_string(str(info.get("hint_string", ""))),
			"usage": usage,
			"editable": (usage & PROPERTY_USAGE_READ_ONLY) == 0,
			"value": _serialize_inspector_value(object.get(property_name))
		}
		if info.has("class_name"):
			entry["class_name"] = str(info.get("class_name", ""))
		properties.append(entry)
	return {
		"object_class": object.get_class(),
		"property_count": properties.size(),
		"properties": properties,
		"truncated": truncated
	}


func _bounded_inspector_string(value: String) -> String:
	if value.length() > MAX_INSPECTOR_STRING_LENGTH:
		return value.substr(0, MAX_INSPECTOR_STRING_LENGTH) + "…"
	return value


func _serialize_inspector_value(value: Variant) -> Variant:
	match typeof(value):
		TYPE_NIL, TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_STRING:
			if value is String:
				return _bounded_inspector_string(value)
			return value
		TYPE_VECTOR2:
			return {"x": value.x, "y": value.y}
		TYPE_VECTOR2I:
			return {"x": value.x, "y": value.y}
		TYPE_VECTOR3:
			return {"x": value.x, "y": value.y, "z": value.z}
		TYPE_VECTOR3I:
			return {"x": value.x, "y": value.y, "z": value.z}
		TYPE_COLOR:
			return {"r": value.r, "g": value.g, "b": value.b, "a": value.a}
		TYPE_RECT2:
			return {"position": {"x": value.position.x, "y": value.position.y}, "size": {"x": value.size.x, "y": value.size.y}}
		TYPE_RECT2I:
			return {"position": {"x": value.position.x, "y": value.position.y}, "size": {"x": value.size.x, "y": value.size.y}}
		TYPE_NODE_PATH:
			return str(value)
		TYPE_STRING_NAME:
			return str(value)
		TYPE_ARRAY:
			var items: Array = []
			for index in range(min(value.size(), 32)):
				var item: Variant = value[index]
				if typeof(item) in [TYPE_NIL, TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_STRING, TYPE_VECTOR2, TYPE_VECTOR2I, TYPE_VECTOR3, TYPE_VECTOR3I, TYPE_COLOR, TYPE_NODE_PATH, TYPE_STRING_NAME]:
					items.append(_serialize_inspector_value(item))
				else:
					items.append({"type": type_string(typeof(item)), "summary": "complex_value"})
			return {"items": items, "size": value.size(), "truncated": value.size() > items.size()}
		TYPE_DICTIONARY:
			return {"size": value.size(), "summary": "dictionary_not_expanded"}
		TYPE_OBJECT:
			if value == null:
				return null
			if value is Resource:
				var resource := value as Resource
				return {
					"type": resource.get_class(),
					"resource_path": resource.resource_path,
					"local_to_scene": resource.resource_local_to_scene
				}
			return {"type": value.get_class(), "summary": "object_reference"}
		_:
			return {"type": type_string(typeof(value)), "summary": "not_serialized"}


func _inspect_shape_resource(shape: Shape2D) -> Dictionary:
	if shape == null:
		return {"assigned": false}
	var result := {"assigned": true, "type": shape.get_class()}
	var available_properties: Dictionary = {}
	for property_info in shape.get_property_list():
		available_properties[str(property_info.get("name", ""))] = true
	for property_name in ["radius", "height", "size", "a", "b", "extents"]:
		if not available_properties.has(property_name):
			continue
		var value: Variant = shape.get(property_name)
		if value is Vector2:
			result[property_name] = _vector2_to_json(value)
		elif value is float or value is int:
			result[property_name] = value
	return result


func _get_group_names(node: Node) -> Array[String]:
	var names: Array[String] = []
	for group_name in node.get_groups():
		names.append(str(group_name))
	return names


func _vector2_to_json(value: Vector2) -> Dictionary:
	return {"x": value.x, "y": value.y}


func _list_project_resources() -> Dictionary:
	var entries: Array[String] = []
	_collect_resources("res://", entries)
	return {"ok": true, "entries": entries, "truncated": entries.size() >= MAX_RESOURCE_ENTRIES}


func _collect_resources(path: String, entries: Array[String]) -> void:
	if entries.size() >= MAX_RESOURCE_ENTRIES:
		return
	var directory := DirAccess.open(path)
	if directory == null:
		return
	directory.list_dir_begin()
	var item := directory.get_next()
	while not item.is_empty() and entries.size() < MAX_RESOURCE_ENTRIES:
		if item.begins_with("."):
			item = directory.get_next()
			continue
		var child_path := path.path_join(item)
		if directory.current_is_dir():
			_collect_resources(child_path, entries)
		elif item.get_extension().to_lower() in ["tscn", "tres", "gd", "png", "webp", "svg", "ogg", "wav", "json"]:
			entries.append(child_path)
		item = directory.get_next()
	directory.list_dir_end()


func _add_node_to_edited_scene(raw_args: Variant) -> Dictionary:
	if not raw_args is Dictionary:
		return {"ok": false, "error": "invalid_args"}
	var args: Dictionary = raw_args
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return {"ok": false, "error": "no_edited_scene"}
	var type_name := str(args.get("type", ""))
	if type_name not in ALLOWED_NODE_TYPES:
		return {"ok": false, "error": "node_type_not_allowed"}
	var parent_path := str(args.get("parent_path", ""))
	if parent_path.begins_with("/") or parent_path.contains(".."):
		return {"ok": false, "error": "invalid_parent_path"}
	var parent: Node = root if parent_path.is_empty() else root.get_node_or_null(NodePath(parent_path))
	if parent == null:
		return {"ok": false, "error": "parent_not_found"}
	if type_name in ["CollisionShape2D", "CollisionPolygon2D"] and not parent is CollisionObject2D:
		return {"ok": false, "error": "collision_shape_parent_must_be_collision_object"}
	var node_name := str(args.get("name", type_name))
	if node_name.is_empty() or node_name.contains("/") or node_name.contains(":") or node_name == "." or node_name == "..":
		return {"ok": false, "error": "invalid_node_name"}
	var instance := ClassDB.instantiate(type_name)
	if not instance is Node:
		return {"ok": false, "error": "node_creation_failed"}
	var new_node: Node = instance
	new_node.name = node_name
	var undo_redo := get_undo_redo()
	undo_redo.create_action("Headless Bridge: Add " + node_name)
	undo_redo.add_do_method(parent, "add_child", new_node)
	undo_redo.add_do_method(new_node, "set_owner", root)
	undo_redo.add_undo_method(parent, "remove_child", new_node)
	undo_redo.add_undo_method(new_node, "set_owner", null)
	undo_redo.commit_action()
	return {"ok": true, "node_path": str(root.get_path_to(new_node)), "type": type_name, "name": node_name}



const COLLISION_SHAPE_TYPES := ["CircleShape2D", "RectangleShape2D", "CapsuleShape2D", "SegmentShape2D"]


func _create_sprite_frames(raw_args: Variant) -> Dictionary:
	if not raw_args is Dictionary:
		return {"ok": false, "error": "invalid_args"}
	var args: Dictionary = raw_args
	var resource_path := str(args.get("path", ""))
	if not resource_path.begins_with("res://") or resource_path.contains("..") or resource_path.contains("\\") or not resource_path.ends_with(".tres"):
		return {"ok": false, "error": "invalid_sprite_frames_path"}
	if ResourceLoader.exists(resource_path) or FileAccess.file_exists(resource_path):
		return {"ok": false, "error": "resource_already_exists", "path": resource_path}
	var directory_path := ProjectSettings.globalize_path(resource_path).get_base_dir()
	if not DirAccess.dir_exists_absolute(directory_path):
		var directory_error := DirAccess.make_dir_recursive_absolute(directory_path)
		if directory_error != OK and not DirAccess.dir_exists_absolute(directory_path):
			return {"ok": false, "error": "resource_directory_create_failed", "code": directory_error}
	var raw_animations: Variant = args.get("animations", [])
	if not raw_animations is Array or raw_animations.is_empty() or raw_animations.size() > 32:
		return {"ok": false, "error": "animations_required_or_limit_exceeded"}
	var prepared: Array[Dictionary] = []
	var animation_names: Array[String] = []
	var total_frames := 0
	for raw_animation in raw_animations:
		if not raw_animation is Dictionary:
			return {"ok": false, "error": "invalid_animation_definition"}
		var animation_name := str(raw_animation.get("name", ""))
		if not animation_name.is_valid_identifier() or animation_name == "default" or animation_name in animation_names:
			return {"ok": false, "error": "invalid_or_duplicate_animation_name", "name": animation_name}
		var speed := float(raw_animation.get("speed", 8.0))
		if not is_finite(speed) or speed < 0.1 or speed > 120.0:
			return {"ok": false, "error": "invalid_animation_speed", "name": animation_name}
		var raw_frames: Variant = raw_animation.get("frames", [])
		if not raw_frames is Array or raw_frames.is_empty() or raw_frames.size() > 120:
			return {"ok": false, "error": "animation_frames_required_or_limit_exceeded", "name": animation_name}
		var frames: Array[Dictionary] = []
		for raw_frame in raw_frames:
			if not raw_frame is Dictionary:
				return {"ok": false, "error": "invalid_frame_definition", "name": animation_name}
			var texture_path := str(raw_frame.get("texture_path", ""))
			if not texture_path.begins_with("res://") or texture_path.contains("..") or texture_path.contains("\\") or not ResourceLoader.exists(texture_path):
				return {"ok": false, "error": "frame_texture_not_found_or_invalid", "path": texture_path}
			var texture: Resource = ResourceLoader.load(texture_path)
			if not texture is Texture2D:
				return {"ok": false, "error": "frame_texture_required", "path": texture_path}
			var duration := float(raw_frame.get("duration", 1.0))
			if not is_finite(duration) or duration <= 0.0 or duration > 60.0:
				return {"ok": false, "error": "invalid_frame_duration", "path": texture_path}
			frames.append({"texture": texture, "texture_path": texture_path, "duration": duration})
		total_frames += frames.size()
		if total_frames > 500:
			return {"ok": false, "error": "total_frame_limit_exceeded"}
		animation_names.append(animation_name)
		prepared.append({"name": animation_name, "speed": speed, "loop": bool(raw_animation.get("loop", true)), "frames": frames})
	var sprite_frames := SpriteFrames.new()
	if sprite_frames.has_animation("default"):
		sprite_frames.remove_animation("default")
	for animation in prepared:
		var animation_name := str(animation["name"])
		sprite_frames.add_animation(animation_name)
		sprite_frames.set_animation_speed(animation_name, float(animation["speed"]))
		sprite_frames.set_animation_loop(animation_name, bool(animation["loop"]))
		for frame in animation["frames"]:
			sprite_frames.add_frame(animation_name, frame["texture"], float(frame["duration"]))
	var save_error := ResourceSaver.save(sprite_frames, resource_path)
	if save_error != OK:
		return {"ok": false, "error": "sprite_frames_save_failed", "code": save_error}
	return {"ok": true, "path": resource_path, "type": "SpriteFrames", "animation_count": prepared.size(), "frame_count": total_frames, "animations": animation_names}


func _assign_visual_resource(raw_args: Variant) -> Dictionary:
	if not raw_args is Dictionary:
		return {"ok": false, "error": "invalid_args"}
	var args: Dictionary = raw_args
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return {"ok": false, "error": "no_edited_scene"}
	var node_path := str(args.get("node_path", ""))
	if node_path.begins_with("/") or node_path == ".." or node_path.contains("../") or node_path.contains("/..") or node_path.contains("\\"):
		return {"ok": false, "error": "invalid_node_path"}
	var node: Node = root if node_path.is_empty() or node_path == "." else root.get_node_or_null(NodePath(node_path))
	if node == null:
		return {"ok": false, "error": "node_not_found"}
	var property_name := str(args.get("property", ""))
	var expected_class := ""
	if property_name == "texture" and (node is Sprite2D or node is TextureRect):
		expected_class = "Texture2D"
	elif property_name == "sprite_frames" and node is AnimatedSprite2D:
		expected_class = "SpriteFrames"
	else:
		return {"ok": false, "error": "visual_resource_target_not_allowed"}
	var resource_path := str(args.get("resource_path", ""))
	if not resource_path.begins_with("res://") or resource_path.contains("..") or resource_path.contains("\\"):
		return {"ok": false, "error": "invalid_resource_path"}
	if not ResourceLoader.exists(resource_path):
		return {"ok": false, "error": "resource_not_found", "path": resource_path}
	var resource: Resource = ResourceLoader.load(resource_path)
	if resource == null:
		return {"ok": false, "error": "resource_load_failed", "path": resource_path}
	if expected_class == "Texture2D" and not resource is Texture2D:
		return {"ok": false, "error": "texture_resource_required", "actual_type": resource.get_class()}
	if expected_class == "SpriteFrames" and not resource is SpriteFrames:
		return {"ok": false, "error": "sprite_frames_resource_required", "actual_type": resource.get_class()}
	var previous: Resource = node.get(property_name)
	var undo_redo := get_undo_redo()
	undo_redo.create_action("Headless Bridge: Assign " + property_name + " to " + str(node.name))
	undo_redo.add_do_property(node, property_name, resource)
	undo_redo.add_undo_property(node, property_name, previous)
	undo_redo.commit_action()
	return {
		"ok": true,
		"node_path": str(root.get_path_to(node)),
		"property": property_name,
		"resource_path": resource_path,
		"resource_type": resource.get_class(),
		"previous_resource_path": previous.resource_path if previous != null else ""
	}


func _configure_collision_shape(raw_args: Variant) -> Dictionary:
	if not raw_args is Dictionary:
		return {"ok": false, "error": "invalid_args"}
	var args: Dictionary = raw_args
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return {"ok": false, "error": "no_edited_scene"}
	var node_path := str(args.get("node_path", ""))
	if node_path.begins_with("/") or node_path == ".." or node_path.contains("../") or node_path.contains("/.."):
		return {"ok": false, "error": "invalid_node_path"}
	var node: Node = root if node_path.is_empty() or node_path == "." else root.get_node_or_null(NodePath(node_path))
	if not node is CollisionShape2D:
		return {"ok": false, "error": "collision_shape_node_required"}
	var shape_type := str(args.get("shape_type", ""))
	if shape_type not in COLLISION_SHAPE_TYPES:
		return {"ok": false, "error": "shape_type_not_allowed"}
	var raw_dimensions: Variant = args.get("dimensions", {})
	if not raw_dimensions is Dictionary:
		return {"ok": false, "error": "dimensions_required"}
	var expected_dimensions: Array = []
	match shape_type:
		"CircleShape2D":
			expected_dimensions = ["radius"]
		"RectangleShape2D":
			expected_dimensions = ["size"]
		"CapsuleShape2D":
			expected_dimensions = ["radius", "height"]
		"SegmentShape2D":
			expected_dimensions = ["a", "b"]
	for dimension_name in raw_dimensions:
		if str(dimension_name) not in expected_dimensions:
			return {"ok": false, "error": "dimension_not_allowed", "dimension": str(dimension_name)}
	var shape := ClassDB.instantiate(shape_type) as Shape2D
	if shape == null:
		return {"ok": false, "error": "shape_creation_failed"}
	shape.resource_local_to_scene = true
	var dimension_error := _apply_shape_dimensions(shape, shape_type, raw_dimensions)
	if not dimension_error.is_empty():
		return {"ok": false, "error": dimension_error}
	var undo_redo := get_undo_redo()
	undo_redo.create_action("Headless Bridge: Configure collision shape " + str(node.name))
	undo_redo.add_do_property(node, "shape", shape)
	undo_redo.add_undo_property(node, "shape", node.shape)
	undo_redo.commit_action()
	return {"ok": true, "node_path": str(root.get_path_to(node)), "shape": _inspect_shape_resource(shape)}


func _apply_shape_dimensions(shape: Shape2D, shape_type: String, dimensions: Dictionary) -> String:
	match shape_type:
		"CircleShape2D":
			if not dimensions.has("radius"):
				return "radius_required"
			var radius := float(dimensions["radius"])
			if not is_finite(radius) or radius <= 0.0 or radius > 1000000.0:
				return "invalid_radius"
			(shape as CircleShape2D).radius = radius
		"RectangleShape2D":
			if not dimensions.has("size"):
				return "size_required"
			var size := _parse_bounded_vector2(dimensions["size"])
			if size == null or size.x <= 0.0 or size.y <= 0.0:
				return "invalid_size"
			(shape as RectangleShape2D).size = size
		"CapsuleShape2D":
			if not dimensions.has("radius") or not dimensions.has("height"):
				return "radius_and_height_required"
			var capsule_radius := float(dimensions["radius"])
			var capsule_height := float(dimensions["height"])
			if not is_finite(capsule_radius) or not is_finite(capsule_height) or capsule_radius <= 0.0 or capsule_radius > 500000.0 or capsule_height < capsule_radius * 2.0 or capsule_height > 1000000.0:
				return "invalid_capsule_dimensions"
			(shape as CapsuleShape2D).radius = capsule_radius
			(shape as CapsuleShape2D).height = capsule_height
		"SegmentShape2D":
			if not dimensions.has("a") or not dimensions.has("b"):
				return "segment_points_required"
			var point_a := _parse_bounded_vector2(dimensions["a"])
			var point_b := _parse_bounded_vector2(dimensions["b"])
			if point_a == null or point_b == null or point_a.is_equal_approx(point_b):
				return "invalid_segment_points"
			(shape as SegmentShape2D).a = point_a
			(shape as SegmentShape2D).b = point_b
	return ""


func _parse_bounded_vector2(raw_value: Variant) -> Variant:
	if not raw_value is Dictionary or not raw_value.has("x") or not raw_value.has("y"):
		return null
	var x := float(raw_value["x"])
	var y := float(raw_value["y"])
	if not is_finite(x) or not is_finite(y) or absf(x) > 1000000.0 or absf(y) > 1000000.0:
		return null
	return Vector2(x, y)


const NODE_PROPERTY_ALLOWLIST := {
	"Node2D": ["position", "rotation_degrees", "scale", "z_index", "visible"],
	"CollisionObject2D": ["collision_layer", "collision_mask", "input_pickable"],
	"Area2D": ["monitoring", "monitorable"],
	"CharacterBody2D": ["up_direction", "motion_mode", "floor_max_angle"],
	"RayCast2D": ["enabled", "target_position", "collide_with_areas", "collide_with_bodies"],
	"ShapeCast2D": ["enabled", "target_position", "collide_with_areas", "collide_with_bodies"],
	"CollisionShape2D": ["disabled", "one_way_collision"],
	"CollisionPolygon2D": ["disabled"]
}


func _set_node_properties(raw_args: Variant) -> Dictionary:
	if not raw_args is Dictionary:
		return {"ok": false, "error": "invalid_args"}
	var args: Dictionary = raw_args
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return {"ok": false, "error": "no_edited_scene"}
	var node_path := str(args.get("node_path", ""))
	if node_path.begins_with("/") or node_path == ".." or node_path.contains("../") or node_path.contains("/.."):
		return {"ok": false, "error": "invalid_node_path"}
	var node: Node = root if node_path.is_empty() or node_path == "." else root.get_node_or_null(NodePath(node_path))
	if node == null:
		return {"ok": false, "error": "node_not_found"}
	var raw_properties: Variant = args.get("properties", {})
	if not raw_properties is Dictionary or raw_properties.is_empty():
		return {"ok": false, "error": "properties_required"}
	var allowed: Array = []
	for class_key in NODE_PROPERTY_ALLOWLIST:
		if node.is_class(class_key):
			allowed.append_array(NODE_PROPERTY_ALLOWLIST[class_key])
	var changes: Dictionary = {}
	for property_name in raw_properties:
		var key := str(property_name)
		if key not in allowed:
			return {"ok": false, "error": "property_not_allowed", "property": key}
		var parsed := _validate_node_property(node, key, raw_properties[property_name])
		if not bool(parsed.get("ok", false)):
			return parsed
		changes[key] = parsed["value"]
	var undo_redo := get_undo_redo()
	undo_redo.create_action("Headless Bridge: Configure " + str(node.name))
	for key in changes:
		undo_redo.add_do_property(node, key, changes[key])
		undo_redo.add_undo_property(node, key, node.get(key))
	undo_redo.commit_action()
	return {"ok": true, "node_path": str(root.get_path_to(node)), "changed_properties": changes}


func _validate_node_property(node: Node, key: String, raw_value: Variant) -> Dictionary:
	if key in ["position", "scale", "up_direction", "target_position"]:
		if not raw_value is Dictionary or not raw_value.has("x") or not raw_value.has("y"):
			return {"ok": false, "error": "vector2_expected", "property": key}
		var x := float(raw_value["x"])
		var y := float(raw_value["y"])
		if not is_finite(x) or not is_finite(y) or absf(x) > 1000000.0 or absf(y) > 1000000.0:
			return {"ok": false, "error": "vector2_out_of_range", "property": key}
		return {"ok": true, "value": Vector2(x, y)}
	if key in ["rotation_degrees", "floor_max_angle"]:
		if not (raw_value is int or raw_value is float):
			return {"ok": false, "error": "number_expected", "property": key}
		var number := float(raw_value)
		if not is_finite(number) or absf(number) > 360000.0:
			return {"ok": false, "error": "number_out_of_range", "property": key}
		return {"ok": true, "value": number}
	if key in ["collision_layer", "collision_mask"]:
		if not (raw_value is int or raw_value is float) or not is_finite(float(raw_value)) or float(raw_value) != floorf(float(raw_value)) or float(raw_value) < 0.0 or float(raw_value) > 4294967295.0:
			return {"ok": false, "error": "unsigned_32bit_integer_expected", "property": key}
		return {"ok": true, "value": int(raw_value)}
	if key == "z_index":
		if not (raw_value is int or raw_value is float) or not is_finite(float(raw_value)) or float(raw_value) != floorf(float(raw_value)) or float(raw_value) < -4096.0 or float(raw_value) > 4096.0:
			return {"ok": false, "error": "integer_out_of_range", "property": key}
		return {"ok": true, "value": int(raw_value)}
	if key == "motion_mode":
		if not (raw_value is int or raw_value is float) or not is_finite(float(raw_value)) or float(raw_value) != floorf(float(raw_value)) or int(raw_value) not in [0, 1]:
			return {"ok": false, "error": "invalid_motion_mode", "property": key}
		return {"ok": true, "value": int(raw_value)}
	if key in ["visible", "input_pickable", "monitoring", "monitorable", "enabled", "collide_with_areas", "collide_with_bodies", "disabled", "one_way_collision"]:
		if not raw_value is bool:
			return {"ok": false, "error": "boolean_expected", "property": key}
		return {"ok": true, "value": raw_value}
	return {"ok": false, "error": "unsupported_property", "property": key}


func _open_project_scene(raw_args: Variant) -> Dictionary:
	if not raw_args is Dictionary:
		return {"ok": false, "error": "invalid_args"}
	var requested_path := str(raw_args.get("path", ""))
	if not requested_path.begins_with("res://") or requested_path.contains("..") or requested_path.contains("\\"):
		return {"ok": false, "error": "scene_path_not_allowed"}
	var scene_path := requested_path.simplify_path()
	if not scene_path.ends_with(".tscn"):
		return {"ok": false, "error": "scene_path_not_allowed"}
	if not FileAccess.file_exists(scene_path):
		return {"ok": false, "error": "scene_not_found"}
	EditorInterface.open_scene_from_path(scene_path)
	return {"ok": true, "scene_path": scene_path, "pending": true}



const CAPTURE_DIRECTORY := "user://headless_bridge_captures"
const MAX_VIDEO_FPS := 10
const MAX_VIDEO_SECONDS := 30
const MAX_VIDEO_FRAMES := 300


func _capture_editor_window_image() -> Dictionary:
	var screen_index := DisplayServer.window_get_current_screen()
	var screen_image := DisplayServer.screen_get_image(screen_index)
	if screen_image == null or screen_image.is_empty():
		return {"ok": false, "error": "screen_capture_unavailable"}
	var screen_origin := DisplayServer.screen_get_position(screen_index)
	var window_position := DisplayServer.window_get_position()
	var window_size := DisplayServer.window_get_size()
	var local_position := window_position - screen_origin
	var rect := Rect2i(local_position, window_size)
	var bounds := Rect2i(Vector2i.ZERO, screen_image.get_size())
	var clipped := rect.intersection(bounds)
	if clipped.size.x <= 0 or clipped.size.y <= 0:
		return {"ok": false, "error": "editor_window_outside_capture_screen"}
	var editor_image := screen_image.get_region(clipped)
	if editor_image == null or editor_image.is_empty():
		return {"ok": false, "error": "editor_window_crop_failed"}
	return {
		"ok": true,
		"image": editor_image,
		"screen": screen_index,
		"window_rect": {"x": clipped.position.x, "y": clipped.position.y, "width": clipped.size.x, "height": clipped.size.y}
	}


func _ensure_capture_directory() -> bool:
	return DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(CAPTURE_DIRECTORY)) == OK or DirAccess.dir_exists_absolute(ProjectSettings.globalize_path(CAPTURE_DIRECTORY))


func _capture_editor_screenshot() -> Dictionary:
	if not _video_recording.is_empty():
		return {"ok": false, "error": "video_recording_in_progress"}
	if not _ensure_capture_directory():
		return {"ok": false, "error": "capture_directory_unavailable"}
	var captured := _capture_editor_window_image()
	if not bool(captured.get("ok", false)):
		return captured
	_capture_sequence += 1
	var file_name := "editor_%d_%d.png" % [OS.get_process_id(), _capture_sequence]
	var capture_path := CAPTURE_DIRECTORY.path_join(file_name)
	var image: Image = captured["image"]
	var error := image.save_png(capture_path)
	if error != OK:
		return {"ok": false, "error": "screenshot_save_failed", "code": error}
	return {
		"ok": true,
		"capture_path": ProjectSettings.globalize_path(capture_path),
		"file_size": _get_capture_file_size(ProjectSettings.globalize_path(capture_path)),
		"width": image.get_width(),
		"height": image.get_height(),
		"source": "actual_editor_window",
		"window_rect": captured["window_rect"],
		"screen": captured["screen"]
	}


func _capture_desktop_screenshot() -> Dictionary:
	if not _video_recording.is_empty():
		return {"ok": false, "error": "video_recording_in_progress"}
	if not _ensure_capture_directory():
		return {"ok": false, "error": "capture_directory_unavailable"}
	var screen_index := DisplayServer.window_get_current_screen()
	var image := DisplayServer.screen_get_image(screen_index)
	if image == null or image.is_empty():
		return {"ok": false, "error": "screen_capture_unavailable"}
	_capture_sequence += 1
	var file_name := "desktop_%d_%d.png" % [OS.get_process_id(), _capture_sequence]
	var capture_path := CAPTURE_DIRECTORY.path_join(file_name)
	var absolute_path := ProjectSettings.globalize_path(capture_path)
	var error := image.save_png(absolute_path)
	if error != OK:
		return {"ok": false, "error": "screenshot_save_failed", "code": error}
	return {
		"ok": true,
		"capture_path": absolute_path,
		"file_size": _get_capture_file_size(absolute_path),
		"width": image.get_width(),
		"height": image.get_height(),
		"source": "actual_display",
		"screen": screen_index,
		"includes_preview_when_visible": true
	}


func _start_editor_video(raw_args: Variant) -> Dictionary:
	if not _video_recording.is_empty():
		return {"ok": false, "error": "video_recording_already_active"}
	if not raw_args is Dictionary:
		return {"ok": false, "error": "invalid_arguments"}
	var fps := int(raw_args.get("fps", 5))
	var duration := int(raw_args.get("duration_seconds", 5))
	if fps < 1 or fps > MAX_VIDEO_FPS:
		return {"ok": false, "error": "fps_out_of_range", "max_fps": MAX_VIDEO_FPS}
	if duration < 1 or duration > MAX_VIDEO_SECONDS or fps * duration > MAX_VIDEO_FRAMES:
		return {"ok": false, "error": "duration_out_of_range", "max_seconds": MAX_VIDEO_SECONDS, "max_frames": MAX_VIDEO_FRAMES}
	if not _ensure_capture_directory():
		return {"ok": false, "error": "capture_directory_unavailable"}
	var captured := _capture_editor_window_image()
	if not bool(captured.get("ok", false)):
		return captured
	_last_video_result.clear()
	var session_id := "%d_%d" % [OS.get_process_id(), Time.get_ticks_usec()]
	var frame_directory := ProjectSettings.globalize_path(CAPTURE_DIRECTORY.path_join("video_" + session_id))
	if DirAccess.make_dir_recursive_absolute(frame_directory) != OK:
		return {"ok": false, "error": "video_frame_directory_unavailable"}
	_video_recording = {
		"session_id": session_id,
		"frame_directory": frame_directory,
		"fps": fps,
		"duration_seconds": duration,
		"max_frames": fps * duration,
		"frames": 0,
		"next_frame_msec": 0,
		"started_msec": Time.get_ticks_msec(),
		"state": "recording"
	}
	return {"ok": true, "session_id": session_id, "status": "recording", "fps": fps, "duration_seconds": duration, "max_frames": fps * duration}


func _process_video_recording() -> void:
	if _video_recording.is_empty():
		return
	var now := Time.get_ticks_msec()
	var fps := int(_video_recording["fps"])
	var interval := maxi(1, int(1000.0 / float(fps)))
	if now < int(_video_recording["next_frame_msec"]):
		return
	if now - int(_video_recording["started_msec"]) >= int(_video_recording["duration_seconds"]) * 1000 or int(_video_recording["frames"]) >= int(_video_recording["max_frames"]):
		_finalize_editor_video()
		return
	var captured := _capture_editor_window_image()
	if not bool(captured.get("ok", false)):
		_video_recording["capture_error"] = str(captured.get("error", "capture_failed"))
		_finalize_editor_video()
		return
	var frame_index := int(_video_recording["frames"])
	var frame_path := str(_video_recording["frame_directory"]).path_join("frame_%05d.png" % frame_index)
	var image: Image = captured["image"]
	if image.save_png(frame_path) != OK:
		_video_recording["capture_error"] = "frame_save_failed"
		_finalize_editor_video()
		return
	_video_recording["frames"] = frame_index + 1
	_video_recording["next_frame_msec"] = now + interval
	if int(_video_recording["frames"]) >= int(_video_recording["max_frames"]):
		_finalize_editor_video()


func _stop_editor_video() -> Dictionary:
	if _video_recording.is_empty():
		if not _last_video_result.is_empty():
			return _last_video_result.duplicate(true)
		return {"ok": false, "error": "no_video_recording"}
	return _finalize_editor_video()


func _get_editor_video_status() -> Dictionary:
	if not _video_recording.is_empty():
		return {"ok": true, "status": "recording", "session_id": _video_recording.get("session_id", ""), "frames": _video_recording.get("frames", 0), "max_frames": _video_recording.get("max_frames", 0), "fps": _video_recording.get("fps", 0)}
	if not _last_video_result.is_empty():
		return _last_video_result.duplicate(true)
	return {"ok": true, "status": "idle"}


func _get_capture_file_size(path: String) -> int:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return -1
	var size := file.get_length()
	file.close()
	return size


func _finalize_editor_video() -> Dictionary:
	if _video_recording.is_empty():
		return {"ok": false, "error": "no_video_recording"}
	var recording := _video_recording.duplicate(true)
	_video_recording.clear()
	var frames := int(recording.get("frames", 0))
	if frames < 2:
		_last_video_result = {"ok": false, "error": "not_enough_video_frames", "frames": frames, "capture_error": recording.get("capture_error", "")}
		return _last_video_result.duplicate(true)
	var output_path := ProjectSettings.globalize_path(CAPTURE_DIRECTORY.path_join("editor_" + str(recording["session_id"]) + ".mp4"))
	var args := PackedStringArray([
		"-y", "-loglevel", "error", "-framerate", str(recording["fps"]),
		"-i", str(recording["frame_directory"]).path_join("frame_%05d.png"),
		"-frames:v", str(frames), "-c:v", "libx264", "-pix_fmt", "yuv420p",
		"-movflags", "+faststart", output_path
	])
	var output: Array = []
	var exit_code := OS.execute("ffmpeg", args, output, true)
	if exit_code != 0 or not FileAccess.file_exists(output_path):
		_last_video_result = {"ok": false, "error": "video_encoding_failed", "exit_code": exit_code, "output": output}
		return _last_video_result.duplicate(true)
	_last_video_result = {
		"ok": true,
		"video_path": output_path,
		"file_size": _get_capture_file_size(output_path),
		"frames": frames,
		"fps": recording["fps"],
		"duration_seconds": float(frames) / float(recording["fps"]),
		"source": "actual_editor_window",
		"capture_error": recording.get("capture_error", "")
	}
	return _last_video_result.duplicate(true)



const MAX_CAPTURE_CHUNK_BYTES := 48000


func _read_capture_chunk(raw_args: Variant) -> Dictionary:
	if not raw_args is Dictionary:
		return {"ok": false, "error": "invalid_arguments"}
	var path := str(raw_args.get("path", ""))
	var capture_root := ProjectSettings.globalize_path(CAPTURE_DIRECTORY).simplify_path()
	var normalized_path := path.simplify_path()
	if not normalized_path.begins_with(capture_root + "/") or normalized_path.contains("/../") or normalized_path.get_extension().to_lower() not in ["png", "mp4"]:
		return {"ok": false, "error": "capture_path_not_allowed"}
	if not FileAccess.file_exists(normalized_path):
		return {"ok": false, "error": "capture_file_not_found"}
	var offset := int(raw_args.get("offset", 0))
	var requested_length := int(raw_args.get("length", MAX_CAPTURE_CHUNK_BYTES))
	var file := FileAccess.open(normalized_path, FileAccess.READ)
	if file == null:
		return {"ok": false, "error": "capture_file_unreadable"}
	var file_size := file.get_length()
	if offset < 0 or offset > file_size or requested_length < 1 or requested_length > MAX_CAPTURE_CHUNK_BYTES:
		file.close()
		return {"ok": false, "error": "capture_chunk_range_invalid", "file_size": file_size}
	file.seek(offset)
	var bytes := file.get_buffer(mini(requested_length, file_size - offset))
	file.close()
	return {
		"ok": true,
		"path": normalized_path,
		"offset": offset,
		"file_size": file_size,
		"bytes_read": bytes.size(),
		"eof": offset + bytes.size() >= file_size,
		"encoding": "base64",
		"data": Marshalls.raw_to_base64(bytes)
	}


# Runtime preview is controlled through EditorInterface, but remains a separate
# game process. Only project-local scene files can be launched by this bridge.
func _preview_status() -> Dictionary:
	return {
		"ok": true,
		"running": EditorInterface.is_playing_scene(),
		"scene_path": EditorInterface.get_playing_scene(),
		"editor_pid": OS.get_process_id(),
		"project_id": _project_id
	}


func _start_preview(raw_args: Variant) -> Dictionary:
	if not raw_args is Dictionary:
		return {"ok": false, "error": "invalid_arguments"}
	var scene_path := str(raw_args.get("scene_path", ""))
	if not scene_path.begins_with("res://") or scene_path.contains("..") or scene_path.contains("\\"):
		return {"ok": false, "error": "invalid_scene_path"}
	if not scene_path.ends_with(".tscn") or not ResourceLoader.exists(scene_path):
		return {"ok": false, "error": "scene_not_found", "scene_path": scene_path}
	if EditorInterface.is_playing_scene():
		return {"ok": false, "error": "preview_already_running", "scene_path": EditorInterface.get_playing_scene()}
	EditorInterface.play_custom_scene(scene_path)
	return {
		"ok": true,
		"started": true,
		"scene_path": scene_path,
		"running": EditorInterface.is_playing_scene(),
		"editor_pid": OS.get_process_id(),
		"project_id": _project_id
	}


func _stop_preview() -> Dictionary:
	var was_running := EditorInterface.is_playing_scene()
	if was_running:
		EditorInterface.stop_playing_scene()
	return {
		"ok": true,
		"stopped": was_running,
		"running": EditorInterface.is_playing_scene(),
		"scene_path": EditorInterface.get_playing_scene(),
		"editor_pid": OS.get_process_id(),
		"project_id": _project_id
	}
