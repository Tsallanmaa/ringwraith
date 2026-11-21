"""The chronicle: a session as it was played at the web table, written into its Obsidian session note.

Built straight from `.ringwraith/table-log.jsonl`, so nothing is retold or lost:
- every scene as a heading with its painting;
- the narration in full (bookkeeping asides and folded recaps left out);
- the player's moves;
- portraits and other images where they first appeared;
- rolls and oracle answers as Obsidian callouts.

A play session starts at a player message `/session-start` (or the start of the log).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import campaign as cp
from . import vault
from . import fileio

SECTION = "## As it was played"
ICONS = {"{success}": "✦", "{eye}": "◉", "{gandalf}": "ᚷ"}
FACE = {"eye": "◉ Eye", "gandalf": "ᚷ Rune"}


def load_events(slug: str | None = None, root: Path | None = None) -> list[dict]:
    f = cp.private_dir(slug, root) / "table-log.jsonl"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def sessions(events: list[dict]) -> list[tuple[int, int]]:
    """(start, end) index ranges of the play sessions in the log."""
    starts = [i for i, e in enumerate(events)
              if e.get("t") == "player" and e.get("text", "").strip().startswith("/session-start")]
    if not starts or starts[0] != 0:
        starts = [0] + starts
    return [(s, (starts[k + 1] if k + 1 < len(starts) else len(events))) for k, s in enumerate(starts)]


def _icons(text: str) -> str:
    for k, v in ICONS.items():
        text = text.replace(k, v)
    return text


def _asset(url: str) -> str:
    """'/assets/scenes/x.png' -> '90 Assets/scenes/x.png' (the vault path Obsidian embeds)."""
    return "90 Assets/" + url.removeprefix("/assets/")


def _callout(kind: str, title: str, body: str = "", folded: bool = False) -> str:
    lines = [f"> [!{kind}]{'-' if folded else ''} {title}".rstrip()]
    for line in body.strip().splitlines():
        lines.append(f"> {line}" if line.strip() else ">")
    return "\n".join(lines)


def _narration(text: str) -> str:
    """Story text as-is; `> OOC:` blockquotes become Loremaster callouts, `> CUTAWAY:` ones (a scene elsewhere,
    which the hero doesn't see) cutaway callouts."""
    out, block = [], []
    kind = None

    def flush_block():
        if not block:
            return
        first = re.sub(r"^\s*(OOC|CUTAWAY):\s*", "", block[0])
        body = "\n".join([first, *block[1:]]).strip()
        if kind == "cutaway":
            out.append(_callout("cutaway", "Elsewhere…", body))
        else:
            out.append(_callout("loremaster", "Loremaster", body, folded=True))
        block.clear()

    for line in text.splitlines():
        m = re.match(r"^\s*>\s?(.*)$", line)
        opener = re.match(r"^\s*(OOC|CUTAWAY):", m.group(1)) if m else None
        if m and (kind or opener):
            if opener and kind and block:          # a new box starts right after the last
                flush_block()
            if opener:
                kind = "cutaway" if opener.group(1) == "CUTAWAY" else "ooc"
            block.append(m.group(1))
            continue
        if kind:
            flush_block()
            kind = None
        out.append(line)
    flush_block()
    # headings inside narration become small subheadings, so they never break the note's own sections
    text = "\n".join(re.sub(r"^#{1,4}\s+", "#### ", line) for line in out)
    return _icons(text.strip())


def _face(f: str) -> str:
    return FACE.get(str(f), str(f))


def _roll(e: dict) -> str:
    ok = e.get("outcome") == "success"
    degree = f" ({e['degree']})" if ok and e.get("degree") not in (None, "", "success") else ""
    feat = " / ".join(_face(f) for f in e.get("feat", []))
    succ = " ".join("✦6" if v == 6 else str(v) for v in e.get("success", [])) or "–"
    extra = [x for x in ("Hope spent" if e.get("hope") else "", "physical dice" if e.get("manual") else "") if x]
    title = (f"{e.get('who')}: {e.get('what')}, TN {e.get('tn')}: "
             f"{'Success' if ok else 'Failure'}{degree}, total {e.get('total')}")
    body = f"Feat {feat} · Success {succ}" + (f" · {', '.join(extra)}" if extra else "")
    return _callout("success" if ok else "failure", _icons(title), _icons(body))


def render(events: list[dict], start: int = 0, end: int | None = None) -> str:
    events = events[start:end]
    images = {e["job"]: e for e in events if e.get("t") == "image" and e.get("job")}
    used: set[str] = set()
    parts: list[str] = []
    summary_at: int | None = None    # a mechanics-only reply; the story told after it goes above it
    retell = False
    for e in events:
        t = e.get("t")
        if t in ("player", "turn_end"):
            summary_at, retell = None, False
        if t == "text_start":
            retell = bool(e.get("retell"))
        if t == "player":
            text = e.get("text", "").strip()
            if not text or text.startswith("/") or (text.startswith("(") and text.endswith(")")):
                continue      # slash commands and table nudges aren't part of the tale
            parts.append(_callout("player", "You", _icons(text)))
        elif t == "narration":
            if e.get("aside") or e.get("recap"):
                continue
            if e.get("summary"):
                summary_at = len(parts)
            if retell and summary_at is not None:
                parts.insert(summary_at, _narration(e.get("text", "")))
                summary_at += 1
                continue
            parts.append(_narration(e.get("text", "")))
        elif t == "scene":
            parts.append(f"### {e.get('title', '')}")
            img = images.get(e.get("job") or "")
            if img:
                parts.append(f"![[{_asset(img['url'])}]]")
                used.add(img["job"])
        elif t == "image" and e.get("job") not in used:
            used.add(e.get("job"))
            if e.get("preset") == "scene":
                continue      # a scene painting whose scene event isn't in this session
            if e.get("preset") == "map":
                parts.append(f"![[{_asset(e['url'])}|560]]\n*The road, day {e.get('day', '')}: {e.get('subject', '')}*")
                continue
            name = Path(e.get("note") or "").stem
            parts.append(f"![[{_asset(e['url'])}|220]]" + (f"\n*{name}*" if name else ""))
        elif t == "fight_end":
            parts.append(_callout("battle" if e.get("kind") == "battle" else "fight", e.get("title") or "The fight",
                                  _icons(e.get("outcome") or "")))
        elif t == "journey_mark":       # a waymark on the road: where the next moment of the journey happens
            parts.append(f"*— Day {e.get('day', '')}{', ' + e['at'] if e.get('at') else ''}: {_icons(e.get('title') or '')} —*")
        elif t == "journey_end":
            f = e.get("fatigue") or {}
            cost = ", ".join(x for x in (f"hero fatigue +{f['hero']}" if f.get("hero") else "",
                                         f"Band fatigue +{f['band']}" if f.get("band") else "") if x)
            parts.append(_callout("journey", (e.get("title") or "The journey") + (
                " (turned back)" if e.get("status") == "abandoned" else ""),
                f"{e.get('days', '?')} days on the road{'; ' + cost if cost else ''}. {_icons(e.get('outcome') or '')}".strip()))
        elif t == "roll_result":
            parts.append(_roll(e))
        elif t == "oracle":
            if e.get("kind") == "telling":
                parts.append(_callout("oracle", _icons(f"The Telling ({e.get('chance')}): {e.get('question')}"),
                                      _icons(f"{_face(e.get('feat'))}: {e.get('answer')}")))
            else:
                parts.append(_callout("oracle", _icons(f"Lore: {e.get('question') or 'table'}"),
                                      _icons(str(e.get("answer", "")))))
    return "\n\n".join(p for p in parts if p.strip()) + "\n"


@fileio.with_lock
def write(note: Path, text: str, heading: str = SECTION, intro: str | None = None,
          before: str | None = None) -> None:
    """Put text under a `## heading` in the note, replacing that section if it's there. A new section
    goes before the heading `before` if given (and present), else at the end."""
    fm, body = vault.read_note(note)
    if intro is None:
        intro = "*Written from the Ringwraith Table log; regenerated by `ringwraith chronicle`.*" if heading == SECTION else ""
    section = f"{heading}\n{intro + chr(10) if intro else ''}\n{text}"
    m = re.search(rf"^{re.escape(heading)}\s*$", body, re.M)
    if not m and before:
        b = re.search(rf"^{re.escape(before)}\s*$", body, re.M)
        if b:
            body = body[:b.start()] + section.rstrip() + "\n\n" + body[b.start():]
            vault.write_note(note, fm, body)
            return
    if m:
        nxt = re.search(r"^## ", body[m.end():], re.M)
        end = m.end() + nxt.start() if nxt else len(body)
        body = body[:m.start()] + section + ("\n" + body[end:] if nxt else "")
    else:
        body = body.rstrip() + "\n\n" + section
    vault.write_note(note, fm, body)
