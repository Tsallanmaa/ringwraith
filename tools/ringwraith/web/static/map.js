"use strict";
// Ringwraith Table: the map view (Leaflet on the stage), with tokens, routes and a timeline.
// Positions are image pixels of each map; region maps sit on their parent through box_on_parent.

const RWMap = (() => {
  let lmap = null, data = null, cur = null, overlay = null;
  let lastPlan = null;                       // the plan last seen, to switch to a new one's map
  let hexLayer = null, fogLayer = null, showHex = false, showFog = false;
  let layer = null, tokenLayer = null, legLayer = null;
  let dayIndex = null, playing = false, playTimer = null;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const ll = (xy) => [-xy[1], xy[0]];

  // ------------------------------------------------------------------ geometry
  function project(mapId, xy, target) {
    let m = mapId, p = xy;
    while (m !== target) {
      const def = data.maps[m];
      if (!def || !def.parent || !def.box_on_parent) return null;
      const [[x0, y0], [x1, y1]] = def.box_on_parent;
      p = [x0 + (p[0] / def.size[0]) * (x1 - x0), y0 + (p[1] / def.size[1]) * (y1 - y0)];
      m = def.parent;
    }
    return p;
  }
  function chainOf(id) {
    const out = [id];
    while (data.maps[out[out.length - 1]] && data.maps[out[out.length - 1]].parent) out.push(data.maps[out[out.length - 1]].parent);
    return out;
  }
  function toMap(mapId, xy, target) {        // a point on one map, on another map of the same tree (or null)
    if (mapId === target) return xy;
    const up = chainOf(mapId), down = chainOf(target);
    const common = up.find((m) => down.includes(m));
    if (!common) return null;
    let p = project(mapId, xy, common);
    if (!p) return null;
    for (const m of down.slice(0, down.indexOf(common)).reverse()) {   // into the child maps, outermost first
      const def = data.maps[m];
      if (!def || !def.box_on_parent) return null;
      const [[x0, y0], [x1, y1]] = def.box_on_parent;
      p = [((p[0] - x0) / (x1 - x0)) * def.size[0], ((p[1] - y0) / (y1 - y0)) * def.size[1]];
    }
    return p;
  }
  function onMap(xy, id = cur, margin = 0) {  // is a point on the map's picture (with some slack)?
    const [w, h] = data.maps[id].size;
    return xy && xy[0] >= -w * margin && xy[1] >= -h * margin && xy[0] <= w * (1 + margin) && xy[1] <= h * (1 + margin);
  }
  function onCurrent(mapId, xy) {
    return toMap(mapId, xy, cur);              // shown on this map: from a child, a parent or a sibling map
  }
  function placeXY(name) {
    const p = data.places.find((q) => q.name === name && q.map === cur) || data.places.find((q) => q.name === name);
    const xy = p ? onCurrent(p.map, p.at) : null;
    return onMap(xy, cur, 0.02) ? xy : null;   // someone off this map's picture isn't drawn on it
  }

  // ------------------------------------------------------------------ timeline
  function days() {
    const ds = [...new Set(data.legs.map((l) => l.day))].sort((a, b) => a - b);
    if (!ds.includes(data.day)) ds.push(data.day);
    return ds.sort((a, b) => a - b);
  }
  function positionsAt(day, upto = null) {
    // replay the travel log: everyone starts where their first leg began
    const pos = {};
    for (const l of data.legs) for (const w of l.who) if (!(w in pos)) pos[w] = l.from;
    for (const t of data.tokens) if (!(t.name in pos)) pos[t.name] = t.place;
    data.legs.forEach((l, i) => {
      if (l.day <= day && (upto === null || i <= upto)) for (const w of l.who) pos[w] = l.to;
    });
    return pos;
  }

  // ------------------------------------------------------------------ drawing
  function setMap(id) {
    cur = id;
    const def = data.maps[id];
    const [w, h] = def.size;
    const bounds = [[-h, 0], [0, w]];
    if (overlay) lmap.removeLayer(overlay);
    overlay = L.imageOverlay(def.image, bounds).addTo(lmap);
    lmap.setMaxBounds([[-h * 1.15, -w * 0.15], [h * 0.15, w * 1.15]]);
    userMoved = false;
    fit();
    const pick = document.getElementById("map-pick");
    pick.querySelectorAll(".site-btn").forEach((b) => b.remove());
    if (def.site) {        // the open plan gets its own button, with the way back up
      const b = document.createElement("button");
      b.type = "button"; b.className = "site-btn"; b.textContent = def.title; b.dataset.map = id;
      pick.appendChild(b);
    }
    document.querySelectorAll("#map-pick button").forEach((b) => b.classList.toggle("on", b.dataset.map === id));
    draw();
  }

  // frame the view on where things happened: the routes and the people on this map
  // Frame the current map in the space it has: the routes and people on it (or the whole map), clear of the map
  // picker at the top and the timeline at the bottom. It is framed again whenever its box changes size (it opens
  // as a banner and grows), until the player zooms or drags it themselves.
  let userMoved = false;
  function fit() {
    if (!lmap || !cur) return;
    const [w, h] = data.maps[cur].size;
    const whole = L.latLngBounds([[-h, 0], [0, w]]);
    const act = activityBounds(cur);
    const focus = act ? L.latLngBounds(act) : whole;
    const timeline = document.querySelector(".map-time");
    const top = 64, below = (timeline ? timeline.offsetHeight : 0) + 24;
    // zoom to show the tale's part of the map, but at least far enough in that the map fills the box (no empty
    // margins beside a tall map in a wide box), centred on that part in the space between picker and timeline
    const zFocus = lmap.getBoundsZoom(focus, false, L.point(48, top + below));
    const zFill = lmap.getBoundsZoom(whole, true);
    const z = Math.min(lmap.getMaxZoom(), Math.max(zFocus, zFill));
    lmap.setView(focus.getCenter(), z, { animate: false });
    lmap.panBy([0, (below - top) / 2], { animate: false });
    lmap.panInsideBounds(whole, { animate: false });      // centring on the tale must not show past the map's edge
  }
  function activityBounds(id) {
    const pts = [];
    const prev = cur; cur = id;               // project closer maps' points onto this one
    for (const l of data.legs) for (const p of l.path) { const q = onCurrent(l.map, p); if (onMap(q, id)) pts.push(q); }
    for (const t of data.tokens) { const q = onCurrent(t.map, t.at); if (onMap(q, id)) pts.push(q); }
    cur = prev;
    if (!pts.length) return null;
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
    const [mw, mh] = data.maps[id].size;
    const least = data.maps[id].parent ? 0.32 * Math.max(mw, mh) : 700;   // never zoom in closer than this
    const pad = Math.max(60, span * 0.15, least - span / 2);
    return [ll([Math.min(...xs) - pad, Math.min(...ys) - pad]), ll([Math.max(...xs) + pad, Math.max(...ys) + pad])];
  }
  function zoomClass() {
    const c = lmap.getContainer();
    c.classList.toggle("zoomed-out", lmap.getZoom() < 0.25);
  }

  function draw(upto = null) {
    if (!lmap || !data || !cur) return;
    for (const l of [layer, legLayer, tokenLayer]) if (l) lmap.removeLayer(l);
    layer = L.layerGroup().addTo(lmap);
    legLayer = L.layerGroup().addTo(lmap);
    tokenLayer = L.layerGroup().addTo(lmap);
    const ds = days();
    const day = ds[dayIndex ?? ds.length - 1];

    // child maps as outlined areas you can open
    for (const m of Object.values(data.maps)) {
      if (m.parent === cur && m.site) {           // a site plan opens from its place
        const p = data.places.find((q) => q.name === m.anchor && q.map === cur);
        if (p) {
          L.marker(ll(p.at), { icon: L.divIcon({ className: "site-mark", html: "⌂", iconSize: [20, 20], iconAnchor: [-6, 22] }) })
            .bindTooltip(`Plan of ${esc(m.title)}`, { direction: "top", className: "pl-label" })
            .on("click", () => setMap(m.id)).addTo(layer);
        }
        continue;
      }
      if (m.parent === cur && m.box_on_parent) {
        const [[x0, y0], [x1, y1]] = m.box_on_parent;
        L.rectangle([ll([x0, y0]), ll([x1, y1])], { className: "region-box", weight: 2 })
          .bindTooltip(esc(m.title), { permanent: true, direction: "top", className: "region-label" })
          .on("click", () => setMap(m.id)).addTo(layer);
      }
    }
    // places the hero knows of
    for (const p of data.places) {
      if (!p.state) continue;
      const xy = p.map === cur ? p.at : null;
      if (!xy) continue;
      const icon = L.divIcon({ className: `pl pl-${p.state}`, iconSize: [14, 14] });
      const m = L.marker(ll(xy), { icon, keyboard: false }).addTo(layer);
      if (!p.builtin) {   // a small name that shows once zoomed in; the note on hover
        m.bindTooltip(esc(p.name), { permanent: true, direction: "right", offset: [7, 0], className: "pl-name" });
      }
      m.bindPopup(`<b>${esc(p.name)}</b>${p.note ? `<br><i>${esc(p.note)}</i>` : ""}<br><small>${{ heard: "heard of", visited: "visited", current: "you are here" }[p.state]}</small>`, { className: "pl-pop" });
    }
    // routes up to the chosen day
    data.legs.forEach((l, i) => {
      if (l.day > day || (upto !== null && i > upto)) return;
      const pts = l.path.map((xy) => onCurrent(l.map, xy)).filter(Boolean);
      if (pts.length < 2) return;
      const fresh = l.day === day;
      L.polyline(pts.map(ll), { className: `route ${fresh ? "route-fresh" : "route-old"}`, weight: fresh ? 3.5 : 2.5 })
        .bindTooltip(`<b>Day ${l.day}${l.time ? ", " + esc(l.time) : ""}</b><br>${esc(l.who.map((w) => w.split(" ")[0]).join(", "))}: ${esc(l.from)} → ${esc(l.to)}<br><i>${esc(l.mode)}${l.note ? ": " + esc(l.note) : ""}</i>`, { sticky: true, className: "pl-label" })
        .addTo(legLayer);
    });
    // a planned journey: the hexes it enters (on the map it was counted on) and its route on every map of
    // that tree, so it shows on the regions it starts in, ends in or passes through. No land types.
    const planMap = data.plan ? data.plan.map || "eriador" : null;
    const route = data.plan ? data.plan.route.map((p) => onCurrent(planMap, p)) : [];
    if (data.plan && route.every(Boolean)) {
      const g = cur === planMap ? (data.plan.grid ? { width: data.plan.grid[0], height: data.plan.grid[1], x0: data.plan.grid[2], y0: data.plan.grid[3] }
        : planMap === "eriador" ? data.grid : null) : null;
      if (g) for (const [c, r] of (data.plan.cells || []).slice(1)) {
        L.polygon(hexCorners(c, r, g).map(ll), { className: "plan-hex", weight: 1.5 }).addTo(legLayer);
      }
      const tip = `<b>Planned: ${esc(data.plan.from)} → ${esc(data.plan.to)}</b><br>${data.plan.hexes} hex${data.plan.hexes === 1 ? "" : "es"}, about ${data.plan.miles} miles`;
      L.polyline(route.map(ll), { className: "route-plan-halo", weight: 9, interactive: false }).addTo(legLayer);
      L.polyline(route.map(ll), { className: "route route-plan", weight: 4 })
        .bindTooltip(tip, { sticky: true, className: "pl-label" }).addTo(legLayer);
      const end = route[route.length - 1];
      if (onMap(end)) {
        L.circleMarker(ll(end), { radius: 6, className: "plan-end", weight: 2 })
          .bindTooltip(`Planned: ${data.plan.hexes} hex${data.plan.hexes === 1 ? "" : "es"} · ${data.plan.miles} miles`,
            { permanent: true, direction: "right", offset: [8, 0], className: "plan-label" })
          .addTo(legLayer);
      }
    }
    drawOverlays();
    drawTokens(positionsAt(day, upto));
    const lbl = document.getElementById("map-day");
    if (lbl) {
      const legsToday = data.legs.filter((l) => l.day === day);
      lbl.textContent = `Day ${day}${legsToday.length ? " · " + (legsToday[legsToday.length - 1].time || "") : day === data.day ? " · now" : ""}`;
    }
  }

  function drawTokens(pos) {
    tokenLayer.clearLayers();
    const groups = {};
    for (const [who, place] of Object.entries(pos)) {
      const xy = placeXY(place);
      if (!xy) continue;
      const key = place;
      (groups[key] = groups[key] || { xy, members: [] }).members.push(who);
    }
    for (const g of Object.values(groups)) {
      g.members.sort((a, b) => kindRank(a) - kindRank(b));
      g.members.forEach((who, k) => {
        const t = data.tokens.find((x) => x.name === who) || { name: who, kind: "npc" };
        const n = g.members.length, r = n > 1 ? 16 + n * 2 : 0;
        const a = (k / n) * 2 * Math.PI - Math.PI / 2;
        const off = [Math.round(Math.cos(a) * r), Math.round(Math.sin(a) * r)];
        const html = t.image ? `<img src="${esc(t.image)}" alt="">` : `<span>${esc(who[0])}</span>`;
        const icon = L.divIcon({ className: `tok tok-${t.kind}`, html, iconSize: [34, 34], iconAnchor: [17 - off[0], 17 - off[1]] });
        L.marker(ll(g.xy), { icon, zIndexOffset: t.kind === "hero" ? 1000 : 500 })
          .bindTooltip(`${esc(who)}<br><i>${esc(Object.keys(groups).find((p) => groups[p] === g))}</i>`, { direction: "top", offset: [off[0], -18 + off[1]], className: "pl-label" })
          .addTo(tokenLayer);
      });
    }
  }
  function hexCorners(c, r, g) {
    const R = g.width / Math.sqrt(3), cx = g.x0 + c * g.width + (r & 1 ? g.width / 2 : 0), cy = g.y0 + r * g.height;
    return [0, 1, 2, 3, 4, 5].map((k) => {
      const a = (Math.PI / 180) * (90 + 60 * k);
      return [cx + R * Math.cos(a), cy + (g.height / 1.5) * Math.sin(a)];
    });
  }
  // the hex grid of a map: Eriador's own (measured on the Loremaster map), or 20-mile hexes on a land map
  function gridFor(id) {
    const def = data.maps[id];
    if (id === "eriador") return data.grid || null;
    if (!def || def.scale !== "land" || !def.miles_per_px) return null;
    const width = 20 / def.miles_per_px;             // flat side to flat side: 20 miles
    return { width, height: width * Math.sqrt(3) / 2, x0: 0, y0: 0 };
  }
  function drawOverlays() {
    if (hexLayer) { lmap.removeLayer(hexLayer); hexLayer = null; }
    if (fogLayer) { lmap.removeLayer(fogLayer); fogLayer = null; }
    const def = data.maps[cur];
    if (showFog) {
      fogLayer = L.imageOverlay(`/api/fog/${cur}.png?t=${Date.now()}`, [[-def.size[1], 0], [0, def.size[0]]], { className: "fog", interactive: false }).addTo(lmap);
    }
    const grid = gridFor(cur);
    if (showHex && grid) {
      const g = grid, lines = [];
      const rows = Math.ceil(def.size[1] / g.height) + 2, cols = Math.ceil(def.size[0] / g.width) + 2;
      const r0 = Math.floor(-g.y0 / g.height) - 1, c0 = Math.floor(-g.x0 / g.width) - 1;
      for (let r = r0; r < r0 + rows; r++) for (let c = c0; c < c0 + cols; c++) {
        const cx = g.x0 + c * g.width + (r & 1 ? g.width / 2 : 0), cy = g.y0 + r * g.height;
        if (cx < 0 || cy < 0 || cx > def.size[0] || cy > def.size[1]) continue;   // only hexes on the map
        const pts = hexCorners(c, r, g);
        lines.push([...pts, pts[0]].map(ll));
      }
      hexLayer = L.polyline(lines, { color: "#3a2816", opacity: 0.32, weight: 1, interactive: false, renderer: L.canvas() }).addTo(lmap);
    }
    document.getElementById("map-hex").classList.toggle("on", showHex);
    document.getElementById("map-fog").classList.toggle("on", showFog);
    document.getElementById("map-hex").style.display = grid ? "" : "none";
  }
  const kindRank = (who) => ({ hero: 0, ally: 1, npc: 2 }[(data.tokens.find((t) => t.name === who) || {}).kind] ?? 3);

  // ------------------------------------------------------------------ play the timeline
  function play() {
    if (playing) { stop(); return; }
    playing = true;
    document.getElementById("map-play").textContent = "❚❚";
    const ds = days();
    const startDay = ds[Math.min(dayIndex ?? 0, ds.length - 1)] === ds[ds.length - 1] ? ds[0] : ds[dayIndex ?? 0];
    let i = data.legs.findIndex((l) => l.day >= startDay);
    if (i < 0) i = 0;
    const step = () => {
      if (!playing || i >= data.legs.length) { stop(); return; }
      const l = data.legs[i];
      const di = days().indexOf(l.day);
      dayIndex = di;
      document.getElementById("map-slider").value = di;
      draw(i);
      i += 1;
      playTimer = setTimeout(step, 1100);
    };
    step();
  }
  function stop() {
    playing = false;
    clearTimeout(playTimer);
    const b = document.getElementById("map-play");
    if (b) b.textContent = "▶";
    draw();
  }

  // ------------------------------------------------------------------ public
  async function refresh() {
    try { data = await (await fetch("/api/geo")).json(); } catch { return; }
    if (!lmap) return;
    const slider = document.getElementById("map-slider");
    const ds = days();
    slider.max = ds.length - 1;
    if (dayIndex === null || dayIndex >= ds.length) dayIndex = ds.length - 1;
    slider.value = dayIndex;
    const plan = data.plan ? `${data.plan.from}|${data.plan.to}|${data.plan.map || "eriador"}` : "";
    const newPlan = plan && plan !== lastPlan;
    lastPlan = plan;
    if (cur && !data.maps[cur]) cur = null;          // the map shown before is no longer offered
    if (!cur) {
      // open on: a journey just planned, else where the hero is, else where anyone is, else the tale's first map
      const who = data.tokens.find((t) => t.kind === "hero") || data.tokens[0];
      const roots = Object.keys(data.maps).filter((m) => !data.maps[m].parent);
      setMap(newPlan && data.maps[data.plan.map || "eriador"] ? (data.plan.map || "eriador")
        : who && data.maps[who.map] ? who.map : roots[0] || Object.keys(data.maps)[0]);
    } else if (newPlan && (data.plan.map || "eriador") !== cur && data.maps[data.plan.map || "eriador"]) {
      setMap(data.plan.map || "eriador");     // a journey was just planned: show the map it's drawn on
    } else draw();
  }
  function open() {
    if (!lmap) {
      lmap = L.map("leaflet", { crs: L.CRS.Simple, minZoom: -3, maxZoom: 3, zoomSnap: 0.25, attributionControl: false,
                                zoomControl: false });
      L.control.zoom({ position: "bottomright" }).addTo(lmap);   // the top-left corner holds the map picker
      lmap.on("zoomend", zoomClass);
      // The map's box changes size often: it grows from the banner when the Map view opens (the stage animates),
      // and shrinks or grows as a roll tray, the Paths, a fight or a journey come and go. Leaflet measures its box
      // only when told, and otherwise keeps drawing the routes, hexes and markers for the old size, cut off at
      // its old edge. So tell it whenever the box changes.
      let sizing = 0;
      new ResizeObserver(() => {
        cancelAnimationFrame(sizing);
        sizing = requestAnimationFrame(() => { lmap.invalidateSize({ pan: false }); if (!userMoved) fit(); });
      }).observe(document.getElementById("leaflet"));
      // the player's own zooming and dragging (not the framing above) keeps their view
      const box = document.getElementById("leaflet");
      for (const ev of ["wheel", "mousedown", "touchstart", "keydown", "dblclick"]) {
        box.addEventListener(ev, () => { userMoved = true; }, { passive: true });
      }
      const pick = document.getElementById("map-pick");
      pick.innerHTML = "";
      refresh().then(() => {
        for (const m of Object.values(data.maps).filter((m) => !m.site).sort((a, b) => (a.parent ? 1 : 0) - (b.parent ? 1 : 0))) {
          const b = document.createElement("button");
          b.type = "button"; b.textContent = m.title; b.dataset.map = m.id;
          b.onclick = () => setMap(m.id);
          pick.appendChild(b);
        }
        document.querySelectorAll("#map-pick button").forEach((b) => b.classList.toggle("on", b.dataset.map === cur));
      });
      document.getElementById("map-slider").oninput = (e) => { stop(); dayIndex = +e.target.value; draw(); };
      document.getElementById("map-play").onclick = play;
      document.getElementById("map-hex").onclick = () => { showHex = !showHex; drawOverlays(); };
      document.getElementById("map-fog").onclick = () => { showFog = !showFog; drawOverlays(); };
      document.getElementById("map-now").onclick = () => { stop(); dayIndex = days().length - 1; document.getElementById("map-slider").value = dayIndex; draw(); };
    } else {
      setTimeout(() => lmap.invalidateSize(), 50);
      refresh();
    }
  }
  return { open, refresh };
})();
