"""The tale as the vault records it: open and resolved threads, the Compass, and the mission and journey
under way. Read by the table's Tale panel and the Obsidian Home dashboard.
"""

from __future__ import annotations

import re
from typing import Any

from . import campaign as cp
from . import vault

_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
_BOLD = re.compile(r"^\*\*(.+?)\*\*[:.]?\s*(.*)$")
_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def _plain(text: str) -> str:
    """Wiki-links become their names; the rest of the Markdown is left for the browser to render."""
    return _LINK.sub(lambda m: m.group(2) or m.group(1), text).strip()


def _sections(body: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current = None
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            out[current] = []
        elif current and (m := _BULLET.match(line)):
            out[current].append(m.group(1).strip())
    return out


def threads() -> dict:
    f = cp.campaign_dir() / "10 Campaign" / "Threads.md"
    if not f.exists():
        return {"open": [], "resolved": []}
    secs = _sections(vault.read_note(f)[1])

    def items(name: str) -> list[dict]:
        res = []
        for b in secs.get(name, []):
            m = _BOLD.match(b)
            title, text = (m.group(1), m.group(2)) if m else (b, "")
            res.append({"title": _plain(title).rstrip(".:"), "text": _plain(text)})
        return res
    return {"open": items("Open"), "resolved": items("Resolved")}


def compass() -> dict:
    f = cp.campaign_dir() / "10 Campaign" / "Compass.md"
    if not f.exists():
        return {}
    fm, body = vault.read_note(f)
    secs = {k: [_plain(x) for x in v] for k, v in _sections(body).items() if v}
    return {"surprise": fm.get("surprise"), "pacing": fm.get("pacing") or [], "cutaways": cutaways_on(fm),
            "sections": secs}


def _active(kind: str, ref: str) -> dict | None:
    """The mission or journey named in the state, or else the newest one still underway."""
    folder = cp.campaign_dir() / vault.NOTE_TYPES[kind]
    path = None
    if ref:
        try:
            path = vault.resolve_note(_LINK.sub(lambda m: m.group(1), ref))
        except cp.CampaignError:
            path = None
    if path is None and folder.is_dir():
        live = [p for p in folder.glob("*.md") if vault.read_note(p)[0].get("status") in ("underway", "planned")]
        path = max(live, key=lambda p: p.stat().st_mtime) if live else None
    if path is None:
        return None
    fm = vault.read_note(path)[0]
    keep = {"mission": ("name", "status", "objective", "patron", "roster", "readiness", "size", "burden"),
            "journey": ("name", "status", "from", "to", "season", "route", "hexes", "days", "fatigue_gained")}[kind]
    out = {k: fm.get(k) for k in keep if fm.get(k) not in (None, "", [])}
    for k in ("patron", "from", "to"):
        if isinstance(out.get(k), str):
            out[k] = _plain(out[k])
    for k in ("roster", "route"):
        if isinstance(out.get(k), list):
            out[k] = [_plain(str(x)) for x in out[k]]
    out.setdefault("name", path.stem)
    return out


def tale(state: dict | None = None) -> dict:
    state = state or {}
    out: dict[str, Any] = {"threads": threads(), "compass": compass(), "mission": None, "journey": None}
    for kind in ("mission", "journey"):
        try:
            out[kind] = _active(kind, str(state.get(kind) or ""))
        except Exception:  # noqa: BLE001 - a malformed note must not break the panels
            out[kind] = None
    try:
        from . import geo
        plan = geo.load().get("plan")
        out["plan"] = {k: plan.get(k) for k in ("from", "to", "hexes", "miles")} if plan else None
    except Exception:  # noqa: BLE001
        out["plan"] = None
    return out


def cutaways_on(fm: dict) -> bool:
    """The Compass's `cutaways` setting: true, on or yes turns cutaways on; anything else (the default) is off."""
    v = fm.get("cutaways")
    return v is True or str(v).strip().lower() in ("on", "yes", "true")
