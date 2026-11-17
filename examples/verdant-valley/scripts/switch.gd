@tool
extends Area2D
class_name ValleySwitch

signal activated

var is_active := false
var glow: Sprite2D
var elapsed := 0.0

func _ready() -> void:
	add_to_group("interactables")
	collision_layer = 0
	collision_mask = 1
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = 38.0
	shape.shape = circle
	add_child(shape)
	glow = Sprite2D.new()
	glow.texture = load("res://assets/environment/crystal.png")
	glow.scale = Vector2(0.75, 0.75)
	add_child(glow)

func _process(delta: float) -> void:
	if Engine.is_editor_hint() or not is_instance_valid(glow):
		return
	elapsed += delta
	if not is_active:
		glow.scale = Vector2.ONE * (0.75 + sin(elapsed * 2.5) * 0.045)
		glow.rotation = sin(elapsed * 1.3) * 0.08
	else:
		glow.rotation = 0.0
		glow.scale = Vector2.ONE * 0.82

func activate(_player: ValleyPlayer) -> void:
	if is_active:
		return
	is_active = true
	glow.modulate = Color(1.0, 0.83, 0.45)
	activated.emit()
