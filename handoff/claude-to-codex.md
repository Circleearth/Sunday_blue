# Claude → Codex：Claude 做的改动，Codex 请读取

> 本文件只由 **Claude** 追加记录，由 **Codex 阅读**。
> Codex 读完本文件全部记录后：把本文件内容整体移入 `handoff/archive/`，命名为
> `YYYY-MM-DD_claude-by-codex.md`（当天日期 + 谁做的 + 谁归档），再新建一个空的本文件（保留头部说明）。
> 详见 `handoff/HANDOFF.md` 的"归档规则"。

---

## 2026-11-06 · QQ 提醒插件落地为"正常运行"版（Claude 做，主人指令：写清说明，正常运行的插件，Codex 除非恶性 bug 否则勿改）

**状态：插件已在本机实际运行并端到端验证通过**（守护进程 pythonw 无窗口常驻 + 看门狗计划任务
`SundayBlue-QQ-Reminders` 每 30 分钟自检拉起 + 「试发一条」真实发到主人 QQ 成功）。
**请 Codex 保持不动**（避免混乱）：除发现恶性 bug（守护崩、提醒全丢、误杀进程）外不要改本插件
`extensions/plugins/qq-reminders/` 与 `extensions/skills/qq-reminders/`，以及宿主
`settings.py` / `plugin_preferences.py` / `plugin_runtime.py` / `agent.py` 里对应 3b 钩子的行。

**相对 11-05 那条的演进（本插件已自包含，不再依赖 Rui 网关）**：
- **拆掉"网关在线才发"闸门**：守护进程到点**直接**调 QQ Bot OpenAPI 主动私聊（`daemon/run.py`
  删除 `_gateway_alive()` 判断；`_deliver` 不再因网关不在线而挂起）。凭据仍是运行时读
  `%USERPROFILE%\.dsh\profiles\<profile>\cordis.patch.yml`，不另存。11-05 条目里"QQ 网关当前没跑
  会一直挂起"的风险**已消除**——现在没有网关也能发。
- **语义**：单次=到点发一次；每日循环=每天固定点都发；断网时段挂起、联网后自动补发（保留）。
- **控制面板进"设置"对话框**：宿主新增可选钩子 `settings_extra(root)`（PLUGIN_SPEC 3b 由
  `status_widget` 改名/挪位置），嵌在 `PluginPreferences` 对话框**参数表单上方**。面板含 3 行状态
  （守护进程 / 看门狗任务 / 挂起中提醒）+ 4 按钮（重启 / 停止 / 试发一条 / 检查），后台 QThread 执行不卡窗。
  宿主的插件页已还原为"每插件一行 + 设置按钮"，不再有独立状态块。
- **UI 清理**：`_conf_schema.json` 里纯技术/自动复用型字段（`llm_base_url`、`llm_model`、
  `llm_key_override`、`test_send_url`）标 `invisible` 不再显示，仅保留 8 个主人真正要改的。
- **修两个小 bug**：① 试发/重启/停止结束（含失败）后按钮一直灰显 → 完成回调里统一恢复；
  ② `send_test` 经 7890 代理偶发 SSL EOF → 加一次自动重试 + 失败给"代理/网络不通"人话提示。

**验证**：全量 69 tests OK（`tests/test_qq_reminders.py` 6 条不变）；offscreen 构建设置面板通过；
本机 `daemon_ctl.restart()` 后新守护 PID 在位、看门狗任务 `task_installed: True`；`send_test` 实发成功。

**留给主人**（非 Codex）：插件页 Skills 标签里给需要的角色勾上 `qq-reminders` 技能，角色才带完整
创建规范（模糊时间反问、每天=循环等）；不勾也能建（走插件自带简短提示），只是缺判断规则细节。

---

## 2026-11-05 · QQ 定时提醒插件（Claude 做，主人指定：达成目的的最轻量级插件）

**目标**（主人）：和任意角色聊天即可创建定时/循环提醒，到点由 QQ 机器人私聊送达；
无时间时角色必须反问；循环=每天固定点；输出=固定文案（可选 LLM 润色）；
断网时段（上下班通勤）提醒不丢；看门狗保每日运行；后台耗用微乎其微、不显示命令行窗口。

**新增文件**（都在 `extensions/plugins/qq-reminders/` 与 `extensions/skills/qq-reminders/`）：
- `plugin.json` + `main.py`：agent 侧工具 `add_reminder/list_reminders/remove_reminder`
  （经 `sunday_blue/agent.py` 新增的插件工具分发：`plugin_<pid>_<tool>` 命名，宿主最小改动 3 处）；
  状态存 `data/plugins/qq-reminders/state.sqlite3`（rem 表，按角色隔离）。
  `main.py` 不再重复存 schema，唯一权威在 `_conf_schema.json`。
- `daemon/run.py`：**无窗口守护进程**（pythonw 跑，`install_task.bat` 注册任务计划程序
  每小时拉起 + pid 锁单实例，Rui 侧 vbs 模式）。15 秒轮询到期提醒；
  LLM 润色走**宿主 settings.json 的现有 API**（主人指定复用现有 Agnes key，不经 DSH），
  默认关、每日上限 10 条（poll_state 表计数）；QQ 发送沿用 Rui 的 DSH qqbot 凭据
  （`%USERPROFILE%\.dsh\profiles\qqbot\cordis.patch.yml`，不另存凭据）；
  网关不在线（dsh 无 ESTABLISHED 连接，判活逻辑同 rui-watchdog.ps1）→ 提醒挂起重试，
  超过 `delivery_max_retries`（5）放弃并写 `daemon.log`。
  `test_send_url` 参数可指向本地端点做不发真实 QQ 的验证。
- `SKILL.md`：角色操作规范（模糊时间必须反问；"每天/循环"→daily；告知下次触发与取消方式）。

**宿主最小改动**：`agent.py`（discover/load/dispatch 三处）、`plugin_runtime.py`
（1 行：schema 字段对象化兼容——Codex 8fcb8b7 里 schema 已改字段对象，参数读取器
需 `spec.get('default')`，我修了这处）。

**验证**：全量 69 tests OK；`tests/test_qq_reminders.py` 6 条新测试覆盖发现/默认启用、
增删查、缺时间拒绝、agent 分发、守护进程经 test_send_url 真实 POST、daily 续期不置 done。
真实 LLM 润色已用宿主 key（Agnes）实测通（经 7890 代理），返回正常中文。

**留给主人 / 剩余风险**：
1. **QQ 网关当前没在跑**（无 dsh node 进程）——守护进程装好后提醒会一直"挂起"
   到网关恢复；需要主人用 Rui 的 restart.bat 或手动启动 dsh qqbot。
2. `install_task.bat` **尚未执行**（要动 Windows 计划任务，等主人点头再装）。
3. 通勤断网：提醒补发而非放弃（挂起重试 5 次上限内）；真正长时间断网会超上限被放弃，
   属"没法处理只能放弃"的情况，已在 SKILL.md 如实告知角色口径。
