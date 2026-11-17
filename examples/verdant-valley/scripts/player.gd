@tool
extends CharacterBody2D
class_name ValleyPlayer

signal health_changed(value: int)
signal shards_changed(value: int)
signal checkpoint_reached
signal landed

const SPEED := 270.0
const JUMP_VELOCITY := -700.0
const GRAVITY := 1550.0
const MAX_FALL_SPEED := 920.0
const GROUND_ACCELERATION := 1900.0
const AIR_ACCELERATION := 1250.0
const GROUND_FRICTION := 2300.0
const AIR_FRICTION := 520.0
const COYOTE_DURATION := 0.13
const JUMP_BUFFER_DURATION := 0.15
const MAX_HEALTH := 5

var health := MAX_HEALTH
var shards := 0
var facing := 1
var invulnerable := 0.0
var spawn_point := Vector2(120, 520)
var coyote_timer := 0.0
var jump_buffer_timer := 0.0
var was_on_floor := false
var anim: AnimatedSprite2D
var camera: Camera2D

func _ready() -> void:
	collision_layer = 1
	collision_mask = 1
	floor_snap_length = 8.0
	floor_max_angle = deg_to_rad(48.0)
	var shape := CollisionShape2D.new()
	var capsule := CapsuleShape2D.new()
	capsule.radius = 13
	capsule.height = 38
	shape.shape = capsule
	shape.position = Vector2(0, -19)
	add_child(shape)
	anim = AnimatedSprite2D.new()
	# The sprite's feet and the capsule bottom share the same world-space baseline.
	anim.position = Vector2(0, -22)
	anim.sprite_frames = _make_frames()
	anim.play("idle")
	add_child(anim)
	camera = Camera2D.new()
	camera.position_smoothing_enabled = true
	camera.position_smoothing_speed = 6.5
	camera.limit_left = 0
	camera.limit_top = 0
	camera.limit_right = 3900
	camera.limit_bottom = 720
	camera.drag_horizontal_enabled = true
	camera.drag_vertical_enabled = false
	add_child(camera)
	position = spawn_point

func _make_frames() -> SpriteFrames:
	var frames := SpriteFrames.new()
	for anim_name in ["idle", "run", "jump"]:
		frames.add_animation(anim_name)
		frames.set_animation_speed(anim_name, 4 if anim_name == "idle" else (12 if anim_name == "run" else 1))
		frames.set_animation_loop(anim_name, true)
		var count := 2 if anim_name == "idle" else (4 if anim_name == "run" else 1)
		for i in count:
			frames.add_frame(anim_name, load("res://assets/characters/hero_%s_%d.png" % [anim_name, i]))
	return frames

func _physics_process(delta: float) -> void:
	if Engine.is_editor_hint():
		return

	var grounded_before_move := is_on_floor()
	if grounded_before_move:
		coyote_timer = COYOTE_DURATION
	else:
		coyote_timer = maxf(0.0, coyote_timer - delta)

	if Input.is_action_just_pressed("jump"):
		jump_buffer_timer = JUMP_BUFFER_DURATION
	else:
		jump_buffer_timer = maxf(0.0, jump_buffer_timer - delta)

	var axis := Input.get_axis("move_left", "move_right")
	if axis != 0.0:
		facing = int(sign(axis))
		var acceleration := GROUND_ACCELERATION if grounded_before_move else AIR_ACCELERATION
		velocity.x = move_toward(velocity.x, axis * SPEED, acceleration * delta)
	else:
		var friction := GROUND_FRICTION if grounded_before_move else AIR_FRICTION
		velocity.x = move_toward(velocity.x, 0.0, friction * delta)

	if not grounded_before_move:
		var gravity_scale := 1.0
		# Releasing jump early gives a short hop instead of forcing every jump to full height.
		if velocity.y < 0.0 and not Input.is_action_pressed("jump"):
			gravity_scale = 2.15
		velocity.y = minf(velocity.y + GRAVITY * gravity_scale * delta, MAX_FALL_SPEED)

	if jump_buffer_timer > 0.0 and coyote_timer > 0.0:
		velocity.y = JUMP_VELOCITY
		jump_buffer_timer = 0.0
		coyote_timer = 0.0

	if Input.is_action_just_pressed("interact"):
		interact_nearby()

	if invulnerable > 0.0:
		invulnerable = maxf(0.0, invulnerable - delta)
		anim.modulate.a = 0.42 if int(Time.get_ticks_msec() / 85) % 2 == 0 else 1.0
	else:
		anim.modulate.a = 1.0

	anim.flip_h = facing < 0
	if not is_on_floor():
		anim.play("jump")
	elif absf(velocity.x) > 24.0:
		anim.play("run")
	else:
		anim.play("idle")

	move_and_slide()
	if is_on_floor() and not was_on_floor:
		landed.emit()
	was_on_floor = is_on_floor()

	if global_position.y > 900.0:
		take_damage(1, 0.0)
		global_position = spawn_point
		velocity = Vector2.ZERO
		coyote_timer = 0.0
		jump_buffer_timer = 0.0

func interact_nearby() -> void:
	for item in get_tree().get_nodes_in_group("interactables"):
		if global_position.distance_to(item.global_position) < 96.0 and item.has_method("activate"):
			item.activate(self)

func take_damage(amount: int = 1, knockback_direction: float = 0.0) -> void:
	if invulnerable > 0.0:
		return
	health = maxi(0, health - amount)
	invulnerable = 1.1
	velocity.x = knockback_direction * 245.0
	velocity.y = -300.0 if knockback_direction != 0.0 else minf(velocity.y, -180.0)
	health_changed.emit(health)
	if health == 0:
		health = MAX_HEALTH
		global_position = spawn_point
		velocity = Vector2.ZERO
		invulnerable = 1.35
		health_changed.emit(health)

func heal(amount: int) -> void:
	var previous := health
	health = mini(MAX_HEALTH, health + maxi(0, amount))
	if health != previous:
		health_changed.emit(health)

func collect_shard() -> void:
	shards += 1
	shards_changed.emit(shards)

func set_checkpoint(point: Vector2) -> void:
	spawn_point = point
	checkpoint_reached.emit()
