# Architecture / 扩展说明

## 分层

- `storage.py`：应用路径、角色元数据、原子 JSON、Windows DPAPI、SQLite。每次数据库操作独立连接、事务、确定关闭；WAL 支持多会话线程。
- `provider.py`：统一内部消息（text / tool_use / tool_result），转换 Anthropic Messages 与 OpenAI Chat Completions。支持 JSON 和 SSE；必须收到结束标记才算完整。禁止重定向转发凭据；网络错误不记录密钥或服务端原始响应体。
- `files.py`：目录授权、路径检查、文本读取/搜索、差异生成、审阅后再次验证、冲突检测、旧字节备份、同目录临时文件 + 原子替换。文件锁串行化软件内写入。另提供文件夹级工具：`create_directory`（建目录，含中间层）、`delete_directory`（递归删除，审阅时逐条列出将删清单，最多 50 项 + 总数，删除前 re-check `no_links` 与仍为目录）、`move`（同卷 `os.rename`，目标须在可写目录内、不得位于源内部、已存在则拒绝不覆盖）。
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

目录授权由程序检查，不依赖人格自觉。外部文件工具不能修改软件自身及其他角色记忆。没有任意 shell 工具；删除能力仅限已授权目录内的文件夹递归删除，必须经审阅并列出将删清单。模型工具名必须在本轮启用列表中。Skill 和插件不能直接扩大目录授权。

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


## 2026-11-03 维护导航更新

UI 组件实现已移至 `sunday_blue/ui_components.py`，主窗口协调仍在 ui.py。时间注入在 time_context.py，由 Agent 的 system_prompt 调用；不写 messages。插件合同见 [PLUGIN_SPEC](../handoff/PLUGIN_SPEC.md)，职责定位见 [维护地图](../handoff/MAINTENANCE_MAP.md)。当前不打包；AstrBot 桥接属于评估方案，尚未实现。


聊天展示更新：Bubble 已改为无内滚动的 QLabel；短消息分段/延时只影响展示，不改变 messages 内容。chat_presentation.py 负责纯显示策略，chat_preferences.py 提供设置控件；ui.py 管线程信号和非阻塞分段计时。主题更新现有组件，避免重建历史后跳动。

宿主插件更新：native_plugins 显式注册时间上下文与时段寒暄，Settings 按角色配置。Greetings 独立 SQLite 存首次状态及本地事件，UI 发送路径触发并显示，不注入模型 history/system，主聊天数据库 schema 不变。

时段寒暄 v2 更新：触发入口已从 UI.send 移至 Agent._run，本地规则生成短暂控制信息，由同一次 LLM 回复表达并正常落库；不再添加本地固定气泡。旧 events 保留并按当前消息范围重放至请求/压缩历史，详细合同以 PLUGIN_SPEC 第7节为准。
