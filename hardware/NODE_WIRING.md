# TASL sensor node — complete wiring reference

One node = one measurement station = **two IR beams** a known distance apart,
on an **ESP32 DevKit V1 (30-pin)**, battery powered, in a 3D-printed housing.

This document covers the **final** node, including everything: IR sensors,
LiPo, TP4056 charger, power switch, RGB status LED and battery sensing. Build
it in stages (see *Build order*), but solder the layout for the finished thing
so you're not reworking 20 boards later.

You do your own track routing. This gives you every connection, every pin.

---

## 1. Battery sizing — 500 mAh vs 1000 mAh

### The current budget

| Load | Current @ 3.3 V |
|---|---|
| ESP32 + Wi-Fi, average | 45 – 100 mA |
| IR emitter, beam A (20 mA) | 20 mA |
| IR emitter, beam B (20 mA) | 20 mA |
| Two phototransistors | ~2 mA |
| RGB LED, one colour | 3 mA |
| Battery divider | 0.02 mA |
| **Total average** | **90 – 145 mA** |

The ESP32 figure is a genuine range, not hedging. With Wi-Fi modem sleep
active it idles near 45 mA; with it disabled, over 100 mA. Which one you get
depends on the core version's defaults, so **it has to be measured, not
assumed.**

Through the boost + onboard regulator at ~72% efficiency, that's **110 – 180 mA
drawn from the cell**.

### Runtime

| Cell | Worst case | Likely | With the easy wins below |
|---|---|---|---|
| **500 mAh** | 2.8 h | 4.5 h | ~6.5 h |
| **1000 mAh** | 5.5 h | 9 h | ~13 h |
| 2000 mAh | 11 h | 18 h | ~26 h |

### The requirement: a 4-hour event needs ~6 hours of cell

The event runs **4 hours**. The nodes are powered for longer than that: setup,
teams building their sections, dry runs, the run itself, teardown. Design for
**6 hours of switch-on time**, not 4.

Two derates nobody accounts for:

- **You can't use the last of the cell.** Below ~3.5 V the node is in RED and
  you'd swap it. Call it 85% usable.
- **Cheap cells are overstated.** A generic "1000 mAh" is often 700–800 mAh
  real. On a 500 mAh cell that leaves you working with ~400.

### Verdict: go to 1000 mAh

**1000 mAh clears the 6-hour requirement even in the worst case**, and with the
two free firmware wins below it reaches ~13 h and stops being something you
think about. You don't need 2000 mAh, and the smaller cell fits a smaller
housing.

Three things make battery life a non-issue rather than a risk:

1. **Use the switch.** The SPST isn't decoration — it's the battery strategy.
   Nodes don't need to be on while teams are still cutting pipe. Switch on
   30 minutes before the first run and the 6-hour requirement drops to ~4.5.
2. **Charge spares.** JST-XH means a swap takes ten seconds.
3. **A flat cell isn't a failure.** The dashboard turns that node yellow, then
   red, then flashing, well before it dies. You swap it in a natural pause.
   That's the whole reason the battery indicator exists.

**500 mAh is the one to avoid.** Its worst case is 2.8 hours, which is roughly
"the event, if nothing goes wrong and every cell started full." That's not a
margin, that's a hope. And you'd have to modify all 20 TP4056 modules
(§1.3 below).

### 1.2 What about 2× 500 mAh in parallel?

Electrically it's fine — capacity adds, voltage stays at 3.7 V, and the TP4056
and protection circuit see one 1000 mAh pack. Stock 1000 mA charge is 1C,
exactly as with a single cell.

**For a 20-node build it's still the wrong call**, for practical reasons:

| | 2× 500 mAh | 1× 1000 mAh |
|---|---|---|
| Cells to buy, charge, track | **40** | 20 |
| Solder joints in the power path | **40** | 20 |
| Voltage-matching procedure | 20× | none |
| Physical volume | **larger** — two cases, two sets of tabs | smaller |
| Cost | usually **more** | less |

Every extra joint across 20 nodes is another intermittent-fault candidate, and
intermittent power faults are the hardest class to diagnose at an event.

> **⚠ The genuine hazard: never join two cells at different states of charge.**
> Internal resistance is ~50–100 mΩ, so connecting a 4.2 V cell to a 3.6 V one
> gives `(4.2 − 3.6) / 0.15 Ω ≈ 4 A` instantaneously, through cells rated for a
> fraction of that. It damages cells and can start a fire.

**If you already own 40× 500 mAh cells**, do it like this:

1. Charge **each cell individually** to full first.
2. Meter both — **within 50 mV** before they touch.
3. Same brand, same batch, same age. Never pair a new cell with a used one.
4. Solder them permanently in parallel and treat the pair as **one sealed
   pack**. The danger is repeated connect/disconnect at differing charge, so
   design that possibility out.
5. Both positives to one point, both negatives to another, then a single
   JST-XH-2 to the board.
6. Charge as one 1000 mAh pack — stock TP4056 is correct.

### 1.3 Charge current

The TP4056's charge current is set by `R_prog`, and should be **0.5C to 1C**.

| Cell | Stock 1.2 kΩ = 1000 mA | Action |
|---|---|---|
| 500 mAh | 2C — **too fast** | Must change to 4 kΩ (≈300 mA) on all 20 |
| 1000 mAh | 1C — acceptable | Leave stock, or 2 kΩ (580 mA) to be gentle |
| 2000 mAh | 0.5C — ideal | Leave stock |
| **3000 mAh** (as built) | **0.33C — ideal** | **Leave stock. No module modification needed** |

The 3000 mAh cell also takes battery runtime off the risk list entirely:
roughly **17–27 hours** at the 110–180 mA the node draws, against a 6-hour
switch-on requirement. Charging one from empty at 1000 mA takes about 3.5 hours,
so charge overnight rather than between runs.

1C on a 1000 mAh cell is within spec for modern LiPos. It shortens cycle life
slightly, which is irrelevant over the ~20 charges this project will ever see.

### 1.4 Easy wins, in order of value

Apply these before deciding you need a bigger cell.

| Change | Saves | Cost to you |
|---|---|---|
| **Confirm Wi-Fi modem sleep is on** — `WiFi.setSleep(true)` | up to 55 mA | One line. Doesn't affect outgoing events, which is all we send |
| **CPU to 80 MHz** — `setCpuFrequencyMhz(80)` | ~20 mA | One line. Wi-Fi and `micros()` timing both unaffected |
| **IR emitters at 10 mA** — 200 Ω instead of 100 Ω | 20 mA | Resistor swap. Fine with a tight aperture and a black shroud; test alignment first |
| **Flash the RGB LED** instead of solid on | ~3 mA | Small firmware change. Also easier to read across a hall |

Together these roughly halve consumption. The first two are free and carry no
real downside.

> **Not worth it:** strobing the IR emitters at 10 kHz with synchronous
> sampling would cut emitter current by ~90%, but it complicates the timing
> path — the one part of this system that must not be clever.

### 1.5 Measure it before you commit

Every number above is calculated, not measured. Once **stage 1** of the build
works, put a multimeter in series with the battery and read the actual current.
Ten minutes, and it replaces this entire section with a fact.

If it comes in near 90 mA, a 500 mAh cell would genuinely last ~4.5 h and you
could keep them. If it's near 145 mA, you'll be glad you went to 1000 mAh.

### 1.6 The cheap insurance

You're using JST-XH connectors, so **swapping a cell takes ten seconds**.
Charge a set of spares and keep them in the toolbox. That, plus the dashboard
turning a node's battery icon red before it dies, means a flat cell is a
30-second interruption rather than a failure.

---

## 2. Power architecture

The single most important decision, and the one most likely to destroy an
ESP32 if you get it wrong.

```
LiPo ──> TP4056 ──> SPST ──> MT3608 ──> AMS1117 ──> ESP32 3V3 pin
3000mAh  +protect   switch   boost 5V    3.3V       (VIN unused)
                                            │
                                       1000 µF 16V
```

**This is the as-built chain.** It differs from the original design in §2.1
below: an external AMS1117 feeds the **`3V3` pin** directly and the ESP32's
onboard regulator is bypassed, so `VIN` is left disconnected. The sensors get
the same clean rail as the ESP32.

The rule that follows: **switch OFF before plugging in USB**, every time. With
the `3V3` pin driven externally there is no diode protecting you from two
supplies fighting.

### Why not simpler?

**Can the LiPo feed VIN directly?** No. `VIN` goes through the onboard
AMS1117 regulator, which needs ~1.1 V of headroom — so at least 4.4 V in. A
LiPo starts at 4.2 V and falls. It would brown out immediately.

**Can the LiPo feed the 3V3 pin directly?** No, and this one kills boards. The
3V3 pin sits straight on the 3.3 V rail. A charged LiPo at 4.2 V is **0.9 V
over** what the ESP32 is rated for.

**Can an LM2596 step 3.7 V down to 3.3 V for VIN?** No — it fails twice over.

1. **The LM2596 is a buck (step-down) converter, and its datasheet minimum
   input is 4.5 V.** A 3.7 V cell is already below that, so it won't even
   start. And a buck can never produce 3.3 V from a cell that sags to 3.0 V —
   that's physics, not a tuning problem.
2. **3.3 V into `VIN` does nothing useful anyway.** `VIN` feeds the onboard
   AMS1117, which needs ~4.4 V. Give it 3.3 V and the 3.3 V rail comes out at
   roughly 2.2 V. The ESP32 won't run.

If you want 3.3 V it has to go to the **`3V3` pin**, bypassing the onboard
regulator — and to make 3.3 V across the cell's whole 4.2 → 3.0 V range you
need a **buck-boost**, not a buck. The LM2596 also idles at 5–10 mA, which is
most of a phototransistor's budget wasted continuously.

**So:** boost the LiPo to a steady 5 V and feed `VIN`. The onboard regulator
then does what it was designed to do. Costs some efficiency, but it works over
the cell's whole range and is very hard to get wrong.

### 2.1 If you want the extra runtime: buck-boost to 3V3

There is a better-but-pricier option. A **TPS63020-based buck-boost module**
set to 3.3 V, feeding the **`3V3` pin** directly, skips the onboard regulator
entirely.

| | MT3608 boost → `VIN` | TPS63020 buck-boost → `3V3` |
|---|---|---|
| Efficiency | ~72% (two conversions) | ~90% (one) |
| Runtime, 1000 mAh | 5.5 – 9 h | **7 – 12 h** |
| Cost | ~₹30 | ~₹150–250 |
| Risk if mis-set | Destroys the ESP32 | Destroys the ESP32 |
| Complexity | Lower | Slightly higher |

Both need the same care: **set the output voltage with a meter, on no load,
before it ever touches the board.** The switch still goes before the module,
and the USB rule is unchanged.

Use the MT3608 unless the battery budget turns out tight after you measure
(§1.5). It's the simpler part, and simpler wins on a 20-node build.

### ⚠ Adjust every MT3608 before it ever touches an ESP32

MT3608 modules are **adjustable and ship at an arbitrary setting**. The pot can
output up to 28 V. Connecting an unadjusted one to `VIN` can destroy the board
instantly.

For every module, in this order:

1. Connect the module's input to the battery (or any 3.7–4.2 V source).
2. **Nothing connected to the output.**
3. Multimeter on the output pads.
4. Turn the pot until it reads **5.0 V**. Many turns — it's a multi-turn pot.
5. Disconnect, then wire it to the ESP32.
6. Put a dab of nail varnish or hot glue on the pot so it can't drift.

Do this for all 20 before you solder any of them in.

### ⚠ Switch the node OFF before plugging in USB

With the node powered from the battery, the boost drives `VIN` while USB
drives the 5 V rail. They'll fight. The SPST switch sits *before* the boost, so
switching off disconnects it completely.

**Rule: switch OFF → then plug in USB.** Every time.

### Charging

The switch is between `OUT+` and the boost, so the TP4056 charges the cell
through `B+`/`B−` regardless of switch position. **Charging works with the node
switched off**, which is what you want overnight.

---

## 3. Bill of materials — ONE node

| # | Part | Value / spec | Notes |
|---|---|---|---|
| 1 | ESP32 DevKit V1 | 30-pin DOIT | Not the 36-pin DevKitC — pin positions differ |
| 2 | TP4056 module | **with protection** | Must have DW01A + 8205A chips. See §7 |
| 3 | MT3608 boost module | adjustable | Set to 5.0 V *before* connecting |
| 4 | 1S LiPo | 3.7 V **3000 mAh** | With JST connector. See §1 — 1000 mAh was the original spec, 3000 mAh is what the build actually uses |
| 5 | SPST switch | any, ≥500 mA | Slide or toggle |
| 6 | IR LED, 940 nm | 5 mm clear | ×2 (one per beam) |
| 7 | IR phototransistor | 5 mm dark/black | ×2 (one per beam) |
| 8 | RGB LED | 5 mm, 4-pin, **common cathode**, diffused | Diffused matters — clear ones are hard to read off-axis |
| 9 | Resistor **220 Ω** | ¼ W | ×2 — IR emitter current limit (in cartridges). **Bench-proven value**, see §8 |
| 10 | Resistor **100 kΩ** | ¼ W | ×2 — phototransistor pull-downs. **Bench-proven value**, see §8 |
| 11 | Resistor 100 kΩ | ¼ W, 1% | ×2 — battery divider |
| 12 | Resistor 330 Ω | ¼ W | ×1 — RGB red |
| 13 | Resistor 150 Ω | ¼ W | ×2 — RGB green, blue |
| 14 | Capacitor 100 nF | ceramic | ×1 — ADC filter |
| 15 | Capacitor **1000 µF** | electrolytic, **16 V** | ×1 — bulk, across 3V3/GND, close to the ESP32 |
| 15b | **AMS1117-3.3** regulator | SOT-223 module or bare | ×1 — 5 V from the boost down to a clean 3V3 rail. See §2.2 |
| 16 | JST-XH 2-pin | male + female | Battery to board |
| 17 | JST-XH 3-pin | male + female | ×2 — one per beam cartridge |
| 18 | Perfboard | | |

**1% resistors for the divider (item 11)** — the divider ratio directly sets
your battery reading, and 5% parts give you Â±5% error on a measurement whose
whole job is distinguishing 3.65 V from 3.80 V.

---

## 4. GPIO allocation — ESP32 DevKit V1

| GPIO | Silkscreen | Function | Why this pin |
|---|---|---|---|
| **19** | `D19` | Beam A signal | Digital-only, right-hand header. Chosen so both beams land on the same side as the sensor cable run |
| **18** | `D18` | Beam B signal | Same |
| **34** | `D34` | Battery sense | ADC1, input-only — perfect for analog, needs no pull-up |
| **25** | `D25` | RGB red | Safe output, no strapping conflict |
| **26** | `D26` | RGB green | " |
| **27** | `D27` | RGB blue | " |
| 2 | `D2` | Onboard blue LED | Already used by firmware for status |
| 0 | `BOOT` btn | Test/align button | Onboard, no wiring needed |

The battery sense and RGB LED are on the **left-hand header**; the two beams
are on the **right**, next to each other, so the sensor cables leave the board
on one side.

### Why ADC1 and not ADC2 — battery sense only

**ADC2 stops working the moment Wi-Fi is active.** It's shared with the radio.
Since every node runs Wi-Fi permanently, ADC2 is unusable for analog. GPIO32–39
are ADC1 and unaffected, which is why battery sense sits on GPIO34.

### Pins to avoid

- **GPIO6–11** — wired to the onboard SPI flash. Using them bricks the boot.
- **GPIO12** — strapping pin; held high at boot stops the board starting.
- **GPIO34–39** — input-only, and no internal pull-ups. Fine for our ADC use,
  useless for driving anything.
- **GPIO1, GPIO3** — TX0/RX0. Using them breaks upload and the Serial Monitor.
- **GPIO15** — strapping pin.

### The beams are digital-only, and that is fine

Ball timing uses **digital reads** — fast, deterministic edges, which is what
accurate timing needs. GPIO19 and GPIO18 are not ADC-capable, so they cannot do
the analog *alignment* readout.

That costs nothing in practice: alignment is a bench operation, done once per
cartridge with the standalone `firmware/tasl_beam_align` sketch before the
sensors go on the track. Run that sketch in digital mode (`BEAM_ANALOG 0`) and
break the beam with a finger — the break counter tells you whether the beam is
reliable, which is the question that actually matters.

If you want the raw analog margin while aiming a difficult cartridge, move that
one beam's wire to **GPIO32** temporarily, set `BEAM_ANALOG 1`, aim it, then put
it back on GPIO19.

---

## 5. Net table

Every connection on the board. Grouped by net — everything in one block is
electrically the same node.

### NET: `BAT+` — raw cell positive
| From | To |
|---|---|
| LiPo red wire | JST-XH-2 **pin 1** |
| JST-XH-2 **pin 1** | TP4056 `B+` pad |

### NET: `BAT−` — raw cell negative
| From | To |
|---|---|
| LiPo black wire | JST-XH-2 **pin 2** |
| JST-XH-2 **pin 2** | TP4056 `B−` pad |

### NET: `VBAT_RAW` — protected battery output
| From | To |
|---|---|
| TP4056 `OUT+` | SPST switch, terminal 1 |

### NET: `VBAT_SW` — after the switch
| From | To |
|---|---|
| SPST switch, terminal 2 | MT3608 `IN+` |
| SPST switch, terminal 2 | R11a (100 kΩ), leg 1 |

*The divider hangs off the switched side, so it draws nothing when the node is
off.*

### NET: `+5V` — boost output
| From | To |
|---|---|
| MT3608 `OUT+` | AMS1117 **`IN`** |

*ESP32 `VIN` is **not** connected. The onboard regulator is bypassed.*

### NET: `+3V3` — regulated rail (output from the external AMS1117)
| From | To |
|---|---|
| AMS1117 **`OUT`** | ESP32 **`3V3`** pin |
| AMS1117 **`OUT`** | Beam A JST-XH-3 **pin 1** |
| AMS1117 **`OUT`** | Beam B JST-XH-3 **pin 1** |
| AMS1117 **`OUT`** | C15 (1000 µF) **+** leg |

*Put C15 physically as close to the ESP32's `3V3`/`GND` pins as you can — it is
there to supply the ~250 mA Wi-Fi transmit spike, and track resistance between
the cap and the chip defeats the purpose.*

### NET: `GND` — common ground (all of these tie together)
| Connection |
|---|
| TP4056 `OUT−` |
| MT3608 `IN−` |
| MT3608 `OUT−` |
| AMS1117 **`GND`** |
| ESP32 **`GND`** (either pin) |
| RGB LED **common cathode** |
| Beam A JST-XH-3 **pin 3** |
| Beam B JST-XH-3 **pin 3** |
| R11b (100 kΩ) leg 2 — divider bottom |
| C14 (100 nF) leg 2 |
| R10a (100 kΩ) leg 2 — beam A pull-down |
| R10b (100 kΩ) leg 2 — beam B pull-down |
| C15 (1000 µF) **−** leg |

**One ground, everything on it.** A node with a floating ground between the
boost and the ESP32 gives bizarre, intermittent faults that look like sensor
problems.

### NET: `BATT_SENSE` → GPIO34
| From | To |
|---|---|
| R11a (100 kΩ) leg 2 | R11b (100 kΩ) leg 1 |
| that junction | ESP32 **`D34`** |
| that junction | C14 (100 nF) leg 1 |

### NET: `BEAM_A_SIG` → GPIO19
| From | To |
|---|---|
| Beam A JST-XH-3 **pin 2** | ESP32 **`D19`** |
| Beam A JST-XH-3 **pin 2** | R10a (100 kΩ) leg 1 |

### NET: `BEAM_B_SIG` → GPIO18
| From | To |
|---|---|
| Beam B JST-XH-3 **pin 2** | ESP32 **`D18`** |
| Beam B JST-XH-3 **pin 2** | R10b (100 kΩ) leg 1 |

### NET: `LED_R` / `LED_G` / `LED_B`
| From | To |
|---|---|
| ESP32 **`D25`** | R12 (330 Ω) → RGB **red** anode |
| ESP32 **`D26`** | R13 (150 Ω) → RGB **green** anode |
| ESP32 **`D27`** | R13b (150 Ω) → RGB **blue** anode |

---

## 6. JST-XH pinout cards

Print these. Getting a battery backwards destroys things.

### Battery — JST-XH **2-pin**

```
        â”Œ─────────â”
        â”‚  1   2  â”‚
        â””─â”¬─────â”¬─â”˜
          â”‚     â”‚
        RED   BLACK
        BAT+   BAT−
       (to     (to
       TP4056  TP4056
        B+)     B−)
```

| Pin | Signal | Wire |
|---|---|---|
| 1 | `BAT+` | **Red** |
| 2 | `BAT−` | **Black** |

> **Check with a multimeter before every first connection.** LiPo cells ship
> with varying connector orientations, and reversing one can vent the cell.

### IR beam cartridge — JST-XH **3-pin** (×2, identical)

```
        â”Œ───────────â”
        â”‚  1  2  3  â”‚
        â””─â”¬──â”¬──â”¬───â”˜
          â”‚  â”‚  â”‚
        RED YEL BLK
        3V3 SIG GND
```

| Pin | Signal | Wire | Goes to |
|---|---|---|---|
| 1 | `+3V3` | Red | IR LED anode (via 220 Ω) **and** phototransistor collector |
| 2 | `SIGNAL` | Yellow | Phototransistor emitter |
| 3 | `GND` | Black | IR LED cathode |

**Both cartridges are wired identically** — beam A and beam B are
interchangeable, so a spare fits either socket. Only the board-side connector
decides which is which.

### Inside one cartridge

The **220 Ω resistor lives in the cartridge**, not on the board. That's what
gets each beam down to three wires instead of four.

```
  pin 1 (3V3) ──â”¬── [220 Ω] ── IR LED anode
                â”‚                 IR LED cathode ── pin 3 (GND)
                â”‚
                â””── phototransistor COLLECTOR
                    phototransistor EMITTER ────── pin 2 (SIGNAL)
```

The 100 kΩ pull-down stays on the **main board**, so you can change sensitivity
without opening a sealed cartridge.

---

## 7. Identifying component pins

Don't trust leg length alone — test.

### TP4056 — is it the protected version?

**Critical.** The unprotected version has no over-discharge cutoff and will
flatten a LiPo until it's damaged and potentially unsafe.

Look at the board. The **protected** version has **three** ICs:
- `TP4056` — the charge controller
- `DW01A` — protection controller (6-pin, near the `B−` pad)
- `8205A` — dual MOSFET (8-pin, beside the DW01A)

Only the TP4056 chip and no others → **unprotected, don't use it.**

Pads: `IN+`/`IN−` (or micro-USB), `B+`/`B−` (cell), `OUT+`/`OUT−` (load).

### IR phototransistor — which leg is the collector?

Convention is unreliable across manufacturers. Test it:

1. Wire the suspected **collector to 3V3**, **emitter through 100 kΩ to GND**.
2. Multimeter on the emitter leg (relative to GND).
3. Point a TV remote at it and press a button.
4. **Voltage rises** → correct. **Nothing happens** → swap the legs.

Bare phototransistors are IR-sensitive but visibly dark/black-tinted, unlike
the clear IR emitters.

### IR emitter vs phototransistor — telling them apart

They look almost identical. The **emitter** is clear or faintly blue; the
**phototransistor** is dark grey/black. If you can't tell, a phone camera sees
940 nm as pale violet — power one through a 220 Ω resistor and look at it
through your phone. If it glows on camera, it's the emitter.

### RGB LED — finding the common cathode

The longest leg is *usually* the common, but test:

1. 3.3 V through a 330 Ω resistor.
2. Suspected common → **negative**.
3. Touch the resistor to each of the other three legs.
4. All three light (red, green, blue) → common cathode confirmed, and you've
   just identified which leg is which colour.
5. Nothing lights → you have common **anode**; see below.

**If it's common anode:** tie the common to `3V3` instead of `GND`, and the
firmware logic inverts — `LOW` turns a colour **on**. Everything else is
unchanged.

---

## 8. Resistor values, and why

### IR emitters — 220 Ω

940 nm IR LED forward voltage ≈ 1.3 V.
`(3.3 − 1.3) / 220 Ω = 9 mA`

**Bench-proven at a 40 mm beam gap through PVC pipe.** 9 mA is half the 20 mA a
100 Ω would give, and it works because the pull-down was raised to 100 kΩ at the
same time — sensitivity on the receiver side is cheaper than brightness on the
emitter side, in both current and battery life.

Across two beams that saves ~22 mA per node continuously, which matters on a
supply that has to survive Wi-Fi transmit spikes.

If a cartridge genuinely needs more light, **two 220 Ω in parallel = 110 Ω →
18 mA**. Do not parallel three: 73 Ω gives 27 mA, over the 20 mA continuous
rating of a typical 5 mm IR LED.

### Phototransistor pull-downs — 100 kΩ

Sets sensitivity and edge speed, and this is the value that made the beam work.

At 10 kΩ the pair only triggered with the emitter and phototransistor almost
touching — useless across a pipe. At **100 kΩ** the same parts cleared 40 mm
with margin. That single change was worth more than any amount of emitter
current.

- **Beam never triggers / ball not detected** → the pull-down is too small, or
  the parts are aimed off-axis
- **False triggers, or "implausible speed" in diagnostics** → drop to 10 kΩ
  (crisper edges, less noise pickup) and add emitter current to compensate

> The trade-off: 100 kΩ is sensitive enough to respond to room light and
> sunlight. It is only safe because the beam runs **inside the PVC pipe**, which
> acts as the shroud. A beam mounted in open air needs a proper aperture and
> hood, or a smaller pull-down.

### RGB LED — 330 Ω red, 150 Ω green and blue

Red's forward voltage (~2.0 V) is much lower than green/blue (~3.0 V), so red
needs the bigger resistor or it swamps the others.

`Red:   (3.3 − 2.0) / 330 = 4 mA`
`Green: (3.3 − 3.0) / 150 = 2 mA`

Deliberately modest — this is a battery-powered node, and 20 mA per colour
would be both wasteful and blinding in a dark housing.

**Yellow = red + green together.** Turn both on. If your yellow looks orange,
raise the red resistor to 470 Ω to balance it.

PWM isn't needed for on/off colours, though the ESP32's LEDC peripheral is
there if you later want dimming.

### Battery divider — 100 kΩ / 100 kΩ

Halves the battery voltage so the ADC never sees more than it can take:

| Battery | ADC sees |
|---|---|
| 4.20 V (full) | 2.10 V |
| 3.70 V (nominal) | 1.85 V |
| 3.30 V (empty) | 1.65 V |

Comfortably inside the ESP32's range with 11 dB attenuation. Draw is
`4.2 V / 200 kΩ = 21 µA` — negligible.

The **100 nF cap** across the bottom resistor is not optional. The ESP32's ADC
samples in bursts and its input impedance is not friendly to a 50 kΩ source;
without the cap your readings jump around by 100 mV or more.

---

## 9. Battery thresholds for the RGB LED

A 1S LiPo's voltage is nearly flat through most of its usable charge, then
falls off a cliff. **Don't present it as a percentage** — these four states are
the honest reading. Measured *under load*, so they already include sag.

| State | Voltage | LED | Meaning |
|---|---|---|---|
| `GREEN` | ≥ 3.80 V | Green | Healthy |
| `YELLOW` | 3.65 – 3.80 V | Red + green | Getting low — have a spare ready |
| `RED` | 3.50 – 3.65 V | Red | Swap at the next reset |
| `CRITICAL` | < 3.50 V | **Flashing red** | Minutes from dropping off |

These are the same thresholds the dashboard uses, so the LED on the node and
the battery icon on screen always agree.

### ADC calibration — do this once per board

The ESP32's ADC is **noticeably non-linear** and varies between chips. Don't
trust the raw number:

1. Measure the actual battery voltage with a multimeter at `OUT+`.
2. Read what the firmware reports.
3. `correction = actual / reported`
4. Store that constant per node.

Also **average 16–64 samples** per reading. A single ADC read on an ESP32 is
noisy enough to bounce a node between GREEN and YELLOW.

---

## 10. Build order

Don't build a whole node and then find out. Each stage is testable.

**Stage 1 — power** (do this on one board first)
TP4056 + switch + MT3608, set to 5.0 V, into ESP32 `VIN`. No sensors, no LED.
Success: board boots on battery, existing connection-test firmware reports
ONLINE, and charging works with the switch off.

**Stage 2 — battery sensing**
Add the divider and cap to `D34`. Calibrate against a multimeter.
Success: real voltage in the dashboard instead of grey/UNKNOWN.

**Stage 3 — RGB LED**
Add LED and its three resistors.
Success: colour matches the dashboard's battery icon as the cell drains.

**Stage 4 — one beam**
Beam A cartridge and pull-down only.
Success: blocking the beam with your finger toggles the GPIO.

**Stage 5 — second beam and timing**
Beam B, spaced at your measured `gap_mm`.
Success: rolling a ball through produces a plausible speed on the dashboard.

**Then build the other 19**, from a node you know works.

---

## 11. Do we need a comparator?

Your original notes asked. Short answer: **start without one.**

A phototransistor with a 100 kΩ pull-down gives a usable logic swing, and the
ESP32's inputs have some hysteresis. The firmware state machine handles
debouncing.

An LM393 comparator per beam gives crisper edges and better ambient-light
immunity — but adds a trimpot per beam, which is **40 trimpots to calibrate**
across 20 nodes. That's a real cost.

Build stage 5 without one and watch the troubleshooting panel. If a station
reports **"Implausible speed recorded"** or **"Beam A triggered without beam
B"** repeatedly after you've confirmed alignment, *then* add an LM393 to that
station. The diagnostics were built to make this decision for you with
evidence instead of guesswork.

---

## 12. Common mistakes

| Mistake | Result |
|---|---|
| **MT3608 not pre-set to 5 V** | Up to 28 V into `VIN`. Dead ESP32, instantly |
| **LiPo straight to the `3V3` pin** | 4.2 V on a 3.3 V rail. Damages the ESP32 |
| **LiPo to `VIN` without the boost** | Won't run — regulator has no headroom |
| **TP4056 without protection** | Cell over-discharged and damaged; a safety risk |
| **USB plugged in with the switch ON** | Boost and USB fight over the 5 V rail |
| **Battery JST reversed** | Can vent the cell. Meter it, every time |
| **Using ADC2 pins for battery** | Reads garbage the moment Wi-Fi starts |
| **Using GPIO6–11** | Board won't boot at all |
| **Grounds not all common** | Bizarre intermittent faults that mimic sensor problems |
| **No 100 nF on the ADC** | Battery reading jumps 100 mV+, flickers GREEN/YELLOW |
| **Phototransistor legs swapped** | Beam never triggers. Test before soldering |
| **Forgetting `gap_mm`** | Every speed from that station is silently wrong |

---

## 13. The one measurement that matters

`gap_mm` — the distance between beam A and beam B — is the number every
velocity depends on:

```
speed = gap_mm / Δt
```

**Measure it on the built cartridge, not from the CAD model.** A 2 mm error
over a 100 mm gap is a 2% error on every reading that station ever produces,
and nothing in the system can detect it.

Record it per station in `config/nodes.json`, and put the same value in that
node's firmware.

