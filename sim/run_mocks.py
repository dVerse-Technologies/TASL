"""
Run the whole simulated marble run: 3 fake ESP32s plus a ball that travels
NODE01 -> NODE02 -> NODE03 with realistic gaps between stations.

    python sim/run_mocks.py

Controls (type in this window, then ENTER):
    <enter>   launch one ball down the course
    a         auto mode on/off - a new ball every ~18 seconds
    f         inject a fault at a random node
    d         drop NODE02 offline (stops its heartbeat) - watch the dashboard
    u         bring NODE02 back
    q         quit
"""

from __future__ import annotations

import json
import random
import sys
import threading
import time
from pathlib import Path

# Allow "python sim/run_mocks.py" from the project root without installing.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from sim.mock_node import MockNode  # noqa: E402

SERVER = "http://127.0.0.1:8000"
AUTO_PERIOD_S = 18.0


def load_nodes() -> list[dict]:
    with open(ROOT / "config" / "nodes.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return sorted(cfg["nodes"], key=lambda n: n["order"])


class Course:
    """Drives a ball down the line of stations."""

    def __init__(self, nodes: list[MockNode]) -> None:
        self.nodes = nodes
        self.auto = False
        self._busy = threading.Lock()

    def launch_ball(self) -> None:
        if not self._busy.acquire(blocking=False):
            print("  (a ball is already on the course)")
            return
        threading.Thread(target=self._travel, daemon=True).start()

    def _travel(self) -> None:
        try:
            print("\n--- ball launched ---")
            # Balls generally lose energy along a gravity-fed run, so start
            # fastish and decay. Jitter keeps the dashboard from looking fake.
            speed = random.uniform(1.6, 2.3)
            for i, node in enumerate(self.nodes):
                node.fire_ball(speed_mps=speed)
                speed = max(0.30, speed * random.uniform(0.62, 0.88))
                if i < len(self.nodes) - 1:
                    # Time for the ball to physically travel to the next station.
                    time.sleep(random.uniform(1.5, 3.5))
            print("--- ball reached FINISH ---\n")
        finally:
            self._busy.release()

    def auto_loop(self, stop: threading.Event) -> None:
        while not stop.is_set():
            if self.auto:
                self.launch_ball()
                stop.wait(AUTO_PERIOD_S)
            else:
                stop.wait(0.5)


def wait_for_server() -> bool:
    print(f"Looking for the dashboard server at {SERVER} ...")
    for _ in range(20):
        try:
            if requests.get(f"{SERVER}/api/state", timeout=1.0).ok:
                print("Server found.\n")
                return True
        except requests.RequestException:
            pass
        time.sleep(0.5)
    print("\nCould not reach the server.")
    print("Open another terminal, run 'python run_server.py' first, then re-run this.\n")
    return False


def main() -> None:
    if not wait_for_server():
        return

    cfg_nodes = load_nodes()
    # Slightly different starting voltages so the battery column isn't uniform.
    start_mv = [4050, 3900, 3720]
    nodes = [
        MockNode(
            node_id=n["node_id"],
            server=SERVER,
            gap_mm=float(n["gap_mm"]),
            batt_mv=start_mv[i % len(start_mv)],
        )
        for i, n in enumerate(cfg_nodes)
    ]
    for n in nodes:
        n.start()
        time.sleep(0.15)  # stagger boots so the log reads cleanly

    course = Course(nodes)
    stop = threading.Event()
    threading.Thread(target=course.auto_loop, args=(stop,), daemon=True).start()

    print(__doc__.split("Controls")[1].replace("(type in this window, then ENTER):", "").strip())
    print()

    dropped: dict[str, MockNode] = {}
    try:
        while True:
            cmd = input().strip().lower()
            if cmd == "q":
                break
            elif cmd == "a":
                course.auto = not course.auto
                print(f"  auto mode: {'ON' if course.auto else 'OFF'}")
            elif cmd == "f":
                random.choice(nodes).fire_fault(random.choice(["BEAM_A_ONLY", "TIMEOUT"]))
            elif cmd == "d":
                target = nodes[1] if len(nodes) > 1 else nodes[0]
                if target.node_id not in dropped:
                    target.stop()
                    dropped[target.node_id] = target
                    print(f"  {target.node_id} powered down - it should go OFFLINE in ~6s")
            elif cmd == "u":
                for node_id, target in list(dropped.items()):
                    fresh = MockNode(node_id, SERVER, target.gap_mm, target._batt_mv)
                    fresh.start()
                    idx = next(i for i, n in enumerate(nodes) if n.node_id == node_id)
                    nodes[idx] = fresh
                    del dropped[node_id]
                    print(f"  {node_id} powered back up")
            else:
                course.launch_ball()
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop.set()
        for n in nodes:
            n.stop()
        print("\nSimulated nodes stopped.")


if __name__ == "__main__":
    main()
