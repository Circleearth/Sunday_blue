# Claude → Codex：Claude 做的改动，Codex 请读取

> 本文件只由 **Claude** 追加记录，由 **Codex 阅读**。
> Codex 读完本文件全部记录后：把本文件内容整体移入 `handoff/archive/`，命名为
> `YYYY-MM-DD_claude-by-codex.md`（当天日期 + 谁做的 + 谁归档），再新建一个空的本文件（保留头部说明）。
> 详见 `handoff/HANDOFF.md` 的"归档规则"。

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
