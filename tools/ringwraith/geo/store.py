"""The campaign's places, place states, whereabouts and travel log (.ringwraith/geo.yaml, travels.jsonl),
and the moves that change them."""

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
from .common import BEARINGS, GeoError, LOCAL_MILES, STATES, _cache, _stamp  # noqa: F401
from . import registry
from . import routing


# ---------------------------------------------------------------------- campaign data
def _files(slug: str | None = None, root: Path | None = None) -> tuple[Path, Path]:
    p = cp.private_dir(slug, root)
    return p / "geo.yaml", p / "travels.jsonl"


def load(slug: str | None = None, root: Path | None = None) -> dict:
    """The campaign's places, place states and whereabouts. The parsed file is kept until it changes on
    disk; each caller gets its own copy, free to change and save."""
    import copy
    f, _ = _files(slug, root)
    key = _stamp([f])
    hit = _cache.get(str(f))
    if not (hit and hit[0] == key):
        text = f.read_text(encoding="utf-8") if f.exists() else ""
        parsed = yaml.safe_load(text) if text.strip() else None
        if text.strip() and not isinstance(parsed, dict):
            raise GeoError(f"{f} is damaged (not a mapping); restore it before playing on")
        hit = (key, parsed or {})
        _cache[str(f)] = hit
    data = copy.deepcopy(hit[1])
    data.setdefault("places", {})
    data.setdefault("states", {})
    data.setdefault("whereabouts", {})
    return data


def save(data: dict, slug: str | None = None, root: Path | None = None) -> None:
    f, _ = _files(slug, root)
    fileio.atomic_write(f, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def legs(slug: str | None = None, root: Path | None = None) -> list[dict]:
    import copy
    _, f = _files(slug, root)
    if not f.exists():
        return []
    key = _stamp([f])
    hit = _cache.get(str(f))
    if not (hit and hit[0] == key):
        hit = (key, [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()])
        _cache[str(f)] = hit
    return copy.deepcopy(hit[1])


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower().replace("the ", " ")).strip()


def find(name: str, data: dict | None = None) -> tuple[str, str, list[float]]:
    """Resolve a place name to (canonical name, map, xy). Campaign places first, then the most local map."""
    data = data if data is not None else load()
    key = _norm(name)
    for pname, p in data["places"].items():
        if _norm(pname) == key:
            return pname, p["map"], list(p["at"])
    ordered = sorted(registry.maps().values(), key=lambda m: -len(registry.chain(m["id"])))   # regions before Eriador
    for m in ordered:
        for pname, xy in m["places_px"].items():
            if _norm(pname) == key:
                return pname, m["id"], list(xy)
    raise GeoError(f"no place called {name!r}. Add it with place(name, near=..., bearing=..., miles=...)")


def state_of(name: str, data: dict) -> str | None:
    return data["states"].get(name)


@fileio.with_lock
def add_place(name: str, map_id: str | None = None, at=None, near: str | None = None, bearing: str | None = None,
              miles: float | None = None, state: str = "heard", note: str = "", **kw) -> dict:
    """Add (or move) a campaign place: exact pixels on a map, or relative to a known place."""
    data = load(**kw)
    if near:
        _, nmap, nxy = find(near, data)
        map_id = map_id or nmap
        if map_id != nmap:
            nxy = registry.project(nmap, nxy, map_id)
        if bearing is None or miles is None:
            raise GeoError("with near=, give bearing (N, NE, ESE…) and miles")
        b = BEARINGS.get(bearing.upper().replace("-", "").replace(" ", ""))
        if b is None:
            raise GeoError(f"bearing must be one of {', '.join(BEARINGS)}")
        mpp = registry.map_def(map_id)["miles_per_px"]
        r = math.radians(b)
        at = [nxy[0] + math.sin(r) * miles / mpp, nxy[1] - math.cos(r) * miles / mpp]
        map_id, at = registry.lift(map_id, at)         # off the local map: it goes on the map that holds it
    if map_id is None or at is None:
        raise GeoError("give map and at, or near with bearing and miles")
    registry.map_def(map_id)
    data["places"][name] = {"map": map_id, "at": [round(at[0], 1), round(at[1], 1)], **({"note": note} if note else {})}
    if state:
        _set_state(data, name, state)
    save(data, **kw)
    return {"name": name, **data["places"][name], "state": data["states"].get(name)}


def _set_state(data: dict, name: str, state: str) -> None:
    if state not in STATES:
        raise GeoError(f"state must be one of {', '.join(STATES)}")
    old = data["states"].get(name)
    if old == "visited" and state == "heard":
        return                     # don't forget a place once visited
    if state == "current":
        for k, v in list(data["states"].items()):
            if v == "current":
                data["states"][k] = "visited"
    data["states"][name] = state


@fileio.with_lock
def set_state(name: str, state: str, **kw) -> None:
    data = load(**kw)
    pname, _, _ = find(name, data)
    _set_state(data, pname, state)
    save(data, **kw)


@fileio.with_lock
def move(who: list[str], to: str, frm: str | None = None, via: list[str] | None = None, mode: str = "on foot",
         note: str = "", day: int | None = None, time: str | None = None, hero: str | None = None,
         **kw) -> dict:
    """Record a move, update whereabouts and place states. Returns the (last) leg.

    Movers who start from different places get a leg each, so every route is drawn from where that
    person really was."""
    if not who:
        raise GeoError("who is moving?")
    if not frm:
        data = load(**kw)
        groups: dict[str, list[str]] = {}
        for w in who:
            groups.setdefault(data["whereabouts"].get(w, {}).get("place") or "", []).append(w)
        if len(groups) > 1:
            leg = None
            for start, members in groups.items():
                leg = move(members, to, frm=start or None, via=via, mode=mode, note=note, day=day, time=time,
                           hero=hero, **kw)
            return leg
    return _move_group(who, to, frm, via, mode, note, day, time, hero, **kw)


def _move_group(who, to, frm, via, mode, note, day, time, hero, **kw) -> dict:
    from .. import clock
    data = load(**kw)
    start_name = frm or data["whereabouts"].get(who[0], {}).get("place")
    if not start_name:
        raise GeoError(f"where does {who[0]} start? Give from=")
    s_name, s_map, s_xy = find(start_name, data)
    t_name, t_map, t_xy = find(to, data)
    points = [(s_map, s_xy)] + [find(v, data)[1:] for v in (via or [])] + [(t_map, t_xy)]
    # draw the whole route on the most local map that holds every point
    target = points[0][0]
    for pm, pxy in points[1:]:
        target, _, _ = registry.common_map((target, [0, 0]), (pm, pxy))
    stops = [[round(c, 1) for c in registry.project(pm, pxy, target)] for pm, pxy in points]
    path = [stops[0]]
    for a, b in zip(stops, stops[1:]):
        path += [[round(c, 1) for c in p] for p in routing.route_between(target, a, b)[1:]]
    st = clock.state(**kw)[1]
    leg = {"id": uuid.uuid4().hex[:8], "session": int(st.get("session") or 0),
           "day": day if day is not None else clock.today(st),
           "time": time if time is not None else st.get("time", ""), "who": who, "from": s_name, "to": t_name,
           "map": target, "stops": stops, "path": path, "mode": mode, "note": note,
           "logged": dt.datetime.now().isoformat(timespec="seconds")}
    _, lf = _files(**kw)
    with lf.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(leg, ensure_ascii=False) + "\n")
    for w in who:
        data["whereabouts"][w] = {"place": t_name, "since_day": leg["day"]}
    if data.get("plan", {}).get("to") == t_name:
        data.pop("plan", None)       # the planned journey is done
    for name in (s_name, t_name):                # both ends have been visited now...
        if data["states"].get(name) != "current":
            _set_state(data, name, "visited")
    # ...and "you are here" is wherever the hero is: an Ally's errand never moves it, and an Ally walking
    # to the hero's place never clears it. With no hero known, the destination is the current place.
    here = data["whereabouts"].get(hero, {}).get("place") if hero else t_name
    if here:
        _set_state(data, here, "current")
    save(data, **kw)
    return leg


def leg_miles(leg: dict) -> float:
    """How far a move went as the crow flies, in miles."""
    pts = leg.get("stops") or leg["path"]
    return math.dist(pts[0], pts[-1]) * registry.map_def(leg["map"])["miles_per_px"] if leg["map"] in registry.maps() else 0.0


def is_notable(leg: dict) -> bool:
    """A move that really takes the company somewhere (not a step across the same village or town)."""
    return leg["from"] != leg["to"] and leg["map"] in registry.maps() and leg_miles(leg) >= LOCAL_MILES


def who_text(who: list[str]) -> str:
    """'Herb and Molly', 'Tomas, Sid, Sage and Giles': first names, for captions."""
    names = [w if w.lower().startswith("the ") else w.split()[0] for w in who if w.strip()]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


@fileio.with_lock
def reroute_legs(**kw) -> int:
    """Redraw the recorded moves along the roads (for travel logs recorded before moves followed roads)."""
    _, lf = _files(**kw)
    if not lf.exists():
        return 0
    out, changed = [], 0
    for line in lf.read_text(encoding="utf-8").splitlines():
        try:
            leg = json.loads(line)
        except ValueError:
            out.append(line)
            continue
        if leg.get("map") in registry.maps():
            stops = leg.get("stops") or ([leg["path"][0], leg["path"][-1]] if len(leg["path"]) >= 2 else leg["path"])
            path = [stops[0]]
            for a, b in zip(stops, stops[1:]):
                path += [[round(c, 1) for c in p] for p in routing.route_between(leg["map"], a, b)[1:]]
            if path != leg["path"] or "stops" not in leg:
                leg["stops"], leg["path"] = stops, path
                changed += 1
        out.append(json.dumps(leg, ensure_ascii=False))
    fileio.atomic_write(lf, "\n".join(out) + "\n")
    return changed


@fileio.with_lock
def place_at(name: str, who: list[str], **kw) -> None:
    """Set whereabouts without a recorded journey (e.g. at the start of a campaign)."""
    data = load(**kw)
    pname, _, _ = find(name, data)
    for w in who:
        data["whereabouts"][w] = {"place": pname}
    save(data, **kw)


def snapshot(**kw) -> dict:
    """Everything a map view needs: maps (minus drawing data), places with states, whereabouts, legs."""
    data = load(**kw)
    out_maps = {}
    for mid, m in registry.maps().items():
        out_maps[mid] = {"id": mid, "title": m.get("title", mid), "size": m["size"], "parent": m.get("parent"),
                         "miles_per_px": m["miles_per_px"], "image": f"/assets/maps/{mid}.jpg",
                         "site": bool(m.get("site")), "anchor": (m.get("anchor") or {}).get("place"),
                         "scale": m.get("scale")}
        if m.get("parent"):
            p_id = m["parent"]
            w, h = m["size"]
            tl = registry.project(mid, [0, 0], p_id)
            br = registry.project(mid, [w, h], p_id)
            out_maps[mid]["box_on_parent"] = [tl, br]
    places = []
    for mid, m in registry.maps().items():
        for name, xy in m["places_px"].items():
            if m.get("site") and name not in m["explored"]:
                continue                         # unexplored rooms stay secret
            places.append({"name": name, "map": mid, "at": xy, "state": data["states"].get(name), "builtin": True})
    for name, p in data["places"].items():
        places.append({"name": name, "map": p["map"], "at": p["at"], "state": data["states"].get(name),
                       "note": p.get("note", "")})
    hd = routing.hexdata()
    grid = {"map": "eriador", **hd["grid"]} if hd else None
    return {"maps": out_maps, "places": places, "whereabouts": data["whereabouts"], "legs": legs(**kw),
            "plan": data.get("plan"), "grid": grid}


@fileio.with_lock
def set_plan(plan: dict | None, **kw) -> None:
    """Show (or clear) a planned journey on the map. The player sees the route, never the land types."""
    data = load(**kw)
    if plan:
        data["plan"] = {"from": plan["from"], "to": plan["to"], "route": plan["route"], "hexes": plan["hexes"],
                        "miles": plan["miles"], "cells": plan["hex_cells"], "map": plan.get("map", "eriador"),
                        "grid": plan.get("grid")}
    else:
        data.pop("plan", None)
    save(data, **kw)
