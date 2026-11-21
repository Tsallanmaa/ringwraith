"""The maps: the base maps from lore/maps, the campaign's regions and site plans, and projecting points
between nested maps."""

from __future__ import annotations

import datetime as dt
import functools
import json
import math
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any
import yaml
from .. import campaign as cp
from .. import config as cfg
from .. import fileio
from .common import GeoError, REGION_MARGIN, _cache, _stamp  # noqa: F401
from . import store


def _is_built_region(g: Any) -> bool:
    """A region file Ringwraith has written but `map region` hasn't built yet is only a spec (miles, no
    bounds): it isn't a map until it is built."""
    return (isinstance(g, dict) and bool(g.get("id")) and "bounds" in g and "px_per_mile" in g
            and isinstance(g.get("anchor"), dict) and "at" in g["anchor"])


def maps() -> dict[str, dict]:
    """All map definitions: the base maps, plus the active campaign's regions and site plans.

    Read once and kept until one of the campaign's map files changes: the map code asks for this hundreds
    of times while drawing one picture. A broken region or site file is left out (and logged), so one bad
    file never takes every map down."""
    out = dict(_base_maps())
    try:
        pdir = cp.private_dir()
    except Exception:  # noqa: BLE001 - no campaign: base maps only
        return out
    files = [pdir / "geo.yaml", *sorted((pdir / "regions").glob("*.yaml")), *sorted((pdir / "sites").glob("*.yaml"))]
    key = _stamp(files)
    hit = _cache.get("maps")
    if hit and hit[0] == key:
        return dict(out, **hit[1])
    built = _campaign_maps(pdir)
    _cache["maps"] = (key, built)
    return dict(out, **built)


def _campaign_maps(pdir: Path) -> dict[str, dict]:
    import logging
    from .. import sites
    log = logging.getLogger("ringwraith.geo")
    out: dict[str, dict] = {}
    camp = store.load()
    for f in sorted((pdir / "regions").glob("*.yaml")):    # regions Ringwraith laid out in this campaign
        try:
            g = yaml.safe_load(f.read_text(encoding="utf-8"))
            if _is_built_region(g):
                out[g["id"]] = prepare_region(g)
        except Exception as e:  # noqa: BLE001
            log.warning("skipping region %s: %s", f.name, e)
    for f in sorted((pdir / "sites").glob("*.yaml")):
        try:
            site = yaml.safe_load(f.read_text(encoding="utf-8"))
            place = camp["places"].get(site["place"])
            if not place:
                continue
            lay = sites.layout(site)
            out[f"site-{site['id']}"] = {
                "id": f"site-{site['id']}", "title": site["title"], "size": lay["size"], "site": site["id"],
                "parent": place["map"], "anchor": {"place": site["place"]},
                "anchor_px": [lay["size"][0] / 2, lay["size"][1] / 2],
                "miles_per_px": 5 / 5280 / sites.CELL,
                "places_px": {sites.room_place(site, r): lay["centres"][r["id"]] for r in site["rooms"]},
                "explored": [sites.room_place(site, r) for r in site["rooms"] if r.get("explored")],
            }
        except Exception as e:  # noqa: BLE001
            log.warning("skipping site %s: %s", f.name, e)
    return out


@lru_cache(maxsize=1)
def _base_maps() -> dict[str, dict]:
    """The base maps from lore/maps/, with places in their own pixel coordinates."""
    out: dict[str, dict] = {}
    mdir = cfg.load().lore / "maps"
    for f in sorted(mdir.glob("*.yaml")) if mdir.is_dir() else []:
        g = yaml.safe_load(f.read_text(encoding="utf-8"))
        if not isinstance(g, dict) or "id" not in g:
            continue                      # not a map (e.g. eriador-roads.yaml, the roads drawn on one)
        if "px_per_mile" in g:            # a region drawn from miles: convert to its image pixels
            prepare_region(g)
        else:
            g["places_px"] = dict(g.get("places") or {})
        out[g["id"]] = g
    return out


def prepare_region(g: dict) -> dict:
    """A region geography (miles) gets its image size, scale, and places in image pixels."""
    x0, y0, x1, y1 = g["bounds"]
    ppm = g["px_per_mile"]
    to_px = lambda p: [REGION_MARGIN + (p[0] - x0) * ppm, REGION_MARGIN + (p[1] - y0) * ppm]  # noqa: E731
    g["size"] = [int((x1 - x0) * ppm) + 2 * REGION_MARGIN, int((y1 - y0) * ppm) + 2 * REGION_MARGIN]
    g["miles_per_px"] = 1 / ppm
    g["places_px"] = {p["name"]: to_px(p["at"]) for p in g.get("places", [])}
    for key in ("forests", "marshes", "downs", "lakes", "hills", "mountains"):
        for feat in g.get(key, []):
            at = feat.get("label_at") or feat.get("center")
            if feat.get("name") and at and feat.get("label", True) is not False:
                g["places_px"].setdefault(feat["name"], to_px(at))
    g["anchor_px"] = to_px(g["anchor"]["at"])
    return g


def map_def(map_id: str) -> dict:
    m = maps().get(map_id)
    if not m:
        raise GeoError(f"no map {map_id!r}; maps: {', '.join(maps())}")
    return m


def to_parent(map_id: str, xy) -> tuple[str, list[float]] | None:
    """Project a point on a region map onto its parent map."""
    m = map_def(map_id)
    if not m.get("parent"):
        return None
    parent = map_def(m["parent"])
    anchor_name = m["anchor"]["place"]
    if anchor_name in parent["places_px"]:
        ax, ay = parent["places_px"][anchor_name]
    else:                                       # a site anchored on a campaign place
        cplace = store.load()["places"].get(anchor_name)
        if not cplace or cplace["map"] != parent["id"]:
            raise GeoError(f"{anchor_name} isn't placed on {parent['id']}")
        ax, ay = cplace["at"]
    k = m["miles_per_px"] / parent["miles_per_px"]
    return parent["id"], [ax + (xy[0] - m["anchor_px"][0]) * k, ay + (xy[1] - m["anchor_px"][1]) * k]


def inside(map_id: str, xy) -> bool:
    """Is this point within the map's picture?"""
    size = map_def(map_id).get("size")
    return not size or (0 <= xy[0] <= size[0] and 0 <= xy[1] <= size[1])


def lift(map_id: str, xy) -> tuple[str, list[float]]:
    """A point off the edge of a local map, carried up to the first map above it that holds it
    (the Old Watch, 45 miles from Bree, belongs on Eriador, not on Bree-land)."""
    cur, pt = map_id, list(xy)
    while not inside(cur, pt):
        up = to_parent(cur, pt)
        if up is None:
            break
        cur, pt = up
    return cur, pt


def chain(map_id: str) -> list[str]:
    out = [map_id]
    while map_def(out[-1]).get("parent"):
        out.append(map_def(out[-1])["parent"])
    return out


def project(map_id: str, xy, target: str) -> list[float]:
    """A point on `map_id` expressed on `target` (an ancestor of it, or itself)."""
    cur, pt = map_id, list(xy)
    while cur != target:
        nxt = to_parent(cur, pt)
        if nxt is None:
            raise GeoError(f"{target} isn't above {map_id}")
        cur, pt = nxt
    return pt


def common_map(a: tuple[str, list], b: tuple[str, list]) -> tuple[str, list, list]:
    """The most local map both points can be drawn on, with both points on it."""
    ca, cb = chain(a[0]), chain(b[0])
    for m in ca:
        if m in cb:
            return m, project(a[0], a[1], m), project(b[0], b[1], m)
    raise GeoError(f"{a[0]} and {b[0]} share no map")


def holding_map(map_ids: list[str]) -> str:
    """The most local map that holds all of these maps (each map counts as holding itself)."""
    chains = [chain(m) for m in map_ids]
    for cand in chains[0]:
        if all(cand in c for c in chains[1:]):
            return cand
    raise GeoError("those places aren't on one map: draw a land map that holds them all (region_map)")
