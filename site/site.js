// Page behavior: header hairline, copy buttons, build stats, chart pins,
// tour tabs with #tour/<id> links, and the screenshot lightbox.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  // Header hairline after scroll.
  const nav = $(".nav");
  const onScroll = () => nav.classList.toggle("scrolled", scrollY > 4);
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // Copy buttons keep their width; the label swaps to a check.
  for (const btn of $$(".copy")) {
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
      } catch {
        return;
      }
      const label = btn.querySelector("span");
      btn.classList.add("done");
      label.textContent = "✓ Copied";
      clearTimeout(btn._t);
      btn._t = setTimeout(() => {
        btn.classList.remove("done");
        label.textContent = "Copy";
      }, 1600);
    });
  }

  // Numbers counted at build time (site/scripts/build_demo.py).
  fetch("demo/stats.json")
    .then((r) => (r.ok ? r.json() : null))
    .then((stats) => {
      if (!stats) return;
      for (const el of $$("[data-stat]")) {
        const v = stats[el.dataset.stat];
        if (v != null) el.textContent = typeof v === "number" ? v.toLocaleString("en-US") : v;
      }
    })
    .catch(() => {});

  // Chart pins: hover a list item to light its pin.
  for (const li of $$(".pins li")) {
    const pin = $(`.pin[data-pin="${li.dataset.pin}"]`);
    const on = (v) => {
      li.classList.toggle("on", v);
      pin?.classList.toggle("on", v);
    };
    li.addEventListener("mouseenter", () => on(true));
    li.addEventListener("mouseleave", () => on(false));
  }

  // Tour tabs: arrows, Home and End; the URL follows the selection.
  const tabs = $$('.tabs [role="tab"]');
  function select(id, focus = false, push = true) {
    const tab = tabs.find((t) => t.dataset.tab === id) || tabs[0];
    for (const t of tabs) {
      const on = t === tab;
      t.setAttribute("aria-selected", on);
      t.tabIndex = on ? 0 : -1;
      $("#" + t.getAttribute("aria-controls")).hidden = !on;
    }
    if (focus) tab.focus();
    if (push) history.replaceState(null, "", "#tour/" + tab.dataset.tab);
  }
  for (const t of tabs) {
    t.addEventListener("click", () => select(t.dataset.tab));
    t.addEventListener("keydown", (e) => {
      const i = tabs.indexOf(t);
      const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
      if (next == null) return;
      e.preventDefault();
      select(tabs[(next + tabs.length) % tabs.length].dataset.tab, true);
    });
  }
  function fromHash() {
    const m = location.hash.match(/^#tour\/([\w-]+)/);
    if (!m) return;
    select(m[1], false, false);
    $("#tour").scrollIntoView();
  }
  addEventListener("hashchange", fromHash);
  fromHash();

  // Lightbox: opens fitted, click zooms 2x at the point, drag pans,
  // arrows step through the shots, Esc closes.
  const box = $("#lightbox");
  const stage = $("#lbStage");
  const img = $("#lbImg");
  const shots = $$(".zoomable");
  let index = 0;
  let view = { s: 1, x: 0, y: 0 };
  let fit = 1;
  let opener = null;

  const apply = () => {
    img.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.s})`;
    stage.classList.toggle("zoomed", view.s > fit + 0.001);
  };
  const clamp = () => {
    const w = img.naturalWidth * view.s;
    const h = img.naturalHeight * view.s;
    const W = stage.clientWidth;
    const H = stage.clientHeight;
    view.x = w <= W ? (W - w) / 2 : Math.min(0, Math.max(W - w, view.x));
    view.y = h <= H ? (H - h) / 2 : Math.min(0, Math.max(H - h, view.y));
  };
  const fitView = () => {
    fit = Math.min(stage.clientWidth / img.naturalWidth, stage.clientHeight / img.naturalHeight);
    view = { s: fit, x: 0, y: 0 };
    clamp();
    apply();
  };
  const zoomAt = (s, px, py) => {
    const k = s / view.s;
    view = { s, x: px - (px - view.x) * k, y: py - (py - view.y) * k };
    clamp();
    apply();
  };
  function show(i) {
    index = (i + shots.length) % shots.length;
    const shot = shots[index];
    $("#lbTitle").textContent = `${shot.dataset.title}  ·  ${index + 1} of ${shots.length}`;
    img.alt = shot.querySelector("img").alt;
    img.onload = fitView;
    img.src = shot.dataset.full;
    if (img.complete && img.naturalWidth) fitView();
  }
  for (const [i, shot] of shots.entries()) {
    shot.addEventListener("click", () => {
      opener = shot;
      box.showModal();
      show(i);
      $("#lbClose").focus();
    });
  }
  $("#lbClose").addEventListener("click", () => box.close());
  $("#lbPrev").addEventListener("click", () => show(index - 1));
  $("#lbNext").addEventListener("click", () => show(index + 1));
  $("#lbActual").addEventListener("click", () => zoomAt(1, stage.clientWidth / 2, stage.clientHeight / 2));
  box.addEventListener("close", () => {
    img.removeAttribute("src");
    opener?.focus();
  });
  box.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") show(index + 1);
    else if (e.key === "ArrowLeft") show(index - 1);
  });
  addEventListener("resize", () => box.open && fitView());

  let drag = null;
  stage.addEventListener("pointerdown", (e) => {
    drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false };
    stage.setPointerCapture(e.pointerId);
  });
  stage.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x;
    const dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    drag.moved = true;
    stage.classList.add("dragging");
    view.x = drag.vx + dx;
    view.y = drag.vy + dy;
    clamp();
    apply();
  });
  stage.addEventListener("pointerup", (e) => {
    stage.classList.remove("dragging");
    const d = drag;
    drag = null;
    if (!d || d.moved) return;
    const r = stage.getBoundingClientRect();
    const px = e.clientX - r.left;
    const py = e.clientY - r.top;
    // A click outside the image closes the viewer.
    const ir = img.getBoundingClientRect();
    if (e.clientX < ir.left || e.clientX > ir.right || e.clientY < ir.top || e.clientY > ir.bottom) {
      box.close();
      return;
    }
    if (view.s > fit + 0.001) fitView();
    else zoomAt(Math.min(fit * 2, Math.max(fit * 1.5, 1)), px, py);
  });
})();
