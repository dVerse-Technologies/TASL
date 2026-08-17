# IR beam circuit — as built and tested

Values below are the ones that actually worked on the bench at a 40 mm beam
gap, not the theoretical values in NODE_WIRING.md §8.

| Part | Value | Colour code |
|---|---|---|
| IR emitter current limit | **220 Ω** | red, red, brown, gold |
| Phototransistor pull-down | **100 kΩ** | brown, black, yellow, gold |

The 100 kΩ pull-down is what took the range from ~5 mm to comfortably past
40 mm. A 10 kΩ works only with the parts almost touching.

---

## One beam

```
   +3V3 ────┬──────────────────────────────┐
            │                              │
         [220 Ω]                           │
            │                              │
            │  long leg (anode)            │  COLLECTOR
            ▼                              ▼
         ┌─────┐                        ┌─────┐
         │ IR  │  ) ) )  40 mm  ( ( (   │photo│
         │ LED │ ──────────────────────>│trans│
         └─────┘                        └─────┘
            │  short leg (cathode)          │  EMITTER
            │                              │
            │                              ├──────────> GPIO
            │                              │
            │                          [100 kΩ]
            │                              │
   GND  ────┴──────────────────────────────┴────

   Beam clear   -> phototransistor conducts -> GPIO reads HIGH
   Beam blocked -> phototransistor off      -> GPIO pulled LOW
```

A ball passing is a **falling edge**.

---

## Power — AMS1117 + 1000 µF

```
  LiPo      TP4056     SPST      MT3608        AMS1117-3.3
 1000mAh   +protect   switch   boost to 5.0V    regulator
    │         │         │          │                │
    ●─────────●─────────●──────────●────────────────●──────┬──── +3V3 rail
                                                           │
                                                     [1000 µF 16V]
                                                           │
   GND ────────────────────────────────────────────────────┴──── GND
```

The +3V3 rail feeds the **ESP32 `3V3` pin**, both IR emitters and both
phototransistors.

### Three things that will destroy a board if you get them wrong

**The AMS1117 must be fed from the 5 V boost, never from the LiPo.** It needs
about 1.1 V of dropout, so at least 4.4 V in to give 3.3 V out. A 3.7 V cell
straight into it produces roughly 2.6 V and the ESP32 will not run —
that is the same brownout that took NODE02 offline.

```
5.0 V in − 3.3 V out = 1.7 V headroom   ✓  (needs > 1.1 V)
```

**Feeding the `3V3` pin bypasses the ESP32's onboard regulator.** That is the
point — it is why the sensors get a clean rail. But it means `VIN` must be left
unconnected, and the **switch must be OFF before you plug in USB**, every time.

**The 1000 µF is polarised.** Its negative stripe goes to GND. Backwards, it
vents. It sits across the 3V3 rail as close to the ESP32 as you can get it, and
it is what absorbs the ~250 mA current spike each Wi-Fi transmit draws.

A 100 nF ceramic in parallel with it, right at the ESP32 pins, is worth adding
if you have one — the electrolytic is too slow for high-frequency noise.

### Heat

The AMS1117 burns the difference as heat:

```
(5.0 − 3.3) V × 0.15 A ≈ 0.26 W
```

Warm to the touch is normal. Too hot to hold means something is drawing far
more than it should — switch off and find it before it fails.

---

## Both beams on one node

```
                    ESP32 DevKit V1
                   ┌─────────────────┐
   +3V3 rail ──────┤ 3V3             │
       GND ────────┤ GND             │
                   │                 │
   beam A sig ─────┤ D19             │
   beam B sig ─────┤ D18             │
                   │                 │
   batt divider ───┤ D34             │
                   │                 │
        (unused) ──┤ VIN             │   ← leave disconnected
                   └─────────────────┘
```

Beam A and beam B are **electrically identical**. Build one, test it, then
build the second the same way.

---

## Connection table

Repeat every row for beam B, substituting **D18** for **D19**.

| From | To |
|---|---|
| `3V3` | 220 Ω, leg 1 |
| 220 Ω, leg 2 | IR LED **long leg** (anode) |
| IR LED **short leg** (cathode) | `GND` |
| `3V3` | phototransistor **collector** |
| phototransistor **emitter** | `D19` |
| phototransistor **emitter** | 100 kΩ, leg 1 |
| 100 kΩ, leg 2 | `GND` |

---

## Mounting through the PVC pipe

- Drill **5 mm holes directly opposite** each other, on the same axis.
- Beam sits **~12 mm up from the inner floor** — a 25 mm ball in a 40 mm pipe
  rolls along the bottom, so that height is its centre and it always blocks
  fully.
- Push both parts in **flush with the inner wall**. Anything protruding gets
  hit by the ball.
- Hot glue from the outside.

The pipe wall doubles as the ambient-light shroud, which is what makes the
sensitive 100 kΩ pull-down safe to use.

---

## gap_mm

The distance between **beam A and beam B** along the pipe — not the 40 mm
across it. Measure it on the finished assembly and record it in
`config/nodes.json` and in that node's firmware.

`speed = gap_mm / Δt`, so a 2 mm error is a 2% error on every reading that
station ever produces, and nothing downstream can detect it.

---

## Pin note

D19 and D18 are digital-only — they are **not** ADC pins. `analogRead()` will
not work on them, so the beam-align sketch runs in digital mode
(`BEAM_ANALOG 0`). Ball timing only needs digital edges, so nothing is lost.
