# Codex → Claude：Codex 做的改动，Claude 请读取

> 本文件只由 **Codex** 追加记录，由 **Claude 阅读**。
> Claude 读完本文件全部记录后按 `handoff/HANDOFF.md` 归档，并保留本头部。

---

## 2026-11-06 16:14 — Codex
改动：新增 `design_system.py` 和 `docs/UI_DESIGN_SYSTEM.md`；重写 `theme.py` 的 token 生成样式；调整 `ui.py`、`ui_components.py`、`settings.py`、`chat_preferences.py`、`chat_presentation.py`、`storage.py`、README、架构与维护地图；增加 UI 回归测试和两张新版预览。
目的：按主人确认的方案建立可维护 UI 设计系统；界面字体精选且固定字号；九角色气泡字体独立；缩小等距气泡；设置页改为左侧导航和分组卡片；保存字体不再打断正在等待显示的分段。
状态：完成。
对方需要知道：`ui_display.font_family` 只管 UI；`chat_display.role_fonts.<role>` 管角色气泡。九个默认字体来自本机已有中文字体，不分发来历不明的字体文件；每个角色可在设置中独立导入。QQ reminders 插件及宿主钩子未修改。Claude 原交接已按规则归档为 `archive/2026-11-06_claude-by-codex.md`。
验证：`python -m unittest discover -s tests -v` 最终 71 tests OK；`py_compile` 与 `git diff --check` 通过。第一次全量中并发 UI 用例偶发 8 秒超时，单独复跑通过，随后完整全量 71/71 通过。
