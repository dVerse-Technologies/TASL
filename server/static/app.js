/* TASL dashboard client.
 *
 * Talks to the server over one WebSocket. The server pushes:
 *   snapshot  - full state (on connect, and after a reset)
 *   node      - one node's state changed (heartbeat, or went offline)
 *   event     - something happened; carries the node state AND the log record
 *   run       - run started / stopped
 *
 * If the socket drops we reconnect automatically. At a live event the laptop
 * lid gets closed, Wi-Fi hiccups, someone reloads - it has to just come back.
 *
 * This is the screen participants stand in front of, so it shows the ball and
 * nothing else. Troubleshooting lives on /admin, out of their sight.
 */

(() => {
  "use strict";

  const state = {
    run: { active: false, started_wall: null, ball_at_order: 0, run_name: "Marble Run" },
    nodes: [],
    events: [],
  };

  const $ = (id) => document.getElementById(id);
  const el = { linkDot: $("link-dot"), runName: $("run-name"), elapsed: $("elapsed"),
               chain: $("chain"), cards: $("cards"), log: $("log") };

  /* ------------------------------------------------------------ formatting */

  const pad = (n, w = 2) => String(n).padStart(w, "0");

  function clockTime(wall) {
    if (!wall) return "--:--:--.---";
    const d = new Date(wall * 1000);
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
  }

  function shortTime(wall) {
    if (!wall) return "--:--:--";
    const d = new Date(wall * 1000);
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(Math.floor(d.getMilliseconds() / 100), 1)}`;
  }

  function fmtDt(us) {
    if (us === null || us === undefined) return null;
    return us >= 1000000 ? `${(us / 1e6).toFixed(3)} s` : `${(us / 1000).toFixed(1)} ms`;
  }

  function fmtSpeed(mps) {
    if (mps === null || mps === undefined) return null;
    return `${mps.toFixed(3)}`;
  }

  /* --------------------------------------------------------- battery icon */

  // Fill is DISCRETE per state, not a linear map of voltage. A 1S LiPo's
  // voltage curve is flat through most of its usable charge and then falls off
  // a cliff, so a proportional bar would sit near "full" and then plummet -
  // worse than useless. Four steps that mean OK / getting low / low / replace
  // it now is the honest reading.
  //
  // The fill level is deliberately redundant with the colour, so the icon
  // still reads correctly on a washed-out projector and for colour-blind
  // viewers.
  const BATT_FILL = { GREEN: 27, YELLOW: 17, RED: 8, CRITICAL: 5, UNKNOWN: 0 };

  // Millivolts -> percentage, mapped linearly across the usable 1S LiPo window
  // (3.40 V empty, 4.20 V full). Computed here rather than on the node so the
  // mapping can be changed without reflashing twenty boards.
  //
  // Read it as detail, not as a fuel gauge: the cell's discharge curve is flat,
  // so this number loiters in the 60-90 range for most of the battery's life
  // and then drops quickly. The colour and fill level are what the four-state
  // decision (leave it / swap at next reset / swap now) is based on.
  const BATT_EMPTY_MV = 3400;
  const BATT_FULL_MV  = 4200;

  function battPct(mv) {
    if (mv === null || mv === undefined) return null;
    const pct = ((mv - BATT_EMPTY_MV) / (BATT_FULL_MV - BATT_EMPTY_MV)) * 100;
    return Math.max(0, Math.min(100, Math.round(pct)));
  }

  function battHtml(state, mv) {
    const s = BATT_FILL[state] !== undefined ? state : "UNKNOWN";
    const w = BATT_FILL[s];
    const pct = battPct(mv);
    // Voltage stays on hover - the percentage answers "roughly how much left",
    // the voltage is what you actually debug and calibrate against.
    const tip = mv ? `${state} - ${(mv / 1000).toFixed(2)} V` : "no battery report yet";
    // Dashes, not "0%", when nothing has been reported. A node with no divider
    // fitted must not look like a node that is flat.
    const label = pct === null ? "--" : `${pct}%`;
    return `
      <span class="batt ${s}" title="${tip}">
        <svg class="batticon" viewBox="0 0 40 20" aria-label="Battery ${s}">
          <rect class="shell" x="1" y="1" width="33" height="18" rx="3.5"/>
          <rect class="cap"   x="35" y="6.5" width="4" height="7" rx="1.5"/>
          ${w ? `<rect class="fill" x="4" y="4.5" width="${w}" height="11" rx="1.5"/>` : ""}
        </svg>
        <span class="battpct">${label}</span>
      </span>`;
  }

  /* ------------------------------------------------------------- elapsed */

  // Driven by requestAnimationFrame rather than the server, so it stays smooth
  // even when no packets are arriving.
  function tickElapsed() {
    const r = state.run;
    let ms = 0;
    if (r.started_wall) {
      const end = r.active ? Date.now() / 1000 : (r.ended_wall || r.started_wall);
      ms = Math.max(0, (end - r.started_wall) * 1000);
    }
    const total = Math.floor(ms / 100);
    const tenths = total % 10;
    const secs = Math.floor(total / 10) % 60;
    const mins = Math.floor(total / 600);
    el.elapsed.textContent = `${pad(mins)}:${pad(secs)}.${tenths}`;
    requestAnimationFrame(tickElapsed);
  }

  /* -------------------------------------------------------- progress chain */

  function renderChain() {
    const nodes = state.nodes;
    const at = state.run.ball_at_order || 0;
    // Once the ball clears the last station it belongs to FINISH, so the last
    // node must read as "done" rather than still holding the ball.
    const finished = nodes.length > 0 && at >= nodes[nodes.length - 1].order;
    const parts = [];

    parts.push(stopHtml("START", at > 0, false));
    for (const n of nodes) {
      parts.push(`<div class="link${at > n.order ? " done" : ""}"></div>`);
      parts.push(stopHtml(n.node_id, at > n.order || finished, at === n.order && !finished));
    }
    parts.push(`<div class="link${finished ? " done" : ""}"></div>`);
    parts.push(stopHtml("FINISH", false, finished));

    el.chain.innerHTML = parts.join("");
  }

  function stopHtml(name, done, here) {
    const cls = here ? "stop here" : done ? "stop done" : "stop";
    return `<div class="${cls}" id="stop-${name}">` +
           `<div class="bead"></div><div class="name">${name}</div></div>`;
  }

  // Fire the bead on the progress strip at the same instant its card flashes,
  // so the eye is drawn to both halves of the same event.
  function flashStop(nodeId) {
    const stop = document.getElementById(`stop-${nodeId}`);
    if (!stop) return;
    stop.classList.remove("pop");
    void stop.offsetWidth; // force reflow so the animation restarts
    stop.classList.add("pop");
  }

  /* ---------------------------------------------------------------- cards */

  function renderCards() {
    el.cards.innerHTML = state.nodes.map(cardHtml).join("");
  }

  function cardHtml(n) {
    const status = n.online ? "online" : "offline";
    const dt = fmtDt(n.last_dt_us);
    const sp = fmtSpeed(n.last_speed_mps);
    const rssi = n.rssi !== null && n.rssi !== undefined ? `${n.rssi} dBm` : "--";
    const fault = n.fault_count > 0
      ? `<span class="fault">${n.fault_count} fault${n.fault_count > 1 ? "s" : ""}</span>` : "";

    return `
    <article class="card ${status}" id="card-${n.node_id}" data-node="${n.node_id}">
      <div class="card-head">
        <div>
          <div class="card-id">${n.node_id}</div>
          <div class="card-label">${n.label}</div>
        </div>
        <div class="card-status ${status}">${status.toUpperCase()}</div>
      </div>

      <div class="readout">
        <div class="metric">
          <div class="k">&Delta;t (A&rarr;B)</div>
          <div class="v ${dt ? "" : "dim"}">${dt || "--"}</div>
        </div>
        <div class="metric">
          <div class="k">SPEED m/s</div>
          <div class="v ${sp ? "" : "dim"}">${sp || "--"}</div>
        </div>
      </div>

      <div class="metric" style="margin-bottom:10px">
        <div class="k">LAST BALL</div>
        <div class="v ${n.last_ball_wall ? "" : "dim"}" style="font-size:16px">
          ${n.last_ball_wall ? clockTime(n.last_ball_wall) : "no ball yet"}
        </div>
      </div>

      <div class="card-foot">
        ${battHtml(n.batt_state, n.batt_mv)}
        <span>${n.ball_count} balls ${fault}</span>
        <span title="Wi-Fi signal strength">${rssi}</span>
      </div>
    </article>`;
  }

  function flashCard(nodeId) {
    const card = document.getElementById(`card-${nodeId}`);
    if (!card) return;
    card.classList.remove("hit");
    void card.offsetWidth; // force reflow so the animation restarts
    card.classList.add("hit");
  }

  /* ------------------------------------------------------------------ log */

  function renderLog() {
    if (!state.events.length) {
      el.log.innerHTML = `<div class="empty">Waiting for events...</div>`;
      return;
    }
    el.log.innerHTML = state.events.slice(0, 120).map(logRowHtml).join("");
  }

  function logRowHtml(e) {
    let cls = "log-row", msg;
    if (e.event === "BALL_PASS") {
      cls += " pass";
      msg = `BALL &nbsp;${fmtDt(e.dt_us) || "?"} &nbsp;${fmtSpeed(e.speed_mps) || "?"} m/s`;
    } else if (e.event === "BOOT") {
      cls += " boot";
      msg = "booted";
    } else if (e.event === "LOW_BATTERY") {
      // The only fault where the number matters more than the label: "which
      // state did it fall to" is what decides whether you walk over now or at
      // the next reset. Voltage is shown here and nowhere else on the glance-path.
      cls += " fault";
      const v = e.batt_mv ? ` &nbsp;${(e.batt_mv / 1000).toFixed(2)} V` : "";
      msg = `LOW BATTERY &nbsp;${e.batt_state || "?"}${v}`;
    } else {
      cls += " fault";
      msg = e.event.replace(/_/g, " ");
    }
    return `<div class="${cls}"><span class="t">${shortTime(e.ts_wall)}</span>` +
           `<span class="n">${e.node_id}</span><span class="m">${msg}</span></div>`;
  }

  /* --------------------------------------------------------------- socket */

  let ws = null, retry = 500;

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => {
      retry = 500;
      el.linkDot.className = "dot up";
      // Tell the server which screen this is, so the admin panel can see
      // whether the build-space monitor is still connected.
      try { ws.send(JSON.stringify({ hello: "live" })); } catch { /* already closed */ }
    };

    ws.onclose = () => {
      el.linkDot.className = "dot down";
      setTimeout(connect, retry);
      retry = Math.min(retry * 2, 5000); // back off, but never give up
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      switch (msg.type) {
        case "snapshot":
          state.run = msg.run;
          state.nodes = msg.nodes;
          state.events = msg.events || [];
          el.runName.textContent = msg.run.run_name;
          document.title = `${msg.run.run_name} - Live`;
          renderCards(); renderChain(); renderLog();
          break;

        case "node":
          upsertNode(msg.node);
          break;

        case "event":
          upsertNode(msg.node);
          if (msg.run) { state.run = msg.run; renderChain(); }
          state.events.unshift(msg.event);
          state.events.length = Math.min(state.events.length, 300);
          renderLog();
          if (msg.event.event === "BALL_PASS") {
            flashCard(msg.event.node_id);
            flashStop(msg.event.node_id); // after renderChain, which rebuilt the DOM
          }
          break;

        case "run":
          state.run = msg.run;
          renderChain();
          break;
      }
    };
  }

  function upsertNode(node) {
    const i = state.nodes.findIndex((n) => n.node_id === node.node_id);
    if (i === -1) {
      state.nodes.push(node);
      state.nodes.sort((a, b) => a.order - b.order);
      renderCards();
      return;
    }
    state.nodes[i] = node;
    // Patch just this card so we don't nuke a running flash animation.
    const card = document.getElementById(`card-${node.node_id}`);
    if (card) {
      const wasHit = card.classList.contains("hit");
      card.outerHTML = cardHtml(node);
      if (wasHit) flashCard(node.node_id);
    } else {
      renderCards();
    }
  }

  /* -------------------------------------------------------------- controls */

  const post = (path) => fetch(path, { method: "POST" });
  $("btn-start").onclick = () => post("/api/run/start");
  $("btn-stop").onclick = () => post("/api/run/stop");
  $("btn-reset").onclick = () => {
    if (confirm("Reset the board for a new run?\n\n(The saved event log on disk is kept.)")) {
      post("/api/run/reset");
    }
  };

  connect();
  requestAnimationFrame(tickElapsed);
})();
