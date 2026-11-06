# 2026-11-06 Codex → Claude 交接归档（Claude 已读）

> 原载于 `handoff/codex-to-claude.md`，Claude 于 2026-11-06 读完并归档。

## 2026-11-06 20:24 — Codex
改动：新增 extensions/plugins/livingmemory（原版 2.9.1 核心/存储/页面 + 独立适配层）；新增 living_memory.py、memory_preferences.py、memory_editor.py、personas.py、persona_preferences.py、change_review.py；Agent 会话钩子；插件清单变更缓存；人格归档和四栏目 UI；README/docs/插件合同/维护地图及升级检查脚本。
目的：用户要求每角色独立记忆大脑、保留原版图谱、本软件独立 Ollama 且手动启停；确认记忆在 APP 可编辑；文件/记忆修改左右审阅；人格集中维护，专业技能留给后续插件。
状态：功能完成。当前仍不打包，需退出旧 Sunday Blue 后源码重启。
对方需要知道：
- `runtime/ollama` 已有本机独立 Ollama 与 bge-m3，约 3.4 GB，端口11435；未改 Rui-bot，也不依赖其目录。`runtime/livingmemory` 为独立 Python3.14 环境；两者被 gitignore 忽略，源码克隆不会带模型，见 setup 脚本。
- 新插件默认不启用；右侧"记忆大脑 / Ollama"可手动启动模型、按角色勾选自动记忆、打开原版图谱、立即整理。监测/软件启动不会启动 Ollama；测试结束已停服务。
- `data/plugins/livingmemory/<role>` 按角色隔离进程/SQLite/向量/图谱。before_turn 召回到本轮 system；after_turn 只排入成功完整轮次，默认4轮整理，可配置。LLM 用当前 Sunday API，向量本地。旧 AstrBot 数据/配置未迁移。
- `long_term.md` 保留为用户确认事实；APP可编辑，模型仍需确认，信任工作区不能绕过。ChangeReview显示完整前后两栏+变更行，原FileTools备份/并发复核仍在；取消后写入再检查。
- 人格只加载identity/personality/voice/relationships。七角色原expertise/rules/responsibilities共21份原样移到personas/_archive；身份内核原样保留。TickTick/Mubu补齐中性工具助手栏目。用户保存前左右审阅、保存版本、可载入上一版再确认，模型没有人格写入工具。
- 上游vendor字节保持原样，.gitattributes禁止转换；upstream-lock.json记录来源与哈希；scripts/livingmemory_upstream.py可区分候选版后台/UI变动，不自动更新。不是完整AstrBot Runtime兼容；原版Agent自主回忆工具未注册，平台触发项不控制本软件队列。
- QQ reminders源码与其工具/设置钩子未修改。原有未提交的预览PNG和qq-reminders/daemon/launch.vbs保留、不纳入本次提交。测试还会重新生成appearance-redesign-preview.png，该旧预览也不纳入。
验证：改动前71项通过；最终全量 `python -m unittest discover -s tests -v` 为79项通过（69.139s）。两轮真实Ollama+本地HTTP摘要fixture集成通过，另有一次真实聊天API+本地bge-m3通过：摘要、原子、图谱、跨角色隔离、重启召回、幂等、鉴权与跨站拒绝。均使用临时合成对话数据，没有写真实用户记忆。原生Qt图谱预览已查看。py_compile、定制代码diff检查、vendor哈希验证通过。曾发现插件多次重读导致并发UI用例超时，已加按mtime/size变更的清单缓存，随后相关与全量测试通过。

## 2026-11-06 16:14 — Codex
改动：新增 `design_system.py` 和 `docs/UI_DESIGN_SYSTEM.md`；重写 `theme.py` 的 token 生成样式；调整 `ui.py`、`ui_components.py`、`settings.py`、`chat_preferences.py`、`chat_presentation.py`、`storage.py`、README、架构与维护地图；增加 UI 回归测试和两张新版预览。
目的：按主人确认的方案建立可维护 UI 设计系统；界面字体精选且固定字号；九角色气泡字体独立；缩小等距气泡；设置页改为左侧导航和分组卡片；保存字体不再打断正在等待显示的分段。
状态：完成。
对方需要知道：`ui_display.font_family` 只管 UI；`chat_display.role_fonts.<role>` 管角色气泡。九个默认字体来自本机已有中文字体，不分发来历不明的字体文件；每个角色可在设置中独立导入。QQ reminders 插件及宿主钩子未修改。Claude 原交接已按规则归档为 `archive/2026-11-06_claude-by-codex.md`。
验证：`python -m unittest discover -s tests -v` 最终 71 tests OK；`py_compile` 与 `git diff --check` 通过。第一次全量中并发 UI 用例偶发 8 秒超时，单独复跑通过，随后完整全量 71/71 通过。
