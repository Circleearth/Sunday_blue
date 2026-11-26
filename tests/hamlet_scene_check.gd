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
	if scene.world_map.size.y<280 or not scene.world_map.sprites.has("swift"):
		push_error("Map collapsed or sprite atlas failed to load")
		quit(9)
		return
	scene.set_place("farm")
	var click:=InputEventMouseButton.new()
	click.button_index=MOUSE_BUTTON_LEFT
	click.pressed=true
	var farm=scene.world_map.Farm
	click.position=scene.world_map.origin()+farm.bounds(2).get_center()*scene.world_map.zoom()
	scene.world_map._gui_input(click)
	if scene.chosen_plot!=2 or scene.world_map.wheat_frames.size()!=4:
		push_error("Farm tile hit test or four-stage wheat failed")
		quit(10)
		return
	for pair in [["farm","种植 雾麦 "],["market","1 工作积分"],["dungeon","遗迹远征"]]:
		scene.set_place(pair[0])
		var found:=false
		for widget in scene.right.get_children():
			if widget is Button and widget.text.begins_with(pair[1]):
				found=true
				if widget.disabled:
					push_error("Unexpected disabled action: "+pair[1])
					quit(5)
					return
				widget.pressed.emit()
				if pair[0]=="market":
					for child in scene.get_children():
						if child is ConfirmationDialog:
							if not scene.pending.is_empty():
								push_error("Exchange started before confirmation")
								quit(6)
								return
							child.confirmed.emit()
							child.hide()
							break
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
	for i in 15:
		if not scene.busy and scene.pending.is_empty():break
		await create_timer(.05).timeout
	scene.open_portfolio("orders")
	if scene.right.get_child(0).text!="委托进度":
		quit(11)
		return
	scene.open_portfolio("bag")
	if scene.right.get_child(0).text!="旅人背包":
		quit(7)
		return
	scene.open_portfolio("journal")
	if scene.right.get_child(0).text!="谷地手记":
		quit(8)
		return
	scene.set_place("overview")
	scene.greet()
	if not is_instance_valid(scene.guide_dialog) or not scene.guide_dialog.visible or scene.page.visible:
		push_error("Keeper portrait dialogue failed to open")
		quit(12)
		return
	var portrait:=scene.guide_dialog.get_node_or_null("Portrait") as TextureRect
	var box:=scene.guide_dialog.get_node_or_null("DialogueBox") as PanelContainer
	if not portrait or not portrait.texture or not box or portrait.get_parent()==box:
		push_error("Keeper portrait texture was not rendered")
		quit(13)
		return
	var view_file:=OS.get_environment("SUNDAY_VALLEY_CAPTURE")
	if view_file!="":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(view_file.get_basename()+"-portrait.png")
	await process_frame
	var actions:=box.find_children("*","Button",true,false)
	var panel_style:=box.get_theme_stylebox("panel") as StyleBoxFlat
	if actions.is_empty() or not panel_style or panel_style.bg_color.a>=1.0 or not scene.guide_dialog.get_rect().encloses(box.get_rect()):
		push_error("Keeper dialogue box must be translucent and fit the viewport")
		quit(14)
		return
	(actions[0] as Button).pressed.emit()
	if scene.guide_dialog.visible or not scene.page.visible:
		push_error("Keeper dialogue could not bring back the workspace")
		quit(15)
		return
	scene.set_place("dungeon")
	await create_timer(.2).timeout
	if view_file!="":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(view_file)
		scene.set_place("farm")
		var ready:Dictionary=scene.snapshot.state.duplicate(true)
		ready.world=ready.jobs[0].end
		ready.ready.append(ready.jobs.pop_front())
		scene.snapshot.state=ready
		scene.world_map.state=ready
		scene.choose_plot(2)
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(view_file.get_basename()+"-farm.png")
	print("Game scene navigation, planting, exchange and expedition passed")
	quit(0)
