"""
OpenHarness Desktop 前端 ↔ 后端交互协议 v1
==========================================

基于 OpenHarness 原生 BackendEvent / FrontendRequest / StreamEvent 类型定义，
从 stdin/stdout (OHJSON) 升级为 HTTP + WebSocket。

设计原则:
1. 完整兼容 OpenHarness 原生事件——所有 stream_events 类型 1:1 映射
2. 最小适配层——只做传输升级，不改语义
3. 多会话并发——一个 WebSocket 连接 = 一个 Agent 会话

传输:
- 控制面 (REST):  会话创建/销毁/状态查询 → HTTP
- 数据面 (WS):    实时事件流 + 双向交互     → WebSocket
"""

_PROTO_VERSION = "1"

# ──────────────────────────────────────────────────────
# 前端 → 后端 请求类型 (WebSocket 双向 / HTTP REST)
# 对齐 OpenHarness FrontendRequest
# ──────────────────────────────────────────────────────
WS_REQUEST_TYPES = {
    "session.create",           # 创建新会话
    "session.submit",           # 发送用户消息 (等价 submit_line)
    "session.interrupt",        # 中断当前会话
    "permission.response",      # 审批结果 (等价 permission_response)
    "question.response",        # 问答回复 (等价 question_response)
    "session.list",             # 列出历史会话 (等价 list_sessions)
    "session.resume",           # 恢复历史会话
    "session.shutdown",         # 关闭会话 (等价 shutdown)
    "ping",                     # 心跳
}

# ──────────────────────────────────────────────────────
# 后端 → 前端 事件类型 (WebSocket 推送)
# 对齐 OpenHarness BackendEvent + StreamEvent
# ──────────────────────────────────────────────────────
WS_EVENT_TYPES = {
    # 会话生命周期
    "session.ready",           # 会话初始化完成 (对齐 BackendEvent.ready)
    "session.state_updated",   # 状态变更 (对齐 state_snapshot)
    "session.run_complete",    # 本轮完成 (对齐 line_complete)
    "session.closed",          # 会话已关闭 (对齐 shutdown)
    "session.busy",            # 会话繁忙中

    # Agent 输出 (对齐 AssistantTextDelta / AssistantTurnComplete)
    "assistant.delta",         # 增量文本 (对齐 assistant_delta)
    "assistant.complete",      # 本轮回复完成 (对齐 assistant_complete)

    # 工具执行 (对齐 ToolExecutionStarted / ToolExecutionCompleted)
    "tool.started",            # 工具开始 (对齐 tool_started)
    "tool.completed",          # 工具完成 (对齐 tool_completed)

    # 对话记录 (对齐 transcript_item)
    "transcript.item",         # 消息/工具结果记录项
    "transcript.clear",        # 清空显示 (对齐 clear_transcript)

    # 审批与交互 (对齐 modal_request)
    "approval.request",        # 需要用户审批 (permission)
    "question.request",        # 需要用户回答 (question)
    "select.request",          # 选择请求 (如恢复会话)

    # 状态
    "tasks.updated",           # 任务列表变更 (对齐 tasks_snapshot)

    # 异常
    "error",

    # 心跳
    "pong",

    # OpenHarness 原生未映射事件前缀
    # 格式: openharness.<ClassName>
}
