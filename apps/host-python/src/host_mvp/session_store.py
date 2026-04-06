"""
OpenHarness Desktop — SQLite 会话存储
=====================================

职责:
1. 持久化会话元数据 + 消息（SQLite）
2. 同时保存 OpenHarness 原生 JSON 快照（备份兼容）
3. 提供完整的 CRUD + 恢复/分叉/搜索

存储位置:
- SQLite DB:  ~/.openharness/desktop.db
- OH 快照:    ~/.openharness/sessions/<project>-<hash>/session-{id}.json
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import sqlite3

OPENHARNESS_STORAGE = {
    "sessions_dir": Path.home() / ".openharness" / "sessions",
}

DESKTOP_DB_PATH = Path.home() / ".openharness" / "desktop.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,
    title         TEXT DEFAULT '',
    status        TEXT DEFAULT 'active',   -- active / archived / closed
    cwd           TEXT NOT NULL DEFAULT '',
    model         TEXT NOT NULL DEFAULT '',
    message_count INTEGER DEFAULT 0,
    usage_input   INTEGER DEFAULT 0,
    usage_output  INTEGER DEFAULT 0,
    snapshot_path TEXT DEFAULT '',         -- OpenHarness 原生 JSON 快照路径
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role          TEXT NOT NULL,           -- user / assistant / system / tool / tool_result
    content       TEXT NOT NULL DEFAULT '',
    tool_name     TEXT DEFAULT '',
    tool_input    TEXT DEFAULT '',         -- JSON，工具调用输入
    tool_output   TEXT DEFAULT '',         -- 工具执行结果
    is_error      INTEGER DEFAULT 0,
    seq           INTEGER NOT NULL,         -- 消息顺序号
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id   TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    request_type  TEXT NOT NULL DEFAULT 'permission',
    tool_name     TEXT DEFAULT '',
    reason        TEXT DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'pending',
    requested_at  REAL NOT NULL,
    decided_at    REAL,
    decision      TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    tool_name TEXT DEFAULT '',
    artifact_type TEXT DEFAULT 'text',
    content TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id, created_at DESC);
"""


def _ensure_db() -> sqlite3.Connection:
    """确保 DB 文件与 schema 就绪，返回连接。"""
    db_dir = DESKTOP_DB_PATH.parent
    db_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DESKTOP_DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)

    # Migrate legacy schema: add permission_mode column if missing
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN permission_mode TEXT DEFAULT 'full_auto'")
    except sqlite3.OperationalError:
        pass  # column already exists

    return conn


# 单例
_db_conn: sqlite3.Connection | None = None

def get_db() -> sqlite3.Connection:
    global _db_conn
    if _db_conn is None:
        _db_conn = _ensure_db()
    return _db_conn


# ═══════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════

@dataclass
class SessionMeta:
    session_id: str
    title: str = ""
    status: str = "active"
    cwd: str = ""
    model: str = ""
    permission_mode: str = "full_auto"  # safe/balanced/full_auto
    message_count: int = 0
    usage_input: int = 0
    usage_output: int = 0
    snapshot_path: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    @classmethod
    def from_row(cls, row: tuple) -> "SessionMeta":
        # Map by column name for safe ALTER TABLE compatibility
        return cls(
            session_id=row[0],
            title=row[1],
            status=row[2],
            cwd=row[3],
            model=row[4],
            permission_mode=row[11] if len(row) > 11 else (row[5] if len(row) > 5 and isinstance(row[5], str) else "full_auto"),
            message_count=row[5] if len(row) > 5 and isinstance(row[5], int) else (row[6] if len(row) > 6 else 0),
            usage_input=row[6] if len(row) > 6 and isinstance(row[6], int) else (row[7] if len(row) > 7 else 0),
            usage_output=row[7] if len(row) > 7 and isinstance(row[7], int) else (row[8] if len(row) > 8 else 0),
            snapshot_path=row[8] if len(row) > 8 else (row[9] if len(row) > 9 else ""),
            created_at=row[9] if len(row) > 9 else (row[10] if len(row) > 10 else 0.0),
            updated_at=row[10] if len(row) > 10 else (row[11] if len(row) > 11 else 0.0),
        )


@dataclass
class MessageRecord:
    session_id: str
    role: str
    content: str = ""
    tool_name: str = ""
    tool_input: str = ""
    tool_output: str = ""
    is_error: bool = False
    seq: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "tool_name": self.tool_name,
            "tool_input": json.loads(self.tool_input) if self.tool_input else None,
            "tool_output": self.tool_output,
            "is_error": self.is_error,
        }


@dataclass
class ApprovalRecord:
    approval_id: str
    session_id: str
    request_type: str = "permission"
    tool_name: str = ""
    reason: str = ""
    status: str = "pending"
    requested_at: float = field(default_factory=time.time)
    decided_at: float | None = None
    decision: str = ""

    @classmethod
    def from_row(cls, row: tuple) -> "ApprovalRecord":
        return cls(
            approval_id=row[0],
            session_id=row[1],
            request_type=row[2],
            tool_name=row[3] or "",
            reason=row[4] or "",
            status=row[5],
            requested_at=row[6],
            decided_at=row[7],
            decision=row[8] or "",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "session_id": self.session_id,
            "request_type": self.request_type,
            "tool_name": self.tool_name,
            "reason": self.reason,
            "status": self.status,
            "requested_at": self.requested_at,
            "decided_at": self.decided_at,
            "decision": self.decision,
        }


@dataclass
class ArtifactRecord:
    artifact_id: str
    session_id: str
    tool_name: str = ""
    artifact_type: str = "text"
    content: str = ""
    file_path: str = ""
    created_at: float = field(default_factory=time.time)

    @classmethod
    def from_row(cls, row: tuple) -> "ArtifactRecord":
        return cls(
            artifact_id=row[0],
            session_id=row[1],
            tool_name=row[2] or "",
            artifact_type=row[3] or "text",
            content=row[4] or "",
            file_path=row[5] or "",
            created_at=row[6],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "artifact_type": self.artifact_type,
            "content": self.content,
            "file_path": self.file_path,
            "created_at": self.created_at,
        }


# ═══════════════════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════════════════

def create_session(
    session_id: str,
    *,
    cwd: str = "",
    model: str = "",
    title: str = "",
) -> SessionMeta:
    """创建新会话记录。"""
    now = time.time()
    meta = SessionMeta(
        session_id=session_id,
        title=title,
        cwd=cwd,
        model=model,
        created_at=now,
        updated_at=now,
    )
    conn = get_db()
    conn.execute(
        "INSERT INTO sessions (session_id, title, status, cwd, model, message_count, "
        "usage_input, usage_output, snapshot_path, created_at, updated_at, permission_mode, was_running_runtime) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            meta.session_id, meta.title, meta.status,
            meta.cwd, meta.model, meta.message_count,
            meta.usage_input, meta.usage_output,
            meta.snapshot_path, meta.created_at, meta.updated_at,
            'full_auto', 0,
        ),
    )
    conn.commit()
    return meta


def get_session(session_id: str) -> SessionMeta | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    return SessionMeta.from_row(row) if row else None


def list_sessions(limit: int = 50, offset: int = 0) -> list[SessionMeta]:
    """按更新时间倒序返回会话列表。"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [SessionMeta.from_row(r) for r in rows]


def delete_session(session_id: str) -> bool:
    conn = get_db()
    cur = conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
    conn.commit()
    return cur.rowcount > 0


def update_session(session_id: str, **fields: Any) -> SessionMeta | None:
    """更新指定字段并返回更新后的元数据。"""
    if not fields:
        return get_session(session_id)

    allowed = {"title", "status", "cwd", "model", "snapshot_path", "permission_mode"}
    filtered = {k: v for k, v in fields.items() if k in allowed}
    if not filtered:
        return get_session(session_id)

    filtered["updated_at"] = time.time()
    cols = ", ".join(f"{k}=?" for k in filtered)
    vals = list(filtered.values()) + [session_id]

    conn = get_db()
    conn.execute(f"UPDATE sessions SET {cols} WHERE session_id=?", vals)
    conn.commit()
    return get_session(session_id)


# ── 消息操作 ────────────────────────────────────────────

def generate_title_from_text(text: str, max_len: int = 28) -> str:
    """从用户首条消息提取/生成标题（规则方案）。
    
    MVP 阶段使用，后续可替换为 LLM 生成。
    """
    if not text or not text.strip():
        return "新对话"
    
    clean = text.strip()
    
    # 去掉斜杠命令前缀，提取命令内容
    if clean.startswith("/"):
        parts = clean.split(" ", 1)
        clean = parts[-1] if len(parts) > 1 else clean.lstrip("/")
        if not clean.strip():
            clean = parts[0].lstrip("/")  # 回退到命令名本身
    
    clean = clean.strip()
    if not clean:
        return "新对话"
    
    # 如果本身很短，直接返回
    if len(clean) <= max_len:
        return clean
    
    # 截断，优先在标点处断开
    for ch in "。！？!?，,；;：:":
        idx = clean.find(ch)
        if 0 < idx < max_len:
            return clean[:idx].strip()
    
    # 没有合适标点，直接截断
    return clean[:max_len].rstrip() + "…"


def auto_generate_title(session_id: str) -> str | None:
    """如果会话还没有标题，从第一条 user 消息自动生成。
    
    策略（MVP 阶段—规则提取，后续可接入 LLM）：
    1. 检查会话 title 是否为空
    2. 读取第一条 role='user' 的 content
    3. 用规则方案生成标题并更新
    4. 返回生成的标题（如果无内容则返回 None）
    
    LLM 接入后替换 generate_title_from_text 为 LLM 调用即可。
    """
    meta = get_session(session_id)
    if not meta:
        return None
    if meta.title and meta.title.strip():
        return meta.title  # 已有标题，跳过
    
    conn = get_db()
    row = conn.execute(
        "SELECT content FROM messages WHERE session_id=? AND role='user' ORDER BY seq ASC LIMIT 1",
        (session_id,),
    ).fetchone()
    
    if not row or not row[0].strip():
        return None
    
    title = generate_title_from_text(row[0])
    update_session(session_id, title=title)
    return title


def save_message(msg: MessageRecord) -> int:
    """保存一条消息，返回自增 ID。"""
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_name, tool_input, tool_output, is_error, seq, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            msg.session_id, msg.role, msg.content,
            msg.tool_name, msg.tool_input, msg.tool_output,
            int(msg.is_error), msg.seq, msg.created_at,
        ),
    )
    conn.commit()
    return cur.lastrowid


def increment_message_count(session_id: str) -> None:
    conn = get_db()
    conn.execute(
        "UPDATE sessions SET message_count = message_count + 1, updated_at = ? WHERE session_id = ?",
        (time.time(), session_id),
    )
    conn.commit()


def get_messages(session_id: str, limit: int | None = None) -> list[MessageRecord]:
    """按 seq 顺序读取会话消息。"""
    conn = get_db()
    query = "SELECT * FROM messages WHERE session_id=? ORDER BY seq ASC"
    if limit:
        query += f" LIMIT {limit}"
    rows = conn.execute(query, (session_id,)).fetchall()
    return [
        MessageRecord(
            session_id=r[1],
            role=r[2],
            content=r[3],
            tool_name=r[4],
            tool_input=r[5],
            tool_output=r[6],
            is_error=bool(r[7]),
            seq=r[8],
            created_at=r[9],
        )
        for r in rows
    ]


def create_approval(record: ApprovalRecord) -> str:
    conn = get_db()
    conn.execute(
        "INSERT INTO approvals (approval_id, session_id, request_type, tool_name, reason, status, requested_at, decided_at, decision) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            record.approval_id,
            record.session_id,
            record.request_type,
            record.tool_name,
            record.reason,
            record.status,
            record.requested_at,
            record.decided_at,
            record.decision,
        ),
    )
    conn.commit()
    return record.approval_id


def update_approval_status(
    approval_id: str,
    *,
    status: str,
    decision: str = "",
    decided_at: float | None = None,
) -> None:
    conn = get_db()
    conn.execute(
        "UPDATE approvals SET status=?, decision=?, decided_at=? WHERE approval_id=?",
        (status, decision, decided_at, approval_id),
    )
    conn.commit()


def list_approvals(session_id: str, status: str | None = None) -> list[ApprovalRecord]:
    conn = get_db()
    if status:
        rows = conn.execute(
            "SELECT approval_id, session_id, request_type, tool_name, reason, status, requested_at, decided_at, decision FROM approvals WHERE session_id=? AND status=? ORDER BY requested_at ASC",
            (session_id, status),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT approval_id, session_id, request_type, tool_name, reason, status, requested_at, decided_at, decision FROM approvals WHERE session_id=? ORDER BY requested_at ASC",
            (session_id,),
        ).fetchall()
    return [ApprovalRecord.from_row(row) for row in rows]


def create_artifact(
    session_id: str,
    tool_name: str = "",
    artifact_type: str = "text",
    content: str = "",
    file_path: str = "",
) -> ArtifactRecord:
    import uuid

    record = ArtifactRecord(
        artifact_id=uuid.uuid4().hex,
        session_id=session_id,
        tool_name=tool_name,
        artifact_type=artifact_type or "text",
        content=content or "",
        file_path=file_path or "",
        created_at=time.time(),
    )
    conn = get_db()
    conn.execute(
        "INSERT INTO artifacts (artifact_id, session_id, tool_name, artifact_type, content, file_path, created_at) VALUES (?,?,?,?,?,?,?)",
        (
            record.artifact_id,
            record.session_id,
            record.tool_name,
            record.artifact_type,
            record.content,
            record.file_path,
            record.created_at,
        ),
    )
    conn.commit()
    return record


def list_artifacts(session_id: str, limit: int = 50) -> list[ArtifactRecord]:
    conn = get_db()
    rows = conn.execute(
        "SELECT artifact_id, session_id, tool_name, artifact_type, content, file_path, created_at FROM artifacts WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return [ArtifactRecord.from_row(row) for row in rows]


def get_artifact(artifact_id: str) -> ArtifactRecord | None:
    conn = get_db()
    row = conn.execute(
        "SELECT artifact_id, session_id, tool_name, artifact_type, content, file_path, created_at FROM artifacts WHERE artifact_id=?",
        (artifact_id,),
    ).fetchone()
    return ArtifactRecord.from_row(row) if row else None


def fork_session(session_id: str) -> str | None:
    """分叉会话。返回新会话 ID。"""
    src = get_session(session_id)
    if not src:
        return None

    import uuid
    new_id = uuid.uuid4().hex[:12]
    from datetime import datetime
    now = time.time()

    conn = get_db()
    conn.execute(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (new_id, src.title, "active", src.cwd, src.model, 0, 0, 0, "", now, now),
    )

    # 复制消息
    rows = conn.execute(
        "SELECT role, content, tool_name, tool_input, tool_output, is_error FROM messages WHERE session_id=? ORDER BY seq ASC",
        (session_id,),
    ).fetchall()
    for i, row in enumerate(rows):
        conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_name, tool_input, tool_output, is_error, seq, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (new_id, row[0], row[1], row[2], row[3], row[4], int(row[5]), i, now),
        )

    conn.commit()
    return new_id


def search_sessions(query: str, limit: int = 20) -> list[SessionMeta]:
    """按标题或内容搜索会话。"""
    conn = get_db()
    # 搜索 title 或 messages 中存在 query 关键词的会话
    rows = conn.execute("""
        SELECT DISTINCT s.* FROM sessions s
        LEFT JOIN messages m ON s.session_id = m.session_id
        WHERE s.title LIKE ? OR m.content LIKE ?
        ORDER BY s.updated_at DESC
        LIMIT ?
    """, (f"%{query}%", f"%{query}%", limit)).fetchall()
    return [SessionMeta.from_row(r) for r in rows]




def save_openharness_snapshot(
    session_id: str,
    cwd: str,
    model: str,
    messages: list[dict],
    summary: str = "",
    usage: dict | None = None,
) -> str:
    """保存 OpenHarness 原生 JSON 快照，返回文件路径。"""
    from hashlib import sha1

    session_dir = OPENHARNESS_STORAGE["sessions_dir"]
    # 按 cwd 生成项目哈希
    path_hash = sha1(str(Path(cwd).resolve()).encode()).hexdigest()[:12]
    project_dir = session_dir / f"{Path(cwd).name}-{path_hash}"
    project_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "session_id": session_id,
        "cwd": str(Path(cwd).resolve()),
        "model": model,
        "messages": messages,
        "usage": usage or {},
        "created_at": time.time(),
        "summary": summary,
        "message_count": len(messages),
    }

    session_path = project_dir / f"session-{session_id}.json"
    session_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # 同步更新 SQLite 中的快照路径
    update_session(session_id, snapshot_path=str(session_path))

    return str(session_path)
