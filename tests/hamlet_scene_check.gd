extends SceneTree
# Drive the real scene with an isolated live bridge, without touching the desktop.
func _initialize():
	run.call_deferred()

func run():
	var scene=load("res://Valley.tscn").instantiate()
	root.add_child(scene)
	for i in 150:
		await create_timer(.03).timeout
		if not scene.snapshot.is_empty():break
	if scene.snapshot.is_empty():
		push_error("No village snapshot")
		quit(2)
		return
	for pair in [["farm","雾麦 "],["market","1 工作积分"],["dungeon","遗迹远征"]]:
		scene.set_place(pair[0])
		var found:=false
		for widget in scene.right.get_children():
			if widget is Button and widget.text.begins_with(pair[1]):
				found=true
				widget.pressed.emit()
				break
		if not found:
			push_error("Missing action: "+pair[1])
			quit(3)
			return
		while scene.busy:await process_frame
		if not scene.pending.is_empty() or scene.snapshot.message=="":
			push_error("Missing receipt")
			quit(4)
			return
	await create_timer(.2).timeout
	var view_file:=OS.get_environment("SUNDAY_VALLEY_CAPTURE")
	if view_file!="":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(view_file)
	print("Game scene navigation, planting, exchange and expedition passed")
	quit(0)
