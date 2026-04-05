"""
OpenHarness Desktop Host — HTTP + WebSocket 协议服务 v0.3.0
============================================================

基于 OpenHarness 原生事件定义，将 stdin/stdout 升级为 HTTP + WebSocket。
新增 SQLite 会话存储层（元数据 + 消息），同时并行保存 OpenHarness 原生 JSON 快照。
"""

from __future__ import annotations

# ─── 必须在所有 OpenHarness 导入之前执行 ───────────────
from pathlib import Path
import os
import sys
import time

_PROTO_VERSION = "1"

def _setup_openharness_path():
    repo_root = Path(__file__).resolve().parents[4]
    vendor_src = repo_root / "vendor" / "OpenHarness" / "src"
    if vendor_src.exists():
        src = str(vendor_src)
        if src not in sys.path:
            sys.path.insert(0, src)

    config_dir = repo_root / ".tmp" / "openharness-config"
    data_dir = repo_root / ".tmp" / "openharness-data"
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("OPENHARNESS_CONFIG_DIR", str(config_dir))
    os.environ.setdefault("OPENHARNESS_DATA_DIR", str(data_dir))

def _apply_env_aliases():
    base = os.environ.get("DEEPSEEK_BASE_URL")
    key = os.environ.get("DEEPSEEK_API_KEY")
    if base and key:
        os.environ.setdefault("OPENHARNESS_API_FORMAT", "openai")
        os.environ.setdefault("OPENHARNESS_BASE_URL", base)
        os.environ.setdefault("OPENAI_API_KEY", key)

_setup_openharness_path()

# ─── stdlib ─────────────────────────────────────────────
import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from dataclasses import asdict
from uuid import uuid4

# ─── 3rd party ──────────────────────────────────────────
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# ─── 内部模块 ───────────────────────────────────────────
from . import session_store
from .session_store import (
    ApprovalRecord,
    create_artifact,
    create_session as db_create_session,
    create_approval as db_create_approval,
    get_artifact as db_get_artifact,
    get_session as db_get_session,
    list_sessions as db_list_sessions,
    list_artifacts as db_list_artifacts,
    list_approvals as db_list_approvals,
    save_message,
    get_messages as db_get_messages,
    update_session as db_update_session,
    update_approval_status as db_update_approval_status,
    delete_session as db_delete_session,
    fork_session as db_fork_session,
    increment_message_count,
    auto_generate_title,
    MessageRecord,
)

# ─── OpenHarness 原生 ───────────────────────────────────
from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from openharness.ui.runtime import build_runtime, close_runtime, handle_line, start_runtime
from openharness.tasks import get_task_manager
from openharness.permissions.modes import PermissionMode
from openharness.config.settings import load_settings, save_settings

# ───────────────────────────────────────────────────────
app = FastAPI(title="OpenHarness Desktop Host", version="0.3.0")
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

# 静态文件目录（预留给未来拆分 CSS/JS 资源）
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ═══════════════════════════════════════════════════════
# Agent 会话
# ═══════════════════════════════════════════════════════

class AgentSession:
    """一个 Agent 会话 = 一个 OpenHarness Runtime + 一个 WebSocket 连接."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.bundle = None
        self.busy = False
        self._closed = False
        self._msg_seq = 0  # 消息序号
        self._permission_futures: dict[str, asyncio.Future[bool]] = {}
        self._question_futures: dict[str, asyncio.Future[str]] = {}
        self.ws: WebSocket | None = None

        # SQLite 持久化 ID（可以与 session_id 相同或不同）
        self._db_session_id: str = session_id
        self.permission_mode: str = "full_auto"

    async def init_runtime(self, *, restore_messages: list[dict] | None = None, permission_mode: str = "full_auto"):
        """初始化 OpenHarness 运行时，可选恢复历史消息和权限模式。"""
        self.permission_mode = permission_mode
        _apply_env_aliases()

        # 确保 SQLite 会话记录存在
        meta = db_get_session(self._db_session_id)
        if not meta:
            db_create_session(
                self._db_session_id,
                cwd=os.getcwd(),
                model=os.environ.get("OPENHARNESS_MODEL") or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat",
            )

        model = meta.model if meta else (os.environ.get("OPENHARNESS_MODEL") or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat")
        perm = getattr(meta, 'permission_mode', None) or self.permission_mode

        settings = load_settings()
        settings.api_format = "openai"
        settings.model = model
        settings.max_tokens = 4096
        mode_map = {"safe": PermissionMode.DEFAULT, "balanced": PermissionMode.DEFAULT, "full_auto": PermissionMode.FULL_AUTO}
        settings.permission.mode = mode_map.get(perm, PermissionMode.FULL_AUTO)
        save_settings(settings)

        self.bundle = await build_runtime(
            api_format="openai",
            model=model,
            permission_prompt=self._ask_permission,
            ask_user_prompt=self._ask_question,
            restore_messages=restore_messages,
        )
        await start_runtime(self.bundle)

        # 如果有恢复消息，更新消息序号
        if restore_messages:
            self._msg_seq = len(restore_messages)

    async def handle_submit(self, text: str):
        """处理用户消息."""
        if self.busy:
            await self._push("session.busy", {"message": "Session is busy"})
            return
        if not self.bundle:
            await self._push("error", {"message": "Session not initialized"})
            return

        self.busy = True
        try:
            # 用户消息 → WebSocket
            await self._push("transcript.item", {"role": "user", "text": text})

            # 用户消息 → SQLite
            save_message(MessageRecord(
                session_id=self._db_session_id,
                role="user",
                content=text,
                seq=self._msg_seq,
                created_at=time.time(),
            ))
            self._msg_seq += 1

            async def _print_system(msg: str):
                await self._push("transcript.item", {"role": "system", "text": msg})
                save_message(MessageRecord(
                    session_id=self._db_session_id,
                    role="system",
                    content=msg,
                    seq=self._msg_seq,
                    created_at=time.time(),
                ))
                self._msg_seq += 1
                increment_message_count(self._db_session_id)

            async def _render_event(event: StreamEvent):
                await self._forward_stream(event)

            async def _clear_output():
                await self._push("transcript.clear", {})

            await handle_line(
                self.bundle,
                text,
                print_system=_print_system,
                render_event=_render_event,
                clear_output=_clear_output,
            )

            # 保存 OpenHarness 原生 JSON 快照
            if self.bundle and self.bundle.engine:
                try:
                    messages_raw = [
                        m.model_dump(mode="json")
                        for m in self.bundle.engine.messages
                    ]
                    summary = text[:80] if text else ""
                    usage = self.bundle.engine.total_usage.model_dump() if hasattr(self.bundle.engine.total_usage, 'model_dump') else {}
                    session_store.save_openharness_snapshot(
                        session_id=self._db_session_id,
                        cwd=self.bundle.cwd,
                        model=self.bundle.engine._model if hasattr(self.bundle.engine, '_model') else "unknown",
                        messages=messages_raw,
                        summary=summary,
                        usage=usage,
                    )
                except Exception:
                    pass  # 快照失败不影响主流程

            await self._push("session.run_complete", {})

        finally:
            self.busy = False

    async def set_permission_mode(self, mode: str):
        """动态切换权限模式（当前会话）。"""
        valid = {"safe", "balanced", "full_auto"}
        if mode not in valid:
            return {"ok": False, "error": "mode must be one of safe/balanced/full_auto"}
        self.permission_mode = mode
        mode_map = {"safe": PermissionMode.DEFAULT, "balanced": PermissionMode.DEFAULT, "full_auto": PermissionMode.FULL_AUTO}
        settings = load_settings()
        settings.permission.mode = mode_map[mode]
        save_settings(settings)
        return {"ok": True, "mode": mode}

    async def handle_permission_response(self, request_id: str, allowed: bool):
        db_update_approval_status(
            request_id,
            status="approved" if allowed else "denied",
            decision="allow" if allowed else "deny",
            decided_at=time.time(),
        )
        fut = self._permission_futures.pop(request_id, None)
        if fut and not fut.done():
            fut.set_result(allowed)

    async def handle_question_response(self, request_id: str, answer: str):
        fut = self._question_futures.pop(request_id, None)
        if fut and not fut.done():
            fut.set_result(answer)

    async def shutdown(self):
        if self._closed:
            return
        self._closed = True

        # 自动生成标题（如果还没有）
        auto_generate_title(self._db_session_id)

        for fut in self._permission_futures.values():
            if not fut.done():
                fut.set_result(False)
        self._permission_futures.clear()
        self._question_futures.clear()

        if self.bundle:
            await close_runtime(self.bundle)
            self.bundle = None

        await self._push("session.closed", {"session_id": self.session_id})

    # ── 内部方法 ─────────────────────────────────────────

    async def _ask_permission(self, tool_name: str, reason: str) -> bool:
        rid = uuid4().hex
        fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._permission_futures[rid] = fut

        db_create_approval(ApprovalRecord(
            approval_id=rid,
            session_id=self._db_session_id,
            request_type="permission",
            tool_name=tool_name,
            reason=reason,
            status="pending",
            requested_at=time.time(),
        ))

        await self._push("approval.request", {
            "request_id": rid,
            "tool_name": tool_name,
            "reason": reason,
        })
        try:
            return await fut
        except asyncio.CancelledError:
            return False

    async def _ask_question(self, question: str) -> str:
        rid = uuid4().hex
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._question_futures[rid] = fut

        await self._push("question.request", {
            "request_id": rid,
            "question": question,
        })
        try:
            return await fut
        except asyncio.CancelledError:
            return ""

    async def _forward_stream(self, event: StreamEvent):
        """OpenHarness 原生 StreamEvent → WebSocket 事件 + SQLite 持久化。"""
        if isinstance(event, AssistantTextDelta):
            await self._push("assistant.delta", {"text": event.text})

        elif isinstance(event, AssistantTurnComplete):
            text = event.message.text.strip() if hasattr(event.message, "text") else str(event.message)
            usage = None
            if hasattr(event.message, "tool_uses") and event.message.tool_uses:
                # 提取工具调用信息作为 tool_input
                tool_uses = [
                    {"tool": tu.name, "input": tu.input}
                    for tu in event.message.tool_uses
                ]
            else:
                tool_uses = []

            save_message(MessageRecord(
                session_id=self._db_session_id,
                role="assistant",
                content=text,
                seq=self._msg_seq,
                created_at=time.time(),
            ))
            self._msg_seq += 1
            increment_message_count(self._db_session_id)

            await self._push("assistant.complete", {"text": text})
            await self._push("tasks.updated", {
                "tasks": [
                    {"id": t.id, "type": t.type, "status": t.status, "description": t.description}
                    for t in get_task_manager().list_tasks()
                ],
            })

        elif isinstance(event, ToolExecutionStarted):
            await self._push("tool.started", {
                "tool_name": event.tool_name,
                "tool_input": event.tool_input,
            })

        elif isinstance(event, ToolExecutionCompleted):
            artifact_output = event.output if isinstance(event.output, str) else json.dumps(event.output, ensure_ascii=False, indent=2)

            # 工具结果 → SQLite
            save_message(MessageRecord(
                session_id=self._db_session_id,
                role="tool_result",
                content=artifact_output,
                tool_name=event.tool_name,
                tool_output=artifact_output,
                is_error=event.is_error,
                seq=self._msg_seq,
                created_at=time.time(),
            ))
            create_artifact(
                session_id=self._db_session_id,
                tool_name=event.tool_name,
                artifact_type="error" if event.is_error else ("text" if isinstance(event.output, str) else "json"),
                content=artifact_output,
                file_path="",
            )
            self._msg_seq += 1
            increment_message_count(self._db_session_id)

            await self._push("tool.completed", {
                "tool_name": event.tool_name,
                "output": artifact_output,
                "is_error": event.is_error,
            })

        else:
            payload = asdict(event) if hasattr(event, "__dataclass_fields__") else {"raw": str(event)}
            await self._push(f"openharness.{event.__class__.__name__}", payload)

    async def _push(self, event_type: str, payload: dict):
        if not self.ws or self._closed:
            return

        envelope = {
            "type": event_type,
            "session_id": self.session_id,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await self.ws.send_json(envelope)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════
# 会话管理器
# ═══════════════════════════════════════════════════════

class SessionManager:
    """内存中活跃的 WebSocket 会话。"""
    sessions: dict[str, AgentSession] = {}

    @classmethod
    def create(cls) -> AgentSession:
        sid = uuid4().hex[:12]
        s = AgentSession(sid)
        cls.sessions[sid] = s
        return s

    @classmethod
    def get(cls, sid: str) -> AgentSession | None:
        return cls.sessions.get(sid)

    @classmethod
    def remove(cls, sid: str):
        cls.sessions.pop(sid, None)


# ═══════════════════════════════════════════════════════
# REST API — 健康检查
# ═══════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    active = [s for s in SessionManager.sessions.values() if not s._closed]
    return {
        "service": "openharness-desktop-host",
        "version": "0.3.0",
        "protocol": "http+websocket",
        "protocol_version": _PROTO_VERSION,
        "active_sessions": len(active),
    }


# ═══════════════════════════════════════════════════════
# REST API — 会话管理
# ═══════════════════════════════════════════════════════

@app.post("/api/sessions")
async def create_session(body: dict = {}):
    """创建新会话（同时创建 SQLite 记录）。"""
    sid = uuid4().hex[:12]
    db_create_session(
        sid,
        cwd=body.get("cwd", os.getcwd()),
        model=body.get("model") or os.environ.get("OPENHARNESS_MODEL") or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat",
        title=body.get("title", ""),
    )
    return {
        "session_id": sid,
        "ws_url": f"/ws/{sid}",
    }


@app.get("/api/sessions")
async def list_sessions_db(limit: int = 50):
    """从 SQLite 获取会话列表。"""
    sessions = db_list_sessions(limit=limit)
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "title": s.title,
                "status": s.status,
                "model": s.model,
                "permission_mode": getattr(s, 'permission_mode', 'full_auto') or 'full_auto',
                "message_count": s.message_count,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in sessions
        ],
    }


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str, limit: int = 200):
    """获取单条会话详情（含消息列表）。"""
    meta = db_get_session(session_id)
    if not meta:
        return {"error": "session not found"}, 404

    messages = db_get_messages(session_id, limit=limit)
    return {
        "session": {
            "session_id": meta.session_id,
            "title": meta.title,
            "status": meta.status,
            "model": meta.model,
            "message_count": meta.message_count,
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
        },
        "messages": [m.to_dict() for m in messages],
    }


@app.post("/api/sessions/{session_id}/resume")
async def resume_session(session_id: str):
    """恢复历史会话。
    
    前端流程：
    1. 调用此接口获取恢复信息
    2. 带上 session_id 连接 WebSocket
    3. 后端自动恢复历史消息，前端渲染
    4. 新消息追加到同一个会话
    """
    meta = db_get_session(session_id)
    if not meta:
        return {"error": "session not found"}, 404

    messages = db_get_messages(session_id)
    messages_raw = []
    for m in messages:
        msg_dict = {"role": m.role, "content": m.content}
        if m.tool_name:
            msg_dict["tool_name"] = m.tool_name
            if m.tool_input:
                msg_dict["tool_input"] = json.loads(m.tool_input)
        if m.tool_output:
            msg_dict["tool_output"] = m.tool_output
            msg_dict["is_error"] = m.is_error
        messages_raw.append(msg_dict)

    # 更新状态
    db_update_session(session_id, status="active")

    return {
        "session": {
            "session_id": meta.session_id,
            "title": meta.title,
            "model": meta.model,
            "message_count": meta.message_count,
            "ws_url": f"/ws/{session_id}",
        },
        "messages": messages_raw,
    }


@app.post("/api/sessions/{session_id}/fork")
async def fork_session(session_id: str, body: dict = {}):
    """分叉历史会话，创建全新的副本。"""
    new_id = db_fork_session(session_id)
    if not new_id:
        return {"error": "session not found"}, 404

    db_update_session(new_id, title=body.get("title", f"Fork of {session_id}"))

    return {
        "new_session_id": new_id,
        "source_session_id": session_id,
        "ws_url": f"/ws/{new_id}",
    }


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话（SQLite 中删除）。"""
    # 先关闭活跃的 AgentSession
    s = SessionManager.get(session_id)
    if s:
        await s.shutdown()
        SessionManager.remove(session_id)

    ok = db_delete_session(session_id)
    return {"ok": ok}


@app.put("/api/sessions/{session_id}/title")
async def update_session_title(session_id: str, body: dict):
    """修改会话标题。"""
    title = body.get("title", "")
    if not title:
        return {"error": "title is required"}, 400
    meta = db_update_session(session_id, title=title)
    if not meta:
        return {"error": "session not found"}, 404
    return {"ok": True, "title": title}


@app.put("/api/sessions/{session_id}/permission")
async def update_permission_mode(session_id: str, body: dict):
    """切换会话权限模式（safe/balanced/full_auto）。"""
    mode = body.get("mode", "")
    if not mode:
        return {"error": "mode is required"}, 400
    s = SessionManager.get(session_id)
    if s:
        result = await s.set_permission_mode(mode)
        if result.get("ok"):
            db_update_session(session_id, permission_mode=mode)
            return result
        return {"error": result.get("error")}, 400
    # Session not in memory, just update DB
    db_update_session(session_id, permission_mode=mode)
    return {"ok": True, "mode": mode}


@app.get("/api/sessions/{session_id}/approvals")
async def get_session_approvals(session_id: str, status: str | None = "pending"):
    meta = db_get_session(session_id)
    if not meta:
        return {"error": "session not found"}, 404

    approvals = db_list_approvals(session_id, status=status)
    return {
        "session_id": session_id,
        "approvals": [approval.to_dict() for approval in approvals],
    }


@app.get("/api/sessions/{session_id}/artifacts")
async def get_session_artifacts(session_id: str, limit: int = 50):
    meta = db_get_session(session_id)
    if not meta:
        return {"error": "session not found"}, 404

    artifacts = db_list_artifacts(session_id, limit=limit)
    return {
        "session_id": session_id,
        "artifacts": [artifact.to_dict() for artifact in artifacts],
    }


@app.get("/api/artifacts/{artifact_id}")
async def get_artifact_detail(artifact_id: str):
    artifact = db_get_artifact(artifact_id)
    if not artifact:
        return {"error": "artifact not found"}, 404
    return artifact.to_dict()


# ═══════════════════════════════════════════════════════
# WebSocket — 核心事件流
# ═══════════════════════════════════════════════════════

@app.websocket("/ws/{session_id}")
async def ws_endpoint(ws: WebSocket, session_id: str):
    await ws.accept()

    # 获取或创建会话
    s = SessionManager.get(session_id)
    if not s:
        s = AgentSession(session_id)
        SessionManager.sessions[session_id] = s

    s.ws = ws

    try:
        if not s.bundle:
            await s.init_runtime()  # 默认不恢复历史消息

        await ws.send_json({
            "type": "session.ready",
            "session_id": s.session_id,
            "payload": {
                "model": getattr(s.bundle.engine, '_model', None) if s.bundle else None,
                "mode": "full_auto",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # 消息循环
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            t = data.get("type", "")

            if t == "ping":
                await ws.send_json({
                    "type": "pong",
                    "session_id": s.session_id,
                    "payload": {},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            elif t == "session.submit":
                text = data.get("payload", {}).get("text", "")
                await s.handle_submit(text)

            elif t == "permission.response":
                p = data.get("payload", {})
                await s.handle_permission_response(p.get("request_id"), p.get("allowed", False))

            elif t == "question.response":
                p = data.get("payload", {})
                await s.handle_question_response(p.get("request_id"), p.get("answer", ""))

            elif t == "session.shutdown":
                break

            else:
                await ws.send_json({
                    "type": "error",
                    "session_id": s.session_id,
                    "payload": {"message": f"Unknown type: {t}"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

    except WebSocketDisconnect:
        pass
    finally:
        if s:
            await s.shutdown()
            SessionManager.remove(session_id)


# ═══════════════════════════════════════════════════════
# 旧 demo 端点（兼容保留，可删）
# ═══════════════════════════════════════════════════════

from .demo_runner import (
    run_combined_tool_validation,
    run_single_bash_validation,
    run_single_web_fetch_validation,
    run_single_web_search_validation,
)

@app.post("/api/demo/run-bash-pwd")
async def demo_bash():
    return await run_single_bash_validation()

@app.post("/api/demo/run-web-search")
async def demo_search():
    return await run_single_web_search_validation()

@app.post("/api/demo/run-web-fetch")
async def demo_fetch():
    return await run_single_web_fetch_validation()

@app.post("/api/demo/run-combined-tools")
async def demo_combined():
    return await run_combined_tool_validation()


# ═══════════════════════════════════════════════════════
# Frontend — serve last (after all API/WS routes)
# ═══════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    html_path = FRONTEND_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/{file_path:path}")
async def serve_frontend_file(file_path: str):
    file_path = file_path.strip("/")
    if not file_path or file_path.startswith(("api/", "ws/", "static/")):
        raise HTTPException(status_code=404, detail="Not found")

    asset_path = FRONTEND_DIR / file_path
    try:
        resolved_path = asset_path.resolve()
        resolved_path.relative_to(FRONTEND_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")

    if resolved_path.is_file():
        return FileResponse(resolved_path)

    raise HTTPException(status_code=404, detail="Not found")
