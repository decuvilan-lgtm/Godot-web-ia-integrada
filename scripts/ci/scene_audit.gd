extends SceneTree

const OUTPUT_PATH := "/tmp/godot-task-results/scene-audit.json"

var _report := {
    "format_version": 1,
    "project": {},
    "summary": {
        "scene_count": 0,
        "node_count": 0,
        "node3d_count": 0,
        "mesh_instance3d_count": 0,
        "camera3d_count": 0,
        "light3d_count": 0,
        "skeleton3d_count": 0,
        "animation_player_count": 0
    },
    "scenes": [],
    "errors": []
}


func _initialize() -> void:
    call_deferred("_run")


func _run() -> void:
    _report["project"] = {
        "name": str(ProjectSettings.get_setting("application/config/name", "Godot project")),
        "main_scene": str(ProjectSettings.get_setting("application/run/main_scene", "")),
        "engine_version": Engine.get_version_info()
    }

    var scene_paths: Array[String] = []
    _collect_scenes("res://", scene_paths)
    scene_paths.sort()

    for scene_path in scene_paths:
        var packed := load(scene_path) as PackedScene
        if packed == null:
            _report["errors"].append({"scene": scene_path, "error": "PackedScene could not be loaded"})
            continue

        var instance := packed.instantiate()
        if instance == null:
            _report["errors"].append({"scene": scene_path, "error": "PackedScene could not be instantiated"})
            continue

        root.add_child(instance)
        await process_frame
        var scene_data := {
            "path": scene_path,
            "root": _inspect_node(instance)
        }
        _report["scenes"].append(scene_data)
        instance.queue_free()
        await process_frame

    _report["summary"]["scene_count"] = _report["scenes"].size()
    var summary: Dictionary = _report["summary"]
    var missing_3d_evidence: Array[String] = []
    if int(summary["node3d_count"]) < 1:
        missing_3d_evidence.append("Node3D")
    if int(summary["mesh_instance3d_count"]) < 1:
        missing_3d_evidence.append("MeshInstance3D")
    if int(summary["camera3d_count"]) < 1:
        missing_3d_evidence.append("Camera3D")
    if not missing_3d_evidence.is_empty():
        _report["errors"].append({
            "error": "3D audit fixture/coverage incomplete",
            "missing": missing_3d_evidence
        })
    var output := FileAccess.open(OUTPUT_PATH, FileAccess.WRITE)
    if output == null:
        push_error("Unable to write scene audit to " + OUTPUT_PATH)
        quit(10)
        return
    output.store_string(JSON.stringify(_report, "\t"))
    output.close()
    print("GODOT_SCENE_AUDIT=" + JSON.stringify(_report))
    quit(6 if not missing_3d_evidence.is_empty() else 0)


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


func _inspect_node(node: Node) -> Dictionary:
    _report["summary"]["node_count"] += 1
    var data := {
        "name": str(node.name),
        "class": node.get_class(),
        "path": str(node.get_path()),
        "children": []
    }

    if node is Node3D:
        _report["summary"]["node3d_count"] += 1
        var spatial := node as Node3D
        var transform := spatial.global_transform
        data["transform"] = {
            "position": _vector3(transform.origin),
            "rotation_degrees": _vector3(spatial.global_rotation_degrees),
            "scale": _vector3(transform.basis.get_scale()),
            "basis_x": _vector3(transform.basis.x),
            "basis_y": _vector3(transform.basis.y),
            "basis_z": _vector3(transform.basis.z)
        }

    if node is MeshInstance3D:
        _report["summary"]["mesh_instance3d_count"] += 1
        var mesh_instance := node as MeshInstance3D
        var mesh_data := {"mesh": null, "materials": []}
        if mesh_instance.mesh != null:
            var mesh := mesh_instance.mesh
            mesh_data["mesh"] = {
                "class": mesh.get_class(),
                "resource_path": mesh.resource_path,
                "surface_count": mesh.get_surface_count(),
                "aabb_position": _vector3(mesh.get_aabb().position),
                "aabb_size": _vector3(mesh.get_aabb().size)
            }
            for surface_index in range(mesh.get_surface_count()):
                var material := mesh_instance.get_surface_override_material(surface_index)
                if material == null:
                    material = mesh.surface_get_material(surface_index)
                if material != null:
                    mesh_data["materials"].append(_inspect_material(material, surface_index))
        if mesh_instance.material_override != null:
            mesh_data["material_override"] = _inspect_material(mesh_instance.material_override, -1)
        data["mesh_data"] = mesh_data

    if node is Camera3D:
        _report["summary"]["camera3d_count"] += 1
        var camera := node as Camera3D
        data["camera"] = {
            "current": camera.current,
            "projection": camera.projection,
            "fov": camera.fov,
            "size": camera.size,
            "near": camera.near,
            "far": camera.far,
            "keep_aspect": camera.keep_aspect
        }

    if node is Light3D:
        _report["summary"]["light3d_count"] += 1
        var light := node as Light3D
        data["light"] = {
            "class": light.get_class(),
            "color": _color(light.light_color),
            "energy": light.light_energy,
            "shadow_enabled": light.shadow_enabled
        }

    if node is Skeleton3D:
        _report["summary"]["skeleton3d_count"] += 1
        data["skeleton"] = {"bone_count": (node as Skeleton3D).get_bone_count()}

    if node is AnimationPlayer:
        _report["summary"]["animation_player_count"] += 1
        var animation_player := node as AnimationPlayer
        data["animations"] = {
            "current": animation_player.current_animation,
            "available": animation_player.get_animation_list()
        }

    for child in node.get_children():
        data["children"].append(_inspect_node(child))
    return data


func _inspect_material(material: Material, surface_index: int) -> Dictionary:
    var data := {
        "surface": surface_index,
        "class": material.get_class(),
        "resource_path": material.resource_path
    }
    if material is StandardMaterial3D:
        var standard := material as StandardMaterial3D
        data["albedo_color"] = _color(standard.albedo_color)
        data["metallic"] = standard.metallic
        data["roughness"] = standard.roughness
        data["emission_enabled"] = standard.emission_enabled
        data["transparency"] = standard.transparency
    return data


func _vector3(value: Vector3) -> Array:
    return [value.x, value.y, value.z]


func _color(value: Color) -> Array:
    return [value.r, value.g, value.b, value.a]
