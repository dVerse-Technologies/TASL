# Event day — the four screens

One server, four pages, four machines. Everything is in sync because there is
only ever one copy of the state: the server holds it, and every screen renders
the same broadcast.

```
                    Archer AX53 (offline, 2.4 GHz)
                               │
        ┌──────────────┬───────┴───────┬──────────────┐
        │              │               │              │
   ADMIN MiniPC   Depot MiniPC   Stage laptop   Build-space MiniPC
   runs server         │          + projector          │
        │              │               │              │
     /admin         /depot          /stage             /
                               ▲
                     ~20 ESP32 nodes ──┘  POST to the ADMIN MiniPC's IP
```

| Machine | URL | Who looks at it |
|---|---|---|
| Admin MiniPC | `/admin` | Operator only |
| Depot MiniPC | `/depot` | Participants buying materials |
| Stage laptop → projector | `/stage` | The whole room |
| Build-space MiniPC | `/` | Participants building |

Replace `<SERVER_IP>` below with the admin machine's address, e.g.
`http://192.168.0.50:8000/depot`.

---

## The one thing to get right first: the server IP

`SERVER_IP` is **compiled into every node's firmware**. The nodes do not care
which machine answers — only which *address* answers.

So moving the server to the Admin MiniPC does **not** mean reflashing anything.
Give the Admin MiniPC the address the firmware already points at, and every
node connects exactly as before.

1. Find the address currently in `firmware/tasl_node_conn_test/secrets.h`.
2. Assign that address statically to the **Admin MiniPC**.
3. Make sure no other machine holds it. Only one machine runs the server.

Reflashing is only needed if you cannot give the Admin MiniPC that address —
and if you find yourself in that position, the cheaper fix is a DHCP
reservation on the Archer, not twenty boards over USB.

---

## Running order

1. Power the Archer AX53. Wait for it to come up fully.
2. Join all four machines to the **2.4 GHz** SSID.
3. On the Admin MiniPC, confirm it holds the agreed static IP, then:

   ```bash
   python run_server.py
   ```

4. Open each screen. Kiosk-mode command lines are below.
5. **Click the CLICK TO ARM prompt on the stage projector.** One click, once.
   Browsers refuse to autoplay audio on a page nobody has touched, and without
   it every news clip plays silently.
6. Power the nodes. Watch them come ONLINE in the admin panel's diagnostics.
7. On `/admin`, check the **SCREENS** panel: all four pips green before you
   start. That is your proof every display is actually listening, without
   walking the hall.

### Kiosk-mode launch

Chrome or Edge, on each display machine:

```bash
chrome --kiosk --noerrdialogs --disable-session-crashed-bubble --incognito http://<SERVER_IP>:8000/depot
```

Swap the path per machine: `/depot`, `/stage`, `/` and `/admin`. `F11` also
works if you would rather not use flags. Press `Alt+F4` to leave kiosk mode.

---

## Firing an event

On `/admin`, under **NEWS TRIGGERS**:

1. Press **FIRE WAR**. The button changes to **CONFIRM — FIRE**.
2. Press it again within four seconds.

At that instant, on every screen at once: prices rise, the depot's hike badge
jumps to `×1.2`, and the projector takes over with the breaking-news flash for
45 seconds before returning to the price board.

Then at the 2:00 mark, the same with **FIRE TARIFF** — the board goes to `×1.56`.

**Firing twice never doubles the price change.** A second press only replays
the flash. This is deliberate: under stage lighting a double-tap is far more
likely to be nerves than a second war.

### If something goes wrong

| Problem | Fix |
|---|---|
| Fired the wrong event | **UNDO PRICE CHANGE** on that trigger. Reverses everywhere immediately. |
| Flash needs to go away now | **DISMISS FROM STAGE** in the red strip at the top. |
| Nobody was looking | **REPLAY ON STAGE**. Re-shows the flash, does not touch prices. |
| Need an unplanned price move | **MANUAL ADJUSTMENT** — a percentage across every item. Or a single item's own % in the pricing table. |
| Rehearsing before the event | **RESET MARKET TO BASE** clears everything back to base prices. |

---

## The pricing math

Each event multiplies the price **already on the board** and the result is
rounded **up** to the nearest 10 before the next event is applied:

```
price = base
on WAR    → price = ceil10(price × 1.2)
on TARIFF → price = ceil10(price × 1.3)
then      → price = ceil10(price × (1 + (manual adjustment + this item's %)/100))
```

War then Tariff gives **×1.56**, not ×1.50. This is the model in
[`docs/gameplan/data/README.md`](gameplan/data/README.md), which is what the
BOM's war and tariff columns and the printed team guide books are computed
from. The board has to agree with the books.

Rounding up between the steps is the whole reason 25mm pipe goes
`60 → 80 → 110` rather than `60 → 72 → 94`. Prices round to 10 because the
coins in `openmarket/` are 10/20/50/100/500 and a price of 85 cannot be paid.

> **Individual rows move by more than 56%, and by different amounts.** 25mm
> pipe at 60 ends up +83%, 32mm pipe at 200 ends up +60%. That is rounding up
> on a cheap item, not a bug. The `×1.56` on the badge is the announced figure
> and is true of every line before rounding; the per-row percentage on `/admin`
> is what that row actually charges.

**Buyback never moves.** It is always against the **base** price — full for
unused material, half for cut-but-usable, nothing for unusable. If buyback
tracked the live price, a team could stockpile before the war announcement and
sell back at wartime prices for risk-free profit.

---

## What survives what

| | Fired events & prices | Ball progress & timer | SQLite event log |
|---|---|---|---|
| **RESET** (marble run) | kept | cleared | kept |
| **RESET MARKET TO BASE** | cleared | kept | kept |
| **Server restart** | **kept** | cleared | kept |
| **Reloading a screen** | kept | kept | kept |

Market state is written to `data/market_state.json` on every change and
reloaded on boot. If the server is restarted at the 1:45 mark, War is still
fired when it comes back — that is not information recoverable any other way.

---

## Diagnostics moved

The wrench icon is gone from the build-space dashboard. Troubleshooting now
lives at the bottom of `/admin` only, so participants standing in front of the
build-space monitor never see a station misbehaving. The rules and explanations
are unchanged.

---

## Editing the event

Everything lives in [`config/market.json`](../config/market.json): the 34
sellable BOM lines with their groups, base prices, buyback and stock counts,
plus the two events with their headlines, tickers and percentages. Restart the
server after editing.

**That file is generated from the BOM, not authored.** The names, prices,
buyback and quantities all come from
[`docs/gameplan/data/materials.json`](gameplan/data/materials.json), which is
generated in turn from
[`docs/gameplan/02-BOM/master-materials-and-mint.md`](gameplan/02-BOM/master-materials-and-mint.md).
If a number disagrees, the BOM wins — fix `config/market.json` to match, not
the other way round. `item_id` is the BOM's own id so the two can be diffed
line for line. To check they still agree:

```bash
python tools/check_bom.py
```

`item_id` and `event_id` are the keys state is stored against —
**do not change them once the event has started.** Names, prices and headlines
are safe to edit any time before.

The depot board shows buyback but deliberately **not** stock counts: a visible
count turns a shortage into a race. Stock is on `/admin` only.

To use your own news clips, drop `.mp4` files into `server/static/media/` and
name them in the event's `video` field. See
[`server/static/media/README.md`](../server/static/media/README.md). A missing
file falls back to the built-in animated slate, so a typo costs you the clip
and never blacks out the projector.

---

## Troubleshooting the screens

**A screen shows OFFLINE / a red veil.** It has lost the WebSocket. It retries
on its own, backing off to every 5 seconds, forever — no need to touch it. If
it stays red: check that machine's Wi-Fi, then that the server is still running
on the Admin MiniPC.

**A screen shows stale prices.** It cannot, unless it is disconnected — in
which case the veil is up saying so. There is one copy of the state and every
screen renders the same broadcast.

**Prices look wrong.** Check the **MARKET LOG** on `/admin`. Every fire, undo,
manual adjustment and reset is timestamped there.

**The projector went black.** The flash never blacks out — a missing video
falls back to the slate. A black projector is the projector's input, sleep
settings, or the cable. Disable screen sleep on the stage laptop before you
start.

**A news clip plays silently.** The CLICK TO ARM prompt was never clicked.
Reload `/stage` and click it.
