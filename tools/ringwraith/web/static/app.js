"use strict";
// Ringwraith Table: browser side. Talks to the server over one WebSocket.

const $ = (sel) => document.querySelector(sel);
const logEl = $("#log"), dockEl = $("#dock"), input = $("#input");
let ws = null;
let live = [];            // narration blocks still streaming (oldest first)
let replaying = false;
let nextOpening = true;   // the next narration gets a drop cap (after a scene change)
let sceneJob = null;      // image job id the stage is waiting for
let stageFront = "a";
const trays = new Map();  // roll id -> tray element
const requests = new Map();  // roll id -> the request as the player saw it

// ------------------------------------------------------------------ helpers
function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// A question to the player in the table's own style (instead of the browser's confirm()).
// ask({title, text, ok, cancel, danger}) resolves true for ok, false for cancel, Escape or a click outside.
// With danger, the safe answer has the focus, so Enter doesn't do the risky thing.
function ask({ title = "", text = "", ok = "Yes", cancel = "Not yet", danger = false } = {}) {
  return new Promise((resolve) => {
    const d = el("dialog", "rw-dialog");
    d.innerHTML = `<form method="dialog">
        ${title ? `<h2>${esc(title)}</h2><div class="rw-rule">❦</div>` : ""}
        <p>${esc(text)}</p>
        <div class="rw-actions">
          <button value="cancel" class="ghost"${danger ? " autofocus" : ""}>${esc(cancel)}</button>
          <button value="ok" class="${danger ? "danger" : ""}"${danger ? "" : " autofocus"}>${esc(ok)}</button>
        </div>
      </form>`;
    d.addEventListener("click", (ev) => { if (ev.target === d) d.close("cancel"); });   // the backdrop
    d.addEventListener("close", () => { resolve(d.returnValue === "ok"); d.remove(); });
    document.body.appendChild(d);
    d.showModal();
  });
}
const pct = (p) => `${Math.round(p * 100)}%`;
if (!window.marked || !window.DOMPurify || !window.L) {      // say so, rather than leave a blank page
  document.body.insertAdjacentHTML("afterbegin", `<div class="boot-error">The table's scripts didn't load
    (the files in <code>web/static/vendor/</code>). Restart <code>ringwraith serve</code> and reload the page.</div>`);
  throw new Error("Ringwraith Table: a library in vendor/ is missing");
}
// Links in the story open in a new tab: following one in this tab would leave the table.
DOMPurify.addHook("afterSanitizeAttributes", (n) => {
  if (n.tagName === "A" && n.getAttribute("href")) { n.setAttribute("target", "_blank"); n.setAttribute("rel", "noopener"); }
});
marked.setOptions({ breaks: true });   // a single line break is a line break (OOC notes are written line by line)
const ICONS = {
  "{success}": '<span class="glyph succ" title="success icon">✦</span>',
  "{eye}": '<span class="glyph eye" title="Eye of Sauron">◉</span>',
  "{gandalf}": '<span class="glyph rune" title="Gandalf rune">ᚷ</span>',
};
const iconize = (escaped) => escaped.replace(/\{(success|eye|gandalf)\}/g, (m) => ICONS[m]);
function md(text) {
  const withIcons = String(text || "").replace(/\{(success|eye|gandalf)\}/g, (m) => ICONS[m]);
  const html = DOMPurify.sanitize(marked.parse(withIcons), { FORBID_TAGS: ["style", "img"] });
  const box = el("div", null, html);
  for (const bq of box.querySelectorAll("blockquote")) {
    const first = bq.querySelector("p") || bq;
    if (/^\s*OOC:\s*/i.test(first.textContent)) {
      bq.classList.add("ooc");
      first.innerHTML = first.innerHTML.replace(/^\s*OOC:\s*/i, "");
    } else if (/^\s*CUTAWAY:\s*/i.test(first.textContent)) {   // a scene elsewhere, which the hero doesn't see
      bq.classList.add("cutaway");
      first.innerHTML = first.innerHTML.replace(/^\s*CUTAWAY:\s*/i, "");
    }
  }
  return box.innerHTML;
}
// ------------------------------------------------------------------ tucking the dock while reading back
// Reading mode: when the player scrolls up to read back, the stage shrinks to a banner and the
// choices (Paths, a waiting roll) slide away, leaving a small bar. Back at the end, all returns.
let tucked = false, lastTop = 0, ignoreScrollUntil = 0;
function dockLabel() {
  if (trays.size) {
    const t = [...trays.values()].pop();
    return "Roll waiting · " + (t.querySelector(".title")?.textContent || "");
  }
  const n = document.querySelectorAll("#paths .path:not(.else)").length;
  return n ? `${n} Paths` : "Show choices";
}
function setTucked(on) {
  const h = $("#dock-handle");
  const hasDock = dockEl.children.length > 0;
  h.textContent = dockLabel();
  h.classList.toggle("on", on && hasDock);
  if (on === tucked) return;
  tucked = on;
  ignoreScrollUntil = performance.now() + 500;     // our own layout change moves the scroll; don't react to it
  dockEl.classList.toggle("tucked", on);
  const stage = $("#stage");
  stage.classList.toggle("banner", on && !stage.classList.contains("mapmode"));
  if (on) { stage.classList.remove("full"); stage.style.height = ""; }
  if (!on) setTimeout(() => { logEl.scrollTop = logEl.scrollHeight; }, 420);
}
function atBottom(slack = 8) { return logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight <= slack; }
logEl.addEventListener("scroll", () => {
  const delta = logEl.scrollTop - lastTop;
  lastTop = logEl.scrollTop;
  if (performance.now() < ignoreScrollUntil) return;
  if (delta < 0 && !atBottom(60)) setTucked(true);       // the player scrolls up to read
  else if (delta > 0 && atBottom()) setTucked(false);    // back at the end
});
logEl.addEventListener("wheel", (ev) => { if (ev.deltaY > 0 && tucked && atBottom()) setTucked(false); });
$("#dock-handle").onclick = () => setTucked(false);

function scrollDown(force) {
  const near = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 240;
  if (force || near || replaying) logEl.scrollTop = logEl.scrollHeight;
}
function add(node) { logEl.appendChild(node); scrollDown(); return node; }
const online = () => !!ws && ws.readyState === 1;
// Returns whether it went: while the table is reconnecting nothing can be sent, and callers keep what was typed.
function send(obj) {
  if (!online()) { flashConn(); return false; }
  ws.send(JSON.stringify(obj));
  return true;
}

// Dice faces: our own simple glyphs for the Feat die runes.
const EYE_SVG = '<svg viewBox="0 0 24 24" aria-label="Eye"><path d="M1.5 12 Q12 1.5 22.5 12 Q12 22.5 1.5 12Z" fill="#8e1f1a" stroke="#e0662a" stroke-width=".8"/><ellipse cx="12" cy="12" rx="1.8" ry="5.2" fill="#f2c14e"/></svg>';
const RUNE_SVG = '<svg viewBox="0 0 24 24" aria-label="Gandalf rune"><circle cx="12" cy="12" r="10" fill="none" stroke="#d8bd7a" stroke-width="1.2"/><path d="M6 6 L18 18 M18 6 L6 18 M12 3.5 L12 8" stroke="#f3e6c4" stroke-width="2.2" stroke-linecap="round"/></svg>';
function featDie(face, dropped) {
  const d = el("span", "die feat" + (dropped ? " dropped" : ""));
  d.innerHTML = face === "eye" ? EYE_SVG : face === "gandalf" ? RUNE_SVG : esc(face);
  d.title = face === "eye" ? "Eye of Sauron" : face === "gandalf" ? "Gandalf rune" : `Feat ${face}`;
  return d;
}
function successDie(v, weary, i) {
  const d = el("span", "die" + (v === 6 ? " icon" : "") + (weary && v <= 3 ? " low" : ""), String(v));
  d.style.animationDelay = `${0.08 * (i + 1)}s`;
  return d;
}

// ------------------------------------------------------------------ the stage
function setStage(url, title, animate = true) {
  if (title !== undefined) $("#stage-title").textContent = title || "";
  if (!url) return;
  const front = $(`#stage-img-${stageFront}`);
  if (front.getAttribute("src") === url) return;
  const backKey = stageFront === "a" ? "b" : "a";
  const back = $(`#stage-img-${backKey}`);
  back.style.transition = animate ? "" : "none";
  front.style.transition = animate ? "" : "none";
  back.onload = () => {
    back.classList.add("show");
    front.classList.remove("show");
    stageFront = backKey;
    fitFull();                                  // a new painting may have another shape
  };
  back.src = url;
}
function painting(on) { $("#stage-painting").classList.toggle("on", !!on); }

// ------------------------------------------------------------------ narration
let pathsThisTurn = false;   // text streamed after the Paths cards is a recap: don't show it while it streams
let untoldSummary = null;    // a mechanics-only reply; the story told afterwards goes above it
function narrStart(retell) {
  const cls = "narr live" + (pathsThisTurn ? " muted" : nextOpening ? " opening" : "");
  let n;
  if (retell && untoldSummary && untoldSummary.isConnected) {
    n = el("div", cls);
    untoldSummary.before(n);
  } else n = add(el("div", cls));
  nextOpening = false;
  n._raw = "";
  live.push(n);
  return n;
}
let renderPending = false;
function narrDelta(text) {
  const n = live.length ? live[live.length - 1] : narrStart();
  n._raw += text;
  if (!renderPending) {
    renderPending = true;
    requestAnimationFrame(() => {
      renderPending = false;
      for (const b of live) b.innerHTML = md(b._raw);
      scrollDown();
    });
  }
}
function narrFinal(text, aside, recap, summary) {
  let n = live.shift();
  if (recap) {   // written after the Paths: a recap the player has already seen; keep it folded away
    const d = el("details", "recap", `<summary>Loremaster's recap</summary><div class="narr">${md(text)}</div>`);
    if (n) n.replaceWith(d); else add(d);
    scrollDown();
    return;
  }
  if (aside) {   // the Loremaster's own bookkeeping: a faint working note, not story
    const a = el("div", "aside", iconize(esc(text.trim())));
    if (n) { n.replaceWith(a); if (n.classList.contains("opening")) nextOpening = true; } else add(a);
    scrollDown();
    return;
  }
  if (!n) { n = add(el("div", "narr" + (nextOpening ? " opening" : ""))); nextOpening = false; }
  n.classList.remove("live");
  n.innerHTML = md(text);
  if (summary) untoldSummary = n;
  scrollDown();
}
function endLive() {
  for (const n of live) { n.classList.remove("live"); if (!n._raw.trim()) n.remove(); }
  live = [];
}

// ------------------------------------------------------------------ rolls
// What the player saw in the tray when they rolled: stakes, TN, modifiers, odds and their choice.
function rollDetail(req, e) {
  const d = el("div", "roll-detail");
  const mods = [req.mode !== "normal" ? req.mode : "", ...(req.flags || []),
    req.bonus ? `+${req.bonus}d` : "", req.penalty ? `−${req.penalty}d` : ""].filter(Boolean).join(", ");
  const chosen = e.hope ? "hope" : "plain";
  const row = (key, name) => {
    const o = req.odds?.[key];
    if (!o) return "";
    return `<tr class="${key === chosen ? "chosen" : ""}"><td>${name}</td><td>${o.dice}d</td><td>${pct(o.success)}</td>
      <td>${pct(o.great)}</td><td>${pct(o.extraordinary)}</td></tr>`;
  };
  d.innerHTML = `
    ${req.stakes ? `<div class="stakes">${iconize(esc(req.stakes))}</div>` : ""}
    <div class="meta">TN ${req.tn}${mods ? " · " + esc(mods) : ""}${req.hope_now != null ? ` · Hope ${req.hope_now}${e.hope ? ` → ${req.hope_now - 1}` : ""}` : ""}
      · ${e.manual ? "physical dice" : "rolled by the table"}</div>
    <table><tr><th></th><th>dice</th><th>success</th><th>great</th><th>extraord.</th></tr>
      ${row("plain", "Without Hope")}${row("hope", req.flags?.includes("inspired") ? "Hope (Inspired)" : "With Hope")}${row("inspired", "Hope + Inspired")}
    </table>
    ${(e.notes || []).length ? `<div class="meta">${iconize(esc(e.notes.join("; ")))}</div>` : ""}`;
  return d;
}

function rollCard(e, req) {
  const ok = e.outcome === "success";
  const c = el("div", `roll ${ok ? "success" : "failure"}${e.adversary ? " adversary" : ""}`);
  const extra = [e.hope ? "Hope spent" : "", e.manual ? "physical dice" : ""].filter(Boolean).join(" · ");
  c.appendChild(el("div", "who", iconize(`${esc(e.who)} — ${esc(e.what)} · TN ${e.tn}${extra ? " · " + extra : ""}`)));
  const dice = el("div", "dice");
  let keptShown = false;
  for (const f of e.feat) {
    const isKept = !keptShown && f === e.kept;
    if (isKept) keptShown = true;
    dice.appendChild(featDie(f, e.feat.length > 1 && !isKept));
  }
  const weary = (e.notes || []).some((n) => /Weary/.test(n));
  e.success.forEach((v, i) => dice.appendChild(successDie(v, weary, i)));
  c.appendChild(dice);
  c.appendChild(el("span", "total", `total ${e.total}`));
  const deg = ok && e.degree && e.degree !== "success" ? ` · ${e.degree}` : "";
  c.appendChild(el("span", "verdict", (ok ? "Success" : "Failure") + deg));
  if (req) {
    c.classList.add("openable");
    c.title = "Show what you were offered when you rolled";
    const det = rollDetail(req, e);
    det.addEventListener("click", (ev) => ev.stopPropagation());   // let the player select text in it
    c.appendChild(det);
    c.addEventListener("click", () => c.classList.toggle("open"));
  } else if (e.notes && e.notes.length) c.title = e.notes.join("; ");
  return c;
}

function rollTray(e) {
  const t = el("div", "tray");
  const mods = [e.mode !== "normal" ? e.mode : "", ...(e.flags || []),
    e.bonus ? `+${e.bonus}d` : "", e.penalty ? `−${e.penalty}d` : ""].filter(Boolean).join(", ");
  t.innerHTML = `
    <div class="tray-head"><span class="title">${esc(e.who)} — ${esc(e.what)}</span>
      <span class="tn">TN ${e.tn}</span>${mods ? `<span class="mods">${esc(mods)}</span>` : ""}</div>
    <div class="stakes">${iconize(esc(e.stakes))}</div>`;
  const choices = el("div", "choices");
  const choice = (name, o, btnLabel, action, enabled, sub) => {
    const c = el("div", "choice" + (action ? "" : " info"));
    c.innerHTML = `<span class="name">${name}</span><span class="pct">${pct(o.success)}</span>
      <div class="bar"><span style="width:${pct(o.success)}"></span></div>
      <span class="sub">${o.dice}d · great ${pct(o.great)} · extraordinary ${pct(o.extraordinary)}${sub ? "<br>" + sub : ""}</span>`;
    if (action) {
      const b = el("button", null, btnLabel);
      b.disabled = !enabled;
      b.onclick = () => answerRoll(e.id, action);
      c.appendChild(b);
    }
    choices.appendChild(c);
  };
  choice("Without Hope", e.odds.plain, "Roll", "roll", true);
  const hopeSub = e.hope_now != null ? `Hope ${e.hope_now} → ${Math.max(0, e.hope_now - 1)}` : "";
  choice(e.flags.includes("inspired") ? "Spend Hope (Inspired)" : "Spend Hope", e.odds.hope,
    "Spend Hope & roll", "hope", e.hope_allowed, e.hope_allowed ? hopeSub : "Hope can't be spent");
  if (e.odds.inspired) choice("Hope + Inspired", e.odds.inspired, null, null, false,
    "invoke a fitting Distinctive Feature: tell Ringwraith below");
  t.appendChild(choices);

  // physical dice
  const man = el("div", "manual" + (e.manual ? " on" : ""));
  const featCount = e.mode === "normal" ? 1 : 2;
  const featOpts = ["", 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, "eye", "gandalf"]
    .map((v) => `<option value="${v}">${v === "eye" ? "Eye" : v === "gandalf" ? "Rune" : v}</option>`).join("");
  const featRow = el("div", "manual-row", `<span>Feat die${featCount > 1 ? ` (${e.mode}, both)` : ""}:</span>` +
    Array.from({ length: featCount }, () => `<select class="feat">${featOpts}</select>`).join(""));
  const succRow = el("div", "manual-row");
  const hopeBox = el("label", "manual-row", `<input type="checkbox" class="usehope" ${e.hope_allowed ? "" : "disabled"} style="width:auto"> Spend Hope (${e.dice.hope} Success dice)`);
  const renderSucc = () => {
    const n = hopeBox.querySelector("input").checked ? e.dice.hope : e.dice.plain;
    succRow.innerHTML = `<span>Success dice (${n}):</span>` +
      Array.from({ length: n }, () => '<input class="succ" type="number" min="1" max="6">').join("");
  };
  hopeBox.querySelector("input").onchange = renderSucc;
  renderSucc();
  const go = el("button", null, "Use these dice");
  go.onclick = () => {
    const feat = [...man.querySelectorAll(".feat")].map((s) => s.value);
    const success = [...man.querySelectorAll(".succ")].map((i) => parseInt(i.value, 10));
    if (feat.some((f) => !f) || success.some((v) => !(v >= 1 && v <= 6))) {
      go.textContent = "Fill in every die"; setTimeout(() => (go.textContent = "Use these dice"), 1500); return;
    }
    answerRoll(e.id, hopeBox.querySelector("input").checked ? "hope" : "roll", { feat, success });
  };
  man.append(featRow, hopeBox, succRow, go);
  t.appendChild(man);

  const foot = el("div", "tray-foot");
  foot.appendChild(el("span", "hint", "Or type below to answer Ringwraith instead of rolling."));
  const manualBtn = el("button", "linkish", e.manual ? "Let the script roll" : "I'll roll physical dice");
  manualBtn.type = "button";
  manualBtn.onclick = () => {
    man.classList.toggle("on");
    manualBtn.textContent = man.classList.contains("on") ? "Let the script roll" : "I'll roll physical dice";
  };
  const cancel = el("button", "linkish", "Cancel roll");
  cancel.type = "button";
  cancel.onclick = () => answerRoll(e.id, "cancel");
  foot.append(manualBtn, cancel);
  t.appendChild(foot);
  return t;
}
function answerRoll(id, action, extra = {}) {
  const t = trays.get(id);
  if (t) t.querySelectorAll("button").forEach((b) => (b.disabled = true));
  send({ t: "answer", id, data: { action, ...extra } });
}
function closeTray(id) {
  const t = trays.get(id);
  if (t) { t.remove(); trays.delete(id); }
  setTucked(tucked);
  updateActivity("Ringwraith is writing…");
}

// ------------------------------------------------------------------ paths
function showPaths(paths) {
  clearPaths();
  const box = el("div", "paths");
  box.id = "paths";
  for (const p of paths) {
    const b = el("button", "path", iconize(esc(p)));
    b.type = "button";
    b.onclick = () => say(p);
    box.appendChild(b);
  }
  const other = el("button", "path else", "…or something else entirely");
  other.type = "button";
  other.onclick = () => input.focus();
  box.appendChild(other);
  dockEl.appendChild(box);
  document.body.classList.add("choosing");      // the stage steps back so the story stays in view
  if (!replaying) setTucked(false);
}
function clearPaths() {
  const p = $("#paths");
  if (p) p.remove();
  document.body.classList.remove("choosing");
  setTucked(tucked);
}

// ------------------------------------------------------------------ side panels
function meter(cls, cur, max, extraMark) {
  const w = max ? Math.max(0, Math.min(100, (cur / max) * 100)) : 0;
  const mark = extraMark != null && max ? `<i class="mark" style="left:${Math.min(100, (extraMark / max) * 100)}%"></i>` : "";
  return `<div class="meter ${cls}"><span style="width:${w}%"></span>${mark}</div>`;
}
// Folding sections in the side panels remember (per browser) whether they are open, across updates and reloads.
function isOpen(id, dflt = true) {
  try { const v = localStorage.getItem("rw.open." + id); return v == null ? dflt : v === "1"; } catch { return dflt; }
}
const openAttr = (id, dflt) => (isOpen(id, dflt) ? " open" : "");
document.addEventListener("toggle", (ev) => {
  const id = ev.target.id;
  if (id && ev.target.closest("#side, #drawer")) { try { localStorage.setItem("rw.open." + id, ev.target.open ? "1" : "0"); } catch {} }
}, true);
const inline = (t) => DOMPurify.sanitize(marked.parseInline(String(t || "").replace(/\{(success|eye|gandalf)\}/g, (m) => ICONS[m])));
// − / + buttons that change the hero sheet (the server writes the note and tells Ringwraith)
const stepper = (key) => `<span class="step"><button type="button" data-adj="${key}" data-d="-1" title="One less">−</button><button type="button" data-adj="${key}" data-d="1" title="One more">+</button></span>`;
function clockSummary(deadlines, day, counters) {
  if (!deadlines.length) return counters ? `${counters} counter${counters > 1 ? "s" : ""}` : "";
  const next = deadlines[0], left = day != null ? next.due - day : null;
  const when = left == null ? `day ${next.due}` : left > 1 ? `in ${left} days` : left === 1 ? "tomorrow"
    : left === 0 ? "today" : "overdue";
  return `${deadlines.length} · next ${when}`;
}
function renderSheet(s) {
  if (!s) return;
  const camp = s.campaign || {};
  $("#campaign").textContent = [camp.name, s.state?.date, s.state?.day ? `day ${s.state.day}` : "", s.state?.location]
    .filter(Boolean).join(" · ");
  if (s.slug) $("#lnk-vault").href = `obsidian://open?vault=${encodeURIComponent(s.slug)}`;
  const h = s.hero;
  const hp = $("#panel-hero");
  if (h) {
    const c = h.conditions || {};
    const hopeCur = h.hope?.current ?? 0, hopeMax = h.hope?.max ?? 0;
    const shadow = (h.shadow?.points ?? 0) + (h.shadow?.scars ?? 0);
    const miserable = c.miserable || (shadow >= hopeCur && hopeMax > 0);
    const load = (h.load ?? 0) + (h.fatigue ?? 0);
    const weary = c.weary || (h.endurance && h.endurance.current <= load);
    const tnBase = s.tn_base || 20;
    const attrs = h.attributes || {};
    const fav = new Set(h.favoured_skills || []);
    const skills = Object.values(h.skills || {}).flatMap((g) => Object.entries(g));
    hp.innerHTML = `
      <h2>The Hero <small>Parry ${esc(h.parry ?? "–")}</small></h2>
      <div class="hero-name">${esc(h.name)}</div>
      <div class="hero-sub">${esc(h.culture || "")}</div>
      <div class="stat"><div class="row"><b>ENDURANCE</b>${stepper("endurance")}<span>${esc(h.endurance?.current ?? "–")} / ${esc(h.endurance?.max ?? "–")}</span></div>
        ${meter("endurance", h.endurance?.current, h.endurance?.max, load)}</div>
      <div class="stat"><div class="row"><b>HOPE</b>${stepper("hope")}<span>${esc(hopeCur)} / ${esc(hopeMax)}</span></div>${meter("hope", hopeCur, hopeMax)}</div>
      <div class="stat"><div class="row"><b>SHADOW</b>${stepper("shadow")}<span>${esc(h.shadow?.points ?? 0)}${h.shadow?.scars ? ` + ${esc(h.shadow.scars)} scar${h.shadow.scars > 1 ? "s" : ""}` : ""}</span></div>
        ${meter("shadow", shadow, hopeMax)}</div>
      ${h.fellowship ? `<div class="stat"><div class="row"><b>FELLOWSHIP</b>${stepper("fellowship")}<span>${esc(h.fellowship.current ?? 0)} / ${esc(h.fellowship.rating ?? 0)}</span></div>
        ${meter("fellowship", h.fellowship.current ?? 0, h.fellowship.rating ?? 0)}</div>` : ""}
      <div class="badges">
        ${weary ? '<span class="badge bad">Weary</span>' : ""}
        ${miserable ? '<span class="badge bad">Miserable</span>' : ""}
        <button type="button" class="badge toggle ${c.wounded ? "bad" : "off"}" data-adj="wounded" title="${c.wounded ? "Click if the hero is no longer Wounded" : "Click to mark the hero Wounded"}">Wounded</button>
        ${!weary && !miserable && !c.wounded ? '<span class="badge ok">Hale</span>' : ""}
        <span class="badge">Load ${esc(h.load ?? 0)}</span>
        <span class="badge fat">Fatigue ${esc(h.fatigue ?? 0)}${stepper("fatigue")}</span>
      </div>
      <div class="attrs">${["strength", "heart", "wits"].map((a) =>
        `<div class="attr"><b>${a.toUpperCase()}</b><span>${esc(attrs[a] ?? "–")}</span> <i>TN ${attrs[a] != null ? tnBase - attrs[a] : "–"}</i></div>`).join("")}</div>
      ${traitsRow(h.traits)}
      ${traitsFold(h.traits)}
      <details><summary>Skills & proficiencies</summary>
        <div class="skills">${skills.map(([k, v]) => `<div class="${fav.has(k) ? "fav" : ""}"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join("")}</div>
        <div class="skills" style="margin-top:6px">${Object.entries(h.proficiencies || {}).map(([k, v]) => `<div><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join("")}</div>

      </details>`;
  } else hp.innerHTML = "";

  const st = s.state || {};
  const day = Number(st.day) || null;
  const deadlines = [...(st.deadlines || [])].sort((a, b) => (a.due || 0) - (b.due || 0));
  const dlRows = deadlines.map((d) => {
    const left = day != null ? d.due - day : null;
    const when = left == null ? `day ${d.due}` : left > 1 ? `${left} days` : left === 1 ? "tomorrow"
      : left === 0 ? "today" : `${-left} day${left === -1 ? "" : "s"} late`;
    const cls = left != null && left <= 2 ? " urgent" : "";
    return `<div class="clock${cls}"><span>${esc(d.name)}${d.note ? `<i>${esc(d.note)}</i>` : ""}</span><b>${when}</b></div>`;
  }).join("");
  const ctRows = (st.counters || []).map((c) =>
    `<div class="clock count"><span>${esc(c.name)}</span><b>day ${day != null ? day - c.since + 1 : "?"}</b></div>`).join("");
  $("#panel-world").innerHTML = (st.date || st.location || day) ? `
    <h2>The World <small>${day ? `Day ${day}` : esc(st.phase || "")}${st.time ? " · " + esc(st.time) : ""}</small></h2>
    <div class="kv"><span>Date</span><span>${esc(st.date || "–")}</span></div>
    <div class="kv"><span>Place</span><span>${esc(st.location || "–")}</span></div>
    ${dlRows || ctRows ? `<details class="clocks" id="clocks"${openAttr("clocks", true)}>
      <summary><span>Deadlines</span><em>${esc(clockSummary(deadlines, day, (st.counters || []).length))}</em></summary>
      ${dlRows}${ctRows}</details>` : ""}
    <div class="stat"><div class="row"><b>EYE AWARENESS</b><span>${esc(st.eye_awareness ?? 0)} / ${esc(st.hunt_threshold ?? "–")}</span></div>
      ${meter("eye", st.eye_awareness ?? 0, st.hunt_threshold || 18)}</div>` : "";

  const b = s.band;
  const bp = $("#panel-band");
  if (b || (s.allies || []).length) {
    const d = b?.dispositions || {};
    bp.innerHTML = `
      <h2>The Band ${b ? `<small>Readiness ${esc(b.readiness)} · TN ${(s.tn_base || 20) - (b.readiness || 0)}</small>` : ""}</h2>
      ${b ? `<div class="disps">${["expertise", "manoeuvre", "rally", "vigilance", "war"].map((k) =>
        `<div><b>${k.toUpperCase()}</b>${esc(d[k] ?? "–")}</div>`).join("")}</div>` : ""}
      ${(s.allies || []).map((a) => {
        const img = a.image ? String(a.image).replace(/^\[\[|\]\]$/g, "").replace(/^90 Assets\//, "/assets/") : "";
        const bad = [a.injury && a.injury !== "none" ? a.injury : "", a.fatigue && a.fatigue !== "none" ? a.fatigue : "",
          a.status && a.status !== "active" ? a.status : ""].filter(Boolean);
        return `<div class="ally">${img ? `<img src="${esc(img)}" alt="">` : '<span class="ph"></span>'}
          <div><div class="nm">${esc(a.name)}${a.hardened ? " ★" : ""}</div>
          <div class="gift">${giftChip(a.gift, a.gift_wasted, "Gift")}${a.second_gift ? giftChip(a.second_gift, false, "Gift") : ""}${a.quirk ? chip("quirk", `Quirk: ${a.quirk}`, "quirk") : ""}</div>
          <div class="badges">${bad.map((x) => `<span class="badge bad">${esc(x)}</span>`).join("") || '<span class="badge ok">ready</span>'}</div></div></div>`;
      }).join("")}`;
  } else bp.innerHTML = "";
  renderTale(s.tale || {});
}

// Small labels for a hero's traits and an Ally's Gifts and Quirks: the name, and what it does on hover.
function chip(name, text, cls = "") {
  return `<span class="trait ${cls}" tabindex="0"${text ? ` title="${esc(text)}"` : ""}>${iconize(esc(name))}</span>`;
}
// What comes up in play stays in view (Distinctive Features to invoke, Rewards on gear); the rest of the
// hero's makeup (Blessing, Calling, Virtues, Shadow Path) folds away under "Traits & virtues".
function traitsRow(t) {
  if (!t) return "";
  const parts = [];
  for (const f of t.features || []) parts.push(chip(f.name, f.text, "feature"));
  for (const r of t.rewards || []) parts.push(chip(r.name, r.text, "reward"));
  return parts.length ? `<div class="traits">${parts.join("")}</div>` : "";
}
function traitsFold(t) {
  if (!t) return "";
  const parts = [];
  if (t.blessing) parts.push(chip(t.blessing.name, t.blessing.text, "blessing"));
  if (t.calling) parts.push(chip(String(t.calling.name).replace(/\s*\(.*\)$/, ""), t.calling.text, "calling"));
  for (const v of t.virtues || []) parts.push(chip(String(v.name).replace(/\s*\(.*\)$/, ""), v.text, "virtue"));
  if (t.shadow_path) parts.push(chip(t.shadow_path.name, t.shadow_path.text, "shadowpath"));
  return parts.length ? `<details id="fold-traits"${openAttr("fold-traits", false)}><summary>Traits & virtues</summary>
      <div class="traits">${parts.join("")}</div></details>` : "";
}
function giftChip(raw, wasted, label, cls = "") {
  const [name, ...rest] = String(raw || "").split(":");
  if (!name.trim()) return "";
  const text = `${label}${wasted ? " (wasted until the next Fellowship Phase)" : ""}: ${rest.join(":").trim() || name.trim()}`;
  return chip(name.trim(), text, `${cls} ${wasted ? "wasted" : ""}`);
}

function renderTale(t) {
  const tp = $("#panel-tale");
  const m = t.mission, j = t.journey, plan = t.plan, th = t.threads || { open: [], resolved: [] }, cp = t.compass || {};
  const kv = (k, v) => (v == null || v === "" || (Array.isArray(v) && !v.length) ? "" :
    `<div class="kv"><span>${k}</span><span>${esc(Array.isArray(v) ? v.join(", ") : v)}</span></div>`);
  const mission = m ? `<div class="tale-block"><div class="tale-head">Mission <em>${esc(m.status || "")}</em></div>
      <div class="tale-name">${esc(m.name)}</div>${m.objective ? `<div class="tale-text">${inline(m.objective)}</div>` : ""}
      ${kv("Patron", m.patron)}${kv("Roster", m.roster)}${kv("Readiness", m.readiness)}${kv("Burden", m.burden)}</div>` : "";
  const journey = j ? `<div class="tale-block"><div class="tale-head">Journey <em>${esc(j.status || "")}</em></div>
      <div class="tale-name">${esc(j.from || "?")} → ${esc(j.to || "?")}</div>
      ${kv("Season", j.season)}${kv("Hexes", j.hexes || null)}${kv("Days", j.days || null)}${kv("Fatigue gained", j.fatigue_gained || null)}${kv("Route", j.route)}</div>`
    : plan ? `<div class="tale-block"><div class="tale-head">Planned journey</div>
      <div class="tale-name">${esc(plan.from)} → ${esc(plan.to)}</div>
      <div class="kv"><span>Distance</span><span>${plan.hexes} hex${plan.hexes === 1 ? "" : "es"} · ${Math.round(plan.miles)} miles</span></div></div>` : "";
  const thread = (x) => x.text ? `<details class="thread"><summary>${inline(x.title)}</summary><div>${inline(x.text)}</div></details>`
    : `<div class="thread plain">${inline(x.title)}</div>`;
  const threads = th.open.length || th.resolved.length ? `<details class="fold" id="fold-threads"${openAttr("fold-threads", true)}>
      <summary><span>Threads</span><em>${th.open.length} open</em></summary>
      ${th.open.map(thread).join("")}
      ${th.resolved.length ? `<details class="fold sub" id="fold-resolved"${openAttr("fold-resolved", false)}><summary><span>Resolved</span><em>${th.resolved.length}</em></summary>
        ${th.resolved.map(thread).join("")}</details>` : ""}</details>` : "";
  const secs = Object.entries(cp.sections || {});
  const compass = secs.length ? `<details class="fold" id="fold-compass"${openAttr("fold-compass", false)}>
      <summary><span>Compass</span><em>surprise ${esc(cp.surprise || "–")}${cp.cutaways ? " · cutaways" : ""}</em></summary>
      ${(cp.pacing || []).length ? `<div class="kv"><span>More of</span><span>${esc(cp.pacing.join(", "))}</span></div>` : ""}
      ${secs.map(([k, v]) => `<div class="compass-sec"><b>${esc(k)}</b><ul>${v.map((x) => `<li>${inline(x)}</li>`).join("")}</ul></div>`).join("")}
      <div class="tale-hint">You write the Compass in Obsidian (10 Campaign/Compass).</div></details>` : "";
  const any = mission || journey || threads || compass;
  $("#dtab-tale").hidden = !any;
  $("#dtab-tale em").textContent = th.open.length ? `${th.open.length}` : "";
  $("#dtab-tale").title = `${m ? "On a mission. " : j ? "On the road. " : ""}${th.open.length} open thread${th.open.length === 1 ? "" : "s"}; Compass`;
  tp.innerHTML = any
    ? `<h2>The Tale <small>${m ? "on a mission" : j ? "on the road" : plan ? "a journey planned" : ""}</small></h2>${mission}${journey}${threads}${compass}` : "";
}

// ------------------------------------------------------------------ drawer (The Tale, Rolls)
function openDrawer(which) {
  const d = $("#drawer");
  if (d.classList.contains("open") && d.dataset.show === which) { closeDrawer(); return; }
  d.dataset.show = which;
  d.style.top = `${Math.round($(".topbar").getBoundingClientRect().bottom)}px`;   // just under the top bar
  d.classList.add("open");
  document.body.classList.add("drawer-open");
  d.setAttribute("aria-hidden", "false");
  document.querySelectorAll(".dtab").forEach((b) => b.classList.toggle("on", b.dataset.drawer === which));
}
function closeDrawer() {
  const d = $("#drawer");
  d.classList.remove("open");
  document.body.classList.remove("drawer-open");
  d.setAttribute("aria-hidden", "true");
  document.querySelectorAll(".dtab").forEach((b) => b.classList.remove("on"));
}
document.querySelectorAll(".dtab").forEach((b) => (b.onclick = (ev) => { ev.stopPropagation(); openDrawer(b.dataset.drawer); }));
$("#drawer-close").onclick = closeDrawer;
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && $("#drawer").classList.contains("open")) closeDrawer(); });
document.addEventListener("pointerdown", (ev) => {   // a click elsewhere on the table closes it
  if ($("#drawer").classList.contains("open") && !ev.target.closest("#drawer, #drawer-tabs")) closeDrawer();
});

// ------------------------------------------------------------------ the Fight panel
// What the hero can see of a fight: each foe's state as a bar and a word, the numbers the hero has come to
// know, the Fell Abilities it has shown; for a battle, how the war party holds and what helps or hinders.
function renderFight(f) {
  const box = $("#fight");
  document.body.classList.toggle("in-fight", !!f);   // the painting steps back to a banner while a fight lasts
  if (!f) { box.hidden = true; box.innerHTML = ""; return; }
  box.hidden = false;
  const bar = (r, word, cls = "") => r == null ? "" :
    `<div class="fbar ${cls} w-${esc(String(word).replace(/\s+/g, "-"))}"><span style="width:${Math.round(r * 100)}%"></span></div>`;
  const b = f.battle;
  const head = [f.kind === "battle" ? `Clash ${b?.clash ?? 1}` : `Round ${f.round ?? 1}`,
    f.stance ? `stance: ${f.stance}` : "", b?.focus ? `focus: ${b.focus}` : "", b?.band_stance ? `Band: ${b.band_stance}` : ""]
    .filter(Boolean).join(" · ");
  const battle = b ? `<div class="fbattle">
      <div class="frow"><b>The war party</b>${bar(b.bar, b.word, "party")}<em>${esc(b.word)}</em></div>
      ${b.objective ? `<div class="frow"><b>${esc(b.objective)}</b>${bar(b.objective_bar, b.objective_word, "objective")}<em>${esc(b.objective_word)}</em></div>` : ""}
      <div class="ftags">${b.advantages.map((t) => `<span class="ftag good">${iconize(esc(t))}</span>`).join("")}${b.complications.map((t) => `<span class="ftag bad">${iconize(esc(t))}</span>`).join("")}</div>
    </div>` : "";
  const foes = f.foes.map((x) => {
    const pic = x.image ? `<img src="${esc(x.image)}" alt="">` : `<span class="ph">${esc(x.name[0])}</span>`;
    const count = x.count > 1 ? ` ×${x.count}${x.down ? ` <small>(${x.down} down)</small>` : ""}` : "";
    const nums = Object.entries(x.known || {}).map(([k, v]) => `<span class="fnum">${esc(k)} ${esc(v)}</span>`).join("");
    const abil = (x.abilities || []).map((a) => `<span class="fabil" title="${esc(a.text || "")}">${esc(a.name)}</span>`).join("");
    return `<div class="foe ${x.state !== "fighting" ? "out" : ""}">${pic}<div class="fbody">
        <div class="fname">${esc(x.name)}${count}${x.features.length ? ` <i>${esc(x.features.join(", "))}</i>` : ""}</div>
        <div class="frow">${bar(x.bar, x.word)}<em>${esc(x.word)}</em>${x.marks.map((m) => `<span class="badge bad">${esc(m)}</span>`).join("")}</div>
        ${x.weapons.length || x.engaged.length || nums || abil ? `<div class="fsub">${esc(x.weapons.join(", "))}${x.engaged.length ? `${x.weapons.length ? " · " : ""}vs ${esc(x.engaged.join(", "))}` : ""}${nums}${abil}</div>` : ""}
      </div></div>`;
  }).join("");
  box.innerHTML = `<details id="fight-fold"${isOpen("fight-fold", true) ? " open" : ""}>
      <summary><span class="ftitle">⚔ ${esc(f.title)}</span><em>${esc(head)}</em></summary>
      ${battle}<div class="foes">${foes}</div>
      ${f.log.length ? `<div class="flog">${f.log.map((l) => `<div>${iconize(esc(l))}</div>`).join("")}</div>` : ""}
    </details>`;
}
document.addEventListener("toggle", (ev) => {
  if (ev.target.id === "fight-fold" || ev.target.id === "journey-fold") {
    try { localStorage.setItem("rw.open." + ev.target.id, ev.target.open ? "1" : "0"); } catch {}
  }
}, true);

// ------------------------------------------------------------------ the Journey panel
// The road as a strip of hexes (walked, here, still ahead; road stretches marked), the days on the road, the
// fatigue it has cost, and every moment so far: marching tests, events and the interludes between them.
const ROAD_MARK = { march: "»", event: "◆", interlude: "☾", rest: "⌂", other: "·" };
function renderJourney(j) {
  const box = $("#journey");
  document.body.classList.toggle("on-road", !!j);
  if (!j) { box.hidden = true; box.innerHTML = ""; return; }
  box.hidden = false;
  const n = j.hexes || 0;
  const pips = n ? Array.from({ length: n }, (_, i) =>
    `<span class="pip${i < j.done ? " done" : ""}${i === Math.min(j.done, n - 1) && j.done < n ? " here" : ""}${j.road[i] ? " road" : ""}"
       title="Hex ${i + 1} of ${n}${j.road[i] ? " · on the road" : ""}"></span>`).join("") : "";
  const strip = `<div class="jstrip"><span class="jend">${esc(j.from)}</span>
      <span class="pips">${pips || '<span class="jline"></span>'}</span><span class="jend">${esc(j.to)}</span></div>`;
  const cost = [j.fatigue.hero ? `<span class="ftag bad">Hero fatigue +${j.fatigue.hero}</span>` : "",
    j.fatigue.band ? `<span class="ftag bad">Band fatigue +${j.fatigue.band}</span>` : ""].join("");
  const rows = j.log.map((e) => {
    const f = [e.fatigue_hero ? `hero +${e.fatigue_hero}` : "", e.fatigue_band ? `Band +${e.fatigue_band}` : ""].filter(Boolean).join(", ");
    const sub = [e.who, e.outcome].filter(Boolean).join(" · ");
    return `<button type="button" class="jrow k-${esc(e.kind)}" data-mark="${esc(e.id)}" title="Show it in the tale">
        <span class="jm">${ROAD_MARK[e.kind] || "·"}</span>
        <span class="jt"><b>Day ${esc(e.day)}${e.at ? ` · ${esc(e.at)}` : ""}</b> ${iconize(esc(e.title))}${sub ? ` <i>(${iconize(esc(sub))})</i>` : ""}
          ${e.text ? `<span class="jx">${iconize(esc(e.text))}</span>` : ""}</span>
        ${f ? `<span class="jf">${esc(f)}</span>` : ""}</button>`;
  }).join("");
  const head = [`day ${j.day_on_road} on the road`, n ? `${j.done} of ${n} hexes` : "", j.season, j.mode].filter(Boolean).join(" · ");
  box.innerHTML = `<details id="journey-fold"${isOpen("journey-fold", true) ? " open" : ""}>
      <summary><span class="jtitle">The road: ${esc(j.title)}</span><em>${esc(head)}</em></summary>
      ${strip}${cost ? `<div class="ftags">${cost}</div>` : ""}
      ${rows ? `<div class="jlog">${rows}</div>` : '<div class="jempty">The road lies ahead.</div>'}
    </details>`;
  const lg = box.querySelector(".jlog");
  if (lg) lg.scrollTop = lg.scrollHeight;          // the newest moment in view
}
$("#journey").addEventListener("click", (ev) => {
  const r = ev.target.closest(".jrow");
  const m = r && document.getElementById("jm-" + r.dataset.mark);
  if (m) { if (tucked) setTucked(false); m.scrollIntoView({ block: "center" }); m.classList.add("flash"); setTimeout(() => m.classList.remove("flash"), 1500); }
});

// ------------------------------------------------------------------ roll log
const rollLog = [];   // {kind, ok, who, what, tn, total, degree, adversary, answer, card}
function logRoll(r) { rollLog.push(r); if (!replaying) renderRolls(); }
function renderRolls() {
  const rp = $("#panel-rolls");
  $("#dtab-rolls").hidden = !rollLog.length;
  if (!rollLog.length) { rp.innerHTML = ""; return; }
  const last = rollLog[rollLog.length - 1];
  const rows = rollLog.slice(-40).reverse().map((r, i) => {
    const mark = r.kind === "oracle" ? "?" : r.ok ? "✓" : "✗";
    const res = r.kind === "oracle" ? esc(r.answer) : `${r.total} vs ${r.tn}${r.degree && r.ok && r.degree !== "success" ? " · " + esc(r.degree) : ""}`;
    return `<div class="rl ${r.kind === "oracle" ? "or" : r.ok ? "ok" : "ko"}${r.adversary ? " adv" : ""}" data-i="${rollLog.length - 1 - i}" title="Show it in the tale">
      <span class="m">${mark}</span><span class="w">${iconize(esc(r.who ? `${r.who}: ${r.what}` : r.what))}</span><span class="r">${iconize(res)}</span></div>`;
  }).join("");
  const mine = rollLog.filter((r) => r.kind === "roll" && !r.adversary);
  const wins = mine.filter((r) => r.ok).length;
  const lastMark = last.kind === "oracle" ? "?" : last.ok ? "✓" : "✗";
  const tab = $("#dtab-rolls em");
  tab.textContent = lastMark;
  tab.className = last.kind === "oracle" ? "or" : last.ok ? "ok" : "ko";
  $("#dtab-rolls").title = `${mine.length ? `${wins} of ${mine.length} of your rolls succeeded. ` : ""}Last: ${last.kind === "oracle" ? "an oracle" : last.ok ? "a success" : "a failure"}`;
  rp.innerHTML = `<h2>Rolls <small>${mine.length ? `${wins} of ${mine.length} succeeded` : ""}</small></h2>
    <div class="rolllog">${rows}</div>`;
}
document.addEventListener("click", (ev) => {
  const row = ev.target.closest(".rl[data-i]");
  if (row) {
    const r = rollLog[Number(row.dataset.i)];
    closeDrawer();
    if (r?.card?.isConnected) { r.card.scrollIntoView({ behavior: "smooth", block: "center" }); r.card.classList.add("flash"); setTimeout(() => r.card.classList.remove("flash"), 1600); }
    return;
  }
  const adj = ev.target.closest("[data-adj]");
  if (adj && adj.closest("#side")) {
    ev.preventDefault();
    send(adj.dataset.d ? { t: "adjust", key: adj.dataset.adj, delta: Number(adj.dataset.d) } : { t: "adjust", key: adj.dataset.adj });
  }
});

// ------------------------------------------------------------------ events
let busyNow = false;
function setBusy(busy) {
  busyNow = !!busy;
  updateActivity();
  const b = $("#btn-stop");          // Stop only makes sense while Ringwraith is working
  b.disabled = !busyNow;
  if (!busyNow) b.textContent = "Interrupt";
}
function updateActivity(text) {
  const waiting = trays.size > 0;
  document.body.classList.toggle("tray-open", waiting);
  const a = $("#activity");
  a.classList.toggle("on", busyNow);
  a.classList.toggle("waiting", waiting);
  if (waiting) $("#activity-text").textContent = "Ringwraith waits for your roll…";
  else if (text) $("#activity-text").textContent = text;
  else if (!busyNow) $("#activity-text").textContent = "Ringwraith is writing…";
}
function handle(e) {
  switch (e.t) {
    case "text_start": { const n = narrStart(e.retell); if (e.muted) n.classList.add("muted"); break; }
    case "text_delta": narrDelta(e.text); break;
    case "narration": narrFinal(e.text, e.aside, e.recap, e.summary); break;
    case "turn_end": endLive(); pathsThisTurn = false; untoldSummary = null; break;
    case "busy":
      setBusy(e.busy);
      if (!e.busy) endLive();
      else document.querySelector(".player.queued")?.classList.remove("queued");   // its turn has come
      break;
    case "activity":
      updateActivity(e.text ? `Ringwraith ${e.text}…` : "Ringwraith is writing…");
      break;
    case "player":
      endLive(); clearPaths(); pathsThisTurn = false;
      document.querySelectorAll(".card.stale button, .error-box button").forEach((b) => b.remove());
      lastSaid = e.text;
      // Sent while Ringwraith is still busy (and not answering a waiting roll): it is read when this turn ends.
      add(el("div", "player" + (busyNow && !replaying && !trays.size ? " queued" : ""), iconize(esc(e.text))));
      scrollDown(true);
      break;
    case "paths": showPaths(e.paths); pathsThisTurn = true; break;
    case "roll_request": {
      requests.set(e.id, e);
      if (e.stale) {
        const c = add(el("div", "card stale", `<div><div class="label">ROLL INTERRUPTED</div>${esc(e.who)} — ${esc(e.what)}, TN ${e.tn}: the table restarted before the dice were cast.</div>`));
        const b = el("button", null, "Ask again");
        b.type = "button";
        b.style.marginLeft = "auto";
        b.onclick = () => say(`(The table restarted while the ${e.what} roll for ${e.who} was waiting. Please ask for that roll again.)`);
        c.appendChild(b);
        break;
      }
      const t = rollTray(e);
      trays.set(e.id, t);
      dockEl.appendChild(t);
      updateActivity();
      if (!replaying) setTucked(false);
      scrollDown(true);
      if (!replaying) t.scrollIntoView({ behavior: "smooth", block: "end" });
      break;
    }
    case "roll_result": {
      if (e.id) closeTray(e.id);
      const card = add(rollCard(e, requests.get(e.id)));
      logRoll({ kind: "roll", ok: e.outcome === "success", who: e.who, what: e.what, tn: e.tn, total: e.total,
        degree: e.degree, adversary: !!e.adversary, card });
      break;
    }
    case "roll_cancelled": closeTray(e.id); break;
    case "oracle": {
      const c = el("div", "card");
      c.innerHTML = e.kind === "telling"
        ? `<div><div class="label">THE TELLING · ${esc(e.chance)}</div>${iconize(esc(e.question))}</div><div class="answer" style="margin-left:auto">${iconize(esc(e.answer))}</div>`
        : `<div><div class="label">LORE TABLE</div><span style="white-space:pre-wrap">${iconize(esc(e.answer))}</span></div>`;
      if (e.kind === "telling") c.insertBefore(featDie(e.feat), c.firstChild);
      add(c);
      logRoll({ kind: "oracle", what: e.kind === "telling" ? `Telling (${e.chance}): ${e.question}` : "Lore table",
        answer: String(e.answer || "").split("\n")[0].slice(0, 60), card: c });
      break;
    }
    case "scene":
      endLive();
      add(el("div", "divider"));
      add(el("div", "scene-head", esc(e.title)));
      nextOpening = true;
      $("#stage-title").textContent = e.title;
      sceneJob = e.job;
      painting(!!e.job);
      break;
    case "image":
      if (e.preset === "scene") {
        if (!sceneJob || e.job === sceneJob) { setStage(e.url, undefined, !replaying); painting(false); sceneJob = null; }
      } else if (e.preset === "portrait" || e.preset === "adversary" || e.preset === "item") {
        const name = e.note ? e.note.split("/").pop().replace(/\.md$/, "") : "";
        const c = el("div", "card portrait");
        c.innerHTML = `<img src="${esc(e.url)}" alt=""><div><div class="label">${e.preset.toUpperCase()}</div>${esc(name)}</div>`;
        add(c);
      } else if (e.preset === "map") {             // a journey's way, drawn when the company moves
        const c = el("div", "card mapcard");
        c.innerHTML = `<img src="${esc(e.url)}" alt="Map of the way"><div class="label">THE ROAD · DAY ${esc(e.day ?? "")}</div><div>${esc(e.subject || "")}</div>`;
        add(c);
      } else if (e.preset === "scenery" && !sceneJob) {
        setStage(e.url, undefined, !replaying);
      }
      break;
    case "sheet": renderSheet(e.sheet); break;
    case "fight": renderFight(e.fight); break;
    case "journey": renderJourney(e.journey); break;
    case "journey_mark": {        // a waymark in the tale where a moment of the road begins
      endLive();
      const m = add(el("div", "waymark k-" + (e.kind || "other"),
        `${ROAD_MARK[e.kind] || "·"} Day ${esc(e.day)}${e.at ? ", " + esc(e.at) : ""}: ${iconize(esc(e.title))}`));
      m.id = "jm-" + e.id;
      nextOpening = true;
      break;
    }
    case "journey_end": {
      const f = e.fatigue || {};
      const cost = [f.hero ? `hero fatigue +${f.hero}` : "", f.band ? `Band fatigue +${f.band}` : ""].filter(Boolean).join(", ");
      add(el("div", "card journeyend", `<div><div class="label">${e.status === "abandoned" ? "THE COMPANY TURNS BACK" : "THE JOURNEY ENDS"}</div>
        <b>${esc(e.title)}</b>: ${esc(e.days)} days on the road${cost ? `; ${esc(cost)}` : ""}.${e.outcome ? ` ${iconize(esc(e.outcome))}` : ""}</div>`));
      break;
    }
    case "fight_end": {
      const c = el("div", "card fightend");
      c.innerHTML = `<div><div class="label">${e.kind === "battle" ? "THE BATTLE ENDS" : "THE FIGHT ENDS"}</div><b>${esc(e.title)}</b>${e.outcome ? `: ${iconize(esc(e.outcome))}` : ""}</div>`;
      add(c);
      break;
    }
    case "geo":
      if (!replaying) { RWMap.refresh(); if (e.show) stageView("map"); }
      break;
    case "system": {
      const prev = logEl.lastElementChild;
      if (e.change && prev && prev.dataset.change === e.change) { prev.textContent = e.text; break; }
      const n = add(el("div", "note", esc(e.text)));
      if (e.change) n.dataset.change = e.change;
      break;
    }
    case "error": showError(e.text); break;
  }
}

// When a turn fails: say plainly what happened and what to do, with the technical detail folded away.
let lastSaid = "";
function showError(detail) {
  endLive();
  const box = el("div", "error-box");
  box.innerHTML = `<div><b>Ringwraith stumbled, and this turn didn't finish.</b> Nothing in the vault was lost.
      ${lastSaid ? "Try again sends your last words once more." : ""}</div>
    <details><summary>What went wrong</summary><code>${esc(detail)}</code></details>`;
  if (lastSaid && !replaying) {
    const b = el("button", null, "Try again");
    b.type = "button";
    b.onclick = () => { if (send({ t: "say", text: lastSaid })) b.remove(); };
    box.appendChild(b);
  }
  add(box);
}

// The connection: one pill in the top bar says whether the table is reachable, and it reconnects by itself,
// waiting a little longer each time while the server is down.
let retryMs = 1000;
function setConn(state) {
  const c = $("#conn");
  c.dataset.state = state;
  c.textContent = { online: "Connected", connecting: "Connecting…", offline: "Reconnecting…" }[state];
  c.title = state === "online" ? "The table is connected to Ringwraith"
    : "The table can't reach the server (is `ringwraith serve` running?). It keeps trying; nothing you type is lost.";
  document.body.classList.toggle("offline", state !== "online");
  if (state === "offline" && !logEl.children.length)       // a first load with no server: say why it's empty
    add(el("div", "note", "The table can't reach its server. Start it with <code>ringwraith serve</code>; this page connects by itself once it runs."));
}
function flashConn() { const c = $("#conn"); c.classList.remove("flash"); void c.offsetWidth; c.classList.add("flash"); }
function connect() {
  setConn("connecting");
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onopen = () => { retryMs = 1000; setConn("online"); };
  ws.onmessage = (m) => {
    const e = JSON.parse(m.data);
    if (e.t === "hello") {
      // A fresh start: everything shown is rebuilt from the replay.
      logEl.innerHTML = ""; dockEl.innerHTML = ""; trays.clear(); requests.clear(); live = []; rollLog.length = 0;
      pathsThisTurn = false; untoldSummary = null; sceneJob = null; nextOpening = true; lastSaid = "";
      renderFight(null);
      renderJourney(null);
      if (tucked) setTucked(false);
      replaying = true;
      for (const r of e.replay) { try { handle(r); } catch (err) { console.error(err, r); } }
      replaying = false;
      renderRolls();
      painting(false);
      if (!e.replay.length) add(el("div", "note", "The table is set. Press “Begin session”, or speak to Ringwraith below."));
      renderSheet(e.sheet);
      setBusy(e.busy);
      scrollDown(true);
      setTimeout(() => scrollDown(true), 300);   // again once fonts and images have laid out
      return;
    }
    handle(e);
  };
  ws.onclose = () => {
    setConn("offline");
    setBusy(false);
    setTimeout(connect, retryMs);
    retryMs = Math.min(retryMs * 2, 15000);
  };
}

// Returns whether the words went; if the table is offline they stay in the box.
function say(text) {
  text = text.trim();
  if (!text) return false;
  return send({ t: "say", text });
}
function sayInput() { if (say(input.value)) input.value = ""; }

$("#composer").addEventListener("submit", (ev) => { ev.preventDefault(); sayInput(); });
input.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); sayInput(); }
});
$("#stage").onclick = (ev) => {
  if ($("#stage").classList.contains("mapmode") || ev.target.closest(".stage-tabs")) return;
  $("#stage").classList.toggle("full");
  fitFull();
};
// The whole painting: as tall as the painting is at this width (no bands above and below), up to 78% of the window.
function fitFull() {
  const st = $("#stage"), img = $(`#stage-img-${stageFront}`);
  st.style.height = "";
  if (!st.classList.contains("full") || !img.naturalWidth) return;
  st.style.height = Math.min(st.clientWidth * img.naturalHeight / img.naturalWidth, innerHeight * 0.78) + "px";
}
addEventListener("resize", fitFull);
function stageView(view) {
  const st = $("#stage");
  st.classList.toggle("mapmode", view === "map");
  st.classList.remove("full", "banner");
  st.style.height = "";
  st.title = view === "map" ? "" : "Click to see the whole painting";     // the map has its own controls
  document.querySelectorAll("#stage-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.view === view));
  if (view === "map") RWMap.open();
}
document.querySelectorAll("#stage-tabs button").forEach((b) => (b.onclick = (ev) => { ev.stopPropagation(); stageView(b.dataset.view); }));
$("#stage-repaint").onclick = (ev) => {
  ev.stopPropagation();
  const now = $("#stage-title").textContent || "an old scene";
  say(`(The stage still shows “${now}”. Please set the scene for where we are now.)`);
};
$("#stage").title = "Click to see the whole painting";
$("#btn-begin").onclick = () => {
  // Mid-session it only repeats the load and the recap, so ask first; at the start it just begins.
  const lastStart = [...logEl.querySelectorAll(".player")].reverse().find((p) => /^\/session-(start|end)/.test(p.textContent));
  if (!lastStart || /session-end/.test(lastStart.textContent)) { say("/session-start"); return; }
  ask({ title: "Begin again?", ok: "Begin session", cancel: "Play on",
        text: "A session is already under way. Beginning again makes Ringwraith reload the campaign and recap; the story so far is kept." })
    .then((yes) => { if (yes) say("/session-start"); });
};
$("#btn-end").onclick = () => {
  ask({ title: "End the session?", ok: "End the session", cancel: "Play on",
        text: "Ringwraith will write the session into Obsidian: the tale with its paintings, the people and places met, the rolls, and the experience earned." })
    .then((yes) => { if (yes) say("/session-end"); });
};
$("#btn-stop").onclick = () => {
  if (!send({ t: "interrupt" })) return;
  const b = $("#btn-stop");
  b.textContent = "Interrupting…";
  b.disabled = true;
};
$("#btn-new").onclick = () => {
  ask({ title: "A new conversation?", ok: "Start afresh", cancel: "Keep this one", danger: true,
        text: "Ringwraith forgets this conversation and reloads the campaign. The vault and the state are kept; only the chat memory resets." })
    .then((yes) => { if (yes) send({ t: "new_session" }); });
};
connect();
