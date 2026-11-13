# 模块索引与增量维护约定

2026-11-10。先读本索引和最新 Handoff，再读任务所在模块；不要默认全项目扫描、遍历 `data/`、读取私聊或截图。

## 当前入口与边界

| 需求 | 优先读取 | 必要测试 |
|---|---|---|
| 页面导航 / 后台生命周期 | `main.py` 的 install_workspace 调用；`modules/workspace.py`、`modules/hub.py` | `test_module_views.py` |
| 专注、有效记录、结算 | `modules/focus.py`、`module_views/focus.py` | `test_modules.py`、`test_module_views.py` |
| 番茄钟阶段 / 声音设置 | `modules/focus_preferences.py`、`focus_alarm.py`、`module_views/focus_settings.py`；Hub 的 focus_timer | `test_pomodoro.py` |
| 金币、奖励、独立现实预算 | `modules/rewards.py`、`module_views/rewards.py` | 同上 |
| 关系、情绪衰减、明确的负面事件 | `modules/relations.py`、`module_views/relations.py` | `test_modules.py` |
| 群聊、读空气、@、总结、主动交流 | `modules/social.py`、`module_views/social.py` | `test_modules.py`、`test_module_http.py` |
| 私聊 ↔ 群聊连续记忆 | `modules/memory_bridge.py`、social.recent_context、agent.system_prompt | `test_module_http.py` |
| 现实事实读取，不重复归档 | `modules/activity.py`、capabilities/Agent 的 activity 接口 | `test_modules.py`、`test_module_http.py` |
| 角色独立模型 / 请求诊断 | `models.py`、`model_preferences.py`、provider 协议参数段 | `test_module_http.py`、`test_capabilities.py` |
| 事件插件示例 | `extensions/plugins/focus-cheer`、hub._plugin_events | `test_modules.py` |
| 既有角色增删 / 人格 | `roles.py`、role_lifecycle、personas | 本轮不扩展删除；旧验收已完成 |

路径省略的宿主模块都在 `sunday_blue/`；测试都在 `tests/`。

## 数据所有权与通信

新增的 `data/modules.sqlite3` 是模块账本，**不在角色删除范围内**：

- focus_runs / activity_records：计时与真实活动；role_id 只是陪伴参与者，不是数据所有者。
- focus_timers：新增附属表（run_id 对应 focus_runs），保存阶段、固定时长、轮次间隔快照和结束原因。不改旧表结构；无元数据的旧计时按原正计时处理。配置在 module_settings.pomodoro_options；自选音频复制到 data/sounds/focus。
- coin_ledger / rewards / redemptions：虚拟金币与兑换；real_budget 另记现实预算，只有用户确认入口可写实际支出。
- module_events / module_receipts：持久事件与消费者回执。产生事实的事务同时写事件；消费者按 event_key 去重。
- relationships / relationship_history：长期关系、短期情绪、事件来源分别保存。
- social_groups / group_messages：群成员与公开发言，保留当时显示名。
- shared_episodes / episode_readers：共同摘要及参与者读取范围。
- private_followups：主动私聊发件箱；聊天库的 module_message_links 提供跨库交付去重，不重发已有消息。
- social_calls：群聊/主动交流的预算预留，失败请求也占次数，防止重试无限消耗。
- request_diagnostics：模型、协议、耗时、usage、错误类型、实际请求的推理参数；不存正文或密钥。

模块互相复用 service 方法和事件，不在 UI 直接执行 SQL。角色变动不能删除模块记录、金币、兑换或群聊经历。不要迁移到“每角色一套活动数据库”，不要自动复制真实账本到多个记忆主库。

## 已实现的规则

- 专注用单调时钟累计，Hub 独立每秒检查/持久化（不依赖页面可见）；超过 30 秒调度空档视为休眠/长暂停，自动暂停，不奖励离线时间。重启后从暂停恢复，正常暂停不计时；异常退出可能丢最近一个检查间隔，不能宣称绝对零损失。
- 严格超过 120 秒才有效；每完整分钟 1 金币，每天最多 180 专注金币。结算、记录、发币、事件在一个事务中，重复结束不重复奖励。
- 番茄钟默认专注 25 / 短休息 5 / 长休息 15 分钟，每 4 个完整番茄建议长休息；到点截断到目标时长、自动结算一次并发一次提醒，下一阶段手动开始。休息不写 activity_records、不发币、不发 focus.completed 事件。提前结束仅按实际有效专注结算，不增加完整番茄数。旧版无元数据的计时仍手动结束。跨午夜按结束日统计，原始起止时间保留。
- 声音通过 QtMultimedia 懒加载播放；三个阶段独立音频、总开关/音量、试听；缺文件/解码失败尝试系统提示音并显示原因，不能因此撤销已经提交的结算。不自动重播上次关机前的提示。默认 WAV 由本地代码生成，无下载依赖；MP3/WAV 导入上限 20 MB，最长播放 30 秒。
- 关系默认 50，日正增量最多 6；负反馈只来自用户明确报告，每天最多 -1，关系不低于 30。没记录与缺席不产生负事件。情绪半衰期 3 小时；礼物不是恢复所必需。
- 群聊每话题有角色尝试上限，允许 `[SILENT]`；用户 @ 优先，角色 @ 可调换下一位候选。发言/沉默决定落回执，同源重试不让所有角色再说一遍。不实现无限后台互聊。
- 主动群聊默认关闭；用户选择目标群、开启事件分享后才从真实专注事件发起。少量闲聊需另开启。静默时段、专注状态、冷却、每日调用及保守 Token 估算预算在代码中检查。
- Rui 会后私聊另行开关；只跟进其参与的、包含需跟进事项的摘要，最多约每 12 小时尝试一次；静默或专注时延后。不依据缺席推断偷懒。

## 双向连续记忆（最新用户要求）

群聊默认启用角色自己的私聊支撑，可按群关闭：每个发言角色读取自己最近 24 小时最多 6 条、总计约 1800 字的私聊，自己的确认记忆，以及已启用 LivingMemory 的检索结果。**不读取其他角色私聊**。这是生成背景，不把原文直接复制进群聊数据库；模型仍需只自然引用相关经历，不能宣称程序能保证模型绝不引用任何私聊细节。

私聊直接接入当前角色参与群聊的最近原文和摘要，默认约 1 小时窗口；不等向量召回。共同摘要只写一次，已启用 LivingMemory 的参与者分别通过幂等队列接收；未启用者不追补。Ollama 仍为同一独立服务、手动启动；离线时保留近期直连上下文，正常聊天继续。

原始活动事实直接查询模块账本；LivingMemory 处理历史对话与共同摘要。自动摘要和 AI 推断不冒充用户确认。

## 模型与成本

角色配置 `model_profile` 可覆盖连接/模型/DPAPI 密钥及推理参数，未覆盖时沿用全局。可填写轻互动模型，群聊与主动短互动关闭额外推理；私聊和记忆整理使用该角色主配置。推理支持由服务商声明 + 用户显式测试确认，不根据型号名称猜测，不声称自动发现了远端能力。

社交预算按输入 UTF-8 字节数加最大输出保守预留，不是服务商精确 Token 计费器。最终 usage 单独显示，失败也占调用次数。普通用户主动私聊不受社交预算限制。

## 验证与回退

新链路测试使用 `tests/sunday-test-*` 临时目录和本地 HTTP 服务；不得用真实聊天、正式 data 或用户密钥做测试。每条关键链路提交 Git 检查点。代码可按对应提交回退；新增模块库保留，不删除、不倒灌旧数据。需要换回旧入口时只在代码版本层回退 install_workspace，不能删除用户模块账本。不要运行 build.ps1，仍从 .cmd/main.py 启动。

更详细的下一轮制作任务只在 `handoff/codex-to-claude.md` 最新段维护，不另建任务系统。

番茄钟版本回滚前先结束当前阶段（尤其是休息），再回退代码；旧版本不认识休息元数据。保留新增表和音频，不通过删库回滚。


## 共享功能与限额增量（2026-11-10）

仅按下表增量阅读；本次用户明确要求不制作 Claude 交接任务，维护记录放本索引及 README。

| 模块 | 文件 | 数据边界 |
|---|---|---|
| 动态番茄钟气泡 | modules/focus_dialogue.py | 后台线程 + Qt 信号；事件请求 ID 丢弃过时回包，临时上下文不入聊天。每日调用计数独立 module_settings。 |
| 月度现实奖励额度 | modules/allowance.py + rewards.py | allowance_policy / allowance_months / allowance_usage；人民币分；与兑换同事务占额，次月新额度，累积结转。 |
| 共享提醒/打卡 | modules/planner.py | schedules / reminder_occurrences / checkins / checkin_history；循环实例稳定唯一键，保留历史。 |
| 两渠道投递 | modules/reminder_delivery.py | 电脑声与 QQ 分别记状态；QQ 复用原插件 transport 函数，不改守护代码；外部发送与本地库不能承诺 exactly-once。 |
| 记录整理 | modules/organizer.py；extensions/plugins/kia-organizer | organized_records / record_revisions；逻辑分类目录、来源/内容哈希去重、可撤销、不自动确认 AI 推断。 |
| 国内滴答同步/完成 | modules/dida.py / dida_mcp.py | dida_tasks / dida_history；按稳定 ID 更新、快照去重，消失不推断删除；DPAPI 授权独立保存，无原项目运行依赖。 |
| 共享页面 | module_views/planner.py | RemindersPage / CalendarPage / CheckinsPage；使用服务方法，不直接写 SQL。 |

新测试 `test_shared_features.py`，动态气泡的真实本地 HTTP 验证在 `test_module_http.py`。真实国内只读联调已成功（29 条任务，仅读取，未打印正文或授权）；未发送真实 QQ 测试消息。第三方 Cookie 接口不是官方 OAuth 合同，变化或 401 时先区分凭据问题，不随意改已验证请求格式。

新增表仅追加，原聊天、角色、人格、LivingMemory、QQ 守护存储不迁移。回退代码时保留全部新增表和本地加密授权；额度/投递历史不能通过删库“修复”。未配置 QQ / 滴答时核心本地功能仍可使用。现有角色删除不删除这些共享模块数据。

2026-11-11 收尾：全量回归 135 tests / 63.545s / OK；中断恢复后仅复核新增共享功能，7 tests / 0.536s / OK。未新增业务范围、未制作 Claude 交接任务。国内滴答只读成功不等于远端写操作已开放；QQ 新共享渠道本轮未向真实联系人试发。


### 官方滴答增量（2026-11-11，覆盖上文只读阶段限制）
- 页面：`module_views/planner.py::CheckinsPage`，滴答/本地打卡双标签，搜索、清单、状态筛选，勾选后异步完成并刷新。
- 适配：`modules/dida_mcp.py` 固定官方地址与工具白名单；`modules/dida.py` 保存授权、任务与版本、完成提交凭据。新增表 `dida_official_meta` / `dida_completion_ops`，授权键 `dida_mcp_auth`。
- 测试：`tests/test_dida_official.py` 覆盖本地 HTTP JSON/SSE、任务隔离、循环版本、失败不重试、历史去重、UI 渲染不触发写入。真实账户已通过官方只读通道同步 28 条活动任务；没有完成任何真实任务。完成写入只在隔离测试服务中验证。
- 已完成列表为本地已同步历史，不拉取全部历史；未新增滴答习惯接口、远端创建/删除和后台自动轮询。仍使用“同步滴答清单”按钮获取其他客户端的变更。
- 口令不入 Git；回退保留新增表/加密授权/提交凭据，禁止通过清库重置未确认的完成操作。
- 本轮验证：全量 144 tests / 64.995s / OK（新增 9 项）；日志 `.cache/role-refactor-checkpoint/dida-official-final.log`。


### 提醒 UI / QQ 卡顿修复（2026-11-11）
- 保留 Claude 的专注金币显示（9f99eb3），本轮只改共享提醒页面及渠道。
- 页面入口 `module_views/planner.py::RemindersPage`；渠道/声音设置拆到 `module_views/reminder_settings.py`。网络相关入口在 `modules/reminder_delivery.py`，后续禁止从 UI 同步调用 diagnose/test_send，应使用 start_check 与 check_result 信号。
- 修复打开设置/点击检查/试发阻塞 UI、测试忽略未保存表单、空 token 被视为成功、失败无原因、投递记录刷新丢选中项，以及误称共享链路自动重试。定时与试发复用发送入口，最多两个定时发送并发；诊断与试发仅允许一个进行中。
- 新持久化表 `reminder_delivery_details`；`Planner.update` 编辑计划而保留已产生的投递历史。用户关闭设置不会使工作线程访问已销毁的控件。
- 新测试 `tests/test_reminder_channels.py`：真实 transport 对本地 HTTP 服务投递、定时去重/失败重试、UI 心跳、草稿配置、关闭窗口、空令牌、编辑历史。全量 151 tests / 92.055s / OK，日志 `.cache/role-refactor-checkpoint/reminder-channels-final.log`。
- 真实 QQ 只读诊断：接收者已配置、凭据存在、令牌有效；本轮未向真实 QQ 联系人试发。发送链路通过隔离本地 HTTP 验证，不把这个结果表述成真实用户已收到。无需 Claude 交接。


### 最新增量：工作 / 生活 / 职责 / 恢复
优先读 `modules/work.py`、`life.py`、`duties.py`、`duty_tools.py`、`recovery.py`；对应 UI 为 `module_views/life_work.py`。Focus/Hub 做结算和页面接入，Agent/capabilities/native_plugins 做按需权限；role_lifecycle 阻止删除仍任职的人格。`ui.py` 导航改为可滚动，页面共 11 个。
规则覆盖上文旧“所有专注均金币”：v2 工作积分与学习金币分开；运动走上报；家务同日同标题计时/打卡共用奖额。旧结算不迁移，旧在途计时保留 legacy。
测试索引：`test_work_service.py`、`test_life_flows.py`、`test_duties.py`、`test_life_work_views.py`、`test_recovery.py`。中断前全量 173 项通过；最终验证见本节后续结果与 `.cache/role-refactor-checkpoint/recovery-final.log`。
本轮单代理完成中断收尾及两项行为机制，没有启动新子代理；不读取真实私聊、不调用付费 LLM、不向真实 QQ 试发。

最终收尾验证：全量 **179 tests / 109.050s / OK**；自然回复/群聊保护上下文最后增量复测 **26 tests / 9.765s / OK**（`recovery-incremental.log`）。原生 Qt 联动测试通过，未额外进行截图扫描。真实模型自然表达与 QQ 到达仍须使用者环境体验，测试未花费模型额度或外发消息。

聊天加载优化：仅增量读 `storage.py::message_page/message_days/context_characters`、`ui.py::render/more_history`、`chat_history.py`；测试 `test_chat_history.py`。20 条是存储消息数，工具空回执不渲染；不影响 AI 完整上下文。历史按天且每页 20 条，不在主窗口无限追加。无数据库迁移。
聊天验证：全量 181 项检查中 179 项通过，2 项要求旧“无限追加历史”行为的断言随后更新；聊天跟随、分页与修订相关 18 项复测全部通过（29.609s）。日志 `chat-history-final.log` / `chat-history-recheck.log`。


2026-11-12 资料阅读增量：`modules/markdown_library.py` / `module_views/markdown_reader.py` / `settings.py::_duties_page`；书写规范在 `extensions/skills/markdown-writing/SKILL.md`，职责一次性绑定在 Duties 初始化中。顶部新增“资料”并移除独立“职责”（职责进入设置），保持原 11 页总数。无用户资料迁移。测试 `test_markdown_library.py` 覆盖读取边界/大小/UTF-8、正文搜索、目录链接、图片资源限制、Skill按需与换岗绑定、设置入口。仅以合成文档做一次原生布局预览，未读取 MasterData 正文。
资料阅读验证：全量 **184 tests / 76.663s / OK**；最后的目录启用状态与相对链接调整后专项 **3 tests / 0.265s / OK**。日志 `.cache/role-refactor-checkpoint/markdown-reader-final.log`；真实 MasterData 只设置路径，未读取或修改正文。

2026-11-12 文档编辑增量：`modules/document_changes.py`（修订日志、幂等交接、断点恢复），`modules/markdown_library.py::save`（用户保存），`files.py::write`（职责角色写入桥接），`module_views/document_revisions.py`（快照与差异），`markdown_reader.py::can_leave/save_document` + `modules/workspace.py`/`ui.py::closeEvent`（未保存保护）。职责动态提示在 duties.context，查询接口在 duty_tools。测试入口 `test_document_changes.py`：保存/无变化、Kia写入/拒绝、冲突/恢复、Qt后台保存响应、导航保存/放弃/取消。没有改动真实 MasterData、私聊或人格文件。

文档修订验证：全量 **189 tests / 75.204s / OK**，日志 `.cache/role-refactor-checkpoint/document-edit-final.log`。使用隔离测试资料验证内置文件工具与 Qt 交互，未调用真实 LLM、未读取或修改 MasterData 正文。

2026-11-12 自助打包：`Build Sunday Blue.bat` → `build.ps1` → `SundayBlue.spec`；普通修改不自动打包，由用户决定。`main.py --verify-package` / `package_check.py` 隔离启动完整页面、托盘隐藏/恢复及后台事件循环，不访问真实数据。`Start Sunday Blue Source.cmd` 明确启动最新源码，避免旧 EXE 优先导致误判修改失效。目录/跨机限制详见 `docs/PACKAGING.md`。全量回归 **189 tests / 77.819s / OK**；本机关闭到托盘已开启，修改前配置已备份（不提交 Git）。


### 2026-11-12 桌面优化收尾入口
- 后台/唤醒：`instance.py`、`tray.py`、`main.py`、`ui.py::closeEvent`。
- 工作/生活：`module_views/life_work.py`；计时/状态新职责分别在 `modules/life_timer.py` / `life_state.py`，原始事实与奖励仍由 `life.py`。`hub.navigate` 接入工作→专注导航。不得删除旧daily_life字段或改变已有activity_records账目。
- QQ周期：`life_state.report_cycle` + `reminder_delivery.send`，投递状态包含unknown，禁止把unknown批量重置pending。每日提醒依赖共享QQ配置及APP正在运行；休眠期间不发送，恢复后本周期可补发。
- 滴答Agent：`modules/dida_tools.py`、`dida_mcp.py`、`capabilities.py`、`agent.py`；官方工具契约已在真实端点只读校验，create/update为task对象，delete回执为deleted ID。旧handoff中Cookie格式仅历史参考，不可套到官方MCP上。
- 压缩：`context_budget.py` / `provider.py::count_tokens` / `agent.py::_compact_session` / `ui.py::request_compact`。上次usage不等于当前精确token量；禁止恢复字符除2作为真实统计。
- 记忆：`living_memory.py::startup/stop_ollama`、MemoryPanel、插件worker scope/reflect/status。当前Mia空图谱诊断为3轮待整理、阈值4，非已确认存储失败；不读私聊正文。隔离真实本地向量联调通过自动阈值4、user作用域、1条文档/2个原子/5个图节点、召回、跨角色隔离、重启与图谱API；模型摘要由本地fixture提供，不消耗真实LLM。
- 商店：`module_views/rewards.py`，图片约定 `assets/shop/README.md`。不改变金币/预算账本。
- 测试：`test_desktop_upgrade.py`、`test_core.py`、`test_life_work_views.py` 及原全量回归；记忆完整链路运行 `scripts/test_livingmemory_live.py`（默认不调用付费聊天API，复用已有Ollama且不接管）。禁止为验收删除/完成真实滴答任务或修改真实记忆。

最终验证：全量 **203 tests / 131.050s / OK**，日志 `.cache/role-refactor-checkpoint/desktop-upgrade-final.log`；真实 Ollama + 隔离记忆自动提取联调日志 `memory-auto-scope-final.log`。源码 `--verify-package` 验证11个页面、托盘与后台循环通过，未重新构建EXE。滴答真实验证仅限工具契约读取，QQ外发及滴答真实写操作未执行；对应代码使用本地隔离测试验证。测试产生的预览图片不作为本轮修改提交。未删除用户数据、人格或历史记录。

### 生活恢复站 UI 增量入口
- 页面：`module_views/life.py`；只读状态卡/肌群命中/趋势：`life_widgets.py`；通用表单：`module_forms.py`。`life_work.py`继续提供Work/Duties与LifePage兼容导出。不要重新把三个页面逻辑堆回同一文件。
- 美术：`art_assets.py`、`assets/ui/resources.json`；规则及ComfyUI说明在原 `docs/UI_DESIGN_SYSTEM.md`。没有正式图片，默认矢量可交互。
- 关系：`ui.py::open_relations`，导航移除relations；旧默认页面在workspace兼容转入聊天。业务服务及数据不变。
- 窗口：`window_geometry.py` + `ui.py::nativeEvent`，初始/最大化按屏幕工作区；不得恢复1440×900固定初始几何。
- 验证：`tests/test_life_cockpit.py`覆盖状态联动/无重复结算/肌群命中/数据不足/占位直接输入/关系入口/实际Windows初始及最大化边界。`scripts/preview_life_ui.py`只使用隔离合成记录，生成目标页面浅深色和记录区预览到.cache；不读取真实生活记录。

本轮最终验证：**208 tests / 85.220s / OK**，日志 `.cache/role-refactor-checkpoint/life-cockpit-final.log`。源码隔离启动验证10个页面、聊天关系入口、托盘可用与后台事件循环通过；原生Windows窗口初始及最大化工作区测试通过。目标页面浅色/深色、窄布局与上报/运动/正计时截图验证完成，图片只保存在.cache。未重新打包，未修改真实用户数据或奖励规则；保留Claude已验收的空值输入改动。

### 学习成长 / 契约 / 用眼状态入口
- 规则与数据说明：`docs/LEARNING_AND_STATE.md`；服务 `modules/learning.py` / `contracts.py` / `attention.py`，消息桥 `notices.py`。
- UI：`module_views/growth.py`（学习、契约、日程容器）、`attention_controls.py`；生活恢复站保留原布局增补参数和休息入口。旧提醒/日历/打卡页面类不重写。
- 编排：Hub五秒任务检查、学习自动循环绑定、rest_requested信号；workspace旧导航兼容。duty_tools只读摘要按现有职责授权。
- 测试：`tests/test_growth.py`覆盖掌握证据、错题重做、时长绑定/循环、旧金币去重、契约增量基线/签约规则/结算上限、QQ本机outbox、夜间持续使用、休息与体力隔离、睡眠去重、旧导航兼容。QQ实发未执行；共享投递仍由已有隔离HTTP测试覆盖。

本轮验证：全量 **221 tests / 89.806s / OK**（`.cache/role-refactor-checkpoint/growth-final.log`）；夜间时间格式归一化后专项 **13 tests / 3.873s / OK**（growth-recheck.log）。源码隔离启动检查9个主页、托盘与后台循环通过；成长/契约原生截图及状态参数滚动边界检查通过。未调用付费LLM、未向真实QQ试发、未改写用户事实或原金币账本。新功能核心链路可用，规则与识别局限见 LEARNING_AND_STATE；未重新构建EXE。

## 2026-11-13：数字输入、专注语境、日常状态与结算

| 需求 | 唯一实现入口 | 验证 |
|---|---|---|
| 数字与不可选单位、焦点全选 | `numeric_inputs.py`；现有表单使用别名复用 | `test_daily_experience.py`、原UI测试 |
| 专注当天短上下文 / 模型来源 | `modules/focus_dialogue.py` → `module_views/focus.py` | 同上、`test_shared_features.py` |
| 09点结转、22点提醒、阶段模式 | `modules/attention.py` / Hub / `life_timer.py` | 同上、`test_growth.py` |
| 私人记录与修订 | `modules/private_wellbeing.py` → `module_views/life.py` | 同上 |
| 日结算 / 周月年报告 / 异步评价 | `modules/reports.py` → `module_views/reports.py` | 同上；完整回归232项通过 |

使用/迁移边界见 [DAILY_EXPERIENCE.md](DAILY_EXPERIENCE.md)。新表均为增量创建，不重算旧账、不迁移或删除旧事实。
