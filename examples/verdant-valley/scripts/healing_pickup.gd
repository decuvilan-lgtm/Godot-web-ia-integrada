@tool
extends Area2D
class_name ValleyHealingPickup

var collected := false
var sprite: Sprite2D
var elapsed := 0.0

func _ready() -> void:
	add_to_group("consumables")
	collision_layer = 0
	collision_mask = 1
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = 20.0
	shape.shape = circle
	add_child(shape)
	sprite = Sprite2D.new()
	sprite.texture = load("res://assets/environment/crystal.png")
	sprite.scale = Vector2(0.58, 0.58)
	sprite.modulate = Color(1.0, 0.68, 0.78, 1.0)
	add_child(sprite)
	body_entered.connect(_on_body_entered)

func _process(delta: float) -> void:
	if Engine.is_editor_hint() or collected:
		return
	elapsed += delta
	sprite.position.y = sin(elapsed * 2.8) * 4.0
	sprite.rotation = sin(elapsed * 1.5) * 0.08

func _on_body_entered(body: Node2D) -> void:
	if collected or not body is ValleyPlayer or body.health >= body.MAX_HEALTH:
		return
	collected = true
	body.heal(2)
	print("PLAYTEST EVENT: healing crystal used; health=", body.health)
	queue_free()
