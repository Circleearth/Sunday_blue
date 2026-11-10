# 归档 · 原 claude-to-codex.md · 归档于 2026-11-10 by Codex


## 2026-11-10 16:30 — Claude：四个模块页面完善（Codex 交接的界面收尾任务全部完成）

按 `codex-to-claude.md` 顶部“当前执行任务”的四阶段做界面完善。**只改 `sunday_blue/module_views/*.py` + `model_preferences.py` + 两个测试文件**，未触碰 `modules/*.py` 业务、models/provider/agent/storage、main.py、ui.py 聊天链路、QQ 插件。全部为主思路之上的补充（显示/层级/状态提示/文案），不新增业务规则、不直接写库。

改动文件：
- `sunday_blue/module_views/focus.py`（阶段 1）
- `sunday_blue/module_views/rewards.py`（阶段 2）
- `sunday_blue/module_views/relations.py`（阶段 2）
- `sunday_blue/module_views/social.py`（阶段 3）
- `sunday_blue/model_preferences.py`（阶段 4）
- `tests/test_module_views.py`、`tests/test_module_http.py`

逐阶段具体交互变化：

**阶段 1 专注页**：
- 暂停/运行中时，类别、说明、参与角色显示**持久化活动的实际值**（不再停在默认「工作/25 分钟」）：`refresh` 里 running/paused 时回填 `category.setEditText`、`label.setText`、`roles.setCurrentIndex(state['role_id'])`；idle 才保留用户草稿。
- 新增一行小字提示「目标仅提醒；点击「结束并结算」才记录有效。」（section 样式）。
- 最近记录每条追加服务给出的**起止时间**（`_hm` 格式化 started/finished），标题改为「最近的现实记录 · 最多显示最近 30 条」；空列表时给一句「还没有有效记录。」占位。
- 头像加载加 `isNull()` 兜底，缺 avatar.png 不再白屏。

**阶段 2 商店 + 关系**：
- 商店：礼物（gift）正确显示目标角色名（卡片与兑换历史两处都带「送给 <角色名>」，历史保留来源）；金币与真实预算本就分开显示，保留。
- 兑换取消不扣币（由 `rewards.redeem` 服务保证，UI 只是确认弹框为 No 时不调用）；预算确认仍走原有 `confirm_budget`。
- 关系卡片把「长期关系」和「短期情绪」**分行明确区分**（长期关系 X · 短期情绪 标签），说明文案沿用原「情绪随时间平复、休息/无记录不是过错」。

**阶段 3 群聊页**：
- **切群保留各自草稿**：新增 `_drafts`（按 gid 存）+ `_group_changed`，切到某群恢复它自己的未发送文本；服务触发 `refresh` 重建下拉时也显式回填目标群草稿，不清空。发消息成功后清掉该群草稿。
- **忙碌/停止/可继续/记忆支撑状态**：新增 `_stopped` 集合；「停止回复」把当前 gid 记入并 `hub.cancel_group`，状态栏显示「已停止…可继续发消息或点「继续回复」」；忙碌中显示原「正在倾听」文案；非忙碌非停止时**只按当前群成员过滤**记忆支撑状态（不再显示上一个群的角色）。
- **发送者姓名取历史快照 `m['name']`**（原就如此）+ 每条附时间（`_when`），角色改名不破坏历史显示。
- 保留 `private_context` 开关及其说明，未改成员/记忆授权/后台预算算法。

**阶段 4 模型配置界面**：
- 仅排版与帮助文案：把表单分三段「连接（留空继承全局）/ 群聊与轻互动模型 / 推理参数」，段标题用 section 样式；帮助文字讲清「不勾选完全沿用全局、留空项仍继承、各角色不串值、本页改草稿需点应用才生效、取消不改正式配置、测试按钮会真实发请求产生少量用量、不按型号名猜测推理」。
- **保留现有 DPAPI 写入（`protect`）和异步 `ModelTest` 线程机制不动**；`value()`/`save()`/`done()` 逻辑原样。

验证（命令 + 结果）：
- 页面相关：`python -m unittest discover -s tests -p test_module_views.py -v` → 6 tests OK；`-p test_module_http.py -v` → 3 tests OK。
- 新增/加强断言（均在临时目录 + 本地 HTTP，未用正式数据）：
  - focus：非默认 类别/说明/角色 持久化回填；暂停不计时（`elapsed` 不随假时钟增长）；结算只在一次 finish 内发生（二次 settle 余额不变、`records()` 仅 1 条）；idle 草稿不被 full refresh 覆盖。
  - rewards：兑换取消（question=No）金币不扣、不产生 redemption 记录；实际兑换扣币一次；礼物目标角色名出现在卡片与历史。
  - social：两个隔离群切来切去草稿各自保留；记忆支撑状态只按当前群成员过滤（第二群不显示第一群角色）；历史发言改名后仍显示旧快照名；忙碌时 send/stop 状态正确。
  - model：`RoleModelDialog` 取消不写 `config.value`；「测试」按钮通过本地 fixture 真实发出 1 条请求且 `result_label` 显示成功（自动化用本地 mock，无真实费用）。
- 全量：`python -m unittest discover -s tests -v` → **118 tests，83.96s，OK**（原 115，新增 3 条新测试；未删断言、未放宽金额/隐私限制）。

未完成 / 留待：
- 未实测真实付费模型的行为质量（仅本地 fixture 验证请求形状与诊断落库），真实供应商兼容性仍需主人显式测试。
- 群聊“在底部才跟随、未到底保留位置”的滚动锚点逻辑沿用原有实现，未重写增量气泡（Codex 已实现 message-id 去重跟随）。
- 未做打包、未启动 Ollama、未改数据库结构/迁移。

跨边界接口请求：无。本批全部在允许文件内完成，未需要 Codex 侧改动。

提交：见下方 git（含本记录 + 上述 5 个源文件 + 2 个测试文件；测试再生成的 `docs/*-preview.png` 已还原不混入提交）。

