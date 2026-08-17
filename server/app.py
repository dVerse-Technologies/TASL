"""
TASL laptop server.

Two audiences:
  - ESP32 nodes, which POST JSON to /api/heartbeat and /api/event
  - the browser dashboard, which loads / and then listens on /ws

Run it with:   python run_server.py
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server.diagnostics import diagnose_all
from server.protocol import Heartbeat, NodeEvent
from server.store import Store

STATIC_DIR = Path(__file__).resolve().parent / "static"

store = Store()


class Hub:
    """Keeps the set of connected browsers and fans messages out to them."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def join(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def leave(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message)
        async with self._lock:
            targets = list(self._clients)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                # A browser tab closed mid-send. Not an error worth logging at
                # an event; just drop it.
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


hub = Hub()


async def _offline_watchdog() -> None:
    """Once a second, demote silent nodes to OFFLINE and tell the browsers."""
    while True:
        try:
            for node in store.sweep_offline():
                await hub.broadcast({"type": "node", "node": node.to_dict()})
        except Exception as exc:  # never let the watchdog die
            print(f"[watchdog] {exc!r}")
        await asyncio.sleep(1.0)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_offline_watchdog())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="TASL Marble Run", lifespan=lifespan)


# ----------------------------------------------------------------- node API

@app.post("/api/heartbeat")
async def post_heartbeat(hb: Heartbeat) -> JSONResponse:
    node = store.apply_heartbeat(hb)
    if node is None:
        # Unknown node. Tell the ESP32 clearly rather than silently accepting -
        # a typo'd node_id is otherwise invisible until event day.
        return JSONResponse(
            {"ok": False, "error": f"unknown node_id '{hb.node_id}' - add it to config/nodes.json"},
            status_code=404,
        )
    await hub.broadcast({"type": "node", "node": node.to_dict()})
    return JSONResponse({"ok": True})


@app.post("/api/event")
async def post_event(ev: NodeEvent) -> JSONResponse:
    node, record = store.apply_event(ev)
    if node is None or record is None:
        return JSONResponse(
            {"ok": False, "error": f"unknown node_id '{ev.node_id}' - add it to config/nodes.json"},
            status_code=404,
        )
    await hub.broadcast(
        {
            "type": "event",
            "node": node.to_dict(),
            "event": record,
            "run": store.run_dict(),
        }
    )
    return JSONResponse({"ok": True})


# ------------------------------------------------------------ dashboard API

@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    return store.snapshot()


@app.get("/api/diagnostics")
async def get_diagnostics() -> dict[str, Any]:
    """
    Computed fresh on request rather than pushed. The browser polls this every
    couple of seconds while the Diagnostics tab is relevant - far simpler than
    recomputing and broadcasting the whole rule set on every packet, and with
    20 nodes it costs nothing.
    """
    return diagnose_all(list(store.nodes.values()))


@app.post("/api/diagnostics/clear")
async def clear_diagnostics() -> dict[str, Any]:
    """Zero the health counters, for use after physically fixing something."""
    store.clear_diagnostics()
    snap = store.snapshot()
    await hub.broadcast(snap)
    return diagnose_all(list(store.nodes.values()))


@app.post("/api/run/start")
async def run_start() -> dict[str, Any]:
    run = store.start_run()
    await hub.broadcast({"type": "run", "run": run})
    return run


@app.post("/api/run/stop")
async def run_stop() -> dict[str, Any]:
    run = store.stop_run()
    await hub.broadcast({"type": "run", "run": run})
    return run


@app.post("/api/run/reset")
async def run_reset() -> dict[str, Any]:
    store.reset_run()
    snap = store.snapshot()
    await hub.broadcast(snap)  # full redraw is simplest after a wipe
    return snap["run"]


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await hub.join(ws)
    try:
        await ws.send_text(json.dumps(store.snapshot()))
        while True:
            # We never expect input from the browser, but we must keep reading
            # so the socket close is detected promptly.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.leave(ws)


# --------------------------------------------------------------------- page

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
