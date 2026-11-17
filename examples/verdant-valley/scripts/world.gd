@tool
extends Node2D

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const PICKUP_SCRIPT := preload("res://scripts/pickup.gd")
const HEALING_SCRIPT := preload("res://scripts/healing_pickup.gd")
const SWITCH_SCRIPT := preload("res://scripts/switch.gd")
const GATE_SCRIPT := preload("res://scripts/gate.gd")
const CRITTER_SCRIPT := preload("res://scripts/critter.gd")
var player: ValleyPlayer
var gate: Node2D
var hud: CanvasLayer
var status_label: Label
var hearts_label: Label
var shard_label: Label
var message_timer := 0.0
var finished := false
var portal_visual: Polygon2D
var world_time := 0.0
var demo_mode := false
var demo_elapsed := 0.0
var playtest_mode := false
var playtest_elapsed := 0.0
var playtest_reported := false
var playtest_last_trace_second := -1
var playtest_jump_index := 0
var playtest_jump_hold := 0.0
const PLAYTEST_JUMP_TARGETS := [680.0, 940.0, 1300.0, 1600.0, 1940.0, 2320.0, 2930.0, 3250.0]

func _ready() -> void:
	demo_mode = OS.get_cmdline_user_args().has("--demo")
	playtest_mode = OS.get_cmdline_user_args().has("--playtest")
	print("PLAYTEST INIT: args=", OS.get_cmdline_user_args(), " enabled=", playtest_mode)
	_setup_input()
	_build_backdrop()
	_build_terrain()
	_build_decor()
	_build_objects()
	_build_player()
	_build_hud()
	show_message("EL SENDERO DE LAS LUCIÉRNAGAS  •  Sigue los fragmentos y activa el cristal")

func _setup_input() -> void:
	var actions := {"move_left":[KEY_A,KEY_LEFT],"move_right":[KEY_D,KEY_RIGHT],"jump":[KEY_SPACE,KEY_W,KEY_UP],"interact":[KEY_E,KEY_F]}
	for action in actions:
		if not InputMap.has_action(action): InputMap.add_action(action)
		for code in actions[action]:
			var event := InputEventKey.new()
			event.physical_keycode = code
			InputMap.action_add_event(action,event)

func _build_backdrop() -> void:
	for path in ["res://assets/backgrounds/sky.png","res://assets/backgrounds/far_hills.png"]:
		var sprite := Sprite2D.new()
		sprite.texture = load(path)
		sprite.centered = false
		sprite.position = Vector2.ZERO
		sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		add_child(sprite)

func _build_terrain() -> void:
	for data in [[0,650,720,140,"moss"],[760,650,380,140,"moss"],[1210,650,520,140,"moss"],[1780,650,430,140,"moss"],[2220,650,780,140,"moss"],[3060,650,840,140,"moss"],[420,520,170,28,"stone"],[900,505,170,28,"stone"],[1130,430,190,28,"stone"],[1480,520,190,28,"stone"],[1900,500,180,28,"stone"],[2150,420,190,28,"stone"],[2500,520,170,28,"stone"],[2790,455,170,28,"stone"],[3250,510,180,28,"stone"],[3500,430,200,28,"stone"]]:
		_add_platform(data[0],data[1],data[2],data[3],data[4])
	for data in [[1060,96],[1670,100],[2070,110],[3350,110]]:
		_add_hazard(data[0],650,data[1])

func _add_platform(x:float,y:float,w:float,h:float,texture_name:String) -> void:
	var body := StaticBody2D.new()
	body.position = Vector2(x+w/2,y+h/2)
	var shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = Vector2(w,h)
	shape.shape = rect
	body.add_child(shape)
	var sprite := Sprite2D.new()
	sprite.texture = load("res://assets/environment/%s.png" % texture_name)
	sprite.centered = false
	sprite.position = Vector2(-w/2,-h/2)
	sprite.scale = Vector2(w/64.0,h/64.0)
	sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	body.add_child(sprite)
	add_child(body)

func _add_hazard(x:float,y:float,w:float) -> void:
	var area := Area2D.new()
	area.position = Vector2(x,y-24)
	area.collision_layer = 0
	area.collision_mask = 1
	var shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = Vector2(w,42)
	shape.shape = rect
	area.add_child(shape)
	var sprite := Sprite2D.new()
	sprite.texture = load("res://assets/environment/hazard.png")
	sprite.centered = false
	sprite.position = Vector2(-w/2,-24)
	sprite.scale = Vector2(w/64.0,0.5)
	area.add_child(sprite)
	area.body_entered.connect(_on_hazard_entered)
	add_child(area)

func _build_decor() -> void:
	for x in [150,330,680,850,1370,1570,1870,2350,2710,2980,3390,3710]:
		var fern := Sprite2D.new()
		fern.texture = load("res://assets/environment/fern.png")
		fern.position = Vector2(x,638)
		fern.scale = Vector2(0.72,0.72)
		fern.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		add_child(fern)
	for x in [600,1300,1850,2430,3440]:
		var crystal := Sprite2D.new()
		crystal.texture = load("res://assets/environment/crystal.png")
		crystal.position = Vector2(x,570)
		crystal.scale = Vector2(0.32,0.32)
		crystal.modulate = Color(0.7,1.0,0.85,0.75)
		add_child(crystal)

func _build_objects() -> void:
	for p in [Vector2(270,610),Vector2(470,470),Vector2(960,450),Vector2(1190,375),Vector2(1540,465),Vector2(1945,445),Vector2(2200,365),Vector2(2550,465),Vector2(2840,400),Vector2(3300,455),Vector2(3560,375)]:
		_add_pickup(p)
	_add_healing_pickup(Vector2(1830,450))
	_add_critter(Vector2(1370,650),1250,1570)
	_add_critter(Vector2(2390,650),2260,2690)
	_add_checkpoint(Vector2(1800,650))
	var gate_node := StaticBody2D.new()
	gate_node.set_script(GATE_SCRIPT)
	gate_node.position = Vector2(3020,650)
	gate = gate_node
	add_child(gate_node)
	var switch := Area2D.new()
	switch.set_script(SWITCH_SCRIPT)
	switch.position = Vector2(2820,650)
	switch.activated.connect(_on_switch_activated)
	add_child(switch)
	_add_exit(Vector2(3780,650))

func _add_pickup(point:Vector2) -> void:
	var item := Area2D.new()
	item.set_script(PICKUP_SCRIPT)
	item.position = point
	var sprite := Sprite2D.new()
	sprite.texture = load("res://assets/environment/gold.png")
	sprite.scale = Vector2(0.62,0.62)
	item.add_child(sprite)
	add_child(item)

func _add_healing_pickup(point:Vector2) -> void:
	var item := Area2D.new()
	item.set_script(HEALING_SCRIPT)
	item.position = point
	add_child(item)

func _add_critter(point:Vector2,left:float,right:float) -> void:
	var critter := CharacterBody2D.new()
	critter.set_script(CRITTER_SCRIPT)
	critter.position = point
	critter.left_edge = left
	critter.right_edge = right
	add_child(critter)
	var sensor := Area2D.new()
	sensor.collision_layer = 0
	sensor.collision_mask = 1
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = 30
	shape.shape = circle
	sensor.add_child(shape)
	sensor.body_entered.connect(critter._on_detection_body_entered)
	critter.add_child(sensor)

func _add_checkpoint(point:Vector2) -> void:
	var area := Area2D.new()
	area.add_to_group("checkpoints")
	area.position = point
	area.collision_layer = 0
	area.collision_mask = 1
	var shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = Vector2(80,360)
	shape.shape = rect
	shape.position.y = -180
	area.add_child(shape)
	var flag := Polygon2D.new()
	flag.polygon = PackedVector2Array([Vector2(0,-108),Vector2(54,-90),Vector2(0,-72)])
	flag.color = Color(0.98,0.76,0.39)
	area.add_child(flag)
	area.body_entered.connect(_on_checkpoint_entered.bind(point))
	add_child(area)

func _add_exit(point:Vector2) -> void:
	var portal := Area2D.new()
	portal.add_to_group("exit_portal")
	portal.position = point
	portal.collision_layer = 0
	portal.collision_mask = 1
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = 45
	shape.shape = circle
	shape.position.y = -42
	portal.add_child(shape)
	var visual := Polygon2D.new()
	visual.polygon = PackedVector2Array([Vector2(0,-95),Vector2(34,-70),Vector2(30,-12),Vector2(0,0),Vector2(-30,-12),Vector2(-34,-70)])
	visual.color = Color(0.38,0.89,0.77,0.9)
	portal.add_child(visual)
	portal.body_entered.connect(_on_exit_entered)
	add_child(portal)

func _build_player() -> void:
	player = PLAYER_SCENE.instantiate()
	player.position = Vector2(120,520)
	player.health_changed.connect(_update_hud)
	player.shards_changed.connect(_update_hud)
	add_child(player)

func _build_hud() -> void:
	hud = CanvasLayer.new()
	add_child(hud)
	var panel := PanelContainer.new()
	panel.position = Vector2(20,18)
	panel.add_theme_stylebox_override("panel",_panel_style())
	hud.add_child(panel)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation",22)
	panel.add_child(row)
	hearts_label = Label.new()
	hearts_label.add_theme_color_override("font_color",Color(1.0,0.62,0.52))
	row.add_child(hearts_label)
	shard_label = Label.new()
	shard_label.add_theme_color_override("font_color",Color(1.0,0.85,0.52))
	row.add_child(shard_label)
	var controls := Label.new()
	controls.text = "A / D  MOVER   •   ESPACIO  SALTAR   •   E  INTERACTUAR"
	controls.position = Vector2(20,676)
	controls.add_theme_color_override("font_color",Color(0.79,0.9,0.83))
	controls.add_theme_font_size_override("font_size",15)
	hud.add_child(controls)
	status_label = Label.new()
	status_label.position = Vector2(270,24)
	status_label.size = Vector2(740,40)
	status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	status_label.add_theme_color_override("font_color",Color(0.94,0.94,0.79))
	status_label.add_theme_font_size_override("font_size",17)
	hud.add_child(status_label)
	_update_hud(5)
	for spec in [{"action":"move_left","pos":Vector2(82,600)},{"action":"move_right","pos":Vector2(174,600)},{"action":"jump","pos":Vector2(1195,590)},{"action":"interact","pos":Vector2(1095,630)}]:
		var touch := TouchScreenButton.new()
		touch.action = spec.action
		touch.position = spec.pos
		touch.visibility_mode = TouchScreenButton.VISIBILITY_TOUCHSCREEN_ONLY
		var circle := CircleShape2D.new()
		circle.radius = 34
		touch.shape = circle
		touch.passby_press = true
		hud.add_child(touch)

func _panel_style() -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.035,0.09,0.12,0.82)
	style.border_color = Color(0.31,0.57,0.48,0.8)
	style.set_border_width_all(2)
	style.set_corner_radius_all(12)
	style.content_margin_left = 14
	style.content_margin_right = 14
	style.content_margin_top = 8
	style.content_margin_bottom = 8
	return style

func _update_hud(_value:int) -> void:
	if not is_instance_valid(player) or not is_instance_valid(hearts_label): return
	hearts_label.text = "♥ ".repeat(player.health) + "♡ ".repeat(player.MAX_HEALTH-player.health)
	shard_label.text = "✦ %d / 11" % player.shards

func _on_switch_activated() -> void:
	print("PLAYTEST EVENT: crystal activated; gate opening")
	gate.call("open_gate")
	show_message("¡El sello respondió! El arco del valle está abierto.")

func _on_checkpoint_entered(body:Node2D,point:Vector2) -> void:
	var safe_point := point + Vector2(0,-4)
	if body is ValleyPlayer and body.spawn_point.distance_to(safe_point) > 1.0:
		body.set_checkpoint(safe_point)
		print("PLAYTEST EVENT: checkpoint reached")
		show_message("Punto de descanso activado")

func _on_hazard_entered(body:Node2D) -> void:
	if body is ValleyPlayer:
		body.take_damage(1)
		body.velocity.y = -300

func _on_exit_entered(body:Node2D) -> void:
	if body is ValleyPlayer and not finished:
		if not is_instance_valid(gate) or not gate.get("opened"):
			show_message("El portal está sellado. Activa primero el cristal antiguo.")
			return
		print("PLAYTEST EVENT: portal body_entered body=Player")
		finished = true
		show_message("¡LO LOGRASTE!  •  Fragmentos: %d / 11" % player.shards)

func show_message(message:String) -> void:
	if is_instance_valid(status_label):
		status_label.text = message
		message_timer = 4.0

func _process_playtest(delta:float) -> void:
	playtest_elapsed += delta
	var trace_second := int(floor(playtest_elapsed))
	if trace_second != playtest_last_trace_second:
		playtest_last_trace_second = trace_second
		print("PLAYTEST TRACE: t=", snappedf(playtest_elapsed, 0.1), " position=", player.global_position, " velocity=", player.velocity, " grounded=", player.is_on_floor(), " health=", player.health, " shards=", player.shards, " finished=", finished)
	if finished:
		Input.action_release("move_right")
	else:
		Input.action_press("move_right")
	var jump_now := false
	if playtest_jump_index < PLAYTEST_JUMP_TARGETS.size() and player.is_on_floor() and player.global_position.x >= PLAYTEST_JUMP_TARGETS[playtest_jump_index]:
		jump_now = true
		print("PLAYTEST ACTION: jump target=", PLAYTEST_JUMP_TARGETS[playtest_jump_index], " actual_x=", player.global_position.x)
		playtest_jump_index += 1
	if jump_now:
		playtest_jump_hold = 0.28 if playtest_jump_index == 1 else 0.9
	if playtest_jump_hold > 0.0:
		Input.action_press("jump")
		playtest_jump_hold = maxf(0.0, playtest_jump_hold - delta)
	else:
		Input.action_release("jump")
	var interact_now := false
	var switches := get_tree().get_nodes_in_group("interactables")
	if not switches.is_empty() and not switches[0].is_active and player.is_on_floor():
		if player.global_position.distance_to(switches[0].global_position) < 80.0:
			interact_now = true
			print("PLAYTEST ACTION: interact with crystal at ", player.global_position)
	if interact_now:
		Input.action_press("interact")
	else:
		Input.action_release("interact")
	if playtest_elapsed >= 14.1 and not playtest_reported:
		playtest_reported = true
		print("PLAYTEST RESULT: position=", player.global_position, " health=", player.health, " shards=", player.shards, " jumps=", playtest_jump_index, " finished=", finished)

func _process(delta:float) -> void:
	if Engine.is_editor_hint(): return
	if playtest_mode and is_instance_valid(player):
		_process_playtest(delta)
	if demo_mode and is_instance_valid(player):
		demo_elapsed += delta
		if demo_elapsed < 7.0: Input.action_press("move_right")
		else: Input.action_release("move_right")
		if (demo_elapsed > 2.05 and demo_elapsed < 2.22) or (demo_elapsed > 4.55 and demo_elapsed < 4.72):
			Input.action_press("jump")
		else: Input.action_release("jump")
	if message_timer > 0:
		message_timer -= delta
	elif is_instance_valid(status_label) and not finished:
		status_label.text = "EL ARCO ANTIGUO  •  Activa el cristal para abrir la salida"
	if Input.is_action_just_pressed("ui_cancel"):
		get_tree().paused = not get_tree().paused
