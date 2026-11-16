extends StaticBody2D
class_name ValleyGate
var opened := false
var collision: CollisionShape2D
var visual: Polygon2D
func _ready() -> void:
	collision = CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = Vector2(28, 150)
	collision.shape = rect
	collision.position = Vector2(0, -75)
	add_child(collision)
	visual = Polygon2D.new()
	visual.polygon = PackedVector2Array([Vector2(-14,-150),Vector2(14,-150),Vector2(14,0),Vector2(-14,0)])
	visual.color = Color(0.23,0.48,0.46)
	add_child(visual)
func open_gate() -> void:
	opened = true
	collision.set_deferred("disabled", true)
	visual.visible = false
