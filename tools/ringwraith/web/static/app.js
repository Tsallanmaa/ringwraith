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
// Model and vault text may only use what Markdown makes, plus the icon spans: no style, id, forms or images that
// could cover the controls, post somewhere, or capture the page's own element lookups.
const SAFE = {
  ALLOWED_TAGS: ["p", "br", "hr", "em", "strong", "del", "a", "ul", "ol", "li", "blockquote", "code", "pre",
                 "h1", "h2", "h3", "h4", "table", "thead", "tbody", "tr", "th", "td", "span", "sup", "sub"],
  ALLOWED_ATTR: ["href", "title", "class"],
};
marked.setOptions({ breaks: true });   // a single line break is a line break (OOC notes are written line by line)
const ICONS = {
  "{success}": '<span class="glyph succ" title="success icon">✦</span>',
  "{eye}": '<span class="glyph eye" title="Eye of Sauron">◉</span>',
  "{gandalf}": '<span class="glyph rune" title="Gandalf rune">ᚷ</span>',
};
const iconize = (escaped) => escaped.replace(/\{(success|eye|gandalf)\}/g, (m) => ICONS[m]);
function md(text) {
  const withIcons = String(text || "").replace(/\{(success|eye|gandalf)\}/g, (m) => ICONS[m]);
  const html = DOMPurify.sanitize(marked.parse(withIcons), SAFE);
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
    return (t.classList.contains("reading") ? "Reading waiting · " : "Roll waiting · ") + (t.querySelector(".title")?.textContent || "");
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
  if (replaying) return;            // the replay scrolls once at its end: each scroll here forces a layout
  const near = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 240;
  if (force || near) logEl.scrollTop = logEl.scrollHeight;
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
  if (!replaying) announce(n.textContent);
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
    keyClickable(c);
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
let askingAboutReading = false;   // the next words are a question to Ringwraith, not the player's reading
function readingTray(e) {
  askingAboutReading = false;
  const t = el("div", "tray reading");
  t.innerHTML = `
    <div class="tray-head"><span class="title">Oracle — ${iconize(esc(e.question))}</span></div>
    <div class="stakes">${iconize(esc(e.result))}</div>
    <div class="suggestion"><span class="label">Ringwraith suggests</span> ${iconize(esc(e.suggestion))}</div>`;
  const foot = el("div", "tray-foot");
  const ok = el("button", null, "Accept this reading");
  ok.type = "button";
  ok.onclick = () => answerRoll(e.id, "accept");
  const hint = el("span", "hint", "or type below: your words become the reading");
  const ask = el("button", "linkish", "Ask Ringwraith first");
  ask.type = "button";
  ask.onclick = () => {
    askingAboutReading = !askingAboutReading;
    ask.textContent = askingAboutReading ? "Give my own reading instead" : "Ask Ringwraith first";
    hint.textContent = askingAboutReading ? "or type your question below" : "or type below: your words become the reading";
    updateActivity();
    input.focus();
  };
  foot.append(ok, hint, ask);
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
const inline = (t) => DOMPurify.sanitize(marked.parseInline(String(t || "").replace(/\{(success|eye|gandalf)\}/g, (m) => ICONS[m])), SAFE);
// What each number on the sheets does, in a line, for the hover tooltips.
const TIP = {
  parry: "The TN of every attack made against you. It comes from Wits and your culture, plus a shield.",
  endurance: "Staying power in a fight. Blows lower it; at 0 you fall unconscious. At or below your Load plus Fatigue (the mark on the bar) you are Weary.",
  hope: "Spend a point before a roll for an extra Success die (two when Inspired). It comes back with rest among friends and in the Fellowship Phase. If Shadow reaches your current Hope, you are Miserable.",
  shadow: "Darkness taken in: dread, greed, misdeeds, sorcery. At or above your current Hope you are Miserable. If it fills all your Hope, every roll is Ill-favoured until a bout of madness clears it and leaves a lasting flaw. Scars are Shadow that never leaves.",
  fellowship: "The ties that hold you up: while resting, spend points from it to regain Hope. The pool fills again after moments of true fellowship.",
  weary: "Endurance at or below Load plus Fatigue: 1, 2 and 3 on the Success dice count as nothing.",
  miserable: "Shadow at or above current Hope: an Eye on the Feat die fails the roll outright.",
  wounded: "A wound that takes hours or days to heal and slows your recovery while resting. A second wound before then leaves you dying.",
  load: "War gear and treasure; travelling gear doesn't count. Endurance at or below Load plus Fatigue makes you Weary.",
  fatigue: "The toll of the road. It counts as extra Load and wears off with rest in a safe refuge.",
  strength: "TN for the skills of body and force. It also sets your Endurance.",
  heart: "TN for the skills of spirit and fellowship. It also sets your Hope.",
  wits: "TN for the skills of mind and wariness. It also sets your Parry.",
  xp: "Skill points buy Skill ranks; Adventure points buy Combat Proficiencies and Valour or Wisdom. Spent in the Fellowship Phase.",
  eye: "How much the Enemy has noticed you. An Eye on the Feat die outside combat, gaining Shadow and open magic raise it. At the Hunt threshold you are found out: something comes for you, and the count starts over.",
  readiness: "How ready the Band is: every Band and Ally roll is made against the TN beside it. Hardened Allies raise it.",
  expertise: "The Band's learning: crafts, first aid, hunting, lore.",
  manoeuvre: "The Band's movement: hard paths, keeping pace, sneaking past foes, fleeing.",
  rally: "The Band's heart: enduring harm and weariness, standing fast, holding together.",
  vigilance: "The Band's watchfulness: spotting threats, keeping watch, searching.",
  war: "The Band's fighting strength, tactics and gear. Rolled in battles.",
};
const tipAttr = (k) => (TIP[k] ? ` class="tip" title="${esc(TIP[k])}"` : "");
// − / + buttons that change the hero sheet (the server writes the note and tells Ringwraith)
const stepper = (key) => `<span class="step"><button type="button" data-adj="${key}" data-d="-1" title="One less">−</button><button type="button" data-adj="${key}" data-d="1" title="One more">+</button></span>`;
function clockSummary(deadlines, day, counters) {
  if (!deadlines.length) return counters ? `${counters} counter${counters > 1 ? "s" : ""}` : "";
  const next = deadlines[0], left = day != null ? next.due - day : null;
  const when = left == null ? `day ${next.due}` : left > 1 ? `in ${left} days` : left === 1 ? "tomorrow"
    : left === 0 ? "today" : "overdue";
  return `${deadlines.length} · next ${when}`;
}
// A procedure panel, redrawn only when what it shows has changed (a redraw would reset its scroll).
const PANELS = { fight: (v) => renderFight(v), council: (v) => renderCouncil(v), journey: (v) => renderJourney(v),
  fellowship: (v) => renderFellowship(v) };
const panelShown = {};
function showPanel(key, v) {
  const j = JSON.stringify(v ?? null);
  if (panelShown[key] === j) return;
  panelShown[key] = j;
  PANELS[key](v ?? null);
}
function renderSheet(s) {
  if (!s) return;
  // The saved state is the truth, whatever the event log still holds.
  for (const [k, v] of Object.entries(s.panels || {})) showPanel(k, v);
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
      <h2>The Hero <small><span${tipAttr("parry")}>Parry ${esc(h.parry ?? "–")}</span>${h.xp ? ` · <span class="xp tip" title="${esc(TIP.xp)}">SP ${esc(h.xp.skill ?? 0)} · AP ${esc(h.xp.adventure ?? 0)}</span>` : ""}</small></h2>
      <div class="hero-name">${esc(h.name)}</div>
      <div class="hero-sub">${esc(h.culture || "")}</div>
      <div class="stat"><div class="row"><b${tipAttr("endurance")}>ENDURANCE</b>${stepper("endurance")}<span>${esc(h.endurance?.current ?? "–")} / ${esc(h.endurance?.max ?? "–")}</span></div>
        ${meter("endurance", h.endurance?.current, h.endurance?.max, load)}</div>
      <div class="stat"><div class="row"><b${tipAttr("hope")}>HOPE</b>${stepper("hope")}<span>${esc(hopeCur)} / ${esc(hopeMax)}</span></div>${meter("hope", hopeCur, hopeMax)}</div>
      <div class="stat"><div class="row"><b${tipAttr("shadow")}>SHADOW</b>${stepper("shadow")}<span>${esc(h.shadow?.points ?? 0)}${h.shadow?.scars ? ` + ${esc(h.shadow.scars)} scar${h.shadow.scars > 1 ? "s" : ""}` : ""}</span></div>
        ${meter("shadow", shadow, hopeMax)}</div>
      ${h.fellowship ? `<div class="stat"><div class="row"><b${tipAttr("fellowship")}>FELLOWSHIP</b>${stepper("fellowship")}<span>${esc(h.fellowship.current ?? 0)} / ${esc(h.fellowship.rating ?? 0)}</span></div>
        ${meter("fellowship", h.fellowship.current ?? 0, h.fellowship.rating ?? 0)}</div>` : ""}
      <div class="badges">
        ${weary ? `<span class="badge bad tip" title="${esc(TIP.weary)}">Weary</span>` : ""}
        ${miserable ? `<span class="badge bad tip" title="${esc(TIP.miserable)}">Miserable</span>` : ""}
        <button type="button" class="badge toggle ${c.wounded ? "bad" : "off"}" data-adj="wounded" title="${esc(TIP.wounded)} ${c.wounded ? "Click if the hero is no longer Wounded." : "Click to mark the hero Wounded."}">Wounded</button>
        ${!weary && !miserable && !c.wounded ? '<span class="badge ok">Hale</span>' : ""}
        <span class="badge tip" title="${esc(TIP.load)}">Load ${esc(h.load ?? 0)}</span>
        <span class="badge fat tip" title="${esc(TIP.fatigue)}">Fatigue ${esc(h.fatigue ?? 0)}${stepper("fatigue")}</span>
      </div>
      <div class="attrs">${["strength", "heart", "wits"].map((a) =>
        `<div class="attr"><b${tipAttr(a)}>${a.toUpperCase()}</b><span>${esc(attrs[a] ?? "–")}</span> <i>TN ${attrs[a] != null ? tnBase - attrs[a] : "–"}</i></div>`).join("")}</div>
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
    <div class="stat"><div class="row"><b${tipAttr("eye")}>EYE AWARENESS</b><span>${esc(st.eye_awareness ?? 0)} / ${esc(st.hunt_threshold ?? "–")}</span></div>
      ${meter("eye", st.eye_awareness ?? 0, st.hunt_threshold || 18)}</div>` : "";

  const b = s.band;
  const bp = $("#panel-band");
  if (b || (s.allies || []).length) {
    const d = b?.dispositions || {};
    bp.innerHTML = `
      <h2>The Band ${b ? `<small${tipAttr("readiness")}>Readiness ${esc(b.readiness)} · TN ${(s.tn_base || 20) - (b.readiness || 0)}</small>` : ""}</h2>
      ${b ? `<div class="disps">${["expertise", "manoeuvre", "rally", "vigilance", "war"].map((k) =>
        `<div${tipAttr(k)}><b>${k.toUpperCase()}</b>${esc(d[k] ?? "–")}</div>`).join("")}</div>` : ""}
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
// An advantage or complication: its name, what it gives (+1d), whether it lasts the battle, and a line of story
// as the tooltip. (Plain text comes from fights saved before effects were kept.)
function ftag(t, cls) {
  const e = typeof t === "string" ? { name: t } : t;
  const tip = [e.text, e.persistent ? "Lasts the whole battle." : ""].filter(Boolean).join(" ");
  return `<span class="ftag ${cls}"${tip ? ` title="${esc(tip)}"` : ""}>${iconize(esc(e.name))}` +
    `${e.effect ? ` <b class="feff">${esc(e.effect)}</b>` : ""}${e.persistent ? ` <i class="fpers">persistent</i>` : ""}</span>`;
}
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
      <div class="ftags">${b.advantages.map((t) => ftag(t, "good")).join("")}${b.complications.map((t) => ftag(t, "bad")).join("")}</div>
    </div>` : "";
  const names = (v) => (v || []).map((w) => (w && typeof w === "object" ? w.name : w) || "").filter(Boolean);
  const foes = f.foes.map((x) => {
    x = { ...x, weapons: names(x.weapons), features: names(x.features), engaged: names(x.engaged) };
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
// ------------------------------------------------------------------ the Council panel
// What the hero can tell of a council: who listens and their mood, what the hero asks, how far they are swayed
// (a bar and a word, never the numbers), the exchanges they will allow and how many are spent.
function renderCouncil(c) {
  const box = $("#council");
  if (!c) { box.hidden = true; box.innerHTML = ""; return; }
  box.hidden = false;
  const faces = c.who.map((w) => w.image ? `<img src="${esc(w.image)}" alt="" title="${esc(w.name)}">`
    : `<span class="ph" title="${esc(w.name)}">${esc(w.name[0])}</span>`).join("");
  const n = c.rounds || 0;
  const pips = n ? Array.from({ length: n }, (_, i) => `<span class="pip${i < c.used ? " done" : ""}"></span>`).join("") : "";
  const left = n ? `${Math.max(0, n - c.used)} of ${n} left` : "the introduction comes first";
  const head = [c.who.map((w) => w.name).join(", "), c.attitude].filter(Boolean).join(" · ");
  box.innerHTML = `<details id="council-fold"${isOpen("council-fold", true) ? " open" : ""}>
      <summary><span class="ftitle">☙ ${esc(c.title)}</span><em>${esc(head)}</em></summary>
      <div class="foe"><span class="cfaces">${faces}</span><div class="fbody">
        ${c.request ? `<div class="crequest">${iconize(esc(c.request))}</div>` : ""}
        ${c.bar != null ? `<div class="frow"><b>Swayed</b><div class="fbar sway"><span style="width:${Math.round(c.bar * 100)}%"></span></div><em>${esc(c.word)}</em></div>` : ""}
        <div class="frow"><b>Exchanges</b><span class="pips">${pips}</span><em>${esc(left)}</em></div>
      </div></div>
      ${c.log.length ? `<div class="flog">${c.log.map((l) => `<div>${iconize(esc(l))}</div>`).join("")}</div>` : ""}
    </details>`;
}
// ------------------------------------------------------------------ the Fellowship panel
// The phase as a checklist that survives a break: the duration, the steps done and the next one, the points the
// hero has to spend, the undertakings allowed and taken, and what befell the Band if anything did.
function renderFellowship(p) {
  const box = $("#fellowship");
  if (!p) { box.hidden = true; box.innerHTML = ""; return; }
  box.hidden = false;
  const steps = p.steps.map((s) => `<span class="fstep${s.done ? " done" : s.next ? " next" : ""}">${s.done ? "✓" : s.next ? "▸" : "○"} ${esc(s.label)}</span>`).join("");
  const n = p.undertakings;
  const pips = n ? Array.from({ length: n }, (_, i) => `<span class="pip${i < p.chosen.length ? " done" : ""}"></span>`).join("") : "";
  const und = n == null ? "" : n === 0 ? "none this time"
    : `${Math.max(0, n - p.chosen.length)} of ${n} left${p.chosen.length ? ": " + p.chosen.map(esc).join(", ") : ""}`;
  const done = p.steps.filter((s) => s.done).length;
  const head = [p.duration[0].toUpperCase() + p.duration.slice(1), `${done} of ${p.steps.length} done`].join(" · ");
  box.innerHTML = `<details id="fellowship-fold"${isOpen("fellowship-fold", true) ? " open" : ""}>
      <summary><span class="ftitle">✦ Fellowship${p.place ? " at " + esc(p.place) : ""}</span><em>${esc(head)}</em></summary>
      <div class="fbody">
        <div class="fsteps">${steps}</div>
        <div class="frow"><b>Points</b><span title="Skill points buy Skills; Adventure points buy Proficiencies, Valour and Wisdom">Skill ${esc(p.xp.skill)} · Adventure ${esc(p.xp.adventure)}</span></div>
        ${n != null ? `<div class="frow"><b>Undertakings</b><span class="pips">${pips}</span><em>${und}</em></div>` : ""}
        ${p.interruption ? `<div class="frow"><b>Interrupted</b><span>${iconize(esc(p.interruption))}</span></div>` : ""}
      </div>
      ${p.log.length ? `<div class="flog">${p.log.map((l) => `<div>${iconize(esc(l))}</div>`).join("")}</div>` : ""}
    </details>`;
}
document.addEventListener("toggle", (ev) => {
  if (["fight-fold", "journey-fold", "council-fold", "fellowship-fold"].includes(ev.target.id)) {
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
    return `<div class="rl ${r.kind === "oracle" ? "or" : r.ok ? "ok" : "ko"}${r.adversary ? " adv" : ""}" data-i="${rollLog.length - 1 - i}" title="Show it in the tale" tabindex="0" role="button" data-key-click="1">
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
const PLACEHOLDER = input.placeholder;
// Screen readers hear finished narration and what waits, not every streamed frame.
function announce(text) { const a = $("#announce"); if (a) a.textContent = String(text || "").slice(0, 600); }
function updateActivity(text) {
  const waiting = trays.size > 0;
  const reading = waiting && [...trays.values()].pop().classList.contains("reading");
  input.placeholder = !reading ? PLACEHOLDER
    : askingAboutReading ? "Your question to Ringwraith about the oracle"
    : "Your own reading of the oracle, or accept Ringwraith's above";
  document.body.classList.toggle("tray-open", waiting);
  const a = $("#activity");
  a.classList.toggle("on", busyNow);
  a.classList.toggle("waiting", waiting);
  if (waiting) $("#activity-text").textContent = [...trays.values()].pop().classList.contains("reading")
    ? "Ringwraith waits for your reading of the oracle…" : "Ringwraith waits for your roll…";
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
      if (!replaying) announce(`Roll waiting: ${e.who}, ${e.what}, TN ${e.tn}. Ctrl+Enter rolls.`);
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
    case "roll_cancelled": case "reading_cancelled": closeTray(e.id); break;
    case "reading_request": {     // the player reads the oracle: accept Ringwraith's reading or type their own
      if (e.stale) {
        const c = add(el("div", "card stale", `<div><div class="label">ORACLE READING INTERRUPTED</div>The table restarted before you read the oracle: ${iconize(esc(e.question))}</div>`));
        const b = el("button", null, "Ask again");
        b.type = "button";
        b.style.marginLeft = "auto";
        b.onclick = () => say(`(The table restarted while my reading of the oracle "${e.question}" was waiting. Please offer your reading again.)`);
        c.appendChild(b);
        break;
      }
      const t = readingTray(e);
      trays.set(e.id, t);
      if (!replaying) announce(`Your reading of the oracle waits: ${e.question}. Ctrl+Enter accepts Ringwraith's.`);
      dockEl.appendChild(t);
      updateActivity();
      if (!replaying) setTucked(false);
      scrollDown(true);
      break;
    }
    case "reading_result": {
      closeTray(e.id);
      const card = add(el("div", "card reading", `<div><div class="label">${e.own ? "YOUR READING" : "READING ACCEPTED"} · ${iconize(esc(e.question))}</div>${iconize(esc(e.text))}</div>`));
      logRoll({ kind: "oracle", what: `Reading: ${e.question}`, answer: String(e.text || "").slice(0, 60), card });
      break;
    }
    case "oracle": {
      const c = el("div", "card");
      c.innerHTML = e.kind === "telling"
        ? `<div><div class="label">THE TELLING · ${esc(e.chance)}</div>${iconize(esc(e.question))}</div><div class="answer" style="margin-left:auto">${iconize(esc(e.answer))}</div>`
        : `<div><div class="label">LORE TABLE${e.question ? " · " + iconize(esc(e.question)) : ""}</div><span style="white-space:pre-wrap">${iconize(esc(e.answer))}</span></div>`;
      if (e.kind === "telling") c.insertBefore(featDie(e.feat), c.firstChild);
      add(c);
      logRoll({ kind: "oracle", what: e.kind === "telling" ? `Telling (${e.chance}): ${e.question}` : `Lore table${e.question ? ": " + e.question : ""}`,
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
    case "sketch": {              // a drawing of something told, not seen: it fills in when it is done
      endLive();
      const f = add(el("figure", "sketch waiting", `<div class="sk-wait">sketching…</div><figcaption>${iconize(esc(e.caption || ""))}</figcaption>`));
      f.id = "sk-" + e.job;
      break;
    }
    case "image_failed": {        // the art worker gave up on it: say so rather than wait forever
      const f = document.getElementById("sk-" + e.job);
      if (f) { f.classList.remove("waiting"); f.querySelector(".sk-wait")?.replaceWith(el("div", "sk-wait", "the sketch couldn't be drawn")); }
      if (e.job === sceneJob) { painting(false); sceneJob = null; }
      break;
    }
    case "image":
      if (e.preset === "sketch") {
        const f = document.getElementById("sk-" + e.job);
        if (f) {
          f.classList.remove("waiting");
          const a = Object.assign(document.createElement("a"), { href: e.url, target: "_blank", title: "Open the sketch" });
          a.appendChild(Object.assign(document.createElement("img"), { src: e.url, alt: e.subject || "" }));
          f.querySelector(".sk-wait")?.replaceWith(a);
        }
      } else if (e.preset === "scene") {
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
    case "fight": showPanel("fight", e.fight); break;
    case "council": showPanel("council", e.council); break;
    case "fellowship": showPanel("fellowship", e.fellowship); break;
    case "journey": showPanel("journey", e.journey); break;
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
    case "fellowship_end": {
      const c = el("div", "card councilend fellowshipend");
      c.innerHTML = `<div><div class="label">THE FELLOWSHIP PHASE ENDS</div><b>${esc(e.duration ? e.duration[0].toUpperCase() + e.duration.slice(1) : "")}${e.place ? " at " + esc(e.place) : ""}</b>${e.outcome ? `: ${iconize(esc(e.outcome))}` : ""}</div>`;
      add(c);
      break;
    }
    case "council_end": {
      const c = el("div", "card councilend");
      c.innerHTML = `<div><div class="label">THE COUNCIL ENDS</div><b>${esc(e.title)}</b>${e.outcome ? `: ${iconize(esc(e.outcome))}` : ""}</div>`;
      add(c);
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
      ${lastSaid && !replaying ? "Try again sends your last words once more." : "Type your last words again to carry on."}</div>
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
      for (const k in PANELS) showPanel(k, null);
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
// Keyboard use: what opens on a click opens on Enter or Space too; Ctrl+Enter rolls or accepts the waiting tray.
function keyClickable(n) { n.tabIndex = 0; n.setAttribute("role", "button"); n.dataset.keyClick = "1"; return n; }
document.addEventListener("keydown", (ev) => {
  if ((ev.key === "Enter" || ev.key === " ") && ev.target.dataset?.keyClick) { ev.preventDefault(); ev.target.click(); return; }
  if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey) && trays.size) {
    const b = [...trays.values()].pop().querySelector("button:not(:disabled)");
    if (b) { ev.preventDefault(); b.click(); }
  }
});
function say(text) {
  text = text.trim();
  if (!text) return false;
  const ask = askingAboutReading && [...trays.values()].some((t) => t.classList.contains("reading"));
  return send({ t: "say", text, ...(ask ? { ask: true } : {}) });
}
function sayInput() { if (say(input.value)) input.value = ""; }

$("#composer").addEventListener("submit", (ev) => { ev.preventDefault(); sayInput(); });
input.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); sayInput(); }
});
keyClickable($("#stage"));
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
  // The server starts a fresh conversation first if the last session was ended (cheaper turns, nothing lost).
  if (!lastStart || /session-end/.test(lastStart.textContent)) { send({ t: "begin" }); return; }
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
// ------------------------------------------------------------------ the Settings dialog
// The campaign's settings the player may change here; the server accepts only these keys and values.
async function openSettings() {
  let data;
  try { data = await (await fetch("/api/settings")).json(); }
  catch { flashConn(); add(el("div", "note", "The settings couldn't be loaded. Is the table still running?")); return; }
  const key = (v) => JSON.stringify(v ?? null);
  const d = el("dialog", "rw-dialog rw-settings");
  d.innerHTML = `<form method="dialog">
      <h2>Settings</h2><div class="rw-rule">❦</div>
      ${data.fields.map((f, i) => `<label class="rw-field">
          <span class="rw-flabel" title="${esc(f.help)}">${esc(f.label)}</span>
          <select data-i="${i}">${f.options.map((o) => `<option value="${esc(key(o.value))}"${key(o.value) === key(f.value) ? " selected" : ""}>${esc(o.label)}</option>`).join("")}</select>
          <small class="rw-hint"></small></label>`).join("")}
      <p class="rw-note">Saved for this campaign. A new model takes over from your next message.</p>
      <div class="rw-actions">
        <button value="cancel" class="ghost">Cancel</button>
        <button value="ok" id="settings-save" disabled>Save</button>
      </div>
    </form>`;
  const selects = [...d.querySelectorAll("select")];
  const hint = (s) => {
    const f = data.fields[s.dataset.i];
    // what the setting is, then what the chosen value does: visible, not only in a hover tooltip
    s.parentElement.querySelector(".rw-hint").textContent = [f.help, f.options[s.selectedIndex].hint].filter(Boolean).join(" ");
  };
  const changed = () => selects.filter((s) => s.value !== key(data.fields[s.dataset.i].value));
  selects.forEach((s) => {
    hint(s);
    s.addEventListener("change", () => { hint(s); d.querySelector("#settings-save").disabled = !changed().length; });
  });
  d.addEventListener("click", (ev) => { if (ev.target === d) d.close("cancel"); });
  d.addEventListener("close", () => {
    if (d.returnValue === "ok") {
      const values = Object.fromEntries(changed().map((s) => [data.fields[s.dataset.i].key, JSON.parse(s.value)]));
      if (Object.keys(values).length) send({ t: "settings", values });
    }
    d.remove();
  });
  document.body.appendChild(d);
  d.showModal();
}
$("#btn-settings").onclick = openSettings;
connect();
