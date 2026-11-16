@tool
extends Area2D
class_name ValleyPickup
var collected := false
func _ready() -> void:
	add_to_group("collectibles")
	collision_layer = 0
	collision_mask = 1
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = 22
	shape.shape = circle
	add_child(shape)
	body_entered.connect(_on_body_entered)
func _on_body_entered(body: Node2D) -> void:
	if collected or not body is ValleyPlayer:
		return
	collected = true
	body.collect_shard()
	print("PLAYTEST EVENT: pickup collected, shards=", body.shards)
	queue_free()
