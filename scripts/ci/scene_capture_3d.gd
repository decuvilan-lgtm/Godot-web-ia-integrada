extends SceneTree

const OUTPUT_DIR := "/tmp/godot-task-results/multiview"
const IMAGE_SIZE := Vector2i(1280, 720)
const VIEW_COUNT := 8

var _capture_report: Array[Dictionary] = []


func _initialize() -> void:
    call_deferred("_run")


func _run() -> void:
    var scene_paths: Array[String] = []
    _collect_scenes("res://", scene_paths)
    scene_paths.sort()
    var captured_scene_count := 0

    DirAccess.make_dir_recursive_absolute(OUTPUT_DIR)

    for scene_path in scene_paths:
        var packed := load(scene_path) as PackedScene
        if packed == null:
            continue
        var scene_instance := packed.instantiate()
        if scene_instance == null:
            continue

        var meshes: Array[MeshInstance3D] = []
        _collect_meshes(scene_instance, meshes)
        if meshes.is_empty():
            scene_instance.free()
            continue

        var viewport := SubViewport.new()
        viewport.size = IMAGE_SIZE
        viewport.own_world_3d = true
        viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
        viewport.transparent_bg = false
        root.add_child(viewport)
        viewport.add_child(scene_instance)

        var bounds := _calculate_bounds(meshes)
        var center := bounds.position + bounds.size * 0.5
        var extent := maxf(bounds.size.x, maxf(bounds.size.y, bounds.size.z))
        var distance := maxf(extent * 2.8, 4.0)

        var environment := WorldEnvironment.new()
        var environment_data := Environment.new()
        environment_data.background_mode = Environment.BG_COLOR
        environment_data.background_color = Color(0.055, 0.065, 0.085, 1.0)
        environment_data.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
        environment_data.ambient_light_color = Color(0.72, 0.76, 0.84, 1.0)
        environment_data.ambient_light_energy = 0.8
        environment.environment = environment_data
        viewport.add_child(environment)

        var light := DirectionalLight3D.new()
        light.rotation_degrees = Vector3(-48.0, -32.0, 0.0)
        light.light_energy = 1.2
        light.shadow_enabled = true
        viewport.add_child(light)

        var camera := Camera3D.new()
        camera.fov = 55.0
        camera.near = 0.05
        camera.far = maxf(1000.0, distance * 20.0)
        viewport.add_child(camera)
        camera.current = true

        var safe_name := scene_path.get_file().get_basename().validate_filename()
        for view_index in range(VIEW_COUNT):
            var angle := TAU * float(view_index) / float(VIEW_COUNT)
            var elevation := 0.28 if view_index % 2 == 0 else 0.58
            var horizontal := Vector2(cos(angle), sin(angle)) * distance
            camera.position = center + Vector3(horizontal.x, extent * elevation + 0.2, horizontal.y)
            camera.look_at(center, Vector3.UP)
            await process_frame
            await process_frame
            await RenderingServer.frame_post_draw
            var image := viewport.get_texture().get_image()
            var filename := "%s_view_%02d.png" % [safe_name, view_index + 1]
            var output_path := OUTPUT_DIR.path_join(filename)
            var save_error := image.save_png(output_path)
            if save_error != OK:
                push_error("Failed to save 3D capture: " + output_path)
                quit(20)
                return
            _capture_report.append({
                "scene": scene_path,
                "view_index": view_index + 1,
                "camera_position": [camera.global_position.x, camera.global_position.y, camera.global_position.z],
                "target": [center.x, center.y, center.z],
                "image": output_path,
                "width": image.get_width(),
                "height": image.get_height(),
                "bytes": FileAccess.get_file_as_bytes(output_path).size()
            })

        viewport.queue_free()
        await process_frame
        captured_scene_count += 1

    var report_path := "/tmp/godot-task-results/multiview.json"
    var report := FileAccess.open(report_path, FileAccess.WRITE)
    if report == null:
        push_error("Unable to write multiview capture report")
        quit(21)
        return
    report.store_string(JSON.stringify({
        "format_version": 1,
        "renderer": "Godot 4.7.2 gl_compatibility with Mesa software rendering",
        "view_count_per_scene": VIEW_COUNT,
        "captured_scene_count": captured_scene_count,
        "captures": _capture_report
    }, "\t"))
    report.close()

    if captured_scene_count == 0:
        push_error("No 3D scenes with MeshInstance3D nodes were found for multiview capture")
        quit(22)
        return
    print("GODOT_MULTIVIEW_CAPTURE_COUNT=" + str(_capture_report.size()))
    quit(0)


func _collect_scenes(directory_path: String, output: Array[String]) -> void:
    var directory := DirAccess.open(directory_path)
    if directory == null:
        return
    directory.list_dir_begin()
    var entry := directory.get_next()
    while entry != "":
        if entry.begins_with(".") or entry == "addons":
            entry = directory.get_next()
            continue
        var full_path := directory_path.path_join(entry)
        if directory.current_is_dir():
            _collect_scenes(full_path, output)
        elif entry.ends_with(".tscn"):
            output.append(full_path)
        entry = directory.get_next()
    directory.list_dir_end()


func _collect_meshes(node: Node, output: Array[MeshInstance3D]) -> void:
    if node is MeshInstance3D:
        output.append(node as MeshInstance3D)
    for child in node.get_children():
        _collect_meshes(child, output)


func _calculate_bounds(meshes: Array[MeshInstance3D]) -> AABB:
    var combined := AABB()
    var has_bounds := false
    for mesh_instance in meshes:
        if mesh_instance.mesh == null:
            continue
        var mesh_bounds := mesh_instance.global_transform * mesh_instance.mesh.get_aabb()
        if not has_bounds:
            combined = mesh_bounds
            has_bounds = true
        else:
            combined = combined.merge(mesh_bounds)
    if not has_bounds:
        return AABB(Vector3.ZERO, Vector3.ONE)
    return combined
