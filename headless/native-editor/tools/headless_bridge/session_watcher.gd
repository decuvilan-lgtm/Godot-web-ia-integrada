extends SceneTree
## Persistent session watcher for the Headless Session Bridge.
## Run with:
## Godot --headless --path . --script res://tools/headless_bridge/session_watcher.gd
##
## The watcher never launches or owns the editor. It discovers the editor's
## per-project registry, authenticates, sends heartbeats, and reconnects after
## the editor disappears or restarts. Stop it with Ctrl+C / process termination.

const REGISTRY_PATH := "user://headless_bridge.json"
const PROTOCOL_VERSION := 1
const DISCOVERY_INTERVAL := 0.5
const HEARTBEAT_INTERVAL := 1.0
const CONNECT_TIMEOUT_MS := 2500
const RESPONSE_TIMEOUT_MS := 2500

var _project_id := ""


func _initialize() -> void:
	_project_id = ProjectSettings.globalize_path("res://").simplify_path().sha256_text()
	call_deferred("_watch_forever")


func _watch_forever() -> void:
	print("SESSION_WATCHER_START project_id=", _project_id)
	while true:
		var registry := _read_registry()
		if registry.is_empty():
			await create_timer(DISCOVERY_INTERVAL).timeout
			continue

		if str(registry.get("project_id", "")) != _project_id:
			push_warning("SESSION_WATCHER_IGNORED registry for a different project.")
			await create_timer(DISCOVERY_INTERVAL).timeout
			continue
		if int(registry.get("protocol", -1)) != PROTOCOL_VERSION:
			push_warning("SESSION_WATCHER_IGNORED incompatible bridge protocol.")
			await create_timer(DISCOVERY_INTERVAL).timeout
			continue

		var peer := await _connect_and_authenticate(registry)
		if peer == null:
			# The registry can briefly outlive an editor crash/restart. Keep
			# rereading it so a replacement editor can publish a new token.
			await create_timer(DISCOVERY_INTERVAL).timeout
			continue

		print("SESSION_CONNECTED editor_pid=", registry.get("editor_pid", -1))
		while peer.get_status() == StreamPeerTCP.STATUS_CONNECTED:
			await create_timer(HEARTBEAT_INTERVAL).timeout
			if not await _send_ping(peer, registry):
				break

		if peer.get_status() == StreamPeerTCP.STATUS_CONNECTED:
			peer.disconnect_from_host()
		print("SESSION_DISCONNECTED reason=heartbeat_or_editor_exit; searching_again")
		await create_timer(DISCOVERY_INTERVAL).timeout


func _read_registry() -> Dictionary:
	if not FileAccess.file_exists(REGISTRY_PATH):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(REGISTRY_PATH))
	if parsed is Dictionary:
		return parsed
	return {}


func _connect_and_authenticate(registry: Dictionary) -> StreamPeerTCP:
	var peer := StreamPeerTCP.new()
	var error := peer.connect_to_host("127.0.0.1", int(registry.get("port", -1)))
	if error != OK:
		return null

	var deadline := Time.get_ticks_msec() + CONNECT_TIMEOUT_MS
	while peer.get_status() == StreamPeerTCP.STATUS_CONNECTING and Time.get_ticks_msec() < deadline:
		peer.poll()
		await create_timer(0.05).timeout
	if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		peer.disconnect_from_host()
		return null

	if not await _send_ping(peer, registry):
		peer.disconnect_from_host()
		return null
	return peer


func _send_ping(peer: StreamPeerTCP, registry: Dictionary) -> bool:
	if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		return false

	var request := {
		"protocol": PROTOCOL_VERSION,
		"token": str(registry.get("token", "")),
		"project_id": _project_id,
		"command": "ping"
	}
	if peer.put_data((JSON.stringify(request) + "\n").to_utf8_buffer()) != OK:
		return false

	var response_text := ""
	var deadline := Time.get_ticks_msec() + RESPONSE_TIMEOUT_MS
	while Time.get_ticks_msec() < deadline:
		peer.poll()
		if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
			return false
		var available := peer.get_available_bytes()
		if available > 0:
			var packet := peer.get_data(available)
			if packet[0] != OK:
				return false
			response_text += packet[1].get_string_from_utf8()
			if response_text.contains("\n"):
				var parsed: Variant = JSON.parse_string(response_text.strip_edges())
				return parsed is Dictionary and bool(parsed.get("ok", false)) and str(parsed.get("status", "")) == "alive"
		await create_timer(0.05).timeout
	return false
