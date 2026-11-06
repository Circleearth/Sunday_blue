# 主人的直接指令 / Master Notes

> 这个文件由**主人**（或替主人记录的人）直接写，是最高优先级的指令。
> **Claude 和 Codex 双方都必须读**。这里的内容压过两份 to- 文件里的任何"下一步建议"。
> 目前打包仍暂停、启动一律走 `.cmd`/`main.py`、版本分歧优先以 Codex 为准——这些约定
> 由 Claude 从主人的原话整理如下，主人可随时在此修改或追加。

---

## 2026-11-06 14:53 — 主人指令（qq-reminders 插件）

**qq-reminders 已是正常运行的插件（本机守护进程 + 看门狗 + 试发全通）。
Codex 除非发现恶性 bug（守护崩溃、提醒全丢、误杀进程），否则不要改本插件及宿主对应钩子，避免混乱。**
Claude 已在 `claude-to-codex.md` 写清现状与改动边界。

---

## 2026-11-03 20:06 — 主人指令（Claude 代为整理，待主人确认或修改）

1. **先不要打包。** 还在调整阶段，不要跑 `build.ps1`；日常启动一律用 `Start Sunday Blue.cmd` 或
   源码模式（`pythonw main.py`），数据照常落 `data/`。
2. **启动路径要稳**：双机/单机都从 `.cmd` 或 `main.py` 直接启动即可，不依赖 EXE。
3. **版本/方案分歧原则**：如果 Claude 和 Codex 用了不同方案处理同一处，**优先以 Codex 的为准**；
   只有确认 Codex 的做法有明确错误或不清楚，才允许 Claude 修复。
4. **每次改完必须同步 handoff**（写进对应的 to- 文件）+ `git add -A && git commit && git push`。
5. **改动前后跑** `python -m unittest discover -s tests -v`。

---

（主人在这里直接追加新的指令；Claude / Codex 读到后按此执行，不要擅自改写本文件的措辞，
有异议在各自 to- 文件里另开一条"风险预警"。）
