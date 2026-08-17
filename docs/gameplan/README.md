# GamePlan — TASL Marble Run

Working documents for the marble run day. Ten teams of six, four hours, one shared run.

## Contents

| Folder | What's in it |
|---|---|
| `01-Decisions/` | Decisions taken, and what's still open |
| `02-BOM/` | Basekit contents, totals, depot materials, procurement list |
| `03-Economy/` | Coins, trade rules, God Mode levers |
| `04-Crew/` | Who does what, phased across the day |
| `05-Awards/` | Award categories for the wrap-up |
| `06-Sizing/` | Pipe standardisation and the ball/bend physics behind it |
| `07-Team-Guides/` | Participant guide books |
| `data/` | Machine-readable JSON for parallel development — prices, events, coins, teams |
| `scripts/` | `push-gameplan.sh` to publish this folder; guide book generator |

## Stock sizing

The venue is remote and nothing can be sourced on the day. Depot stock is the greater of 1.5× basekit quantity, or enough to bring total availability to **twice estimated consumption**. Every line sits at or above 2×.

## The design in one paragraph

Two balls launch together from Team 1, travel two independent paths through the room, and must land in their buckets at the same time. Each team owns one section and must hand off to the next. Basekits are deliberately unequal so no team can finish alone. Coins are uniform at 2,000 Kasu per team, so any difference in outcome comes from material position and trading, not endowment. Prices at the depot rise with scripted news events, which squeezes teams who leave their buying late.

## Rules the design depends on

- A shortage may be inconvenient, never fatal. Anything that can deadlock the run is issued in kits and stocked deep.
- Designed scarcity lives in the kits and in price. The depot never runs out — depot stock is 1.5× basekit on every line.
- Buyback is always against the base price, never the live one. Without this, teams can arbitrage the price shocks.
- Balls are not purchasable. Ball size stays a facilitator lever.
