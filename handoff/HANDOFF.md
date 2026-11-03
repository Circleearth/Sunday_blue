# Sunday_Blue 共同交接文件夹（Claude ↔ Codex）

本文件夹是 Claude 与 Codex 两个开发方共用的交接区。规则：

- **每个开发方每完成一批有意义的改动，就来这里追加一节**，格式见下方模板。不要删除或改写对方已写的记录，只追加。
- 记录要写清：改了哪些文件、为什么改、当前状态（完成/进行中/遗留问题）、下一步给对方的建议。
- 涉及构建/打包/测试结果的，附上运行过的命令和结果。
- 如果一方发现会破坏整个应用的改法（例如打包参数、目录结构、数据布局），先在这里留一条"风险预警"，再动手。

## 模板

```markdown
## YYYY-MM-DD HH:MM — <Claude | Codex>
改动：<文件/目录列表>
目的：<为什么>
状态：完成 / 进行中（还剩 X）
对方需要知道：<遗留问题、风险、下一步>
验证：<跑过的测试/构建命令与结果>
```

---

## 2026-11-03 17:04 — Claude

改动：
- 初始化本地 git 仓库（`D:\Sunday_Blue\.git`，分支 `main`），提交基线。`.gitignore` 已排除 `data/`、`build/`、`_internal/`、`*.exe`、`__pycache__/`、`tests/sunday-test-*/`、`tests/ui-test-*/`。
- 新建本交接文件夹 `handoff/`。
- 在 `README.md` 增加对本文件夹的指引（见"共同交接"一节）。

目的：
- 主人要求 Codex 也来维护本目录，双方修改文件时避免把整个 APP 改坏。git 仓库用于保护：任何改动前先有可回退的基线，改坏了可以 `git diff` 对照、`git checkout` 恢复。

当前状态：**进行中**。

对方（Codex）需要知道：
1. 打包尚未完成。`build/work/SundayBlue/` 里只有构建中间产物，`build/dist/` 为空，根目录没有 `SundayBlue.exe`。上次构建在"Copying icon to EXE"失败：`FileNotFoundError: D:\Sunday_Blue\build\assets/app.ico`。
   - 根因：`build/SundayBlue.spec` 第 35 行写的是相对路径 `icon=['assets/app.ico']`，而 `build.ps1` 用 `--specpath build` 让 PyInstaller 生成的 spec 落在 `build/` 目录，PyInstaller 解析相对路径时以 spec 所在目录（`build/`）为基准，于是找 `build/assets/app.ico`（不存在）。
   - 修复方向（任选其一）：spec 中 icon 改为绝对路径或用 `os.path` 拼到项目根；或构建时 cwd 保持在根目录且 spec 路径相对方式调整。修复后重跑 `build.ps1 -Python python`，确认根目录生成 `SundayBlue.exe` + `_internal/`，并用 `Start Sunday Blue.cmd` 启动做独立检查。
2. 改动前后请跑 `python -m unittest discover -s tests -v`（上次 22 项全部通过，见 `docs/test-results.txt`）。
3. 遵守 `AGENTS.md`：不依赖旧项目（Great_blue/RedOS/Sunday），不读旧数据库，测试用本机 HTTP/MCP 假服务，不触碰真实 API Key 与 `data/` 中的用户会话。
4. git 提交时保留本交接文件夹，提交信息写清动了什么；提交署名按主人全局 git 身份（环状地球 / 2294104744@qq.com）。

验证：
- `git init` + 首次提交（见 git log）。测试基线沿用上轮 `docs/test-results.txt`（22 passed，7.998s）。
