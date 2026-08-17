"""
TASL wire protocol - the contract between an ESP32 node and the laptop.

THIS FILE IS THE SPEC. The mock simulator (sim/mock_node.py) and the real
ESP32 firmware must both produce exactly these fields. If you change anything
here, you have to change the firmware too - so try not to.

Two messages, both HTTP POST with a JSON body:

  POST /api/heartbeat   every 2 seconds, always
  POST /api/event       only when something happened (ball, fault, boot)

Design rule that matters:
  The NODE computes dt_us and speed_mps itself, from its own microsecond clock,
  before it ever touches Wi-Fi. The laptop never times anything. That is why
  Wi-Fi latency, packet retries and laptop clock drift cannot corrupt a
  velocity measurement.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

PROTOCOL_VERSION = 1

# What a node can report. Keep this list short and explicit - the dashboard
# switches on it, and so will you at 2am when a station misbehaves.
EventType = Literal[
    "BOOT",         # node just powered up / rebooted
    "BALL_PASS",    # clean pass: beam A then beam B. Has dt_us and speed_mps.
    "BEAM_A_ONLY",  # beam A broke, beam B never did within the timeout
    "BEAM_B_ONLY",  # beam B broke with no preceding beam A (ball came backwards?)
    "TIMEOUT",      # ball appears to have stopped between the beams
    "LOW_BATTERY",  # battery crossed a warning threshold
]

BatteryState = Literal["GREEN", "YELLOW", "RED", "CRITICAL", "UNKNOWN"]


class Heartbeat(BaseModel):
    """Sent every 2s so the laptop knows the node is alive and how it feels."""

    node_id: str = Field(..., description="Unique node name, e.g. NODE01")
    fw: str = Field("0.0.0", description="Firmware version string")
    proto: int = Field(PROTOCOL_VERSION, description="Protocol version")
    seq: int = Field(0, description="Increments per message; lets us spot drops")
    uptime_ms: int = Field(0, description="Node millis() since boot")

    batt_mv: Optional[int] = Field(None, description="Battery millivolts, e.g. 3820")
    batt_state: BatteryState = Field("UNKNOWN")
    rssi: Optional[int] = Field(None, description="Wi-Fi signal, dBm, e.g. -55")


class NodeEvent(Heartbeat):
    """
    A thing that happened. Inherits every heartbeat field, so one event also
    refreshes liveness and battery - a node that is reporting balls is
    obviously online.
    """

    event: EventType = Field(..., description="What happened")

    # Timing. All from the node's own micros() clock. Present on BALL_PASS.
    t_a_us: Optional[int] = Field(None, description="micros() when beam A broke")
    t_b_us: Optional[int] = Field(None, description="micros() when beam B broke")
    dt_us: Optional[int] = Field(None, description="t_b_us - t_a_us")

    # Measurement. gap_mm is echoed by the node so the log is self-describing:
    # if someone re-spaces a sensor sleeve mid-event, the record still says
    # which distance the speed was computed from.
    gap_mm: Optional[float] = Field(None, description="Beam A to beam B, mm")
    speed_mps: Optional[float] = Field(None, description="gap_mm / dt_us, in m/s")

    note: Optional[str] = Field(None, description="Free text for humans")
