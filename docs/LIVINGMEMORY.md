# LivingMemory 接入与维护

## 目录职责

| 位置 | 职责 |
|---|---|
| `extensions/plugins/livingmemory/main.py` | 宿主会话钩子、插件设置入口 |
| `worker.py` | 每角色运行期、队列整理、原版 Page API 和受保护的本地服务 |
| `providers.py` | Sunday Blue 聊天 API、Ollama 向量接口 |
| `compat.py` | 独立子进程中的最小 AstrBot logger/provider/context 类型表面 |
| `bridge.js` | 原版前端与本地 API 的桥接；不改上游页面 |
| `vendor/livingmemory` | 原版 2.9.1 核心、数据层、页面、资源、schema、许可证 |
| `vendor/astrbot` | 原版 AstrBot FAISS/文档存储、分词器和词表 |
| `upstream-lock.json` | 上游版本、提交与每个源文件的 SHA-256 |
| `sunday_blue/living_memory.py` | 进程所有权、手动启停 Ollama、消息队列、宿主调用 |
| `sunday_blue/memory_preferences.py` | 状态、角色选择、启停、图谱原生窗口 |
| `runtime/livingmemory` | 本软件独立 Python 环境（不入 Git） |
| `runtime/ollama` | 独立 Ollama 程序、库、models（不入 Git） |
| `data/plugins/livingmemory/<role>` | 该角色 inbox、引擎库、索引、备份、配置、日志 |

## 生命周期与边界

软件启动和监测均不启动 Ollama。用户点启动才以独立环境变量 `OLLAMA_HOST=127.0.0.1:11435`、`OLLAMA_MODELS=<本软件>/runtime/ollama/models` 启动自己的实例。无需从 Rui-bot 读取任何运行文件。

角色记忆进程在 Ollama 已在线且本机 bge-m3 存在时按需启动。每个角色的数据目录和进程都独立，避免上游 PromptManager 等全局对象串角色。关闭插件停止新增和自动整理；已有页面仍可管理该角色历史。正常退出停止本软件进程；worker 监测桌面进程异常结束并退出。Ollama 异常退出残留不按名称全局杀进程；UI 不接管未知的端口占用者。

before_turn 召回历史数据，仅注入当前 system，不写消息；after_turn 只接收完成的用户/助手文本。工具回执、thinking 和失败片段不送记忆。默认按 4 轮整理，每个角色单独参数。成功前不推进 inbox 游标，服务重启后继续。重复 turn 不重复写；sunday_job/sunday_committed 处理文档已经保存而队列游标尚未落库的恢复。

两层记忆：`long_term.md` 是用户确认的事实；LivingMemory 是自动摘要的历史证据。后者可能有误，禁止据此认定用户授权、覆盖确认事实或改写人格。人格四文件是用户设置，不提供模型写入工具。身份与文件权限分离。

## 原版保留与适配差异

保留实际记忆引擎、原子分类/生命周期、BM25+向量+图谱检索、重要性衰减、整合器、索引验证/备份以及 Page API。保留原版 2D/3D 图谱和设置资源，无需 Node 构建即可运行。

没有启动完整 AstrBot，没有其事件总线、QQ/群聊适配器和原版 Agent 工具注册；本版接入自动召回与按轮次反思，尚未注册上游自主多轮 recall/forget 工具。高级页保留上游 schema，AstrBot 专属的会话触发/平台权限项不影响桌面队列；桌面触发参数由 plugin schema 控制。UI 修改高级参数会保存到 engine-config.json，涉及初始化的核心设置需要重启记忆服务。

向量为本地 bge-m3，摘要使用当前聊天 API；未安装 reranker，因此该高级选项不应被误认为已配置成功。大模型仍可能总结错或漏掉事实，用户可在图谱修正/删除。自动队列不会回溯导入旧历史和旧 AstrBot 数据。

## 升级接口（低优先级维护入口）

1. 不直接覆盖 vendor；另行下载想升级的上游版本到独立目录。
2. `python scripts/livingmemory_upstream.py` 验证本机快照未被改动。
3. `python scripts/livingmemory_upstream.py --candidate <候选源码目录>` 按 backend/UI/metadata 输出增删改列表，优先审阅 core/storage 的技术变化。
4. 审阅 providers/context/Page API 和数据迁移兼容性；更新前备份整个 `data/plugins/livingmemory`。不要复制现有 AstrBot 用户库覆盖它。
5. 在临时目录跑兼容测试和真实向量测试，通过后才替换固定快照、调整必要适配层，并更新 lock 的版本/commit 和 SHA-256。
6. `--record` 仅是维护者确认后重新记录当前快照，不是自动更新；版本/commit 常量也须同步改成真实来源。保留两份原版许可证。

脚本不访问网络、不自动更新、不改用户记忆；未来可以在此基础上添加上游 release 检测。没有声称自动跟随上游。

## 验证

- `python -m unittest discover -s tests -v`：宿主、权限、记忆确认、人格版本、UI、队列和钩子。
- `python scripts/test_livingmemory_live.py`：显式手动启动本软件 Ollama，真实 bge-m3 + 原版核心 + 本地 HTTP 摘要 fixture；临时数据库。
- 加 `--live-chat`：使用当前聊天 API 对合成文本做少量真实整理，产生 API 用量。
- 加 `--preview`：应用内加载原版图谱，生成 docs/livingmemory-preview.png；临时数据随测试清理。

已验证一轮真实模型摘要、原子/图谱生成、不同问法召回、两个角色互不读取、同轮去重、重启持久化、Page API、未鉴权/跨站访问拒绝。测试不等于对长期记忆准确率的保证。
