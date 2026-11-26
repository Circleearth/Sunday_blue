extends RefCounted

# Illustrated route is shared by the live expedition and the last battle replay.
static func render(map, p: float, s: Dictionary, c: Dictionary):
	var j:Dictionary={}
	for job in s.get("jobs",[]):
		if job.key=="delve":j=job
	if j.is_empty():j=s.get("last_expedition",{})
	var layer:=int(j.get("floor",s.get("floor",1)))
	var back: String="depth_%d"%(1+(layer-1)%3)
	if not map.sprites.has(back):back="depth"
	if map.sprites.has(back):
		map.draw_texture_rect(map.sprites[back],Rect2(0,0,640,512),false)
	else:
		paint_fallback(map,p,layer)
		map.house(Vector2(97,321),"946a55")
	var hud:=StyleBoxFlat.new()
	hud.bg_color=Color(0.055,0.105,0.108,0.86)
	hud.set_corner_radius_all(8)
	map.draw_style_box(hud,Rect2(20,23,352,87 if j.is_empty() else 168))
	map.draw_string(map.font,Vector2(36,56),"遗迹  /  第 %d 层"%layer,HORIZONTAL_ALIGNMENT_LEFT,-1,24,Color("fff0d6"))
	if j.is_empty():
		map.draw_string(map.font,Vector2(38,93),"队伍正在营地休整",HORIZONTAL_ALIGNMENT_LEFT,-1,17,Color("d6dfc6"))
		return
	var b:Dictionary=j.battle
	var turns:Array=b.rounds
	var fraction:=clampf((float(s.world)-float(j.start))/(j.end-j.start),0,1)
	var idx:=mini(turns.size()-1,int(fraction*turns.size()))
	if fraction>=1:idx=turns.size()-1
	var turn:Dictionary=turns[idx]
	var x:=218+fraction*76
	for i in j.team.size():
		var pos:=Vector2(x-i*60+sin(p*2.4)*2,363+7*i+abs(sin(p*2+i))*2)
		map.oval(pos+Vector2(0,10),Vector2(23,5),"2c423e")
		if map.sprite(j.team[i],pos+Vector2(0,9),86):continue
		var cloak:String={"swift":"78b587","ward":"aa90bf","pierce":"bd7e69"}[j.team[i]]
		map.oval(pos+Vector2(0,7),Vector2(14,4),"52695c")
		map.poly([pos+Vector2(-10,3),pos+Vector2(0,-24),pos+Vector2(12,3)],cloak)
		map.draw_circle(pos+Vector2(0,-23),8,Color("eed0a7"))
		map.draw_arc(pos+Vector2(0,-23),8,PI,TAU,12,Color("624f49"),4,true)
	var foe:=Vector2(433,368+sin(p*2)*3)
	var kind:=(layer-1)%3
	map.oval(foe+Vector2(0,10),Vector2(29,6),"2c423e")
	var illustrated:bool=map.sprite("foe_%d"%(kind+1),foe+Vector2(0,15),100)
	if not illustrated and kind==1:
		map.poly([foe+Vector2(-22,8),foe+Vector2(-17,-14),foe+Vector2(2,-24),foe+Vector2(21,-8),foe+Vector2(18,9)],"939f9c")
	elif not illustrated and kind==2:
		for side in [-1,1]:
			map.oval(foe+Vector2(15*side,-10+sin(p*4)*3),Vector2(13,11),"b5a1c8")
		map.oval(foe,Vector2(6,12),"e7d2aa")
	elif not illustrated:map.oval(foe,Vector2(20,14),"a3bb97")
	if not illustrated:
		for side in [-1,1]:
			if kind==0:map.poly([foe+Vector2(5*side,-10),foe+Vector2(14*side,-26),foe+Vector2(16*side,-7)],"93b09b")
			map.draw_circle(foe+Vector2(6*side,-1),2,Color("3a5450"))
	if fraction<1:
		var arc_center:=foe-Vector2(36,38)
		map.draw_arc(arc_center,24,-1.5+sin(p*4),.5+sin(p*4),20,Color("f3df9d"),2,true)
	map.draw_string(map.font,Vector2(38,88),b.area+"   ·   "+b.enemy,HORIZONTAL_ALIGNMENT_LEFT,-1,18,Color("e7e6cd"))
	var caption: String = "回合 %d    %s    伤害 %d"%( [idx+1,turn.skill,int(turn.hit)] )
	if fraction>=1:caption=("远征成功   ·   " if b.won else "队伍回营   ·   ")+caption
	map.draw_string(map.font,Vector2(38,121),caption,HORIZONTAL_ALIGNMENT_LEFT,-1,16,Color("ebd7a6"))
	for i in 2:
		var width:float=118*(float(turn.stamina)/b.stamina if i==0 else float(turn.hp)/b.hp)
		var start:=Vector2(39+i*172,170)
		map.draw_string(map.font,start-Vector2(0,9),"队伍体力" if i==0 else "敌方体力",HORIZONTAL_ALIGNMENT_LEFT,-1,14,Color("d6dfc6"))
		map.draw_rect(Rect2(start,Vector2(118,6)),Color("334643"))
		map.draw_rect(Rect2(start,Vector2(width,6)),Color("c7d598" if i==0 else "d99682"))

static func paint_fallback(map, p:float, layer:int):
	var tint=["435e58","505b69","534f69"][(layer-1)%3]
	map.draw_rect(Rect2(0,0,640,512),Color(tint))
	for i in 21:
		var x:float=fmod(i*97,720)-40
		var h:float=72+fmod(i*73,94)
		map.poly([Vector2(x-60,110),Vector2(x,-14),Vector2(x+26,h)],"34474c")
	for i in 40:
		var x:=fmod(i*79,640)
		var y:=fmod(i*41,300)
		map.draw_circle(Vector2(x,y+sin(p*.7+i)*2),1.4,Color("b4c2a1"))
	# Broken aqueduct and hanging lanterns establish the route silhouette.
	for i in 6:
		var col:=Vector2(58+i*111,235+sin(i*2.1)*14)
		map.draw_line(col,col+Vector2(0,71),Color("68746a"),13,true)
		map.draw_rect(Rect2(col-Vector2(11,5),Vector2(22,8)),Color("838a76"))
		map.draw_arc(col+Vector2(55,0),55,PI,TAU,22,Color("66766d"),8,true)
		for vine in 3:
			var leaf:=col+Vector2(vine*4-4,3+vine*9)
			map.draw_line(leaf,leaf+Vector2(2,12),Color("79926f"),2,true)
		if i%2==1:
			var lamp:=col+Vector2(12,37+sin(p+i))
			map.draw_line(col+Vector2(12,4),lamp,Color("999479"),1,true)
			for ring in [11,7,4]:
				map.draw_circle(lamp,ring,Color(.98,.84,.50,.13 if ring>4 else .94))
	var route:=PackedVector2Array([Vector2(-50,378),Vector2(104,347),Vector2(250,369),Vector2(435,310),Vector2(681,346)])
	map.draw_polyline(route,Color("2b4143"),64,true)
	map.draw_polyline(route,Color("8e947b"),52,true)
	for i in 15:
		var xy:=Vector2(fmod(i*79,630),390+fmod(i*59,100))
		map.poly([xy+Vector2(-9,0),xy+Vector2(-4,-16),xy+Vector2(3,-22),xy+Vector2(6,-3)],"88b8b7")
	for i in 43:
		var mote:=Vector2(fmod(i*83.7,640),363+fmod(i*37,139))
		map.draw_line(mote,mote+Vector2(4,1),Color("71877a"),1.4,true)
