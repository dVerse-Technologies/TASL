# Machine-readable data

Source of truth for anything built in parallel — the live price display, the trigger panel, the sensor readout.

| File | Contents |
|---|---|
| `materials.json` | Every item: group, MOQ, base/war/tariff price, buyback, basekit total, depot stock, per-team kit quantities |
| `events.json` | God Mode events, multipliers, caps and rules |
| `coins.json` | Denominations, basekit coins, both depot stashes, total mint |
| `teams.json` | Path assignment, per-team challenge and goal, per-team basekit |

## Price model

```
livePrice = base
on "war"    → livePrice = roundUpTo10(livePrice × 1.2)
on "tariff" → livePrice = roundUpTo10(livePrice × 1.3)
```

Both events compound; cumulative effect is ×1.56.

**Buyback never moves.** It is always against `price.base`, never the live price — `buyback.fresh` for unused material, `buyback.modified` for cut but usable. Every base price is a multiple of 20, so `modified` is always payable in coins.

`war` and `tariff` in `materials.json` are pre-computed for display; recompute from `base` if you change the multipliers.

## Regenerating

`materials.json`, `events.json`, `coins.json` and `teams.json` are generated. If quantities or prices change, regenerate rather than hand-editing, so the documents and the data cannot drift.
