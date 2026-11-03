# Codex → Claude：Codex 做的改动，Claude 请读取

> 本文件只由 **Codex** 追加记录，由 **Claude 阅读**。
> Claude 读完本文件全部记录后：把本文件内容整体移入 `handoff/archive/`，命名为
> `YYYY-MM-DD_codex-by-claude.md`（当天日期 + 谁做的 + 谁归档），再新建一个空的本文件（保留头部说明）。
> 详见 `handoff/HANDOFF.md` 的"归档规则"。

---

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
