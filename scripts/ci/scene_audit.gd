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
        "animation_player_count": 0,
        "collision_shape3d_count": 0,
        "physics_body3d_count": 0,
        "multimesh_instance3d_count": 0
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

    if node is CollisionShape3D:
        _report["summary"]["collision_shape3d_count"] += 1
        var collision := node as CollisionShape3D
        data["collision_shape"] = _inspect_shape(collision.shape)

    if node is CollisionObject3D:
        var collision_object := node as CollisionObject3D
        data["collision_layers"] = {
            "layer": collision_object.collision_layer,
            "mask": collision_object.collision_mask
        }

    if node is PhysicsBody3D:
        _report["summary"]["physics_body3d_count"] += 1
        if node is RigidBody3D:
            var rigid := node as RigidBody3D
            data["rigid_body"] = {
                "mass": rigid.mass,
                "gravity_scale": rigid.gravity_scale,
                "linear_damp": rigid.linear_damp,
                "angular_damp": rigid.angular_damp,
                "freeze": rigid.freeze
            }
        elif node is CharacterBody3D:
            var character := node as CharacterBody3D
            data["character_body"] = {
                "motion_mode": character.motion_mode,
                "floor_max_angle": character.floor_max_angle,
                "floor_snap_length": character.floor_snap_length,
                "safe_margin": character.safe_margin
            }

    if node is MultiMeshInstance3D:
        _report["summary"]["multimesh_instance3d_count"] += 1
        var multi := node as MultiMeshInstance3D
        data["multimesh"] = {
            "instance_count": multi.multimesh.instance_count if multi.multimesh != null else 0
        }

    if node is Skeleton3D:
        _report["summary"]["skeleton3d_count"] += 1
        var skeleton := node as Skeleton3D
        var bones: Array[String] = []
        for bone_index in range(skeleton.get_bone_count()):
            bones.append(skeleton.get_bone_name(bone_index))
        data["skeleton"] = {"bone_count": bones.size(), "bone_names": bones}

    if node is AnimationPlayer:
        _report["summary"]["animation_player_count"] += 1
        var animation_player := node as AnimationPlayer
        var animations: Array[Dictionary] = []
        for animation_name in animation_player.get_animation_list():
            var animation := animation_player.get_animation(animation_name)
            var tracks: Array[Dictionary] = []
            if animation != null:
                for track_index in range(animation.get_track_count()):
                    var keys: Array[Dictionary] = []
                    var key_limit := mini(animation.track_get_key_count(track_index), 24)
                    for key_index in range(key_limit):
                        keys.append({
                            "time": animation.track_get_key_time(track_index, key_index),
                            "value": str(animation.track_get_key_value(track_index, key_index))
                        })
                    tracks.append({
                        "path": str(animation.track_get_path(track_index)),
                        "type": animation.track_get_type(track_index),
                        "key_count": animation.track_get_key_count(track_index),
                        "sampled_keys": keys
                    })
            animations.append({
                "name": animation_name,
                "length": animation.length if animation != null else 0.0,
                "loop_mode": animation.loop_mode if animation != null else 0,
                "tracks": tracks
            })
        data["animations"] = {
            "current": animation_player.current_animation,
            "available": animations
        }

    for child in node.get_children():
        data["children"].append(_inspect_node(child))
    return data


func _inspect_shape(shape: Shape3D) -> Dictionary:
    if shape == null:
        return {"class": "null"}
    var data := {"class": shape.get_class(), "resource_path": shape.resource_path}
    if shape is BoxShape3D:
        data["size"] = _vector3((shape as BoxShape3D).size)
    elif shape is SphereShape3D:
        data["radius"] = (shape as SphereShape3D).radius
    elif shape is CapsuleShape3D:
        var capsule := shape as CapsuleShape3D
        data["radius"] = capsule.radius
        data["height"] = capsule.height
    elif shape is CylinderShape3D:
        var cylinder := shape as CylinderShape3D
        data["radius"] = cylinder.radius
        data["height"] = cylinder.height
    elif shape is ConvexPolygonShape3D:
        data["point_count"] = (shape as ConvexPolygonShape3D).points.size()
    elif shape is ConcavePolygonShape3D:
        data["face_count"] = (shape as ConcavePolygonShape3D).get_faces().size() / 3
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
