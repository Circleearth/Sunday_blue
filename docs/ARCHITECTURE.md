# Architecture / 扩展说明

## 分层

- `storage.py`：应用路径、角色元数据、原子 JSON、Windows DPAPI、SQLite。每次数据库操作独立连接、事务、确定关闭；WAL 支持多会话线程。
- `provider.py`：统一内部消息（text / tool_use / tool_result），转换 Anthropic Messages 与 OpenAI Chat Completions。支持 JSON 和 SSE；必须收到结束标记才算完整。禁止重定向转发凭据；网络错误不记录密钥或服务端原始响应体。
- `files.py`：目录授权、路径检查、文本读取/搜索、差异生成、审阅后再次验证、冲突检测、旧字节备份、同目录临时文件 + 原子替换。文件锁串行化软件内写入。信任目录按角色配置自动确认，普通写目录审阅。提供创建、同卷移动、文件/目录删除；删除完整备份、目标清单前后核验，禁止删除授权根目录。
- `extensions.py`：声明式提示词插件、Skill 文本加载、MCP stdio 进程及 JSON-RPC。每个 Agent 独立连接，任务结束关闭服务。仅初始化/列工具/调用工具，不提供 sampling。
- `agent.py`：每会话 QThread。构建人格/记忆/扩展提示词 → 请求 → 保存模型输出 → 工具审阅/调用 → 保存回执 → 下一轮。最多 16 轮，避免无限工具循环。
- `ui.py`：frameless Qt Widgets 界面、会话选择、流式气泡、工具回执、上下文/记忆查看、差异审阅。线程信号传递 UI 更新，`threading.Event` 传回审阅结果。
- `settings.py`：API、角色权限、插件、MCP、Skill、素材页。每次任务启动取深拷贝配置，保存设置不影响已经启动的任务。

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

不绑定旧项目的 Python 路径。不复制第三方已有项目源码。人格是已授权复制的项目内容；Qt/PySide6、Python、requests 等第三方库使用各自许可证，随依赖包保留许可证资料。公开分发前应审查对应许可证义务。


## 插件与 UI 生命周期（2026-11-04）

plugin_runtime 扫描 extensions/plugins/*/plugin.json，读取 _conf_schema.json 并加载 main.py；plugin_preferences 生成按角色参数表单。time-context 和 daypart-greetings 均已外置。旧模块只兼容导入。完整合同见 [PLUGIN_SPEC](../handoff/PLUGIN_SPEC.md)，定位见 [维护地图](../handoff/MAINTENANCE_MAP.md)。未实现 AstrBot Runtime 兼容。

时段事件仅在需要时进入当前模型请求，不写 messages；实际问候由正常模型回复保存。activity 记录最近用户发送时刻，默认 60 分钟连续聊天免寒暄；凌晨规则独立。失败/取消无正文释放预留。旧 events 保留只读显示和按需请求重放。

聊天同会话增量追加；长流式气泡复用为落库气泡，分段插回对应消息行，不清空整个布局。用户滚动位置决定跟随状态，rangeChanged 只在跟随时调度置底。Bubble 高度计算先取消旧高度约束，防止主题/resize/流式累计增高。chat_presentation 提供纯显示分段、字体、失败提取；字体从字节载入，避免 Windows 文件占用。

停止撤回：worker 先取消，完成信号后主线程事务移除该用户输入及后续本轮消息，原内容保留 audit，输入与新草稿合并。已执行工具操作不能回滚；摘要涉及撤回边界时清空摘要并恢复完整历史上下文。用户主动关闭到托盘时进程和任务保持运行，托盘可重开；退出仍要先结束任务。默认关闭到托盘不启用。没有 Windows 服务、开机自启或休眠运行。

当前源码启动，不打包；用户实际数据与凭据不用于测试。
