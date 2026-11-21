"""Journeys: the Eriador hex grid and its roads, land types, routes along roads, and journey plans."""

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
from .common import GeoError, HEX_MILES, REGION_MARGIN, ROAD_COST  # noqa: F401
from . import registry
from . import store


@lru_cache(maxsize=1)
def hexdata() -> dict | None:
    f = cfg.load().lore / "maps" / "eriador-hexes.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    d["types"] = {tuple(map(int, k.split(","))): t for k, t in d["hexes"].items()}
    return d


def _grid():
    d = hexdata()
    if not d:
        raise GeoError("no hex data (lore/maps/eriador-hexes.json)")
    g = d["grid"]
    return g["width"], g["height"], g["x0"], g["y0"]


def land_grid(m: dict) -> tuple[float, float, float, float]:
    """A land map's hex grid: 20-mile hexes, pointy, odd rows shifted right, from the map's top-left corner.
    The map view draws the same grid (map.js gridFor)."""
    w = HEX_MILES / m["miles_per_px"]
    return w, w * math.sqrt(3) / 2, 0.0, 0.0


def hex_center(col: int, row: int, grid: tuple | None = None) -> list[float]:
    W, H, X0, Y0 = grid or _grid()
    return [X0 + col * W + (W / 2 if row % 2 else 0), Y0 + row * H]


def px_to_hex(x: float, y: float, grid: tuple | None = None) -> tuple[int, int]:
    """Pixels -> (col, row) of the hex containing them (cube rounding); Eriador's grid unless one is given."""
    W, H, X0, Y0 = grid or _grid()
    r = (y - Y0) / H
    q = (x - X0) / W - r / 2
    sq, sr = -q - r, r
    rq, rr, rs = round(q), round(sr), round(sq)
    dq, dr, ds = abs(rq - q), abs(rr - sr), abs(rs - sq)
    if dq > dr and dq > ds:
        rq = -rr - rs
    elif dr > ds:
        rr = -rq - rs
    return int(rq + (rr - (rr & 1)) // 2), int(rr)


def _axial(col: int, row: int) -> tuple[int, int]:
    return col - (row - (row & 1)) // 2, row


def hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    (aq, ar), (bq, br) = _axial(*a), _axial(*b)
    return (abs(aq - bq) + abs(ar - br) + abs((-aq - ar) - (-bq - br))) // 2


def hex_neighbours(col: int, row: int) -> list[tuple[int, int]]:
    d = [(1, 0), (-1, 0), (1, -1), (0, -1), (1, 1), (0, 1)] if row % 2 else \
        [(1, 0), (-1, 0), (0, -1), (-1, -1), (0, 1), (-1, 1)]
    return [(col + a, row + b) for a, b in d]


@functools.lru_cache(maxsize=1)
def eriador_roads() -> dict[str, list]:
    """The roads of Eriador: {name: [stop, ...]}, each stop a pixel point on the Eriador map or the name of one of
    its calibrated places. They are traced from the official map, so they live in lore/maps/eriador-roads.yaml
    (gitignored) rather than in the code; without that file Eriador simply has no roads."""
    f = cfg.load().lore / "maps" / "eriador-roads.yaml"
    if not f.exists():
        return {}
    return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("roads") or {}


@functools.lru_cache(maxsize=1)
def road_hexes() -> dict[tuple[int, int], str]:
    """Hex -> road name, by tracing each road's waypoints across the Eriador hex grid."""
    if not hexdata():
        return {}
    places = (registry.map_def("eriador").get("places") or {})
    out: dict[tuple[int, int], str] = {}
    for name, stops in eriador_roads().items():
        pts = [places[s] if isinstance(s, str) else s for s in stops if not isinstance(s, str) or s in places]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            steps = max(2, int(math.hypot(x1 - x0, y1 - y0) / 8))
            for i in range(steps + 1):
                t = i / steps
                out.setdefault(px_to_hex(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t), name)
    return out


def hex_path(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """The hex route from a to b that avoids impassable hexes and the sea (A*). Road hexes cost a little
    less, so a route follows a road where one runs the right way."""
    import heapq
    types = hexdata()["types"]
    blocked = lambda h: types.get(h) in (None, "impassable", "sea")  # noqa: E731
    start, goal = a, b
    roads = road_hexes()
    frontier = [(0, 0, start)]
    came: dict = {start: None}
    cost = {start: 0}
    n = 0
    while frontier:
        _, _, cur = heapq.heappop(frontier)
        if cur == goal:
            break
        for nb in hex_neighbours(*cur):
            if nb != goal and blocked(nb):
                continue
            c = cost[cur] + (ROAD_COST if nb in roads else 1)
            if nb not in cost or c < cost[nb]:
                cost[nb] = c
                came[nb] = cur
                n += 1
                heapq.heappush(frontier, (c + ROAD_COST * hex_distance(nb, goal), n, nb))
    if goal not in came:
        raise GeoError("no route between those places that avoids mountains and sea")
    path, h = [], goal
    while h is not None:
        path.append(h)
        h = came[h]
    return path[::-1]


def _inside(p, poly) -> bool:
    from .common import point_in_polygon
    return point_in_polygon(p, poly)


def _seg_dist(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _to_miles(m: dict, xy) -> list[float]:
    """Region-map pixels -> its own miles (x east, y south of the anchor)."""
    x0, y0 = m["bounds"][0], m["bounds"][1]
    return [(xy[0] - REGION_MARGIN) / m["px_per_mile"] + x0, (xy[1] - REGION_MARGIN) / m["px_per_mile"] + y0]


def _default_land() -> str:
    try:
        from .. import clock
        land = clock.state()[1].get("region_land")
    except Exception:  # noqa: BLE001
        land = None
    return land if land in ("border", "wild", "dark") else "wild"


def land_at(map_id: str, xy) -> str:
    """The journey land type at a point: border, wild, dark or impassable (Loremaster knowledge)."""
    m = registry.map_def(map_id)
    if map_id == "eriador" and hexdata():
        return hexdata()["types"].get(px_to_hex(*xy), "unknown")
    if "bounds" in m:                                     # a region or land map drawn from miles
        p = _to_miles(m, xy)
        if any(_inside(p, f["area"]) for f in m.get("mountains", [])):
            return "impassable"
        for f in reversed(m.get("lands", [])):
            if _inside(p, f["area"]):
                return f["type"]
        if m.get("land"):
            return m["land"]
    return _default_land()


def road_at(map_id: str, xy) -> str | None:
    """The road a point lies on (within about a mile and a half), if any."""
    if map_id == "eriador":
        return road_hexes().get(px_to_hex(*xy)) if hexdata() else None
    m = registry.map_def(map_id)
    if "bounds" not in m:
        return None
    p = _to_miles(m, xy)
    for rd in m.get("roads", []):
        pts = rd["points"]
        if any(_seg_dist(p, a, b) <= 1.5 for a, b in zip(pts, pts[1:])):
            return rd.get("name") or "road"
    return None


def _hex_plan(pts: list[tuple[str, list[float]]]) -> dict:
    """Counting on the Eriador hex grid (pts in Eriador pixels)."""
    hexes: list[tuple[int, int]] = []
    for (_, a), (_, b) in zip(pts, pts[1:]):
        seg = hex_path(px_to_hex(*a), px_to_hex(*b))
        hexes += seg if not hexes else seg[1:]
    types = hexdata()["types"]
    entered = hexes[1:]
    route = [pts[0][1]] + [hex_center(*h) for h in hexes[1:-1]] + [pts[-1][1]]
    return {"map": "eriador", "hexes": len(entered), "miles": len(entered) * HEX_MILES,
            "lands_in_order": [types.get(h, "unknown") for h in entered],
            "road_in_order": [road_hexes().get(h) for h in entered],
            "route": route, "hex_cells": [list(h) for h in hexes]}


def _road_lines(map_id: str) -> list[list[list[float]]]:
    """The roads drawn on a map, as polylines in its pixels."""
    m = registry.map_def(map_id)
    if map_id == "eriador":
        places = m.get("places") or {}
        return [[places[s] if isinstance(s, str) else s for s in stops if not isinstance(s, str) or s in places]
                for stops in eriador_roads().values()]
    if "bounds" not in m:
        return []
    ppm, x0, y0 = m["px_per_mile"], m["bounds"][0], m["bounds"][1]
    to_px = lambda p: [REGION_MARGIN + (p[0] - x0) * ppm, REGION_MARGIN + (p[1] - y0) * ppm]  # noqa: E731
    return [[to_px(p) for p in rd["points"]] for rd in m.get("roads", [])]


def route_between(map_id: str, a: list[float], b: list[float]) -> list[list[float]]:
    """The way from a to b on a map, as a traveller would go it: along a road when one runs near both ends
    (within 3 miles, or half the way, of each) and the whole way is no more than half as long again as going
    straight."""
    m = registry.map_def(map_id)
    return _follow_roads(_road_lines(map_id), list(a), list(b), 3 / m["miles_per_px"])


def _road_legs(m: dict, a: list[float], b: list[float]) -> list[list[float]]:
    """A leg on a drawn map, following its roads (see route_between)."""
    if "bounds" not in m:
        return [a, b]
    return _follow_roads(_road_lines(m["id"]), a, b, 3 * m["px_per_mile"])


def _follow_roads(lines: list, a: list[float], b: list[float], near: float) -> list[list[float]]:
    near = max(near, 0.5 * math.dist(a, b))     # cross country to a road and along it, if that's not much longer
    best, best_len = [a, b], math.dist(a, b) * 1.5
    for pts in lines:
        if len(pts) < 2:
            continue
        segs = list(zip(pts, pts[1:]))
        da = [(_seg_dist(a, u, v), i) for i, (u, v) in enumerate(segs)]
        db = [(_seg_dist(b, u, v), i) for i, (u, v) in enumerate(segs)]
        (ea, ia), (eb, ib) = min(da), min(db)
        if ea > near or eb > near:
            continue
        inner = pts[ia + 1:ib + 1] if ia <= ib else list(reversed(pts[ib + 1:ia + 1]))
        path = [a, *inner, b]
        length = sum(math.dist(u, v) for u, v in zip(path, path[1:]))
        if length <= best_len:
            best, best_len = path, length
    return best


def _miles_plan(map_id: str, pts: list[tuple[str, list[float]]]) -> dict:
    """Counting by miles on any map: one hex per 20 miles along the route, each judged at its middle."""
    m = registry.map_def(map_id)
    mpp = m["miles_per_px"]
    path = [pts[0][1]]
    for (_, a), (_, b) in zip(pts, pts[1:]):
        path += _road_legs(m, list(a), list(b))[1:]       # follow a road where one runs the right way
    legs = [(a, b, math.dist(a, b) * mpp) for a, b in zip(path, path[1:])]
    miles = sum(d for _, _, d in legs)
    n = max(1, math.ceil(miles / HEX_MILES - 1e-9))

    def at(dist: float) -> list[float]:
        for a, b, d in legs:
            if dist <= d or (a, b, d) == legs[-1]:
                t = 0 if d == 0 else min(1.0, dist / d)
                return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
            dist -= d
        return list(path[-1])
    if m.get("scale") == "land":                  # a land map has its own 20-mile grid: count hexes entered
        grid = land_grid(m)
        step = grid[0] / 8
        cells, where = [], {}
        dist = 0.0
        total_px = miles / mpp
        while dist <= total_px:
            p = at(dist * mpp)
            c = px_to_hex(p[0], p[1], grid)
            if not cells or cells[-1] != c:
                if c not in cells:
                    cells.append(c)
                    where[c] = p
            dist += step
        end = px_to_hex(*path[-1], grid)
        if cells[-1] != end:
            cells.append(end)
            where[end] = list(path[-1])
        entered = cells[1:]
        if entered:
            return {"map": map_id, "hexes": len(entered), "miles": round(miles),
                    "lands_in_order": [land_at(map_id, where[c]) for c in entered],
                    "road_in_order": [road_at(map_id, where[c]) for c in entered],
                    "route": path, "hex_cells": [list(c) for c in cells], "grid": list(grid)}
    marks = [at(miles * (i + 0.5) / n) for i in range(n)]
    return {"map": map_id, "hexes": n, "miles": round(miles), "lands_in_order": [land_at(map_id, p) for p in marks],
            "road_in_order": [road_at(map_id, p) for p in marks],
            "route": path, "hex_cells": []}


def journey_plan(frm: str, to: str, via: list[str] | None = None, **kw) -> dict:
    """Plan a journey: hexes entered (destination counted, departure not), miles, the land types crossed
    (Loremaster knowledge, for events and fatigue), and which hexes lie on a road (an event there gains (1d)).

    Across Eriador it counts the official hex map. Otherwise (within a region such as Bree-land, on a land map
    beyond Eriador, or a route running off the hex grid) it counts 20 miles to a hex on the most local map
    that holds the whole journey, judging each hex at its middle."""
    data = store.load(**kw)
    stops = [store.find(name, data) for name in [frm] + list(via or []) + [to]]
    stops = [(n, *registry.lift(mp, xy)) for n, mp, xy in stops]     # a place recorded off its map's edge
    home = registry.holding_map([s[1] for s in stops])
    plan = None
    if home == "eriador" and hexdata():        # a journey across Eriador: the official hex map
        pts = [(n, registry.project(mp, xy, "eriador") if mp != "eriador" else xy) for n, mp, xy in stops]
        try:
            plan = _hex_plan(pts)
            if "unknown" in plan["lands_in_order"]:
                plan = None                    # off the hex grid: count by miles instead
        except GeoError:
            plan = None
        if plan is None:
            plan = _miles_plan("eriador", pts)
    if plan is None:
        pts = [(n, registry.project(mp, xy, home) if mp != home else xy) for n, mp, xy in stops]
        plan = _miles_plan(home, pts)
    from collections import Counter
    plan.update({"from": stops[0][0], "to": stops[-1][0], "via": [s[0] for s in stops[1:-1]],
                 "lands": dict(Counter(plan["lands_in_order"])),
                 "road_hexes": sum(1 for r in plan["road_in_order"] if r),
                 "route": [[round(x, 1), round(y, 1)] for x, y in plan["route"]]})
    return plan


def route_in_order(plan: dict) -> str:
    """'1 border (road), 2 wild, …': each hex entered, for the Loremaster."""
    roads = plan.get("road_in_order") or [None] * len(plan["lands_in_order"])
    return ", ".join(f"{i} {land}{' (road)' if road else ''}"
                     for i, (land, road) in enumerate(zip(plan["lands_in_order"], roads), 1))
