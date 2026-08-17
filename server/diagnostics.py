"""
Turns node telemetry into "here is what is wrong and here is what to check".

The physical node already tells you one thing on its own: if the RGB LED is
blank, it has no power - flat battery, switch off, or a broken power
connection. Nobody needs a dashboard for that.

So everything here is about the failures where the node IS powered and the LED
IS lit, but something is still wrong. Those are the ones you cannot diagnose by
walking up and looking at it.

Every finding carries concrete physical checks, in the order worth trying.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from server.store import NodeState

# Severity drives sort order and colour. "critical" = this station is not
# working right now. "warning" = it works but will bite you. "info" = worth
# knowing, no action needed yet.
CRITICAL = "critical"
WARNING = "warning"
INFO = "info"

# Below this, Wi-Fi gets unreliable on a crowded 2.4 GHz band in a hall full
# of people. -80 is where packets start disappearing in practice.
RSSI_POOR = -78
RSSI_MARGINAL = -70

# A node that reboots more than this during one event is not just unlucky.
REBOOT_ALARM = 3

# Packet loss above this is a real network problem, not noise.
LOSS_ALARM_PCT = 5.0


def _finding(sev: str, code: str, title: str, detail: str, checks: list[str]) -> dict[str, Any]:
    return {
        "severity": sev,
        "code": code,
        "title": title,
        "detail": detail,
        "checks": checks,
    }


def diagnose_node(
    node: NodeState,
    any_peer_has_balls: bool,
    now: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Findings for one node, most severe first."""
    now = now or time.time()
    out: list[dict[str, Any]] = []

    # ---------------------------------------------------------- not reporting

    if not node.ever_seen:
        out.append(
            _finding(
                CRITICAL,
                "NEVER_SEEN",
                "Never reported since the server started",
                "This node has not sent a single packet. It is either not powered, "
                "not on the Wi-Fi, or pointed at the wrong laptop.",
                [
                    "Look at the node's RGB LED. Blank = no power: check the switch, "
                    "the battery JST plug, and that the cell is charged.",
                    "LED lit? Then it has power but no network. Check the Wi-Fi SSID "
                    "and password compiled into the firmware.",
                    "Check the laptop IP in the firmware matches this laptop "
                    "(run 'ipconfig'). A changed IP is the single most common cause.",
                    "Check node_id in the firmware exactly matches config/nodes.json. "
                    "A typo gets rejected with HTTP 404 - watch the server terminal.",
                    "Confirm Windows Firewall allows inbound TCP port 8000 on the "
                    "private network.",
                ],
            )
        )
        return out  # nothing else is knowable about a node we've never heard from

    if not node.online:
        quiet_s = int(now - (node.last_seen_wall or now))

        # We can often say WHY it dropped, from its dying words.
        if node.last_seen_batt_state in ("RED", "CRITICAL"):
            out.append(
                _finding(
                    CRITICAL,
                    "OFFLINE_BATTERY",
                    f"Dropped out {quiet_s}s ago - battery was {node.last_seen_batt_state}",
                    "Its last report showed a low battery, so it almost certainly "
                    "browned out. Wi-Fi transmit current is what finally kills a "
                    "sagging LiPo.",
                    [
                        "Swap or recharge the cell. This one is done for the session.",
                        "The RGB LED will be blank - that confirms it, no need to probe.",
                    ],
                )
            )
        elif node.last_seen_rssi is not None and node.last_seen_rssi <= RSSI_POOR:
            out.append(
                _finding(
                    CRITICAL,
                    "OFFLINE_SIGNAL",
                    f"Dropped out {quiet_s}s ago - signal was weak ({node.last_seen_rssi} dBm)",
                    "It was already on the edge of Wi-Fi range when it went quiet.",
                    [
                        "If the RGB LED is still lit, it has power and lost Wi-Fi - "
                        "move the node or the router closer.",
                        "Check nothing metal was placed between the node and the router.",
                        "Router on 2.4 GHz and not hidden? Nodes cannot see 5 GHz.",
                    ],
                )
            )
        else:
            out.append(
                _finding(
                    CRITICAL,
                    "OFFLINE",
                    f"Stopped reporting {quiet_s}s ago",
                    "It was healthy and then went silent, with no warning sign in "
                    "its last packet.",
                    [
                        "Check the RGB LED first - it splits the problem in half.",
                        "LED blank -> power. Switch knocked off, JST unplugged, "
                        "or the battery finally gave out.",
                        "LED lit -> Wi-Fi. It has power but lost the router; it should "
                        "rejoin on its own within a few seconds.",
                        "Still nothing? Power-cycle the node and watch for a BOOT event.",
                    ],
                )
            )
        # Fall through: stale counters below are still worth reporting.

    # ---------------------------------------------------------------- battery

    if node.batt_state == "CRITICAL":
        out.append(
            _finding(
                CRITICAL,
                "BATT_CRITICAL",
                "Battery critically low",
                "This node is minutes from dropping off the network.",
                ["Swap the cell now, before the next run.",
                 "The node's own RGB LED is flashing red to match."],
            )
        )
    elif node.batt_state == "RED":
        out.append(
            _finding(
                WARNING,
                "BATT_LOW",
                "Battery low",
                "Still working, but it will not last the session.",
                ["Swap or recharge at the next reset."],
            )
        )
    elif node.batt_state == "YELLOW":
        out.append(
            _finding(
                INFO,
                "BATT_YELLOW",
                "Battery getting low",
                "Fine for now. Worth having a charged spare to hand.",
                ["No action needed yet - keep an eye on it."],
            )
        )

    # ------------------------------------------------------------- rebooting

    if node.boot_count > REBOOT_ALARM:
        out.append(
            _finding(
                WARNING,
                "REBOOTING",
                f"Rebooted {node.boot_count} times",
                "Repeated reboots almost always mean the supply is collapsing when "
                "the Wi-Fi radio transmits, not a software fault.",
                [
                    "Battery sag: a tired or very small LiPo cannot deliver the ~250 mA "
                    "burst the ESP32 draws on transmit. Try a freshly charged cell.",
                    "Check the battery JST-XH plug is fully seated and the crimps are sound.",
                    "Check for a cold solder joint on the power rail - reflow the "
                    "battery, switch and 3V3 connections.",
                    "Add a bulk capacitor (470-1000 uF) across the ESP32 supply pins "
                    "if it persists.",
                ],
            )
        )

    # ----------------------------------------------------------- packet loss

    delivered = node.total_msgs
    lost = node.missed_seq
    if delivered + lost > 20 and lost > 0:
        loss_pct = 100.0 * lost / (delivered + lost)
        if loss_pct >= LOSS_ALARM_PCT:
            out.append(
                _finding(
                    WARNING,
                    "PACKET_LOSS",
                    f"Losing {loss_pct:.1f}% of packets ({lost} missed)",
                    "Messages from this node are not all arriving. A lost heartbeat is "
                    "cosmetic; a lost BALL_PASS is a missed measurement.",
                    [
                        "Check signal strength below - weak signal is the usual cause.",
                        "Move the node away from metal structure and other nodes' "
                        "antennas.",
                        "If many nodes show this, the 2.4 GHz band is congested - "
                        "change the router's channel to 1, 6 or 11, whichever is quietest.",
                    ],
                )
            )

    # --------------------------------------------------------- signal quality

    if node.online and node.rssi is not None:
        if node.rssi <= RSSI_POOR:
            out.append(
                _finding(
                    WARNING,
                    "RSSI_POOR",
                    f"Weak Wi-Fi signal ({node.rssi} dBm)",
                    "Below about -78 dBm, packets start disappearing in a hall full "
                    "of people.",
                    [
                        "Move the router closer, or higher, or more central.",
                        "Keep the ESP32 antenna end clear of metal and out of the "
                        "3D-printed housing's shadow.",
                        "Do not coil the node's wiring around the antenna.",
                    ],
                )
            )
        elif node.rssi <= RSSI_MARGINAL:
            out.append(
                _finding(
                    INFO,
                    "RSSI_MARGINAL",
                    f"Marginal Wi-Fi signal ({node.rssi} dBm)",
                    "Working, but with less headroom than the others.",
                    ["Fine for now. If it starts losing packets, move it first."],
                )
            )

    # ------------------------------------------------------------ beam faults

    if node.fault_a_only > 0:
        out.append(
            _finding(
                WARNING,
                "BEAM_A_ONLY",
                f"Beam A triggered without beam B ({node.fault_a_only}x)",
                "The ball broke the first beam and then never reached the second. "
                "Either beam B is not seeing it, or the ball never got there.",
                [
                    "Check beam B alignment first: IR LED and phototransistor must "
                    "face each other squarely across the pipe.",
                    "Confirm beam B's IR LED is actually lit - view it through a phone "
                    "camera, 940 nm shows up as pale violet on most sensors.",
                    "Check the phototransistor is the right way round: the LONGER leg "
                    "is the collector and goes to 3V3, short leg to the pull-down "
                    "and the GPIO.",
                    "Is the ball physically stopping or jumping the gap? Watch one "
                    "roll through by eye.",
                    "Direct sunlight or hall lighting on beam B's receiver will "
                    "saturate it so it never sees a break. Shroud it.",
                ],
            )
        )

    if node.fault_b_only > 0:
        out.append(
            _finding(
                WARNING,
                "BEAM_B_ONLY",
                f"Beam B triggered without beam A ({node.fault_b_only}x)",
                "The second beam fired with no first beam. Either beam A missed the "
                "ball entirely, or something came through backwards.",
                [
                    "Check beam A alignment and that its IR LED is lit.",
                    "Check beam A's current-limiting resistor is not open or "
                    "mis-valued - a dim emitter reads as no beam break at all.",
                    "Is the ball rolling backwards at this station? Check the pipe "
                    "gradient.",
                    "Swap beam A's phototransistor with a known-good one to isolate it.",
                ],
            )
        )

    if node.fault_timeout > 0:
        out.append(
            _finding(
                WARNING,
                "BALL_STALLED",
                f"Ball stalled between the beams ({node.fault_timeout}x)",
                "Beam A broke and the node waited out its timeout without seeing "
                "beam B. This usually means a physical blockage, not electronics.",
                [
                    "Check the pipe gradient at this station - it may be too shallow.",
                    "Check for a step, burr or lip at a pipe coupler that is catching "
                    "the ball.",
                    "Confirm the sensor sleeve is not intruding into the pipe bore.",
                ],
            )
        )

    if node.implausible_count > 0:
        out.append(
            _finding(
                WARNING,
                "IMPLAUSIBLE_SPEED",
                f"Implausible speed recorded ({node.implausible_count}x)",
                "A measurement came back far too fast to be a 25 mm ball. The node "
                "timed something that was not a ball passing.",
                [
                    "Most likely one beam double-triggered on the ball's edge. "
                    "Increase the debounce window in firmware.",
                    "Check for a floating input: the phototransistor needs its "
                    "pull-down resistor fitted, or the GPIO reads noise.",
                    "Keep the sensor wiring short and away from the ESP32 antenna.",
                    "Check gap_mm in config/nodes.json matches the real beam spacing.",
                ],
            )
        )

    # ------------------------------------------- online but sensing nothing

    if node.online and node.ball_count == 0 and node.fault_count == 0 and any_peer_has_balls:
        out.append(
            _finding(
                WARNING,
                "NO_DETECTIONS",
                "Online and healthy, but has never detected a ball",
                "Other stations are reporting balls and this one is not. The node is "
                "fine; the optics are not.",
                [
                    "Check both IR LEDs are lit (look through a phone camera).",
                    "Check emitter and receiver line up across the pipe bore - a few "
                    "degrees off and the ball never breaks the beam cleanly.",
                    "Check the phototransistor orientation: longer leg = collector.",
                    "Check ambient light is not saturating the receiver. Black PETG "
                    "shrouds exist for exactly this.",
                    "Confirm balls are actually reaching this station.",
                ],
            )
        )

    if not out:
        out.append(
            _finding(
                INFO,
                "OK",
                "No problems detected",
                "Online, reporting, battery and signal healthy.",
                [],
            )
        )

    order = {CRITICAL: 0, WARNING: 1, INFO: 2}
    out.sort(key=lambda f: order[f["severity"]])
    return out


def diagnose_all(nodes: list[NodeState]) -> dict[str, Any]:
    now = time.time()
    any_balls = any(n.ball_count > 0 for n in nodes)

    per_node = []
    n_crit = n_warn = 0
    for node in sorted(nodes, key=lambda x: x.order):
        findings = diagnose_node(node, any_balls, now)
        n_crit += sum(1 for f in findings if f["severity"] == CRITICAL)
        n_warn += sum(1 for f in findings if f["severity"] == WARNING)
        per_node.append(
            {
                "node_id": node.node_id,
                "label": node.label,
                "online": node.online,
                "worst": findings[0]["severity"],
                "findings": findings,
            }
        )

    return {
        "generated_wall": now,
        "critical": n_crit,
        "warnings": n_warn,
        "nodes": per_node,
    }
