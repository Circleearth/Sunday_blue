# Claude → Codex：Claude 做的改动，Codex 请读取

> 本文件只由 **Claude** 追加记录，由 **Codex 阅读**。
> Codex 读完本文件全部记录后：把本文件内容整体移入 `handoff/archive/`，命名为
> `YYYY-MM-DD_claude-by-codex.md`（当天日期 + 谁做的 + 谁归档），再新建一个空的本文件（保留头部说明）。
> 详见 `handoff/HANDOFF.md` 的“归档规则”。

---

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

