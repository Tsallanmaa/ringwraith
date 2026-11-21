"""Pictures and notes: map images in the vault, a move's little map, session road maps, the fog layer, and
the Obsidian map notes."""

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
from .common import GeoError, HEX_MILES, _cache, _stamp  # noqa: F401
from . import registry
from . import store


def move_picture(leg: dict, slug: str | None = None, root: Path | None = None) -> Path:
    """A small map of one move, for the tale: the route in the planned-journey style, its stops named."""
    from .. import mapdraw
    vault_dir = cp.campaign_dir(slug, root)
    base = vault_dir / "90 Assets" / "maps" / f"{leg['map']}.jpg"
    if not base.exists():
        build_images(slug, root, log=lambda *_: None)
    data = store.load(slug, root)
    places = []
    for name in (leg["from"], leg["to"]):
        try:
            pname, pmap, pxy = store.find(name, data)
        except GeoError:
            continue
        places.append({"name": pname, "at": registry.project(pmap, pxy, leg["map"]) if pmap != leg["map"] else pxy,
                       "state": data["states"].get(pname), "builtin": pname not in data["places"]})
    out_dir = vault_dir / "90 Assets" / "maps" / "moves"
    out_dir.mkdir(parents=True, exist_ok=True)
    from ..vault import slugify
    f = out_dir / f"day-{int(leg['day']):02d}-{slugify(leg['from'])}-to-{slugify(leg['to'])}-{leg['id'][:4]}.jpg"
    title = f"Day {leg['day']}{', ' + leg['time'] if leg.get('time') else ''}"
    mapdraw.session_map(base, registry.map_def(leg["map"])["size"], [leg], places, f, title, min_size=(820, 560),
                        out_width=1100, day_tags=False)
    return f


# ---------------------------------------------------------------------- map images in the vault
def build_images(slug: str | None = None, root: Path | None = None, force: bool = False, log=print) -> list[Path]:
    """Put every map's image into the vault's 90 Assets/maps/ (extracted or drawn locally, never in git)."""
    from PIL import Image
    from .. import mapdraw, sites
    c = cfg.load()
    out_dir = cp.campaign_dir(slug, root) / "90 Assets" / "maps"
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for mid, m in registry.maps().items():
        if m.get("site"):
            out = out_dir / f"{mid}.jpg"
            if force or not out.exists():
                sites.render_to_vault(sites.load(m["site"], slug, root), slug, root)
                made.append(out)
            continue
        out = out_dir / f"{mid}.jpg"
        if out.exists() and not force:
            continue
        if "px_per_mile" in m:
            from .. import regions
            g = regions.load(mid) if regions.exists(mid) else mapdraw.load_geo(mid)
            mapdraw.render_geo(g, out)
        else:
            src = m.get("source") or {}
            cached = c.build / "maps" / f"{mid}.png"
            if not cached.exists():
                import pymupdf
                from .. import sources
                doc = pymupdf.open(sources.resolve(c.references, src["pdf"]))
                pix = pymupdf.Pixmap(doc, src["xref"])
                if pix.n - pix.alpha >= 4:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                cached.parent.mkdir(parents=True, exist_ok=True)
                pix.save(str(cached))
            Image.open(cached).convert("RGB").save(out, quality=86)
        log(f"map image: {out}")
        made.append(out)
    return made


# ---------------------------------------------------------------------- Obsidian: session maps and map notes
def _map_title(map_id: str) -> str:
    return registry.map_def(map_id).get("title", map_id)


def session_maps(session: int, slug: str | None = None, root: Path | None = None) -> list[Path]:
    """Static maps of one session's travels (one per map used), in 90 Assets/maps/. Returns the files."""
    from .. import mapdraw
    vault_dir = cp.campaign_dir(slug, root)
    data = store.load(slug, root)
    by_map: dict[str, list[dict]] = {}
    for l in store.legs(slug, root):
        if l.get("session") == session and store.is_notable(l):     # steps across a town aren't the road
            by_map.setdefault(l["map"], []).append(l)
    out = []
    for mid, ls in by_map.items():
        names = {l["from"] for l in ls} | {l["to"] for l in ls}
        places = []
        for n in names:
            try:
                pname, pmap, pxy = store.find(n, data)
            except GeoError:
                continue
            places.append({"name": pname, "at": registry.project(pmap, pxy, mid) if pmap != mid else pxy,
                           "state": data["states"].get(pname), "builtin": pname not in data["places"]})
        places.sort(key=lambda p: 0 if p["state"] == "current" else 1)
        base = vault_dir / "90 Assets" / "maps" / f"{mid}.jpg"
        if not base.exists():
            build_images(slug, root, log=lambda *_: None)
        f = vault_dir / "90 Assets" / "maps" / f"session-{session:03d}-{mid}.jpg"
        mapdraw.session_map(base, registry.map_def(mid)["size"], ls, places, f, f"Session {session}: {_map_title(mid)}")
        out.append(f)
    return out


def _leg_line(l: dict) -> str:
    who = ", ".join(f"[[{w}]]" for w in l["who"])
    return (f"| {l['day']} | {l.get('time', '')} | {who} | [[{l['from']}]] → [[{l['to']}]] | {l.get('mode', '')} "
            f"| {l.get('note', '')} |")


def write_notes(slug: str | None = None, root: Path | None = None) -> list[Path]:
    """60 Maps/: one note per map (its picture, places, travels) and the Travel log. Regenerated each time."""
    from .. import vault
    vault_dir = cp.campaign_dir(slug, root)
    folder = vault_dir / "60 Maps"
    folder.mkdir(parents=True, exist_ok=True)
    data = store.load(slug, root)
    all_legs = store.legs(slug, root)
    written = []
    head = "| Day | Time | Who | Route | How | Note |\n|---|---|---|---|---|---|"
    for mid, m in registry.maps().items():
        title = _map_title(mid)
        known = [(n, data["states"][n]) for n in m["places_px"] if data["states"].get(n)]
        known += [(n, data["states"].get(n)) for n, p in data["places"].items() if p["map"] == mid]
        here = [l for l in all_legs if l["map"] == mid]
        sessions = sorted({l.get("session") for l in here if l.get("session")})
        lines = [f"# {title}", "", f"![[90 Assets/maps/{mid}.jpg]]", ""]
        if m.get("parent"):
            lines += [f"Part of [[{_map_title(m['parent'])}]].", ""]
        children = [c for c in registry.maps().values() if c.get("parent") == mid]
        if children:
            lines += ["Closer maps: " + ", ".join(f"[[{_map_title(c['id'])}]]" for c in children), ""]
        if sessions:
            lines += ["## Session maps", ""]
            lines += [f"![[90 Assets/maps/session-{s:03d}-{mid}.jpg]]" for s in sessions
                      if (vault_dir / "90 Assets" / "maps" / f"session-{s:03d}-{mid}.jpg").exists()]
            lines.append("")
        if known:
            label = {"current": "here now", "visited": "visited", "heard": "heard of"}
            lines += ["## Places", ""] + [f"- [[{n}]]: {label.get(st or '', 'unknown')}" for n, st in sorted(known)] + [""]
        if here:
            lines += ["## Travels", "", head] + [_leg_line(l) for l in here] + [""]
        f = folder / f"{title}.md"
        vault.write_note(f, {"type": "map", "map": mid, "image": f"[[90 Assets/maps/{mid}.jpg]]"}, "\n".join(lines))
        written.append(f)
    who_lines = [f"- [[{w}]]: [[{v.get('place')}]]" + (f" (since day {v['since_day']})" if v.get("since_day") else "")
                 for w, v in data["whereabouts"].items()]
    body = ["# Travel log", "", "Where everyone is, and every road taken. Maps: "
            + ", ".join(f"[[{_map_title(mid)}]]" for mid in registry.maps()), "", "## Where everyone is", "", *who_lines, "",
            "## The road so far", "", head, *[_leg_line(l) for l in all_legs], ""]
    f = folder / "Travel log.md"
    vault.write_note(f, {"type": "travel-log"}, "\n".join(body))
    written.append(f)
    return written


def session_note_section(session: int, files: list[Path], slug: str | None = None, root: Path | None = None) -> str:
    """Markdown for a session note's 'The road' section: the session maps and that session's legs."""
    ls = [l for l in store.legs(slug, root) if l.get("session") == session]
    lines = [f"![[90 Assets/maps/{f.name}]]" for f in files]
    lines += ["", f"Maps: {', '.join(f'[[{_map_title(m)}]]' for m in registry.maps())} · [[Travel log]]", ""]
    if ls:
        lines += ["| Day | Time | Who | Route | How |", "|---|---|---|---|---|"]
        lines += [f"| {l['day']} | {l.get('time', '')} | {', '.join(w.split()[0] for w in l['who'])} | "
                  f"[[{l['from']}]] → [[{l['to']}]] | {l.get('mode', '')} |" for l in ls]
    return "\n".join(lines) + "\n"


def fog_png(map_id: str) -> bytes:
    """The fog layer as PNG bytes, kept until a place, a move or a map changes."""
    import io
    pdir = cp.private_dir()
    files = [pdir / "geo.yaml", pdir / "travels.jsonl", *sorted((pdir / "regions").glob("*.yaml")),
             *sorted((pdir / "sites").glob("*.yaml"))]
    key = _stamp(files)
    hit = _cache.get(f"fog:{map_id}")
    if hit and hit[0] == key:
        return hit[1]
    buf = io.BytesIO()
    fog_image(map_id).save(buf, format="PNG")
    _cache[f"fog:{map_id}"] = (key, buf.getvalue())
    return buf.getvalue()


def fog_image(map_id: str, **kw):
    """A fog layer (PNG with alpha) that clears around the places known and the roads travelled."""
    from PIL import Image, ImageDraw, ImageFilter
    m = registry.map_def(map_id)
    w, h = m["size"]
    k = 0.25                                    # draw small; Leaflet stretches it over the map
    fog = Image.new("L", (int(w * k), int(h * k)), 150)
    d = ImageDraw.Draw(fog)
    data = store.load(**kw)
    clear = (3 * HEX_MILES if map_id == "eriador" or m.get("scale") == "land" else 1.6) / m["miles_per_px"] * k
    seen = []
    for name, st in data["states"].items():
        if st in ("visited", "current", "heard"):
            try:
                _, pm, pxy = store.find(name, data)
            except GeoError:
                continue
            xy = pxy if pm == map_id else (registry.project(pm, pxy, map_id) if map_id in registry.chain(pm) else None)
            if xy:
                seen.append(xy)
    for l in store.legs(**kw):
        if l["map"] == map_id or map_id in registry.chain(l["map"]):
            seen += [p if l["map"] == map_id else registry.project(l["map"], p, map_id) for p in l["path"]]
    for x, y in seen:
        d.ellipse([x * k - clear, y * k - clear, x * k + clear, y * k + clear], fill=0)
    fog = fog.filter(ImageFilter.GaussianBlur(clear * 0.35))
    tint = Image.new("RGBA", fog.size, (60, 44, 26, 0))
    tint.putalpha(fog)
    return tint
