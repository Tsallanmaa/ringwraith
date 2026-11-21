"""Site plans: buildings, ruins, camps and delves, drawn as ink floor plans that reveal only what the hero
has explored.

A site lives in the campaign (`.ringwraith/sites/<id>.yaml`) and belongs to a place on a region map:

    id: mungos-house
    title: Mungo's house
    place: Mungo's house            # the campaign place it belongs to
    levels: [Ground floor, Upper floor]
    rooms:
      - {id: office, name: The office, level: Ground floor, x: 0, y: 0, w: 6, h: 5, explored: true,
         features: [{kind: chest, at: [5, 4], label: iron-bound chest}, {kind: desk, at: [2, 1]}]}
    doors:
      - {rooms: [office, hall], at: [6, 2]}           # a door on the wall between two rooms (grid point)
      - {rooms: [kitchen], at: [10, 9], kind: outside, label: back door}

Grid squares are 5 feet. `at` for doors is a point on a wall line; for features, a square in the room.
Each room is also a place ("Mungo's house: The office") so people can be moved into it.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

from . import campaign as cp
from . import fileio
from .mapdraw import INK, INK_SOFT, PARCHMENT, RED, _font, parchment

CELL = 44           # pixels per 5-foot square
MARGIN = 90
GAP = 120           # between levels drawn side by side
FEATURES = ("chest", "desk", "table", "bed", "hearth", "stair", "barrel", "well", "altar", "statue", "pillar", "crate")


class SiteError(ValueError):
    pass


def _dir(slug=None, root=None) -> Path:
    d = cp.private_dir(slug, root) / "sites"
    d.mkdir(exist_ok=True)
    return d


def slug_of(text: str) -> str:
    from .vault import slugify
    return slugify(text)


def load(site_id: str, slug=None, root=None) -> dict:
    f = _dir(slug, root) / f"{site_id}.yaml"
    if not f.exists():
        raise SiteError(f"no site {site_id!r}")
    return yaml.safe_load(f.read_text(encoding="utf-8"))


def all_sites(slug=None, root=None) -> list[dict]:
    try:
        d = _dir(slug, root)
    except cp.CampaignError:
        return []
    return [yaml.safe_load(f.read_text(encoding="utf-8")) for f in sorted(d.glob("*.yaml"))]


def validate(site: dict) -> dict:
    if not site.get("title") or not site.get("place"):
        raise SiteError("a site needs title and place")
    site.setdefault("id", slug_of(site["title"]))
    site.setdefault("levels", sorted({r.get("level", "Ground floor") for r in site.get("rooms", [])}) or ["Ground floor"])
    ids = set()
    for r in site.get("rooms", []):
        for k in ("id", "name", "x", "y", "w", "h"):
            if k not in r:
                raise SiteError(f"room {r.get('id', '?')} is missing {k}")
        if r["w"] < 1 or r["h"] < 1:
            raise SiteError(f"room {r['id']} must be at least 1x1")
        r.setdefault("level", site["levels"][0])
        if r["level"] not in site["levels"]:
            site["levels"].append(r["level"])
        r.setdefault("explored", False)
        for f in r.get("features", []):
            if f.get("kind") not in FEATURES:
                raise SiteError(f"feature kind must be one of {', '.join(FEATURES)}")
        ids.add(r["id"])
    for dr in site.get("doors", []):
        for rid in dr.get("rooms", []):
            if rid not in ids:
                raise SiteError(f"door refers to unknown room {rid!r}")
    return site


def save(site: dict, slug=None, root=None) -> Path:
    site = validate(site)
    f = _dir(slug, root) / f"{site['id']}.yaml"
    fileio.atomic_write(f, yaml.safe_dump(site, sort_keys=False, allow_unicode=True))
    return f


@fileio.with_lock
def explore(site_id: str, room_ids: list[str], slug=None, root=None) -> dict:
    site = load(site_id, slug, root)
    known = {r["id"] for r in site["rooms"]}
    bad = [r for r in room_ids if r not in known]
    if bad:
        raise SiteError(f"unknown rooms: {', '.join(bad)}")
    for r in site["rooms"]:
        if r["id"] in room_ids:
            r["explored"] = True
    save(site, slug, root)
    return site


# ---------------------------------------------------------------------- geometry shared with geo
def layout(site: dict) -> dict:
    """Pixel geometry: each shown level's offset, the image size, and each room's centre.
    A level with nothing explored isn't drawn; its rooms sit at the plan's centre until revealed."""
    levels = [lv for lv in site["levels"] if any(r.get("explored") and r["level"] == lv for r in site["rooms"])]
    levels = levels or site["levels"][:1]
    spans = {}
    for lv in levels:
        rs = [r for r in site["rooms"] if r["level"] == lv] or [{"x": 0, "y": 0, "w": 4, "h": 4}]
        spans[lv] = (min(r["x"] for r in rs), min(r["y"] for r in rs),
                     max(r["x"] + r["w"] for r in rs), max(r["y"] + r["h"] for r in rs))
    content_w = sum((spans[lv][2] - spans[lv][0]) * CELL for lv in levels) + GAP * (len(levels) - 1)
    width = max(int(content_w + 2 * MARGIN + 160), 820)
    offsets, x = {}, (width - content_w) / 2
    height = 0
    top = MARGIN + 100
    for lv in levels:
        x0, y0, x1, y1 = spans[lv]
        offsets[lv] = (x - x0 * CELL, top - y0 * CELL)
        x += (x1 - x0) * CELL + GAP
        height = max(height, (y1 - y0) * CELL)
    size = [width, int(height + top + MARGIN + 40)]
    centres = {}
    for r in site["rooms"]:
        if r["level"] not in offsets:
            centres[r["id"]] = [size[0] / 2, size[1] / 2]
            continue
        ox, oy = offsets[r["level"]]
        centres[r["id"]] = [ox + (r["x"] + r["w"] / 2) * CELL, oy + (r["y"] + r["h"] / 2) * CELL]
    return {"offsets": offsets, "size": size, "centres": centres, "spans": spans, "levels": levels}


def room_place(site: dict, room: dict) -> str:
    return f"{site['title']}: {room['name']}"


# ---------------------------------------------------------------------- drawing
def render(site: dict, out: Path) -> Path:
    site = validate(site)
    lay = layout(site)
    W, H = lay["size"]
    img = parchment(W, H, seed=hash(site["id"]) & 0xFFFF).convert("RGB")
    d = ImageDraw.Draw(img)
    fell, fell_s = _font("IMFellEnglish-Italic.ttf", 22), _font("IMFellEnglish-Italic.ttf", 17)
    unc = _font("UncialAntiqua-Regular.ttf", 26)
    explored = {r["id"] for r in site["rooms"] if r["explored"]}

    def box(r):
        ox, oy = lay["offsets"][r["level"]]
        return (ox + r["x"] * CELL, oy + r["y"] * CELL, ox + (r["x"] + r["w"]) * CELL, oy + (r["y"] + r["h"]) * CELL)

    for lv in lay["levels"]:      # level headings
        ox, oy = lay["offsets"][lv]
        x0, y0, x1, _ = lay["spans"][lv]
        d.text((ox + (x0 + x1) / 2 * CELL, oy + y0 * CELL - 64), lv.upper(), font=fell, fill=INK, anchor="mm")

    rooms = [r for r in site["rooms"] if r["id"] in explored]
    # hatching round the walls: short diagonal strokes in a band outside each explored room
    for r in rooms:
        bx0, by0, bx1, by1 = box(r)
        band = 14
        for k in range(int(bx0 - band), int(bx1 + band), 7):
            for (ya, yb) in ((by0 - band, by0), (by1, by1 + band)):
                d.line([(k, yb), (k + band * .7, ya)], fill=INK_SOFT, width=1)
        for k in range(int(by0), int(by1), 7):
            for (xa, xb) in ((bx0 - band, bx0), (bx1, bx1 + band)):
                d.line([(xa, k + band * .7), (xb, k)], fill=INK_SOFT, width=1)
    for r in rooms:              # floors, with a faint 5-foot grid
        bx0, by0, bx1, by1 = box(r)
        d.rectangle([bx0, by0, bx1, by1], fill=PARCHMENT)
        for gx in range(r["w"] + 1):
            d.line([(bx0 + gx * CELL, by0), (bx0 + gx * CELL, by1)], fill=(190, 172, 140), width=1)
        for gy in range(r["h"] + 1):
            d.line([(bx0, by0 + gy * CELL), (bx1, by0 + gy * CELL)], fill=(190, 172, 140), width=1)
    for r in rooms:              # walls
        d.rectangle(list(box(r)), outline=INK, width=5)
    for r in rooms:              # furnishings
        bx0, by0, *_ = box(r)
        for f in r.get("features", []):
            fx, fy = f["at"]
            cx, cy = bx0 + (fx - r["x"] + .5) * CELL, by0 + (fy - r["y"] + .5) * CELL
            _feature(d, f["kind"], cx, cy)
            if f.get("label"):
                bx0_, _, bx1_, _ = box(r)
                tw = d.textlength(f["label"], font=fell_s)
                lx = min(max(cx, bx0_ + tw / 2 + 8), bx1_ - tw / 2 - 8)
                d.text((lx, cy + CELL * .5), f["label"], font=fell_s, fill=INK_SOFT, anchor="mt")
    for dr in site.get("doors", []):   # doors: only where at least one side is explored
        rs = [r for r in site["rooms"] if r["id"] in dr.get("rooms", [])]
        seen = [r for r in rs if r["id"] in explored and r["level"] in lay["offsets"]]
        if not seen:
            continue
        ox, oy = lay["offsets"][seen[0]["level"]]
        px, py = ox + dr["at"][0] * CELL, oy + dr["at"][1] * CELL
        r0 = seen[0]
        vertical = abs(dr["at"][0] - r0["x"]) < 1e-6 or abs(dr["at"][0] - (r0["x"] + r0["w"])) < 1e-6
        if vertical:
            d.rectangle([px - 6, py + 6, px + 6, py + CELL - 6], fill=PARCHMENT, outline=INK, width=2)
            mid = (px, py + CELL / 2)
        else:
            d.rectangle([px + 6, py - 6, px + CELL - 6, py + 6], fill=PARCHMENT, outline=INK, width=2)
            mid = (px + CELL / 2, py)
        unexplored_beyond = len(rs) > len(seen)
        if unexplored_beyond:
            d.text((mid[0] + (18 if vertical else 0), mid[1] + (0 if vertical else 18)), "?", font=unc, fill=RED,
                   anchor="mm")
        if dr.get("kind") == "outside" and dr.get("label"):
            bx0, by0, bx1, by1 = box(r0)
            if vertical:
                left = abs(px - bx0) < 2
                d.text((mid[0] + (-22 if left else 22), mid[1]), dr["label"], font=fell_s, fill=INK_SOFT,
                       anchor="rm" if left else "lm")
            else:
                top_wall = abs(py - by0) < 2
                d.text((mid[0], mid[1] + (-20 if top_wall else 20)), dr["label"], font=fell_s, fill=INK_SOFT,
                       anchor="mb" if top_wall else "mt")
    for r in rooms:              # names
        bx0, by0, bx1, by1 = box(r)
        d.text(((bx0 + bx1) / 2, by0 + 16), r["name"], font=fell, fill=INK, anchor="mt", stroke_width=3,
               stroke_fill=PARCHMENT)

    # frame, title, scale
    d.rectangle([20, 20, W - 20, H - 20], outline=INK, width=3)
    d.rectangle([28, 28, W - 28, H - 28], outline=INK, width=1)
    size = 40
    tf = _font("UncialAntiqua-Regular.ttf", size)
    while d.textlength(site["title"].upper(), font=tf) > W - 120 and size > 18:
        size -= 2
        tf = _font("UncialAntiqua-Regular.ttf", size)
    d.text((W / 2, 62), site["title"].upper(), font=tf, fill=RED, anchor="mm")
    sx, sy = W - MARGIN - 4 * CELL, H - 52
    for k in range(4):
        d.rectangle([sx + k * CELL, sy, sx + (k + 1) * CELL, sy + 8], fill=INK if k % 2 == 0 else PARCHMENT, outline=INK)
    d.text((sx + 4 * CELL + 8, sy + 4), "20 feet", font=fell_s, fill=INK, anchor="lm")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=90)
    return out


def _feature(d, kind, cx, cy):
    c = CELL
    if kind == "chest":
        d.rectangle([cx - c * .35, cy - c * .22, cx + c * .35, cy + c * .22], fill=PARCHMENT, outline=INK, width=2)
        d.line([(cx - c * .35, cy - c * .05), (cx + c * .35, cy - c * .05)], fill=INK, width=2)
        d.rectangle([cx - 3, cy - 6, cx + 3, cy + 2], fill=INK)
    elif kind in ("desk", "table"):
        w = .42 if kind == "desk" else .45
        d.rectangle([cx - c * w, cy - c * .28, cx + c * w, cy + c * .28], fill=PARCHMENT, outline=INK, width=2)
        if kind == "desk":
            d.ellipse([cx + c * .1, cy + c * .05, cx + c * .2, cy + c * .15], fill=INK)
    elif kind == "bed":
        d.rectangle([cx - c * .3, cy - c * .45, cx + c * .3, cy + c * .45], fill=PARCHMENT, outline=INK, width=2)
        d.rectangle([cx - c * .22, cy - c * .4, cx + c * .22, cy - c * .2], outline=INK, width=1)
    elif kind == "hearth":
        d.pieslice([cx - c * .45, cy - c * .45, cx + c * .45, cy + c * .45], 180, 360, fill=INK_SOFT, outline=INK)
    elif kind == "stair":
        for k in range(6):
            y = cy - c * .45 + k * c * .18
            d.line([(cx - c * .4, y), (cx + c * .4, y)], fill=INK, width=2)
        d.line([(cx - c * .4, cy - c * .45), (cx - c * .4, cy + c * .45)], fill=INK, width=2)
        d.line([(cx + c * .4, cy - c * .45), (cx + c * .4, cy + c * .45)], fill=INK, width=2)
    elif kind in ("barrel", "well", "pillar"):
        r = c * (.28 if kind != "well" else .35)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PARCHMENT if kind != "pillar" else INK_SOFT, outline=INK, width=2)
        if kind == "well":
            d.ellipse([cx - r * .55, cy - r * .55, cx + r * .55, cy + r * .55], outline=INK, width=1)
    elif kind in ("altar", "crate"):
        d.rectangle([cx - c * .3, cy - c * .3, cx + c * .3, cy + c * .3], fill=PARCHMENT, outline=INK, width=2)
        d.line([(cx - c * .3, cy - c * .3), (cx + c * .3, cy + c * .3)], fill=INK_SOFT, width=1)
    elif kind == "statue":
        d.ellipse([cx - c * .3, cy - c * .3, cx + c * .3, cy + c * .3], fill=INK_SOFT, outline=INK, width=2)


def render_to_vault(site: dict, slug=None, root=None) -> Path:
    out = cp.campaign_dir(slug, root) / "90 Assets" / "maps" / f"site-{site['id']}.jpg"
    return render(site, out)
