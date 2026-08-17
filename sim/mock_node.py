"""
A fake ESP32 sensor node.

This pretends to be one station: two IR beams a known distance apart, timing a
steel ball between them and computing its own speed. It speaks EXACTLY the
protocol in server/protocol.py, over exactly the same HTTP endpoints the real
firmware will use.

That is the whole point. In Step 3 you delete nothing on the laptop side - you
just stop running this and power on real hardware instead.

Run one node on its own:
    python sim/mock_node.py --node-id NODE01

Or run the whole simulated course (normal case):
    python sim/run_mocks.py
"""

from __future__ import annotations

import argparse
import random
import threading
import time
from typing import Any, Optional

import requests

DEFAULT_SERVER = "http://127.0.0.1:8000"
HEARTBEAT_PERIOD_S = 2.0
FW_VERSION = "sim-1.0.0"


class MockNode:
    """One simulated ESP32. Owns its own thread and its own fake microsecond clock."""

    def __init__(
        self,
        node_id: str,
        server: str = DEFAULT_SERVER,
        gap_mm: float = 100.0,
        batt_mv: int = 4050,
        quiet: bool = False,
    ) -> None:
        self.node_id = node_id
        self.server = server.rstrip("/")
        self.gap_mm = gap_mm
        self.quiet = quiet

        self._seq = 0
        self._boot_wall = time.time()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Battery. Step 1 just drifts it slowly downward so the field is
        # populated and the plumbing is proven; Step 2 makes it mean something.
        self._batt_mv = batt_mv

        # An outbox, so a node that cannot reach the laptop does not lose the
        # ball it just measured. The real firmware needs this too - it is the
        # answer to "what happens when Wi-Fi disappears mid-run".
        self._outbox: list[tuple[str, dict[str, Any]]] = []
        self._outbox_lock = threading.Lock()

    # ------------------------------------------------------------ node clocks

    def _uptime_ms(self) -> int:
        return int((time.time() - self._boot_wall) * 1000)

    def _micros(self) -> int:
        """Stand-in for the ESP32's micros(). Monotonic, microsecond resolution."""
        return int((time.time() - self._boot_wall) * 1_000_000)

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _base_fields(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "fw": FW_VERSION,
            "proto": 1,
            "seq": self._next_seq(),
            "uptime_ms": self._uptime_ms(),
            "batt_mv": self._batt_mv,
            "batt_state": self._batt_state(),
            "rssi": random.randint(-72, -45),
        }

    def _batt_state(self) -> str:
        # Placeholder thresholds. Step 2 replaces these with values chosen for a
        # real 1S LiPo under ESP32 load, and the same thresholds go in firmware.
        mv = self._batt_mv
        if mv >= 3800:
            return "GREEN"
        if mv >= 3650:
            return "YELLOW"
        if mv >= 3500:
            return "RED"
        return "CRITICAL"

    # ---------------------------------------------------------------- sending

    def _post(self, path: str, body: dict[str, Any]) -> bool:
        try:
            r = requests.post(f"{self.server}{path}", json=body, timeout=2.0)
            if r.status_code == 404:
                # Server does not know this node_id. Shout, because this is a
                # config typo and it will not fix itself.
                self._log(f"REJECTED by server: {r.json().get('error')}")
                return True  # do not retry forever; the payload is wrong
            return r.ok
        except requests.RequestException:
            return False

    def _send_or_queue(self, path: str, body: dict[str, Any]) -> None:
        if not self._post(path, body):
            with self._outbox_lock:
                self._outbox.append((path, body))
                del self._outbox[50:]  # bounded, like real firmware RAM
            self._log("laptop unreachable - queued")

    def _drain_outbox(self) -> None:
        with self._outbox_lock:
            pending = list(self._outbox)
            self._outbox.clear()
        still_failing: list[tuple[str, dict[str, Any]]] = []
        for path, body in pending:
            if not self._post(path, body):
                still_failing.append((path, body))
        if still_failing:
            with self._outbox_lock:
                self._outbox[:0] = still_failing
        elif pending:
            self._log(f"reconnected - flushed {len(pending)} queued message(s)")

    def _log(self, msg: str) -> None:
        if not self.quiet:
            print(f"[{self.node_id}] {msg}", flush=True)

    # ----------------------------------------------------------------- events

    def send_boot(self) -> None:
        body = self._base_fields()
        body["event"] = "BOOT"
        body["note"] = "simulated node started"
        self._send_or_queue("/api/event", body)
        self._log("BOOT")

    def send_heartbeat(self) -> None:
        self._send_or_queue("/api/heartbeat", self._base_fields())

    def fire_ball(self, speed_mps: Optional[float] = None) -> float:
        """
        Simulate one clean ball pass and report it.

        Note the ordering, because it mirrors the real firmware: we work out
        dt and speed from the node's own clock FIRST, then transmit. Nothing
        about the network can influence the number we measured.
        """
        if speed_mps is None:
            speed_mps = random.uniform(0.35, 2.40)

        t_a = self._micros()
        dt_us = int((self.gap_mm / 1000.0) / speed_mps * 1_000_000)
        t_b = t_a + dt_us
        measured = (self.gap_mm / 1000.0) / (dt_us / 1_000_000)

        body = self._base_fields()
        body.update(
            {
                "event": "BALL_PASS",
                "t_a_us": t_a,
                "t_b_us": t_b,
                "dt_us": dt_us,
                "gap_mm": self.gap_mm,
                "speed_mps": round(measured, 4),
            }
        )
        self._send_or_queue("/api/event", body)
        self._log(f"BALL_PASS  dt={dt_us/1000:.1f} ms  speed={measured:.3f} m/s")
        return measured

    def fire_fault(self, kind: str = "BEAM_A_ONLY") -> None:
        """Simulate a misread, so you can see how the dashboard shows trouble."""
        body = self._base_fields()
        body["event"] = kind
        body["gap_mm"] = self.gap_mm
        body["note"] = "simulated fault"
        self._send_or_queue("/api/event", body)
        self._log(f"FAULT {kind}")

    # ------------------------------------------------------------ thread loop

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name=self.node_id, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self.send_boot()
        last_beat = 0.0
        while not self._stop.is_set():
            now = time.time()
            if now - last_beat >= HEARTBEAT_PERIOD_S:
                self._drain_outbox()
                self.send_heartbeat()
                # ~1 mV per beat: visible drift over a few minutes of demo.
                self._batt_mv = max(3300, self._batt_mv - 1)
                last_beat = now
            self._stop.wait(0.1)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)


def main() -> None:
    p = argparse.ArgumentParser(description="Simulate one ESP32 sensor node.")
    p.add_argument("--node-id", required=True, help="e.g. NODE01")
    p.add_argument("--server", default=DEFAULT_SERVER)
    p.add_argument("--gap-mm", type=float, default=100.0)
    p.add_argument("--batt-mv", type=int, default=4050)
    p.add_argument(
        "--interval",
        type=float,
        default=0.0,
        help="Seconds between automatic balls. 0 = only fire when you press ENTER.",
    )
    args = p.parse_args()

    node = MockNode(args.node_id, args.server, args.gap_mm, args.batt_mv)
    node.start()

    try:
        if args.interval > 0:
            print(f"Firing a ball every {args.interval}s. Ctrl+C to stop.")
            while True:
                time.sleep(args.interval)
                node.fire_ball()
        else:
            print("Press ENTER to send a ball. Type 'f' + ENTER for a fault. Ctrl+C to stop.")
            while True:
                line = input().strip().lower()
                if line == "f":
                    node.fire_fault()
                else:
                    node.fire_ball()
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        node.stop()


if __name__ == "__main__":
    main()
