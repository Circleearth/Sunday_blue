extends Control

signal plot_clicked(index: int)
signal greet
signal selected(site: String)
const Expedition = preload("res://expedition.gd")
const Farm = preload("res://farm.gd")
const SPOTS = {"farm":Vector2(144,291),"ranch":Vector2(408,230),"mine":Vector2(540,149),"forge":Vector2(470,409),"dungeon":Vector2(271,106),"market":Vector2(122,438)}
const PLAZA = Vector2(311,320)
const WORLD_SIZE = Vector2(640,512)
const NAMES = {"farm":"雾麦梯田","ranch":"月露牧场","mine":"星辉矿脉","forge":"溪畔工坊","dungeon":"雾门遗迹","market":"风铃集市"}
var place := "overview"
var open_plots:Array=[0,1,2]
var wheat_frames:Array[Texture2D]=[]
var farm_selection:=-1
var hover_plot:=-1
var state := {}
var catalog := {}
var phase := 0.0
var font: Font
var sprites := {}
var overlay: Texture2D
var hovered := ""
var strike := 0.0

func _ready():
	clip_contents=true
	texture_filter=CanvasItem.TEXTURE_FILTER_NEAREST
	mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	font = get_theme_default_font()
	var file := "res://art/valley.png"
	if FileAccess.file_exists(file):
		var img := Image.load_from_file(ProjectSettings.globalize_path(file))
		if img != null: overlay = ImageTexture.create_from_image(img)
	for id in ["keeper","keeper_portrait","sheep","farm","depth_1","depth_2","depth_3","depth","wheat","berry","swift","pierce","ward","foe_1","foe_2","foe_3"]:
		var path:="res://art/%s.png"%id
		if FileAccess.file_exists(path):
			var img:=Image.load_from_file(ProjectSettings.globalize_path(path))
			if img!=null:sprites[id]=ImageTexture.create_from_image(img)
	var atlas_file:="res://art/expedition-atlas.png"
	if FileAccess.file_exists(atlas_file):
		var atlas:=Image.load_from_file(ProjectSettings.globalize_path(atlas_file))
		if atlas!=null:
			var cell:=Vector2i(atlas.get_width()/3,atlas.get_height()/2)
			var keys:=["swift","pierce","ward","foe_1","foe_2","foe_3"]
			for i in keys.size():
				if sprites.has(keys[i]):continue
				var frame:=atlas.get_region(Rect2i(Vector2i(i%3,i/3)*cell,cell))
				var used:=visible_region(frame)
				if used.has_area():sprites[keys[i]]=ImageTexture.create_from_image(frame.get_region(used))
	var wheat_file:="res://art/wheat-growth.png"
	if FileAccess.file_exists(wheat_file):
		var wheat:=Image.load_from_file(ProjectSettings.globalize_path(wheat_file))
		if wheat!=null:
			var cell:=Vector2i(wheat.get_width()/4,wheat.get_height())
			for i in 4:
				var frame:=wheat.get_region(Rect2i(Vector2i(i*cell.x,0),cell))
				var used:=visible_region(frame)
				if used.has_area():wheat_frames.append(ImageTexture.create_from_image(frame.get_region(used)))
			if wheat_frames.size()!=4:wheat_frames.clear()
	mouse_exited.connect(func():
		hovered=""
		hover_plot=-1)

func visible_region(frame:Image) -> Rect2i:
	frame.convert(Image.FORMAT_RGBA8)
	var pixels:=frame.get_data()
	var width:=frame.get_width()
	var height:=frame.get_height()
	var low:=Vector2i(width,height)
	var high:=Vector2i.ZERO
	for y in range(0,height,3):
		for x in range(0,width,3):
			if pixels[(y*width+x)*4+3]>=110:
				low=Vector2i(mini(low.x,x),mini(low.y,y))
				high=Vector2i(maxi(high.x,x),maxi(high.y,y))
	if high.x<low.x or high.y<low.y:return Rect2i()
	var padding:=Vector2i(4,4)
	low=(low-padding).max(Vector2i.ZERO)
	high=(high+padding).min(Vector2i(width,height))
	return Rect2i(low,high-low)

func origin() -> Vector2:
	return (size-WORLD_SIZE*zoom())*0.5

func zoom() -> float:
	return minf(size.x/WORLD_SIZE.x,size.y/WORLD_SIZE.y)

func _gui_input(event):
	if place=="dungeon" or not event is InputEventMouse:return
	var point:Vector2 = (event.position-origin())/maxf(zoom(),0.01)
	var press:bool=event is InputEventMouseButton and event.button_index==MOUSE_BUTTON_LEFT and event.pressed
	hovered=""
	hover_plot=-1
	if place=="farm":
		for i in Farm.TILE_COUNT:
			if Farm.bounds(i).has_point(point):
				hover_plot=i
				if press:
					plot_clicked.emit(i)
					accept_event()
				break
		return
	if point.distance_to(PLAZA-Vector2(0,12))<24 and event is InputEventMouseButton and event.pressed and event.button_index==MOUSE_BUTTON_LEFT:
		greet.emit()
		accept_event()
		return
	for id in SPOTS:
		if point.distance_to(SPOTS[id]+Vector2(0,-7)) < 59:
			hovered=id
			break
	if event is InputEventMouseButton and event.button_index==MOUSE_BUTTON_LEFT and event.pressed and hovered!="":
		selected.emit(hovered)
		accept_event()

func _process(delta):
	if get_window().mode==Window.MODE_MINIMIZED:return
	phase=fmod(phase+delta,10000)
	strike=maxf(0,strike-delta)
	queue_redraw()

func poly(points: Array, tint: String):
	draw_colored_polygon(PackedVector2Array(points),Color(tint))

func oval(p: Vector2, radius: Vector2, tint: String):
	var pts := PackedVector2Array()
	for i in 32:
		pts.append(p+Vector2(cos(TAU*i/32)*radius.x,sin(TAU*i/32)*radius.y))
	draw_colored_polygon(pts,Color(tint))

func tree(p: Vector2, k: float):
	oval(p+Vector2(3,4),Vector2(14,5)*k,"86a493")
	draw_line(p,p-Vector2(0,28)*k,Color("795e47"),4*k,true)
	for i in 3:
		var y := p-Vector2(0,8+i*9)*k
		var w := (17-i*3)*k
		poly([y+Vector2(-w,0),y-Vector2(0,23)*k,y+Vector2(w,0)],["447b70","518e76","75a783"][i])

func house(p: Vector2, roof: String):
	oval(p+Vector2(0,6),Vector2(43,10),"92a381")
	draw_rect(Rect2(p-Vector2(30,34),Vector2(60,38)),Color("f3dfae"))
	for x in [-24,0,24]:
		draw_line(p+Vector2(x,-32),p+Vector2(x,3),Color("976b4f"),4)
	poly([p+Vector2(-39,-29),p+Vector2(-19,-56),p+Vector2(20,-56),p+Vector2(39,-29)],roof)
	draw_rect(Rect2(p+Vector2(6,-18),Vector2(14,22)),Color("715e50"))
	draw_rect(Rect2(p+Vector2(-20,-20),Vector2(12,12)),Color("7ba8a1"))

func sprite(id:String,foot:Vector2,height:float) -> bool:
	if not sprites.has(id):return false
	var texture:Texture2D=sprites[id]
	var dims:=texture.get_size()*height/texture.get_height()
	draw_texture_rect(texture,Rect2(foot-Vector2(dims.x*.5,dims.y),dims),false)
	return true

func sheep(p: Vector2):
	if sprite("sheep",p+Vector2(0,10),36):return
	oval(p+Vector2(0,10),Vector2(13,3),"87a388")
	for dx in [-7,7]:draw_line(p+Vector2(dx,2),p+Vector2(dx,9),Color("735d55"),3)
	oval(p,Vector2(14,10),"fff1d8")
	oval(p+Vector2(11,-4),Vector2(7,7),"816f68")
	draw_circle(p+Vector2(13,-6),1.5,Color.WHITE)

func plot_offset(i:int) -> Vector2:
	return Vector2((i%3-1)*30,(floori(i/3.0)-1)*13)

func fields(p: Vector2):
	var crops: Dictionary={}
	for job in state.get("jobs",[])+state.get("ready",[]):
		if job.key in ["berry","wheat"]:crops[int(job.plot)]=job
	for i in open_plots:
		var pos:=p+plot_offset(i)
		poly([pos+Vector2(-15,0),pos+Vector2(1,-8),pos+Vector2(17,0),pos+Vector2(1,8)],"a06e50")
		if crops.has(i) and sprites.has(crops[i].key):
			var j:Dictionary=crops[i]
			var tex:Texture2D=sprites[j.key]
			var part:=Vector2(tex.get_width()/3.0,tex.get_height())
			var frame:=clampi(int(3*(float(state.world)-float(j.start))/(j.end-j.start)),0,2)
			draw_texture_rect_region(tex,Rect2(pos-Vector2(14,26),Vector2(28,28)),Rect2(Vector2(frame*part.x,0),part))
			continue
		for n in 3:
			var seed:=pos+Vector2(n*5-5,1-n%2)
			draw_line(seed+Vector2(-4,2),seed+Vector2(3,-2),Color("ce9d68"),1.5,true)
			if crops.has(i):
				var j:Dictionary=crops[i]
				var growth:=clampf((float(state.world)-float(j.start))/(float(j.end)-float(j.start)),0,1)
				var top:=seed-Vector2(0,3+12*growth)
				draw_line(seed,top,Color("527e4b"),2,true)
				draw_circle(top,2+growth*2,Color("cb6882" if j.key=="berry" else "f4cb65"))

func _draw():
	draw_rect(Rect2(Vector2.ZERO,size),Color("182823"))
	draw_set_transform(origin(),0,Vector2.ONE*zoom())
	if place=="farm":
		Farm.render(self,state)
		return
	if place=="dungeon" and not catalog.is_empty():
		Expedition.render(self,phase,state,catalog)
		return
	if overlay:draw_texture_rect(overlay,Rect2(Vector2.ZERO,WORLD_SIZE),false)
	else:
		poly([Vector2(-80,117),Vector2(40,39),Vector2(96,65),Vector2(167,8),Vector2(216,57),Vector2(313,-4),Vector2(417,73),Vector2(523,4),Vector2(717,100),Vector2(717,-120),Vector2(-80,-120)],"92b7a5")
		for i in 41:
			var p:=Vector2(fmod(i*87.3,650),72+sin(i*2.4)*24)
			tree(p,0.57+fmod(i*0.21,.36))
		var river:=PackedVector2Array([Vector2(-100,158),Vector2(54,180),Vector2(114,222),Vector2(230,238),Vector2(254,292),Vector2(238,371),Vector2(305,419),Vector2(344,567)])
		draw_polyline(river,Color("9bbda6"),42,true)
		draw_polyline(river,Color("80bdba"),33,true)
		for i in 22:
			var y:=fmod(i*19+phase*5,355)
			var pair:=clampi(int(y/55),0,river.size()-2)
			var pos:=river[pair].lerp(river[pair+1],fmod(y/55,1))
			draw_line(pos,pos+Vector2(8,1),Color("b5dbcd"),1.5,true)
		for loc in SPOTS.values():
			draw_line(Vector2(318,329),loc,Color("d1bb91"),15,true)
			draw_line(Vector2(318,329),loc,Color("e7d4ac"),11,true)
		for i in 24:
			var p:=Vector2(fmod(i*93,635),180+fmod(i*63,311))
			var near:=false
			for loc in SPOTS.values():
				if p.distance_to(loc)<63:near=true
			if not near:tree(p,.72)
		for i in 65:
			var p:=Vector2(fmod(i*101+21,640),fmod(i*47+250,510))
			draw_circle(p,1.8,Color("ecdbab"))
	for id in SPOTS:
		var p:Vector2=SPOTS[id]
		if id==place or id==hovered:
			draw_arc(p,22,0,TAU,40,Color("edc77d"),2,true)
		if not overlay or id=="farm":
			draw_site(id,p)
		draw_site_label(id,p)
	draw_keeper()
	if strike>0 and place=="forge":
		draw_string(font,SPOTS.forge+Vector2(16,-45-(1-strike)*22),"✧",HORIZONTAL_ALIGNMENT_LEFT,-1,30,Color("ffe39a"))

func draw_site(id:String, p:Vector2):
	match id:
			"farm":fields(p)
			"ranch":
				house(p+Vector2(9,-8),"ad7862")
				sheep(p+Vector2(-24+sin(phase*.65)*12,5+abs(sin(phase*2))))
				sheep(p+Vector2(29+cos(phase*.4)*10,9))
			"mine","dungeon":
				var rock:="587674" if id=="mine" else "6c7788"
				poly([p+Vector2(-41,5),p+Vector2(-26,-33),p+Vector2(0,-48),p+Vector2(24,-33),p+Vector2(40,5)],rock)
				oval(p+Vector2(1,-6),Vector2(13,17),"384e53")
				for n in 3:
					var q:=p+Vector2(19+n*5,-4-n%2*5)
					poly([q+Vector2(-3,1),q+Vector2(-1,-10),q+Vector2(4,-3),q+Vector2(2,1)],"a3d7d2")
				if id=="dungeon":
					for job in state.get("jobs",[]):
						if job.key=="delve":
							var a:=p+Vector2(-24+sin(phase*3)*8,6)
							draw_circle(a,6,Color("e4b279"));draw_arc(a,13,-1.4+sin(phase*4),.8+sin(phase*4),9,Color("fff0ad"),2,true)
			"market":house(p,"618e99")
			"forge":
				house(p,"b96850")
				for n in 3:
					var t:=fmod(phase*.6+n*.34,1)
					draw_circle(p+Vector2(18+t*8,-53-t*21),3+t*4,Color(1,.98,.9,.5*(1-t)))
func draw_site_label(id:String, p:Vector2):
		if not catalog.is_empty():
			for job in state.get("jobs",[]):
				var site:String=catalog.activities[job.key].site
				if site==id or (site=="build" and id=="farm"):
					var ratio:=clampf((float(state.world)-float(job.start))/(job.end-job.start),0,1)
					draw_rect(Rect2(p+Vector2(-28,43),Vector2(56,3)),Color("83a393"))
					draw_rect(Rect2(p+Vector2(-28,43),Vector2(56*ratio,3)),Color("f9d77b"))
					if id=="mine":
						var tip:=p+Vector2(-19,-5)
						var hand:=tip+Vector2(-11,-14).rotated(sin(phase*3)*.6)
						draw_line(hand,tip,Color("a48557"),3,true)
						draw_line(hand-Vector2(5,0),hand+Vector2(5,1),Color("d9d7b3"),3,true)
					break

		var badge:=StyleBoxFlat.new()
		badge.bg_color=Color("22302c") if id==place else Color(0.10,0.16,0.15,0.86)
		badge.border_color=Color("ebc782") if id==place else Color("899a82")
		badge.set_border_width_all(1)
		badge.set_corner_radius_all(5)
		draw_style_box(badge,Rect2(p+Vector2(-42,18),Vector2(84,25)))
		draw_string(font,p+Vector2(-42,36),NAMES[id],HORIZONTAL_ALIGNMENT_CENTER,84,14,Color("fff5da"))

func draw_keeper():
	var npc:=PLAZA+Vector2(0,sin(phase*2))
	if overlay and sprites.has("keeper_portrait") and not sprites.has("keeper"):
		var texture:Texture2D=sprites.keeper_portrait
		var frame:=StyleBoxFlat.new()
		frame.bg_color=Color("273d36")
		frame.border_color=Color("edc77d")
		frame.set_corner_radius_all(6)
		frame.set_border_width_all(1)
		draw_style_box(frame,Rect2(npc+Vector2(-17,-41),Vector2(34,43)))
		draw_texture_rect_region(texture,Rect2(npc+Vector2(-15,-38),Vector2(30,38)),Rect2(texture.get_width()*.27,0,texture.get_width()*.48,texture.get_height()*.40))
	elif not sprite("keeper",npc,52):
		oval(npc,Vector2(12,4),"91a48d")
		poly([npc+Vector2(-11,-2),npc+Vector2(-5,-21),npc+Vector2(6,-21),npc+Vector2(12,-2)],"517f80")
		draw_circle(npc+Vector2(0,-28),9,Color("edc8a8"))
		draw_arc(npc+Vector2(0,-28),9,PI,TAU,12,Color("785746"),5,true)
		draw_circle(npc+Vector2(7,-33),3,Color("ecc473"))
	draw_string(font,npc+Vector2(-22,15),"铃禾",HORIZONTAL_ALIGNMENT_CENTER,44,13,Color("fff5da"))
