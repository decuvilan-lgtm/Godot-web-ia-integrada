extends CharacterBody2D

const SPEED := 280.0
const JUMP_VELOCITY := -520.0
const GRAVITY := 1250.0

func _ready() -> void:
    var collision := CollisionShape2D.new()
    var rectangle := RectangleShape2D.new()
    rectangle.size = Vector2(30, 48)
    collision.shape = rectangle
    add_child(collision)

func _physics_process(delta: float) -> void:
    var direction := Input.get_axis("ui_left", "ui_right")
    velocity.x = direction * SPEED
    if not is_on_floor():
        velocity.y += GRAVITY * delta
    elif Input.is_action_just_pressed("ui_accept"):
        velocity.y = JUMP_VELOCITY
    move_and_slide()

func _draw() -> void:
    draw_rect(Rect2(-15, -24, 30, 48), Color("#f2b84b"), true)
    draw_rect(Rect2(-15, -24, 30, 10), Color("#ffe6a1"), true)
    draw_circle(Vector2(6, -9), 3.0, Color("#17213b"))
    draw_rect(Rect2(-11, 17, 9, 8), Color("#26385f"), true)
    draw_rect(Rect2(3, 17, 9, 8), Color("#26385f"), true)
