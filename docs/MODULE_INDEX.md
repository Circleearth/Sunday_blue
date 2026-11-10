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
