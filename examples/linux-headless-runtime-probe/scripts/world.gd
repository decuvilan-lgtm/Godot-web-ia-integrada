extends Node2D

var status_label: Label
var elapsed := 0.0

func _ready() -> void:
    status_label = get_node("HUD/Status")
    status_label.text = "READY · arrows: move · Space/Enter: jump"
    queue_redraw()

func _process(delta: float) -> void:
    elapsed += delta
    if is_instance_valid(status_label):
        status_label.text = "READY · runtime %.1fs · scene + physics active" % elapsed

func _draw() -> void:
    draw_rect(Rect2(-2000, -1000, 5000, 2000), Color("#101a38"), true)
    for i in range(36):
        var x := float((i * 173) % 1500) - 300.0
        var y := float((i * 97) % 260) - 180.0
        draw_circle(Vector2(x, y), 1.5 + float(i % 3) * 0.6, Color(0.72, 0.86, 1.0, 0.65))
    draw_colored_polygon(PackedVector2Array([Vector2(-200, 420), Vector2(1200, 420), Vector2(1200, 700), Vector2(-200, 700)]), Color("#25385a"))
    draw_colored_polygon(PackedVector2Array([Vector2(-200, 420), Vector2(1200, 420), Vector2(1200, 440), Vector2(-200, 440)]), Color("#63d5c7"))
    draw_colored_polygon(PackedVector2Array([Vector2(360, 330), Vector2(560, 330), Vector2(560, 350), Vector2(360, 350)]), Color("#63d5c7"))
    draw_colored_polygon(PackedVector2Array([Vector2(700, 260), Vector2(860, 260), Vector2(860, 280), Vector2(700, 280)]), Color("#63d5c7"))
    draw_circle(Vector2(760, 150), 42, Color("#f6c96b"))
    draw_circle(Vector2(775, 138), 42, Color("#101a38"))
