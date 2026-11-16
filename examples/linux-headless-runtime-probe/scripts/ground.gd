extends Node

func _ready() -> void:
    _add_platform.call_deferred(Vector2(500, 430), Vector2(1800, 40))
    _add_platform.call_deferred(Vector2(460, 340), Vector2(200, 20))
    _add_platform.call_deferred(Vector2(780, 270), Vector2(160, 20))

func _add_platform(at: Vector2, size: Vector2) -> void:
    var body := StaticBody2D.new()
    body.position = at
    var shape := CollisionShape2D.new()
    var rectangle := RectangleShape2D.new()
    rectangle.size = size
    shape.shape = rectangle
    body.add_child(shape)
    get_parent().add_child(body)
