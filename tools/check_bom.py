"""
Check config/market.json against the BOM.

    python tools/check_bom.py

config/market.json is generated from docs/gameplan/data/materials.json, which
is generated from docs/gameplan/02-BOM/master-materials-and-mint.md, which is
what the printed team guide books are typeset from. Three copies of the same
numbers, and the only one the depot board reads is the first.

So this script re-derives every price the market engine will show - base, after
War, after War+Tariff - and compares them, plus the names, buyback and stock
counts, against the BOM. It exits non-zero on any disagreement.

Run it after touching either file, and once more the week of the event. A
mismatch here means the board will quote a price the books do not.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.market import Market  # noqa: E402

BOM_PATH = ROOT / "docs" / "gameplan" / "data" / "materials.json"

# The BOM's own field names on the left, ours on the right.
FIELDS = [
    ("name", "name", lambda b: b["name"]),
    ("moq", "moq", lambda b: b["moq"]),
    ("buyback fresh", "buyback_fresh", lambda b: b["buyback"]["fresh"]),
    ("buyback modified", "buyback_modified", lambda b: b["buyback"]["modified"]),
    ("basekit qty", "stock_basekit", lambda b: b["basekitTotal"]),
    ("depot qty", "stock_depot", lambda b: b["depotStock"]),
    ("total to procure", "stock_procure", lambda b: b["totalToProcure"]),
]


def columns_multiplier(market: Market) -> float:
    """The compounded effect of everything currently fired, before rounding."""
    mult = 1.0
    for ev in market.events:
        if ev["event_id"] in market.fired:
            mult *= 1.0 + float(ev.get("price_pct", 0.0)) / 100.0
    return round(mult, 4)


def main() -> int:
    bom = json.loads(BOM_PATH.read_text(encoding="utf-8"))
    sold = {i["id"]: i for i in bom["items"] if i["sold"]}
    not_sold = {i["id"]: i for i in bom["items"] if not i["sold"]}

    market = Market()

    # Snapshot the three price columns the BOM publishes. Fired in the order
    # they are meant to be fired on the day, because the math compounds.
    #
    # fire_event() writes to disk and appends to the market log, so everything
    # it touches is saved first and put back below - including history, or
    # running this check would leave "War fired" in the operator's log.
    saved = (
        dict(market.fired),
        market.global_pct,
        dict(market.item_pct),
        market.flash,
        list(market.history),
    )
    market.fired.clear()
    market.global_pct = 0.0
    market.item_pct.clear()

    columns = {"base": {i["item_id"]: i["live_price"] for i in market.priced_items()}}
    for event_id, column in (("WAR", "war"), ("TARIFF", "tariff")):
        market.fire_event(event_id)
        columns[column] = {i["item_id"]: i["live_price"] for i in market.priced_items()}

    priced = {i["item_id"]: i for i in market.priced_items()}
    cumulative = columns_multiplier(market)

    # Put the live state back exactly as it was. This script is safe to run on
    # the admin machine mid-event; it must not un-fire a war to do its job.
    (market.fired, market.global_pct, market.item_pct,
     market.flash, market.history) = saved
    market._save_state()

    problems: list[str] = []

    for iid, b in sold.items():
        if iid not in priced:
            problems.append(f"{iid}: sold in the BOM, missing from config/market.json")
            continue
        for column, want in b["price"].items():
            got = columns[column][iid]
            if got != want:
                problems.append(f"{iid}: {column} price is {got}, BOM says {want}")
        for label, ours, pull in FIELDS:
            got, want = priced[iid][ours], pull(b)
            if got != want:
                problems.append(f"{iid}: {label} is {got!r}, BOM says {want!r}")

    for iid in set(priced) - set(sold):
        why = "not sold in the BOM" if iid in not_sold else "not in the BOM at all"
        problems.append(f"{iid}: priced on the depot board but {why}")

    configured_not_sold = {i["item_id"] for i in market.not_sold}
    for iid in set(not_sold) - configured_not_sold:
        problems.append(f"{iid}: facilitator-only in the BOM, not listed in not_sold")

    kit = sum(i["stock_basekit"] for i in priced.values())
    kit += sum(i["stock"]["basekit"] for i in market.not_sold)
    depot = sum(i["stock_depot"] for i in priced.values())
    for label, got, want in (
        ("basekit pieces", kit, bom["totals"]["basekitPieces"]),
        ("depot pieces", depot, bom["totals"]["depotPieces"]),
    ):
        if got != want:
            problems.append(f"total {label} is {got}, BOM says {want}")

    if problems:
        print(f"config/market.json DISAGREES WITH THE BOM - {len(problems)} problem(s):\n")
        for p in problems:
            print(f"  · {p}")
        print(f"\nThe BOM wins. Fix config/market.json, not {BOM_PATH.name}.")
        return 1

    print(
        f"config/market.json agrees with the BOM: {len(sold)} sellable lines "
        f"checked at base, war and tariff, plus names, MOQ, buyback and stock.\n"
        f"{kit} basekit pieces · {depot} depot pieces · "
        f"every event fired = ×{cumulative:g} of base"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
