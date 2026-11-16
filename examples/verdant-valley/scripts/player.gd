@tool
extends CharacterBody2D
class_name ValleyPlayer
signal health_changed(value: int)
signal shards_changed(value: int)
signal checkpoint_reached

const SPEED := 270.0
const JUMP_VELOCITY := -510.0
const GRAVITY := 1350.0
const MAX_HEALTH := 5
var health := MAX_HEALTH
var shards := 0
var facing := 1
var invulnerable := 0.0
var spawn_point := Vector2(120, 520)
var anim: AnimatedSprite2D

func _ready() -> void:
	collision_layer = 1
	collision_mask = 1
	var shape := CollisionShape2D.new()
	var capsule := CapsuleShape2D.new()
	capsule.radius = 13
	capsule.height = 38
	shape.shape = capsule
	shape.position = Vector2(0, -19)
	add_child(shape)
	anim = AnimatedSprite2D.new()
	anim.position = Vector2(0, -24)
	anim.sprite_frames = _make_frames()
	anim.play("idle")
	add_child(anim)
	var cam := Camera2D.new()
	cam.position_smoothing_enabled = true
	cam.position_smoothing_speed = 5.5
	cam.limit_left = 0
	cam.limit_top = 0
	cam.limit_right = 3900
	cam.limit_bottom = 720
	add_child(cam)
	position = spawn_point

func _make_frames() -> SpriteFrames:
	var frames := SpriteFrames.new()
	for anim_name in ["idle", "run", "jump"]:
		frames.add_animation(anim_name)
		frames.set_animation_speed(anim_name, 3 if anim_name == "idle" else (10 if anim_name == "run" else 1))
		frames.set_animation_loop(anim_name, true)
		var count := 2 if anim_name == "idle" else (4 if anim_name == "run" else 1)
		for i in count:
			frames.add_frame(anim_name, load("res://assets/characters/hero_%s_%d.png" % [anim_name, i]))
	return frames

func _physics_process(delta: float) -> void:
	if Engine.is_editor_hint(): return
	if not is_on_floor():
		velocity.y += GRAVITY * delta
	var axis := Input.get_axis("move_left", "move_right")
	if axis != 0:
		facing = int(sign(axis))
		velocity.x = move_toward(velocity.x, axis * SPEED, 1800.0 * delta)
	else:
		velocity.x = move_toward(velocity.x, 0.0, 2100.0 * delta)
	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = JUMP_VELOCITY
	if Input.is_action_just_pressed("interact"):
		interact_nearby()
	if invulnerable > 0.0:
		invulnerable -= delta
		anim.modulate.a = 0.45 if int(Time.get_ticks_msec() / 90) % 2 == 0 else 1.0
	else:
		anim.modulate.a = 1.0
	anim.flip_h = facing < 0
	if not is_on_floor():
		anim.play("jump")
	elif abs(velocity.x) > 20:
		anim.play("run")
	else:
		anim.play("idle")
	move_and_slide()
	if global_position.y > 900.0:
		take_damage(1)
		global_position = spawn_point
		velocity = Vector2.ZERO

func interact_nearby() -> void:
	for item in get_tree().get_nodes_in_group("interactables"):
		if global_position.distance_to(item.global_position) < 92 and item.has_method("activate"):
			item.activate(self)

func take_damage(amount: int = 1) -> void:
	if invulnerable > 0.0:
		return
	health = maxi(0, health - amount)
	invulnerable = 1.15
	health_changed.emit(health)
	if health == 0:
		health = MAX_HEALTH
		global_position = spawn_point
		velocity = Vector2.ZERO
		health_changed.emit(health)

func collect_shard() -> void:
	shards += 1
	shards_changed.emit(shards)

func set_checkpoint(point: Vector2) -> void:
	spawn_point = point
	checkpoint_reached.emit()
