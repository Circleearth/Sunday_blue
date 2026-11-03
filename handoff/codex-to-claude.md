# Codex → Claude：Codex 做的改动，Claude 请读取

> 本文件只由 **Codex** 追加记录，由 **Claude 阅读**。
> Claude 读完本文件全部记录后：把本文件内容整体移入 `handoff/archive/`，命名为
> `YYYY-MM-DD_codex-by-claude.md`（当天日期 + 谁做的 + 谁归档），再新建一个空的本文件（保留头部说明）。
> 详见 `handoff/HANDOFF.md` 的"归档规则"。

---

## 2026-11-03 21:55 — Codex（时间插件、维护导航、组件拆分）
改动：time_context.py、agent.py、ui_components.py、ui.py、test_time_context.py；PLUGIN_SPEC.md、MAINTENANCE_MAP.md、HANDOFF.md、README、ARCHITECTURE 及测试记录。
目的：每轮新鲜日期/本地时间作为系统背景，避免日期过期和例行报时；明确插件创建合同和维护入口，降低重复读取成本。
状态：完成。本轮不打包、不动用户配置/数据、不安装 AstrBot。
对方需要知道：
- 已读完并确认你原有全部交接，归档到 archive/2026-11-03_claude-by-codex.md；暂停打包以及已修复主题/IME/thinking/目录工具均沿用。
- 唯一行为新增为 time_context：九角色常驻系统插件，无设置开关，不是 JSON 插件。取 OS 本地时区，精确到分钟，每用户轮/重试采样，同轮工具调用共享时间快照。纯整理压缩器不注入当前时间。不要重新加 agent 原来的 UTC 当前时间句子。
- UI 拆分只移动 text_label/button/TitleBar/Composer/Portrait/Bubble，逐字对比原实现一致。ui.py 同名导入兼容旧测试；以后改组件去 ui_components.py，编排去 ui.py。
- 插件规范唯一来源 PLUGIN_SPEC.md；维护职责唯一索引 MAINTENANCE_MAP.md。settings/agent 暂不再细拆。
- AstrBot 当前只是评估。优先可选原生运行时桥接以复用插件；JSON 插件加载器不能加载 AstrBot Python 插件。不宣称全市场兼容或已有桥。PoC 和第三方插件版本/许可证检查尚未实施。
- README 修正了源码启动、/compact 和已移除上下文详情按钮，保留其他功能。
验证：基线全量 26 OK；修改后 `python -m unittest discover -s tests -v` → 29 OK（13.302s）；diff --check 通过；移动的组件与 HEAD 原实现一致。新测试覆盖跨日/时区/九角色系统注入/不写 messages。测试为本地 mock，未做真人自然度 A/B 或真实 API 联调。
