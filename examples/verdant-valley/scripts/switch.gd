@tool
extends Area2D
class_name ValleySwitch
signal activated
var is_active := false
var glow: Sprite2D
func _ready() -> void:
	add_to_group("interactables")
	collision_layer = 0
	collision_mask = 1
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = 38
	shape.shape = circle
	add_child(shape)
	glow = Sprite2D.new()
	glow.texture = load("res://assets/environment/crystal.png")
	glow.scale = Vector2(0.75, 0.75)
	add_child(glow)
func activate(_player: ValleyPlayer) -> void:
	if is_active: return
	is_active = true
	glow.modulate = Color(1.0, 0.83, 0.45)
	activated.emit()
