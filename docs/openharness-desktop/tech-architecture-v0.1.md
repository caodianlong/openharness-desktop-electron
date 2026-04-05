# OpenHarness Desktop Electron 技术架构设计文档（TAD）v0.1

> 文档状态：初版
> 输出日期：2026-04-05
> 依据文档：`prd-v0.2.md`、`srs-v0.1.md`、`2026-04-05-handoff.md`
> 参考方法论：`docs/refs/Coding_Agent_技术架构师.md`、`docs/refs/harness-design-long-running-apps.md`

---

## 1. 架构概览

### 1.1 架构目标

OpenHarness Desktop Electron 的技术架构目标，不是把 OpenHarness CLI 包一层桌面 UI，而是构建一个**可持续运行、可恢复、可审计、可升级的桌面 AI 协作工作台**。

该架构必须同时满足以下产品目标：

1. **长时段协作**：单个会话可持续数小时到数天；
2. **过程可见**：用户能看到消息流、工具调用、审批、产物与错误；
3. **可控自动化**：默认安全，支持 Safe / Balanced / Full Auto；
4. **崩溃可恢复**：UI 或 Host 中断后可回到最近工作现场；
5. **升级可维护**：OpenHarness 升级影响收敛在 Host Adapter，不扩散到 UI 层。

### 1.2 总体架构结论

本系统采用 **Electron Shell + Python Host + Frontend SPA + Local Storage** 的四段式架构：

```text
桌面应用（Electron）
  ├─ Main Process
  │   ├─ 应用生命周期管理
  │   ├─ Host 进程托管
  │   ├─ 单实例控制
  │   ├─ 打包/安装/更新入口
  │   └─ 本地 OS 能力桥接（后续预留）
  │
  ├─ Renderer Process（SPA）
  │   ├─ 会话工作台 UI
  │   ├─ 消息流 / 工具卡片 / 审批 UI
  │   ├─ 输入材料管理
  │   ├─ 产物预览与导出
  │   ├─ 长会话治理视图
  │   └─ 设置 / 诊断 / 恢复入口
  │
  └─ Local Host（Python / FastAPI / WebSocket）
      ├─ HTTP REST 控制面
      ├─ WebSocket 事件流数据面
      ├─ Host Adapter（OpenHarness 适配层）
      ├─ Runtime Session Manager
      ├─ Approval Orchestrator
      ├─ Persistence Service
      └─ Recovery Coordinator

底层执行与存储
  ├─ OpenHarness Runtime（import 集成）
  ├─ SQLite 元数据存储（~/.openharness/desktop.db）
  ├─ JSON 快照（~/.openharness/sessions/...）
  ├─ Artifacts / Logs / Diagnostics 目录
  └─ Workspace 文件系统
```

### 1.3 核心设计原则

#### 原则 A：桌面壳主导产品态，OpenHarness 主导执行态
- 产品中的会话、审批、恢复、导出、预览、设置等状态属于桌面壳；
- Agent 运行、工具调度、行为事件流属于 OpenHarness；
- 两者通过 Host Adapter 解耦。

#### 原则 B：控制面与数据面分离
- **REST** 负责会话 CRUD、健康检查、配置与恢复元信息；
- **WebSocket** 负责流式消息、工具事件、审批请求、状态变更；
- 减少复杂交互对 REST 轮询的依赖。

#### 原则 C：结构化库 + 快照双层存储
- SQLite 负责高频查询、列表、筛选、恢复索引；
- JSON 快照负责兼容兜底与上游演进缓冲；
- 双层存储满足“产品化查询能力 + 长期兼容性”。

#### 原则 D：事件标准化优先于直接暴露底层对象
- 前端只消费稳定事件协议；
- OpenHarness 原始事件先进入 Host Adapter 进行语义归并；
- 避免 UI 与上游内部 Python 对象结构强耦合。

#### 原则 E：长运行系统优先设计恢复与治理
- 所有关键事件落盘；
- 会话与 Run 为一级恢复对象；
- 摘要、折叠、阶段标记和懒加载是架构内建能力，而非后补优化。

### 1.4 约束条件

1. 必须以 `import` 方式集成 OpenHarness，不采用 CLI 包装作为正式架构；
2. Host 与前端同源服务，后端监听 `8789`；
3. 当前后端主模块位于 `apps/host-python/src/host_mvp/`；
4. OpenHarness 源码位于 `vendor/OpenHarness/src`；
5. 数据库存储于 `~/.openharness/desktop.db`；
6. 首期为单窗口桌面工作台；
7. 对标 Claude Cowork / Codex 类产品体验，优先保证持续协作与恢复能力。

### 1.5 关键专家决策

- **[专家决策] 采用 Electron + 本地 Python Host + 前端 SPA 的三段式形态，而不是 Electron 直嵌 Python 或纯 Node Host。**  
  理由：最贴近 Cowork 类桌面 AI 工作台形态；Python Host 能无损复用 OpenHarness 运行时；SPA 保持 UI 高迭代效率。

- **[专家决策] 采用“本地同源 Host 服务”而不是 file:// 静态前端 + 分离 API 服务。**  
  理由：简化打包、健康检查、协议管理和跨域问题，适合单机桌面产品。

- **[专家决策] 采用会话（Conversation）为一级产品对象，Run 为二级执行对象。**  
  理由：符合长时段协作产品心智，也更适合恢复、摘要、审批与产物追踪。

---

## 2. 系统边界与上下文图

### 2.1 系统上下文

```text
[用户]
  ├─ 在桌面工作台中输入任务 / 材料 / 审批决策
  ├─ 查看消息、产物、日志、恢复提示
  └─ 切换权限模式、导出结果

[OpenHarness Desktop Electron]
  ├─ Electron Main
  ├─ Frontend SPA
  ├─ Python Host
  ├─ SQLite / JSON / Artifacts
  └─ Local Diagnostics

[OpenHarness Runtime]
  ├─ Agent 执行
  ├─ Tool 编排
  ├─ 事件流
  ├─ 子任务 / 审批回调
  └─ 运行时上下文

[本地文件系统]
  ├─ Workspace
  ├─ 用户输入文件
  ├─ 输出产物
  ├─ 日志
  └─ 快照

[外部模型 / 工具 / 网络资源]
  ├─ LLM API
  ├─ Web 搜索 / 网页抓取
  ├─ 文件读写与本地执行工具
  └─ 其他 OpenHarness 工具依赖
```

### 2.2 系统边界划分

#### 系统内负责
- 会话管理、消息流渲染、审批、恢复、导出；
- Host 生命周期与健康检查；
- 本地持久化与快照；
- 前后端协议；
- 长会话治理；
- 设置与诊断。

#### 系统外依赖
- OpenHarness Runtime 的具体 Agent 执行能力；
- 模型服务、网络搜索、外部 API；
- 本地文件系统权限；
- 操作系统窗口与安装环境。

### 2.3 关键边界原则

1. UI 不直接调用 OpenHarness Python 对象；
2. OpenHarness 不直接管理产品态数据库；
3. Electron Main 不处理 Agent 业务语义，只负责托管与桌面能力；
4. 所有外部工具访问必须经过权限模式与审批策略。

---

## 3. 架构分层设计

### 3.1 分层总览

```text
L1. 交互表现层（UI Layer）
L2. 应用服务层（Application Service Layer）
L3. Host 适配层（Adapter Layer）
L4. 运行时编排层（Runtime Layer）
L5. 存储与归档层（Persistence Layer）
L6. 基础设施层（Infrastructure Layer）
```

### 3.2 L1：交互表现层（UI Layer）

**职责**：面向用户的工作台体验，负责展示与交互，不承担底层运行时复杂性。

#### 子模块
- 会话侧边栏
- 消息流视图
- 输入区与 slash 补全
- 工具卡片与状态条
- 审批面板 / 队列
- 产物列表与预览器
- 恢复弹窗 / 崩溃摘要
- 设置中心 / 诊断页
- Full Auto 标识与模式切换

#### 设计原则
- UI 仅处理 ViewModel，不持有 OpenHarness 原始对象；
- 所有状态变化通过统一状态仓库驱动；
- 长会话采用分段渲染与折叠加载。

### 3.3 L2：应用服务层（Application Service Layer）

**职责**：承载前端业务编排逻辑，把用户动作转换为稳定的应用行为。

#### 核心服务
- SessionService
- RunService
- ApprovalService
- ArtifactService
- RecoveryService
- SettingsService
- SearchService
- ExportService

#### 主要能力
- REST 调用封装
- WebSocket 连接管理
- 事件归并为 ViewModel
- 本地草稿与短期 UI 状态管理
- 错误提示与重试策略

### 3.4 L3：Host 适配层（Adapter Layer）

**职责**：隔离 UI 协议与 OpenHarness Runtime 差异，统一对外暴露稳定事件集合。

#### 子模块
- Protocol Adapter
- Event Translator
- Permission Adapter
- Session Restore Adapter
- Version Compatibility Adapter

#### 适配策略
- OpenHarness 原生 `StreamEvent` → 标准 WS 事件；
- OpenHarness `permission_prompt` / `ask_user_prompt` → 审批/提问请求；
- 上游新事件进入 `openharness.<ClassName>` 扩展通道，不阻塞主协议；
- 上游属性变更由适配层吸收，例如当前已知 `engine._model` 与 `engine.model` 差异。

### 3.5 L4：运行时编排层（Runtime Layer）

**职责**：管理会话运行状态、执行生命周期、审批阻塞与恢复逻辑。

#### 核心对象
- AgentSession
- SessionManager
- RuntimeBundle
- ApprovalWaiter
- RunCoordinator
- TaskStateCollector

#### 核心能力
- 初始化 / 启动 / 关闭 OpenHarness Runtime；
- 接收用户提交并驱动 `handle_line()`；
- 监听流式事件并持久化；
- 跟踪忙闲状态、停止、中断与恢复；
- 维护运行中的未来对象（Future）以等待审批/问答。

### 3.6 L5：存储与归档层（Persistence Layer）

**职责**：负责结构化存储、快照、产物索引、日志与恢复数据。

#### 组成
- SQLite Repository
- Snapshot Writer
- Artifact Indexer
- Recovery Metadata Store
- Audit Log Store

#### 存储原则
- 高频查询走 SQLite；
- 恢复兜底走 JSON snapshot；
- 产物与日志文件按目录归档；
- 关键写操作事务化。

### 3.7 L6：基础设施层（Infrastructure Layer）

**职责**：系统托管、网络通信、打包分发、操作系统能力。

#### 组成
- Electron Main / Preload
- FastAPI / uvicorn
- WebSocket Server
- 本地文件系统
- Python 运行时 / 虚拟环境
- 安装器与自动更新能力（后续）

---

## 4. 组件设计

## 4.1 Electron Main Process

### 职责
- 应用启动与退出；
- 单实例控制；
- 后台拉起 Python Host；
- 健康检查与故障态反馈；
- 打包后的资源路径管理；
- 后续桥接 OS 级文件选择、系统通知等能力。

### 输入/输出
- 输入：应用启动事件、窗口事件、安装环境配置；
- 输出：Renderer 窗口、Host 子进程、应用生命周期事件。

### 依赖
- Node/Electron Runtime；
- Python Host 可执行入口；
- 打包后的静态资源。

### 设计说明
- **[专家决策]** Main Process 不承担任何 Agent 业务逻辑。  
  理由：避免桌面壳与业务执行耦合，利于测试与替换 Host。

## 4.2 Frontend SPA

### 职责
- 工作台 UI 呈现；
- 用户输入与交互反馈；
- 状态管理与事件渲染；
- 预览器、审批 UI、恢复 UI。

### 关键状态域
- `sessionList`
- `activeSession`
- `messageTimeline`
- `activeRun`
- `approvalQueue`
- `artifacts`
- `connectionState`
- `permissionMode`
- `recoveryBanner`

### 依赖
- REST API
- WebSocket 协议
- 本地文件拖拽/选择能力（经 Electron 或浏览器能力）

## 4.3 API Gateway（FastAPI 控制面）

### 职责
- 暴露健康检查与会话 CRUD；
- 暴露恢复、分叉、重命名等控制操作；
- 未来扩展设置、导出、诊断接口。

### 当前已验证接口
- `GET /api/health`
- `POST /api/sessions`
- `GET /api/sessions`
- `GET /api/sessions/{session_id}`
- `POST /api/sessions/{session_id}/resume`
- `POST /api/sessions/{session_id}/fork`
- `PUT /api/sessions/{session_id}/title`（根据交接文档已存在）
- `DELETE /api/sessions/{session_id}`

### 设计原则
- REST 仅处理控制面，不承载流式执行；
- 返回值保持稳定 JSON 结构；
- 不直接返回底层 Runtime 对象。

## 4.4 WebSocket Event Bridge

### 职责
- 绑定一个 `session_id` 到一个实时事件通道；
- 承载 `session.submit`、审批回复、问答回复、停止与关闭等交互；
- 推送 assistant 增量、工具事件、审批请求、状态变化。

### 设计说明
- 一个 WebSocket 连接 = 一个 Agent 会话；
- 事件以 envelope 结构统一封装：

```json
{
  "type": "assistant.delta",
  "session_id": "abc123",
  "payload": { "text": "..." },
  "timestamp": "2026-04-05T03:00:00Z"
}
```

## 4.5 SessionManager

### 职责
- 管理内存中活跃 AgentSession；
- 提供创建、查找、移除能力；
- 与 SQLite 中的持久会话区分开：前者是**活跃连接态**，后者是**持久业务态**。

### 风险控制
- 活跃 Session 崩溃不应破坏持久数据；
- 断开连接后可基于持久层重建 Runtime。

## 4.6 AgentSession

### 职责
- 封装单会话 Runtime；
- 处理用户提交、事件转发、审批等待、持久化落盘；
- 维护 `busy`、`_msg_seq`、`_permission_futures`、`_question_futures` 等运行状态。

### 关键方法
- `init_runtime(restore_messages)`
- `handle_submit(text)`
- `handle_permission_response(request_id, allowed)`
- `handle_question_response(request_id, answer)`
- `shutdown()`
- `_forward_stream(event)`
- `_push(event_type, payload)`

### 已验证可行项
- OpenHarness 通过 `build_runtime()` / `start_runtime()` / `handle_line()` import 调用可行；
- `AssistantTextDelta` / `ToolExecutionStarted` / `ToolExecutionCompleted` 全链路桥接可行；
- 会话结束时自动生成标题与写入快照已验证。

## 4.7 Host Adapter

### 职责
- 屏蔽上游 OpenHarness 运行时差异；
- 控制对 UI 暴露的事件语义；
- 实现权限模式映射与版本兼容。

### 关键决策
- **[专家决策] Host Adapter 作为独立抽象层保留，即使当前 MVP 仍在 `ws_server.py` 中部分混合实现。**  
  理由：当前验证阶段为了提速可接受，但产品化必须抽出，否则未来 OpenHarness 升级会把风险扩散到接口层和持久层。

## 4.8 Persistence Service

### 职责
- 管理 SQLite schema 与 CRUD；
- 写入消息、会话元数据、快照路径；
- 后续扩展 Run、Approval、Artifact、Summary、AuditEvent 等表。

### 当前已实现
- `sessions` 表
- `messages` 表
- 自动标题生成
- 会话分叉
- 搜索
- OpenHarness JSON snapshot 保存

## 4.9 Recovery Coordinator

### 职责
- 异常退出标记检查；
- 最近会话 / 未完成 Run / 待审批项恢复；
- 快照回放与索引修复；
- 崩溃摘要生成。

### 当前状态
- 基础历史恢复已验证；
- Run 级恢复、待审批恢复、崩溃摘要仍需产品化实现。

## 4.10 Artifact & Preview Subsystem

### 职责
- 归档 Run 输出；
- 建立 artifact 索引与来源链路；
- 支持文本、Markdown、图片、PDF、JSON 预览；
- 导出与“基于此继续”。

### 当前状态
- 属于 TAD 明确设计项；
- 现阶段需在 Host 与 UI 之间补齐元数据结构与索引表。

---

## 5. 核心数据流设计

## 5.1 会话创建数据流

```text
用户点击“新建会话”
  → Frontend 调用 POST /api/sessions
  → Host 创建 sessions 记录（SQLite）
  → 返回 session_id + ws_url
  → Frontend 建立 /ws/{session_id}
  → AgentSession.init_runtime()
  → session.ready
  → UI 切换到新会话可输入态
```

### 关键点
- 会话元数据先落 SQLite，再建立 Runtime；
- WebSocket 就绪后会话才进入真正“可执行”状态；
- 新会话标题初始可为空，首轮执行后自动生成。

## 5.2 消息发送与流式回复数据流

```text
用户输入文本并发送
  → Frontend 发送 WS: session.submit
  → AgentSession.handle_submit(text)
  → save_message(role=user)
  → OpenHarness.handle_line()
  → AssistantTextDelta* N
  → assistant.delta* N
  → AssistantTurnComplete
  → save_message(role=assistant)
  → assistant.complete
  → session.run_complete
  → auto_generate_title()（如标题为空）
  → save_openharness_snapshot()
```

### 关键设计
- 用户消息先入库，再进入 Runtime；
- assistant 增量以 UI 临时态展示，完成后落盘为稳定消息；
- 运行结束后触发快照写入，保证可恢复。

## 5.3 工具执行数据流

```text
OpenHarness ToolExecutionStarted
  → Host Adapter 生成 tool.started
  → UI 创建/更新工具卡片

OpenHarness ToolExecutionCompleted
  → save_message(role=tool_result, tool_name, tool_output)
  → tool.completed
  → UI 更新卡片状态/摘要/错误态
```

### 已验证可行
- 工具卡片折叠展示已验证；
- 工具结果写入 SQLite 已验证；
- assistant / tool 事件混合流式渲染已验证。

## 5.4 审批数据流

```text
OpenHarness 触发 permission_prompt(tool_name, reason)
  → AgentSession._ask_permission()
  → 创建 request_id + Future
  → 推送 approval.request
  → UI 展示审批卡片/审批队列
  → 用户批准/拒绝/作用域授权
  → WS: permission.response
  → Future.set_result()
  → Runtime 继续 / 中断
  → 审计事件落盘
```

### 关键设计
- 审批必须中断运行主线；
- request_id 是恢复与追踪主键；
- MVP 先实现单次决策，后扩展作用域授权与批量处理。

## 5.5 提问交互数据流

```text
OpenHarness ask_user_prompt(question)
  → question.request
  → 用户回答
  → question.response
  → Future.set_result(answer)
  → Runtime 继续执行
```

## 5.6 会话恢复数据流

```text
用户选择历史会话 / 应用启动触发恢复
  → POST /api/sessions/{id}/resume
  → 从 SQLite 读取 meta + messages
  → 构造 restore_messages
  → WebSocket 连接 /ws/{id}
  → AgentSession.init_runtime(restore_messages)
  → Runtime 恢复上下文
  → UI 渲染历史 + 当前有效上下文
```

### 当前与目标差异
- 当前已支持消息级恢复；
- 目标需继续补齐 Run 状态、审批状态、摘要状态与 artifact 索引恢复。

## 5.7 崩溃恢复数据流

```text
应用异常退出
  → 启动时检测异常退出标记
  → 读取最近 session / run / snapshot
  → 展示恢复弹窗
  → 用户选择：继续 / 终止 / 仅查看
  → Recovery Coordinator 执行对应恢复策略
```

### [专家决策]
崩溃恢复默认不自动重放高风险动作，只恢复到“可决策、可继续”的中间态。  
理由：符合 Cowork 类产品的安全预期，避免用户重启应用即自动再次执行危险动作。

## 5.8 “基于产物继续”数据流

```text
用户在预览器/产物列表点击“基于此继续”
  → UI 生成 ContextRef(artifact)
  → 新 Run 输入中带入 artifact 引用
  → Host 记录父子链路
  → Runtime 将 artifact 作为上下文对象
  → 新产物与旧产物建立追溯关系
```

---

## 6. 数据模型设计

## 6.1 存储总体方案

采用“双层持久化”：

1. **SQLite**：产品态结构化数据与高频查询；
2. **JSON 快照**：OpenHarness 原生恢复兜底与版本兼容；
3. **文件归档**：产物、日志、诊断包、预览缓存。

### [专家决策]
不采用单一 JSON 存储，也不采用只依赖 SQLite。  
理由：单 JSON 查询弱、产品化能力差；单 SQLite 对上游结构演进缓冲不足。双层方案最稳妥。

## 6.2 当前已实现 SQLite DDL

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,
    title         TEXT DEFAULT '',
    status        TEXT DEFAULT 'active',
    cwd           TEXT NOT NULL DEFAULT '',
    model         TEXT NOT NULL DEFAULT '',
    message_count INTEGER DEFAULT 0,
    usage_input   INTEGER DEFAULT 0,
    usage_output  INTEGER DEFAULT 0,
    snapshot_path TEXT DEFAULT '',
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role          TEXT NOT NULL,
    content       TEXT NOT NULL DEFAULT '',
    tool_name     TEXT DEFAULT '',
    tool_input    TEXT DEFAULT '',
    tool_output   TEXT DEFAULT '',
    is_error      INTEGER DEFAULT 0,
    seq           INTEGER NOT NULL,
    created_at    REAL NOT NULL
);
```

## 6.3 产品化目标数据模型（建议）

### 6.3.1 conversations（对 sessions 的产品语义扩展）

```sql
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    title_source TEXT NOT NULL DEFAULT 'manual', -- manual/rule/llm/system
    status TEXT NOT NULL DEFAULT 'active',       -- draft/active/archived/deleted
    workspace_path TEXT NOT NULL DEFAULT '',
    permission_mode TEXT NOT NULL DEFAULT 'safe', -- safe/balanced/full_auto
    summary_latest_id TEXT DEFAULT '',
    last_run_id TEXT DEFAULT '',
    last_error_code TEXT DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    archived_at REAL,
    deleted_at REAL
);
```

### 6.3.2 runs

```sql
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    trace_id TEXT NOT NULL,
    parent_run_id TEXT DEFAULT '',
    status TEXT NOT NULL, -- created/running/waiting_approval/completed/failed/stopped/interrupted
    started_at REAL NOT NULL,
    ended_at REAL,
    interruption_reason TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    error_code TEXT DEFAULT '',
    error_message TEXT DEFAULT '',
    snapshot_path TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_runs_conversation_id ON runs(conversation_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_trace_id ON runs(trace_id);
```

### 6.3.3 messages

```sql
CREATE TABLE IF NOT EXISTS messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    run_id TEXT DEFAULT '' REFERENCES runs(run_id) ON DELETE SET NULL,
    role TEXT NOT NULL, -- user/assistant/system/tool/tool_result
    content TEXT NOT NULL DEFAULT '',
    tool_name TEXT DEFAULT '',
    tool_input_json TEXT DEFAULT '',
    tool_output_json TEXT DEFAULT '',
    display_state TEXT NOT NULL DEFAULT 'final', -- streaming/final/folded/error
    is_error INTEGER NOT NULL DEFAULT 0,
    seq INTEGER NOT NULL,
    created_at REAL NOT NULL
);
```

### 6.3.4 approvals

```sql
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    request_type TEXT NOT NULL,      -- permission/question/select
    tool_name TEXT DEFAULT '',
    reason TEXT DEFAULT '',
    scope_type TEXT DEFAULT '',      -- once/conversation/path/tool/full_auto_scope
    scope_value TEXT DEFAULT '',
    status TEXT NOT NULL,            -- pending/approved_once/approved_scoped/rejected/expired/cancelled
    requested_at REAL NOT NULL,
    decided_at REAL,
    decided_by TEXT DEFAULT 'user'
);
CREATE INDEX IF NOT EXISTS idx_approvals_pending ON approvals(status, requested_at DESC);
```

### 6.3.5 artifacts

```sql
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    source_message_id INTEGER,
    parent_artifact_id TEXT DEFAULT '',
    name TEXT NOT NULL,
    artifact_type TEXT NOT NULL,     -- text/markdown/image/pdf/json/code/diff/log/file
    mime_type TEXT DEFAULT '',
    file_path TEXT NOT NULL,
    file_size INTEGER DEFAULT 0,
    preview_status TEXT NOT NULL DEFAULT 'unknown', -- supported/unsupported/error
    export_name TEXT DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_conversation ON artifacts(conversation_id, created_at DESC);
```

### 6.3.6 context_refs

```sql
CREATE TABLE IF NOT EXISTS context_refs (
    ref_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    run_id TEXT DEFAULT '' REFERENCES runs(run_id) ON DELETE SET NULL,
    ref_type TEXT NOT NULL,         -- text/file/url/workspace_path/artifact/summary
    source_value TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    inclusion_state TEXT NOT NULL,  -- attached/included/excluded/missing
    metadata_json TEXT DEFAULT '',
    created_at REAL NOT NULL
);
```

### 6.3.7 summaries

```sql
CREATE TABLE IF NOT EXISTS summaries (
    summary_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    range_start_seq INTEGER NOT NULL,
    range_end_seq INTEGER NOT NULL,
    summary_type TEXT NOT NULL,     -- stage/context/recovery
    content TEXT NOT NULL,
    source_run_id TEXT DEFAULT '',
    created_at REAL NOT NULL
);
```

### 6.3.8 audit_events

```sql
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    conversation_id TEXT DEFAULT '',
    run_id TEXT DEFAULT '',
    event_type TEXT NOT NULL,       -- mode_changed/approval_requested/approval_decided/exported/recovered/error
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit_events(trace_id, created_at ASC);
```

## 6.4 JSON 快照格式

### 当前快照结构（已验证）

```json
{
  "session_id": "abc123",
  "cwd": "/path/to/workspace",
  "model": "deepseek-chat",
  "messages": [],
  "usage": {},
  "created_at": 1760000000,
  "summary": "用户最后一次输入摘要",
  "message_count": 14
}
```

### 目标快照结构（建议）

```json
{
  "snapshot_version": "1.0",
  "conversation": {
    "conversation_id": "conv_xxx",
    "title": "检查磁盘空间",
    "workspace_path": "/workspace",
    "permission_mode": "balanced"
  },
  "run": {
    "run_id": "run_xxx",
    "trace_id": "trace_xxx",
    "status": "interrupted",
    "started_at": 1760000000,
    "ended_at": null
  },
  "messages": [],
  "approvals_pending": [],
  "context_refs": [],
  "artifacts": [],
  "summary": {
    "current_effective_context": "...",
    "stage_summary": "..."
  },
  "runtime_metadata": {
    "model": "deepseek-chat",
    "usage": {},
    "openharness_version": "x.y.z"
  }
}
```

## 6.5 文件归档结构建议

```text
~/.openharness/
  ├─ desktop.db
  ├─ sessions/
  │   └─ <project>-<hash>/session-<id>.json
  ├─ artifacts/
  │   └─ <conversation_id>/<run_id>/...
  ├─ logs/
  │   ├─ host/
  │   ├─ ui/
  │   └─ runtime/
  ├─ diagnostics/
  └─ recovery/
```

---

## 7. 接口契约设计

## 7.1 设计原则

1. REST 负责控制面；
2. WS 负责数据面；
3. Envelope 结构统一；
4. 协议版本化；
5. 允许扩展字段，保证向后兼容。

## 7.2 REST API 定义

### 7.2.1 健康检查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | Host 健康检查 |

**响应**

```json
{
  "service": "openharness-desktop-host",
  "version": "0.3.0",
  "protocol": "http+websocket",
  "protocol_version": "1",
  "active_sessions": 1
}
```

### 7.2.2 创建会话

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/sessions` | 创建新会话 |

**请求**

```json
{
  "cwd": "/workspace",
  "model": "deepseek-chat",
  "title": ""
}
```

**响应**

```json
{
  "session_id": "abc123",
  "ws_url": "/ws/abc123"
}
```

### 7.2.3 列出会话

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/sessions?limit=50` | 会话列表 |

### 7.2.4 获取会话详情

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/sessions/{session_id}` | 获取会话与消息 |

### 7.2.5 恢复会话

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/sessions/{session_id}/resume` | 恢复会话 |

### 7.2.6 分叉会话

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/sessions/{session_id}/fork` | 复制历史会话为新会话 |

### 7.2.7 重命名会话

| 方法 | 路径 | 说明 |
|---|---|---|
| PUT | `/api/sessions/{session_id}/title` | 修改标题 |

### 7.2.8 删除会话

| 方法 | 路径 | 说明 |
|---|---|---|
| DELETE | `/api/sessions/{session_id}` | 删除/归档（MVP 可先实现删除） |

## 7.3 WebSocket 请求契约

### 请求类型

```text
session.create
session.submit
session.interrupt
permission.response
question.response
session.list
session.resume
session.shutdown
ping
```

### 示例：发送用户消息

```json
{
  "type": "session.submit",
  "payload": {
    "text": "帮我搜索 gemma 4 的资讯"
  }
}
```

### 示例：审批响应

```json
{
  "type": "permission.response",
  "payload": {
    "request_id": "req_xxx",
    "allowed": true
  }
}
```

## 7.4 WebSocket 事件契约

### 标准事件

| 事件 | 说明 |
|---|---|
| `session.ready` | 会话就绪 |
| `session.state_updated` | 状态快照更新 |
| `session.run_complete` | 当前 run 完成 |
| `session.closed` | 会话关闭 |
| `session.busy` | 会话忙碌 |
| `assistant.delta` | 助手增量输出 |
| `assistant.complete` | 助手回答完成 |
| `tool.started` | 工具开始 |
| `tool.completed` | 工具完成 |
| `transcript.item` | 对话记录项 |
| `transcript.clear` | 清理临时输出 |
| `approval.request` | 审批请求 |
| `question.request` | 追问请求 |
| `select.request` | 选择请求 |
| `tasks.updated` | 任务快照更新 |
| `error` | 异常 |
| `pong` | 心跳回应 |
| `openharness.<ClassName>` | 未映射扩展事件 |

### 示例：assistant.delta

```json
{
  "type": "assistant.delta",
  "session_id": "abc123",
  "payload": {
    "text": "Gemma 4 是..."
  },
  "timestamp": "2026-04-05T02:00:00Z"
}
```

### 示例：tool.completed

```json
{
  "type": "tool.completed",
  "session_id": "abc123",
  "payload": {
    "tool_name": "web_search",
    "output": "...",
    "is_error": false
  },
  "timestamp": "2026-04-05T02:00:01Z"
}
```

## 7.5 内部模块 API 契约

### 7.5.1 Session Repository

```python
create_session(session_id: str, cwd: str = '', model: str = '', title: str = '') -> SessionMeta
get_session(session_id: str) -> SessionMeta | None
list_sessions(limit: int = 50, offset: int = 0) -> list[SessionMeta]
update_session(session_id: str, **fields) -> SessionMeta | None
delete_session(session_id: str) -> bool
search_sessions(query: str, limit: int = 20) -> list[SessionMeta]
```

### 7.5.2 Message Repository

```python
save_message(msg: MessageRecord) -> int
get_messages(session_id: str, limit: int | None = None) -> list[MessageRecord]
increment_message_count(session_id: str) -> None
```

### 7.5.3 Snapshot Service

```python
save_openharness_snapshot(
    session_id: str,
    cwd: str,
    model: str,
    messages: list[dict],
    summary: str = '',
    usage: dict | None = None,
) -> str
```

### 7.5.4 标题生成

```python
generate_title_from_text(text: str, max_len: int = 28) -> str
auto_generate_title(session_id: str) -> str | None
```

## 7.6 协议兼容策略

- 协议头保留 `protocol_version`；
- 新字段追加不删除旧字段；
- 新事件优先进入扩展命名空间；
- UI 以容错方式忽略未知字段；
- Host Adapter 负责上游事件到标准协议的映射升级。

---

## 8. 错误处理策略

## 8.1 错误分层

### 层 1：UI 交互错误
示例：空输入、文件不存在、预览失败、导出路径不可写。

**策略**：
- 就地提示；
- 保留用户输入；
- 提供重试或替代动作。

### 层 2：连接与协议错误
示例：WebSocket 断开、REST 超时、消息乱序、协议不兼容。

**策略**：
- 自动重连；
- 进入 Degraded 状态；
- 提示用户恢复或重试；
- 所有事件 envelope 带时间戳和 session_id 以便纠偏。

### 层 3：Host 运行错误
示例：Runtime 初始化失败、build_runtime 异常、OpenHarness 事件异常。

**策略**：
- 记录 host 日志；
- 当前 Run 标记 failed/interrupted；
- 不拖死 UI；
- 提供重试或查看诊断。

### 层 4：外部依赖错误
示例：模型超时、网络错误、工具执行失败。

**策略**：
- 工具卡片显式标红；
- 保留失败上下文；
- 提供继续执行或切回人工控制。

### 层 5：持久化错误
示例：SQLite 写失败、快照写失败、磁盘空间不足。

**策略**：
- 关键链路优先 SQLite；
- 快照写失败不阻塞主流程，但记入 audit；
- SQLite 写失败则 Run 不可宣称成功。

## 8.2 超时策略

| 场景 | 超时策略 |
|---|---|
| Host 启动 | >4s 显示启动慢提示，>10s 显示失败可重试 |
| WebSocket 连接 | 断线立即转 Degraded，后台重连 |
| 审批等待 | 长时间等待保持 `waiting_approval`，支持取消 |
| 工具执行 | 由 OpenHarness / 工具层处理；UI 展示等待态 |
| 导出 | 超时后提示用户检查目标目录 |

## 8.3 崩溃处理策略

### UI 崩溃
- 重启 Renderer；
- 从 SQLite 恢复会话与最近消息；
- 若 Host 仍存活则重新连回当前 Session。

### Host 崩溃
- UI 转为故障态；
- 提示“恢复会话 / 查看日志 / 重新启动 Host”；
- 不自动丢弃会话。

### 存储损坏
- 优先尝试 SQLite 修复或只读打开；
- 如失败则回退 JSON snapshot 重建索引；
- 输出诊断报告。

## 8.4 重试策略

- 连接类：指数退避 1s / 2s / 5s；
- 非幂等高风险操作：不自动重试；
- 预览/导出类：允许用户主动重试；
- 审批类：请求重试必须保持 request_id 不变或可追踪映射。

### [专家决策]
对于会改变外部世界状态的动作，不进行隐式自动重试。  
理由：桌面 AI 助手比 Web App 更接近“执行代理”，重复写文件/重复发请求的成本更高。

---

## 9. 性能设计

## 9.1 性能目标

| 指标 | 目标 |
|---|---|
| 冷启动进入主界面 | ≤ 2.5 秒 |
| Host ready | ≤ 4 秒 |
| 会话切换 | ≤ 200ms |
| 新建会话到可发送 | ≤ 1 秒 |
| 审批 UI 响应 | ≤ 300ms |
| 大会话首屏渲染 | ≤ 800ms |

## 9.2 冷启动优化

### 方案
1. Electron Main 与 Host 并行初始化；
2. 首屏 skeleton 先出，不等待全部历史加载；
3. 默认只加载最近会话列表元信息；
4. OpenHarness 路径与环境变量预热；
5. Python Host 使用常驻本地服务方式，不在首屏做重量级模型握手。

### [专家决策]
启动流程采用“主界面先可见，输入区按 Host ready 解锁”的策略。  
理由：更贴近 Cowork 类产品感受，减少黑屏等待。

## 9.3 会话切换优化

- 会话列表仅取摘要字段；
- 消息采用分页/窗口化渲染；
- 最近活跃会话保留内存缓存；
- 切换时优先展示 SQLite 中稳定消息，再补齐扩展数据。

## 9.4 大会话渲染优化

- 虚拟列表；
- 工具卡片默认折叠；
- 摘要节点代替远古历史直接渲染；
- 按阶段懒加载；
- 预览器与主消息流分区渲染。

## 9.5 数据访问优化

- SQLite 启用 WAL（当前已实现）；
- 高频索引：会话更新时间、消息 seq、run trace_id；
- 搜索优先标题 + 最近消息摘要；
- 大字段（日志、结构化 tool_output）必要时外置文件索引化。

## 9.6 运行态优化

- 一个活跃会话仅允许一个前台 Run，降低并发混乱；
- 助手增量只更新当前消息节点，避免全量 rerender；
- 工具结果完成后再入库，开始态只走内存状态；
- Host 保持热启动，避免频繁 build_runtime。

---

## 10. 安全设计

## 10.1 安全目标

1. 默认安全，不默认 Full Auto；
2. 对敏感动作显式审批；
3. 审批与模式切换可审计；
4. 访问范围可控；
5. 本地数据不隐式外传。

## 10.2 权限模式设计

### Safe
- 中高风险动作全部审批；
- 适合普通用户。

### Balanced
- 常规读操作自动执行；
- 中风险动作按规则审批；
- 适合日常高频使用。

### Full Auto
- 大部分动作自动执行；
- 顶部常驻高风险标识；
- 可随时降级回审批模式。

### [专家决策]
MVP 中 Host 内部权限模式仍可先以 OpenHarness `FULL_AUTO` 跑通验证链路，但产品层必须在适配层与 UI 层实现独立权限编排。  
理由：当前技术验证以通链路为主；正式产品不能把 OpenHarness 内部模式直接等同于用户可见权限模型。

## 10.3 审批模型

- 审批对象：文件写入、系统执行、危险操作、外部不可逆动作；
- 审批粒度：一次批准 / 作用域授权 / 拒绝；
- 审批记录落 `approvals` + `audit_events`；
- 审批恢复后必须可重新查看。

## 10.4 文件访问控制

- 工作区路径显式展示；
- 文件/目录引用必须用户可见；
- 超大范围目录引用需确认；
- 不允许悄悄扩大作用域。

## 10.5 审计与追踪

- 每个 Run 生成 trace_id；
- 模式切换、审批、导出、恢复都记录审计事件；
- 诊断包导出前做敏感字段脱敏。

## 10.6 本地数据安全

- SQLite、logs、artifacts 均存本地用户可控目录；
- 不引入默认云同步；
- 离线状态只允许本地可完成动作，不伪装联网执行成功。

---

## 11. 部署与打包设计

## 11.1 部署形态

MVP 部署目标：**单机桌面安装包**。

```text
安装包
  ├─ Electron App
  ├─ 前端静态资源
  ├─ Python Runtime / venv 或内嵌解释器
  ├─ Host 启动脚本
  ├─ OpenHarness vendor 代码
  └─ 默认配置模板
```

## 11.2 启动流程

```text
用户双击桌面应用
  → Electron Main 启动
  → 拉起 Python Host（本地 127.0.0.1:8789）
  → Host 挂载前端静态资源 / API / WS
  → Renderer 加载本地同源页面
  → /api/health 检查
  → Host ready
```

## 11.3 打包方案

### Electron 打包
- 使用 Electron Builder 或等价方案；
- 打包前端静态资源与 Main/Preload；
- 平台产物：macOS dmg/pkg、Windows nsis/msi、Linux AppImage/deb。

### Python 打包
- 方案 A：随应用内嵌 Python 解释器 + venv；
- 方案 B：使用 PyInstaller/Briefcase 打包 Host 为独立二进制；
- **[专家决策] MVP 优先采用内嵌 Python Runtime + 受控 venv。**  
  理由：对 OpenHarness import 集成最稳、调试成本最低，适合验证期到首发过渡。

## 11.4 一键安装要求

- 用户无需手工安装 Python；
- 首次运行自动初始化数据目录；
- 初始化完成后主界面可直接打开；
- 应用退出时回收 Host 进程。

## 11.5 环境配置

当前已知环境需求：
- `.venv/bin/python3` 运行 Host；
- `OPENHARNESS_CONFIG_DIR` / `OPENHARNESS_DATA_DIR` 指向应用可控目录；
- `DEEPSEEK_*` 环境变量映射到 `OPENHARNESS_*`；
- `vendor/OpenHarness/src` 需加入 `sys.path`。

---

## 12. 升级与兼容性设计

## 12.1 升级目标

- OpenHarness 小版本升级不要求 UI 重构；
- 快照与数据库可迁移；
- 升级失败可回退；
- 新事件类型不会破坏旧 UI。

## 12.2 兼容分层

### UI 层
- 只依赖稳定协议；
- 忽略未知字段；
- 新功能通过 feature flag 控制。

### Host Adapter 层
- 负责适配 OpenHarness 新旧事件；
- 负责内部属性兼容，如模型字段、usage 字段、runtime API 差异；
- 负责快照版本识别。

### 存储层
- 数据库采用 schema version 管理；
- JSON snapshot 带 `snapshot_version`；
- 若新版本字段缺失，按默认值回填。

## 12.3 升级流程建议

```text
检测到新版本
  → 下载/替换应用包或 Host 包
  → 备份 desktop.db + snapshots
  → 执行 schema migration
  → 启动兼容检查
  → 成功：切换新版本
  → 失败：回退到上个可用版本
```

## 12.4 版本兼容策略

- 协议版本号与应用版本分离；
- 数据 schema migration 独立管理；
- OpenHarness 版本写入诊断信息与快照；
- 扩展事件命名空间保证未识别事件可旁路处理。

### [专家决策]
优先保证“旧会话可恢复、主路径可运行”，次优先保证“新能力完全可见”。  
理由：桌面长会话产品的核心资产是历史与连续性，不是每次升级都暴露全部新事件细节。

---

## 13. 技术选型理由

## 13.1 Electron

### 选择理由
- 最成熟的跨平台桌面壳方案；
- 能提供 Claude Cowork / Codex 类单窗口工作台体验；
- 易于打包前端 SPA 与本地宿主；
- 后续扩展系统通知、文件选择、剪贴板、协议注册方便。

### 不选原生桌面框架原因
- 迭代速度慢；
- 前端工作台 UI 与预览器生态弱；
- 不利于快速复刻 Cowork 体验。

## 13.2 Python + FastAPI + WebSocket

### 选择理由
- OpenHarness 本身为 Python 生态，import 集成成本最低；
- FastAPI 开发效率高，适合桌面本地服务；
- WebSocket 适合流式输出、工具事件、审批阻塞这类长连接场景；
- 当前技术验证已证明可行。

### 不选 Node Host 原因
- 将增加 OpenHarness 适配复杂度；
- 需要跨语言桥接核心运行时；
- 失去 import 直连能力。

## 13.3 SQLite

### 选择理由
- 单机桌面产品首选；
- 无外部服务依赖；
- 支持事务、索引、搜索、恢复；
- 当前已验证可行。

### 不选纯文件 DB 原因
- 查询、筛选、恢复、列表性能与一致性不足；
- 难以支撑产品化会话管理。

## 13.4 JSON 快照

### 选择理由
- 可保留 OpenHarness 原生语义；
- 兼容性兜底；
- 便于手工诊断和版本过渡。

## 13.5 Frontend SPA

### 选择理由
- 适合构建高交互工作台；
- 组件化实现消息流、审批、预览器、侧边栏；
- 后续支持虚拟列表、状态管理、长会话治理能力。

## 13.6 长运行应用方法论吸收

来自 `harness-design-long-running-apps.md` 的架构启示已明确吸收进本设计：

1. **上下文治理重于单轮对话**：本产品以会话+摘要+恢复为核心，而非只做聊天；
2. **结构化 handoff artifact 是长期运行系统基础设施**：本设计采用 SQLite + JSON snapshot；
3. **执行与评估/控制分离**：OpenHarness 负责执行，桌面壳负责审批、诊断、恢复与产品态；
4. **复杂任务要靠分层和工件化而不是堆上下文**：阶段摘要、折叠、artifact 链路是产品内建能力。

---

## 14. 已验证可行项与落地映射

| 设计项 | 状态 | 说明 |
|---|---|---|
| FastAPI + WebSocket 同源服务 | 已验证可行 | 后端可同时提供 REST/WS 与前端资源 |
| 前端 SPA 工作台 | 已验证可行 | 深色主题、侧边栏、聊天区、输入区已跑通 |
| 会话 CRUD + 搜索 + 自动标题 | 已验证可行 | SQLite 主链路已实现 |
| WebSocket 流式消息 | 已验证可行 | assistant.delta / complete 已验证 |
| 工具执行卡片折叠 | 已验证可行 | tool.started / tool.completed 已验证 |
| slash 命令补全 | 已验证可行 | 50+ 命令可补全 |
| SQLite 持久化 + 历史恢复 | 已验证可行 | 2 条会话、14 条消息验证通过 |
| OpenHarness import 调用 | 已验证可行 | 非 CLI 集成已跑通 |
| 双层存储（SQLite + JSON） | 已验证可行 | 快照与结构化库同时存在 |
| Run 级恢复 | 部分可行，待补齐 | 当前主要为消息级恢复 |
| 审批 UI 与审批持久化 | 架构已定，待产品化 | 技术回调机制已具备 |
| Artifact 索引 / 预览器 / 导出 | 架构已定，待实现 | MVP 必补 |
| 长会话摘要与阶段治理 | 架构已定，待实现 | 对标 Cowork 的关键能力 |

---

## 15. 研发落地建议

## 15.1 第一阶段：Host 产品化重构

目标：把验证版 `ws_server.py` 中混合的职责拆成清晰模块。

建议拆分：
- `api/health.py`
- `api/sessions.py`
- `runtime/agent_session.py`
- `runtime/session_manager.py`
- `adapter/event_mapper.py`
- `adapter/permission_adapter.py`
- `storage/repositories/*.py`
- `recovery/coordinator.py`

## 15.2 第二阶段：补齐 MVP 主路径闭环

优先实现：
1. Approval 持久化与审批队列；
2. Artifact 索引与基础预览器；
3. Recovery Coordinator；
4. 设置中心与权限模式产品化；
5. 导出与诊断包。

## 15.3 第三阶段：长会话治理

优先实现：
1. 阶段摘要；
2. 历史折叠；
3. 分段渲染；
4. “基于此继续”；
5. 大会话性能优化。

## 15.4 第四阶段：桌面壳打包与升级体系

优先实现：
1. Electron Main 托管 Host；
2. 单实例；
3. 打包后的内嵌 Python 方案；
4. 日志路径与 crash dump；
5. 版本检查与回退机制。

---

## 16. 结论

OpenHarness Desktop Electron 的正确技术路线，不是“桌面聊天壳 + Agent 后端”，而是：

- **Electron 提供桌面产品壳与生命周期托管**；
- **Python Host 提供本地同源 API/WS 服务**；
- **Host Adapter 隔离 OpenHarness 升级影响**；
- **SQLite + JSON 快照构成可恢复、可查询、可兼容的持久化体系**；
- **会话、Run、审批、产物、摘要、恢复共同构成长时段协作工作台**。

这套架构与当前技术验证结果一致，也与 Claude Cowork 类产品的已知架构模式高度贴合，能够作为 OpenHarness Desktop Electron MVP 到 Beta/1.0 的稳定实现基线。
