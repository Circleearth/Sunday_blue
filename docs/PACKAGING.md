# 自行打包、后台运行与迁移

## 日常使用
- 双击根目录 SundayBlue.exe（无命令行黑窗）。设置 → 外观 / 数据 → 开启“关闭窗口后留在系统托盘”。关闭窗口后继续运行计时、提醒和后台任务；托盘点“打开”恢复、“退出软件”真正结束。源码版本同样支持，不是 EXE 专属能力。
- 不等于 Windows 服务或开机自启。关机、注销、睡眠期间不能持续执行；Ollama 仍按既有约定手动启动。
- 修改主代码后，旧 EXE 不会自动更新。希望暂时体验最新源码，运行 Start Sunday Blue Source.cmd；Start Sunday Blue.cmd 则优先使用 EXE。

## 用户决定何时构建
1. 从托盘退出 Sunday Blue。保留未保存编辑后再退出。
2. 双击根目录 Build Sunday Blue.bat；第一次需安装 requirements-build.txt 依赖。
3. 成功后运行根目录 SundayBlue.exe。build/dist/SundayBlue 是构建中间产物，没有你的数据和完整外置插件，不能单独当成完整发布包。

BAT 只是稳定入口，build.ps1 负责构建，并隔离开发工具注入的 PATH，避免打包进不兼容的同名 DLL。SundayBlue.spec 自动收集 sunday_blue 包模块及可分析的依赖。普通源码变更通常不用改这三个文件。外部插件代码保持 extensions 外置；特殊动态第三方依赖、新 DLL 或新独立运行时仍需调整依赖/Spec。不能承诺永远不需要维护打包脚本。

构建失败或隔离启动检查失败时不会替换当前程序。更新前在 build/previous/时间戳 保存旧 EXE 和 _internal；复制失败会恢复旧版本。只替换程序二进制，不清空 data/personas/assets/extensions/runtime。备份旧二进制不等于用户数据备份，也不保证未来数据库迁移可仅靠旧 EXE 回滚。

验证模式 --verify-package 使用临时数据检查完整页面、托盘隐藏/恢复和隐藏后的事件循环，不发起模型请求、不启动 Ollama、不读取真实资料。报告 package-check.json 位于被验证的 EXE 同目录。当前 Windows 桌面有系统托盘时才验证托盘行为。

## 一套压缩包建议布局
```text
SundayBlueBundle/
├─ Sunday_Blue/
│  ├─ SundayBlue.exe
│  ├─ _internal/
│  ├─ assets/
│  ├─ personas/
│  ├─ extensions/
│  ├─ data/
│  ├─ runtime/ollama/           包含模型 models/
│  ├─ runtime/livingmemory/     本机记忆运行环境
│  └─ 源码、requirements、scripts、打包入口（以后还要打包就保留）
└─ MasterData/                  用户文档，与软件目录并列
```

本轮没有移动现有 D:\MasterData，也没有复制或压缩个人数据。当前可继续原路径使用。准备整套备份时，先退出 APP 和它启动的 Ollama/记忆服务，再复制所需目录、压缩；避免运行中直接复制 SQLite。MasterData 不建议放在 Sunday_Blue 内部：AI 文件工具保护整个软件目录，放在内部可能能人工阅读但不能让 Kia/Mia 修改。移动后重新选择资料目录，并为 Kia/Mia 配置新的工作区权限；既有绝对路径、引用、修订路径不会自动重写。

运行用的最小包是 EXE + _internal + assets + personas + extensions + data + runtime，具体外部 MCP/QQ 网关等也要保留或重新配置。大模型文件体积较大；备份可以省略 build、.cache、.git、测试和旧构建，但希望以后自行构建时需保留源码、spec、脚本、requirements 及所需 assets。不要把含 data/API 凭据/个人记录的个人备份作为公共发布包。

## 当前可移植边界
主桌面 EXE 自带 Python/Qt；Ollama 已独立在本项目 runtime/ollama，模型也在其 models 内。但 runtime/livingmemory 目前是 Python venv，其 pyvenv.cfg 关联本机 Python 3.14，不能当作跨电脑便携 Python。换电脑需安装相应 Python 后运行 scripts/setup_livingmemory.ps1 -Python <实际 python.exe> 重建依赖；不要删除 data 中的记忆。Windows DPAPI 密钥换电脑/账户需重新输入；外部 MCP、QQ 网关、任务计划和绝对路径也需核对。

因此本轮交付是本机可用 EXE 与可重复构建入口，不宣称完整离线跨电脑解压即用。未来若需要真正全便携包，再把记忆进程做独立冻结程序/便携解释器，并加入路径迁移流程，不需要现在重做主应用。
