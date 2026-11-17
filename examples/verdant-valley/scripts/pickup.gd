@tool
extends Area2D
class_name ValleyPickup

var collected := false
var sprite: Sprite2D
var elapsed := 0.0
var home_position := Vector2.ZERO

func _ready() -> void:
	add_to_group("collectibles")
	collision_layer = 0
	collision_mask = 1
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = 22.0
	shape.shape = circle
	add_child(shape)
	for child in get_children():
		if child is Sprite2D:
			sprite = child
			break
	if sprite:
		home_position = sprite.position
	body_entered.connect(_on_body_entered)

func _process(delta: float) -> void:
	if Engine.is_editor_hint() or collected or not is_instance_valid(sprite):
		return
	elapsed += delta
	sprite.position = home_position + Vector2(0, sin(elapsed * 3.2) * 4.0)
	sprite.rotation = sin(elapsed * 2.0) * 0.09
	var pulse := 0.96 + (sin(elapsed * 4.0) + 1.0) * 0.035
	sprite.scale = Vector2.ONE * 0.62 * pulse

func _on_body_entered(body: Node2D) -> void:
	if collected or not body is ValleyPlayer:
		return
	collected = true
	body.collect_shard()
	print("PLAYTEST EVENT: pickup collected, shards=", body.shards)
	queue_free()
