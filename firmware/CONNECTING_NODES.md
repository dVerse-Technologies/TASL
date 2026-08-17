# Connecting 3 ESP32s to the laptop

Goal: prove the network path works with real hardware, **before you solder
anything**. USB power only, no sensors, no battery.

```
ESP32 (USB power) --> 2.4 GHz Wi-Fi --> router --> laptop --> dashboard
```

If this doesn't work, no amount of good soldering will save it. Find out now.

---

## Before anything else: two blockers on this laptop

### 1. Your Wi-Fi is 5 GHz. The ESP32 cannot use it.

The laptop is on **`krishna-5G`, 802.11ac, 5 GHz**. The ESP32's radio is
**2.4 GHz only** — this is a hardware limit, not a setting. It will never see
that network, no matter what you type.

**What to do:** find the 2.4 GHz SSID on the same router (often `krishna`,
`krishna-2G`, or similar — check the router admin page or the label on the
back). Put *that* SSID in the firmware.

The laptop can stay on 5 GHz. Both bands on one router are normally bridged to
the same subnet, so a node on 2.4 GHz can still reach a laptop on 5 GHz. If it
can't, check the router doesn't have **AP isolation** or **client isolation**
enabled — that blocks device-to-device traffic and would stop this dead.

> For the event itself, the TP-Link Archer AX53 should have 2.4 GHz broadcast
> as its own distinct SSID, *not* merged with 5 GHz under one name. Band
> steering with a single SSID confuses ESP32s badly.

### 2. Windows has this network as "Public", and there's no firewall rule

On a Public network Windows blocks inbound connections, so the ESP32s' HTTP
POSTs never reach the server. Two commands in an **Administrator PowerShell**:

```powershell
Set-NetConnectionProfile -InterfaceAlias "WiFi 4" -NetworkCategory Private
```

```powershell
New-NetFirewallRule -DisplayName "TASL Dashboard (TCP 8000)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private
```

To undo later: `Remove-NetFirewallRule -DisplayName "TASL Dashboard (TCP 8000)"`

Check both at any time with:

```powershell
powershell -ExecutionPolicy Bypass -File tools\preflight.ps1
```

---

## Step 1 — Install ESP32 support in Arduino IDE

Arduino IDE is installed but has never been opened, and ESP32 support isn't
there yet.

1. Open **Arduino IDE**.
2. **File → Preferences**. In *Additional boards manager URLs*, paste:
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
3. **Tools → Board → Boards Manager**, search `esp32`, install
   **"esp32" by Espressif Systems**. It's a few hundred MB — give it time.
4. **Tools → Board → esp32 → "DOIT ESP32 DEVKIT V1"**.

No libraries to install. `WiFi.h` and `HTTPClient.h` come with the core.

## Step 2 — USB driver

Plug in a board and look at **Tools → Port**. If no new COM port appears, the
USB-serial chip needs a driver. Look at the small chip near the USB socket:

| Chip | Driver |
|---|---|
| CP2102 | Silicon Labs CP210x VCP driver |
| CH340 / CH9102 | WCH CH341SER driver |

Use a **data** USB cable. Charge-only cables are extremely common and give
exactly this symptom — power LED on, no COM port.

## Step 3 — Edit the firmware

Open `firmware/tasl_node_conn_test/tasl_node_conn_test.ino` and edit the four
marked lines near the top:

```cpp
#define NODE_ID  "NODE01"                       // NODE01 / NODE02 / NODE03
const char* WIFI_SSID = "your 2.4GHz SSID";
const char* WIFI_PASS = "your wifi password";
const char* SERVER_IP = "192.168.1.37";         // this laptop
```

`192.168.1.37` is this laptop's current address. Confirm it with `ipconfig` or
the preflight script before each session — **if it changes, every node goes
silent.** Set a DHCP reservation on the router so it can't move.

## Step 4 — Flash each board

Flash all three, **changing `NODE_ID` each time**:

| Board | `NODE_ID` |
|---|---|
| 1st | `NODE01` |
| 2nd | `NODE02` |
| 3rd | `NODE03` |

Press **Upload** (arrow icon). If it stalls at `Connecting......`, hold the
**BOOT** button until upload starts, then release. Some DevKit V1 boards need
this; some auto-reset fine.

## Step 5 — Watch it connect

Open **Tools → Serial Monitor**, set baud to **115200**. You should see:

```
=====================================
 TASL node - connection test firmware
  node id : NODE01
  firmware: conn-test-1.0.0
=====================================
[wifi] connecting to "krishna" ...
[wifi] CONNECTED
       node id : NODE01
       my IP   : 192.168.1.52
       gateway : 192.168.1.1
       signal  : -47 dBm
       server  : http://192.168.1.37:8000
[evt] BOOT sent
```

## Step 6 — Run the dashboard

```bash
python run_server.py
```

Open <http://localhost:8000>. Within a few seconds each flashed board should
turn **ONLINE**.

**Press the BOOT button** on any board — a fake ball event appears on that
node's card and in the event log. That's the full path proven: node → Wi-Fi →
laptop → browser.

Batteries will show as **grey/empty** — correct, since nothing is wired to
measure them yet. That's Step 2.

---

## Reading the onboard LED

| LED (blue, GPIO2) | Meaning |
|---|---|
| Fast blinking | Connecting to Wi-Fi |
| Short flash every 2 s | Connected, heartbeat sent |
| Three rapid flashes | Send failed — message queued for retry |

---

## If it doesn't work

Work down this list in order. Each step splits the problem in half.

**Serial Monitor shows nothing / garbage**
Wrong baud rate — set 115200. Garbage at the right baud means a bad cable.

**`[wifi] FAILED to connect`**
- SSID is 5 GHz — the most likely cause here.
- SSID is case sensitive. `Krishna` ≠ `krishna`.
- Password wrong.
- SSID has emoji or unusual characters — ESP32 handles these poorly.

**Connects to Wi-Fi, but `[net] no response (-1)`**
The node is on the network but can't reach the server.
1. Is `python run_server.py` actually running?
2. Did you run both firewall commands above?
3. Does the node's IP start with `192.168.1.`? If it's `192.168.4.x` or
   similar, it joined a guest network or a different router.
4. Router **AP isolation** — check it's off.
5. From another phone on the same 2.4 GHz Wi-Fi, open
   `http://192.168.1.37:8000`. If the phone can't reach it either, the problem
   is the laptop/firewall, not the ESP32.

**`[net] REJECTED: server does not know node_id "NODEXX"`**
`NODE_ID` in the firmware doesn't match `config/nodes.json`. Case sensitive.

**Node appears then goes OFFLINE repeatedly**
Weak signal. Check the `dBm` on its card — below −78 expect trouble. Move the
node or the router.

**Two boards both show as NODE01**
You forgot to change `NODE_ID` before flashing the second board. The dashboard
will show one node behaving very strangely.

---

## When this works

You've proven: Wi-Fi credentials, laptop IP, firewall, protocol, event
delivery and the offline queue — all with real hardware. Everything after this
is soldering, and if a node then misbehaves you know the network isn't why.

Next: **Step 2**, the battery circuit — TP4056 charging, the divider into an
ADC1 pin, RGB LED thresholds, and the JST-XH net table.
