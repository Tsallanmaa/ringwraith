"""Side-panel data and player edits for the Ringwraith Table.

- `tale()` (from `ringwraith.tale`): the current mission and journey, the threads and the Compass.
- `adjust()`: the player changes a tracker on the hero sheet (Hope, Endurance, Shadow, Fatigue,
  Fellowship, Wounded). The change is written to the hero note at once and remembered, so Ringwraith
  hears about it with the player's next message.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .. import campaign as cp
from .. import vault
from .. import fileio
from ..tale import _LINK, _plain, compass, tale, threads  # noqa: F401 (the panels read the tale)

# key -> (path in the hero frontmatter, path of its maximum or None)
TRACKERS: dict[str, tuple[str, str | None]] = {
    "endurance": ("endurance.current", "endurance.max"),
    "hope": ("hope.current", "hope.max"),
    "shadow": ("shadow.points", None),
    "fatigue": ("fatigue", None),
    "fellowship": ("fellowship.current", "fellowship.rating"),
}
TOGGLES = {"wounded": "conditions.wounded"}
LABELS = {"endurance": "Endurance", "hope": "Hope", "shadow": "Shadow", "fatigue": "Fatigue",
          "fellowship": "Fellowship points", "wounded": "Wounded"}


class AdjustError(ValueError):
    pass


def _hero() -> Path:
    h = vault.hero_note()
    if not h:
        raise AdjustError("there is no hero sheet yet")
    return h


@fileio.with_lock
def adjust(key: str, delta: int | None = None, value: Any = None) -> dict | None:
    """Change one tracker on the hero sheet. Returns {key, label, old, new}, or None if nothing changed."""
    path = _hero()
    fm, body = vault.read_note(path)
    if key in TOGGLES:
        dotted = TOGGLES[key]
        old = bool(vault.get_path(fm, dotted))
        new = (not old) if value is None else bool(value)
        vault.set_path(fm, dotted, new)
        vault.write_note(path, fm, body)
        return {"key": key, "label": LABELS[key], "old": "on" if old else "off", "new": "on" if new else "off"}
    if key not in TRACKERS:
        raise AdjustError(f"unknown tracker: {key}")
    dotted, max_path = TRACKERS[key]
    old = int(vault.get_path(fm, dotted) or 0)
    new = old + int(delta) if delta is not None else int(value)
    top = vault.get_path(fm, max_path) if max_path else None
    new = max(0, min(int(top), new) if top is not None else new)
    if new == old:
        return None
    vault.set_path(fm, dotted, new)
    vault.write_note(path, fm, body)
    return {"key": key, "label": LABELS[key], "old": old, "new": new}


# ---------------------------------------------------------------- what a hero's traits do (for tooltips)
_CITE = re.compile(r"\s*\[[a-z0-9-]+ p\.[^\]]*\]")


def _lore_dir() -> Path | None:
    from .. import config as cfg
    d = cfg.load().lore / "atoms"
    return d if d.is_dir() else None


def _slug(text: str) -> str:
    return vault.slugify(text)


def _first_para(text: str, limit: int = 320) -> str:
    for para in re.split(r"\n\s*\n", text.strip()):
        para = _CITE.sub("", para).strip()
        if para and not para.startswith(("#", "|", "```", "---")):
            para = re.sub(r"\*\*|`", "", para).replace("\n", " ")
            return para if len(para) <= limit else para[:limit].rsplit(" ", 1)[0] + " …"
    return ""


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^##+ {heading}[^\n]*\n(.*?)(?=^##+ |\Z)", text, re.S | re.M | re.I)
    return m.group(1) if m else ""


def trait(kind: str, name: str) -> str:
    """A short description of a Virtue, Reward, Calling or Shadow Path from the lore library ('' if unknown)."""
    base = _lore_dir()
    if not base or not name:
        return ""
    plain = re.sub(r"\s*\(.*?\)", "", name).strip()          # "Prowess (STRENGTH TN -1)" -> "Prowess"
    for slug in (_slug(plain), _slug(name)):
        f = base / kind / f"{slug}.md"
        if f.exists():
            text = f.read_text(encoding="utf-8")
            return _first_para(_section(text, "Effect") or _section(text, "Rules") or text.split("\n# ", 1)[-1]
                               .split("\n", 1)[-1])
    if kind == "callings":                                   # a shared calling lives in shared-callings.md
        f = base / "callings" / "shared-callings.md"
        if f.exists():                                       # its row in the table: focus, skills, path
            for line in f.read_text(encoding="utf-8").splitlines():
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) >= 4 and cells[0].lower() == plain.split()[0].lower():
                    return (f"A Shared Calling. Disposition Focus {cells[1]}: the Band is Inspired when testing it. "
                            f"Favoured Skills from {cells[2]}. Shadow Path: {cells[3]}.")
    return ""


def blessing(culture: str) -> dict | None:
    base = _lore_dir()
    f = base / "cultures" / f"{_slug(culture)}.md" if base and culture else None
    if not f or not f.exists():
        return None
    text = f.read_text(encoding="utf-8")
    m = re.search(r"^##+ Cultural Blessing:?\s*(.+)$", text, re.M | re.I)
    if not m:
        return None
    return {"name": m.group(1).strip(), "text": _first_para(_section(text, "Cultural Blessing"))}


def hero_traits(fm: dict) -> dict:
    """The hero's Blessing, Calling, Shadow Path, Virtues and Rewards, each with what it does."""
    out = {"blessing": blessing(str(fm.get("culture") or "")),
           "calling": {"name": fm.get("calling"), "text": trait("callings", str(fm.get("calling") or ""))}
           if fm.get("calling") else None,
           "shadow_path": {"name": fm.get("shadow_path"), "text": trait("shadow-paths", str(fm.get("shadow_path") or ""))}
           if fm.get("shadow_path") else None,
           "virtues": [{"name": v, "text": trait("virtues", str(v))} for v in fm.get("virtues") or []],
           "rewards": [{"name": r, "text": trait("rewards", str(r))} for r in fm.get("rewards") or []],
           "features": [{"name": f, "text": "Invoke it when it fits what the hero does: the roll is Inspired "
                         "(Hope gives (2d))."} for f in fm.get("distinctive_features") or []]}
    return out


def describe(change: dict) -> str:
    return f"{change['label']} {change['old']} → {change['new']}"
