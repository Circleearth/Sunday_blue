# Sunday Blue 插件创建规范（2026-11-04 / 外置插件 API v1）

本文件是当前扩展合同；取代此前“native_plugins 固定登记、插件实现留在 sunday_blue”方案。用户操作见 README，导航见 MAINTENANCE_MAP。

## 1. 目录与发现

每个 Python 插件放到 `extensions/plugins/<id>/`，三个必要文件：

- `plugin.json`：清单。
- `main.py`：插件入口，UTF-8 Python。
- `_conf_schema.json`：参数定义，没有参数可用 `{}`。

最小清单：
```json
{"id":"my-plugin","name":"示例插件","version":"1.0.0","api_version":1,"entry":"main.py","description":"用途","default_enabled":false}
```

id 只能使用字母、数字、下划线、短横线，必须与目录名相同。宿主 `plugin_runtime.discover(root)` 扫描，错误清单在插件页显示为禁用的错误条目。默认入口仅 main.py；不自动安装依赖、不从网络下载代码。入口在实际启用并发送时加载，模块按绝对路径和修改时间缓存。删除目录后不再发现或加载；替换代码后建议重启，避免运行中任务混用版本。关闭插件不删除其状态或历史。

Python 插件是用户安装的可信本地代码，拥有当前 Windows 用户权限，**不是沙箱**，不受 FileTools 的目录授权约束。新增第三方插件应默认不启用；不要声称它和 JSON 提示词具有同等权限。内置的两个外置插件默认启用。不要读取凭据、记录 API key 或擅自联网。

## 2. 参数读取器 / 设置表单

APP 的 `plugin_preferences.PluginPreferences` 按 `_conf_schema.json` 生成 UI，每个插件一行启停及“设置”按钮。参数按角色保存：
`data/settings.json → roles.<role>.plugin_settings.<plugin-id>`；启停兼容原键 `roles.<role>.native_plugins.<plugin-id>`。

示例：
```json
{
  "interval": {"type":"int","description":"间隔（分钟）","default":60,"hint":"说明","slider":{"min":0,"max":1440}},
  "enabled": {"type":"bool","description":"启用该行为","default":true}
}
```

基础字段名称参考本机 AstrBot `docs/zh/dev/star/guides/plugin-config.md`：支持 bool/int/float/string/text/object/list/dict，description/hint/default、options/labels、slider.min/max、secret、invisible。object/list/dict 使用 JSON 文本编辑器与类型检查；不递归生成嵌套表单。secret 仅遮罩界面，不加密插件参数；密钥应继续使用专门凭据机制。尚不支持 template_list、文件上传、_special 提供商选择器和 AstrBot WebUI 扩展。未知字段类型在 UI 明示不支持。

读取用 `plugin_runtime.parameters(config,role,pid,root)`：schema 默认值 → 旧 greetings 全局设置兼容（仅寒暄）→ 角色参数。外层“保存设置”才原子写入；取消外层对话框丢弃修改。下一条任务获取深拷贝，不改变正在运行任务。`_plugin_root` 只用于任务快照定位，不能持久存储。

## 3. 普通扩展入口

纯上下文插件可以实现：
```python
def system_context(config):
    return "本轮需要的短系统背景"
```

config 是该角色解析后的参数字典。宿主将非空字符串加入当前请求的 system，不显示在聊天中，也不写入 messages。未启用插件不执行入口。异常作为请求失败显示，不伪装成功。没有后台定时任务、自动联网、工具注册/进程隔离或完整 AstrBot 事件总线。普通 system_context 在每次任务开始构建，不能自行往 UI 填固定消息。

3b. 可选工具与设置对话框挂钩（宿主只约定了这两个钩子，实现必须自己带）：
```python
def tools():
    return [{'name':'...','description':'...','input_schema':{...}}]   # 宿主按 plugin_<id>_<name> 注册并分发

def settings_extra(root):
    return QWidget()  # 嵌入该插件“设置”对话框底部；无此函数则对话框只有参数表单
```
`tools()` 的宿主分发规则：工具名加 `plugin_<id>_<name>` 前缀注册；调用时宿主把 (config, role, name, args) 交给 `dispatch`。`settings_extra(root)` 由宿主在 `PluginPreferences` 对话框内嵌到参数表单下方（宿主负责标题与滚动区）；插件只实现自身后台组件（守护进程、计划任务等）的只读状态与启停按钮，异步操作必须用 QThread 后台线程，不得阻塞对话框；不得触碰宿主数据或其他系统的进程。插件可通过 `w._settings_extra_title` 自定义区块标题。

目前时段寒暄还使用一个宿主明确支持的有状态协议（下一节）；不能仅给任意第三方插件写一个任意钩子名就期望自动执行。需要新增钩子时同时修改宿主、合同与测试。

## 4. 时间上下文插件

实现 `extensions/plugins/time-context/main.py`；time_context(moment=None) 接受带时区 datetime，默认读取 OS 本地时区，每轮采样日期、星期、时间及 UTC 偏移。`include_time=false` 只保留日期背景。禁止例行报时；本轮明确 greeting_event 是允许寒暄的例外，避免两份规则冲突。旧 `sunday_blue/time_context.py` 只是兼容包装。

## 5. 时段寒暄插件

实现 `extensions/plugins/daypart-greetings/main.py`，通过 Greetings(data) 接入 Agent：
- on_message(config,role,sid,message_id,moment=None) → 短 greeting_event 或 None。
- replay_legacy(sid,messages) → 将旧本地问候加入本次上下文副本。
- discard(role,sid,message_id) → 未输出正文失败/取消或明确撤回时释放触发。

状态库 `data/plugins/daypart-greetings/state.sqlite3`：seen（角色/日/时段与提醒计数）、triggers（会话/消息预留）、activity（角色最近用户消息时间）、events（v1 只读兼容）。迁移只 CREATE IF NOT EXISTS，不清库。时间比较用带时区 timestamp。插件不改变用户主库 schema。

默认 idle_minutes=60：本次距该角色上次用户消息不超过 60 分钟时免寒暄，跨时段也免；超过间隔再触发。0 表示每天每时段首次。凌晨重复规则优先，由 night_repeat 与 night_interval_minutes 控制，默认开启、0（每个新输入提醒）。所有判断在 BEGIN IMMEDIATE 事务内完成，同角色多会话共用；相同 message 失败重试幂等。未输出正文的请求失败/取消释放自身预留；只删除仍对应本次时间戳的状态，不删除其他并发会话的新记录。已有正文就视为本轮已表达，不再额外请求模型核验内容。

Agent 在最新真实用户消息之后若尚无助手正文，取事件附加到本轮 system；正文一旦保存便撤掉事件，纯工具响应则保留到下一工具轮。实际问候由同次模型回复生成并存入 messages，控制信息不写 messages；不新增一次 API 请求。不能保证任意模型一定遵守自然语言约束。`/compact` 提前返回不触发。

旧 events 不再新增，UI 通过 legacy_greetings.py 只读显示（插件卸载也不丢旧显示）；启用插件时请求仅重放当前上下文范围内旧事件，并保留原消息 ID，避免压缩游标错误。旧固定气泡不分支/导出，新模型寒暄随普通回复分支/导出。旧 sunday_blue/daypart_greetings.py 仅用于已有代码的兼容导入，APP 实际从外置目录加载。

## 6. 旧 JSON 提示词、Skills、MCP

旧 `extensions/plugins/<id>.json` 保持 `{id,prompt}`；不执行代码，角色勾选才注入。每行设置可以编辑该角色的 prompt 覆盖值，默认使用文件内容；取消设置不改变运行配置。单文件导入限制 64 KiB，插件/Skill 总文本限制仍生效。不要与外置目录插件使用同一 id。

Skill 仍仅加载 extensions/skills/<id>/SKILL.md，不执行脚本或自动读附件。MCP 支持本地 stdio tools/list 与 tools/call；启动/调用需确认，进程有系统用户权限，信任工作区不免除 MCP 确认。API/人格提示词不能自行扩大 FileTools 的授权。

## 7. AstrBot 复用边界

本轮仅阅读用户指定本机 AstrBot 的配置规范，参考其 schema 词汇；没有复制其核心源码、插件数据或用户配置，没有运行或连接 AstrBot。Sunday Blue 不是 AstrBot Runtime，现有 AstrBot 插件不能直接把目录复制过来就工作。复用选择：提取插件纯业务逻辑适配以上合同，或今后做独立 AstrBot 服务桥接；原项目及每个插件许可证、依赖、生命周期需单独核对。不得把“参考配置读取方式”写成“兼容整个插件市场”。

### 7b. LivingMemory 专用适配（2026-11-06）

用户要求接入的 LivingMemory 已作为独立插件提供，详见 `docs/LIVINGMEMORY.md`。固定 2.9.1 原版 core/storage/pages，加少量 AstrBot 向量存储；不导入完整 AstrBot。适配层在 vendor 外，来源及技术/UI 差异检查见 upstream-lock.json 与 scripts/livingmemory_upstream.py。不要把该专用适配描述为整个 AstrBot 插件市场兼容。

### 7c. 会话钩子（可选）

```python
def before_turn(root, config, role, sid, user_message):
    return "仅本轮使用的历史背景，或空字符串"

def after_turn(root, config, role, sid, user_message, messages):
    pass  # messages 为该轮落库消息，插件自己过滤文本和工具回执
```

宿主在普通请求开始前调用 before_turn，返回值仅加入当前 system；成功完整回复后调用 after_turn。压缩不触发，失败/截断不写自动记忆。未启用插件不执行。插件异常审计并降级，不阻断普通聊天；不要在异常中暴露密钥。钩子运行在 Agent 工作线程，不得直接修改 UI。

LivingMemory after_turn 只持久入队，后台子进程达到轮数阈值后调用原版处理器。Ollama 必须由用户按钮显式启动；监测、进程启动、插件启用不能隐式启动 Ollama。停用插件不清数据。模型没有自动改写确认记忆或人格的权限。

discover 按清单/schema/入口的 mtime+size 缓存解析结果，仍每次检查文件状态，因此新装、卸载、改参数 schema 可即时发现；入口模块按原 mtime 缓存。后台组件由插件适配层明确负责，不是任意插件自动具备的能力。

## 8. 验证与维护

使用 tests 下临时应用目录安装插件副本，禁止使用真实对话/凭据做自动测试。至少验证发现/卸载、schema 参数持久化与角色隔离、停用不执行、参数真实影响请求、日期边界、免寒暄间隔、失败释放、同消息幂等、工具前后事件撤除、实际回复落库与旧历史兼容。运行 `python -m unittest discover -s tests -v`。更新 README、维护地图、架构与自己的交接后提交。当前不打包；分发源码时必须包含 extensions/plugins 两个目录。
# 角色与按需能力补充（2026-11-09）

角色通过 `roles.list_roles(root)` / `require_role(root, role)` 验证，禁止维护固定 ID 名单。显示名与 ID 分离。插件代码与角色绑定分离，卸载角色不卸载共享插件代码。插件数据若不是已知角色目录/表，角色删除会被阻止，需提供经过测试的清理适配，不能宣称自动清理任意第三方状态。

`capabilities.TurnCapabilities` 在回合内按角色授权过滤 effective config。启用的插件可以配置按需加载；未加载插件不注入说明/工具，也不执行回合钩子。普通模型可调用 `activate_capability` 申请绑定目录中的能力；此调用不授予新权限。新激活插件在工具续接前执行一次 before_turn；after_turn 只在完整成功回复后执行。时间、寒暄属确定性条件服务，启用后每回合可用。已启动的插件独立后台仍遵守原插件生命周期，不等同于工具说明加载策略。新角色默认不继承 default_enabled。

