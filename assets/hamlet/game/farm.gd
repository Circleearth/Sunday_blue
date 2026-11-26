extends RefCounted

const TILE_COUNT = 8
const EDGE = Color("#253630")
const GOLD = Color("#f1c573")
const TEXT = Color("#fff1d2")

static func bounds(index:int) -> Rect2:
	return Rect2(61+(index%4)*132,145+floori(index/4.0)*152,122,123)

static func tasks(state:Dictionary) -> Dictionary:
	var active:Dictionary={}
	for job in state.get("jobs",[])+state.get("ready",[]):
		if job.has("plot"):active[int(job.plot)]=job
	return active

static func title(index:int, open:Array, active:Dictionary, state:Dictionary) -> String:
	if not open.has(index):
		return "开垦中" if active.has(index) else "待开垦"
	if not active.has(index):return "空地"
	return "可收获" if state.world>=active[index].end else "生长中"

static func render(map, state:Dictionary):
	map.draw_rect(Rect2(0,0,640,512),Color("#637b53"))
	if map.sprites.has("farm"):
		map.draw_texture_rect(map.sprites.farm,Rect2(0,0,640,512),false)
	var open:Array=map.open_plots
	var active:=tasks(state)
	for index in TILE_COUNT:
		var rect:=bounds(index)
		var is_open:=open.has(index)
		var state_name:=title(index,open,active,state)
		var outline:=GOLD if map.farm_selection==index else Color("#b6d3a1") if map.hover_plot==index else EDGE
		var tile:=StyleBoxFlat.new()
		tile.bg_color=Color("#86513d") if is_open else Color("#576f4d")
		tile.border_color=outline
		tile.set_border_width_all(3)
		tile.set_corner_radius_all(9)
		tile.shadow_color=Color(0.05,0.09,0.07,0.55)
		tile.shadow_size=3
		tile.shadow_offset=Vector2(2,4)
		map.draw_style_box(tile,rect)
		var middle:=rect.get_center()
		if is_open:
			for i in 5:
				var row:=rect.position.y+17+i*16
				map.draw_line(Vector2(rect.position.x+14,row),Vector2(rect.end.x-14,row),Color("#ae7753"),3)
				map.draw_line(Vector2(rect.position.x+14,row+3),Vector2(rect.end.x-14,row+3),Color("#704434"),2)
			if active.has(index):
				draw_crop(map,middle,active[index],state)
		else:
			map.draw_circle(middle-Vector2(0,10),18,Color("#3d5945"))
			map.draw_line(middle+Vector2(-7,-10),middle+Vector2(7,-10),Color("#d1dcb5"),2)
			map.draw_line(middle+Vector2(0,-17),middle+Vector2(0,-3),Color("#d1dcb5"),2)
		map.draw_rect(Rect2(rect.position.x+7,rect.end.y-30,rect.size.x-14,22),EDGE)
		map.draw_string(map.font,Vector2(rect.position.x+7,rect.end.y-14),"%02d  %s"%[index+1,state_name],
			HORIZONTAL_ALIGNMENT_CENTER,rect.size.x-14,14,GOLD if state_name=="可收获" else TEXT)

static func draw_crop(map, center:Vector2, job:Dictionary, state:Dictionary):
	var growth:=clampf((float(state.world)-float(job.start))/(job.end-job.start),0,1)
	if job.key=="wheat" and not map.wheat_frames.is_empty():
		var stage:=3 if growth>=1.0 else mini(2,floori(growth*3))
		var texture:Texture2D=map.wheat_frames[stage]
		var height:float=[24.0,34.0,49.0,64.0][stage]
		var size:=texture.get_size()*height/texture.get_height()
		for offset in [-26,0,26]:
			var foot:=center+Vector2(offset,20 if offset==0 else 11)
			map.draw_texture_rect(texture,Rect2(foot-Vector2(size.x/2,size.y),size),false)
	else:
		for offset in [-24,0,24]:
			var foot:=center+Vector2(offset,17)
			var tip:=foot-Vector2(0,10+35*growth)
			map.draw_line(foot,tip,Color("#355742"),4)
			map.draw_circle(tip,7+growth*4,Color("#c4788e") if job.key=="berry" else GOLD)
