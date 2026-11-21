"""Region maps laid out during play: when the tale reaches country without a close map (the Shire, the
Lone-lands, Fornost…), Ringwraith describes its geography in miles and it is drawn in the same ink style
as Bree-land.

A region lives in the campaign (`.ringwraith/regions/<id>.yaml`), anchored on a place that is already on
its parent map (Eriador by default). Coordinates are miles from that anchor: x east, y south.

**Land maps** are for tales set beyond the Eriador map (Dunland, Rohan, Wilderland, Lórien…). Give
`parent: none` and `scale: land`: the map stands on its own, may be hundreds of miles across, and its anchor
is simply its first place. Mark the journey lands on it so journeys can be counted there:

    land: wild                                         # the land type of anything not marked otherwise
    lands:     [{type: border|wild|dark, area: [[x, y], ...]}]
    mountains: [{name: the Misty Mountains, area: [[x, y], ...]}]   # impassable to journeys
    # roads work as on any region: a journey on them gains (1d) at its events

Regions can then nest inside a land map (`parent: <land map id>`, anchored on one of its places).

    title: The Weather Hills
    anchor: Weathertop                     # a known place; it sits at [0, 0]
    places:  [{name: Weathertop, at: [0, 0], kind: ruin}, ...]   kind: town, village, hamlet, ruin, tower, stone
    roads:   [{name: the Great East Road, points: [[-12, 3], [0, 2], [12, 4]], width: main}]   main | lane
    rivers / streams: [{name: ..., points: [[x, y], ...]}]
    forests / marshes / downs / lakes: [{name: ..., area: [[x, y], ...], label_at: [x, y]}]   forests: kind mixed | conifer | deciduous
    hills:   [{name: ..., center: [x, y], radius: [rx, ry]}]
    copses:  [[x, y], ...]
    pointers: [{text: "to Bree, 90 miles", at: [x, y], side: west}]   west | east | north | south

Everything drawn is visible to the player (the names are baked into the picture): put only what the hero
can see or would know there. Secrets stay off the map.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import campaign as cp
from . import fileio

LIST_KEYS = ("places", "roads", "rivers", "streams", "forests", "marshes", "downs", "lakes", "hills", "copses",
             "pointers", "mountains", "lands")
LAND_TYPES = ("border", "wild", "dark")
NO_PARENT = (None, "", "none", "None")
TARGET_WIDTH_PX = 2400
PLACE_KINDS = ("town", "village", "hamlet", "ruin", "tower", "stone")


class RegionError(ValueError):
    pass


def _dir(slug=None, root=None) -> Path:
    d = cp.private_dir(slug, root) / "regions"
    d.mkdir(exist_ok=True)
    return d


def slug_of(text: str) -> str:
    from .vault import slugify
    return slugify(text)


def exists(region_id: str, slug=None, root=None) -> bool:
    try:
        return (_dir(slug, root) / f"{region_id}.yaml").exists()
    except cp.CampaignError:
        return False


def load(region_id: str, slug=None, root=None) -> dict:
    f = _dir(slug, root) / f"{region_id}.yaml"
    if not f.exists():
        raise RegionError(f"no region {region_id!r}")
    return yaml.safe_load(f.read_text(encoding="utf-8"))


def all_regions(slug=None, root=None) -> list[dict]:
    try:
        d = _dir(slug, root)
    except cp.CampaignError:
        return []
    return [yaml.safe_load(f.read_text(encoding="utf-8")) for f in sorted(d.glob("*.yaml"))]


def _points(feature: dict, key: str) -> list:
    pts = feature.get(key) or []
    if not isinstance(pts, list) or not all(isinstance(p, (list, tuple)) and len(p) == 2 for p in pts):
        raise RegionError(f"{feature.get('name') or 'a feature'}: {key} must be a list of [x, y] miles")
    return [[float(p[0]), float(p[1])] for p in pts]


def build(spec: dict) -> dict:
    """Validate a region spec and complete it: id, parent, bounds and scale."""
    title = (spec.get("title") or "").strip()
    anchor = (spec.get("anchor") or "").strip()
    if not title or not anchor:
        raise RegionError("a region needs a title and an anchor place")
    parent = spec.get("parent", "eriador")
    if spec.get("scale") == "local" and parent in NO_PARENT:
        raise RegionError("a local region needs a parent map; for country beyond Eriador use scale: land")
    land_scale = spec.get("scale") == "land" or parent in NO_PARENT
    g: dict = {"id": spec.get("id") or slug_of(title), "title": title,
               "parent": None if parent in NO_PARENT else parent, "anchor": {"place": anchor, "at": [0, 0]}}
    if land_scale:
        g["scale"] = "land"
    if spec.get("land"):
        if spec["land"] not in LAND_TYPES:
            raise RegionError(f"land is one of {', '.join(LAND_TYPES)}")
        g["land"] = spec["land"]
    for key in LIST_KEYS:
        g[key] = list(spec.get(key) or [])
    for pl in g["places"]:
        if not pl.get("name") or "at" not in pl:
            raise RegionError("every place needs a name and at: [x, y]")
        pl["at"] = _points({"name": pl["name"], "p": [pl["at"]]}, "p")[0]
        pl.setdefault("kind", "village")
        if pl["kind"] not in PLACE_KINDS:
            raise RegionError(f"place kind is one of {', '.join(PLACE_KINDS)}")
    for key in ("roads", "rivers", "streams"):
        for f in g[key]:
            f["points"] = _points(f, "points")
            if len(f["points"]) < 2:
                raise RegionError(f"{f.get('name') or key}: needs at least 2 points")
            f.setdefault("width", "lane") if key == "roads" else None
    for f in g["lands"]:
        if f.get("type") not in LAND_TYPES:
            raise RegionError(f"lands: type is one of {', '.join(LAND_TYPES)}")
    for key in ("forests", "marshes", "downs", "lakes", "mountains", "lands"):
        for f in g[key]:
            f["area"] = _points(f, "area")
            if len(f["area"]) < 3:
                raise RegionError(f"{f.get('name') or key}: an area needs at least 3 points")
            if f.get("label_at"):
                f["label_at"] = _points({"p": [f["label_at"]]}, "p")[0]
    for h in g["hills"]:
        if "center" not in h or "radius" not in h:
            raise RegionError("a hill needs center and radius: [rx, ry]")
    g["copses"] = [[float(c[0]), float(c[1])] for c in g["copses"]]
    for p in g["pointers"]:
        if p.get("side", "east") not in ("west", "east", "north", "south"):
            raise RegionError("pointer side is west, east, north or south")
    # the frame: everything that matters, with a margin, at a sensible size
    xs, ys = [0.0], [0.0]
    for pl in g["places"]:
        xs.append(pl["at"][0]); ys.append(pl["at"][1])
    for key in ("forests", "marshes", "downs", "lakes", "mountains"):
        for f in g[key]:
            xs += [p[0] for p in f["area"]]; ys += [p[1] for p in f["area"]]
    for h in g["hills"]:
        xs += [h["center"][0] - h["radius"][0], h["center"][0] + h["radius"][0]]
        ys += [h["center"][1] - h["radius"][1], h["center"][1] + h["radius"][1]]
    for c in g["copses"]:
        xs.append(c[0]); ys.append(c[1])
    for ptr in g["pointers"]:           # pointers sit at the edges: they say where the frame ends
        xs.append(ptr["at"][0]); ys.append(ptr["at"][1])
    if spec.get("bounds"):
        x0, y0, x1, y1 = map(float, spec["bounds"])
    else:
        pad = 10 if land_scale else 1.5      # room for labels at the edge
        x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w, h = max(x1 - x0, 12), max(y1 - y0, 8)
        w, h = (min(w, 600), min(h, 450)) if land_scale else (min(w, 45), min(h, 32))
        x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    g["bounds"] = [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]
    low = 3 if land_scale else 50          # a land map may be a few pixels to the mile
    g["px_per_mile"] = round(min(140, max(low, TARGET_WIDTH_PX / (x1 - x0))), 1)
    return g


def save(g: dict, slug=None, root=None) -> Path:
    f = _dir(slug, root) / f"{g['id']}.yaml"
    fileio.atomic_write(f, yaml.safe_dump(g, sort_keys=False, allow_unicode=True))
    return f


@fileio.with_lock
def create(spec: dict, slug=None, root=None) -> dict:
    """Validate, check the anchor is on the parent map, save and draw a region. Returns the region."""
    from . import geo, mapdraw
    g = build(spec)
    data = geo.load(slug, root)
    anchor = g["anchor"]["place"]
    if g["parent"]:                       # a land map (no parent) stands on its own
        parent = geo.map_def(g["parent"])
        if anchor not in parent["places_px"] and data["places"].get(anchor, {}).get("map") != parent["id"]:
            raise RegionError(f"the anchor {anchor!r} must be a place on {parent['title']}; add it there first")
    elif not any(pl["name"] == anchor for pl in g["places"]):
        raise RegionError(f"a land map's anchor {anchor!r} must be one of its places (at [0, 0])")
    save(g, slug, root)
    out = cp.campaign_dir(slug, root) / "90 Assets" / "maps" / f"{g['id']}.jpg"
    mapdraw.render_geo(g, out)
    return g
