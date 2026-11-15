extends SceneTree

const REGISTRY_PATH := "user://headless_bridge.json"
const PROTOCOL_VERSION := 1
const DISCOVERY_TIMEOUT_MS := 45000
const CONNECT_TIMEOUT_MS := 8000
const RESPONSE_TIMEOUT_MS := 15000


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var action := "show_test_marker"
	var user_args := OS.get_cmdline_user_args()
	var command_args: Dictionary = {}
	if not user_args.is_empty():
		action = str(user_args[0])
	if user_args.size() > 1:
		var parsed_args: Variant = JSON.parse_string(str(user_args[1]))
		if not parsed_args is Dictionary:
			_fail("Command arguments must be a JSON object.")
			return
		command_args = parsed_args
	if not ["editor.list_capabilities", "editor.get_state", "scene.get_tree", "scene.inspect_selection", "scene.add_node", "scene.set_node_properties", "scene.configure_collision_shape", "scene.assign_visual_resource", "scene.create_sprite_frames", "editor.open_scene", "editor.focus_inspector", "editor.inspect_undo_history", "editor.undo", "editor.redo", "editor.inspect_project_settings", "editor.inspect_editor_settings", "project.list_resources", "project.inspect_resource", "preview.get_status", "preview.start", "preview.stop", "capture.editor_screenshot", "capture.desktop_screenshot", "capture.start_editor_video", "capture.stop_editor_video", "capture.get_video_status", "capture.read_chunk", "ping", "show_test_marker", "clear_test_marker", "open_scene", "inspect_scene", "inspect_selection", "focus_inspector", "inspect_undo_history", "undo_bridge_action", "redo_bridge_action", "inspect_project_settings", "inspect_editor_settings", "inspect_resource", "list_project_resources", "add_node", "set_node_properties", "configure_collision_shape", "assign_visual_resource", "create_sprite_frames", "preview_status", "start_preview", "stop_preview", "capture_editor_screenshot", "capture_desktop_screenshot", "start_editor_video", "stop_editor_video", "get_editor_video_status", "read_capture_chunk"].has(action):
		_fail("Unsupported action: " + action)
		return

	var registry := await _discover_session()
	if registry.is_empty():
		_fail("No active editor session for this project was discovered.")
		return

	var expected_project_id := ProjectSettings.globalize_path("res://").simplify_path().sha256_text()
	if str(registry.get("project_id", "")) != expected_project_id:
		_fail("The discovered editor belongs to a different project.")
		return
	if int(registry.get("protocol", -1)) != PROTOCOL_VERSION:
		_fail("Bridge protocol version mismatch.")
		return

	var peer := StreamPeerTCP.new()
	var error := peer.connect_to_host("127.0.0.1", int(registry.get("port", -1)))
	if error != OK:
		_fail("Connection attempt failed: %s" % error)
		return
	var connect_deadline := Time.get_ticks_msec() + CONNECT_TIMEOUT_MS
	while peer.get_status() == StreamPeerTCP.STATUS_CONNECTING and Time.get_ticks_msec() < connect_deadline:
		peer.poll()
		await create_timer(0.05).timeout
	if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		_fail("Editor session was discovered but did not accept the connection.")
		return

	var request := {
		"protocol": PROTOCOL_VERSION,
		"token": str(registry.get("token", "")),
		"project_id": expected_project_id,
		"command": action,
		"args": command_args
	}
	peer.put_data((JSON.stringify(request) + "\n").to_utf8_buffer())
	var response_text := ""
	var response_deadline := Time.get_ticks_msec() + RESPONSE_TIMEOUT_MS
	while Time.get_ticks_msec() < response_deadline:
		peer.poll()
		var available := peer.get_available_bytes()
		if available > 0:
			var packet := peer.get_data(available)
			if packet[0] == OK:
				response_text += packet[1].get_string_from_utf8()
				if response_text.contains("\n"):
					break
		await create_timer(0.05).timeout
	peer.disconnect_from_host()

	if response_text.is_empty():
		_fail("The editor did not answer before the response timeout.")
		return
	var response: Variant = JSON.parse_string(response_text.strip_edges())
	if not response is Dictionary or not bool(response.get("ok", false)):
		_fail("Editor rejected the request: " + response_text)
		return
	if action in ["open_scene", "editor.open_scene"]:
		var open_result: Variant = response.get("result", {})
		if not open_result is Dictionary or not bool(open_result.get("opened", false)):
			_fail("Editor acknowledged open_scene without confirming the requested scene became active.")
			return
		if str(open_result.get("scene_path", "")) != str(command_args.get("path", "")).simplify_path():
			_fail("Editor confirmed a different scene than the requested path.")
			return
		print("BRIDGE_SCENE_OPEN_CONFIRMED " + str(open_result.get("scene_path", "")))
	print("BRIDGE_TEST_PASS " + JSON.stringify(response))
	if action == "clear_test_marker":
		var idle_ok := await _verify_idle_timeout(registry, expected_project_id)
		if not idle_ok:
			_fail("The editor did not close an idle connection after the heartbeat timeout.")
			return
		print("BRIDGE_IDLE_TIMEOUT_PASS")
	quit(0)


func _discover_session() -> Dictionary:
	var deadline := Time.get_ticks_msec() + DISCOVERY_TIMEOUT_MS
	while Time.get_ticks_msec() < deadline:
		if FileAccess.file_exists(REGISTRY_PATH):
			var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(REGISTRY_PATH))
			if parsed is Dictionary:
				return parsed
		await create_timer(0.25).timeout
	return {}


func _fail(message: String) -> void:
	push_error("BRIDGE_TEST_FAIL: " + message)
	quit(1)


func _verify_idle_timeout(registry: Dictionary, project_id: String) -> bool:
	var peer := StreamPeerTCP.new()
	var error := peer.connect_to_host("127.0.0.1", int(registry.get("port", -1)))
	if error != OK:
		return false
	var connect_deadline := Time.get_ticks_msec() + CONNECT_TIMEOUT_MS
	while peer.get_status() == StreamPeerTCP.STATUS_CONNECTING and Time.get_ticks_msec() < connect_deadline:
		peer.poll()
		await create_timer(0.05).timeout
	if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		return false
	var request := {
		"protocol": PROTOCOL_VERSION,
		"token": str(registry.get("token", "")),
		"project_id": project_id,
		"command": "ping"
	}
	peer.put_data((JSON.stringify(request) + "\n").to_utf8_buffer())
	var response_text := ""
	var response_deadline := Time.get_ticks_msec() + RESPONSE_TIMEOUT_MS
	while Time.get_ticks_msec() < response_deadline:
		peer.poll()
		var available := peer.get_available_bytes()
		if available > 0:
			var packet := peer.get_data(available)
			if packet[0] == OK:
				response_text += packet[1].get_string_from_utf8()
				if response_text.contains("\n"):
					break
		await create_timer(0.05).timeout
	if response_text.is_empty():
		return false
	var parsed: Variant = JSON.parse_string(response_text.strip_edges())
	if not parsed is Dictionary or not bool(parsed.get("ok", false)):
		return false

	var idle_deadline := Time.get_ticks_msec() + 8000
	while Time.get_ticks_msec() < idle_deadline:
		peer.poll()
		if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
			return true
		await create_timer(0.1).timeout
	return false
