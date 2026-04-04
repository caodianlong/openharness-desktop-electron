from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .adapter import OpenHarnessAdapter

app = FastAPI(title="OpenHarness Desktop Host MVP", version="0.1.0")
adapter = OpenHarnessAdapter()
clients: Set[WebSocket] = set()


@app.get("/health")
async def health():
    return {
        "service": "host-mvp",
        "status": "ok" if adapter.health()["ok"] else "degraded",
        "openharness": adapter.health(),
    }


@app.get("/version")
async def version():
    return {
        "service": "host-mvp",
        "host_version": "0.1.0",
        **adapter.version(),
    }


@app.get("/protocol/version")
async def protocol_version():
    return {"protocol_version": "1", "transport": ["http", "websocket"]}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_json(
            {
                "event_id": "evt_bootstrap",
                "event_type": "host.ready",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "trace_id": None,
                "conversation_id": None,
                "run_id": None,
                "payload": {
                    "service": "host-mvp",
                    "openharness": adapter.health(),
                },
                "version": "1",
            }
        )
        while True:
            data = await ws.receive_json()
            if data.get("type") == "ping":
                await ws.send_json(
                    {
                        "event_id": "evt_pong",
                        "event_type": "host.pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "trace_id": None,
                        "conversation_id": None,
                        "run_id": None,
                        "payload": {"echo": data},
                        "version": "1",
                    }
                )
            else:
                await ws.send_json(
                    {
                        "event_id": "evt_echo",
                        "event_type": "host.echo",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "trace_id": None,
                        "conversation_id": None,
                        "run_id": None,
                        "payload": {"received": data},
                        "version": "1",
                    }
                )
            await asyncio.sleep(0)
    except WebSocketDisconnect:
        clients.discard(ws)
