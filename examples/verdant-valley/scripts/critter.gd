@tool
extends CharacterBody2D
class_name ValleyCritter
var left_edge := 0.0
var right_edge := 0.0
var direction := 1.0
var speed := 72.0
var anim: AnimatedSprite2D
func _ready() -> void:
	collision_layer = 2
	collision_mask = 0
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = 15
	shape.shape = circle
	shape.position = Vector2(0,-14)
	add_child(shape)
	anim = AnimatedSprite2D.new()
	var frames := SpriteFrames.new()
	frames.add_animation("walk")
	frames.set_animation_speed("walk", 4)
	frames.set_animation_loop("walk", true)
	for i in 2:
		frames.add_frame("walk", load("res://assets/characters/critter_idle_%d.png" % i))
	anim.sprite_frames = frames
	anim.play("walk")
	anim.position.y = -20
	add_child(anim)
func _physics_process(delta: float) -> void:
	if Engine.is_editor_hint(): return
	position.x += speed * direction * delta
	if position.x < left_edge or position.x > right_edge:
		direction *= -1.0
		anim.flip_h = direction < 0
func _on_detection_body_entered(body: Node2D) -> void:
	if body is ValleyPlayer:
		body.take_damage(1)
