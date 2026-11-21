"""What the table's panels and map view show, built from the vault: the hero, Band, Allies and world
(`sheet`), the maps with everyone's whereabouts (`geo_view`), and the stage's title (`current_scene`).

They only read. A note that can't be read (half-saved by Obsidian, or broken by a bad edit) is left out and
logged, so one bad file never stops the table from connecting.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .. import campaign as cp
from .. import clock, geo, vault

log = logging.getLogger("ringwraith.table")


def _fm(path: Path) -> dict:
    """A note's frontmatter, or {} if it can't be read right now."""
    try:
        return vault.read_note(path)[0] or {}
    except Exception as e:  # noqa: BLE001
        log.warning("couldn't read %s: %s", path.name, e)
        return {}


def sheet() -> dict:
    """What the side panels show: hero, Band, Allies and the public part of the state."""
    d = cp.campaign_dir()
    settings = cp.load_settings()
    out: dict[str, Any] = {"campaign": settings.get("campaign", {}), "slug": d.name,
                           "tn_base": cp.tn_base(settings), "hero": None,
                           "band": None, "allies": [], "state": {}}
    h = vault.hero_note()
    if h:
        out["hero"] = _fm(h) or None
        try:
            from . import panels  # noqa: F811
            out["hero"]["traits"] = panels.hero_traits(out["hero"])
        except Exception:  # noqa: BLE001 - tooltips are a nicety
            pass
    band = d / "20 Fellowship" / "Band.md"
    if band.exists():
        out["band"] = _fm(band) or None
    for f in sorted((d / vault.NOTE_TYPES["ally"]).glob("*.md")):
        fm = _fm(f)
        if not fm:
            continue
        out["allies"].append({k: fm.get(k) for k in
                              ("name", "gift", "second_gift", "gift_wasted", "quirk", "title", "injury", "fatigue",
                               "status", "hardened", "image")})
    st = d / ".ringwraith" / "state.md"
    if st.exists():
        fm = _fm(st)
        out["state"] = {k: fm.get(k) for k in ("date", "location", "eye_awareness", "hunt_threshold", "phase",
                                               "day", "time", "deadlines", "counters", "mission", "journey")}
    from . import panels  # noqa: F811
    try:
        out["tale"] = panels.tale(out["state"])
    except Exception:  # noqa: BLE001 - the side panels must render even if a note is malformed
        out["tale"] = {}
    return json.loads(json.dumps(out, default=str))


def _portrait(name: str) -> str | None:
    """A character's portrait URL from their note's `image:` frontmatter, if any."""
    try:
        fm, _ = vault.read_note(vault.resolve_note(name))
    except Exception:  # noqa: BLE001 - unknown, ambiguous or malformed note: no portrait
        return None
    img = str(fm.get("image") or "").strip("[]")
    return "/assets/" + img.removeprefix("90 Assets/") if img.startswith("90 Assets/") else None


def geo_view() -> dict:
    """Maps, places, travel log and tokens (who is where, with portraits) for the map view."""
    snap = geo.snapshot()
    hero_name = vault.hero_name()
    ally_dir = cp.campaign_dir() / vault.NOTE_TYPES["ally"]
    allies = {f.stem for f in ally_dir.glob("*.md")} if ally_dir.is_dir() else set()
    data = geo.load()
    tokens = []
    for who, w in snap["whereabouts"].items():
        try:
            pname, pmap, pxy = geo.find(w.get("place", ""), data)
        except geo.GeoError:
            continue
        kind = "hero" if who == hero_name else "ally" if who in allies else "npc"
        tokens.append({"name": who, "kind": kind, "place": pname, "map": pmap, "at": pxy, "image": _portrait(who)})
    snap["tokens"] = tokens
    snap["hero"] = hero_name
    snap["day"] = clock.today(clock.state()[1])
    _only_the_tales_maps(snap)
    return json.loads(json.dumps(snap, default=str))


def _only_the_tales_maps(snap: dict) -> None:
    """Keep the maps the tale has touched. Maps come in trees (a base or land map and the regions and sites
    inside it). A tree is shown when the campaign has something on it: a place of its own, a move, someone
    there, or a planned journey; or when nothing has been placed anywhere yet. Maps whose picture hasn't been
    made yet are left out, so the view never opens on a missing image."""
    maps = snap["maps"]
    assets = cp.campaign_dir() / "90 Assets"
    for mid in [m for m, d in maps.items()
                if str(d.get("image", "")).startswith("/assets/")
                and not (assets / d["image"].removeprefix("/assets/")).exists()]:
        maps.pop(mid)

    def root(mid: str) -> str:
        seen = set()
        while mid in maps and maps[mid].get("parent") and mid not in seen:
            seen.add(mid)
            mid = maps[mid]["parent"]
        return mid
    used = {t["map"] for t in snap["tokens"]} | {lg.get("map") for lg in snap.get("legs", [])}
    used |= {p["map"] for p in snap.get("places", []) if not p.get("builtin")}
    if snap.get("plan"):
        used.add(snap["plan"].get("map", "eriador"))
    roots = {root(m) for m in used if m in maps}
    if roots:
        for mid in [m for m in maps if root(m) not in roots]:
            maps.pop(mid)
    snap["places"] = [p for p in snap.get("places", []) if p["map"] in maps]
    snap["legs"] = [lg for lg in snap.get("legs", []) if lg.get("map") in maps]
    snap["tokens"] = [t for t in snap["tokens"] if t["map"] in maps]
    if snap.get("plan") and snap["plan"].get("map", "eriador") not in maps:
        snap["plan"] = None
    if snap.get("grid") and "eriador" not in maps:
        snap["grid"] = None


def current_scene() -> str:
    """The title the stage shows now (set by set_scene)."""
    try:
        return json.loads((cp.private_dir() / "table-scene.json").read_text(encoding="utf-8")).get("title", "")
    except (OSError, ValueError):
        return ""
