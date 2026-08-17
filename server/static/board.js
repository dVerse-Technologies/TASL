/* Renders the price board. Used by both the depot kiosk and the stage
 * projector, so the two screens are the same code as well as the same data.
 *
 * The BOM is 34 sellable lines in six groups. A single table of 34 rows on a
 * kiosk with no scrollbar shrinks the type to the point of uselessness, so the
 * board lays the groups out in newspaper columns instead - the same groups, in
 * the same order, as the "Parts at the depot" pages of the printed team guide
 * books. Someone walking up with a book open should be able to put a finger on
 * a line in the book and find the same line in the same place on the board.
 *
 * The only cleverness here is change detection: it remembers the last price it
 * drew per item and flashes only the rows that actually moved. Repainting the
 * whole board on every message would either flash everything constantly or
 * flash nothing at all, and the point of the board is that a price change is
 * impossible to miss.
 */

const Board = (() => {
  "use strict";

  const lastPrice = new Map();
  let lastMult = null;
  let lastSig = null;   // group/item structure, so we only rebuild when it changes
  let primed = false;   // first paint must not flash the entire board

  function render(market, root) {
    if (!market) return;
    const sym = market.currency_symbol || "";
    const mult = market.effective_mult == null ? 1 : market.effective_mult;

    /* ---- hike badge -------------------------------------------------- */
    // A multiplier, not a percentage. Rounding up after each event means the
    // items do not all move by the same percentage - 25mm pipe at 60 ends up
    // +83% while 32mm pipe at 200 ends up +60% - but x1.56 is exactly what was
    // announced from the stage, and it is true of every line on the board.
    const badge = root.querySelector(".hike");
    if (badge) {
      const cls = mult > 1 ? "up" : mult < 1 ? "down" : "flat";
      const label = mult > 1 ? "PRICES UP" : mult < 1 ? "PRICES DOWN" : "PRICES AT BASE";
      badge.className = `hike ${cls}`;
      badge.querySelector(".k").textContent = label;
      badge.querySelector(".v").textContent = mult === 1 ? "—" : `×${trim(mult)}`;
      if (primed && mult !== lastMult) {
        badge.classList.remove("bump");
        void badge.offsetWidth; // restart the animation
        badge.classList.add("bump");
      }
      lastMult = mult;
    }

    /* ---- groups and rows --------------------------------------------- */
    const groups = market.groups && market.groups.length
      ? market.groups
      : [{ group_id: "", name: "MATERIALS", note: "" }];

    const wrap = root.querySelector(".groups");
    if (wrap) {
      // Rebuild the skeleton only when the item list itself changes, which in
      // practice means never during an event. Prices are then written into the
      // existing cells, so the browser is not throwing away and re-laying-out
      // 34 rows every time a percentage moves.
      const sig = `${groups.map((g) => g.group_id).join("|")}::${market.items.map((i) => i.item_id).join("|")}`;
      if (sig !== lastSig) {
        // Drives the type size in board.css: everything has to fit a screen
        // that cannot scroll, so a longer BOM shrinks rather than silently
        // losing its last few lines off the bottom. Group headings are taller
        // than rows, hence the 1.8.
        const lines = market.items.length + groups.length * 1.8;
        root.style.setProperty("--rows", Math.max(Math.ceil(lines), 8));
        wrap.innerHTML = groups.map((g) => groupHtml(g, market.items)).join("");
        lastSig = sig;
      }

      for (const it of market.items) {
        const row = wrap.querySelector(`[data-item="${cssEsc(it.item_id)}"]`);
        if (!row) continue;
        paintRow(row, it, sym);
        if (primed && lastPrice.get(it.item_id) !== it.live_price) {
          row.classList.remove("moved");
          void row.offsetWidth;
          row.classList.add("moved");
        }
      }
    }
    for (const it of market.items) lastPrice.set(it.item_id, it.live_price);

    /* ---- footer ------------------------------------------------------ */
    const foot = root.querySelector(".foot-note");
    if (foot) {
      const fired = (market.events || []).filter((e) => e.fired);
      foot.innerHTML = fired.length
        ? `IN EFFECT: ${fired.map((e) => `<span class="tag">${esc(e.name).toUpperCase()} ${TASL.pct(e.price_pct)}</span>`).join(" &nbsp;·&nbsp; ")}`
        : "NO MARKET EVENTS IN EFFECT";
    }

    // Facilitator-only lines. Printed so the counter has something to point at
    // rather than having the same conversation ten times.
    const ns = root.querySelector(".foot-notsold");
    if (ns) {
      const rows = market.not_sold || [];
      ns.innerHTML = rows.length
        ? `NOT SOLD: ${rows.map((i) => esc(i.name).toUpperCase()).join(" &nbsp;·&nbsp; ")}`
        : "";
    }

    const cur = root.querySelector(".foot-currency");
    if (cur) cur.textContent = `PRICES IN ${(market.currency || "").toUpperCase()}`;

    primed = true;
  }

  function groupHtml(g, items) {
    const mine = items.filter((it) => (it.group || "") === (g.group_id || ""));
    if (!mine.length) return "";
    return `
      <section class="group">
        <h2 class="group-head">
          <span class="g-name">${esc(g.name).toUpperCase()}</span>
          ${g.note ? `<span class="g-note">${esc(g.note)}</span>` : ""}
        </h2>
        ${mine.map(rowHtml).join("")}
      </section>`;
  }

  function rowHtml(it) {
    return `
      <div class="row" data-item="${esc(it.item_id)}">
        <span class="name">${esc(it.name)}${it.unit ? `<span class="unit">${esc(it.unit)}</span>` : ""}</span>
        <span class="buy"></span>
        <span class="base num"></span>
        <span class="live num"></span>
      </div>`;
  }

  function paintRow(row, it, sym) {
    // Only show the struck-through base price once it differs from the live
    // one. Before any event fires, "60 was 60" on every row is noise.
    row.className = `row ${!it.changed ? "" : it.live_price > it.base_price ? "changed" : "cheaper"}`;
    row.querySelector(".base").textContent = it.changed ? `${sym}${TASL.money(it.base_price)}` : "";
    row.querySelector(".live").innerHTML =
      `<span class="sym">${sym}</span>${TASL.money(it.live_price)}`;

    // Buyback is a constant against the base price and never moves with the
    // market - that is the whole point of it, otherwise teams arbitrage the
    // price shocks. Shown on the depot kiosk, where the counter needs it to
    // settle a return in a queue; hidden on the stage by board.css, where it
    // is just noise across a hall.
    row.querySelector(".buy").textContent =
      `${TASL.money(it.buyback_fresh)}/${TASL.money(it.buyback_modified)}`;
  }

  // 1.56 not 1.5600, 1.2 not 1.2000.
  function trim(n) {
    return String(Number(Number(n).toFixed(4)));
  }

  // The item names come from a config file the team edits by hand the week of
  // the event. An unescaped ampersand should not be able to break the board.
  function esc(s) {
    return String(s ?? "").replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  // item_id comes from the BOM and contains characters an attribute selector
  // treats as syntax, so escape it before querying rather than trusting it.
  function cssEsc(s) {
    return (window.CSS && CSS.escape) ? CSS.escape(String(s)) : String(s).replace(/["\\]/g, "\\$&");
  }

  function bindLink(root) {
    const dot = root.querySelector(".link-dot");
    const veil = document.querySelector(".offline-veil");
    return (connected) => {
      if (dot) dot.className = `link-dot ${connected ? "up" : "down"}`;
      if (veil) veil.classList.toggle("on", !connected);
    };
  }

  return { render, bindLink, esc };
})();
