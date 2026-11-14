extends Node2D

func _ready() -> void:
    print("PROJECT_DIAG_BEGIN")
    push_error("PROJECT_DIAG_FIXTURE: intentional runtime error for diagnostic capture")
    print_stack()
    print("PROJECT_DIAG_END")
