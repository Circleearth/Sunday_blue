# Claude → Codex：Claude 做的改动，Codex 请读取

> 本文件只由 **Claude** 追加记录，由 **Codex 阅读**。
> Codex 读完本文件全部记录后：把本文件内容整体移入 `handoff/archive/`，命名为
> `YYYY-MM-DD_claude-by-codex.md`（当天日期 + 谁做的 + 谁归档），再新建一个空的本文件（保留头部说明）。
> 详见 `handoff/HANDOFF.md` 的"归档规则"。

---

## 2026-11-04 · "查看最新消息"按钮加 1 秒延迟（Claude 做）

主人要求：不在最底部时，停留 1 秒后才浮出"⌄ 查看最新消息"按钮；回到底部立即隐藏。
只动 `sunday_blue/ui.py` 的 follow 模块（在 Codex 8fcb8b7 之上）：
- 新增 `_follow_show_timer`（单发 1000ms QTimer）；`_update_follow_button` 改为
  在底 → 停止计时器并立即隐藏；不在底且计时器未走 → 启动计时器；超时回调
  `_show_follow_button` 再确认一次仍不在底才显示。
- `_follow_clicked` 里先 stop 计时器。
- 同步更新 `tests/test_chat_follow.py`（延迟 1.2s 断言 + 新增"回底即隐藏"用例）。
验证：全量 62 tests OK。
