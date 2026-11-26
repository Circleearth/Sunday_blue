extends Control

const MAP = preload("res://map.gd")
const INK = Color("#f5e9cf")
const SUB = Color("#b8c7bb")
const GOLD = Color("#ebc782")
const SITE_BUTTONS = {"overview":"谷地地图", "farm":"农田", "ranch":"牧场", "mine":"矿区", "forge":"工坊", "dungeon":"遗迹", "market":"集市"}
var world_map
var stats := Label.new()
var status := Label.new()
var jobs := Label.new()
var right := VBoxContainer.new()
var orders := ProgressBar.new()
var workspace_tabs := {}
var ledger_scroll := ScrollContainer.new()
var portfolio := ""
var guide_dialog: AcceptDialog
var exchange_dialog: ConfirmationDialog
var sound := AudioStreamPlayer.new()
var poll := Timer.new()
var http := HTTPRequest.new()
var selected := "overview"
var chosen_plot := -1
var snapshot := {}
var busy := false
var signature := ""
var pending := {}
var sent_action := "view"
var lost_contact_at := -1
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
	b.alignment=HORIZONTAL_ALIGNMENT_LEFT
	b.custom_minimum_size.y=36
	b.mouse_default_cursor_shape=Control.CURSOR_POINTING_HAND
	b.add_theme_stylebox_override("normal",panel("273d36",6,11))
	b.add_theme_stylebox_override("hover",panel("394e43",6,11))
	b.add_theme_stylebox_override("pressed",panel("4b5c4a",6,11))
	b.add_theme_stylebox_override("disabled",panel("26302b",6,11))
	var focus:=panel("273d36",6,11)
	focus.draw_center=false
	focus.border_color=GOLD
	focus.set_border_width_all(1)
	b.add_theme_stylebox_override("focus",focus)
	b.add_theme_color_override("font_disabled_color",Color("a7b4a8"))
	b.add_theme_color_override("font_color",INK)
	b.add_theme_color_override("font_hover_color",INK)
	b.add_theme_color_override("font_pressed_color",INK)
	b.pressed.connect(task)
	parent.add_child(b)
	return b

func _ready():
	if OS.get_environment("SUNDAY_VALLEY_MANAGED")=="1":
		get_tree().auto_accept_quit=false
		if OS.get_environment("SUNDAY_VALLEY_BACKGROUND")=="1":get_window().mode=Window.MODE_MINIMIZED
		get_window().close_requested.connect(func(): get_window().mode=Window.MODE_MINIMIZED)
	var face:=SystemFont.new()
	face.font_names=PackedStringArray(["Microsoft YaHei UI","Microsoft YaHei","Noto Sans CJK SC","sans-serif"])
	theme=Theme.new()
	theme.default_font=face
	theme.default_font_size=15
	theme.set_color("font_color","Label",INK)
	theme.set_color("font_color","AcceptDialog",INK)
	theme.set_stylebox("panel","AcceptDialog",panel("23332e",12,18))
	theme.set_constant("separation","VBoxContainer",10)
	theme.set_constant("separation","HBoxContainer",8)
	get_window().min_size=Vector2i(920,580)
	var page:=PanelContainer.new()
	add_child(page)
	page.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	page.add_theme_stylebox_override("panel",panel("182823",0,16))
	var col:=VBoxContainer.new()
	page.add_child(col)
	var header:=HBoxContainer.new()
	col.add_child(header)
	var masthead:=VBoxContainer.new()
	masthead.add_theme_constant_override("separation",0)
	header.add_child(masthead)
	label(masthead,"雾铃谷",29,GOLD).autowrap_mode=TextServer.AUTOWRAP_OFF
	label(masthead,"WINDBELL VALLEY",11,SUB).autowrap_mode=TextServer.AUTOWRAP_OFF
	stats.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	stats.horizontal_alignment=HORIZONTAL_ALIGNMENT_RIGHT
	stats.vertical_alignment=VERTICAL_ALIGNMENT_CENTER
	header.add_child(stats)
	btn(header,"铃禾",greet)
	btn(header,"委托",open_portfolio.bind("orders"))
	btn(header,"背包",open_portfolio.bind("bag"))
	btn(header,"手记",open_portfolio.bind("journal"))
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
	for id in SITE_BUTTONS:
		var tab:=btn(nav,SITE_BUTTONS[id],set_place.bind(id))
		tab.alignment=HORIZONTAL_ALIGNMENT_CENTER
		tab.size_flags_horizontal=Control.SIZE_EXPAND_FILL
		workspace_tabs[id]=tab
	ledger_scroll.custom_minimum_size.x=324
	ledger_scroll.horizontal_scroll_mode=ScrollContainer.SCROLL_MODE_DISABLED
	var ledger:=PanelContainer.new()
	ledger.add_theme_stylebox_override("panel",panel("202f29",10,14))
	middle.add_theme_constant_override("separation",14)
	middle.add_child(ledger)
	ledger.add_child(ledger_scroll)
	ledger_scroll.add_child(right)
	right.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	right.add_theme_constant_override("separation",7)
	var activity:=PanelContainer.new()
	activity.add_theme_stylebox_override("panel",panel("22352e",8,10))
	atlas.add_child(activity)
	var feed:=VBoxContainer.new()
	feed.add_theme_constant_override("separation",5)
	activity.add_child(feed)
	for widget in [jobs,status]:
		widget.text_overrun_behavior=TextServer.OVERRUN_TRIM_ELLIPSIS
		feed.add_child(widget)
	orders.custom_minimum_size.y=4
	orders.show_percentage=false
	orders.add_theme_stylebox_override("background",panel("42584b",2,0))
	orders.add_theme_stylebox_override("fill",panel("d7b876",2,0))
	feed.add_child(orders)
	orders.hide()
	status.add_theme_font_size_override("font_size",13)
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
	get_window().focus_entered.connect(func():
		poll.start(2)
		refresh())
	refresh()

func greet():
	if is_instance_valid(guide_dialog):return
	var dlg:=AcceptDialog.new()
	guide_dialog=dlg
	dlg.title="与铃禾交谈"
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
		portrait.custom_minimum_size=Vector2(250,360)
		layout.add_child(portrait)
	var dialogue:=VBoxContainer.new()
	dialogue.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	dialogue.alignment=BoxContainer.ALIGNMENT_CENTER
	dialogue.custom_minimum_size.x=270
	layout.add_child(dialogue)
	label(dialogue,"铃禾",26,GOLD)
	label(dialogue,"守谷人",14,SUB)
	label(dialogue,line,18)
	dlg.visibility_changed.connect(func():
		if not dlg.visible:dlg.queue_free())
	dlg.popup_centered(Vector2i(610,440))

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
	chosen_plot=index
	world_map.farm_selection=index
	set_place("farm")

func begin(id:String):
	if chosen_plot>=0 and id=="expand":
		command("expand",str(chosen_plot))
	elif chosen_plot>=0 and snapshot.catalog.activities[id].site=="farm":
		command("sow",id+":"+str(chosen_plot))
	else:
		command("start",id)

func set_place(id:String):
	if id!="farm":
		chosen_plot=-1
		world_map.farm_selection=-1
	portfolio=""
	selected=id
	world_map.place=id
	rebuild(true)

func open_portfolio(kind:String):
	portfolio=kind
	rebuild(true)

func refresh():
	var minimized:=get_window().mode==Window.MODE_MINIMIZED
	Engine.max_fps=8 if minimized else 30
	poll.wait_time=15 if minimized else 2
	if not busy:send(pending if not pending.is_empty() else {"action":"view"})

func command(action:String,arg:String=""):
	if not pending.is_empty():
		status.text="正在同步上一项操作，请稍候。"
		return
	pending={"action":action,"arg":arg,"id":Crypto.new().generate_random_bytes(16).hex_encode()}
	if not busy:send(pending)

func send(data:Dictionary):
	if token.is_empty():
		status.text="请从 Sunday Blue 顶栏进入雾铃谷。"
		return
	busy=true
	sent_action=data.get("action","view")
	var err:=http.request(url,["Authorization: Bearer "+token,"Content-Type: application/json"],HTTPClient.METHOD_POST,JSON.stringify(data))
	if err!=OK:
		busy=false
		status.text="连接暂时不可用，正在重试。"

func receive(result:int,code:int,_headers:PackedStringArray,body:PackedByteArray):
	busy=false
	if result!=HTTPRequest.RESULT_SUCCESS and OS.get_environment("SUNDAY_VALLEY_MANAGED")=="1":
		if lost_contact_at<0:lost_contact_at=Time.get_ticks_msec()
		elif Time.get_ticks_msec()-lost_contact_at>120000:
			get_tree().quit()
			return
	else:lost_contact_at=-1
	if result!=HTTPRequest.RESULT_SUCCESS or code>=500:
		status.text="与 Sunday Blue 的连接中断，恢复后会核对上次操作。"
		return
	var data=JSON.parse_string(body.get_string_from_utf8())
	if not data is Dictionary:
		status.text="存档未响应。请从 Sunday Blue 顶栏重新进入。"
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
	world_map.open_plots=data.open_plots.map(func(value):return int(value))
	world_map.catalog=data.catalog
	stats.text="等级 %d   ·   %d 谷币   ·   %s"%[1+int(s.xp/10),int(s.cash),"专注流速 ×1" if data.running else "闲时流速 ×0.1"]
	update_orders(s,data.catalog)
	if data.message!="":
		status.text=data.message
		sound.play()
		world_map.strike=1.0
	elif first:status.text="点地图上的地点，安排生产或派遣伙伴。"
	var key:=JSON.stringify([s.ready,s.jobs,s.inventory,s.gear,s.cash,s.log,s.auto,s.team,s.filter,s.equipped,s.floor,data.open_plots,data.coins,data.work])
	if key!=signature:
		if not first and data.message=="" and not s.log.is_empty():status.text=s.log.back()
		signature=key
		rebuild()

func update_orders(s:Dictionary,c:Dictionary):
	if s.jobs.is_empty():
		orders.hide()
		jobs.text="暂无进行中的委托"
		return
	var nearest:Dictionary=s.jobs[0]
	for task in s.jobs:
		if task.end<nearest.end:nearest=task
	orders.show()
	orders.value=100*clampf((s.world-nearest.start)/(nearest.end-nearest.start),0,1)
	if portfolio=="orders":
		for task in s.jobs:
			var key:String=task.id
			var row:=right.get_node_or_null(NodePath(key)) as VBoxContainer
			if row:
				row.get_child(1).value=100*clampf((s.world-task.start)/(task.end-task.start),0,1)
				row.get_child(2).text="剩余 %d 游戏分钟"%ceili(maxf(0,task.end-s.world)/60)
	var remaining:=ceili(maxf(0,nearest.end-s.world)/60)
	jobs.text="下一项完成  ·  %s  ·  %d 游戏分钟"%[c.activities[nearest.key].name,remaining]
	if s.jobs.size()>1:jobs.text+="  /  共 %d 项"%s.jobs.size()
	jobs.tooltip_text=""
	for task in s.jobs:
		jobs.tooltip_text+="%s  ·  %d 游戏分钟\n"%[c.activities[task.key].name,ceili(maxf(0,task.end-s.world)/60)]

func rebuild(reset_scroll:bool=false):
	var previous:=ledger_scroll.scroll_vertical
	for id in workspace_tabs:
		var tab:Button=workspace_tabs[id]
		var active:bool=id==selected and portfolio.is_empty()
		tab.add_theme_color_override("font_color",GOLD if active else INK)
	for child in right.get_children():
		right.remove_child(child)
		child.queue_free()
	if snapshot.is_empty():return
	var s:Dictionary=snapshot.state
	var c:Dictionary=snapshot.catalog
	if not reset_scroll:ledger_scroll.set_deferred("scroll_vertical",previous)
	else:ledger_scroll.scroll_vertical=0
	if portfolio=="orders":
		label(right,"委托进度",23,GOLD)
		for task in s.jobs:
			var order:=VBoxContainer.new()
			order.name=task.id
			right.add_child(order)
			label(order,c.activities[task.key].name,17)
			var progress:=ProgressBar.new()
			progress.show_percentage=false
			progress.custom_minimum_size.y=5
			progress.add_theme_stylebox_override("background",panel("42584b",2,0))
			progress.add_theme_stylebox_override("fill",panel("d7b876",2,0))
			order.add_child(progress)
			label(order,"",13,SUB)
		if s.jobs.is_empty():label(right,"暂无进行中的委托。",14,SUB)
		update_orders(s,c)
		return
	if portfolio=="bag":
		label(right,"旅人背包",23,GOLD)
		for item in s.inventory:
			if s.inventory[item]>0:
				label(right,"%s   × %d"%[c.items[item],s.inventory[item]],16)
		if s.inventory.values().all(func(amount):return amount==0):
			label(right,"暂无物资。种植、采矿或探索后会自动入库。",14,SUB)
		label(right,"装备  %d / 32"%s.gear.size(),16,GOLD)
		for gear in s.gear:
			label(right,"%s   攻击 +%d%s"%[gear.name,gear.power,"  ·  已装备" if gear.id==s.equipped else ""],15)
		btn(right,"前往工坊",set_place.bind("forge"))
		return
	if portfolio=="journal":
		label(right,"谷地手记",23,GOLD)
		for index in range(s.log.size()-1,-1,-1):
			label(right,s.log[index],14,SUB)
		if s.log.is_empty():label(right,"生产、远征与收获会记录在这里。",14,SUB)
		return
	if selected=="overview":
		label(right,"谷地地图",25,GOLD)
		label(right,"选择地点，查看可用的生产、探索和交易。",14,SUB)
		for id in world_map.NAMES:
			btn(right,world_map.NAMES[id]+"   ›",set_place.bind(id))
		return
	label(right,world_map.NAMES[selected],25,GOLD)
	var info={"farm":"播种与开垦","ranch":"喂养苔羊，收集月露乳与苔绒","mine":"从青铜露头到星辉晶脉","forge":"加工矿石、锻造与配装","dungeon":"派遣队伍，战斗结束后自动回收战利品","market":"交易与谷币兑换"}
	label(right,info[selected],14,SUB)
	var active_plots:=MAP.Farm.tasks(s)
	var plot_open:bool=chosen_plot>=0 and world_map.open_plots.has(chosen_plot)
	if selected=="farm":
		farm_controls(s,c,active_plots,plot_open)
	for id in c.activities:
		var recipe:Dictionary=c.activities[id]
		if selected=="farm" and chosen_plot>=0:
			if plot_open and (recipe.site=="build" or active_plots.has(chosen_plot)):continue
			if not plot_open and (recipe.site=="farm" or active_plots.has(chosen_plot)):continue
		if recipe.site!=selected and not (selected=="farm" and recipe.site=="build"):continue
		var needs:=PackedStringArray()
		for k in recipe.inputs:needs.append(c.items[k]+" ×"+str(int(recipe.inputs[k])))
		var action_name:String=("种植 " if recipe.site=="farm" else "")+recipe.name
		var action:=btn(right,"%s   %d 谷币 · %d 分"%[action_name,recipe.cost,recipe.minutes],begin.bind(id))
		var reason:String=snapshot.get("availability",{}).get(id,"")
		action.disabled=not reason.is_empty()
		action.tooltip_text=recipe.desc
		label(right,reason if not reason.is_empty() else ("所需  "+"、".join(needs) if not needs.is_empty() else recipe.desc),13,SUB)
	if selected=="farm" and chosen_plot<0 and s.ready.size()>1:
		btn(right,"收获所有成熟作物 · %d 块田"%s.ready.size(),command.bind("harvest","all"))
	if selected=="ranch":label(right,"羊舍 %d 栏    ·    羁绊 %d"%[s.barn,s.bond],15)
	if selected=="market":
		label(right,"货币兑换",19)
		btn(right,"1 工作积分 → 3 谷币    ｜    余 %d"%snapshot.work,confirm_exchange.bind("work")).disabled=snapshot.work<1
		btn(right,"1 番茄金币 → 6 谷币    ｜    余 %d"%snapshot.coins,confirm_exchange.bind("coin")).disabled=snapshot.coins<1
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
		for k in c.classes:
			var deployed:bool=k in s.team
			var role:=btn(right,("已出战 · " if deployed else "")+c.classes[k][0]+"  "+c.classes[k][1]+" Lv.%d"%(1+mini(5,int(s.mastery[k]/4))),change_team.bind(k))
			role.disabled=deployed and s.team.size()==1
		var capacity:=mini(3,1+int(s.companions))
		label(right,"出战位 %d / %d。队伍已满时，新成员替换队首。"%[s.team.size(),capacity],13,SUB)
		btn(right,"掉落："+("保留全部" if s.filter=="all" else "普通装备分解"),command.bind("filter","rare" if s.filter=="all" else "all"))
	if selected=="forge":
		btn(right,"试打木桩   ·   攻击 %d"%snapshot.damage,command.bind("dummy"))
		for g in s.gear:btn(right,("◆ " if g.id==s.equipped else "装备  ")+g.name+"  +%d"%g.power+(" · "+c.classes[g.affix][1] if g.has("affix") else ""),command.bind("equip",g.id))
func farm_controls(s:Dictionary,c:Dictionary,active:Dictionary,plot_open:bool):
	var pick:=GridContainer.new()
	pick.columns=4
	right.add_child(pick)
	for i in MAP.Farm.TILE_COUNT:
		var tile:=btn(pick,"%02d"%(i+1),choose_plot.bind(i))
		tile.size_flags_horizontal=Control.SIZE_EXPAND_FILL
		tile.alignment=HORIZONTAL_ALIGNMENT_CENTER
		tile.tooltip_text=MAP.Farm.title(i,world_map.open_plots,active,s)
		if i==chosen_plot:tile.add_theme_color_override("font_color",GOLD)
	if chosen_plot<0:
		label(right,"点击田块或编号，指定播种或开垦的位置。",13,SUB)
		return
	var state_name:String=MAP.Farm.title(chosen_plot,world_map.open_plots,active,s)
	label(right,"第 %d 块田 · %s"%[chosen_plot+1,state_name],17,GOLD)
	if active.has(chosen_plot):
		var job:Dictionary=active[chosen_plot]
		var plant:String=c.activities[job.key].name
		if s.world>=job.end and plot_open:
			btn(right,"收获 "+plant,command.bind("harvest",job.id))
		else:
			label(right,plant+"已加入委托。可在「委托」查看实时进度。",13,SUB)

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

func confirm_exchange(source:String):
	if is_instance_valid(exchange_dialog):return
	var dlg:=ConfirmationDialog.new()
	exchange_dialog=dlg
	dlg.title="兑换谷币"
	dlg.dialog_text="消耗 1 工作积分，获得 3 谷币。" if source=="work" else "消耗 1 番茄金币，获得 6 谷币。"
	dlg.ok_button_text="确认兑换"
	dlg.cancel_button_text="取消"
	add_child(dlg)
	dlg.confirmed.connect(command.bind("exchange",source))
	dlg.visibility_changed.connect(func():
		if not dlg.visible:dlg.queue_free())
	dlg.popup_centered()
