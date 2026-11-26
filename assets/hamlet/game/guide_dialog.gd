extends Control

signal dismissed

const NAME_COLOR = Color("#f0ca89")
const BODY_COLOR = Color("#fff1dc")

func setup(backdrop:Texture2D, likeness:Texture2D, line:String):
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

	var scenery:=TextureRect.new()
	scenery.texture=backdrop
	scenery.expand_mode=TextureRect.EXPAND_IGNORE_SIZE
	scenery.stretch_mode=TextureRect.STRETCH_KEEP_ASPECT_COVERED
	scenery.mouse_filter=Control.MOUSE_FILTER_IGNORE
	scenery.texture_filter=CanvasItem.TEXTURE_FILTER_NEAREST
	add_child(scenery)
	scenery.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

	var shade:=ColorRect.new()
	shade.color=Color(0.05,0.08,0.09,0.28) if backdrop else Color("#22352f")
	shade.mouse_filter=Control.MOUSE_FILTER_IGNORE
	add_child(shade)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

	if likeness:
		var portrait:=TextureRect.new()
		portrait.name="Portrait"
		portrait.texture=likeness
		portrait.expand_mode=TextureRect.EXPAND_IGNORE_SIZE
		portrait.stretch_mode=TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		portrait.mouse_filter=Control.MOUSE_FILTER_IGNORE
		add_child(portrait)
		portrait.anchor_left=.41
		portrait.anchor_right=.96
		portrait.anchor_top=.015
		portrait.anchor_bottom=.96

	var box:=PanelContainer.new()
	box.name="DialogueBox"
	add_child(box)
	box.anchor_left=.055
	box.anchor_right=.945
	box.anchor_top=1
	box.anchor_bottom=1
	box.offset_top=-174
	box.offset_bottom=-26
	var style:=StyleBoxFlat.new()
	style.bg_color=Color(0.045,0.075,0.082,0.79)
	style.border_color=Color(0.94,0.79,0.52,0.55)
	style.set_border_width_all(1)
	style.border_width_top=2
	style.set_corner_radius_all(10)
	style.content_margin_left=25
	style.content_margin_right=25
	style.content_margin_top=12
	style.content_margin_bottom=12
	box.add_theme_stylebox_override("panel",style)

	var content:=VBoxContainer.new()
	content.add_theme_constant_override("separation",8)
	box.add_child(content)
	var header:=HBoxContainer.new()
	content.add_child(header)
	var speaker:=Label.new()
	speaker.text="铃禾"
	speaker.add_theme_color_override("font_color",NAME_COLOR)
	speaker.add_theme_font_size_override("font_size",24)
	header.add_child(speaker)
	var role:=Label.new()
	role.text="守谷人"
	role.add_theme_color_override("font_color",Color("#c6c7bb"))
	header.add_child(role)
	var body:=Label.new()
	body.text=line
	body.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
	body.add_theme_color_override("font_color",BODY_COLOR)
	body.add_theme_font_size_override("font_size",20)
	body.size_flags_vertical=Control.SIZE_EXPAND_FILL
	body.vertical_alignment=VERTICAL_ALIGNMENT_CENTER
	content.add_child(body)

	var close:=Button.new()
	close.text="回到谷地   ›"
	close.tooltip_text="Enter / Esc"
	close.mouse_default_cursor_shape=Control.CURSOR_POINTING_HAND
	close.size_flags_horizontal=Control.SIZE_SHRINK_END
	close.add_theme_color_override("font_color",NAME_COLOR)
	close.add_theme_color_override("font_hover_color",BODY_COLOR)
	close.pressed.connect(dismiss)
	content.add_child(close)
	close.grab_focus()

func _input(event:InputEvent):
	if is_visible_in_tree() and event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		dismiss()

func dismiss():
	if not visible:return
	hide()
	dismissed.emit()
	queue_free()
