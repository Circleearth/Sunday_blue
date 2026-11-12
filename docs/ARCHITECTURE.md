# Architecture / 扩展说明

2026-11-10 新增模块层与页面层，见 [模块索引](MODULE_INDEX.md)。该文是新增专注、金币、关系、群聊、双向近期记忆、主动交流和角色模型的优先阅读入口；不要为改一个页面重新扫描整套旧聊天实现。原角色增删本轮保留，不继续扩展。

专注已升级为番茄钟：`modules/focus.py` 管倒计时和原子结算，`focus_timers` 附属表兼容旧正计时；Hub 的独立一秒 timer 负责切页后继续检查。`focus_alarm.py` 只负责本地声音，`focus_preferences.py` 负责配置/音频导入，`module_views/focus_settings.py` 编辑草稿。页面不发币、不自行计算有效时长。音频失败不能撤销结算；休息阶段绝不产生专注事实或奖励。

## 分层

- `roles.py`：安装根内唯一角色注册；`data/roles.json` 存 ID、名称、描述、颜色与状态。`role_lifecycle.py` 负责依赖核验、导出、归档与可续做删除；`role_preferences.py` 只负责管理 UI。固定默认角色仅用于首次初始化。

- `storage.py`：应用路径、角色元数据、原子 JSON、Windows DPAPI、SQLite。每次数据库操作独立连接、事务、确定关闭；WAL 支持多会话线程。
- `provider.py`：统一内部消息（text / tool_use / tool_result），转换 Anthropic Messages 与 OpenAI Chat Completions。支持 JSON 和 SSE；必须收到结束标记才算完整。禁止重定向转发凭据；网络错误不记录密钥或服务端原始响应体。
- `files.py`：目录授权、路径检查、文本读取/搜索、差异生成、审阅后再次验证、冲突检测、旧字节备份、同目录临时文件 + 原子替换。文件锁串行化软件内写入。信任目录按角色配置自动确认，普通写目录审阅。提供创建、同卷移动、文件/目录删除；删除完整备份、目标清单前后核验，禁止删除授权根目录。
- `extensions.py`：声明式提示词插件、Skill 文本加载、MCP stdio 进程及 JSON-RPC。每个 Agent 独立连接，任务结束关闭服务。仅初始化/列工具/调用工具，不提供 sampling。
- `agent.py`：每会话 QThread。构建人格/记忆/扩展提示词 → 请求 → 保存模型输出 → 工具审阅/调用 → 保存回执 → 下一轮。最多 16 轮，避免无限工具循环。
- `ui.py`：frameless Qt Widgets 界面、会话选择、流式气泡、工具回执、上下文/记忆查看、差异审阅。线程信号传递 UI 更新，`threading.Event` 传回审阅结果。
- `settings.py`：左侧分类导航的 API、角色权限、插件、MCP、Skill、外观页。每次任务启动取深拷贝配置，保存设置不影响已经启动的任务。
- `design_system.py` / `theme.py`：统一语义颜色、间距、圆角、精选中文字体和 Qt 组件状态；自绘组件通过 tokens 取色。

## 数据模型

SQLite `sessions`：角色、标题、创建/修改时间、父会话、摘要、已摘要消息游标、最近 usage。
`messages`：全局自增 ID、会话、role、JSON content、时间。
`audit`：工具调用、写入元数据、备份路径、错误、压缩事件；不存 API Key。

分支复制原历史，并重新映射摘要游标。压缩只更新摘要和游标，不删除原始消息。人格源文件独立于会话。记忆按角色文件隔离，多会话同时提议记忆更新时使用旧内容一致性检查，发生竞争后要求重新读取。

发送失败时保留用户消息，通过“重试”重新请求；停止/错误产生的未完成流式片段不作为成功回复保存。工具回执一旦写入数据库，后续继续不会自动重放。异常退出后发现孤立 tool_use，则补记“结果未知”错误回执，要求模型先检查实际状态。

## 权限边界

目录授权由程序检查，不依赖人格自觉。外部文件工具不能修改软件自身及其他角色记忆。没有任意 shell 工具；删除文件/目录限已授权可写子路径，信任目录自动批准，否则审阅。模型工具名必须在本轮启用列表中。Skill 和声明式 JSON 插件不能直接扩大目录授权；Python 插件与 MCP 属于可信本机代码，具有当前用户权限。

MCP 是用户选择运行的本机程序，进程拥有操作系统用户权限；启动和调用审阅不等于操作系统沙箱。文件工具的重解析点检查、硬链接拒绝和写入前重新验证，不能提供对本机恶意并发进程的完整 race-free 防御。

## 后续扩展位置

1. 新 API 协议：在 provider 中添加 wire adapter，保持内部 transcript 格式，增加本地 HTTP 合约测试。
2. 新内置工具：加入 schemas 和 Agent dispatcher，工具是否读取/写入由宿主实现决定，不能让 prompt 自行放宽规则。
3. HTTP MCP/OAuth：增加独立 transport 与凭据生命周期，不把网络连接细节散落在 UI。
4. 完整 Skill package：需要资源读取授权、脚本能力边界、依赖打包与生命周期；当前仅文本加载。
5. 增量自动压缩：估算完整 system + tools + messages，并按模型准确计数策略决定阈值；当前手动压缩、保留原文。
6. 更丰富聊天展示：可引入本地 Markdown 渲染，但禁止自动加载模型生成的远程图片/任意 HTML 资源。
7. 代码执行：必须设计独立工作目录、可审阅命令、超时和系统隔离；当前版本明确未实现。

## 打包

PyInstaller onedir，Python/Qt/requests 放在 `_internal`；assets/personas/extensions/data 外置，定位以 EXE 所在目录为准。开发模式以 main.py 的项目根定位。构建输出在 build 内，再复制 EXE 与 `_internal` 到根。

不绑定旧项目的 Python 路径。LivingMemory 作为用户指定的例外，保留固定版本原版源码与少量 AstrBot 向量存储源码，来源哈希及许可证在其插件目录；不复制 AstrBot 用户配置或旧记忆。人格是已授权复制的项目内容；Qt/PySide6、Python、requests 等依赖保留各自许可证资料。


## 插件与 UI 生命周期（2026-11-04）

plugin_runtime 扫描 extensions/plugins/*/plugin.json，读取 _conf_schema.json 并加载 main.py；plugin_preferences 生成按角色参数表单。time-context 和 daypart-greetings 均已外置。旧模块只兼容导入。完整合同见 [PLUGIN_SPEC](../handoff/PLUGIN_SPEC.md)，定位见 [维护地图](../handoff/MAINTENANCE_MAP.md)。未实现 AstrBot Runtime 兼容。

时段事件仅在需要时进入当前模型请求，不写 messages；实际问候由正常模型回复保存。activity 记录最近用户发送时刻，默认 60 分钟连续聊天免寒暄；凌晨规则独立。失败/取消无正文释放预留。旧 events 保留只读显示和按需请求重放。

聊天同会话增量追加；长流式气泡复用为落库气泡，分段插回对应消息行，不清空整个布局。用户滚动位置决定跟随状态，rangeChanged 只在跟随时调度置底。Bubble 高度计算先取消旧高度约束，防止主题/resize/流式累计增高。chat_presentation 提供纯显示分段、按角色字体、失败提取；字体从字节载入，避免 Windows 文件占用。保存外观设置保留正在运行的分段计划。

停止撤回：worker 先取消，完成信号后主线程事务移除该用户输入及后续本轮消息，原内容保留 audit，输入与新草稿合并。已执行工具操作不能回滚；摘要涉及撤回边界时清空摘要并恢复完整历史上下文。用户主动关闭到托盘时进程和任务保持运行，托盘可重开；退出仍要先结束任务。默认关闭到托盘不启用。没有 Windows 服务、开机自启或休眠运行。

当前源码启动，不打包；用户实际数据与凭据不用于测试。

## LivingMemory / 人格与审阅（2026-11-06）

- `living_memory.py` 管理显式启动的独立 Ollama、角色进程和持久队列。端口 11435；状态检测不启动模型。
- `extensions/plugins/livingmemory/` 持有插件清单、适配器、固定上游和原版页面。每个角色一个子进程隔离上游全局状态；完整后台初始化、BM25/FAISS/图谱检索、记忆原子、衰减、整合使用上游实现。
- `plugin_runtime.turn_hooks` 是通用的 `before_turn / after_turn` 合同；Agent 在检索后注入只读背景，完整成功后入队。插件错误记审计并降级，不丢正常聊天。
- worker 用只绑定 127.0.0.1 的临时端口和随机进程令牌；网页通过 HttpOnly/SameSite cookie 访问，检查 Origin/Host。九角色独立 Qt WebEngine profile，不共享同主机 cookie。
- inbox 以 session/user-message 唯一键去重；整理成功后提交游标，故障保留待办。上游文档额外保存 sunday_job/sunday_committed 以处理跨库提交间隙。
- `personas.py` 与 `persona_preferences.py` 仅允许用户编辑四个人格字段，带并发冲突检查、完整前后快照及恢复。旧专业与平台流程移到 personas/_archive，不加载。
- `memory_editor.py` 用现有 FileTools 审阅备份机制编辑确认记忆；`change_review.py` 提供统一的左右对照及修改行提示。自动记忆与确认记忆不互相覆盖。

全量自动测试用隔离目录和本地 HTTP fixture。显式 `scripts/test_livingmemory_live.py --live-chat` 才使用当前 API 的少量真实调用，输入仍是合成测试文本，不读取用户会话。详见 [接入与维护](LIVINGMEMORY.md)。

共享日程、分类记录、月度兑换额度和滴答适配层已接入，详细目录/表边界见 [模块索引](MODULE_INDEX.md) 的共享功能增量。动态番茄钟气泡只用短暂上下文与受限后台请求，不经过长期记忆写入链路。


### 官方滴答任务同步与完成（2026-11-11）
`module_views/planner.py::CheckinsPage/SyncJob` → `modules/dida.py` → `modules/dida_mcp.py`。
官方 MCP 使用 API 口令 Bearer 授权，Streamable HTTP JSON/SSE；仅允许列清单、查询任务、获取单任务、完成任务及工具说明，未安装 CLI 或引入新依赖。
读取与写入均由 QThread 执行；UI 渲染不触发完成操作。完成前读取当前任务，核对稳定 ID、dueDate、etag；先写操作凭据再请求远端。网络结果不确定时保留 unconfirmed，不盲目重试。同版本操作只能提交一次，循环下一期使用新日期/版本。
`dida_mcp_auth` 使用 DPAPI；`dida_official_meta` 保存 projectId/etag/due/kind，`dida_completion_ops` 保存提交状态，原 `dida_tasks/history` 保存缓存与去重快照。新增表无破坏性迁移，回退代码保留数据及操作凭据。远端消失不推断完成或删除；已缓存未完成项不在活动查询中时按 ID 复核。
官方说明：[MCP](https://help.dida365.com/articles/7438132116019216384)、[CLI](https://help.dida365.com/articles/7464976698707017728)。旧 Cookie v2/v3 路径仅为历史配置只读回退，不再作为本页授权入口。


### 提醒页与 QQ 异步链路（2026-11-11）
- `module_views/planner.py::RemindersPage`：列表/投递记录双标签、筛选、编辑；`module_views/reminder_settings.py`：非模态 QQ/提示音设置。测试使用表单快照，不偷偷保存配置；关闭窗口不撤销已发起的网络请求。
- `modules/reminder_delivery.py`：诊断/试发用单个后台线程槽，定时 QQ 最多两个并发请求。`test_send(text,cfg)` 是实际投递与试发的同一入口，复用原插件 `_creds/_token/_qq_send`；不修改原守护进程。只有显式点击检查/试发才联网，连接诊断只验证令牌，不承诺接收者可达。
- 网络请求保持原 transport 的 20 秒令牌、30 秒发送超时。GUI 信号只负责展示；发送工作线程先持久化回执，再通知 UI。新表 `reminder_delivery_details` 保存尝试次数、时间和脱敏错误。异常不自动重发；进程中断留下 sending 时可人工核对后重试，外部发送不能保证 exactly-once。
- 编辑只修改未来计划，不覆盖既有 occurrence。原 QQ 插件任务继续只读；共享提醒不转存到原插件数据库，防止两套调度重复发消息。回退保留新增投递详情表，不能清空业务历史。


### 职责、真实生活与恢复（2026-11-11）
`modules/work.py` 管理两级任务与审计；`focus_task_links` 保存 run→task 与当时标题/进度，结算事务同时写活动、积分或金币、任务历史和事件。`focus_reward_policy` 为升级前在途计时保留 legacy 规则；新计时 v2，旧流水不改写。`work_points` 不参与商城余额。
`modules/life.py` 管理 exercise_records / daily_life / life_revisions / housework_records / housework_awards；补记和修改是事务，运动重算当天额度只追加奖励差额。体力/专注/视疲劳读取同一份实际记录，未知输入有明确提示，不启动模型测量。
`modules/duties.py` 固定七槽 duty_slots，替换只改 role_id；duty_changes 留审计，duty_handoffs 关联 organized_records。记录与交接同事务，完成分类不改原文及确认状态。`duty_tools.py` 每次调用复核职责权限，事实写入走用户确认，原文捕获可快速保存为 proposal。按需能力路由继承槽位插件/Skills；第三方 allowed_roles 与显式禁用保持有效。旧 Kia 整理插件在新版职责库存在时退场，代码与数据不删除。
`modules/recovery.py` 复用 module_settings 保存恢复截止、情绪有效期和意愿，module_events 保存工作日结算和延后复盘。共享投递与旧 QQ daemon 均在外发之前检查保护；reminder_priority 是独立紧急标记，不改原提醒表。Relations 在记录/消费负事件时复核保护，绝不补扣。Social 的自动发起/追问检查保护；主动请求的聊天仍正常，但带简短恢复上下文。旧 daemon 必须重启才加载新代码。
下班动态回复复用 FocusDialogue 的有限线程/调用预算与失败回退，用独立实例避免打断专注临时上下文。普通番茄钟结束不是下班，用户通过工作页明确结束工作日。
回退：保留所有新增表、音频、人格和用户数据，仅回退代码。不要倒灌数据库或删除奖励调整记录；正在计时先结束，避免旧代码不认识新奖励规则。

### 有界聊天显示
`Store.message_page` 按 session/id 索引倒序 LIMIT 21，返回 20 条与更多标志；`chat_history.py` 独立只读按 created 日期分组、按 id 游标翻页。主 render 增量淘汰旧消息关联控件，始终保持最近 20 条存储消息（单条回复分段仍为多个气泡）。`messages(context=True)` 不变；上下文长度估算改 SQL length 并按最大 id/count 缓存，避免分段动画反复解码整段聊天。历史窗口始终固定所选会话，当前输入与回复不受影响。


### Markdown 资料库与设置整合（2026-11-12）
`modules/markdown_library.py` 提供受所选根目录约束的读取、检索、收藏/最近记录，配置键 `markdown_library` 保存在 modules.sqlite3。`module_views/markdown_reader.py` 复用 Qt 原生 QFileSystemModel（延迟列目录）、QTextBrowser（Markdown）、后台搜索线程；只接受 UTF-8 md/markdown，阻止联接/链接越界，远端资源不会自动加载。点击外部 http(s) 文字链接才交给系统浏览器，图片限定所选库内受限大小的位图。没有引入浏览器引擎或大型依赖。
`Settings._duties_page` 嵌入现有 DutiesPage，优先复用主窗口 ModuleHub，独立设置窗口用仅含职责服务的轻量适配，不启动计时。职责操作仍直接落库，UI 明示即时保存边界。
`Duties` 只在 Markdown Skill 已安装且未迁移时，在同一事务中为 recorder/organizer 追加共享规范，保留其他扩展，写 `markdown_standard_installed` 标记。不修改用户人格、角色私有文件权限或原文文档。capabilities 为该 Skill 设置按需关键词默认值。

### Markdown 保存与修订交接（2026-11-12）
`MarkdownLibrary.save` 与 `FileTools.write` 复用 WRITE_LOCK。手动保存二次核验原始字节，保留 BOM/CRLF、备份并原子替换；AI 仍走已有权限/信任/确认流程，仅已指派 recorder/organizer 在所选资料库写 md/markdown 时接入。data/personas/extensions/.git 排除共享修订。

`modules/document_changes.py` 在 modules.sqlite3 的 document_changes 保存完整前后快照与哈希，prepare 在替换前落盘；finish 在单一 SQLite 事务中生成 organized_records proposal、duty_handoffs、document.changed，并以修订 ID 幂等。磁盘文件与 SQLite 并非同一事务：异常时保留 prepared；启动/保存/查看修订时在写锁内核对当前哈希，等于 after 则补交接、等于 before 标记未写入，其他冲突保留待核对，不盲目回滚。快照与 data/backups 不自动清理。

页面通过后台线程保存、计算差异及生成交接，Qt 信号回到主线程；编辑时只维护脏标记。workspace 导航及主窗口关闭调用 can_leave，异步保存成功才继续原动作；失败保留草稿。修订弹窗 document_revisions.py 展示完整前后和有界差异（大文档只显示快照，避免昂贵 diff）。双方 duty_action 支持 handoffs/file_revision；人格动态上下文只补最近三条待处理标题，不灌入全文，不自动认定用户文档中的推断为事实。新增记录属于共享资料审计，不是私聊或长期记忆。

### 可重复构建（2026-11-12）
Build Sunday Blue.bat → build.ps1 → SundayBlue.spec，SPECPATH 为 spec 所在目录，collect_submodules(sunday_blue) 覆盖模块化的动态导入。one-directory + console=False，保持外部用户数据与插件。main.py --verify-package 进入 package_check.py 隔离离线验证，不走真实 root 初始化；普通启动流程不变。构建验证通过后才替换根目录 EXE/_internal，旧版本保留在 build/previous。源码与 EXE 都复用 tray.py，无新增后台服务。用户决定打包时机；日常任务不默认构建。迁移限制与目录布局见 PACKAGING.md。
