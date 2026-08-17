/* Shared state bus for the depot, stage and admin screens.
 *
 * One WebSocket to the server. The server pushes `snapshot` on connect and
 * after any wholesale change, and narrower messages after that. This file
 * folds them all into one live object and calls your render function.
 *
 * The reconnect behaviour is the important part. These machines sit in kiosk
 * mode for the whole event: the Wi-Fi will hiccup, someone will unplug the
 * wrong thing, the server will get restarted. Every screen has to come back on
 * its own, without anyone walking over to it, and re-sync from the snapshot.
 *
 * (index.html predates this and keeps its own equivalent socket - it is the
 * one that has been through live testing, so it was left alone.)
 */

const TASL = (() => {
  "use strict";

  const state = { run: null, nodes: [], events: [], market: null, screens: {}, connected: false };
  const listeners = [];

  // Which screen this is. Read from <body data-role="stage"> and sent to the
  // server on connect, purely so the admin panel can show what is plugged in.
  const ROLE = document.body?.dataset?.role || "unknown";

  function onState(fn) {
    listeners.push(fn);
    if (state.market) fn(state);
  }

  function emit() {
    for (const fn of listeners) {
      try { fn(state); } catch (err) { console.error(err); }
    }
  }

  let ws = null, retry = 500;

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => {
      retry = 500;
      state.connected = true;
      try { ws.send(JSON.stringify({ hello: ROLE })); } catch { /* closed already */ }
      emit();
    };

    ws.onclose = () => {
      state.connected = false;
      emit();
      setTimeout(connect, retry);
      retry = Math.min(retry * 2, 5000); // back off, but never give up
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (m) => {
      let msg;
      try { msg = JSON.parse(m.data); } catch { return; }

      switch (msg.type) {
        case "snapshot":
          state.run = msg.run;
          state.nodes = msg.nodes || [];
          state.events = msg.events || [];
          state.market = msg.market;
          state.screens = msg.screens || {};
          break;

        case "market":
          state.market = msg.market;
          break;

        case "screens":
          state.screens = msg.screens || {};
          break;

        case "node":
          upsertNode(msg.node);
          return emitNodeOnly();

        case "event":
          upsertNode(msg.node);
          if (msg.run) state.run = msg.run;
          state.events.unshift(msg.event);
          state.events.length = Math.min(state.events.length, 300);
          break;

        case "run":
          state.run = msg.run;
          break;

        default:
          return;
      }
      emit();
    };
  }

  // Heartbeats arrive from every node every 2 s. With 20 nodes that is 10 a
  // second, and a price board has no reason to repaint for any of them. Screens
  // that do care (admin diagnostics) opt in.
  const nodeListeners = [];
  function onNodes(fn) { nodeListeners.push(fn); }
  function emitNodeOnly() {
    for (const fn of nodeListeners) {
      try { fn(state); } catch (err) { console.error(err); }
    }
  }

  function upsertNode(node) {
    if (!node) return;
    const i = state.nodes.findIndex((n) => n.node_id === node.node_id);
    if (i === -1) {
      state.nodes.push(node);
      state.nodes.sort((a, b) => a.order - b.order);
    } else {
      state.nodes[i] = node;
    }
  }

  const post = (path, body) =>
    fetch(path, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });

  /* ------------------------------------------------------------ formatting */

  // Grouped with a thin space rather than a comma. The prices are paid in
  // physical coins and get read aloud across a noisy hall; "1 700" is harder
  // to misread at a glance than "1,700".
  function money(n) {
    if (n === null || n === undefined) return "--";
    return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }

  function pct(n) {
    if (!n) return "0%";
    return `${n > 0 ? "+" : ""}${Number(n.toFixed(2))}%`;
  }

  function clockTime(wall) {
    if (!wall) return "--:--";
    const d = new Date(wall * 1000);
    const p = (x) => String(x).padStart(2, "0");
    return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }

  connect();

  return { state, onState, onNodes, post, money, pct, clockTime };
})();
