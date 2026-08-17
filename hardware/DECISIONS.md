# Hardware decision log

Why the node is built the way it is. Each entry records the decision, the
reasoning, and what it replaced — so a choice that looks arbitrary six months
from now can be re-examined against the reason it was made.

Where this file and [`NODE_WIRING.md`](NODE_WIRING.md) disagree, **this file
and [`BEAM_CIRCUIT.md`](BEAM_CIRCUIT.md) win** — they record what was actually
built and measured. `NODE_WIRING.md` is the original design study and still
holds the rationale for the parts that didn't change.

---

## D1 — ESP32 DevKit V1 (30-pin DOIT)

**Decided:** the 30-pin DOIT DevKit V1, not the 36-pin DevKitC.

Pin *positions* differ between the two, so every wiring table in this repo is
specific to the 30-pin board. Substituting a DevKitC without re-checking the
pinout will put the beams on the wrong pins.

Constraints that follow and drive everything else:

- **ADC2 is unusable.** It shares hardware with the Wi-Fi radio and stops
  returning valid readings the moment Wi-Fi is up. Every analog input must be
  on **ADC1** (GPIO32–39). A battery divider on ADC2 tests perfectly on the
  bench and reads zero in the field.
- **GPIO6–11** are wired to the onboard SPI flash. Using them prevents boot.
- **GPIO34–39** are input-only with no internal pull-ups — fine for the ADC,
  useless for driving anything.
- The onboard **AMS1117** needs ~1.1 V of dropout, which rules out feeding
  `VIN` from a LiPo (see D2).

---

## D2 — Power: LiPo → TP4056 → switch → MT3608 → AMS1117 → `3V3` pin

**Decided:** boost the cell to 5 V, regulate back down to 3.3 V externally, and
feed the ESP32's **`3V3` pin** directly. `VIN` is left unconnected.

```
LiPo ──> TP4056 ──> SPST ──> MT3608 ──> AMS1117-3.3 ──┬──> +3V3 rail
1000mAh  +protect   switch   boost 5V    regulator     │
                                                  [1000 µF]
GND ───────────────────────────────────────────────────┴──> GND
```

**Superseded:** the earlier plan fed the MT3608's 5 V straight into `VIN` and
let the onboard regulator make 3.3 V.

**Why it changed:** the sensors want a clean rail that isn't sharing the
onboard regulator with the ESP32's own transient load. Feeding `3V3` from an
external AMS1117 gives both the MCU and the optics a quieter supply. **NODE02
browning out** during testing is what prompted the change.

**Why not simpler options:**

| Option | Why it fails |
|---|---|
| LiPo → `VIN` | AMS1117 needs ≥4.4 V in. A cell starts at 4.2 V and falls. Brownout immediately. |
| LiPo → `3V3` | `3V3` sits on the 3.3 V rail. A charged cell at 4.2 V is 0.9 V over rating — damages the board. |
| LM2596 buck, 3.7 → 3.3 V | Datasheet minimum input is **4.5 V**; a 3.7 V cell is already below it. And no buck makes 3.3 V from a cell sagging to 3.0 V. It also idles at 5–10 mA. |
| AMS1117 fed straight from the LiPo | Same dropout problem: 3.7 V in gives ~2.6 V out. This was the NODE02 brownout. |

**Consequences that must be respected:**

- `VIN` stays **disconnected**. Feeding both `VIN` and `3V3` fights the onboard
  regulator.
- **Switch OFF before plugging in USB**, every time. The switch sits before the
  boost so that switching off fully disconnects the battery supply.
- The **1000 µF is polarised** — negative stripe to GND. Backwards, it vents.
  It absorbs the ~250 mA spike on each Wi-Fi transmit.
- The AMS1117 dissipates `(5.0 − 3.3) × 0.15 ≈ 0.26 W`. Warm is normal; too hot
  to hold means something is drawing far more than it should.

---

## D3 — Every MT3608 is set to 5.0 V before it is connected

**Decided:** adjust and lock every boost module on the bench, before it ever
touches an ESP32.

MT3608 modules are adjustable and ship at an **arbitrary** setting, with a
range up to 28 V. Connecting an unadjusted one destroys the board instantly.

Procedure: power the input from a cell → **nothing on the output** → meter the
output pads → turn the multi-turn pot to **5.0 V** → disconnect → then wire it
in → lock the pot with nail varnish.

---

## D4 — TP4056 **with protection** (DW01A + 8205A)

**Decided:** only the protected variant.

The bare TP4056 has no over-discharge cutoff and will flatten a LiPo until it
is damaged and potentially unsafe. The protected board carries **three** ICs:
`TP4056`, `DW01A` (6-pin, near `B−`), and `8205A` (8-pin dual MOSFET). If the
board has only the TP4056 chip, it is the wrong part.

The battery connects to `B+`/`B−` and **nothing else** — the protection sits
between `B` and `OUT`, so tapping the cell directly bypasses it.

Charging goes through `IN`/`B` and does not pass through the switch, so
**charging works with the node switched off**.

---

## D5 — Battery: 1000 mAh for production, 500 mAh for prototyping

**Decided:** 1000 mAh 1S LiPo for the 20-node build. The 3× 500 mAh cells on
hand are fine for prototyping.

The event runs **4 hours**, but nodes are powered for longer — setup, teams
building, dry runs, teardown. Design for **~6 hours of switch-on time**.

| Cell | Worst case | Likely | With firmware wins |
|---|---|---|---|
| 500 mAh | 2.8 h | 4.5 h | ~6.5 h |
| **1000 mAh** | **5.5 h** | **9 h** | **~13 h** |
| 2000 mAh | 11 h | 18 h | ~26 h |

1000 mAh clears the requirement even in the worst case, and needs **no TP4056
modification** — stock 1000 mA charge is 1C. A 500 mAh cell would be charged at
2C and need `R_prog` changed on all 20 modules.

**Rejected: 2× 500 mAh in parallel.** Electrically fine, but 40 cells, 40 extra
joints, larger total volume, usually more cost, and a voltage-matching step
repeated 20 times. Cells joined at differing charge can pass several amps
between themselves — the standard way people get hurt paralleling LiPos.

**Still to measure:** actual current draw. Every figure above is calculated. A
multimeter in series with the battery settles it in ten minutes.

---

## D6 — Beam values: 220 Ω emitter, 100 kΩ pull-down

**Decided:** 220 Ω IR emitter current limit, **100 kΩ** phototransistor
pull-down, at a 40 mm beam gap across the pipe.

**Superseded:** the theoretical 100 Ω / 10 kΩ in `NODE_WIRING.md §8`.

**Why it changed:** measured on the bench. The **100 kΩ pull-down took usable
range from ~5 mm to comfortably past 40 mm.** A 10 kΩ only works with the parts
almost touching — useless across a 40 mm pipe.

The higher pull-down makes the receiver more sensitive, which would normally
raise ambient-light risk. It is safe here because **the pipe wall itself is the
shroud** (D7).

Beam clear → phototransistor conducts → GPIO **HIGH**.
Ball blocks it → 100 kΩ pulls it **LOW**. A ball passing is a **falling edge**.

---

## D7 — Sensors mount through the pipe wall

**Decided:** 5 mm holes drilled directly opposite each other, parts pushed
flush with the inner wall, hot-glued from outside. Beam sits **~12 mm up from
the inner floor**.

A 25 mm ball in a ~40 mm pipe rolls along the bottom, so 12 mm is its centre
line and it always blocks the beam fully.

Flush mounting is not cosmetic — anything protruding into the bore gets struck
by the ball.

The pipe wall doubling as an ambient-light shroud is what makes the sensitive
100 kΩ pull-down viable (D6), and removes the need for separate 3D-printed
shrouds.

---

## D8 — Beams on D19 / D18, battery on D34

**Decided:**

| GPIO | Function | Note |
|---|---|---|
| `D19` | Beam A signal | digital only |
| `D18` | Beam B signal | digital only |
| `D34` | Battery sense | ADC1, input-only |

**Superseded:** GPIO32/33 for beams in the original plan.

**Trade-off accepted:** D19 and D18 are **not** ADC pins, so `analogRead()`
does not work on them and the alignment sketch runs in digital mode
(`BEAM_ANALOG 0`). Ball timing only needs digital edges, so nothing is lost for
the measurement — but fine aiming by raw analog level is no longer available on
those pins.

`D34` must stay on ADC1 (D1).

---

## D9 — No comparator, for now

**Decided:** phototransistor straight into the GPIO, with debouncing handled in
firmware. No LM393.

A comparator gives crisper edges and better ambient-light immunity, but adds a
trimpot per beam — **40 trimpots to calibrate** across 20 nodes.

The dashboard's troubleshooting panel reports **"Implausible speed recorded"**
and **"Beam A triggered without beam B"**. If a station keeps reporting those
after alignment is confirmed, add an LM393 to *that station*. The decision is
deferred until there is evidence, rather than paying the calibration cost up
front on a guess.

---

## D10 — Velocity is computed on the node, never on the laptop

**Decided:** each node times both beams against its own `micros()` clock,
computes Δt and speed, and transmits one finished measurement.

```
beam A → micros()  ─┐
beam B → micros()   ├─ all on-node, before the radio is touched
compute Δt, speed  ─┘
                    → then transmit
```

**Why:** Wi-Fi latency, packet retries, reconnects and laptop clock drift can
then only affect *when a result is displayed*, never the result itself. It also
removes any need for NTP or clock sync between nodes — each node only ever
compares two of its own timestamps.

This is why Wi-Fi modem sleep can be left on: it delays inbound traffic, which
this design never depends on.

---

## D11 — `gap_mm` is measured, not assumed

**Decided:** the beam A → beam B spacing is measured on each finished assembly
and recorded per station in `config/nodes.json` and in that node's firmware.

`speed = gap_mm / Δt`, so a 2 mm error over a 100 mm gap is a **2% error on
every reading that station ever produces** — and nothing downstream can detect
it. It is the one number in the system with no error-checking behind it.

Note it is the spacing **along** the pipe, not the ~40 mm across it.

---

## Open items

| Item | Needed before |
|---|---|
| Measure real current draw with a multimeter | ordering 20 cells |
| Confirm `WiFi.setSleep(true)` and `setCpuFrequencyMhz(80)` savings | firmware freeze |
| Calibrate ADC per board against a multimeter | battery thresholds are trustworthy |
| Decide RGB LED common cathode vs anode from the parts in hand | LED wiring is soldered |
| Measure `gap_mm` per station | any speed reading is meaningful |
