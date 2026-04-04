# 工程实施方案 v0.1

## 1. 推荐 Monorepo 结构

```text
openharness-desktop/
  apps/
    desktop/          # Electron + React
    host-python/      # Python Headless Host
  packages/
    ui/               # 组件库
    shared-types/     # TS 类型
    protocol/         # IPC/RPC 协议定义
    db/               # SQLite schema / migration
    previewers/       # 预览器
    logging/          # 日志/trace
    config/           # 配置与 feature flags
  docs/
    prd/
    architecture/
    adr/
    api/
  tests/
    e2e/
    integration/
  tooling/
    build/
    scripts/
    ci/
  resources/
    icons/
    templates/
```

## 2. 模块拆分

| 模块 | 职责 |
|---|---|
| desktop-shell | 窗口、菜单、托盘、Host 托管 |
| renderer-app | 页面、状态管理、路由、交互 |
| host-runtime | OpenHarness 适配、服务 API、事件桥接 |
| shared-protocol | 前后端协议、事件定义、状态枚举 |
| persistence | DB schema、migration、repository |
| artifact-service | 归档、hash、预览元数据 |
| approval-service | 审批规则、挂起、恢复 |
| recovery-service | 崩溃检测、快照、恢复编排 |
| diagnostics | 日志、trace、诊断导出 |
| settings-service | 设置与策略合成 |

## 3. 关键接口列表

### 3.1 HTTP API

#### Conversation
- `POST /conversations`
- `GET /conversations`
- `GET /conversations/:id`
- `PATCH /conversations/:id`
- `POST /conversations/:id/archive`
- `DELETE /conversations/:id`

#### Message
- `GET /conversations/:id/messages`
- `POST /conversations/:id/messages`

#### Run
- `POST /conversations/:id/runs`
- `GET /runs/:id`
- `POST /runs/:id/cancel`
- `POST /runs/:id/retry`

#### Approval
- `GET /approvals/pending`
- `POST /approvals/:id/approve`
- `POST /approvals/:id/reject`
- `POST /approvals/:id/approve-scope`

#### Artifact
- `GET /runs/:id/artifacts`
- `GET /artifacts/:id/meta`
- `GET /artifacts/:id/content`

#### Workspace
- `GET /workspaces`
- `POST /workspaces`
- `PATCH /workspaces/:id`

#### Settings
- `GET /settings`
- `PATCH /settings`

#### Diagnostics
- `GET /health`
- `GET /version`
- `POST /diagnostics/export`

### 3.2 WebSocket Events
- `host.ready`
- `host.degraded`
- `conversation.updated`
- `message.created`
- `run.created`
- `run.updated`
- `run.completed`
- `run.failed`
- `task.updated`
- `approval.requested`
- `approval.resolved`
- `artifact.created`
- `trace.span`
- `log.appended`
- `recovery.suggested`

## 4. 事件协议草案

### 4.1 统一事件信封
```json
{
  "event_id": "evt_123",
  "event_type": "run.updated",
  "timestamp": "2026-04-04T21:00:00+08:00",
  "trace_id": "tr_001",
  "conversation_id": "conv_001",
  "run_id": "run_001",
  "payload": {},
  "version": "1"
}
```

### 4.2 原则
- 每个事件必须幂等
- 关键事件必须带 `trace_id`
- UI 能够基于 event log 重建状态
- 事件协议版本独立于 OpenHarness 版本

## 5. SQLite 表设计草案

### conversations
- id
- title
- workspace_id
- status
- mode
- created_at
- updated_at
- archived_at
- last_run_id

### messages
- id
- conversation_id
- role
- content_text
- content_json
- seq
- created_at
- external_ref

### runs
- id
- conversation_id
- status
- trigger_type
- started_at
- ended_at
- error_code
- error_message
- external_ref
- trace_id
- mode_snapshot_json

### tasks
- id
- run_id
- parent_task_id
- title
- status
- kind
- progress
- created_at
- updated_at
- external_ref

### agent_instances
- id
- run_id
- parent_agent_id
- role
- status
- created_at
- ended_at
- external_ref

### approval_requests
- id
- run_id
- action_type
- scope_type
- payload_json
- status
- created_at
- resolved_at
- decision_json

### artifacts
- id
- run_id
- type
- title
- file_path
- mime_type
- size
- sha256
- preview_status
- created_at
- external_ref

### workspaces
- id
- name
- root_path
- policy_json
- created_at
- updated_at

### event_logs
- id
- trace_id
- event_type
- payload_json
- created_at

### trace_spans
- id
- trace_id
- span_type
- parent_span_id
- started_at
- ended_at
- status
- meta_json

### settings
- key
- value_json
- updated_at

### host_sessions
- id
- host_pid
- started_at
- ended_at
- crash_flag
- restore_snapshot_path

## 6. 日志 / Trace / Artifact 设计

### 日志分层
1. App Log
2. Host Log
3. Run Log
4. Diagnostic Bundle

### Trace 设计
- 每次 run 生成一个 `trace_id`
- 工具调用、审批、artifact、错误都挂 trace
- 关键节点写入 `trace_spans`

### Artifact 类型
- text
- markdown
- image
- pdf
- code
- diff
- json
- binary
- report

## 7. 崩溃恢复方案

### 检测
- Main 检测 Host 退出码
- Host 启动时检查上次 crash flag
- DB 中标记未完成 run

### 恢复流程
1. 启动时读 `host_sessions`
2. 查找未结束的 run
3. 读取最近 snapshot / event logs
4. UI 提示是否恢复
5. 支持继续 / 终止 / 查看日志

### 恢复原则
- 优先恢复“可见状态”
- 不承诺恢复底层执行现场 100% 连续
- 先保证用户知道发生了什么、能继续工作

## 8. 错误处理策略

### 错误分级
- L1 用户可恢复
- L2 系统需重试
- L3 致命错误

### 策略
- 所有错误标准化成统一错误对象
- UI 只展示产品可理解错误
- 内部细节进入日志和诊断包
- 致命错误支持一键导出诊断

## 9. 性能与响应优化

### 前端
- 长列表虚拟滚动
- 会话历史分页
- 预览懒加载
- trace 面板按需展开

### Host
- 事件批量推送
- 大 artifact 只传 meta，不传全文
- 长日志分段读取
- 重计算任务异步化

### 存储
- SQLite 索引：conversation_id、run_id、created_at、trace_id
- 日志与 artifact 分文件归档
