# 雾铃谷

Sunday Blue 启动时会在后台启动游戏引擎。工作页的「进入雾铃谷」打开或唤醒同一游戏窗口，点击游戏窗口的关闭按钮会把它收回后台。在系统托盘可用时，关闭主窗口会让 Sunday Blue 驻留托盘，选择托盘菜单「退出软件」会同时关闭游戏引擎。游戏按经过的时间和有效专注记录结算进度。

## 第一次进谷

初始 24 谷币。可以先种一块雾麦，同时开采青铜矿。雾麦成熟后点击收获，再喂苔羊；青铜矿可以熔炼、锻造或扩田。种灯莓、售奶都可以赚回谷币。集市也可以用工作积分或番茄金币单向兑换，金额在按钮上显示。

遗迹入口先选队伍，再派遣。远征的阵容与攻击在出发时固定。每层有弱点，伙伴技能随出战提升。首胜结识伙伴后可以增加队伍位置。开启续探后，每一层单独收取谷币，战败、到达指定层数或谷币不足都会停下。击败敌人后有机会发现补给或装备；可在工坊配装、试打木桩，在遗迹设置普通装备自动分解。点击村中央的铃禾可交谈。

## 时间与存档

- 完成专注、活动补报、商城兑换各自保留原来的核算。游戏只从真实计时运行的累计秒数取得加速，补报和休息不会加速。相对建档时刻，世界秒数等于实际经过秒数的 10% 加有效专注秒数的 90%。
- 新开生产与远征耗时 28–70 游戏分钟。作物成熟后保留到收获。关游戏后无需常驻游戏循环，重开按结束时间逐项结算，包括离线的续探。
- 存档在现有模块数据库的 `hamlet.v2`，旧版 `hamlet.v1` 留存。旧作物折为麦穗，旧攻强折为旧谷铁剑；迁居时一次性扣除旧档已消耗的工作积分。工作成就仍按历史收入累计。谷币流水在 `hamlet_ledger`；兑换的来源流水和游戏流水共用操作编号。
- 场景通过带临时令牌的本机回环接口发送结构化指令。重试使用同一操作编号。真实账本由 Sunday Blue 写入。

## 运行与维护

运行文件为 `runtime/godot/Godot.exe`（Windows x64，Godot 4.6 标准版 GUI 可执行文件）。当前电脑已放置 4.6.2。新检出源码时需要自行放置引擎，也可用环境变量 `SUNDAY_GODOT` 指向对应可执行文件。便携目录包含引擎、相邻授权说明、主程序和外部 `assets/hamlet/game`。编辑或替换游戏内容后重新进入谷地即可加载。

`catalog.json` 定义生产配方、时长、货物、职业技能、装备原型、区域弱点和探索事件。`world.py` 负责事务、战斗计算与存档；`page.py` 管理进程和接口。`Valley.tscn` 为游戏入口，地图、遗迹和操作界面分别在 `map.gd`、`expedition.gd`、`valley.gd`。用 Godot 编辑器打开 `project.godot` 可检查场景。完整游戏从工作页进入。

在项目根目录运行 `python -m unittest discover -s tests -p test_hamlet.py -v`。使用临时数据库；本机安装引擎时也实际启动场景，点击生产、兑换和远征。仅测试环境的 `SUNDAY_VALLEY_CAPTURE` 可指定引擎视口验证图路径。

## 美术替换

正式图片放入 `assets/hamlet/game/art/`。缺图时用引擎绘制场景、人物与作物。下列路径均相对于该目录。场景与人物请分开出图。主风格见 [美术方向](ART_DIRECTION.md)。

| 文件 | 规格与构图 | ComfyUI Positive | ComfyUI Negative |
| --- | --- | --- | --- |
| valley.png | 1280×1040，不透明。溪流穿过中央，六个互动地块留空，布局以 map.gd 中的 640×520 逻辑坐标为准。 | Original cozy fantasy farming valley, three-quarter overhead orthographic view, winding mint stream, layered wooded hills, willow trees and meadow paths, clean ink contours, warm muted greens and honey light, six quiet clearings for separate structures, polished browser RPG environment painting | characters, houses in the clearings, text, UI, watermark, dithering, noise, harsh shadows, cluttered center |
| keeper.png | 256×320，透明，三头身，脚底居中 | Full-body chibi valley keeper, chestnut bob, small brass bell hairpin, teal apron over linen dress, relaxed friendly posture, clear silhouette, hand-painted cel shading, soft daylight, isolated transparent background | photorealism, extra limbs, malformed fingers, detached accessories, cropped feet, scenery, text, signature |
| keeper_portrait.png | 768×1024，透明，半身略向右 | Visual novel half-body portrait of the same chestnut-haired valley keeper, brass bell hairpin, teal apron and linen blouse, warm knowing smile, natural anatomy, expressive eyes, delicate linework, diffuse outdoor daylight, isolated transparent background | chibi proportions, extra hands, distorted shoulders, text, frame, logo, scenery |
| sheep.png | 256×192，透明，四足着地 | Small woolly moon sheep, moss-green ears and charcoal hooves, three-quarter side view facing right, gentle playful silhouette, clean hand-painted browser RPG creature sprite, transparent background | human limbs, extra legs, duplicate animal, text, checkerboard, cropped feet, noisy details |
| wheat.png / berry.png | 384×128，透明，三个等宽方格依次为幼苗、成长、成熟。两种作物单独生成。 | Single species farm crop growth strip, three evenly spaced aligned orthographic sprites, tiny sprout then leafy stems then golden ripe wheat ears (use ruby lantern berries for the berry strip), rooted at bottom center of each cell, clean shapes, transparent background | soil tile, grid lines, labels, fourth stage, inconsistent perspective, mixed species, shadow plate |
| depth_1.png / depth_2.png / depth_3.png | 各 1280×1040，不透明，横向行进带位于下方三分之一，分别为苔桥、矿廊、星遗迹。 | Hand-painted side-view expedition backdrop, ruined moss aqueduct for region one, copper mine galleries for region two or luminous astral ruins for region three, separate image per setting, lantern accents, open lower-third walking lane and quiet upper-left HUD area, restrained layered depth | heroes, monsters, writing, HUD, watermarks, pure black shadows, excessive bloom, busy foreground |
| swift.png / pierce.png / ward.png | 各 256×320，透明，朝右。游侠弓、剑士破甲锤、术士月杖分别单独生成。 | Single chibi adventurer facing right, distinct ranger bow, armored breaker hammer or moon mage staff for the selected class, feet on one baseline, readable action silhouette, three-head proportions, clean painted edges, isolated transparent background | group portrait, mixed weapons, cropped weapon, extra fingers, inconsistent scale, text, noise |
| foe_1.png / foe_2.png / foe_3.png | 各 256×256，透明，朝左。苔耳团子、石壳守卫、星灯蝶分别单独生成。 | Single fantasy opponent facing left, choose moss-eared round forest creature, weathered stone-shell sentinel or moth with softly glowing lavender wings, clear species silhouette, stylized hand-painted shading, centered full body, isolated transparent background | mixed species, humans, extra legs, duplicates, realism, blurred outline, text, watermark |
