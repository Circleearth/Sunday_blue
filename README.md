# Sunday Blue

独立的 Windows 多角色 AI 桌面软件。保留 Great Blue 的七个人格，另有 TickTick、Mubu 两个工具角色。以 Python + PySide6 实现；聊天直接请求你配置的 API。

## 启动与首次配置

1. 双击本目录 **SundayBlue.exe**，或 **Start Sunday Blue.cmd**。
2. 右上角 **设置 → API 连接**：填写协议、请求地址、API Key、模型 ID。
3. 如果你的 cc-switch 中转站支持 Anthropic Messages，选 **Anthropic Messages**；鉴权按服务商要求选 `x-api-key` 或 `Bearer`。如果服务商提供 OpenAI 兼容接口，选 **OpenAI 兼容 Chat Completions**。
4. 点击 **测试连接**，成功后 **保存设置**。测试会发送一次短请求，产生少量 API 用量。
5. 点击最右侧角色头像开始聊天。Enter 发送，Shift + Enter 换行。

**不需要额外声明“调用插件”或“使用 Skill”。** 此软件不调用 Claude Code / Codex CLI，也不继承 Claude Desktop 登录状态。它使用你填写的 API 配置；可手动填入与 cc-switch 相同的配置，不会读取或修改 cc-switch、Claude 的配置。

模型 ID 不预填，避免假定你的中转站支持某个模型。地址支持根地址、`/v1` 地址或完整 `/v1/messages`、`/v1/chat/completions` 端点。例如：

| 协议 | 填入地址 | 最终请求 |
|---|---|---|
| Anthropic | `https://your-relay.example` | `https://your-relay.example/v1/messages` |
| Anthropic | `https://your-relay.example/v1` | 同上 |
| OpenAI 兼容 | `https://your-relay.example/v1` | `https://your-relay.example/v1/chat/completions` |

API Key 使用当前 Windows 账户的 DPAPI 加密，保存在 `data/settings.json`。没有密钥的本地代理也可使用。网络证书验证保持开启。程序不自动重试外部操作。

## 界面与会话

- 左侧：当前角色的历史会话、新对话、重命名、Markdown 导出。
- 中间：聊天气泡、流式输出、可展开的工具调用与回执；文字与代码可直接选中复制。
- 右侧：角色立绘、上下文用量、持久记忆入口。
- 最右侧：九个角色头像，滚轮可查看下方角色。点击立即切换；发送中的任务在后台继续。
- 顶部边框：拖动移动；双击最大化/还原；右上角最小化/最大化/关闭；右下角可拖拽调整大小。

每个会话有独立历史。同角色会话共享 **该角色自己的** 持久记忆，不共享其他角色的记忆。不同角色可同时请求模型；切换不会重建人格。未发送草稿在当前软件进程中按会话保留，退出时草稿不持久保存。重开后恢复上次角色及已选择的会话。

**分支** 复制当前完整会话和压缩摘要，原会话不受影响。当前会话正在生成时，需要等待或停止后分支。

**压缩** 会真正请求模型生成历史摘要，后续请求使用摘要和新消息，原始消息仍留在数据库。摘要失败或被截断时不替换上下文。建议在接近容量之前压缩；若已经超过服务商的请求限制，压缩请求也可能失败。压缩会产生 API 用量，不代表模型拥有无限精确记忆。

**上下文** 可查看会话 ID、父会话、摘要、系统提示预览和最近一次 API 用量。容量是设置中的手动值，必须与你选择的模型一致；有 usage 时显示最近一次 API 报告的输入与输出合计，无 usage 时仅估算历史字符，不包含完整系统提示和工具 schema，不冒充精确实时 token 数。

停止为协作取消：网络读取最长等待约 60 秒，已执行的写入或外部操作不会回滚。软件关闭前会要求结束正在运行的任务。异常退出后，缺失工具回执的会话标注“结果未知”，不会自动重放操作。

## 替换头像与立绘

素材文件夹名是 **assets**。所有角色目前使用透明空白 PNG，你可以直接覆盖文件。

| 内容 | 文件位置 | 推荐尺寸 |
|---|---|---|
| 头像 | `assets/roles/<角色 ID>/avatar.png` | **512 × 512** |
| 立绘 | `assets/roles/<角色 ID>/portrait.png` | **1200 × 1800** |
| 软件图标 | `assets/app.ico` | 包含 16–256 px 多尺寸 |

角色 ID：`rui`、`red`、`ewa`、`luna`、`loluns`、`kia`、`mia`、`ticktick`、`mubu`。

推荐 PNG 透明背景、人物居中。立绘按比例完整缩放，不强行裁剪。头像为正方形。替换图片后点击 **刷新素材**，不用改代码或重新打包。EXE 自身图标更换需要重新构建。

## 角色文件权限与编辑

**设置 → 角色权限**：选角色，再添加 **只读目录** 或 **可写目录**。初始权限为空。可写目录同时允许读取。权限针对所选目录及其子目录；每个角色单独配置。

可让角色：列出文件、读取 UTF-8 文本、搜索文本、新建文件、精确替换文件内容。操作仅接受已授权目录内的绝对路径。单文本文件最大 1 MiB；搜索最多 1500 个文件、100 个命中，跳过常见依赖目录。

每次写入都会弹出 **差异审阅**。确认后才保存，旧内容写入 `data/backups`，操作元数据写入数据库 audit 表。若你在确认前修改了文件，本次 AI 写入将失败并要求重新读取，避免覆盖新改动。拒绝确认不会写入。

软件自身目录、未授权目录、符号链接、Windows 联接点、硬链接、UNC 路径、设备路径、NTFS 备用流不允许通过内置文件工具访问。此机制是应用权限检查，不是防御本机恶意进程并发攻击的操作系统沙箱。

当前没有 shell、终端执行、删除文件、运行测试命令或通用二进制文件编辑功能。它已能完成常见的文本/代码文件阅读和修改；并不声称覆盖 Claude Code / Codex 的全部开发环境能力。

## 记忆、人格、旧资料

七个人格文件已复制到 `personas/<角色 ID>`，运行时加载 identity、personality、voice、expertise、relationships。为保留来源，旧 rules / responsibilities 也保存在此，但其中旧平台专用流程不注入新宿主。新宿主规则由 `sunday_blue/agent.py` 统一提供。

角色的持久记忆在 `data/memory/<角色 ID>/long_term.md`。模型可通过 memory 工具提出更新，仍需你审阅确认。它不会把所有聊天自动当成事实。没有导入旧聊天记录或旧数据库，也没有扫描或迁移 RedOS 的内容。

## 插件

**设置 → 插件** 提供文件工作台、持久记忆、MCP 桥三个开关，以及按角色启用的提示词插件。

导入 JSON 示例：

```json
{
  "id": "daily-planning",
  "name": "每日计划",
  "prompt": "整理每日计划时，先确认可用时间，再列出三项优先事项。"
}
```

导入后复制到 `extensions/plugins`，勾选角色才加载。该格式是 Sunday Blue 的声明式提示词插件，**不是** Claude Code 插件包的直接兼容层，不执行任意插件代码。

## Skills

**设置 → Skills**：选择角色，导入包含 `SKILL.md` 的文件夹，再勾选启用。文件夹名使用英文字母、数字、短横线或下划线。程序只复制并加载 `SKILL.md`（最大 64 KiB），不自动执行 scripts，不自动读取 references；需要附件或 CLI 的 Skill 必须先改造成此宿主支持的流程。

已启用的 Skill 会加入下一次请求的系统提示，不需要每次手动声明。导入文件会立即复制到本软件；取消设置只取消启用选项，不撤销已导入的文件。

## MCP

先在 **插件** 页启用 MCP 桥，再在 **MCP** 页填写配置：

```json
[
  {
    "name": "my-service",
    "command": "C:/runtime/node.exe",
    "args": ["D:/my-mcp/server.js"],
    "roles": ["rui", "mia"],
    "enabled": true
  }
]
```

支持本地 **stdio JSON-RPC**，初始化、工具列表分页和工具调用。可选 `cwd`、`env`。需要可执行程序路径；不要把整条 shell 命令塞进 command。Windows 的 .cmd 包装器需要你明确配置 `cmd.exe` 及参数，程序不会隐式启用 shell。

每轮会话发送前，可用服务由角色授权筛选；启动外部程序和每次 MCP 工具调用都弹出确认。**MCP 进程拥有当前 Windows 用户权限，不受内置文件工具的目录规则限制。** 只接入自己信任的服务。服务返回错误/超时不伪造成功，超时后先核实实际结果。

当前不支持远程 HTTP MCP、OAuth、MCP resources/prompts/sampling，也未预装 TickTick / 幕布真实连接。MCP `env` 配置以明文保存，优先让服务自行读取凭据。

用户自行配置的外部 MCP 运行时/脚本是可选外部依赖；若你需要迁移或删除其所在文件夹，也应把这些运行时和脚本移入 Sunday_Blue 并更新配置。

## 目录与独立性

```text
Sunday_Blue/
├─ SundayBlue.exe            双击运行
├─ _internal/                打包的 Python、Qt、网络库，必须保留
├─ assets/                   可替换图像
├─ personas/                 人格文件的独立副本
├─ extensions/               已导入的 Skills 与提示词插件
├─ data/                     配置、SQLite 会话库、角色记忆、文件备份
├─ sunday_blue/              Python 源码
├─ tests/                    独立测试
├─ docs/                     架构、测试记录、界面预览
├─ main.py                   源码入口
├─ build.ps1                 打包脚本
└─ README.md
```

**默认软件不依赖 Great_blue、RedOS、Sunday 或其他旧项目。** 保留整个 Sunday_Blue 目录即可运行；只复制 EXE 不够。删除旧目录不会影响已复制的人格和本软件数据。你后来授权的外部工作目录或配置的 MCP 外部程序仍需自行保留。

备份：关闭软件，复制整个目录。若仅备份用户内容，至少保存 data、personas、assets、extensions。换电脑或 Windows 账户后需重新输入 API Key。源码改动后要重新构建 EXE；仅改图像、人格、配置不需要构建。

## 共同交接

本目录由 **Claude** 与 **Codex** 两个开发方共同维护，交接记录都在 `handoff/` 文件夹里，分工如下（详细规则写在 `handoff/HANDOFF.md`）：

- `handoff/claude-to-codex.md` — **Claude 做的改动，Codex 请读取**；
- `handoff/codex-to-claude.md` — **Codex 做的改动，Claude 请读取**；
- `handoff/master-notes.md` — 主人的直接指令，**双方都读**，优先级最高；
- 改动前请先读 `AGENTS.md`；本目录已建立 git 仓库，重要改动应提交 git 以便回退。

**归档约定**：谁读完对方写的全部记录，就把那份文件整体移进 `handoff/archive/`，文件名注明日期和谁做的、谁归档的（如 `2026-11-05_claude-by-codex.md`），然后给对方留一个空文件重新开始。归档 = "已读完"的信号，archive 里的记录不再改动。

## 开发与验证

```powershell
python -m pip install -r requirements-build.txt
python main.py
python -m unittest discover -s tests -v
.\build.ps1 -Python python
```

架构见 `docs/ARCHITECTURE.md`，本轮测试结果见 `docs/test-results.txt`。测试用本机 HTTP 假服务和本机 MCP 假服务验证完整请求、工具回执、写入审阅与界面操作；未使用你的真实 API Key，不能据此声称所有中转站已经联调成功。填入实际配置后使用“测试连接”完成实际验证。

协议参考：[Anthropic 流式消息](https://platform.claude.com/docs/en/build-with-claude/streaming)、[Anthropic 工具调用](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)、[MCP stdio](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)、[OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat)、[Qt for Python](https://doc.qt.io/qtforpython-6/gettingstarted.html)。
