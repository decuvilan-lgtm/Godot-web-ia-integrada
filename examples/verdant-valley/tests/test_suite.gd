extends SceneTree

var failures: Array[String] = []
func _initialize() -> void:
	call_deferred("run")
func check(condition:bool,label:String) -> void:
	if condition: print("PASS: ",label)
	else:
		failures.append(label)
		push_error("FAIL: "+label)
func run() -> void:
	var packed := load("res://scenes/main.tscn") as PackedScene
	check(packed != null,"main scene resource loads")
	if packed == null: quit(1); return
	var world := packed.instantiate()
	root.add_child(world)
	await process_frame
	check(world.player is ValleyPlayer,"player scene instantiated")
	check(world.get_child_count()>35,"level contains a substantial set of world objects")
	check(world.get_tree().get_nodes_in_group("interactables").size()==1,"one crystal switch is registered")
	check(world.gate!=null and not world.gate.get("opened"),"exit gate starts closed")
	check(world.player.health==5,"player starts with five health points")
	check(world.player.shards==0,"collectible counter starts at zero")
	var first_pickup := world.get_tree().get_nodes_in_group("collectibles")[0]
	world.player.global_position = first_pickup.global_position
	await physics_frame
	check(world.player.shards==1,"touching a pickup updates the shard counter")
	world.player.take_damage(1)
	check(world.player.health==4,"hazard damage reduces health")
	world.player.take_damage(1)
	check(world.player.health==4,"invulnerability prevents immediate repeated damage")
	var switch := world.get_tree().get_nodes_in_group("interactables")[0]
	world.player.global_position = switch.global_position
	world.player.interact_nearby()
	check(switch.is_active,"crystal switch changes to active")
	check(world.gate.get("opened"),"nearby interaction opens the exit gate")
	world.player.global_position = Vector2(3780,608)
	world.player.velocity = Vector2.ZERO
	await physics_frame
	check(world.finished,"entering the portal completes the level")
	world.player.set_checkpoint(Vector2(1800,646))
	world.player.health=2
	world.player.invulnerable=0.0
	world.player.take_damage(2)
	check(world.player.health==5,"zero-health recovery restores health")
	check(world.player.global_position.distance_to(Vector2(1800,646))<5,"recovery returns to checkpoint")
	var has_hud := false
	for child in world.get_children():
		if child is CanvasLayer: has_hud=true
	check(has_hud,"HUD layer is present")
	world.player.global_position=Vector2(120,520)
	world.player.velocity=Vector2.ZERO
	Input.action_press("move_right")
	for i in 20: await physics_frame
	Input.action_release("move_right")
	check(world.player.global_position.x>120,"player responds to horizontal movement input")
	world.player.velocity.y=-510
	await physics_frame
	check(world.player.velocity.y<0,"jump impulse enters upward movement")
	world.player.invulnerable=0.0
	world.player.health=4
	world.player.global_position=Vector2(500,1000)
	world.player.velocity=Vector2.ZERO
	await physics_frame
	check(world.player.global_position.y<900,"fall recovery returns player to a safe checkpoint")
	check(world.player.health==3,"fall recovery consumes one health point")
	print("TEST SUMMARY: %d passed, %d failed" % [19-failures.size(),failures.size()])
	quit(1 if not failures.is_empty() else 0)
