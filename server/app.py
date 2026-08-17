"""
TASL laptop server.

Two audiences:
  - ESP32 nodes, which POST JSON to /api/heartbeat and /api/event
  - the browser screens, which load a page and then listen on /ws

Four screens, one server, one WebSocket. Everything is in sync because there
is only ever one copy of the state:

  /         ball location and speed      MiniPC by the build space
  /depot    live BOM prices              MiniPC at the materials depot
  /stage    breaking-news projector      laptop on stage
  /admin    triggers + diagnostics       MiniPC with the operator

There are no logins. The screens are separated by URL, and the diagnostics
that used to sit behind a wrench icon on the public dashboard now live only
on /admin, so participants never see a station misbehaving.

Run it with:   python run_server.py
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server.diagnostics import diagnose_all
from server.protocol import Heartbeat, NodeEvent
from server.store import Store

STATIC_DIR = Path(__file__).resolve().parent / "static"

store = Store()


SCREEN_ROLES = ("live", "depot", "stage", "admin")


class Hub:
    """Keeps the set of connected browsers and fans messages out to them."""

    def __init__(self) -> None:
        # ws -> role. Each page says what it is on connect, which is how the
        # admin panel can answer "is the projector actually still plugged in"
        # without anyone walking across the hall to look at it.
        self._clients: dict[WebSocket, str] = {}
        self._lock = asyncio.Lock()

    async def join(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients[ws] = "unknown"

    async def leave(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.pop(ws, None)

    async def set_role(self, ws: WebSocket, role: str) -> None:
        async with self._lock:
            if ws in self._clients:
                self._clients[ws] = role if role in SCREEN_ROLES else "unknown"

    def screens(self) -> dict[str, int]:
        """How many browsers of each kind are currently connected."""
        counts = {role: 0 for role in SCREEN_ROLES}
        counts["unknown"] = 0
        for role in self._clients.values():
            counts[role] = counts.get(role, 0) + 1
        return counts

    async def broadcast(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message)
        async with self._lock:
            targets = list(self._clients.keys())
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
                    self._clients.pop(ws, None)


hub = Hub()


async def _push_screens() -> None:
    await hub.broadcast({"type": "screens", "screens": hub.screens()})


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


@app.middleware("http")
async def no_store(request, call_next):
    """
    Nothing this server sends is ever worth caching.

    Four machines run this in kiosk mode for a whole day. When something is
    edited and a screen is reloaded, it must come back with the edit - "I
    changed it and nothing happened" is not a puzzle anyone should be solving
    twenty minutes before the event starts. There is no bandwidth argument
    against it: everything is local and measured in kilobytes.
    """
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


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


# ------------------------------------------------------------------- market
#
# Every one of these ends the same way: mutate, then broadcast the new market
# to every screen at once. That single shared broadcast is the whole sync
# story - the depot board, the stage board and the admin panel cannot show
# different prices because they are all rendering the same message.

async def _push_market() -> dict[str, Any]:
    market = store.market.to_dict()
    await hub.broadcast({"type": "market", "market": market})
    return market


@app.get("/api/market")
async def get_market() -> dict[str, Any]:
    return store.market.to_dict()


@app.post("/api/market/fire/{event_id}")
async def market_fire(event_id: str) -> JSONResponse:
    if not store.market.fire_event(event_id):
        return JSONResponse({"ok": False, "error": f"unknown event '{event_id}'"}, status_code=404)
    return JSONResponse({"ok": True, "market": await _push_market()})


@app.post("/api/market/unfire/{event_id}")
async def market_unfire(event_id: str) -> JSONResponse:
    if not store.market.unfire_event(event_id):
        return JSONResponse({"ok": False, "error": f"'{event_id}' was not fired"}, status_code=409)
    return JSONResponse({"ok": True, "market": await _push_market()})


@app.post("/api/market/flash/{event_id}")
async def market_flash(event_id: str) -> JSONResponse:
    """Replay the news takeover on the projector without re-applying prices."""
    if not store.market.flash_again(event_id):
        return JSONResponse({"ok": False, "error": f"unknown event '{event_id}'"}, status_code=404)
    return JSONResponse({"ok": True, "market": await _push_market()})


# Deliberately NOT /api/market/flash/dismiss. That would be shadowed by the
# {event_id} route above and quietly 404 - a dismiss button that does nothing
# is exactly the failure you do not want to discover with a room watching.
@app.post("/api/market/dismiss")
async def market_flash_dismiss() -> dict[str, Any]:
    store.market.dismiss_flash()
    return {"ok": True, "market": await _push_market()}


@app.post("/api/market/global")
async def market_global(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        pct = float(payload.get("pct", 0))
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "pct must be a number"}, status_code=400)
    store.market.set_global_pct(pct)
    return JSONResponse({"ok": True, "market": await _push_market()})


@app.post("/api/market/item/{item_id}")
async def market_item(item_id: str, payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        pct = float(payload.get("pct", 0))
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "pct must be a number"}, status_code=400)
    if not store.market.set_item_pct(item_id, pct):
        return JSONResponse({"ok": False, "error": f"unknown item '{item_id}'"}, status_code=404)
    return JSONResponse({"ok": True, "market": await _push_market()})


@app.post("/api/market/reset")
async def market_reset() -> dict[str, Any]:
    store.market.reset()
    return {"ok": True, "market": await _push_market()}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await hub.join(ws)
    try:
        snap = store.snapshot()
        snap["screens"] = hub.screens()
        await ws.send_text(json.dumps(snap))
        while True:
            # The only thing a browser ever sends is {"hello": "<role>"} on
            # connect. We must keep reading regardless so the socket close is
            # detected promptly.
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if isinstance(msg, dict) and "hello" in msg:
                await hub.set_role(ws, str(msg["hello"]))
                await _push_screens()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.leave(ws)
        await _push_screens()


# -------------------------------------------------------------------- pages

def _page(name: str) -> FileResponse:
    # no-store: these machines run in kiosk mode for hours and are reloaded in
    # a hurry when something goes wrong. Serving a stale cached page on a
    # panic-reload would be a genuinely bad five minutes.
    return FileResponse(STATIC_DIR / name, headers={"Cache-Control": "no-store"})


@app.get("/")
async def index() -> FileResponse:
    """Ball location and speed. The screen by the build space."""
    return _page("index.html")


@app.get("/depot")
async def depot() -> FileResponse:
    """Live BOM prices. The kiosk at the materials depot."""
    return _page("depot.html")


@app.get("/stage")
async def stage() -> FileResponse:
    """Price board, interrupted full-screen by news flashes. The projector."""
    return _page("stage.html")


@app.get("/admin")
async def admin() -> FileResponse:
    """Triggers, manual pricing and diagnostics. Operator only."""
    return _page("admin.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
