I am designing the sensing and live-monitoring subsystem for a large modular marble-run engineering challenge.

Design ONLY the sensing, ESP32 communication and laptop GUI architecture.

PHYSICAL SYSTEM

Approximately 10 modules will be connected together.

Steel bearing ball:
- approximately 25 mm diameter.

Each measurement station has TWO optical break-beam points separated by a precisely known distance.

Example:

IR beam A                 IR beam B
    │                         │
    ▼                         ▼
    ●─────────────────────────●
             100 mm

             ↓
          steel ball

When the marble interrupts Beam A:
- record timestamp t1.

When it interrupts Beam B:
- record timestamp t2.

Then:

velocity = distance / (t2 - t1)

Each measurement station therefore provides:
- ball detected at entry
- ball detected at exit
- elapsed time
- calculated velocity.

SENSOR HARDWARE

Each beam consists of:
- 940 nm IR LED emitter
- bare IR phototransistor receiver

Do NOT use a 38 kHz TV-remote receiver module.

The sensor should be designed as a 3D-printed PETG sleeve/cartridge that mounts around/onto the PVC pathway.

The sensor should:
- be removable
- be repeatable
- align emitter and receiver reliably
- shield the receiver from ambient light
- work indoors and outdoors
- detect a 25 mm steel ball reliably.

Discuss:
- optical geometry
- aperture size
- sensor spacing
- ambient-light rejection
- pull-up resistor
- IR LED current limiting resistor
- phototransistor circuit
- whether comparator/Schmitt trigger is needed
- whether ESP32 ADC or digital GPIO should read the detector
- debounce/noise filtering
- false-trigger prevention.

ESP32

There will be approximately 20 ESP32 nodes.

The goal is to keep each sensor node self-contained and battery powered.

The ESP32 nodes connect over a local 2.4 GHz Wi-Fi network.

Router:
- TP-Link Archer AX53-class router
- no Internet required.

Laptop:
- connected to the same local network
- runs the central dashboard.

The network must work entirely offline.

NETWORK ARCHITECTURE

Design a robust architecture for approximately 20 ESP32 nodes.

Compare:
- HTTP
- WebSocket
- MQTT
- UDP
- TCP

Recommend the simplest reliable solution for this event.

The sensor event data is extremely small.

Each ESP32 should identify itself with a unique node ID, e.g.:

NODE01
NODE02
...
NODE20

Each event should contain at minimum:
- node ID
- sensor ID
- event type
- timestamp
- battery voltage
- Wi-Fi/connectivity status.

TIME SYNCHRONIZATION

This is important.

The laptop needs to calculate/display timing accurately enough for measuring marble velocity.

Explain:
- whether ESP32 local timestamps are sufficient
- whether NTP is suitable on a local router
- whether laptop time synchronization is required
- whether velocity should be calculated locally on each ESP32 rather than relying on laptop timestamps.

I suspect the ESP32 should calculate the interval between Beam A and Beam B locally because both sensors belong to the same node.

Evaluate this.

GUI

The laptop should have a live dashboard.

For each module/sensor station, display:

- NODE ID
- status: ONLINE/OFFLINE
- ball detected
- last ball timestamp
- measured time between beams
- calculated velocity
- battery state
- battery voltage
- communication health.

When a ball passes:

Example:

NODE03
BALL DETECTED
Time: 14:32:17.245
Δt: 0.842 s
Speed: 0.119 m/s
Battery: GREEN

The GUI should make the event visually obvious so there is no ambiguity about whether a ball actually passed a station.

I also want:
- event log
- timestamped records
- ability to reset/start a run
- overall elapsed event time
- module-by-module ball progression.

Potentially:

START → Module 1 → Module 2 → ... → Module 10 → FINISH

The system should detect where the ball currently is.

Please recommend a simple technology stack for the laptop GUI that is easy to build and deploy for an event.

For example:
- Python
- Flask/FastAPI
- WebSocket
- SQLite
- browser-based dashboard

Evaluate whether this is preferable to a native desktop application.

IMPORTANT CONSTRAINTS

This is a live event, so prioritize:

1. Reliability
2. Deterministic sensing
3. Simple debugging
4. Offline operation
5. Clear visualization
6. Minimal latency
7. Easy replacement of a failed ESP32 node
8. No dependence on cloud services
9. No Internet requirement.

Please provide:

1. Complete sensor circuit
2. Recommended components and values
3. ESP32 GPIO allocation
4. Sensor firmware architecture
5. Event packet/message format
6. Network architecture
7. Time synchronization strategy
8. Local velocity calculation strategy
9. Laptop server architecture
10. GUI layout
11. Data model
12. Fault handling
13. Offline startup procedure
14. Testing procedure for 1 node
15. Testing procedure for 20 nodes
16. Recommended final architecture.

Be technically rigorous but avoid unnecessary complexity. The goal is a robust event prototype that can later be replicated across 20 sensor nodes.

IMPORTANT ARCHITECTURAL PREFERENCE

For the ball-pass system, strongly consider calculating speed locally on the ESP32.

The preferred flow is:

Beam A → ESP32 timestamp → Beam B → ESP32 timestamp → calculate Δt → calculate speed → send one completed event to laptop.

Wi-Fi latency should NOT affect the actual speed measurement.

The laptop should receive the completed measurement and display/log it.

Also explain how the ESP32 should handle:
- a Beam B trigger without a preceding Beam A trigger
- multiple triggers caused by one ball
- a ball stopping between the two beams
- a second ball arriving too quickly
- sensor noise
- Wi-Fi temporarily disappearing
- ESP32 rebooting
- low battery.

Recommend sensible timeout, debounce and state-machine logic for these cases.