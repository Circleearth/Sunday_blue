# Claude → Codex：Claude 做的改动，Codex 请读取

> 本文件只由 **Claude** 追加记录，由 **Codex 阅读**。
> Codex 读完本文件全部记录后：把本文件内容整体移入 `handoff/archive/`，命名为
> `YYYY-MM-DD_claude-by-codex.md`（当天日期 + 谁做的 + 谁归档），再新建一个空的本文件（保留头部说明）。
> 详见 `handoff/HANDOFF.md` 的“归档规则”。

---

## 2026-11-12 16:55 — 占位挡输入问题：已解决（主人验收通过），改动未提交，待推送

接续 16:30 那条交棒记录——问题最后**已用简单办法解决，不需要 Codex 接手**，但改动目前**只在工作区，未 commit 未 push**（主人要求先不推，等 Codex 读到时一起处理或直接推）。

**真正的根因（之前理解错了）**：我前几版用了 `setSpecialValueText('未记录')`——那是**真实文本**占位，Qt 编辑器不接受在文字中间直接敲数字，所以必须全选。正确做法就是主人提示的方向：占位改成**灰色 placeholder 提示，框内实际是空字符串**，敲数字自然直接生效。

**最终方案**（全部在 `sunday_blue/module_views/life_work.py` 一个文件，工作区未提交改动）：
- 新增 `PlaceholderSpin(QSpinBox)`：`textFromValue` 在空值时返回 `''`，`未记录`/`未设置` 只作为 `placeholderText` 灰字提示；`zero_is_placeholder=True` 时 0 值也显示灰字（工作页预计时长「未设置」用的就是 0 值灰字）。
- `hm_pair`（屏幕/娱乐）与 `clock_pair`（睡觉/起床）改用 `PlaceholderSpin`；`spin()` 统一入口（工作页预计时长/实际进度等）也改用。
- **删掉了已推送的 `f6670ae`（WIP）里引入的 `AutoSelectSpin` 那套 focusIn/selectAll/事件过滤器**——它还在推送历史里，请确认没有别处引用 `AutoSelectSpin` 或 `setSpecialValueText`（life_work.py 内已全清）。`f6670ae`/`6f9888e` 两笔提交本身可视为被当前工作区改动替代，回退时直接丢弃即可。
- 原测试断言（`test_life_work_views.py` 里的 `page.bed.value() is None` / `empty_clock.value()` 等）**不需要改**，PlaceholderSpin 保持同样的 `.value()`/`.load()` 语义，29 项相关测试本地通过。

**主人验收的语义（已确认"完美"）**：点进空框直接敲数字立即生效；两框都没动 = 未填（睡觉/起床拦上报、屏幕/娱乐不入库）；碰了任一个，另一个按 0。

**给 Codex 的动作**：读完后把工作区这两个文件（`life_work.py` + 本 handoff）commit + push 当前分支即可，或者主人之后会让 Claude 推；`f6670ae` 的 WIP 不需要单独修复。

## 2026-11-12 16:30 — Claude 交棒：生活上报/工作页数字输入框「占位挡输入」问题（已被 16:55 记录取代，留档）

**问题（主人原话核对过）**：`module_views/life_work.py` 里所有带占位文字的输入框（睡觉/起床/屏幕/娱乐的「未记录」、工作页预计时长的「未设置」），**不先拉选/全选就敲数字不生效**，框还停在占位文字。主人要求：直接点进框输数字就要替换掉占位。

**原因（已审计确认）**：Qt `QSpinBox` 的 `specialValueText` 占位文字在键盘焦点进来时**不自动全选**，直接按数字被编辑器拒收；必须先 Ctrl+A / 拉选再输才有效。

**Claude 的尝试（未完成、未提交，主人试玩后说仍不行，交给 Codex 决定怎么做）**：
- 工作区里留有未提交改动：`sunday_blue/module_views/life_work.py` 加了 `AutoSelectSpin(QSpinBox)` 子类（`focusInEvent` 里 `lineEdit().selectAll()`），套用在 `hm_pair`/`clock_pair`/`spin()`；`tests/test_life_work_views.py` 加了键盘路径的替换断言。全量 203 tests OK，键盘模拟（FocusIn 事件 + 按键）验证通过。
- **已知缺口**：鼠标点击路径未验证——`QSpinBox.mousePressEvent` 先让 lineEdit 在点击处放下光标，可能盖掉 focusIn 的 selectAll（Qt 6.11 事件顺序未实测）。主人实际点按仍反馈未解决。
- 可以整段采纳也可以废弃重做（例如改 `lineEdit().textChanged` 驱动、或干脆把占位改成 0 值 + 明确的「留 0 = 未记录」语义），由接手方定。

**主人已确认的语义（改动必须保持）**：
- 睡觉/起床：两个框都没碰过 = 未填，点上报弹「缺少数据」并拦下本次不上报；碰了任一个，另一个没填按 0 算（只填 6 小时 = 06:00）。
- 屏幕/娱乐：都没碰 = 未记录不入库（不存 0）；碰了任一个，另一个按 0。
- 范围：生活上报 4 组（hm_pair/clock_pair）+ 工作页 `spin()` 统一入口的占位框，两处都要修（主人确认过）。

**相关近期提交**（勿回退已推送部分）：`99cc5f5`（生活页游戏属性化 + 对齐输入 + 肌肉逐日衰减）、`abfca28`（占位输入框行为第一版，键盘路径 OK、鼠标路径存疑）、`f6670ae`（WIP：`AutoSelectSpin` 子类只改 `life_work.py`，仅键盘路径验证过，鼠标点击路径未验证）。

## 2026-11-12 15:40 — Claude：生活模块 UI 整理（今日状态游戏属性化 + 生活上报对齐输入 + 肌肉群逐日衰减）

主人新指令（本轮优先）：生活-今日状态与「生活上报」两块 UI 只改界面与显示，但主人明确授权了两处底层逻辑调整（见下②④），并已确认改动范围。

**给 Codex 的重点提醒（你可能做了占位/勾稽，请核对）：**

1. **我删除/废弃了这些符号**（如果别处有引用请知悉）：
   - `module_views/life_work.py` 里的 `nullable_number()` / `nullable_value()` 辅助函数已删（生活上报的屏幕/娱乐输入改成 `hm_pair()` 时不再用 QDoubleSpinBox 的 -1 哨兵）。若其他文件 import 了这两个函数会报错。
   - `LifePage` 的 `self.has_sleep`（睡眠勾选框）已删，改为你确认过的「睡觉/起床必填、缺失不上报」逻辑。测试里原来 `page.has_sleep.setChecked(True)` 那行已删。
   - `LifePage` 的 `self.muscles`（QLabel 文字版肌肉参考）已删，换成 `self.muscle_box`（QVBoxLayout）+ `self.muscle_tiles`（色块列表）。
   - 导入列表里去掉了 `QTime`、`QTimeEdit`、`QGridLayout`（life_work.py 已不再使用）。`QDoubleSpinBox` 仍在用（`finish_activity` 结算），保留。

2. **底层 `life_state.MUSCLES` 键改名了**（主人确认要改成「胸/背/肩/二头肌/三头肌/核心」，去掉「手臂」「臀腿」）：
   - `MUSCLES` 现在是 `{'胸','背','肩','二头肌','三头肌','核心'}`。
   - `modules/life.py::exercise()` 里校验 `muscles` 是否有效用的是这个新表，所以**旧数据里存的「手臂」「臀腿」不再被新记录接受**，但数据库里的旧 exercise_details 行我没动（保留历史）。新写 `muscles=` 参数请用新 6 个部位名。
   - 我加了 `DEFAULT_PARTS`（life_state.py 顶部）：`{'足球':['肩','二头肌','三头肌','核心'],'快走':['核心'],'慢跑':['核心'],'羽毛球':['肩','二头肌','三头肌','核心'],'骑行':['核心']}`。之前旧代码里「足球/羽毛球→臀腿」的默认映射被并入上面的表。**如果你别处也写了 kind→部位 的映射，请同步。**
   - `duty_tools.py` 里工具描述字符串里的「手臂/臀腿」已改成「二头肌/三头肌」。

3. **`life_state.muscles(day)` 返回结构变了**（从「前一天一次性打分」改成「逐日衰减」）：
   - 旧：`[{'part','level','load'}]`，level ∈ {unknown,red,orange,yellow,green}（按前一天总负荷阈值 75/45/20）。
   - 新：`[{'part','age','level'}]`，**去掉了 `load` 键**，加了 `age`（最近一次训练距今天数，未训过=None）。level 现在是按「距最近一次训练 N 天」映射：当天=red、+1天=orange、+2天=yellow、≥3天=green。只看最近 4 天窗口内的记录。
   - `module_views/life_work.py` 的 `refresh_energy()` 已用 `MUSCLE_COLORS`（红/橙/黄/绿，无灰）渲染。若你或别的代码读 `r['load']` 会 KeyError。

4. **`ReminderSettings` 无改动**，本轮只动生活模块。但注意我这次动了 `life_work.py` 的 `LifePage`，它和 `WorkPage`/`DutiesPage` 同文件——我没动后两者。

**改动文件清单：**
- `sunday_blue/modules/life_state.py`：MUSCLES 键改名、新增 DEFAULT_PARTS、重写 `muscles()` 为逐日衰减（去 load 加 age）。
- `sunday_blue/modules/life.py`：`exercise()` 里 muscles 校验自动跟随新 MUSCLES，无额外改动；「运动」类别从 focus categories 移除的既有逻辑保持不变（我没动）。
- `sunday_blue/modules/duty_tools.py`：工具描述字符串部位名更新。
- `sunday_blue/module_views/life_work.py`：今日状态页改游戏属性风（体力/专注/视疲劳三条彩色进度条、肌肉群纵排色块、过去 7 天参考改整数）；生活上报页删睡眠勾选、睡觉/起床改必填+两个整点数字框、屏幕/娱乐改 [小时][分钟] 两个数字框（留空=未记录）；运动对话框部位选项换成新 6 部位。
- `tests/test_life_work_views.py`：删 has_sleep、改 bed/wake/phone 调用方式、加必填拦截断言。
- `tests/test_desktop_upgrade.py`：肌肉测试改新部位名与新 level 语义（前一天 high 训练→orange，非 red；4 天前→green）。

**验证：** 全量 `python -m unittest discover -s tests -v` → **203 tests OK（127.6s）**。另单独跑了一个临时数据冒烟：新建 LifePage，今日力量训练 60min high + 昨日快走，确认 muscle_tiles=6、睡觉/起床默认 None、load 后 '23:00'/'06:30'，进度条格式为整数「20 / 32 点」类。

**未做：** 生活上报的「屏幕使用时长」仍只映射到 phone_total（旧字段口径，未新增独立 screen 输入）；体力/专注条的「点」单位是按 physical_cap 折算的展示，不是新计量；未改 FocusPage 或番茄钟。

## 2026-11-11 10:10 — Claude：专注记录加金币数 + 共享提醒 QQ 渠道诊断/配置

主人新指令（本轮优先于旧 UI-only 边界）：① 专注模块记录中显示本次获得金币；② 检查 QQ 渠道是否接通并帮忙配置。授权范围经主人确认：最小方案，QQ 渠道检测做到「token 验证 + 发一条测试消息」。

改动文件：

1. `modules/focus.py`：`records()` 改为 LEFT JOIN `coin_ledger`（`c.id='focus:'||a.id`），每条记录新增 `coins` 列（无结算行则为 0）。未动 finish()/结算事务。
2. `module_views/focus.py`：记录列表项显示 `· +N 金币`（N=0 时显示「未达时长不发币」）；刷新去重 key 加入 coins。
3. `modules/reminder_delivery.py`：新增只读 `diagnose()`（shared_qq openid 是否配置 → DSH 凭据是否存在 → 调 `module._token` 实测连通，不发消息）与 `test_send()`（发一条固定试发消息）。`_transport()` 加载 `run.py` 时若 hub root 下没有插件文件（测试空根），回退到包内仓库路径；不碰守护进程/插件自身代码。
4. `module_views/planner.py` 的 `RemindersPage.qq()` 对话框：未配置 `shared_qq` 时自动预填第一个有 `qq_openid` 的角色插件配置（当前实际来自 rui）；新增「检查连通」「试发一条」按钮，结果写进对话框内状态标签；保存不再依赖 accept 才生效（保存即写库并关窗）。
5. `tests/test_shared_features.py`：新增 `test_focus_records_include_earned_coins_and_qq_channel_diagnosis`——用 125 秒检查点造一条有效记录断言 `records()[0]['coins']>0` 且页面列表含「+」；用假 transport（patch `_transport`）断言 diagnose 三态（openid 缺失 / 凭据缺失 / 全通）与 `test_send()` 成功路径，不发真实网络请求。

实测（主人已授权）：`shared_qq` 已由 rui 角色插件配置写入 `data/modules.sqlite3`；`diagnose()` 真实返回 openid/凭据/token 三项全 OK；`test_send()` 已向主人 QQ 发出一条「🟢 Sunday Blue 试发消息」，返回成功。凭据仍只读 `~/.dsh/profiles/qqbot/`，未复制进任何配置。

验证：全量 `python -m unittest discover -s tests -v` → **145 tests OK（97.4s，基线 144，+1）**；app 原生启动 12 秒无异常。

给 Codex 的注意：`Focus.records()` 的返回结构变了（多一个 `coins` 键），如有下游按旧字段消费请知悉；`reminder_delivery` 现在多了两个可公开调用的方法（diagnose 只读、test_send 会真实发消息，勿在无用户触发时调用）。原 qq-reminders 插件与其 daemon 一行未改。

## 2026-11-10 22:30 — 用户额外备注（主人让 Claude 代记，不是改动记录，读完知悉即可）

**滴答清单（Dida365/TickTick）skill 整理版**。这是 Claude 侧的一个 skill（完整文件：`C:\Users\zsc18\.claude\skills\dida365\SKILL.md`，仓库外，无需读原文件，下面就是整理后的全文要点）。主人口头备注，仅让 Codex 知悉这个模块的存在与规矩，**不构成对 Sunday_Blue 的任何任务或授权**。

要点：

1. **入口**：模块在 `D:\AICG\rui\dida\dida.mjs`（Node CLI + 可 import 的函数二合一，Rui 侧 `rui_dida` 工具委托它，聊天链路不直连网络）。任何读写滴答都走这个模块，不直接调 HTTP API。
   - CLI（Node 用 `D:\Appdate\Node_js\node.exe`，绝对路径调用）：`status` / `projects` / `tasks` / `add "<标题>"` / `done <词>` / `delete <词>`；健康检查另有 `audit.mjs`（只读）。
   - 代码调用（要指定清单/优先度/循环）：`import { loadCfg, addTask, completeTask, deleteTask, createGroups, createList, parseWhen } from 'file:///D:/AICG/rui/dida/dida.mjs'`。
2. **鉴权**：`dida/config.json` 的 token 是浏览器 HttpOnly cookie `t`；**token 绝不打印/进日志/进 git**。401 `user_not_sign_on` = 凭据失效，去浏览器重取 token 即可，不要改代码。
3. **易踩的 API 语义**（模块已封装，知道即可）：写操作 `POST /api/v2/batch/task` 必须带 `x-device` 头；"当日完成"查询的 `to` 必须带时刻；提醒用**单数** `reminder` 字段且值 `'0M'`（`reminders` 数组 / `PT0M` 无效）；单次任务**不写** `repeatFlag`（写 `"0"` 会被 App 渲染成每天循环），循环用 `P1D` 等 ISO 周期串。
4. **规矩**：滴答只放任务（会被执行/划掉的），偏好、备忘、项目状态不进滴答；打勾看"任务本意达成"，拿不准就回显说明不动手。
5. **迭代纪律**：只有确定性、可复现的报错才改模块/文档；凭据失效、网络抖动、业务拒绝一律不改。
6. **与 Sunday_Blue 的边界（给 Codex 的提醒）**：该模块属于 Rui 的 QQ 聊天项目（`D:\AICG`），不在本仓库。本仓库（AGENTS.md）**禁止引入对其它项目/目录的运行时依赖**；如果后续 Sunday_Blue 需要写滴答（例如提醒能力），应通过调用 dida.mjs 的独立进程方式做外部集成并保持隔离，且先向主人确认，不要擅自加 import/子进程依赖。

读完这条即可，不需要为它做任何代码改动。

