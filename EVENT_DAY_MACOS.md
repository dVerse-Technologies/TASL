# Event day — running the dashboard on the MacBook

Development happens on the Windows PC. The **MacBook runs the live event**.

The good news: nearly all the Windows pain doesn't exist on macOS. There's no
Public/Private network category, and no "Unidentified network" trap on a
WAN-less router. The bad news is one new gotcha and one genuinely important
decision.

---

## The important decision: fix the server IP now

`SERVER_IP` is **compiled into every node's firmware**. Right now it's
`192.168.1.37` — the Windows PC's address.

If the MacBook gets a different address on event day, **every node silently
fails and you'd have to reflash all ~20 of them on site.** That is the single
worst failure this project can have, and it's entirely avoidable.

**Pick one server address and make whichever machine runs the server take it.**

Suggested: whatever subnet the Archer AX53 uses, pick something clearly outside
its DHCP pool, e.g. `192.168.0.50`.

Then:

1. Put that address in the firmware and flash all nodes with it — once, here.
2. On the **MacBook**, set that address manually:
   **System Settings → Network → Wi-Fi → Details → TCP/IP →
   Configure IPv4: Manually**, IP `192.168.0.50`, subnet `255.255.255.0`,
   router = the Archer's address.
3. On the **Windows PC**, set the same address when *it* runs the server, so
   development and event day are identical.

Only one machine holds that address at a time, which is exactly right — only
one runs the server.

Doing this means the firmware never changes between now and event day.

> Alternative: I can add mDNS to the firmware so nodes resolve `tasl.local`
> instead of a hard IP. Bonjour is native on macOS so it works well, but it
> adds a failure mode that a fixed IP doesn't have. Ask if you'd prefer it.

---

## Setting up the MacBook

### 1. Python

macOS doesn't ship a usable Python 3. Install from
[python.org](https://www.python.org/downloads/macos/), or with Homebrew:

```bash
brew install python
```

Check:

```bash
python3 --version
```

### 2. Copy the project across

Copy the whole `TASL` folder. Then:

```bash
cd ~/TASL
python3 -m pip install -r requirements.txt
```

### 3. Preflight

```bash
bash tools/preflight.sh
```

The macOS equivalent of `preflight.ps1`. It reports the Mac's LAN IP, firewall
state, Wi-Fi band, Python deps and whether the server is up — and tells you if
the IP doesn't match what's in your firmware.

### 4. Run it

```bash
python3 run_server.py
```

Open <http://localhost:8000>.

---

## The one macOS gotcha: the firewall prompt

macOS's firewall is **per-application**, not per-port. There's no rule to add.

The first time you run the server, macOS may show:

> *"Do you want the application python3 to accept incoming network
> connections?"*

**Click Allow.** If you click Deny — or the dialog appears behind a window and
gets dismissed — every node fails silently and the dashboard shows all
stations OFFLINE with no clue why.

To check or fix afterwards:
**System Settings → Network → Firewall → Options** — make sure `python3` is
listed and set to *Allow incoming connections*.

Also confirm **"Block all incoming connections" is OFF**. It overrides
everything else, and the preflight script flags it.

If the firewall is off entirely (the default on many Macs), there's nothing to
do at all.

---

## Flashing ESP32s from the Mac

Only needed if you have to reflash on site — which the fixed-IP plan above is
designed to avoid.

- Arduino IDE setup is identical: same boards-manager URL, same
  **DOIT ESP32 DEVKIT V1** board.
- Ports appear as `/dev/cu.usbserial-xxxx`, `/dev/cu.SLAB_USBtoUART` or
  `/dev/cu.wchusbserial-xxxx` instead of `COM3`.
- Pick the `cu.*` entry, not the `tty.*` one.
- **CP2102** boards work with no driver on modern macOS. **CH340/CH9102**
  boards usually need the WCH driver — and on Apple Silicon you need the
  current signed version, older ones won't load.

Worth confirming *before* event day that the Mac can see a board at all, even
if you never plan to use it. Ten minutes now versus a dead end on site.

---

## Event day running order

1. Power the Archer AX53. Wait for it to come up fully.
2. Join the MacBook to the **2.4 GHz** SSID.
3. Confirm the Mac has the agreed static IP.
4. ```bash
   bash tools/preflight.sh
   ```
   Everything must say READY before you power a single node.
5. ```bash
   python3 run_server.py
   ```
6. Open <http://localhost:8000>. Allow the firewall prompt if it appears.
7. Power the nodes. Watch them turn ONLINE one at a time.
8. Any that don't: open the **wrench icon**, top right.

---

## What differs from Windows, in one table

| | Windows (dev) | macOS (event) |
|---|---|---|
| Preflight | `tools\preflight.ps1` | `tools/preflight.sh` |
| Run server | `python run_server.py` | `python3 run_server.py` |
| Firewall model | Per-port rule | Per-application allow |
| Network category | Public/Private — a real trap | Doesn't exist |
| WAN-less network | Flags as Public every time | No such behaviour |
| Serial port | `COM3` | `/dev/cu.usbserial-*` |

The server, dashboard, protocol, diagnostics and firmware are identical on
both. Only the host setup differs.
