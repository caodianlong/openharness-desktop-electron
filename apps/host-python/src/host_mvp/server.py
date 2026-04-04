from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .adapter import OpenHarnessAdapter
from .demo_runner import (
    run_combined_tool_validation,
    run_single_bash_validation,
    run_single_web_fetch_validation,
    run_single_web_search_validation,
)

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


@app.post("/demo/run-bash-pwd")
async def demo_run_bash_pwd():
    return await run_single_bash_validation()


@app.post("/demo/run-web-search")
async def demo_run_web_search():
    return await run_single_web_search_validation()


@app.post("/demo/run-web-fetch")
async def demo_run_web_fetch():
    return await run_single_web_fetch_validation()


@app.post("/demo/run-combined-tools")
async def demo_run_combined_tools():
    return await run_combined_tool_validation()


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
