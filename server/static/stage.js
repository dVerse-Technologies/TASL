/* The stage projector.
 *
 * Idle it mirrors the depot price board. When the admin fires an event the
 * server puts a `flash` on the market state and this takes the screen over.
 *
 * Two decisions worth knowing about:
 *
 * 1. The flash timer is LOCAL, started when this page first sees a given
 *    flash - it does not compare the server's wall clock to its own. These
 *    machines are on an offline network with no NTP, so their clocks can be
 *    minutes apart, and a skewed clock would either cut the headline off
 *    instantly or leave it up forever. The cost is that reloading the page
 *    mid-flash replays it from the start, which is the harmless direction.
 *
 * 2. A missing video file is resolved to null by the server before it ever
 *    reaches here, so the built-in slate takes over. Nothing a typo in the
 *    config can do will leave the projector black.
 */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const boardRoot = $("board");
  const flashEl = $("flash");
  const video = $("flash-video");
  const setLink = Board.bindLink(boardRoot);

  let armed = false;       // has the page been clicked, so audio may play
  let shownKey = null;     // identity of the flash currently on screen
  let hideTimer = null;

  /* ------------------------------------------------------------- arming */

  const arm = $("arm");
  function doArm() {
    armed = true;
    arm.classList.remove("on");
    // If a flash is somehow already up when we arm, give it its sound back.
    if (!flashEl.classList.contains("on")) return;
    video.muted = false;
    video.play().catch(() => {});
  }
  arm.addEventListener("click", doArm);
  document.addEventListener("keydown", doArm, { once: false });

  /* -------------------------------------------------------------- flash */

  function flashKey(f) {
    return f ? `${f.event_id}@${f.started_wall}` : null;
  }

  function showFlash(f, market) {
    const ev = (market.events || []).find((e) => e.event_id === f.event_id);
    if (!ev) return;

    flashEl.style.setProperty("--accent", ev.accent || "#e0231f");
    $("fl-kicker").textContent = ev.kicker || "BREAKING";
    $("fl-headline").textContent = ev.headline || ev.name;
    $("fl-subhead").textContent = ev.subhead || "";
    $("fl-tag").textContent = (ev.name || "LIVE").toUpperCase();

    // State the price consequence as the number it actually is, including any
    // events already in effect - "materials are now x1.56" is what people need,
    // not "this event was +30%". A multiplier rather than a percentage because
    // the events compound and round up, so no single percentage is true of
    // every line on the board.
    const mult = market.effective_mult == null ? 1 : market.effective_mult;
    const impact = $("fl-impact");
    if (ev.price_pct) {
      impact.hidden = false;
      impact.innerHTML =
        `${ev.name.toUpperCase()} ${TASL.pct(ev.price_pct)} &nbsp;&mdash;&nbsp; ` +
        `MATERIALS NOW <span class="now">×${String(Number(mult.toFixed(4)))}</span> OF STARTING PRICE`;
    } else {
      impact.hidden = true;
    }

    // Doubled so the scroll loop has no visible seam.
    const line = ev.ticker || ev.subhead || "";
    $("fl-ticker").innerHTML = `<span>${Board.esc(line)}</span><span>${Board.esc(line)}</span>`;

    if (f.video) {
      flashEl.classList.add("has-video");
      if (video.getAttribute("src") !== f.video) video.setAttribute("src", f.video);
      video.currentTime = 0;
      video.muted = !armed;   // unarmed browsers refuse audio; show it silent
      video.play().catch(() => {
        // Autoplay refused outright. Fall back to the slate rather than
        // sitting on a frozen first frame.
        flashEl.classList.remove("has-video");
      });
    } else {
      flashEl.classList.remove("has-video");
      video.removeAttribute("src");
    }

    flashEl.classList.add("on");

    clearTimeout(hideTimer);
    // seconds = 0 means "stay up until the admin dismisses it".
    if (f.seconds > 0) {
      hideTimer = setTimeout(hideFlash, f.seconds * 1000);
    }
  }

  function hideFlash() {
    clearTimeout(hideTimer);
    flashEl.classList.remove("on");
    video.pause();
  }

  /* -------------------------------------------------------------- render */

  TASL.onState((s) => {
    setLink(s.connected);
    if (!s.market) return;

    Board.render(s.market, boardRoot);

    const f = s.market.flash;
    const key = flashKey(f);

    if (!f) {
      // Dismissed from the admin panel.
      if (shownKey !== null) { shownKey = null; hideFlash(); }
      return;
    }
    if (key === shownKey) return;  // same flash, already running its timer
    shownKey = key;
    showFlash(f, s.market);
  });
})();
