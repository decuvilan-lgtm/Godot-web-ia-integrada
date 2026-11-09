@tool
extends EditorPlugin

const API_DEFAULT := "https://godot-web-ia-relay.onrender.com"
const MAX_FILE_BYTES := 32 * 1024 * 1024
const MAX_FILES := 10000
const MAX_OPERATIONS_PER_SYNC := 500

var _dock: ScrollContainer
var _panel: VBoxContainer
var _api_input: LineEdit
var _label_input: LineEdit
var _pair_code_input: LineEdit
var _slug_input: LineEdit
var _name_input: LineEdit
var _project_select: OptionButton
var _status: Label
var _preview: TextEdit
var _pair_button: Button
var _refresh_button: Button
var _analyze_button: Button
var _sync_button: Button
var _clone_button: Button
var _clone_confirmation: ConfirmationDialog
var _clone_project_id := ""
var _clone_manifest: Dictionary = {}
var _credential := ""
var _device_id := ""
var _installation_id := ""
var _busy := false
var _analyzed_project_id := ""
var _analyzed_plan_fingerprint := ""

func _enter_tree() -> void:
	_build_ui()
	_ensure_installation_id()
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)

func _exit_tree() -> void:
	_credential = ""
	if is_instance_valid(_dock):
		remove_control_from_docks(_dock)
		_dock.queue_free()

func _build_ui() -> void:
	_dock = ScrollContainer.new()
	_dock.name = "Shared Projects"
	_dock.custom_minimum_size = Vector2(280, 300)
	_panel = VBoxContainer.new()
	_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_dock.add_child(_panel)
	var title := Label.new()
	title.text = "Shared Projects · Web / Android"
	_panel.add_child(title)
	_api_input = LineEdit.new()
	_api_input.text = API_DEFAULT
	_panel.add_child(_field("Relay HTTPS", _api_input))
	_label_input = LineEdit.new()
	_label_input.text = "Godot Editor"
	_label_input.max_length = 80
	_panel.add_child(_field("Nombre de este editor", _label_input))
	_pair_code_input = LineEdit.new()
	_pair_code_input.secret = true
	_pair_code_input.placeholder_text = "Código temporal de emparejamiento"
	_panel.add_child(_field("Código de emparejamiento", _pair_code_input))
	_pair_button = Button.new()
	_pair_button.text = "Emparejar este editor"
	_pair_button.pressed.connect(_pair_editor)
	_panel.add_child(_pair_button)
	_panel.add_child(HSeparator.new())
	_slug_input = LineEdit.new()
	_slug_input.placeholder_text = "mi-proyecto"
	_panel.add_child(_field("Identificador del proyecto nuevo", _slug_input))
	_name_input = LineEdit.new()
	_name_input.placeholder_text = "Mi proyecto"
	_panel.add_child(_field("Nombre visible", _name_input))
	var create_button := Button.new()
	create_button.text = "Crear proyecto compartido"
	create_button.pressed.connect(_create_project)
	_panel.add_child(create_button)
	_project_select = OptionButton.new()
	_project_select.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_panel.add_child(_field("Proyecto compartido", _project_select))
	_refresh_button = Button.new()
	_refresh_button.text = "Actualizar lista"
	_refresh_button.pressed.connect(_refresh_projects)
	_panel.add_child(_refresh_button)
	_analyze_button = Button.new()
	_analyze_button.text = "Analizar cambios"
	_analyze_button.pressed.connect(_analyze_changes)
	_panel.add_child(_analyze_button)
	_preview = TextEdit.new()
	_preview.editable = false
	_preview.custom_minimum_size = Vector2(0, 150)
	_preview.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	_preview.text = "El análisis mostrará aquí los archivos que se subirán, descargarán o eliminarán."
	_panel.add_child(_preview)
	_sync_button = Button.new()
	_sync_button.text = "Sincronizar ahora"
	_sync_button.pressed.connect(_sync_now)
	_panel.add_child(_sync_button)
	_clone_button = Button.new()
	_clone_button.text = "Clonar remoto aquí (reemplaza archivos)"
	_clone_button.tooltip_text = "Crea una copia de rescate y reemplaza los archivos del proyecto con la versión compartida."
	_clone_button.pressed.connect(_prepare_remote_clone)
	_panel.add_child(_clone_button)
	_clone_confirmation = ConfirmationDialog.new()
	_clone_confirmation.title = "Clonar proyecto compartido"
	_clone_confirmation.ok_button_text = "Clonar y reemplazar"
	_clone_confirmation.cancel_button_text = "Cancelar"
	_clone_confirmation.confirmed.connect(_execute_remote_clone)
	add_child(_clone_confirmation)
	var forget := Button.new()
	forget.text = "Desconectar editor"
	forget.pressed.connect(_forget_editor)
	_panel.add_child(forget)
	_status = Label.new()
	_status.text = "Sin emparejar. Los dos editores deben usar el mismo workspace."
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_panel.add_child(_status)

func _field(caption: String, control: Control) -> VBoxContainer:
	var box := VBoxContainer.new()
	var label := Label.new()
	label.text = caption
	box.add_child(label)
	box.add_child(control)
	return box

func _ensure_installation_id() -> void:
	var settings := EditorInterface.get_editor_settings()
	var key := "godot_project_sync/installation_id"
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

func _request(path: String, method: int, body: PackedByteArray, extra_headers: PackedStringArray = PackedStringArray()) -> Dictionary:
	if not _valid_api_url():
		return {"ok": false, "code": 0, "error": "La URL del relay debe ser HTTPS."}
	var headers := PackedStringArray(["Accept: application/json"])
	if not _credential.is_empty():
		headers.append("Authorization: Bearer " + _credential)
	for header in extra_headers:
		headers.append(header)
	var request_node := HTTPRequest.new()
	request_node.timeout = 120.0
	request_node.max_redirects = 0
	add_child(request_node)
	var error := request_node.request_raw(_api_base() + path, headers, method, body)
	if error != OK:
		request_node.queue_free()
		return {"ok": false, "code": 0, "error": error_string(error)}
	var response: Array = await request_node.request_completed
	request_node.queue_free()
	var result_code: int = int(response[0])
	var http_code: int = int(response[1])
	return {
		"ok": result_code == HTTPRequest.RESULT_SUCCESS and http_code >= 200 and http_code < 300,
		"transport_result": result_code,
		"code": http_code,
		"headers": response[2],
		"body": response[3]
	}

func _json_request(path: String, method: int, payload: Dictionary) -> Dictionary:
	var body := PackedByteArray()
	var headers := PackedStringArray()
	if method != HTTPClient.METHOD_GET:
		body = JSON.stringify(payload).to_utf8_buffer()
		headers.append("Content-Type: application/json")
	var response: Dictionary = await _request(path, method, body, headers)
	if not bool(response.get("ok", false)):
		return {"ok": false, "code": response.get("code", 0), "error": _response_error(response)}
	var response_body: PackedByteArray = response.get("body", PackedByteArray())
	var parsed: Variant = JSON.parse_string(response_body.get_string_from_utf8())
	if not parsed is Dictionary:
		return {"ok": false, "code": response["code"], "error": "El relay devolvió JSON inválido."}
	return {"ok": true, "code": response["code"], "data": parsed, "headers": response["headers"]}

func _response_error(response: Dictionary) -> String:
	var body: PackedByteArray = response.get("body", PackedByteArray())
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	if parsed is Dictionary:
		return str(parsed.get("detail", "Error HTTP " + str(response.get("code", 0))))
	return str(response.get("error", "Error HTTP " + str(response.get("code", 0))))

func _pair_editor() -> void:
	if _busy or not _credential.is_empty():
		return
	var code := _pair_code_input.text.strip_edges()
	var label := _label_input.text.strip_edges()
	if code.length() < 24 or code.length() > 128 or label.is_empty():
		_set_status("Revisa el código temporal y el nombre del editor.")
		return
	_busy = true
	var response: Dictionary = await _json_request("/v1/command-center/pair", HTTPClient.METHOD_POST, {
		"pairing_code": code, "label": label, "installation_id": _installation_id
	})
	_busy = false
	if not response.ok:
		_set_status("No se pudo emparejar: " + str(response.error))
		return
	var data: Dictionary = response.data
	var credential := str(data.get("device_credential", ""))
	var kind := str(data.get("device_kind", ""))
	var device_id := str(data.get("device_id", ""))
	if credential.length() < 32 or kind not in ["web_editor", "android_editor"] or device_id.is_empty():
		_set_status("El servidor no confirmó una identidad de editor válida.")
		return
	_credential = credential
	_device_id = device_id
	_pair_code_input.clear()
	_pair_code_input.editable = false
	_api_input.editable = false
	_label_input.editable = false
	_pair_button.disabled = true
	_set_status("Emparejado como " + kind + ". Credencial guardada solo en memoria.")
	await _refresh_projects()

func _forget_editor() -> void:
	_credential = ""
	_device_id = ""
	_analyzed_project_id = ""
	_analyzed_plan_fingerprint = ""
	_clone_project_id = ""
	_clone_manifest = {}
	if is_instance_valid(_clone_confirmation):
		_clone_confirmation.hide()
	_pair_code_input.editable = true
	_api_input.editable = true
	_label_input.editable = true
	_pair_button.disabled = false
	_project_select.clear()
	_set_status("Editor desconectado. La credencial en memoria fue descartada.")

func _selected_project_id() -> String:
	if _project_select.item_count == 0 or _project_select.selected < 0:
		return ""
	return str(_project_select.get_item_metadata(_project_select.selected))

func _refresh_projects() -> void:
	if _busy or _credential.is_empty():
		return
	_busy = true
	var response: Dictionary = await _json_request("/v1/command-center/projects", HTTPClient.METHOD_GET, {})
	_busy = false
	if not response.ok:
		_set_status("No se pudo actualizar la lista: " + str(response.error))
		return
	_project_select.clear()
	var projects: Array = response.data.get("projects", [])
	for project in projects:
		var index := _project_select.item_count
		_project_select.add_item(str(project.get("display_name", project.get("slug", "Proyecto"))))
		_project_select.set_item_metadata(index, str(project.get("id", "")))
	if projects.is_empty():
		_set_status("No hay proyectos compartidos en este workspace. Crea uno desde uno de los editores.")
	else:
		_set_status(str(projects.size()) + " proyecto(s) compartido(s). Selecciona uno para analizar o sincronizar.")

func _create_project() -> void:
	if _busy or _credential.is_empty():
		_set_status("Empareja primero este editor.")
		return
	var slug := _slug_input.text.strip_edges().to_lower()
	var display_name := _name_input.text.strip_edges()
	if slug.length() < 2 or display_name.is_empty():
		_set_status("Indica un identificador y un nombre para el proyecto.")
		return
	_busy = true
	var response: Dictionary = await _json_request("/v1/command-center/projects", HTTPClient.METHOD_POST, {
		"slug": slug, "display_name": display_name
	})
	_busy = false
	if not response.ok:
		_set_status("No se pudo crear el proyecto: " + str(response.error))
		return
	_slug_input.clear()
	_name_input.clear()
	_set_status("Proyecto compartido creado. Actualizando lista…")
	await _refresh_projects()

func _analyze_changes() -> void:
	if _busy:
		return
	var project_id := _selected_project_id()
	if project_id.is_empty():
		_set_status("Selecciona un proyecto compartido.")
		return
	_analyzed_project_id = project_id
	_analyzed_plan_fingerprint = ""
	_busy = true
	var plan: Dictionary = await _build_plan(project_id)
	_busy = false
	if not plan.ok:
		_set_status("No se pudo analizar: " + str(plan.error))
		return
	var operations: Array = plan.operations
	var conflicts: Array = plan.conflicts
	_analyzed_project_id = project_id
	_analyzed_plan_fingerprint = ""
	_preview.text = _format_plan(plan)
	if not conflicts.is_empty():
		_set_status("Conflictos: " + str(conflicts.size()) + ". No se modificó ningún archivo. " + _summarize_paths(conflicts))
	else:
		_analyzed_plan_fingerprint = _plan_fingerprint(plan)
		_set_status("Plan listo para revisar · " + str(operations.size()) + " operación(es): " + _count_operations(operations) + ". Pulsa Sincronizar solo si aceptas esta lista.")

func _sync_now() -> void:
	if _busy:
		return
	var project_id := _selected_project_id()
	if project_id.is_empty():
		_set_status("Selecciona un proyecto compartido.")
		return
	if _analyzed_project_id != project_id or _analyzed_plan_fingerprint.is_empty():
		_set_status("Analiza los cambios y revisa la lista antes de sincronizar.")
		return
	_busy = true
	var plan: Dictionary = await _build_plan(project_id)
	if not plan.ok:
		_busy = false
		_analyzed_plan_fingerprint = ""
		_set_status("No se pudo preparar la sincronización: " + str(plan.error))
		return
	if _plan_fingerprint(plan) != _analyzed_plan_fingerprint:
		_busy = false
		_analyzed_plan_fingerprint = ""
		_preview.text = _format_plan(plan)
		_set_status("El proyecto cambió desde el análisis. Revisa el nuevo plan y vuelve a analizar antes de sincronizar.")
		return
	if not plan.conflicts.is_empty():
		_busy = false
		_analyzed_plan_fingerprint = ""
		_set_status("Sincronización detenida: " + str(plan.conflicts.size()) + " conflicto(s). No se modificó ningún archivo. " + _summarize_paths(plan.conflicts))
		return
	if plan.operations.size() > MAX_OPERATIONS_PER_SYNC:
		_busy = false
		_analyzed_plan_fingerprint = ""
		_set_status("Hay " + str(plan.operations.size()) + " operaciones. El límite seguro por tanda es " + str(MAX_OPERATIONS_PER_SYNC) + "; vuelve a analizar después de cada tanda.")
		return
	var total: int = plan.operations.size()
	var completed := 0
	for operation in plan.operations:
		_set_status("Sincronizando " + str(completed + 1) + "/" + str(total) + " · " + str(operation.path))
		var applied: Dictionary = await _apply_operation(project_id, operation)
		if not applied.ok:
			_busy = false
			_analyzed_plan_fingerprint = ""
			_set_status("Sincronización parcial detenida en " + str(operation.path) + ": " + str(applied.error) + ". El punto de control no avanzó; vuelve a analizar.")
			return
		completed += 1
	var manifest: Dictionary = await _fetch_manifest(project_id)
	if not manifest.ok:
		_busy = false
		_analyzed_plan_fingerprint = ""
		_set_status("Los cambios se aplicaron, pero no se pudo confirmar el manifiesto final. Vuelve a analizar antes de continuar.")
		return
	if not _save_baseline(project_id, manifest.files, manifest.head_revision):
		_busy = false
		_analyzed_plan_fingerprint = ""
		_set_status("No se pudo guardar el punto de control local. Vuelve a analizar antes de continuar.")
		return
	_busy = false
	_analyzed_project_id = ""
	_analyzed_plan_fingerprint = ""
	_preview.text = "Sincronización completada. Analiza de nuevo para revisar nuevos cambios."
	_set_status("Sincronización completada · " + str(completed) + " operación(es) · revisión " + str(manifest.head_revision) + ".")
	await _refresh_projects()

func _build_plan(project_id: String) -> Dictionary:
	var local_result: Dictionary = _scan_local_project()
	if not local_result.ok:
		return {"ok": false, "error": local_result.error}
	var remote_result: Dictionary = await _fetch_manifest(project_id)
	if not remote_result.ok:
		return {"ok": false, "error": remote_result.error}
	var local_files: Dictionary = local_result.files
	var remote_files: Dictionary = remote_result.files
	var baseline: Dictionary = _load_baseline(project_id)
	var has_baseline := baseline.has("files") and baseline.files is Dictionary
	var base_files: Dictionary = baseline.get("files", {})
	var all_paths: Dictionary = {}
	for path in local_files:
		all_paths[path] = true
	for path in remote_files:
		all_paths[path] = true
	for path in base_files:
		all_paths[path] = true
	var operations: Array[Dictionary] = []
	var conflicts: Array[String] = []
	var ordered_paths: Array = all_paths.keys()
	ordered_paths.sort()
	for path_value in ordered_paths:
		var path := str(path_value)
		var local_sha := str(local_files.get(path, ""))
		var remote_sha := str(remote_files.get(path, ""))
		var base_sha := str(base_files.get(path, ""))
		if not has_baseline:
			if not local_sha.is_empty() and not remote_sha.is_empty():
				if local_sha != remote_sha:
					conflicts.append(path)
			elif not local_sha.is_empty():
				operations.append({"type": "push", "path": path, "local_sha": local_sha, "remote_sha": ""})
			elif not remote_sha.is_empty():
				operations.append({"type": "pull", "path": path, "remote_sha": remote_sha})
			continue
		var local_changed := local_sha != base_sha
		var remote_changed := remote_sha != base_sha
		if local_changed and remote_changed:
			if local_sha != remote_sha:
				conflicts.append(path)
		elif local_changed:
			if local_sha.is_empty():
				if not remote_sha.is_empty():
					operations.append({"type": "delete_remote", "path": path, "remote_sha": remote_sha})
			else:
				operations.append({"type": "push", "path": path, "local_sha": local_sha, "remote_sha": remote_sha})
		elif remote_changed:
			if remote_sha.is_empty():
				if not local_sha.is_empty():
					operations.append({"type": "delete_local", "path": path, "local_sha": local_sha})
			else:
				operations.append({"type": "pull", "path": path, "remote_sha": remote_sha})
	return {"ok": true, "operations": operations, "conflicts": conflicts,
		"head_revision": remote_result.head_revision, "files": remote_files}



func _prepare_remote_clone() -> void:
	if _busy or _credential.is_empty():
		_set_status("Empareja este editor antes de clonar un proyecto.")
		return
	var project_id := _selected_project_id()
	if project_id.is_empty():
		_set_status("Selecciona un proyecto compartido.")
		return
	_busy = true
	var remote: Dictionary = await _fetch_manifest(project_id)
	var local: Dictionary = _scan_local_project()
	_busy = false
	if not remote.ok:
		_set_status("No se pudo leer el proyecto remoto: " + str(remote.error))
		return
	if not local.ok:
		_set_status("No se puede preparar el respaldo local: " + str(local.error))
		return
	if remote.files.is_empty():
		_set_status("El proyecto remoto está vacío. Primero sube los archivos desde el otro editor.")
		return
	if remote.files.size() > MAX_FILES:
		_set_status("El proyecto remoto supera el límite de " + str(MAX_FILES) + " archivos.")
		return
	var total_bytes := 0
	for path in remote.file_sizes:
		total_bytes += int(remote.file_sizes[path])
	_clone_project_id = project_id
	_clone_manifest = remote
	_clone_confirmation.dialog_text = "Se reemplazarán los archivos sincronizables de este proyecto por la revisión remota %d (%d archivos, %.1f MiB). Antes de reemplazar o borrar cada archivo local se guardará una copia en user://godot_project_sync/rescue/. La clonación se detendrá si el proyecto remoto cambia durante la operación. ¿Continuar?" % [
		int(remote.head_revision), remote.files.size(), float(total_bytes) / 1048576.0
	]
	_clone_confirmation.popup_centered(Vector2i(560, 260))


func _execute_remote_clone() -> void:
	if _busy or _credential.is_empty() or _clone_project_id.is_empty():
		return
	if _selected_project_id() != _clone_project_id:
		_set_status("La selección cambió. Vuelve a preparar la clonación.")
		_clone_project_id = ""
		return
	_busy = true
	var local_result: Dictionary = _scan_local_project()
	if not local_result.ok:
		_busy = false
		_set_status("No se pudo analizar el proyecto local: " + str(local_result.error))
		return
	var local_files: Dictionary = local_result.files
	var remote_files: Dictionary = _clone_manifest.files
	var paths: Array = remote_files.keys()
	paths.sort()
	var completed := 0
	for path_value in paths:
		var path := str(path_value)
		var expected_sha := str(remote_files[path])
		var local_sha := str(local_files.get(path, ""))
		if local_sha == expected_sha:
			completed += 1
			continue
		var target := "res://" + path
		if FileAccess.file_exists(target):
			if _hash_file(target) != local_sha:
				_busy = false
				_set_status("El archivo local cambió durante la clonación: " + path + ". No se sobrescribió.")
				_clone_project_id = ""
				return
			if not _rescue_local_file(_clone_project_id, path, target):
				_busy = false
				_set_status("No se pudo respaldar el archivo local: " + path)
				_clone_project_id = ""
				return
		_set_status("Clonando %d/%d · %s" % [completed + 1, paths.size(), path])
		var url := "/v1/command-center/projects/" + _clone_project_id + "/files/content?path=" + path.uri_encode()
		var downloaded: Dictionary = await _request(url, HTTPClient.METHOD_GET, PackedByteArray())
		if not downloaded.ok:
			_busy = false
			_set_status("Descarga detenida en " + path + ": " + _response_error(downloaded) + ". Los archivos anteriores tienen respaldo; puedes volver a clonar.")
			_clone_project_id = ""
			return
		var bytes: PackedByteArray = downloaded.body
		var digest := _response_header(downloaded.headers, "X-File-SHA256")
		if digest != expected_sha or _hash_bytes(bytes) != digest:
			_busy = false
			_set_status("La verificación SHA-256 falló para " + path + ". No se aplicó ese archivo.")
			_clone_project_id = ""
			return
		if FileAccess.file_exists(target) and _hash_file(target) != local_sha:
			_busy = false
			_set_status("El archivo local cambió mientras se descargaba: " + path + ". No se sobrescribió.")
			_clone_project_id = ""
			return
		if not _write_file_atomically(target, bytes):
			_busy = false
			_set_status("No se pudo escribir " + path + ". Los archivos anteriores tienen respaldo.")
			_clone_project_id = ""
			return
		completed += 1
	for path_value in local_files.keys():
		var path := str(path_value)
		if remote_files.has(path):
			continue
		var target := "res://" + path
		if not FileAccess.file_exists(target):
			continue
		if _hash_file(target) != str(local_files[path]):
			_busy = false
			_set_status("El archivo local cambió durante la clonación: " + path + ". No se eliminó.")
			_clone_project_id = ""
			return
		if not _rescue_local_file(_clone_project_id, path, target):
			_busy = false
			_set_status("No se pudo respaldar antes de eliminar " + path)
			_clone_project_id = ""
			return
		if DirAccess.remove_absolute(ProjectSettings.globalize_path(target)) != OK:
			_busy = false
			_set_status("No se pudo eliminar el archivo local " + path)
			_clone_project_id = ""
			return
	var final_manifest: Dictionary = await _fetch_manifest(_clone_project_id)
	var final_local: Dictionary = _scan_local_project()
	if not final_manifest.ok or not final_local.ok:
		_busy = false
		_set_status("La clonación terminó parcialmente, pero no se pudo verificar el estado final. Vuelve a clonar.")
		_clone_project_id = ""
		return
	if int(final_manifest.head_revision) != int(_clone_manifest.head_revision) or final_manifest.files != remote_files or final_local.files != remote_files:
		_busy = false
		_set_status("El proyecto cambió durante la clonación o quedaron archivos locales distintos. No se avanzó el punto de control; vuelve a clonar.")
		_clone_project_id = ""
		return
	if not _save_baseline(_clone_project_id, final_manifest.files, final_manifest.head_revision):
		_busy = false
		_set_status("La clonación terminó, pero no se pudo guardar el punto de control. Vuelve a analizar.")
		_clone_project_id = ""
		return
	_busy = false
	_analyzed_project_id = ""
	_analyzed_plan_fingerprint = ""
	_preview.text = "Proyecto clonado desde la nube. Reabre el proyecto para recargar escenas y configuración."
	_set_status("Clonación completada · %d archivos verificados · revisión %d. Reabre el proyecto para recargar configuración." % [remote_files.size(), final_manifest.head_revision])
	_clone_project_id = ""
	_clone_manifest = {}


func _plan_fingerprint(plan: Dictionary) -> String:
	var parts := PackedStringArray()
	parts.append("head=" + str(plan.get("head_revision", 0)))
	for operation in plan.get("operations", []):
		parts.append("%s|%s|%s|%s" % [
			str(operation.get("type", "")), str(operation.get("path", "")),
			str(operation.get("local_sha", "")), str(operation.get("remote_sha", ""))
		])
	for conflict in plan.get("conflicts", []):
		parts.append("conflict|" + str(conflict))
	return _hash_bytes("\n".join(parts).to_utf8_buffer())


func _format_plan(plan: Dictionary) -> String:
	var lines := PackedStringArray()
	lines.append("Revisión remota: " + str(plan.get("head_revision", 0)))
	var operations: Array = plan.get("operations", [])
	var conflicts: Array = plan.get("conflicts", [])
	lines.append("Operaciones: " + str(operations.size()) + " · Conflictos: " + str(conflicts.size()))
	if operations.is_empty() and conflicts.is_empty():
		lines.append("No hay cambios pendientes.")
	for operation in operations:
		var kind := str(operation.get("type", ""))
		var prefix := "↑ Subir local" if kind == "push" else "↓ Descargar remoto" if kind == "pull" else "− Eliminar remoto" if kind == "delete_remote" else "− Eliminar local (con rescate)"
		lines.append(prefix + " · " + str(operation.get("path", "")))
	for conflict in conflicts:
		lines.append("⚠ Conflicto · " + str(conflict))
	if lines.size() > 45:
		lines.resize(45)
		lines.append("… Lista truncada en pantalla; el plan completo sigue protegido por el control de conflictos.")
	return "\n".join(lines)


func _scan_local_project() -> Dictionary:
	var output: Dictionary = {}
	var queue: Array[String] = ["res://"]
	while not queue.is_empty():
		var directory: String = queue.pop_back()
		var dir := DirAccess.open(directory)
		if dir == null:
			return {"ok": false, "error": "No se pudo abrir la carpeta " + directory}
		dir.list_dir_begin()
		while true:
			var entry := dir.get_next()
			if entry.is_empty():
				break
			if entry in [".", ".."] or dir.is_link(entry):
				continue
			var relative := directory.trim_prefix("res://")
			if not relative.is_empty():
				relative = relative.path_join(entry)
			else:
				relative = entry
			if dir.current_is_dir():
				if entry.to_lower() in [".git", ".godot"]:
					continue
				queue.append("res://" + relative)
				continue
			if not _is_syncable_path(relative):
				continue
			var source_file := FileAccess.open("res://" + relative, FileAccess.READ)
			if source_file == null:
				dir.list_dir_end()
				return {"ok": false, "error": "No se pudo abrir " + relative}
			var source_size: int = source_file.get_length()
			source_file.close()
			if source_size > MAX_FILE_BYTES:
				dir.list_dir_end()
				return {"ok": false, "error": relative + " supera el límite de 32 MiB por archivo."}
			var digest := _hash_file("res://" + relative)
			if digest.is_empty():
				dir.list_dir_end()
				return {"ok": false, "error": "No se pudo calcular el hash de " + relative}
			output[relative] = digest
			if output.size() > MAX_FILES:
				dir.list_dir_end()
				return {"ok": false, "error": "El proyecto supera el límite de " + str(MAX_FILES) + " archivos."}
		dir.list_dir_end()
	return {"ok": true, "files": output}

func _is_syncable_path(path: String) -> bool:
	var lowered := path.to_lower()
	var parts := lowered.split("/")
	for part in parts:
		if part in [".git", ".godot"]:
			return false
	var name := parts[parts.size() - 1]
	if name in [".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"]:
		return false
	for suffix in [".pem", ".key", ".p8", ".asc", ".gpg", ".p12", ".pfx", ".keystore", ".jks", ".mobileprovision"]:
		if name.ends_with(suffix):
			return false
	return not name.ends_with(".env") and not name.begins_with(".env.") and not name.ends_with(".godot_sync_tmp") and not name.ends_with(".godot_sync_backup")

func _hash_file(path: String) -> String:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return ""
	var hasher := HashingContext.new()
	if hasher.start(HashingContext.HASH_SHA256) != OK:
		file.close()
		return ""
	while not file.eof_reached():
		var chunk := file.get_buffer(65536)
		if chunk.is_empty():
			break
		hasher.update(chunk)
	file.close()
	return hasher.finish().hex_encode()

func _read_file_bytes(path: String) -> PackedByteArray:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return PackedByteArray()
	var size := file.get_length()
	if size > MAX_FILE_BYTES:
		file.close()
		return PackedByteArray()
	var bytes := file.get_buffer(size)
	file.close()
	return bytes

func _fetch_manifest(project_id: String) -> Dictionary:
	var response: Dictionary = await _json_request("/v1/command-center/projects/" + project_id + "/manifest", HTTPClient.METHOD_GET, {})
	if not response.ok:
		return {"ok": false, "error": response.error}
	var data: Dictionary = response.data
	var files: Dictionary = {}
	var file_sizes: Dictionary = {}
	for entry in data.get("files", []):
		if entry is Dictionary:
			var path := str(entry.get("path", ""))
			files[path] = str(entry.get("sha256", ""))
			file_sizes[path] = int(entry.get("byte_size", 0))
	return {"ok": true, "files": files, "file_sizes": file_sizes, "head_revision": int(data.get("head_revision", 0))}

func _apply_operation(project_id: String, operation: Dictionary) -> Dictionary:
	var path := str(operation.path)
	var kind := str(operation.type)
	if kind == "push":
		var bytes := _read_file_bytes("res://" + path)
		var digest := str(operation.local_sha)
		if _hash_bytes(bytes) != digest:
			return {"ok": false, "error": "El archivo local cambió durante la sincronización: " + path}
		var headers := PackedStringArray([
			"Content-Type: application/octet-stream",
			"X-File-SHA256: " + digest
		])
		var base_sha := str(operation.remote_sha)
		if not base_sha.is_empty():
			headers.append("X-Base-SHA256: " + base_sha)
		var uploaded: Dictionary = await _request("/v1/command-center/projects/" + project_id + "/files?path=" + path.uri_encode(), HTTPClient.METHOD_POST, bytes, headers)
		if not uploaded.ok:
			return {"ok": false, "error": _response_error(uploaded)}
		return {"ok": true}
	if kind == "delete_remote":
		var deleted: Dictionary = await _request(
			"/v1/command-center/projects/" + project_id + "/files/delete?path=" + path.uri_encode(),
			HTTPClient.METHOD_POST, PackedByteArray(),
			PackedStringArray(["X-Base-SHA256: " + str(operation.remote_sha)])
		)
		if not deleted.ok:
			return {"ok": false, "error": _response_error(deleted)}
		return {"ok": true}
	if kind == "pull":
		var url := "/v1/command-center/projects/" + project_id + "/files/content?path=" + path.uri_encode()
		var downloaded: Dictionary = await _request(url, HTTPClient.METHOD_GET, PackedByteArray())
		if not downloaded.ok:
			return {"ok": false, "error": _response_error(downloaded)}
		var bytes: PackedByteArray = downloaded.body
		var digest := _response_header(downloaded.headers, "X-File-SHA256")
		if digest != str(operation.remote_sha) or _hash_bytes(bytes) != digest:
			return {"ok": false, "error": "El archivo descargado no coincide con el hash del manifiesto."}
		var target := "res://" + path
		if FileAccess.file_exists(target) and not _rescue_local_file(project_id, path, target):
			return {"ok": false, "error": "No se pudo guardar una copia de rescate de " + path}
		if not _write_file_atomically(target, bytes):
			return {"ok": false, "error": "No se pudo escribir el archivo descargado " + path}
		return {"ok": true}
	if kind == "delete_local":
		var target := "res://" + path
		if FileAccess.file_exists(target):
			if not _rescue_local_file(project_id, path, target):
				return {"ok": false, "error": "No se pudo guardar una copia de rescate de " + path}
			if DirAccess.remove_absolute(ProjectSettings.globalize_path(target)) != OK:
				return {"ok": false, "error": "No se pudo eliminar el archivo sincronizado " + path}
		return {"ok": true}
	return {"ok": false, "error": "Operación de sincronización desconocida: " + kind}

func _hash_bytes(bytes: PackedByteArray) -> String:
	var hasher := HashingContext.new()
	hasher.start(HashingContext.HASH_SHA256)
	hasher.update(bytes)
	return hasher.finish().hex_encode()

func _response_header(headers: PackedStringArray, wanted: String) -> String:
	for header in headers:
		var parts := header.split(":", false, 1)
		if parts.size() == 2 and parts[0].strip_edges().to_lower() == wanted.to_lower():
			return parts[1].strip_edges()
	return ""

func _rescue_local_file(project_id: String, relative_path: String, source: String) -> bool:
	var bytes := _read_file_bytes(source)
	if _hash_bytes(bytes) != _hash_file(source):
		return false
	var rescue_root := "user://godot_project_sync/rescue/" + project_id + "/" + str(Time.get_ticks_usec())
	var rescue_path := rescue_root.path_join(relative_path)
	if DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(rescue_path.get_base_dir())) != OK:
		return false
	var file := FileAccess.open(rescue_path, FileAccess.WRITE)
	if file == null:
		return false
	file.store_buffer(bytes)
	file.flush()
	file.close()
	return true

func _write_file_atomically(target: String, bytes: PackedByteArray) -> bool:
	var absolute := ProjectSettings.globalize_path(target)
	if DirAccess.make_dir_recursive_absolute(absolute.get_base_dir()) != OK:
		return false
	var temporary := absolute + ".godot_sync_tmp"
	var backup := absolute + ".godot_sync_backup"
	var file := FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		return false
	file.store_buffer(bytes)
	file.flush()
	file.close()
	var had_original := FileAccess.file_exists(absolute)
	if had_original and DirAccess.rename_absolute(absolute, backup) != OK:
		DirAccess.remove_absolute(temporary)
		return false
	if DirAccess.rename_absolute(temporary, absolute) != OK:
		if had_original:
			DirAccess.rename_absolute(backup, absolute)
		DirAccess.remove_absolute(temporary)
		return false
	if had_original:
		DirAccess.remove_absolute(backup)
	return true

func _load_baseline(project_id: String) -> Dictionary:
	var path := "user://godot_project_sync/baselines/" + project_id + ".json"
	if not FileAccess.file_exists(path):
		return {}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	return parsed if parsed is Dictionary else {}

func _save_baseline(project_id: String, files: Dictionary, revision: int) -> bool:
	var directory := ProjectSettings.globalize_path("user://godot_project_sync/baselines")
	if DirAccess.make_dir_recursive_absolute(directory) != OK:
		return false
	var file := FileAccess.open("user://godot_project_sync/baselines/" + project_id + ".json", FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(JSON.stringify({"head_revision": revision, "files": files}))
	file.flush()
	file.close()
	return true

func _count_operations(operations: Array) -> String:
	var counts := {"push": 0, "pull": 0, "delete_remote": 0, "delete_local": 0}
	for operation in operations:
		var kind := str(operation.get("type", ""))
		if counts.has(kind):
			counts[kind] += 1
	return "subidas %d · descargas %d · eliminaciones remotas %d · eliminaciones locales %d" % [
		counts.push, counts.pull, counts.delete_remote, counts.delete_local
	]

func _summarize_paths(paths: Array) -> String:
	var sample := PackedStringArray()
	for index in range(mini(paths.size(), 8)):
		sample.append(str(paths[index]))
	return "Archivos: " + ", ".join(sample) + ("…" if paths.size() > sample.size() else "")

func _set_status(value: String) -> void:
	if is_instance_valid(_status):
		_status.text = value
