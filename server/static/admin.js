/* The admin panel. One person, one monitor, out of the participants' sight.
 *
 * Three jobs: fire the news events, adjust prices by hand, and show the
 * diagnostics that used to sit behind a wrench icon on the public dashboard.
 *
 * The rendering rule throughout: never repaint a control the operator is
 * currently typing into. Market state is pushed on every change, and a naive
 * re-render would wipe a half-typed percentage out from under them.
 */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  /* ------------------------------------------------------- run elapsed */

  const pad = (n, w = 2) => String(n).padStart(w, "0");

  function tickElapsed() {
    const r = TASL.state.run;
    let ms = 0;
    if (r && r.started_wall) {
      const end = r.active ? Date.now() / 1000 : (r.ended_wall || r.started_wall);
      ms = Math.max(0, (end - r.started_wall) * 1000);
    }
    const total = Math.floor(ms / 100);
    $("elapsed").textContent =
      `${pad(Math.floor(total / 600))}:${pad(Math.floor(total / 10) % 60)}.${total % 10}`;
    requestAnimationFrame(tickElapsed);
  }

  /* ----------------------------------------------------------- triggers */

  // Two-step firing. The first click arms the button and relabels it; the
  // second, within four seconds, actually fires. A modal confirm() would be
  // safer still but these machines run in kiosk mode and an OS dialog in front
  // of a room is worse than a button that changes colour.
  const armedTrigger = { id: null, timer: null };

  function armTrigger(eventId) {
    clearTimeout(armedTrigger.timer);
    armedTrigger.id = eventId;
    armedTrigger.timer = setTimeout(() => {
      armedTrigger.id = null;
      renderTriggers(TASL.state.market);
    }, 4000);
    renderTriggers(TASL.state.market);
  }

  function disarm() {
    clearTimeout(armedTrigger.timer);
    armedTrigger.id = null;
  }

  function renderTriggers(market) {
    if (!market) return;
    $("triggers").innerHTML = market.events.map((ev) => {
      const armed = armedTrigger.id === ev.event_id;
      const label = ev.fired ? "FIRED" : armed ? "CONFIRM &mdash; FIRE" : `FIRE ${esc(ev.name).toUpperCase()}`;
      return `
        <div class="trigger ${ev.fired ? "is-fired" : ""}">
          <div class="trigger-meta">
            <div class="trigger-name">${esc(ev.name)}</div>
            <div class="trigger-sub">
              Planned for the <b>${esc(ev.planned_at || "operator's call")}</b> &nbsp;·&nbsp;
              multiplies every price <b>currently on the board</b> by
              <b>${TASL.pct(ev.price_pct)}</b>, rounded up to the nearest 10
              <br>${esc(ev.headline)}
            </div>
          </div>
          <button class="btn-fire ${ev.fired ? "fired" : ""}"
                  data-fire="${ev.event_id}" ${ev.fired ? "disabled" : ""}>${label}</button>

          <div class="trigger-actions">
            <span class="fired-at">
              ${ev.fired ? `FIRED AT ${TASL.clockTime(ev.fired_wall)}` : "NOT YET FIRED"}
            </span>
            <span class="spacer"></span>
            <button class="btn-sm" data-flash="${ev.event_id}">REPLAY ON STAGE</button>
            <button class="btn-sm danger" data-unfire="${ev.event_id}"
                    ${ev.fired ? "" : "disabled"}>UNDO PRICE CHANGE</button>
          </div>
        </div>`;
    }).join("");
  }

  $("triggers").addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;

    if (btn.dataset.fire) {
      const id = btn.dataset.fire;
      if (armedTrigger.id !== id) return armTrigger(id);
      disarm();
      await TASL.post(`/api/market/fire/${id}`);
      return;
    }
    if (btn.dataset.flash) {
      await TASL.post(`/api/market/flash/${btn.dataset.flash}`);
      return;
    }
    if (btn.dataset.unfire) {
      const id = btn.dataset.unfire;
      if (!confirm(`Undo ${id}?\n\nIts price change is reversed on every screen ` +
                   `immediately. Use this if it was fired by mistake.`)) return;
      await TASL.post(`/api/market/unfire/${id}`);
    }
  });

  /* ------------------------------------------------------------ pricing */

  // The 34 BOM lines are grouped exactly as they are on the depot board and in
  // the printed books, so "find 32mm bend 45" is the same search in all three.
  // Built once, then only the numbers are written - a wholesale repaint would
  // wipe out a per-item percentage the operator is halfway through typing.
  let itemRowsBuilt = false;

  function buildItemRows(market) {
    const tbody = $("item-rows");
    const groups = market.groups && market.groups.length
      ? market.groups
      : [{ group_id: "", name: "Materials", note: "" }];

    tbody.innerHTML = groups.map((g) => {
      const mine = market.items.filter((it) => (it.group || "") === (g.group_id || ""));
      if (!mine.length) return "";
      const head =
        `<tr class="group-row"><th colspan="7">${esc(g.name).toUpperCase()}` +
        `${g.note ? ` <span class="g-note">${esc(g.note)}</span>` : ""}</th></tr>`;
      return head + mine.map((it) =>
        `<tr data-item="${esc(it.item_id)}">
           <td class="iname"></td>
           <td class="iunit"></td>
           <td class="ibase num"></td>
           <td class="ibuy num"></td>
           <td class="istock num"></td>
           <td class="num"><input class="pct sm" type="number" step="5"
                                  data-item-pct="${esc(it.item_id)}"></td>
           <td class="ilive num"></td>
         </tr>`).join("");
    }).join("");

    const ns = $("not-sold-note");
    const rows = market.not_sold || [];
    ns.innerHTML = rows.length
      ? `<b>Not sold at the depot:</b> ${rows.map((i) =>
           `${esc(i.name)} (${i.stock.basekit} in kits)`).join(" · ")}. ` +
        `Ball size is a facilitator lever — no team can buy its way to a different one.`
      : "";
  }

  function renderPricing(market) {
    if (!market) return;
    const mult = market.effective_mult == null ? 1 : market.effective_mult;

    const tv = $("total-pct");
    tv.textContent = mult === 1 ? "—" : `×${String(Number(mult.toFixed(4)))}`;
    tv.className = `v ${mult > 1 ? "up" : mult < 1 ? "down" : "flat"}`;

    // Leave the field alone while it has focus - the operator is mid-keystroke.
    const gi = $("global-pct");
    if (document.activeElement !== gi) gi.value = market.global_pct;

    if (!itemRowsBuilt) {
      buildItemRows(market);
      itemRowsBuilt = true;
    }

    const sym = market.currency_symbol || "";
    const tbody = $("item-rows");

    for (const it of market.items) {
      const tr = tbody.querySelector(`tr[data-item="${cssEsc(it.item_id)}"]`);
      if (!tr) continue;
      tr.className = !it.changed ? "" : it.live_price > it.base_price ? "up" : "down";
      tr.querySelector(".iname").textContent = it.name;
      tr.querySelector(".iunit").textContent = it.unit;
      tr.querySelector(".ibase").textContent = `${sym}${TASL.money(it.base_price)}`;
      // Constants, both of them - buyback is against base and never moves.
      tr.querySelector(".ibuy").textContent =
        `${TASL.money(it.buyback_fresh)} / ${TASL.money(it.buyback_modified)}`;
      // What was put in the ten team boxes vs what is on the depot shelf. The
      // depot board deliberately does not show this: a visible count turns a
      // shortage into a race.
      tr.querySelector(".istock").textContent =
        `${TASL.money(it.stock_basekit)} / ${TASL.money(it.stock_depot)}`;
      tr.querySelector(".ilive").textContent =
        `${sym}${TASL.money(it.live_price)}${it.changed ? `  (${TASL.pct(it.pct)})` : ""}`;
      const input = tr.querySelector("input");
      if (document.activeElement !== input) input.value = it.item_pct || 0;
    }
  }

  const applyGlobal = () =>
    TASL.post("/api/market/global", { pct: Number($("global-pct").value) || 0 });

  $("btn-global-apply").onclick = applyGlobal;
  $("btn-global-zero").onclick = () => { $("global-pct").value = 0; applyGlobal(); };
  $("global-pct").addEventListener("keydown", (e) => { if (e.key === "Enter") applyGlobal(); });

  // Per-item values commit on blur or Enter, not on every keystroke - typing
  // "-10" would otherwise briefly apply "-1" to a live board.
  $("item-rows").addEventListener("change", (e) => {
    const input = e.target.closest("input[data-item-pct]");
    if (!input) return;
    TASL.post(`/api/market/item/${input.dataset.itemPct}`, { pct: Number(input.value) || 0 });
  });
  $("item-rows").addEventListener("keydown", (e) => {
    if (e.key === "Enter") e.target.blur();
  });

  $("btn-market-reset").onclick = () => {
    if (!confirm("Reset the market to base prices?\n\nThis un-fires every event and " +
                 "clears all manual adjustments on every screen. Intended for between " +
                 "rehearsal runs, not during the event.")) return;
    TASL.post("/api/market/reset");
  };

  /* -------------------------------------------------------- stage strip */

  function renderStage(market) {
    const strip = $("stage-strip");
    const f = market && market.flash;
    strip.hidden = !f;
    if (!f) return;
    const ev = market.events.find((e) => e.event_id === f.event_id);
    const how = f.video ? "video clip" : "news slate";
    const dur = f.seconds > 0 ? `${f.seconds}s` : "until dismissed";
    strip.querySelector(".what").textContent =
      `ON THE PROJECTOR NOW — ${(ev ? ev.name : f.event_id).toUpperCase()} (${how}, ${dur})`;
  }

  $("btn-dismiss").onclick = () => TASL.post("/api/market/dismiss");

  /* ------------------------------------------------------------ screens */

  const SCREENS = [
    { role: "stage", who: "STAGE PROJECTOR", where: "laptop on stage", path: "/stage" },
    { role: "depot", who: "DEPOT PRICES",    where: "MiniPC at the materials depot", path: "/depot" },
    { role: "live",  who: "BALL TRACKING",   where: "MiniPC by the build space", path: "/" },
    { role: "admin", who: "ADMIN",           where: "this machine", path: "/admin" },
  ];

  function renderScreens(screens) {
    $("screens").innerHTML = SCREENS.map((s) => {
      const n = screens[s.role] || 0;
      return `
        <div class="screen-row ${n > 0 ? "up" : ""}">
          <span class="pip"></span>
          <span class="who">${s.who}</span>
          <span class="where">${s.where}</span>
          <span class="n">${n === 0 ? "not connected" : n === 1 ? "connected" : `${n} tabs`}</span>
          <a href="${s.path}" target="_blank" rel="noopener">open</a>
        </div>`;
    }).join("");
  }

  /* ------------------------------------------------------------ history */

  function renderHistory(market) {
    const rows = (market && market.history) || [];
    $("history").innerHTML = rows.length
      ? rows.map((h) =>
          `<div class="hist-row ${h.kind}"><span class="t">${TASL.clockTime(h.wall)}</span>` +
          `<span class="m">${esc(h.text)}</span></div>`).join("")
      : `<div class="empty">Nothing has moved the market yet.</div>`;
  }

  /* -------------------------------------------------------------- render */

  TASL.onState((s) => {
    $("link-dot").className = `dot ${s.connected ? "up" : "down"}`;
    renderTriggers(s.market);
    renderPricing(s.market);
    renderStage(s.market);
    renderHistory(s.market);
    renderScreens(s.screens || {});
  });

  /* --------------------------------------------------------- run control */

  $("btn-start").onclick = () => TASL.post("/api/run/start");
  $("btn-stop").onclick = () => TASL.post("/api/run/stop");
  $("btn-reset").onclick = () => {
    if (confirm("Reset the marble run for a new attempt?\n\n(Prices and fired events " +
                "are NOT affected. The saved event log on disk is kept.)")) {
      TASL.post("/api/run/reset");
    }
  };

  /* ---------------------------------------------------------- diagnostics */

  // Lifted from the old dashboard unchanged. Polled rather than pushed: the
  // rules read accumulated counters, not single events, so there is nothing to
  // gain from recomputing them on every packet.
  const expanded = new Set();
  let lastDiagSig = null;

  async function pollDiagnostics() {
    try {
      const r = await fetch("/api/diagnostics");
      if (!r.ok) return;
      renderDiagnostics(await r.json());
    } catch (_) {
      /* server restarting; the next tick will catch up */
    }
  }

  function renderDiagnostics(d, force = false) {
    // Skip the repaint when nothing changed, otherwise the panel flickers
    // every three seconds while you are trying to read it.
    const sig = JSON.stringify(d.nodes);
    if (!force && sig === lastDiagSig) return;
    lastDiagSig = sig;

    const sum = $("diag-summary");
    if (!d.critical && !d.warnings) {
      sum.innerHTML = `<div class="sum-pill ok">ALL STATIONS HEALTHY</div>`;
    } else {
      const bits = [];
      if (d.critical) bits.push(`<div class="sum-pill critical">${d.critical} CRITICAL</div>`);
      if (d.warnings) bits.push(`<div class="sum-pill warning">${d.warnings} WARNING${d.warnings > 1 ? "S" : ""}</div>`);
      sum.innerHTML = bits.join("");
    }
    $("diag-list").innerHTML = d.nodes.map(diagNodeHtml).join("");
  }

  function diagNodeHtml(n) {
    const healthy = n.findings.length === 1 && n.findings[0].code === "OK";

    // A healthy station collapses to a single line, so the eye lands on the
    // broken ones rather than wading past the working ones.
    if (healthy) {
      return `
        <section class="diag-node ok-row">
          <span class="diag-node-id">${esc(n.node_id)}</span>
          <span class="diag-node-label">${esc(n.label)}</span>
          <span class="ok-tag">OK</span>
        </section>`;
    }

    return `
      <section class="diag-node ${n.worst}">
        <header class="diag-node-head">
          <span class="diag-node-id">${esc(n.node_id)}</span>
          <span class="diag-node-label">${esc(n.label)}</span>
          <span class="diag-node-state ${n.online ? "online" : "offline"}">
            ${n.online ? "ONLINE" : "OFFLINE"}
          </span>
        </header>
        ${n.findings.map((f) => findingHtml(n.node_id, f)).join("")}
      </section>`;
  }

  function findingHtml(nodeId, f) {
    const key = `${nodeId}:${f.code}`;
    const open = expanded.has(key);
    const checks = f.checks.length
      ? `<ol class="checks">${f.checks.map((c) => `<li>${c}</li>`).join("")}</ol>` : "";

    return `
      <div class="finding ${f.severity}${open ? " open" : ""}">
        <div class="finding-head">
          <span class="sev">${f.severity.toUpperCase()}</span>
          <span class="finding-title">${f.title}</span>
          <button class="explain-btn" data-key="${key}">${open ? "HIDE" : "EXPLAIN"}</button>
        </div>
        <div class="finding-body">
          <p class="finding-detail">${f.detail}</p>
          ${checks}
        </div>
      </div>`;
  }

  // Delegated, so the handlers survive every repoll.
  $("diag-list").addEventListener("click", (e) => {
    const btn = e.target.closest(".explain-btn");
    if (!btn) return;
    const key = btn.dataset.key;
    if (expanded.has(key)) expanded.delete(key);
    else expanded.add(key);
    btn.closest(".finding").classList.toggle("open", expanded.has(key));
    btn.textContent = expanded.has(key) ? "HIDE" : "EXPLAIN";
  });

  $("btn-diag-clear").onclick = async () => {
    if (!confirm("Clear the health counters?\n\nDo this after you have physically " +
                 "fixed something, so you can see whether the fault comes back.")) return;
    await fetch("/api/diagnostics/clear", { method: "POST" });
    expanded.clear();
    lastDiagSig = null; // force a repaint
    pollDiagnostics();
  };

  /* --------------------------------------------------------------- utils */

  // Names, headlines and tickers all come from a config file edited by hand
  // the week of the event. An unescaped ampersand should not break the panel.
  function esc(s) {
    return String(s ?? "").replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  // item_id comes from the BOM and contains characters an attribute selector
  // treats as syntax, so escape it before querying rather than trusting it.
  function cssEsc(s) {
    return (window.CSS && CSS.escape) ? CSS.escape(String(s)) : String(s).replace(/["\\]/g, "\\$&");
  }

  requestAnimationFrame(tickElapsed);
  pollDiagnostics();
  setInterval(pollDiagnostics, 3000);
})();
