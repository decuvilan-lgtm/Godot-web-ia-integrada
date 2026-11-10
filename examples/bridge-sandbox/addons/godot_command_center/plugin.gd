@tool
extends EditorPlugin

const API_DEFAULT := "https://godot-web-ia-relay.onrender.com"
const MAX_FILES := 500
const MAX_NODES := 300
const MAX_DEPTH := 24
const MAX_SCRIPT_BYTES := 65536
const ALLOWED_EXTENSIONS := [".gd", ".tscn", ".tres", ".cfg", ".json", ".txt", ".md"]

var _dock: VBoxContainer
var _api_input: LineEdit
var _label_input: LineEdit
var _code_input: LineEdit
var _pair_button: Button
var _poll_button: Button
var _status: Label
var _pair_request: HTTPRequest
var _command_request: HTTPRequest
var _visual_request: HTTPRequest

var _installation_id := ""
var _credential := ""
var _device_id := ""
var _pair_busy := false
var _command_busy := false
var _polling := false
var _request_kind := ""
var _next_poll_ms := 0
var _command_id := ""
var _command_started_ms := 0
var _pending_result: Dictionary = {}


func _enter_tree() -> void:
	_build_dock()
	_pair_request = HTTPRequest.new()
	_pair_request.timeout = 15.0
	_pair_request.max_redirects = 0
	_pair_request.request_completed.connect(_on_pair_completed)
	add_child(_pair_request)
	_command_request = HTTPRequest.new()
	_command_request.timeout = 15.0
	_command_request.max_redirects = 0
	_command_request.request_completed.connect(_on_command_completed)
	add_child(_command_request)
	_visual_request = HTTPRequest.new()
	_visual_request.timeout = 30.0
	_visual_request.max_redirects = 0
	add_child(_visual_request)
	_ensure_installation_id()
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)
	set_process(true)


func _exit_tree() -> void:
	_polling = false
	_credential = ""
	if is_instance_valid(_pair_request):
		_pair_request.cancel_request()
	if is_instance_valid(_command_request):
		_command_request.cancel_request()
	if is_instance_valid(_visual_request):
		_visual_request.cancel_request()
	if is_instance_valid(_dock):
		remove_control_from_docks(_dock)
		_dock.queue_free()


func _build_dock() -> void:
	_dock = VBoxContainer.new()
	_dock.name = "Command Center"
	_dock.custom_minimum_size = Vector2(260, 180)

	var title := Label.new()
	title.text = "Godot Web · Agent Workspace"
	_dock.add_child(title)

	_api_input = LineEdit.new()
	_api_input.text = API_DEFAULT
	_api_input.placeholder_text = "https://relay.example.com"
	_dock.add_child(_field("API HTTPS", _api_input))

	_label_input = LineEdit.new()
	_label_input.text = "Godot Web Agent Workspace"
	_label_input.max_length = 80
	_dock.add_child(_field("Nombre del editor web", _label_input))

	_code_input = LineEdit.new()
	_code_input.secret = true
	_code_input.placeholder_text = "Código temporal de un solo uso"
	_dock.add_child(_field("Código de emparejamiento", _code_input))

	_pair_button = Button.new()
	_pair_button.text = "Emparejar como Godot Web (IA)"
	_pair_button.pressed.connect(_pair_device)
	_dock.add_child(_pair_button)

	_poll_button = Button.new()
	_poll_button.text = "Iniciar recepción de órdenes"
	_poll_button.disabled = true
	_poll_button.pressed.connect(_toggle_polling)
	_dock.add_child(_poll_button)

	var forget := Button.new()
	forget.text = "Desconectar y olvidar credencial"
	forget.pressed.connect(_forget_credential)
	_dock.add_child(forget)

	_status = Label.new()
	_status.text = "Workspace de IA aislado · sin emparejar · solo lectura"
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_dock.add_child(_status)

	var note := Label.new()
	note.text = "No modifica el proyecto Android. No escribe archivos ni ejecuta comandos del sistema."
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_dock.add_child(note)


func _field(caption: String, control: Control) -> VBoxContainer:
	var container := VBoxContainer.new()
	var label := Label.new()
	label.text = caption
	container.add_child(label)
	container.add_child(control)
	return container


func _ensure_installation_id() -> void:
	var settings := EditorInterface.get_editor_settings()
	var key := "godot_command_center/web_installation_id"
	var existing := str(settings.get_setting(key)) if settings.has_setting(key) else ""
	var regex := RegEx.new()
	regex.compile("^[a-f0-9]{32}$")
	if regex.search(existing) != null:
		_installation_id = existing
		return
	var crypto := Crypto.new()
	var bytes := crypto.generate_random_bytes(16)
	if bytes.size() != 16:
		bytes = PackedByteArray()
		for _i in range(16):
			bytes.append(randi_range(0, 255))
	_installation_id = bytes.hex_encode()
	settings.set_setting(key, _installation_id)


func _api_base() -> String:
	return _api_input.text.strip_edges().trim_suffix("/")


func _valid_api_url() -> bool:
	var value := _api_base()
	if not value.begins_with("https://") or value.contains("?") or value.contains("#"):
		return false
	var host := value.trim_prefix("https://")
	return not host.is_empty() and not host.contains("/") and not host.contains(" ")


func _pair_device() -> void:
	if _pair_busy or not _credential.is_empty():
		_set_status("Este workspace ya está emparejado o hay una solicitud en curso.")
		return
	if not _valid_api_url():
		_set_status("La API debe ser HTTPS y contener solo el host, sin rutas ni parámetros.")
		return
	var code := _code_input.text.strip_edges()
	var label := _label_input.text.strip_edges()
	if code.length() < 24 or code.length() > 128 or label.is_empty() or label.length() > 80:
		_set_status("Revisa el código temporal y el nombre del workspace.")
		return
	var payload := {
		"pairing_code": code,
		"label": label,
		"installation_id": _installation_id
	}
	var error := _pair_request.request(
		_api_base() + "/v1/command-center/pair",
		PackedStringArray(["Content-Type: application/json"]),
		HTTPClient.METHOD_POST,
		JSON.stringify(payload)
	)
	if error != OK:
		_set_status("No se pudo iniciar el emparejamiento: " + error_string(error))
		return
	_pair_busy = true
	_pair_button.disabled = true
	_set_status("Emparejando el puesto web de la IA…")


func _on_pair_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_pair_busy = false
	_pair_button.disabled = false
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 201 or not parsed is Dictionary:
		var detail := str(parsed.get("detail", "Respuesta no válida")) if parsed is Dictionary else body.get_string_from_utf8().left(200)
		_set_status("Emparejamiento rechazado (" + str(response_code) + "): " + detail)
		return
	var kind := str(parsed.get("device_kind", ""))
	var credential := str(parsed.get("device_credential", ""))
	_device_id = str(parsed.get("device_id", ""))
	if kind != "web_editor" or credential.length() < 32 or _device_id.is_empty():
		_set_status("El servidor no confirmó un dispositivo web válido. No se guardó la credencial.")
		return
	_credential = credential
	_code_input.clear()
	_code_input.editable = false
	_api_input.editable = false
	_label_input.editable = false
	_pair_button.disabled = true
	_poll_button.disabled = false
	_set_status("Puesto web emparejado. Credencial solo en memoria · " + _device_id)


func _toggle_polling() -> void:
	if _credential.is_empty():
		_set_status("Empareja primero este puesto web.")
		return
	_polling = not _polling
	if _polling:
		_poll_button.text = "Detener recepción de órdenes"
		_next_poll_ms = 0
		_set_status("Godot Web está conectado. Esperando órdenes de inspección…")
	else:
		_poll_button.text = "Iniciar recepción de órdenes"
		_set_status("Recepción pausada. La credencial sigue en memoria.")


func _forget_credential() -> void:
	_polling = false
	_credential = ""
	_device_id = ""
	_command_id = ""
	_pending_result.clear()
	_command_request.cancel_request()
	_visual_request.cancel_request()
	_command_busy = false
	_request_kind = ""
	_code_input.editable = true
	_api_input.editable = true
	_label_input.editable = true
	_pair_button.disabled = false
	_poll_button.disabled = true
	_poll_button.text = "Iniciar recepción de órdenes"
	_set_status("Credencial local eliminada. Solicita un código nuevo para emparejar otra vez.")


func _process(_delta: float) -> void:
	if not _polling or _credential.is_empty() or _command_busy:
		return
	var now := Time.get_ticks_msec()
	if now < _next_poll_ms:
		return
	if not _pending_result.is_empty():
		_send_pending_result()
		return
	if not _valid_api_url():
		_polling = false
		_poll_button.text = "Iniciar recepción de órdenes"
		_set_status("URL de API inválida; recepción pausada.")
		return
	var error := _command_request.request(
		_api_base() + "/v1/command-center/commands/next?target=web_editor",
		PackedStringArray(["Authorization: Bearer " + _credential]),
		HTTPClient.METHOD_GET
	)
	if error != OK:
		_next_poll_ms = now + 5000
		_set_status("Error consultando órdenes: " + error_string(error))
		return
	_command_busy = true
	_request_kind = "poll"


func _on_command_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_command_busy = false
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	if _request_kind == "poll":
		if result != HTTPRequest.RESULT_SUCCESS or response_code != 200 or not parsed is Dictionary:
			_next_poll_ms = Time.get_ticks_msec() + 5000
			if response_code == 401:
				_forget_credential()
				_set_status("Credencial rechazada o revocada. Empareja de nuevo.")
			else:
				_set_status("Error consultando órdenes (" + str(response_code) + "). Reintento en 5 segundos.")
			return
		var command: Variant = parsed.get("command", null)
		if command == null:
			_next_poll_ms = Time.get_ticks_msec() + 2000
			return
		if not command is Dictionary:
			_next_poll_ms = Time.get_ticks_msec() + 5000
			_set_status("El relay devolvió una orden mal formada.")
			return
		_command_id = str(command.get("id", ""))
		if not _is_uuid(_command_id):
			_command_id = ""
			_next_poll_ms = Time.get_ticks_msec() + 5000
			_set_status("La orden no contiene un identificador válido.")
			return
		_command_started_ms = Time.get_ticks_msec()
		_command_busy = true
		var execution: Dictionary = await _execute_command(str(command.get("action", "")), command.get("args", {}))
		_command_busy = false
		_pending_result = {
			"ok": bool(execution.get("ok", false)),
			"result": execution.get("result", {}),
			"duration_ms": maxi(0, Time.get_ticks_msec() - _command_started_ms)
		}
		_send_pending_result()
		return
	if _request_kind == "result":
		if result == HTTPRequest.RESULT_SUCCESS and response_code in [200, 201]:
			_command_id = ""
			_pending_result.clear()
			_next_poll_ms = Time.get_ticks_msec() + 500
			_set_status("Orden completada. Esperando la siguiente…")
		elif response_code == 409:
			_command_id = ""
			_pending_result.clear()
			_next_poll_ms = Time.get_ticks_msec() + 2000
			_set_status("El lease expiró. La orden podrá recuperarse de forma segura.")
		elif response_code == 401:
			_forget_credential()
			_set_status("Credencial revocada. Empareja de nuevo.")
		else:
			_next_poll_ms = Time.get_ticks_msec() + 5000
			_set_status("No se pudo confirmar el resultado. Se conservará para reintentar.")
		return


func _send_pending_result() -> void:
	if _command_id.is_empty() or _pending_result.is_empty() or _command_busy:
		return
	var error := _command_request.request(
		_api_base() + "/v1/command-center/commands/" + _command_id + "/result",
		PackedStringArray([
			"Authorization: Bearer " + _credential,
			"Content-Type: application/json"
		]),
		HTTPClient.METHOD_POST,
		JSON.stringify(_pending_result)
	)
	if error != OK:
		_next_poll_ms = Time.get_ticks_msec() + 5000
		return
	_command_busy = true
	_request_kind = "result"

func _execute_command(action: String, args: Variant) -> Dictionary:
	if action.begins_with("visual."):
		return await _execute_visual_action(action, args)
	return _execute_read_only(action, args)


func _execute_visual_action(action: String, args: Variant) -> Dictionary:
	if not args is Dictionary:
		return {"ok": false, "result": {"error": "Los argumentos visuales deben ser un objeto."}}
	var target := str(args.get("target", ""))
	if target in ["editor_ui", "game_preview"]:
		return {"ok": false, "result": {"error_code": "VISUAL_TARGET_UNAVAILABLE", "message": "Este objetivo requiere captura del navegador; el complemento Godot no lo sustituye por una captura parcial."}}
	if action == "visual.zoom_to":
		return {"ok": false, "result": {"error_code": "VISUAL_ZOOM_BACKEND_UNAVAILABLE", "message": "La captura con zoom se mantiene deshabilitada hasta implementar y probar la restauración exacta de la vista."}}
	if target not in ["editor_2d", "editor_3d"]:
		return {"ok": false, "result": {"error_code": "VISUAL_TARGET_UNAVAILABLE", "message": "Objetivo visual no disponible en este complemento."}}
	var frame_count := int(args.get("frames", 1)) if action == "visual.capture_sequence" else 1
	var interval_ms := int(args.get("interval_ms", 250))
	if frame_count < 1 or frame_count > 24:
		return {"ok": false, "result": {"error_code": "VISUAL_SEQUENCE_LIMIT", "message": "Cantidad de imágenes fuera del límite."}}
	var asset_ids: Array[String] = []
	for frame_index in range(frame_count):
		var uploaded: Dictionary = await _capture_and_upload_visual(str(_command_id), target, args, frame_index if frame_count > 1 else -1)
		if not bool(uploaded.get("ok", false)):
			return {"ok": false, "result": {
				"error_code": str(uploaded.get("error_code", "VISUAL_CAPTURE_FAILED")),
				"message": str(uploaded.get("message", "No se pudo capturar o subir la imagen.")),
				"asset_ids": asset_ids,
				"captured_frames": asset_ids.size(),
				"requested_frames": frame_count
			}}
		asset_ids.append(str(uploaded.get("asset_id", "")))
		if frame_index + 1 < frame_count:
			await get_tree().create_timer(float(interval_ms) / 1000.0).timeout
	return {"ok": true, "result": {
		"asset_ids": asset_ids,
		"captured_frames": asset_ids.size(),
		"requested_frames": frame_count,
		"target": target,
		"source": "godot_editor_subviewport"
	}}


func _capture_and_upload_visual(command_id: String, target: String, args: Dictionary, frame_index: int) -> Dictionary:
	var lease_check: Dictionary = await _request_visual_json("/v1/command-center/commands/" + command_id + "/heartbeat", HTTPClient.METHOD_POST, {})
	if not bool(lease_check.get("ok", false)):
		return {"ok": false, "error_code": "COMMAND_LEASE_LOST", "message": "La orden dejó de pertenecer a este editor."}
	var image: Image = await _capture_editor_viewport(target, args)
	if image == null or image.is_empty():
		return {"ok": false, "error_code": "VISUAL_CAPTURE_EMPTY", "message": "El SubViewport no devolvió una imagen válida."}
	var output: Dictionary = args.get("output", {})
	var max_width := clampi(int(output.get("max_width", 2560)), 320, 8192)
	var max_height := clampi(int(output.get("max_height", 1440)), 320, 8192)
	var scale_factor := minf(1.0, minf(float(max_width) / image.get_width(), float(max_height) / image.get_height()))
	if scale_factor < 1.0:
		image.resize(maxi(1, int(image.get_width() * scale_factor)), maxi(1, int(image.get_height() * scale_factor)), Image.INTERPOLATE_LANCZOS)
	var format := str(output.get("format", "jpeg"))
	var content_type := "image/jpeg" if format == "jpeg" else "image/png"
	if format not in ["jpeg", "png"]:
		return {"ok": false, "error_code": "VISUAL_FORMAT_UNAVAILABLE", "message": "El complemento solo genera JPEG y PNG por ahora."}
	var bytes: PackedByteArray
	if format == "png":
		bytes = image.save_png_to_buffer()
	else:
		var quality := clampi(int(output.get("quality", 85)), 40, 100)
		bytes = image.save_jpg_to_buffer(float(quality) / 100.0)
	if bytes.is_empty() or bytes.size() > 12 * 1024 * 1024:
		return {"ok": false, "error_code": "VISUAL_IMAGE_SIZE", "message": "La imagen comprimida está vacía o supera 12 MiB."}
	var upload_headers := PackedStringArray([
		"Authorization: Bearer " + _credential,
		"Content-Type: " + content_type,
		"X-Command-Id: " + command_id
	])
	if frame_index >= 0:
		upload_headers.append("X-Frame-Index: " + str(frame_index))
	var upload_response: Dictionary = await _perform_visual_request(
		_api_base() + "/v1/command-center/visual/uploads/proxy",
		HTTPClient.METHOD_POST,
		upload_headers,
		bytes
	)
	if not bool(upload_response.get("ok", false)) or int(upload_response.get("code", 0)) != 201:
		return {"ok": false, "error_code": "VISUAL_PROXY_UPLOAD_FAILED", "message": "El relay no pudo guardar la imagen en Neon."}
	var upload_body: PackedByteArray = upload_response.get("body", PackedByteArray())
	var upload_data: Variant = JSON.parse_string(upload_body.get_string_from_utf8())
	if not upload_data is Dictionary:
		return {"ok": false, "error_code": "VISUAL_PROXY_RESPONSE_INVALID", "message": "El relay devolvió una respuesta de subida inválida."}
	var object_key := str(upload_data.get("object_key", ""))
	if object_key.is_empty():
		return {"ok": false, "error_code": "VISUAL_PROXY_KEY_MISSING", "message": "El relay no confirmó la ubicación privada de la imagen."}
	var metadata: Dictionary = {}
	if bool(args.get("include_metadata", true)):
		metadata = {"frame_index": frame_index, "viewport_size": [image.get_width(), image.get_height()], "godot_version": Engine.get_version_info()}
	var lease_before_complete: Dictionary = await _request_visual_json("/v1/command-center/commands/" + command_id + "/heartbeat", HTTPClient.METHOD_POST, {})
	if not bool(lease_before_complete.get("ok", false)):
		await _abandon_visual_upload(object_key)
		return {"ok": false, "error_code": "COMMAND_LEASE_LOST", "message": "El lease expiró antes de registrar la imagen."}
	var complete_payload := {
		"object_key": object_key,
		"width": image.get_width(),
		"height": image.get_height(),
		"metadata": metadata
	}
	var completed: Dictionary = await _request_visual_json("/v1/command-center/visual/uploads/complete", HTTPClient.METHOD_POST, complete_payload)
	if not bool(completed.get("ok", false)):
		await _abandon_visual_upload(object_key)
		return {"ok": false, "error_code": "VISUAL_UPLOAD_REGISTER_FAILED", "message": "La imagen llegó al almacenamiento, pero Neon no confirmó sus metadatos."}
	var completed_data: Dictionary = completed.get("data", {})
	return {"ok": true, "asset_id": str(completed_data.get("asset_id", ""))}


func _abandon_visual_upload(object_key: String) -> void:
	if object_key.is_empty():
		return
	# Cleanup is workspace- and command-scoped on the relay. A registered asset
	# is protected server-side, so a delayed retry cannot delete a valid capture.
	await _request_visual_json(
		"/v1/command-center/visual/uploads/abandon",
		HTTPClient.METHOD_POST,
		{"object_key": object_key}
	)


func _capture_editor_viewport(target: String, args: Dictionary) -> Image:
	var viewport: SubViewport
	if target == "editor_2d":
		viewport = EditorInterface.get_editor_viewport_2d()
	elif target == "editor_3d":
		var viewport_index := clampi(int(args.get("viewport_index", 0)), 0, 3)
		viewport = EditorInterface.get_editor_viewport_3d(viewport_index)
	else:
		return null
	if viewport == null or viewport.get_texture() == null:
		return null
	await RenderingServer.frame_post_draw
	var image := viewport.get_texture().get_image()
	if image == null or image.is_empty():
		return null
	return image


func _request_visual_json(path: String, method: int, payload: Dictionary) -> Dictionary:
	var body := JSON.stringify(payload).to_utf8_buffer()
	var response: Dictionary = await _perform_visual_request(
		_api_base() + path,
		method,
		PackedStringArray(["Authorization: Bearer " + _credential, "Content-Type: application/json"]),
		body
	)
	if not bool(response.get("ok", false)):
		return {"ok": false, "code": response.get("code", 0)}
	var response_body: PackedByteArray = response.get("body", PackedByteArray())
	var parsed: Variant = JSON.parse_string(response_body.get_string_from_utf8())
	if not parsed is Dictionary:
		return {"ok": false, "code": response.get("code", 0)}
	return {"ok": int(response.get("code", 0)) in [200, 201], "data": parsed, "code": response.get("code", 0)}


func _perform_visual_request(url: String, method: int, headers: PackedStringArray, body: PackedByteArray) -> Dictionary:
	var error: Error
	error = _visual_request.request_raw(url, headers, method, body)
	if error != OK:
		return {"ok": false, "code": 0, "body": PackedByteArray()}
	var response: Array = await _visual_request.request_completed
	var result_code: int = int(response[0])
	var http_code: int = int(response[1])
	var response_body: PackedByteArray = response[3]
	return {"ok": result_code == HTTPRequest.RESULT_SUCCESS, "code": http_code, "body": response_body}


func _execute_read_only(action: String, args: Variant) -> Dictionary:
	if not args is Dictionary:
		return {"ok": false, "result": {"error": "Los argumentos deben ser un objeto JSON."}}
	match action:
		"ping":
			return {"ok": true, "result": {
				"pong": true,
				"editor": "Godot Web",
				"version": Engine.get_version_info(),
				"platform": OS.get_name()
			}}
		"project.get_state":
			var root := EditorInterface.get_edited_scene_root()
			return {"ok": true, "result": {				"project_name": str(ProjectSettings.get_setting("application/config/name", "Godot Project")),
				"current_scene": root.scene_file_path if root != null else "",
				"godot_version": Engine.get_version_info(),
				"platform": OS.get_name(),
				"workspace_role": "agent_workspace"
			}}
		"project.list_files":
			return _list_project_files(args)
		"scene.inspect":
			return _inspect_current_scene()
		"script.read":
			return _read_script(args)
		_:
			return {"ok": false, "result": {"error": "Acción no permitida por la política de solo lectura."}}


func _list_project_files(args: Dictionary) -> Dictionary:
	var limit := clampi(int(args.get("limit", 250)), 1, MAX_FILES)
	var files: Array[String] = []
	_collect_files("res://", files, limit, 0)
	return {"ok": true, "result": {"files": files, "count": files.size(), "limit": limit}}


func _collect_files(path: String, output: Array[String], limit: int, depth: int) -> void:
	if output.size() >= limit or depth > MAX_DEPTH:
		return
	var directory := DirAccess.open(path)
	if directory == null:
		return
	for file_name in directory.get_files():
		if output.size() >= limit:
			return
		var lower := file_name.to_lower()
		if file_name.begins_with(".") or lower.ends_with(".import") or _is_sensitive_file(file_name):
			continue
		output.append(path.path_join(file_name))
	for directory_name in directory.get_directories():
		if output.size() >= limit:
			return
		if directory_name.begins_with(".") or directory_name.to_lower() in [".godot", ".git", "node_modules", ".import"]:
			continue
		_collect_files(path.path_join(directory_name), output, limit, depth + 1)


func _inspect_current_scene() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return {"ok": false, "result": {"error": "No hay una escena abierta."}}
	var nodes: Array[Dictionary] = []
	_collect_nodes(root, nodes, 0)
	return {"ok": true, "result": {
		"scene_path": root.scene_file_path,
		"root_name": str(root.name),
		"nodes": nodes,
		"node_count": nodes.size()
	}}


func _collect_nodes(node: Node, output: Array[Dictionary], depth: int) -> void:
	if output.size() >= MAX_NODES:
		return
	output.append({
		"name": str(node.name),
		"class": node.get_class(),
		"path": str(node.get_path()),
		"child_count": node.get_child_count()
	})
	if depth >= MAX_DEPTH:
		return
	for child in node.get_children():
		if output.size() >= MAX_NODES:
			return
		_collect_nodes(child, output, depth + 1)


func _read_script(args: Dictionary) -> Dictionary:
	var path := str(args.get("path", ""))
	if not path.begins_with("res://") or path.contains("..") or path.contains("\\"):
		return {"ok": false, "result": {"error": "Ruta no válida."}}
	var extension := "." + path.get_extension().to_lower()
	if extension not in ALLOWED_EXTENSIONS or _is_sensitive_file(path.get_file()):
		return {"ok": false, "result": {"error": "Tipo de archivo no permitido."}}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {"ok": false, "result": {"error": "No se pudo abrir el archivo."}}
	if file.get_length() > MAX_SCRIPT_BYTES:
		file.close()
		return {"ok": false, "result": {"error": "El archivo supera el límite de lectura."}}
	var content := file.get_as_text()
	file.close()
	return {"ok": true, "result": {"path": path, "text": content}}


func _is_sensitive_file(file_name: String) -> bool:
	var lower := file_name.get_file().to_lower()
	return lower.begins_with(".env") or lower in ["credentials.json", "secrets.json", "id_rsa", "id_ed25519"] or lower.ends_with(".pem") or lower.ends_with(".key") or lower.ends_with(".p12") or lower.ends_with(".pfx") or lower.ends_with(".keystore") or lower.ends_with(".jks")


func _is_uuid(value: String) -> bool:
	var regex := RegEx.new()
	regex.compile("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
	return regex.search(value) != null


func _set_status(value: String) -> void:
	if is_instance_valid(_status):
		_status.text = value