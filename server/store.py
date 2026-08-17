"""
All the laptop's state lives here: who is online, what happened, where the
ball is. Kept separate from app.py so the web layer stays thin.

Two kinds of state:
  - live state, in memory, rebuilt from scratch on restart (node status)
  - the event log, in SQLite on disk, which survives a crash
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from server.market import Market
from server.protocol import Heartbeat, NodeEvent

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "nodes.json"
DB_PATH = ROOT / "data" / "events.sqlite3"


def load_config() -> dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # Strip the _comment_* keys so they never reach the browser.
    cfg = {k: v for k, v in cfg.items() if not k.startswith("_comment")}
    cfg["nodes"].sort(key=lambda n: n["order"])
    return cfg


@dataclass
class NodeState:
    """Everything the dashboard shows for one ESP32."""

    node_id: str
    label: str
    module: int
    station: int
    order: int
    gap_mm: float

    online: bool = False
    last_seen_wall: Optional[float] = None  # laptop time.time() of last contact
    fw: str = "-"
    rssi: Optional[int] = None
    uptime_ms: int = 0
    seq: int = 0
    missed_seq: int = 0  # how many messages we think went missing

    # Last completed ball measurement
    last_ball_wall: Optional[float] = None
    last_dt_us: Optional[int] = None
    last_speed_mps: Optional[float] = None
    ball_count: int = 0

    # Battery (populated for real in Step 2)
    batt_mv: Optional[int] = None
    batt_state: str = "UNKNOWN"

    # Faults, so a flaky station is visible rather than silently wrong
    fault_count: int = 0
    last_fault: Optional[str] = None

    # --- diagnostic counters -------------------------------------------
    # These exist purely so the Diagnostics tab can tell you WHY a station is
    # misbehaving instead of just that it is.
    ever_seen: bool = False
    total_msgs: int = 0
    boot_count: int = 0
    last_boot_wall: Optional[float] = None
    worst_rssi: Optional[int] = None

    fault_a_only: int = 0     # beam A broke, beam B never did
    fault_b_only: int = 0     # beam B broke with no preceding beam A
    fault_timeout: int = 0    # ball appears to have stopped between beams
    implausible_count: int = 0  # a "ball" too fast to be a ball

    # Battery state as of the last contact, kept separately so we can still
    # explain a node that has since gone offline.
    last_seen_batt_state: str = "UNKNOWN"
    last_seen_rssi: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Store:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.heartbeat_timeout_s: float = float(self.cfg.get("heartbeat_timeout_s", 6.0))
        self.run_name: str = self.cfg.get("run_name", "Marble Run")

        self._lock = threading.Lock()
        self.nodes: dict[str, NodeState] = {
            n["node_id"]: NodeState(
                node_id=n["node_id"],
                label=n["label"],
                module=n["module"],
                station=n["station"],
                order=n["order"],
                gap_mm=float(n["gap_mm"]),
            )
            for n in self.cfg["nodes"]
        }

        # Run state
        self.run_active: bool = False
        self.run_started_wall: Optional[float] = None
        self.run_ended_wall: Optional[float] = None
        self.ball_at_order: int = 0  # 0 = not started; else the order of last node passed

        self.recent_events: list[dict[str, Any]] = []  # newest first, capped

        # The simulated economy. It has its own lock and its own on-disk state;
        # a run RESET deliberately does NOT touch it, because resetting the ball
        # for another attempt has nothing to do with whether war has broken out.
        self.market = Market()

        self._init_db()

    # ---------------------------------------------------------------- SQLite

    def _init_db(self) -> None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False because uvicorn touches this from its worker
        # thread; every write is already guarded by self._lock.
        self._db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_wall     REAL NOT NULL,
                run_started REAL,
                node_id     TEXT NOT NULL,
                event       TEXT NOT NULL,
                dt_us       INTEGER,
                speed_mps   REAL,
                gap_mm      REAL,
                batt_mv     INTEGER,
                batt_state  TEXT,
                rssi        INTEGER,
                seq         INTEGER,
                raw         TEXT NOT NULL
            )
            """
        )
        self._db.commit()

    def _log_to_db(self, ev: NodeEvent, ts_wall: float) -> None:
        self._db.execute(
            "INSERT INTO events (ts_wall, run_started, node_id, event, dt_us, speed_mps,"
            " gap_mm, batt_mv, batt_state, rssi, seq, raw)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ts_wall,
                self.run_started_wall,
                ev.node_id,
                ev.event,
                ev.dt_us,
                ev.speed_mps,
                ev.gap_mm,
                ev.batt_mv,
                ev.batt_state,
                ev.rssi,
                ev.seq,
                ev.model_dump_json(),
            ),
        )
        self._db.commit()

    # ------------------------------------------------------- ingest from node

    def _touch(self, node: NodeState, hb: Heartbeat, now: float) -> None:
        """Common bookkeeping for any message from a node."""
        # Detect gaps in the sequence number. A node that reboots resets seq to
        # 0, which is not a drop - so only count forward jumps.
        if node.last_seen_wall is not None and hb.seq > node.seq + 1:
            node.missed_seq += hb.seq - node.seq - 1

        node.online = True
        node.ever_seen = True
        node.total_msgs += 1
        node.last_seen_wall = now
        node.fw = hb.fw
        node.rssi = hb.rssi
        node.uptime_ms = hb.uptime_ms
        node.seq = hb.seq
        if hb.rssi is not None:
            node.last_seen_rssi = hb.rssi
            if node.worst_rssi is None or hb.rssi < node.worst_rssi:
                node.worst_rssi = hb.rssi
        if hb.batt_mv is not None:
            node.batt_mv = hb.batt_mv
        if hb.batt_state != "UNKNOWN":
            node.batt_state = hb.batt_state
            node.last_seen_batt_state = hb.batt_state

    def apply_heartbeat(self, hb: Heartbeat) -> Optional[NodeState]:
        with self._lock:
            node = self.nodes.get(hb.node_id)
            if node is None:
                return None
            self._touch(node, hb, time.time())
            return node

    def apply_event(self, ev: NodeEvent) -> tuple[Optional[NodeState], Optional[dict[str, Any]]]:
        now = time.time()
        with self._lock:
            node = self.nodes.get(ev.node_id)
            if node is None:
                return None, None

            self._touch(node, ev, now)

            if ev.event == "BALL_PASS":
                node.last_ball_wall = now
                node.last_dt_us = ev.dt_us
                node.last_speed_mps = ev.speed_mps
                node.ball_count += 1

                # If a ball turns up before anyone pressed START, start the
                # clock ourselves. Forgetting to press START and losing the
                # elapsed time of a real attempt is a failure mode we can just
                # design out. After an explicit STOP we do NOT auto-restart -
                # stop means stop, until RESET.
                if not self.run_active and self.run_started_wall is None:
                    self.run_active = True
                    self.run_started_wall = now
                    self.run_ended_wall = None

                # Progression tracks regardless of run state, so the strip is
                # never mysteriously frozen. It only moves forward: if a node
                # fires out of order (reflection, second ball, someone waving a
                # hand through a beam) we keep the furthest point rather than
                # yanking the display backwards.
                if node.order > self.ball_at_order:
                    self.ball_at_order = node.order

                # A 25 mm ball in a gravity-fed PVC run does not travel at
                # 10 m/s. If we see that, the node timed something that was not
                # a ball - electrical noise, or one beam double-triggering.
                if (ev.speed_mps is not None and ev.speed_mps > 10.0) or (
                    ev.dt_us is not None and ev.dt_us < 3000
                ):
                    node.implausible_count += 1

            elif ev.event in ("BEAM_A_ONLY", "BEAM_B_ONLY", "TIMEOUT"):
                node.fault_count += 1
                node.last_fault = ev.event
                if ev.event == "BEAM_A_ONLY":
                    node.fault_a_only += 1
                elif ev.event == "BEAM_B_ONLY":
                    node.fault_b_only += 1
                else:
                    node.fault_timeout += 1
            elif ev.event == "BOOT":
                node.seq = ev.seq
                node.boot_count += 1
                node.last_boot_wall = now

            self._log_to_db(ev, now)

            record = {
                "ts_wall": now,
                "node_id": ev.node_id,
                "label": node.label,
                "event": ev.event,
                "dt_us": ev.dt_us,
                "speed_mps": ev.speed_mps,
                "gap_mm": ev.gap_mm,
                "batt_state": ev.batt_state,
                "batt_mv": ev.batt_mv,
                "note": ev.note,
            }
            self.recent_events.insert(0, record)
            del self.recent_events[300:]  # cap memory; SQLite has the full history
            return node, record

    # --------------------------------------------------------------- watchdog

    def sweep_offline(self) -> list[NodeState]:
        """Mark nodes offline if they've gone quiet. Returns those that changed."""
        now = time.time()
        changed: list[NodeState] = []
        with self._lock:
            for node in self.nodes.values():
                if not node.online:
                    continue
                if node.last_seen_wall is None:
                    continue
                if now - node.last_seen_wall > self.heartbeat_timeout_s:
                    node.online = False
                    changed.append(node)
        return changed

    # -------------------------------------------------------------- run control

    def start_run(self) -> dict[str, Any]:
        with self._lock:
            self.run_active = True
            self.run_started_wall = time.time()
            self.run_ended_wall = None
            self.ball_at_order = 0
            return self.run_dict()

    def stop_run(self) -> dict[str, Any]:
        with self._lock:
            self.run_active = False
            self.run_ended_wall = time.time()
            return self.run_dict()

    def reset_run(self) -> dict[str, Any]:
        """Clear the board for the next attempt. Does NOT wipe the SQLite log."""
        with self._lock:
            self.run_active = False
            self.run_started_wall = None
            self.run_ended_wall = None
            self.ball_at_order = 0
            self.recent_events.clear()
            for node in self.nodes.values():
                node.last_ball_wall = None
                node.last_dt_us = None
                node.last_speed_mps = None
                node.ball_count = 0
                node.fault_count = 0
                node.last_fault = None
            return self.run_dict()

    def clear_diagnostics(self) -> None:
        """
        Zero the health counters after you've physically fixed something.

        These deliberately survive a run RESET - a station with a misaligned
        beam is still misaligned after you reset the run, and silently
        forgetting that would be the worst possible behaviour. You clear them
        when you've actually done something about it, then watch whether the
        fault comes back.
        """
        with self._lock:
            for node in self.nodes.values():
                node.boot_count = 0
                node.last_boot_wall = None
                node.missed_seq = 0
                node.total_msgs = 0
                node.worst_rssi = node.rssi
                node.fault_a_only = 0
                node.fault_b_only = 0
                node.fault_timeout = 0
                node.implausible_count = 0
                node.fault_count = 0
                node.last_fault = None

    def run_dict(self) -> dict[str, Any]:
        return {
            "run_name": self.run_name,
            "active": self.run_active,
            "started_wall": self.run_started_wall,
            "ended_wall": self.run_ended_wall,
            "ball_at_order": self.ball_at_order,
        }

    def snapshot(self) -> dict[str, Any]:
        """
        Full state for every screen. All four pages - live, depot, stage and
        admin - open the same WebSocket and receive this same message, then
        render the slice they care about. One payload is why the boards cannot
        drift out of sync with each other.
        """
        market = self.market.to_dict()  # outside self._lock; Market locks itself
        with self._lock:
            return {
                "type": "snapshot",
                "server_wall": time.time(),
                "run": self.run_dict(),
                "nodes": [n.to_dict() for n in sorted(self.nodes.values(), key=lambda x: x.order)],
                "events": list(self.recent_events[:100]),
                "market": market,
            }
