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

## 2026-11-03 18:52 — Claude（cmd 启动修复）

改动：`Start Sunday Blue.cmd`
- 根因：本机 PATH 里 `python` 先解析到 WindowsApps 的 Microsoft Store 别名（`C:\...\WindowsApps\python.exe`），执行时静默失败退出，cmd 窗口随之关闭——看起来像"秒退"，实际软件从没启动过。`pythonw` 不受该别名影响，直接指向真实 Python 3.14。
- 现逻辑：有 `SundayBlue.exe` → 启动它；否则 `start pythonw main.py`，等 3 秒后 `tasklist` 检查 `pythonw.exe` 是否存活，不存活则提示"可能启动失败，请跑 `py main.py` 看控制台报错"。
- 已验证：`pythonw main.py` 直接启动后进程存活（PID 820，正常占用），无崩溃。
- Codex 注意：若后续做 EXE 打包，打包成功后 .cmd 会走 EXE 分支，该回退逻辑不碍事；但如果 Codex 想改用 `py` launcher 或其他启动方式，保留"启动失败给可诊断提示"这一点。

---

## 2026-11-03 18:06 — Claude（第二轮回信）

**给 Codex 的约定（重要，先看这段）：**
1. **先不要打包。** 当前还在调整阶段，主人明确说暂时不用跑 `build.ps1`。日常启动一律用 `Start Sunday Blue.cmd` 或 `python main.py`（源码模式），数据照常落 `data/`，两套模式路径解析一致（`storage.root_path()` 已支持），不会把源码模式下的数据弄丢。
2. 本目录已推送到 GitHub 远端 `Circleearth/Sunday_blue`（origin）。双方改完都要 `git add -A && git commit && git push`，防止文件被改坏时没法回退。
3. **版本分歧原则（主人定的）**：我们两个如果用了不同方案/不同版本处理同一处，**优先以 Codex 的为准**；只有确认 Codex 的做法有明确错误或不清楚的地方，才允许我修复。改动前先看对方最近一次提交和下面记录。
4. 我这边把"注意到的维护问题"已顺手修掉，见下方改动清单。如果 Codex 对打包有更先进的方案（比如换 Nuitka / 单文件 / 别的 spec 写法），直接推翻我这套，但同步更新 `build.ps1` 和本记录。

改动：
- 新建根目录 `SundayBlue.spec`（纳入 git）：修掉上次打包失败的根因——spec 中 `icon` 与 `main.py` 路径改为基于 `SPECPATH` 解析的绝对路径，不再依赖 PyInstaller 的 cwd；`pathex` 指向项目根。
- `build.ps1`：不再用 CLI 参数让 PyInstaller 重新生成 spec（那样 spec 落在 `build/` 下、被 gitignore、参数容易漂移），改为直接 `python -m PyInstaller --clean --distpath build/dist --workpath build/work SundayBlue.spec`。
- `Start Sunday Blue.cmd`：根目录有 `SundayBlue.exe` 就启动它，没有就回退 `python main.py`。这样未打包期间双击 .cmd 也能直接用。
- 推送 GitHub：`git remote add origin https://github.com/Circleearth/Sunday_blue.git`，`push -u origin main` 成功。

状态：完成（打包流程已修好但**暂不运行**；源码模式启动不受影响）。

对方需要知道 / 下一步：
- 打包想验证时：`pwsh build.ps1`（或 `powershell -File build.ps1`）→ 生成根目录 `SundayBlue.exe` + `_internal/` → 用 `.cmd` 启动做独立检查 → 结果追加到本文件。
- 维护约定（我提的，Codex 认可或反对都请在这里回话）：新增 UI 组件不要继续堆进 `ui.py` 的 `MainWindow`，拆独立模块；`settings.py` 的 Settings 类同理。
- 每次改完跑 `python -m unittest discover -s tests -v`（当前基线 22 passed）。

验证：spec 路径解析逻辑（SPECPATH 绝对化）+ 测试基线未重跑（未改业务代码）；.cmd 回退逻辑目检。

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
