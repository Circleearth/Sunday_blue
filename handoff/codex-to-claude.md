# Codex → Claude：Codex 做的改动，Claude 请读取

> 本文件只由 **Codex** 追加记录，由 **Claude 阅读**。
> Claude 读完本文件全部记录后按 `handoff/HANDOFF.md` 归档，并保留本头部。

---

## 2026-11-09 — Codex：角色生命周期阶段完成
改动：新增 roles / role_lifecycle / role_preferences，统一 UI、设置、Store、人格和 LivingMemory 的角色来源。角色 ID 不随显示名变化。归档、恢复、ZIP 导出、带依赖检查和日志续做的永久删除已接入。
目的：保留现有存储和聊天链路，消除固定九角色限制。修复 Agent 插件加载根目录不一致、动态角色字体默认值缺失。
状态：阶段 1 完成；接着做人格请求验证与角色能力加载。
对方需要知道：此前未提交的会话菜单/归档/删除改动已保留；会话删除不代表删除提炼后的角色记忆，已纠正说明和吞错误行为。没有动 QQ 源码和守护钩子；待发提醒阻止归档/删除。正式数据未测试删除。修改前补丁在 `.cache/role-refactor-checkpoint/before.patch`。完整审查见 `docs/ROLE_SYSTEM_REVIEW.md`。
验证：修改前 82 tests OK；本阶段全量 89 tests OK（79.053s），新增角色/改名/重启/隔离、UI 同步、删除故障续做均用临时目录验证。无打包、无真实模型费用。
