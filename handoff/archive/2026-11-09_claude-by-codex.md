# 归档 · 原 claude-to-codex.md · 归档于 2026-11-09 by Codex

## 2026-11-06 21:30 — Claude
改动：`sunday_blue/chat_presentation.py` 第70行 `PreferFullHinting` → `PreferNoHinting`；`main.py` 在 QApplication 创建后给 app 默认字体设一次 `PreferNoHinting`（样式表 `*{font-family:...}` 里的文字继承 app 默认字体的 hinting，一处设置覆盖全 UI）。
目的：本屏 175% 缩放下 UI 13px 按 22.75 物理像素（小数）光栅化，Qt 全量/默认 hinting 会把部分汉字横线吸附到 1px、与相邻 2px 笔画粗细不均（撇捺/横线"粗细非常不均匀、部分横线异常细"）。NoHinting 让所有笔画保持光栅化前权重，与 FreeType 基线一致。已按主人要求审计（排除字体本身笔画设计：四种风格不同的字体同现此现象；实测分数物理像素 + 全量 hinting 是触发条件，整像素时 hinting 模式逐字节无差异）。
状态：已修复并经主人亲验（"确实修好了"）。全量 79 tests OK。
对方需要知道：
- 还原点：`git revert 17139ec`（一行一行都小，revert 即完全恢复旧行为）。
- 仅动字体光栅化参数，未改布局/配色/业务逻辑；`theme.py` 样式表、`design_system.py`、`chat_preferences.py` 均未动。
- 若以后主人把系统缩放改成 100%/125%（整数物理像素），本改动无副作用（整像素时各 hinting 模式输出相同，已实测）。
验证：QImage 逐字节对比（Full vs No，dpr=1.0 全等；dpr=1.75 有差异）+ 汉字笔画厚度量 + 主人在真实窗口确认。
