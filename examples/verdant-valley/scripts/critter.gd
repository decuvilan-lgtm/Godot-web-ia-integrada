@tool
extends CharacterBody2D
class_name ValleyCritter

var left_edge := 0.0
var right_edge := 0.0
var direction := 1.0
var speed := 72.0
var anim: AnimatedSprite2D
var bob_time := 0.0

func _ready() -> void:
	add_to_group("enemies")
	collision_layer = 2
	collision_mask = 0
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = 15.0
	shape.shape = circle
	shape.position = Vector2(0, -14)
	add_child(shape)
	anim = AnimatedSprite2D.new()
	var frames := SpriteFrames.new()
	frames.add_animation("walk")
	frames.set_animation_speed("walk", 5)
	frames.set_animation_loop("walk", true)
	for i in 2:
		frames.add_frame("walk", load("res://assets/characters/critter_idle_%d.png" % i))
	anim.sprite_frames = frames
	anim.play("walk")
	anim.position.y = -22
	add_child(anim)

func _physics_process(delta: float) -> void:
	if Engine.is_editor_hint():
		return
	bob_time += delta
	position.x += speed * direction * delta
	if position.x < left_edge:
		position.x = left_edge
		direction = 1.0
	elif position.x > right_edge:
		position.x = right_edge
		direction = -1.0
	anim.flip_h = direction < 0.0
	anim.position.y = -22.0 + sin(bob_time * 7.0) * 1.5

func _on_detection_body_entered(body: Node2D) -> void:
	if not body is ValleyPlayer:
		return
	# A clean downward landing defeats a patrol creature and gives the player a bounce.
	if body.velocity.y > 80.0 and body.global_position.y < global_position.y - 8.0:
		body.velocity.y = -420.0
		print("PLAYTEST EVENT: critter stomped")
		queue_free()
		return
	body.take_damage(1, signf(body.global_position.x - global_position.x))
	print("PLAYTEST EVENT: critter contact; health=", body.health)
