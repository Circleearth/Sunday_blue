extends Control

const MAP = preload("res://map.gd")
const INK = Color("#273f3c")
const SUB = Color("#50695e")
var world_map
var stats := Label.new()
var status := Label.new()
var jobs := Label.new()
var right := VBoxContainer.new()
var sound := AudioStreamPlayer.new()
var poll := Timer.new()
var http := HTTPRequest.new()
var selected := "farm"
var chosen_plot := -1
var snapshot := {}
var busy := false
var signature := ""
var pending := {}
var sent_action := "view"
var url := ""
var token := ""

func panel(color: String, radius: int, pad: int) -> StyleBoxFlat:
	var style:=StyleBoxFlat.new()
	style.bg_color=Color(color)
	style.set_corner_radius_all(radius)
	style.content_margin_left=pad
	style.content_margin_right=pad
	style.content_margin_top=pad*.66
	style.content_margin_bottom=pad*.66
	return style

func label(parent: Control, text: String, pixels: int, tint: Color=INK) -> Label:
	var l:=Label.new()
	l.text=text
	l.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_font_size_override("font_size",pixels)
	l.add_theme_color_override("font_color",tint)
	parent.add_child(l)
	return l

func btn(parent:Control,title:String,task:Callable) -> Button:
	var b:=Button.new()
	b.text=title
	b.add_theme_stylebox_override("normal",panel("e4ebd9",6,11))
	b.add_theme_stylebox_override("hover",panel("d7e8cb",6,11))
	b.add_theme_stylebox_override("pressed",panel("b7d1b4",6,11))
	b.add_theme_color_override("font_color",INK)
	b.add_theme_color_override("font_hover_color",INK)
	b.add_theme_color_override("font_pressed_color",INK)
	b.pressed.connect(task)
	parent.add_child(b)
	return b

func _ready():
	var face:=SystemFont.new()
	face.font_names=PackedStringArray(["Microsoft YaHei UI","Microsoft YaHei","Noto Sans CJK SC","sans-serif"])
	theme=Theme.new()
	theme.default_font=face
	theme.default_font_size=15
	theme.set_color("font_color","Label",INK)
	var page:=PanelContainer.new()
	add_child(page)
	page.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	page.add_theme_stylebox_override("panel",panel("f7f3e8",0,16))
	var col:=VBoxContainer.new()
	page.add_child(col)
	var header:=HBoxContainer.new()
	col.add_child(header)
	label(header,"雾铃谷",30).custom_minimum_size.x=128
	stats.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	stats.horizontal_alignment=HORIZONTAL_ALIGNMENT_RIGHT
	header.add_child(stats)
	var middle:=HBoxContainer.new()
	middle.size_flags_vertical=Control.SIZE_EXPAND_FILL
	col.add_child(middle)
	var atlas:=VBoxContainer.new()
	atlas.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	middle.add_child(atlas)
	world_map=MAP.new()
	world_map.size_flags_vertical=Control.SIZE_EXPAND_FILL
	world_map.selected.connect(set_place)
	world_map.greet.connect(greet)
	world_map.plot_clicked.connect(choose_plot)
	atlas.add_child(world_map)
	var nav:=HBoxContainer.new()
	atlas.add_child(nav)
	for id in ["farm","ranch","mine","forge","dungeon","market"]:
		btn(nav,{"farm":"农田","ranch":"牧场","mine":"矿区","forge":"工坊","dungeon":"遗迹","market":"集市"}[id],set_place.bind(id)).size_flags_horizontal=Control.SIZE_EXPAND_FILL
	var scroll:=ScrollContainer.new()
	scroll.custom_minimum_size.x=337
	scroll.horizontal_scroll_mode=ScrollContainer.SCROLL_MODE_DISABLED
	var ledger:=PanelContainer.new()
	ledger.add_theme_stylebox_override("panel",panel("fffaf0",10,14))
	middle.add_theme_constant_override("separation",12)
	middle.add_child(ledger)
	ledger.add_child(scroll)
	scroll.add_child(right)
	right.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	right.add_theme_constant_override("separation",7)
	for widget in [jobs,status]:
		widget.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
		col.add_child(widget)
	status.add_theme_color_override("font_color",SUB)
	status.text="正在连接本机谷地存档…"
	setup_sound()
	add_child(http)
	http.timeout=4
	http.request_completed.connect(receive)
	url="http://127.0.0.1:"+OS.get_environment("SUNDAY_VALLEY_PORT")+"/village"
	token=OS.get_environment("SUNDAY_VALLEY_TOKEN")
	add_child(poll)
	poll.wait_time=2
	poll.timeout.connect(refresh)
	poll.start()
	refresh()

func greet():
	var dlg:=AcceptDialog.new()
	dlg.title="守谷人 · 铃禾"
	dlg.ok_button_text="回到谷地"
	add_child(dlg)
	var line:="第一季的雾麦很适合喂苔羊。收成到了，我会替你把田地标出来。"
	if not snapshot.is_empty():
		if not snapshot.state.ready.is_empty():line="你闻，麦香已经飘过桥了。去田里看看，成熟的那批可以收啦。"
		elif snapshot.state.floor>1:line="我看见遗迹那头亮了灯。回来时带点矿石，我们可以把下一把短刃做得更趁手。"
	var layout:=HBoxContainer.new()
	dlg.add_child(layout)
	if world_map.sprites.has("keeper_portrait"):
		var portrait:=TextureRect.new()
		portrait.texture=world_map.sprites.keeper_portrait
		portrait.expand_mode=TextureRect.EXPAND_IGNORE_SIZE
		portrait.stretch_mode=TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		portrait.custom_minimum_size=Vector2(180,240)
		layout.add_child(portrait)
	var text:=Label.new()
	text.text=line
	text.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
	text.custom_minimum_size.x=265
	layout.add_child(text)
	dlg.visibility_changed.connect(func():
		if not dlg.visible:dlg.queue_free())
	dlg.popup_centered(Vector2i(490,300))

func setup_sound():
	var wave:=AudioStreamWAV.new()
	wave.format=AudioStreamWAV.FORMAT_16_BITS
	wave.mix_rate=22050
	var bytes:=PackedByteArray()
	bytes.resize(8800)
	for i in 4400:
		var t:=i/22050.
		var envelope:=exp(-17*t)*minf(1,t*200)
		bytes.encode_s16(i*2,roundi(3100*envelope*(sin(TAU*523*t)+.4*sin(TAU*784*t))))
	wave.data=bytes
	sound.stream=wave
	add_child(sound)

func choose_plot(index:int):
	if snapshot.is_empty():return
	for j in snapshot.state.ready:
		if int(j.plot)==index:
			command("harvest",j.id)
			return
	for j in snapshot.state.jobs:
		if j.has("plot") and int(j.plot)==index:
			status.text="第 %d 块田 · %s还需 %d 游戏分钟"%[index+1,snapshot.catalog.activities[j.key].name,ceili((j.end-snapshot.state.world)/60)]
			return
	chosen_plot=index
	set_place("farm")
	status.text="已选第 %d 块田，请选择作物。"%(index+1)

func begin(id:String):
	if chosen_plot>=0 and snapshot.catalog.activities[id].site=="farm":
		command("sow",id+":"+str(chosen_plot))
		chosen_plot=-1
	else:command("start",id)

func set_place(id:String):
	selected=id
	world_map.place=id
	rebuild()

func refresh():
	if not busy:send(pending if not pending.is_empty() else {"action":"view"})

func command(action:String,arg:String=""):
	if not pending.is_empty():
		status.text="正在同步上一项操作，请稍候。"
		return
	pending={"action":action,"arg":arg,"id":Crypto.new().generate_random_bytes(16).hex_encode()}
	if not busy:send(pending)

func send(data:Dictionary):
	if token.is_empty():
		status.text="请从 Sunday Blue 的工作页进入雾铃谷。"
		return
	busy=true
	sent_action=data.get("action","view")
	var err:=http.request(url,["Authorization: Bearer "+token,"Content-Type: application/json"],HTTPClient.METHOD_POST,JSON.stringify(data))
	if err!=OK:
		busy=false
		status.text="连接暂时不可用，正在重试。"

func receive(result:int,code:int,_headers:PackedStringArray,body:PackedByteArray):
	busy=false
	if result!=HTTPRequest.RESULT_SUCCESS or code>=500:
		status.text="与 Sunday Blue 的连接中断，恢复后会核对上次操作。"
		return
	var data=JSON.parse_string(body.get_string_from_utf8())
	if not data is Dictionary:
		status.text="存档未响应。请从工作页重新进入。"
		return
	if sent_action!="view":pending.clear()
	elif not pending.is_empty():refresh.call_deferred()
	if code!=200:
		status.text=str(data.get("error","无法操作"))
		return
	var first:=snapshot.is_empty()
	snapshot=data
	var s:Dictionary=data.state
	world_map.state=s
	world_map.catalog=data.catalog
	stats.text="Lv.%d    ·    谷币 %d    ·    %s"%[1+int(s.xp/10),int(s.cash),"专注流速 ×1" if data.running else "闲时流速 ×0.1"]
	var ongoing:=PackedStringArray()
	for j in s.jobs:
		ongoing.append("%s  %d 分"%[data.catalog.activities[j.key].name,ceili(maxf(0,j.end-s.world)/60)])
	jobs.text="进行中    "+("暂无委托" if ongoing.is_empty() else "    /    ".join(ongoing))
	if data.message!="":
		status.text=data.message
		sound.play()
		world_map.strike=1.0
	elif first:status.text="点地图上的地点，安排生产或派遣伙伴。"
	var key:=JSON.stringify([s.ready,s.jobs,s.inventory,s.gear,s.cash,s.log,s.auto,s.team,s.filter,s.equipped,s.floor,data.coins,data.work])
	if key!=signature:
		if not first and data.message=="" and not s.log.is_empty():status.text=s.log.back()
		signature=key
		rebuild()

func rebuild():
	for child in right.get_children():
		right.remove_child(child)
		child.queue_free()
	if snapshot.is_empty():return
	var s:Dictionary=snapshot.state
	var c:Dictionary=snapshot.catalog
	label(right,world_map.NAMES[selected],25)
	var info={"farm":"播种与开垦","ranch":"喂养苔羊，收集月露乳与苔绒","mine":"从青铜露头到星辉晶脉","forge":"加工矿石、锻造与配装","dungeon":"派遣队伍，战斗结束后自动回收战利品","market":"交易与谷币兑换"}
	label(right,info[selected],14,SUB)
	for id in c.activities:
		var recipe:Dictionary=c.activities[id]
		if recipe.site!=selected and not (selected=="farm" and recipe.site=="build"):continue
		var needs:=PackedStringArray()
		for k in recipe.inputs:needs.append(c.items[k]+" ×"+str(int(recipe.inputs[k])))
		btn(right,"%s    %d 谷币  ·  %d 分"%[recipe.name,recipe.cost,recipe.minutes],begin.bind(id))
		label(right,("需要 "+"、".join(needs)+"。 " if not needs.is_empty() else "")+recipe.desc,13,SUB)
	if selected=="farm":
		label(right,"点击地图田块可指定播种位置、查看长势或直接收获。",13,SUB)
		for crop in s.ready:btn(right,"收获 · %s   第 %d 块田"%[c.activities[crop.key].name,crop.plot+1],command.bind("harvest",crop.id))
	if selected=="ranch":label(right,"羊舍 %d 栏    ·    羁绊 %d"%[s.barn,s.bond],15)
	if selected=="market":
		label(right,"货币兑换",19)
		btn(right,"1 工作积分 → 3 谷币    ｜    余 %d"%snapshot.work,command.bind("exchange","work"))
		btn(right,"1 番茄金币 → 6 谷币    ｜    余 %d"%snapshot.coins,command.bind("exchange","coin"))
	if selected=="dungeon":
		var area:Array=c.areas[(int(s.floor)-1)%c.areas.size()]
		label(right,"第 %d 层 · %s\n%s   弱点技能 · %s"%[s.floor,area[0],area[1],c.classes[area[2]][1]],16)
		label(right,"续探上限 · 余 %d 层"%s.auto,15)
		var choices:=HBoxContainer.new()
		right.add_child(choices)
		for n in ["0","3","10","20"]:btn(choices,"关闭" if n=="0" else n+"层",command.bind("auto",n))
		var names:=PackedStringArray()
		for k in s.team:names.append(c.classes[k][0])
		label(right,"出战 · "+"、".join(names),16)
		for k in c.classes:btn(right,c.classes[k][0]+"   "+c.classes[k][1]+" Lv.%d"%(1+mini(5,int(s.mastery[k]/4))),change_team.bind(k))
		label(right,"点职业调整队伍。首次探胜可增加队伍位置。",13,SUB)
		btn(right,"掉落："+("保留全部" if s.filter=="all" else "普通装备分解"),command.bind("filter","rare" if s.filter=="all" else "all"))
	if selected=="forge":
		btn(right,"试打木桩   ·   攻击 %d"%snapshot.damage,command.bind("dummy"))
		for g in s.gear:btn(right,("◆ " if g.id==s.equipped else "装备  ")+g.name+"  +%d"%g.power+(" · "+c.classes[g.affix][1] if g.has("affix") else ""),command.bind("equip",g.id))
	label(right,"旅人背包",18)
	var items:=PackedStringArray()
	for k in s.inventory:
		if s.inventory[k]>0:items.append(c.items[k]+" ×%d"%s.inventory[k])
	label(right,"   ".join(items) if not items.is_empty() else "还没有物资",14,SUB)
	label(right,"谷地手记",18)
	if s.log.size()>8:btn(right,"查看全部近期手记",show_journal)
	for i in mini(8,s.log.size()):label(right,s.log[s.log.size()-1-i],14,SUB)
	if s.log.is_empty():label(right,"第一批收成将记在这里。",14,SUB)

func change_team(k:String):
	var s:Dictionary=snapshot.state
	var team:Array=s.team.duplicate()
	if team.has(k):
		if team.size()==1:return
		team.erase(k)
	else:
		if team.size()>=mini(3,1+int(s.companions)):team.pop_front()
		team.append(k)
	command("team",",".join(team))

func show_journal():
	var dlg:=AcceptDialog.new()
	dlg.title="谷地手记"
	add_child(dlg)
	var history:=TextEdit.new()
	history.editable=false
	history.wrap_mode=TextEdit.LINE_WRAPPING_BOUNDARY
	var lines:Array=snapshot.state.log.duplicate()
	lines.reverse()
	history.text="\n\n".join(lines)
	history.custom_minimum_size=Vector2(420,300)
	dlg.add_child(history)
	dlg.visibility_changed.connect(func():
		if not dlg.visible:dlg.queue_free())
	dlg.popup_centered()
