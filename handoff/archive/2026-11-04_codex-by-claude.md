# Codex → Claude：Codex 做的改动，Claude 请读取

> 本文件只由 **Codex** 追加记录，由 **Claude 阅读**。
> Claude 读完本文件全部记录后：把本文件内容整体移入 `handoff/archive/`，命名为
> `YYYY-MM-DD_codex-by-claude.md`（当天日期 + 谁做的 + 谁归档），再新建一个空的本文件（保留头部说明）。
> 详见 `handoff/HANDOFF.md` 的"归档规则"。

---

## 2026-11-04 — Codex（UI 复查、外置插件与工作区信任）
改动：ui/ui_components、files、storage、agent、settings、plugin_runtime/plugin_preferences、tray；extensions/plugins 下两个独立包；README/PLUGIN_SPEC/MAINTENANCE_MAP/ARCHITECTURE；tests/test_revision.py。
目的：处理主人本轮八项反馈，保留 Claude 的增量渲染方向，修复具体回归。
状态：完成，源码模式，未打包；运行中的旧窗口未终止，需要主人重启。

对方需要知道：
- _diag_log 调试引用全部移除。Claude 未提交的临时 pending 清理存在切片错误，已换成整行清理/流式正文落库时复用。欢迎行在首次发送移除；延迟分段继续追加且按 _message_rows 插回原消息位置；加载更早历史强制重建并按高度差保持阅读锚点；右键历史 itemsAt 改为 itemAt。
- 自动跟随状态跟用户实际滚动走；rangeChanged 只在跟随状态调度到底，回调检查 sid/跟随状态。新增气泡主动 show 避免延迟布局令 range 长时间为 0。Bubble.fit 解除旧 fixed minimum 后再 heightForWidth，解决每次多 4px 的隐性膨胀。主题在底继续跟随，读历史保持位置。字体从字节加载，避免 Windows 字体文件锁。
- 权限页显式信任开关：roles.<role>.roots[].trusted。用户本轮已明确授权增加此模式，因此更新 AGENTS 对应规则。信任工作区自动确认文件操作，仍校验权限/路径/冲突并备份；不免除 memory/MCP 审阅。新增 delete_file，目录删除加完整备份和清单重验；禁止根目录删除/移动、嵌套/跨卷移动。
- 停止变为停止并撤回：取消后等 worker.finished 才 Store.withdraw_turn，移除本轮输入与后续输出，全文进 audit，用户输入合并到原会话草稿。新草稿不覆盖。已执行文件操作不回滚。摘要跨过撤回边界则清空摘要恢复原始上下文。停止中的新增 text/changed 信号不再显示。
- 插件实现真正移到 extensions/plugins/time-context 和 daypart-greetings，每包 plugin.json/main.py/_conf_schema.json。宿主扫描加载；新增插件表单读取器，按角色持久参数。旧模块只兼容包装，不要把实现再搬回去。分发源码必须带 extensions。参考本机 AstrBot schema 规范，不是 AstrBot 全运行时兼容；未复制其代码/用户数据。详见重写后的 PLUGIN_SPEC。
- 寒暄 idle_minutes 默认 60，连续用户消息间隔 <=60 分钟不寒暄，超过再触发；0 为原每日每时段首次。凌晨重复/间隔优先，按角色配置。失败且无正文会释放预留，旧 v2 的 seen 不再令首次升级无响应。时间背景加 greeting_event 例外避免规则冲突；事件要求实际时段问候，正文进历史。没有真实付费 API 联调，不能承诺模型绝对遵循。
- 原生插件和旧 JSON 提示词行都有真实“设置”按钮。检查了 DPI 下实际窗口，修正 item padding 导致自定义行高度为 0；自定义 delegate 仅去掉底层重复 check indicator。不要仅测控件存在就判定可见可点。
- 外观/数据新增 close_to_tray（默认 false），源码也能关闭到托盘、继续任务；tray.py 管打开/退出。无系统服务/开机自启，不支持休眠后继续执行。
- Claude 本次全部交接已读并按规则归档到 archive/2026-11-04_claude-by-codex.md；原文件只保留头部。历史日期查询模块仍未实现，主人本轮没要求。

验证：改前 51 测试有 3 个滚动失败；改后原生 Qt 全量 61 测试通过（最终报告 docs/revision-results.txt）。覆盖真实设置按钮点击/参数生效、停止竞态、信任与删除备份、消息分段、流式复用、滚动、主题高度、插件卸载、凌晨/跨时段、失败释放、托盘不结束任务。所有测试临时 fixture，不用真实聊天/密钥。界面预览 docs/plugins-preview.png、plugin-options-preview.png。


## 2026-11-03 22:55 — Codex（时段寒暄 v2：本地触发 + 模型表达）
改动：daypart_greetings、agent、ui、settings、native_plugins；测试和文档。
目的：主人指出固定文案枯燥且角色不知道刚才寒暄过；明确允许改成本地代码 + LLM 回复，取代上一条纯本地方案。
状态：完成，不打包。
对方需要知道：UI 不再生成寒暄。Agent 普通请求按需附加事件，实际回复含寒暄，正常存 messages，下一轮可见。工具前输出正文后立即撤掉事件；纯工具块不撤。无额外模型请求，短事件有少量输入token，但不存消息、不累积。
插件库增量新增 triggers，seen/events 保留；旧本地气泡在原会话请求及压缩历史中补入，携带来源消息 ID，主数据不重写。旧 events 不分支复制；新版正常模型寒暄随历史复制。失败重试复用同条触发。记录的是触发预留，失败未重试时不自动补发。
验证：全量测试新增模型回复落库、工具后撤事件、失败重试与旧历史重放；结果见 docs/greeting-v2-results.txt。无真实API联调，不承诺模型绝不重复措辞。

## 2026-11-03 22:48 — Codex（时间插件可见 + 无 LLM 时段寒暄）
改动：native_plugins.py、daypart_greetings.py；agent/settings/storage/ui/time_context；test_greetings/test_ui；README、插件规范、维护地图、架构、验证日志与截图。
目的：主人要求独立时间插件在插件页可见；确认要新增时段首次寒暄与凌晨多次催睡，且不用 LLM 提示词实现。
状态：完成，不打包。45 tests OK（13.982s），原基线38 OK，原生插件页截图核查通过。
对方需要知道：
- 两个 native 插件以 itemData 区分 JSON prompt 插件，按角色开关，默认启用，旧设置缺省兼容。time_context 1.1.0 关闭时不会调用时间注入。
- Greetings 为独立本地规则模块；每角色每日8时段首次，凌晨默认每次用户新发送提醒（可设冷却或禁重复）。不挂机主动提醒。固定文案加角色语气，不靠 LLM，不增加 prompts/token。
- 插件状态及事件放 data/plugins/daypart-greetings/state.sqlite3，事务锁+唯一消息键。只读回事件插入显示，不添加 messages 行；关闭保留已显示历史。分支/导出目前不复制本地事件，README 已说明。
- UI send 存用户消息后触发，/compact、重试、工具循环不触发；失败记 audit 不阻断请求。重启或换同角色新会话不会重复首次问候。
- 新测试含各时段边界、跨日/跨角色/重启、重复提醒/冷却/幂等、独立开关、插件设置保存、气泡显示且不进入模型历史。未改真实用户数据，运行中的旧窗口需重启。

## 2026-11-03 22:32 — Codex（主人指定五项聊天 UI 修复）
改动：ui_components/ui/settings/storage；新增 chat_presentation.py、chat_preferences.py；requirements、UI/分段测试、README、维护地图。
目的：移除输入框灰字及此前吞键/占位符干预；主题切换不重建历史；可导入字体；气泡完整展开；短回复正则延时分段；隐藏成功工具记录与空白气泡。
状态：完成，源码模式，不打包。
对方需要知道：
- Composer 已删除旧 event/hasCommit/_sync_placeholder 路径，inputMethodEvent 只记录 preeditString 是否非空并调用 super。候选期间按键交回 Qt，不手动吞 Enter/Space；输入框无占位文字。
- Bubble 改用可选中的纯文本 QLabel，宽度测量自适应，最大为 chat viewport 减边距后 80%，高度 heightForWidth，无内部滚动。resize 时重新布局。主题切换原地 set_theme，不调用 render，不改变阅读位置。
- chat_display 配置向后兼容，UI 保存不覆盖其他设置；新字体文件复制到 assets/fonts，使用 QFontDatabase 应用内注册，不安装系统字体。默认 12pt/500，可改。
- 分段默认 threshold=150（严格小于才分）、random=1.5~3.5、log_base=10、正则与主人给定一致。regex==2026.9.29 已加入 requirements 并本机安装；25ms 超时回退全文。主线程 QTimer 延时显示，数据库不拆消息。切换角色计时继续，重启历史直接完整显示。
- 只读检查 Kia 最近 18 条消息的块结构，确认工具前 text 常是两个换行，原 `if text` 判断为真导致空泡。现历史和流式均过滤 whitespace，成功工具不渲染，失败/denied 显示说明。tool_use/tool_result 原样存库供 API 正常回传，未修改用户历史。
- 不重新引入成功工具按钮；审批弹窗保留。新增设置控件独立模块，避免继续扩大 Settings。
验证：原基线 29 OK；修改后全量 38 OK（12.588s），包括原生 Qt 预编辑/提交、长消息/80%宽度/缩窗/无内滚动、两次主题切换位置、导入本机测试字体与保存、工具空白过滤、跨角色分段计时、正则边界/超时。真实 Windows 拼音候选窗口的人工体验仍请主人在重启后确认；自动测试为 Qt 合成输入法事件。测试数据均在 tests 临时目录。源码更新需重启旧窗口。

## 2026-11-03 21:55 — Codex（时间插件、维护导航、组件拆分）
改动：time_context.py、agent.py、ui_components.py、ui.py、test_time_context.py；PLUGIN_SPEC.md、MAINTENANCE_MAP.md、HANDOFF.md、README、ARCHITECTURE 及测试记录。
目的：每轮新鲜日期/本地时间作为系统背景，避免日期过期和例行报时；明确插件创建合同和维护入口，降低重复读取成本。
状态：完成。本轮不打包、不动用户配置/数据、不安装 AstrBot。
对方需要知道：
- 已读完并确认你原有全部交接，归档到 archive/2026-11-03_claude-by-codex.md；暂停打包以及已修复主题/IME/thinking/目录工具均沿用。
- 唯一行为新增为 time_context：九角色常驻系统插件，无设置开关，不是 JSON 插件。取 OS 本地时区，精确到分钟，每用户轮/重试采样，同轮工具调用共享时间快照。纯整理压缩器不注入当前时间。不要重新加 agent 原来的 UTC 当前时间句子。
- UI 拆分只移动 text_label/button/TitleBar/Composer/Portrait/Bubble，逐字对比原实现一致。ui.py 同名导入兼容旧测试；以后改组件去 ui_components.py，编排去 ui.py。
- 插件规范唯一来源 PLUGIN_SPEC.md；维护职责唯一索引 MAINTENANCE_MAP.md。settings/agent 暂不再细拆。
- AstrBot 当前只是评估。优先可选原生运行时桥接以复用插件；JSON 插件加载器不能加载 AstrBot Python 插件。不宣称全市场兼容或已有桥。PoC 和第三方插件版本/许可证检查尚未实施。
- README 修正了源码启动、/compact 和已移除上下文详情按钮，保留其他功能。
验证：基线全量 26 OK；修改后 `python -m unittest discover -s tests -v` → 29 OK（13.302s）；diff --check 通过；移动的组件与 HEAD 原实现一致。新测试覆盖跨日/时区/九角色系统注入/不写 messages。测试为本地 mock，未做真人自然度 A/B 或真实 API 联调。
