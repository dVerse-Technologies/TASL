"""
The activity's simulated economy: BOM prices, the news events that move them,
and the full-screen flash shown on the stage projector.

Kept apart from store.py because it has a different lifetime. Node state is
rebuilt from nothing on restart - a node just heartbeats again a moment later.
Market state cannot be: if the server is restarted at the 1:45 mark, "War has
already been fired" is not recoverable from anything, so it is written to disk
on every change and reloaded on boot.

THE PRICE MATH COMPOUNDS, AND ROUNDS UP AFTER EVERY STEP. Each fired event is
a percentage of the price ALREADY ON THE BOARD, not of the base price, and the
result is rounded up to the nearest coin before the next event is applied:

    price = base
    on WAR    -> price = ceil10(price x 1.2)
    on TARIFF -> price = ceil10(price x 1.3)

War then Tariff gives x1.56 of base, not x1.50. Rounding up between the two
steps is what makes 25mm pipe go 60 -> 80 -> 110 rather than 60 -> 72 -> 94:
the BOM's war and tariff columns are computed this way, the team guide books
are printed from the BOM, and the board has to agree with the books.

Buyback never moves. It is always against the base price - see
config/market.json for why.
"""

from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "market.json"
STATE_PATH = ROOT / "data" / "market_state.json"
MEDIA_DIR = Path(__file__).resolve().parent / "static" / "media"

HISTORY_CAP = 200


def load_market_config() -> dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return {k: v for k, v in cfg.items() if not k.startswith("_comment")}


def round_price(value: float, step: int) -> int:
    """
    Round to something the physical coins can actually pay.

    The coins are 10/20/50/100/500, so a price of 85 is unpayable and a price
    of 90 is. Rounding here rather than in the browser means the depot board,
    the stage board and the admin panel can never disagree about a price.

    Half-UP, deliberately - NOT the built-in round(), which is half-to-even and
    would send 85 down to 80. A price rise that rounds downward is the kind of
    thing a participant notices and argues about at the depot counter.
    """
    step = 1 if not step or step < 1 else int(step)
    value = max(0.0, value)
    return int(math.floor(value / step + 0.5)) * step


def round_up(value: float, step: int) -> int:
    """
    Round a live price UP to the nearest coin.

    Always up, never half-up: the BOM's war and tariff columns are computed
    this way and the printed team guide books are generated from the BOM. A
    board that rounded 72 down to 70 where the book says 80 is an argument at
    the counter that nobody can win.

    The epsilon absorbs binary float error so that a value that is exactly on a
    step - 60 x 1.2 = 72.00000000000001 in float - does not get pushed up an
    extra whole step.
    """
    step = 1 if not step or step < 1 else int(step)
    value = max(0.0, value)
    return int(math.ceil(value / step - 1e-9)) * step


class Market:
    def __init__(self) -> None:
        cfg = load_market_config()

        self.currency: str = cfg.get("currency", "coins")
        self.currency_symbol: str = cfg.get("currency_symbol", "")
        self.round_to: int = int(cfg.get("round_to", 1))

        self.groups: list[dict[str, Any]] = list(cfg.get("groups", []))
        self.items: list[dict[str, Any]] = list(cfg.get("items", []))
        self.not_sold: list[dict[str, Any]] = list(cfg.get("not_sold", []))
        self.events: list[dict[str, Any]] = list(cfg.get("events", []))
        self._events_by_id = {e["event_id"]: e for e in self.events}

        self._lock = threading.RLock()

        # --- mutable state, all persisted ---------------------------------
        # event_id -> {"pct": float, "wall": float}
        self.fired: dict[str, dict[str, Any]] = {}
        self.global_pct: float = 0.0
        self.item_pct: dict[str, float] = {}
        # The full-screen takeover currently owning the projector, or None.
        self.flash: Optional[dict[str, Any]] = None
        self.history: list[dict[str, Any]] = []  # newest first

        self._load_state()

    # -------------------------------------------------------------- persistence

    def _load_state(self) -> None:
        if not STATE_PATH.exists():
            return
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                s = json.load(f)
        except Exception as exc:
            # A corrupt state file must not stop the server booting five minutes
            # before the event. Start clean and say so loudly in the console.
            print(f"[market] ignoring unreadable {STATE_PATH.name}: {exc!r}")
            return

        # Only restore events that still exist in the config - an event_id
        # renamed between sessions is a config change, not live state.
        self.fired = {
            eid: v for eid, v in (s.get("fired") or {}).items() if eid in self._events_by_id
        }
        self.global_pct = float(s.get("global_pct", 0.0))
        known = {i["item_id"] for i in self.items}
        self.item_pct = {
            k: float(v) for k, v in (s.get("item_pct") or {}).items() if k in known
        }
        self.flash = s.get("flash")
        self.history = list(s.get("history") or [])[:HISTORY_CAP]
        if self.fired:
            print(f"[market] resumed with {', '.join(sorted(self.fired))} already fired")

    def _save_state(self) -> None:
        """
        Called on every mutation. Writes to a temp file and replaces, so a power
        cut mid-write leaves the previous good state rather than half a file.
        """
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".json.tmp")
        payload = {
            "fired": self.fired,
            "global_pct": self.global_pct,
            "item_pct": self.item_pct,
            "flash": self.flash,
            "history": self.history[:HISTORY_CAP],
        }
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            tmp.replace(STATE_PATH)
        except Exception as exc:
            # Never let a disk problem take down a live trigger. The in-memory
            # state is still correct and every display already has it.
            print(f"[market] could not save state: {exc!r}")

    def _log(self, kind: str, text: str) -> None:
        self.history.insert(0, {"wall": time.time(), "kind": kind, "text": text})
        del self.history[HISTORY_CAP:]

    # -------------------------------------------------------------------- math

    def _fired_in_order(self) -> list[dict[str, Any]]:
        """
        Fire order matters now that the math compounds, and it is not the order
        the events are listed in the config - the operator can fire Tariff
        first. Sorted by wall clock, which is what actually happened in the room.
        """
        return [f for _, f in sorted(self.fired.items(), key=lambda kv: kv[1]["wall"])]

    def _compound(self, price: float, pct: float) -> int:
        # Clamp the multiplier at zero. A typo'd -400% must show as 0, not as a
        # negative price the depot then has to argue about.
        return round_up(price * max(0.0, 1.0 + pct / 100.0), self.round_to)

    def _live_price(self, item_id: str, base: float) -> int:
        price = float(base)
        for f in self._fired_in_order():
            price = self._compound(price, f["pct"])
        # The two manual dials are applied together, once, after the scripted
        # events. Applying them as separate rounding steps would let "+5% global
        # then +5% on one item" land two coin-steps above "+10% on that item",
        # which is impossible to explain to anyone at the counter.
        manual = self.global_pct + self.item_pct.get(item_id, 0.0)
        if manual:
            price = self._compound(price, manual)
        return int(price)

    def _priced_item(self, item: dict[str, Any]) -> dict[str, Any]:
        item_id = item["item_id"]
        base = round_price(float(item["base_price"]), self.round_to)
        live = self._live_price(item_id, base)
        buyback = item.get("buyback") or {}
        stock = item.get("stock") or {}
        return {
            "item_id": item_id,
            "group": item.get("group", ""),
            "name": item["name"],
            # Trimmed: the config pads this field with spaces to keep its
            # columns readable, and a unit of "   " would still draw a gap on
            # the board next to a name that already states the unit itself.
            "unit": str(item.get("unit", "")).strip(),
            "moq": item.get("moq", 1),
            "base_price": base,
            "live_price": live,
            # Realised, not requested: what the board actually charges over
            # base, after every rounding step. This is the number to quote when
            # someone asks how much prices have moved.
            "pct": round((live / base - 1.0) * 100.0, 2) if base else 0.0,
            "item_pct": round(self.item_pct.get(item_id, 0.0), 2),
            "buyback_fresh": int(buyback.get("fresh", base)),
            "buyback_modified": int(buyback.get("modified", base // 2)),
            "stock_basekit": int(stock.get("basekit", 0)),
            "stock_depot": int(stock.get("depot", 0)),
            "stock_procure": int(stock.get("procure", 0)),
            "changed": live != base,
        }

    def priced_items(self) -> list[dict[str, Any]]:
        return [self._priced_item(i) for i in self.items]

    def _effective_mult(self) -> float:
        """
        The single headline number on the boards, before rounding: what the
        multiplier on a base price currently is. War then Tariff gives 1.56.

        Shown as a multiplier rather than a percentage on purpose. Rounding up
        after each event means individual items move by different percentages -
        25mm pipe at 60 goes to 110, which is +83%, while 32mm pipe at 200 goes
        to 320, which is +60%. There is no one true percentage to print, but
        "x1.56" is exactly what was announced from the stage.
        """
        mult = 1.0
        for f in self._fired_in_order():
            mult *= max(0.0, 1.0 + f["pct"] / 100.0)
        mult *= max(0.0, 1.0 + self.global_pct / 100.0)
        return round(mult, 4)

    # ------------------------------------------------------------------ actions

    def fire_event(self, event_id: str) -> bool:
        """
        Apply an event's price change and take over the projector.

        Idempotent by design: pressing WAR twice must not apply +40%. Under
        stage lighting, with a room watching, the second press is far more
        likely to be a nervous double-tap than a deliberate second war.
        """
        with self._lock:
            ev = self._events_by_id.get(event_id)
            if ev is None:
                return False
            if event_id in self.fired:
                # Already applied. Re-show the flash rather than doing nothing,
                # since a second press almost always means "show it again".
                self._start_flash(ev)
                self._log("flash", f"{ev['name']} re-flashed (price change already applied)")
                self._save_state()
                return True

            self.fired[event_id] = {"pct": float(ev.get("price_pct", 0.0)), "wall": time.time()}
            self._start_flash(ev)
            self._log(
                "fire",
                f"{ev['name']} fired · {self._fmt_pct(ev.get('price_pct', 0))} on prices "
                f"as they stood · board now ×{self._effective_mult():g} of base",
            )
            self._save_state()
            return True

    def unfire_event(self, event_id: str) -> bool:
        """Undo a mis-fire. Removes the price change and kills its flash."""
        with self._lock:
            if event_id not in self.fired:
                return False
            ev = self._events_by_id.get(event_id, {"name": event_id})
            del self.fired[event_id]
            if self.flash and self.flash.get("event_id") == event_id:
                self.flash = None
            self._log("undo", f"{ev.get('name', event_id)} UNDONE · price change reversed")
            self._save_state()
            return True

    def flash_again(self, event_id: str) -> bool:
        """Replay the news takeover without touching prices."""
        with self._lock:
            ev = self._events_by_id.get(event_id)
            if ev is None:
                return False
            self._start_flash(ev)
            self._log("flash", f"{ev['name']} replayed on stage")
            self._save_state()
            return True

    def dismiss_flash(self) -> None:
        with self._lock:
            if self.flash:
                self._log("flash", "stage flash dismissed")
            self.flash = None
            self._save_state()

    def _start_flash(self, ev: dict[str, Any]) -> None:
        video = ev.get("video")
        # Resolve the video here, once, on the machine that has the file. If it
        # is missing the stage gets None and uses the built-in slate - a typo'd
        # filename can never leave the projector blank.
        if video and not (MEDIA_DIR / Path(video).name).exists():
            print(f"[market] video '{video}' not found in static/media - using the built-in slate")
            video = None
        self.flash = {
            "event_id": ev["event_id"],
            "started_wall": time.time(),
            "seconds": float(ev.get("flash_seconds", 45) or 0),
            "video": f"/static/media/{Path(video).name}" if video else None,
        }

    def set_global_pct(self, pct: float) -> None:
        with self._lock:
            self.global_pct = float(pct)
            self._log("manual", f"manual adjustment set to {self._fmt_pct(pct)} on all items")
            self._save_state()

    def set_item_pct(self, item_id: str, pct: float) -> bool:
        with self._lock:
            item = next((i for i in self.items if i["item_id"] == item_id), None)
            if item is None:
                return False
            pct = float(pct)
            if pct == 0.0:
                self.item_pct.pop(item_id, None)
            else:
                self.item_pct[item_id] = pct
            self._log("manual", f"{item['name']} adjusted by {self._fmt_pct(pct)}")
            self._save_state()
            return True

    def reset(self) -> None:
        """Back to base prices, nothing fired. For between rehearsal runs."""
        with self._lock:
            self.fired.clear()
            self.item_pct.clear()
            self.global_pct = 0.0
            self.flash = None
            self._log("reset", "market reset to base prices")
            self._save_state()

    @staticmethod
    def _fmt_pct(pct: float) -> str:
        return f"{pct:+g}%"

    # ------------------------------------------------------------------ output

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            events = []
            for ev in self.events:
                fired = self.fired.get(ev["event_id"])
                events.append(
                    {
                        "event_id": ev["event_id"],
                        "name": ev["name"],
                        "planned_at": ev.get("planned_at", ""),
                        "price_pct": ev.get("price_pct", 0),
                        "kicker": ev.get("kicker", "BREAKING"),
                        "headline": ev.get("headline", ev["name"]),
                        "subhead": ev.get("subhead", ""),
                        "ticker": ev.get("ticker", ""),
                        "accent": ev.get("accent", "#e0231f"),
                        "fired": fired is not None,
                        "fired_wall": fired["wall"] if fired else None,
                    }
                )
            mult = self._effective_mult()
            return {
                "currency": self.currency,
                "currency_symbol": self.currency_symbol,
                "round_to": self.round_to,
                # What the board headlines. effective_pct is derived from the
                # multiplier for anything that still wants a percentage; it is
                # NOT the sum of the fired percentages, because they compound.
                "effective_mult": mult,
                "effective_pct": round((mult - 1.0) * 100.0, 2),
                "global_pct": round(self.global_pct, 2),
                "groups": self.groups,
                "items": self.priced_items(),
                "not_sold": self.not_sold,
                "events": events,
                "flash": self.flash,
                "history": self.history[:60],
            }
