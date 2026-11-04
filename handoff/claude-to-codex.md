# Claude → Codex：Claude 做的改动，Codex 请读取

> 本文件只由 **Claude** 追加记录，由 **Codex 阅读**。
> Codex 读完本文件全部记录后：把本文件内容整体移入 `handoff/archive/`，命名为
> `YYYY-MM-DD_claude-by-codex.md`（当天日期 + 谁做的 + 谁归档），再新建一个空的本文件（保留头部说明）。
> 详见 `handoff/HANDOFF.md` 的"归档规则"。

---

## 2026-11-04 · 聊天增量渲染 + 微信式"查看最新"（Claude 做，分支 fix-chat-incremental-follow）

**主人的原始诉求**：流式回复时"Agent 输出会跳顶"；"每条消息（我发的或 Agent 发的）整个 UI 闪一下"；
希望像微信——在底部看时新消息自动跟随，往上拉历史时不被拽走、浮出可点击的"查看最新"按钮，点击回底。

**根因（Codex 之前 30ms 恢复本身没问题，问题在 clear_chat）**：
`render()` 每次都被 `clear_chat()` 全量拆掉重建（`deleteLater()` 所有气泡再 addWidget）。
流式 tick / 工具回执 / 分段揭示的 80ms 计时器反复触发 render → 内容高度每帧塌到 0
（滚动条 maximum=0，可见跳顶帧）+ 全量重挂触发整块重绘（闪烁）。
Codex 的 30ms `QTimer` 恢复是为了等 Qt 延迟布局稳定，这个思路是对的，我保留了。

**改了什么（只动 `sunday_blue/ui.py` + 新增 `tests/test_chat_follow.py`）**：
1. `render()` 拆成两条路径：
   - **rebuild**：只在"换了会话 / 首次 / settings 强制重建"时全量重建，
     30ms 后恢复滚动（切会话回底；同会话强制重建/切角色保持原位置——沿用 Codex 原语义）。
   - **append**：同会话新内容（流式 tick、工具回执、分段揭示、新落库消息）只插新气泡，
     已显示的气泡不删除、不重排 → 不再塌高度、不再闪烁、不再跳顶。
   - 增量路径新增 `was_at_bottom`（渲染前判定）：在底 → 延迟 30ms 跟随到底；
     在读历史 → 完全不动视图，`_auto_follow=False`。
2. `_auto_follow` 状态：由 rebuild 结果/读历史/点击"查看最新"三处写入；
   `on_text` 的流式跟随改用 `self._auto_follow`（原来每次 render 都在读滚动条位置，
   增量渲染下滚动条可能未更新，会造成"不自动到最新"）。
3. "查看最新"浮动按钮：`follow_button` 是 `chat_scroll` 的**子控件**（绝对定位在滚动区底部居中），
   **不在面板 layout 里**，所以它的显隐不会挤压任何 layout、不会引起闪烁。
   `valueChanged`/`rangeChanged` → `_update_follow_button()`；`_follow_clicked()` 回底并恢复自动跟随。
4. 新增 4 条回归测试（`tests/test_chat_follow.py`）：读历史不被拽走、在底自动跟随、
   增量追加不销毁旧气泡、点"查看最新"后恢复跟随。

**验证**：全量 47 条旧测试 + 4 条新测试（`test_import_font_and_persist_settings` 因
Windows 字体文件锁在干净 main 上也会偶发 ERROR，与本改动无关，已对照 stash 验证）。

**剩余风险 / 留给后续**：
- "会话历史按日期查询（只显示近 50 条 + 历史对话按钮）"主人说要拆成独立模块，**本次未做**，
  等主人再明确；记忆插件将来按日分类时复用。
- `add_tool()` 仍是往 layout 里插旧式工具气泡（目前 Agent 回执走 `tool_failure` 路径，`add_tool` 无调用者）。
- 增量渲染假设"消息只增不改"：若将来加"编辑历史消息"功能需要走 `_force_rebuild` 或重建路径。
