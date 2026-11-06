# 维护地图（按任务定位，不按模型分地盘）

先读 AGENTS.md → HANDOFF.md → master-notes.md → 对方 to- 文件 → README。
只读任务涉及的文件和测试；不要为了解背景扫描 data、MasterData、维护备忘录或 archive。对方记录全部处理后按归档规则归档，存量归档不修改。

| 要改什么 | 入口/负责区域 | 验证 |
|---|---|---|
| 窗口布局、角色/历史切换、后台任务信号 | sunday_blue/ui.py / MainWindow | tests/test_ui.py |
| 拼音输入、气泡尺寸、立绘绘制、标题拖动 | sunday_blue/ui_components.py | UI 测试 + 原生输入法验证 |
| 设计变量、深浅色、精选字体 | sunday_blue/design_system.py / theme.py / docs/UI_DESIGN_SYSTEM.md | 两种主题原生窗口 |
| 设置页、导入、配置控件 | sunday_blue/settings.py | 设置保存/旧配置 |
| 人格拼接、工具分发、压缩、取消 | sunday_blue/agent.py | test_core Agent 测试 |
| 时间注入 / 寒暄 | extensions/plugins/{time-context,daypart-greetings}/main.py | test_time_context.py / test_greetings.py / test_revision.py |
| QQ 定时提醒（已正常运行，主人要求 Codex 除非恶性 bug 勿改） | extensions/plugins/qq-reminders/（main.py 工具+设置面板、daemon/run.py 守护、daemon_ctl.py 检查/启停）+ extensions/skills/qq-reminders/SKILL.md | test_qq_reminders.py + 本机试发 |
| 插件发现 / 参数表单 | sunday_blue/plugin_runtime.py / plugin_preferences.py | test_revision.py |
| LivingMemory、独立 Ollama、图谱 | extensions/plugins/livingmemory/ + sunday_blue/living_memory.py / memory_preferences.py；细分见 docs/LIVINGMEMORY.md | test_memory_personas.py + scripts/test_livingmemory_live.py |
| 人格编辑、版本恢复 | sunday_blue/personas.py / persona_preferences.py；四份人格文件；旧流程在 personas/_archive | test_memory_personas.py |
| 已确认记忆编辑、左右差异审阅 | sunday_blue/memory_editor.py / change_review.py / files.py | test_memory_personas.py + test_ui.py |
| 后台托盘 | sunday_blue/tray.py | test_revision.py |
| API 协议、流式/思考块 | sunday_blue/provider.py | 两协议 mock 测试 |
| 路径/权限、文件与目录操作 | sunday_blue/files.py | 权限、审阅、冲突测试 |
| 数据库、配置、分支、凭据 | sunday_blue/storage.py | 持久化、分支、迁移测试 |
| JSON 插件、Skill、MCP transport | sunday_blue/extensions.py | 插件规范 + MCP mock |
| 启动 | main.py、Start Sunday Blue.cmd | 源码模式启动；暂不打包 |
| 插件开发合同 | handoff/PLUGIN_SPEC.md | 实现与规范一致 |

本轮仅把独立 UI 组件从约 558 行的 ui.py 移出，原行为不改，ui.py 保留同名导出以兼容旧调用。MainWindow 仍负责协调；settings.py 约 294 行、agent.py 约 215 行，暂不细拆。不要用多继承 mixin 隐藏跨模块状态。

以后单模块超过约 500–700 行且包含独立职责、重复读取成本明显时再评估拆分；行数是检查信号，不是机械指标。公共入口兼容、先补关键回归测试，再移动实现。禁止仅为“更细”拆成几十个小文件。新增复杂设置页或独立视觉组件不要继续堆入主窗口。

职责归代码模块，不永久分配给 Claude/Codex。双方修改同一区域先确认 git 状态及交接，保留对方未提交改动。文档单一权威：README 管用户操作；本文件管定位；PLUGIN_SPEC 管扩展合同；HANDOFF 管协作规则；各 to- 文件管此次事实。docs/ARCHITECTURE.md 管跨层关系，变更时链接定位地图，避免复制多份规范。

维护完成：检查 diff（尤其数据/凭据）→全量 tests→写自己的交接→提交→push。只提交本轮明确文件，不把用户资料随 git add -A 带出去。暂停打包，除非主人重新要求。文档记录“已实现/规划/未验证”，不能混写。

## 聊天显示补充

`chat_presentation.py` 管分段纯函数、间隔、按角色字体加载及工具失败识别；`chat_preferences.py` 管界面字体、角色气泡字体和分段控件。配置存 settings.json/ui_display 与 chat_display.role_fonts，旧配置缺省兼容。ui.py 管计时与展示，ui_components.py 的 Bubble 使用无内滚动的 QLabel，禁止恢复为固定高度 QTextBrowser。成功回执仍落库，不要在 storage/provider 删除工具块。

插件已外置到 extensions/plugins/<id>，不再在 native_plugins 写死登记。native_plugins/time_context/daypart_greetings 仅兼容旧入口；实际加载和配置读取器见 plugin_runtime，表单见 plugin_preferences。UI 的 legacy_greetings 只读旧气泡，不触发新问候。完整接口合同见 PLUGIN_SPEC。

2026-11-04：ui.py 继续负责增量行和滚动状态，_message_rows 维持同消息延迟分段顺序；Bubble.fit 必须先解除旧固定高度再计算，防止每次增长 4 像素。不要重新引入 _diag_log 临时调试全局。停止先 cancel 再等待 finished 后 Store.withdraw_turn，避免跨线程删写竞争。后台关闭由 tray.py 管理，不运行服务、不打包。
