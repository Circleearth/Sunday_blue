# qq-reminders 插件说明

聊天创建单次 / 每日循环提醒，由无窗口后台守护进程到点直接经 QQ 机器人 OpenAPI
主动私聊发给主人。**不依赖任何网关进程**（网关只服务于角色双向聊天，提醒
不需要它）；凭据运行时读取 `%USERPROFILE%\.dsh\profiles\<profile>\cordis.patch.yml`，
不另存。

## 使用

1. 跟任意角色说"晚上 22:30 提醒我睡觉" / "每天 21:00 提醒我整理清单"。
   角色用 `add_reminder` 工具创建（时间模糊时角色必须反问具体时间，不猜）。
2. 到点守护进程发送，消息带角色名前缀，如「Luna：主人要去睡觉了哦」。
   可选 LLM 润色（默认开，每日 10 条上限，走宿主 settings.json 的 API）。
3. 断网时段（通勤等）到点的提醒**挂起不丢**，联网后自动补发；
   连续 5 次发不出去才放弃并写日志。

## 管理（设置 → 插件 → 选角色 → qq-reminders → 设置）

对话框顶部控制面板（参数上方）：

| 按钮 | 作用 |
|---|---|
| 重启 | 停掉本插件守护进程 + 看门狗任务，再重新拉起并注册（只动本插件组件） |
| 停止 | 停掉守护进程 + 删看门狗任务；提醒历史保留 |
| 试发一条 | 直接发一条试发消息到你的 QQ，验证链路（需 7890 代理/网络可用） |
| 检查 | 立即刷新下方三行状态 |

三行状态：守护进程（PID）/ 看门狗计划任务 / 挂起中待发的提醒数。

## 组成

- `main.py` — agent 工具（add/list/remove_reminder）+ `settings_extra` 控制面板
- `daemon/run.py` — 无窗口守护（pythonw），15 秒轮询，到期即发
- `daemon_ctl.py` — 检查/安装/停止/重启/试发（控制面板与两个 bat 共用）
- `install_task.bat` / `stop_task.bat` — 命令行等价入口
- 状态：`data/plugins/qq-reminders/state.sqlite3`（提醒，按角色隔离）
- 日志：`data/plugins/qq-reminders/daemon.log`
- 看门狗：Windows 计划任务 `SundayBlue-QQ-Reminders`（每 30 分钟自检，
  守护被杀自动补；pid 锁去重，重复触发零成本）

## 注意

- 给角色启用完整创建规范：设置 → Skills 页勾选 `qq-reminders`（不勾也能建
  提醒，但缺"模糊时间反问/每天=循环"等判断规则）。
- 代理：LLM 润色与 QQ 接口出网走 `http_proxy`（默认 7890）；直连通可留空。
- 本插件已在本机正常运行，Codex 除非恶性 bug 勿改（见 master-notes 2026-11-06）。
