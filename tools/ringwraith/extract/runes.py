"""Detect the One Ring dice icons, which the PDFs draw as small vector paths.

The icons are not font glyphs, so text extraction drops them. They have a
stable path signature in every Free League TOR book we have checked:

    Gandalf rune (Feat die)    ~6.1 x 8.4 pt   8 paths,  96 path items
    Eye of Sauron (Feat die)   ~13.7 x 5.8 pt  3 paths,  38 path items
    Success icon (Success die) ~6.2 x 5.8 pt   1 path,   32 path items

Adjacent success icons merge into one cluster (k paths, 32k items).
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf as fitz

GANDALF = "{gandalf}"
EYE = "{eye}"
SUCCESS = "{success}"
UNKNOWN = "{icon?}"


@dataclass
class Icon:
    rect: fitz.Rect
    token: str
    paths: int
    items: int


def classify(paths: int, items: int) -> str:
    if (paths, items) == (8, 96):
        return GANDALF
    if (paths, items) == (3, 38):
        return EYE
    if paths >= 1 and items == 32 * paths:
        return SUCCESS * paths
    return UNKNOWN


def _clusters(page: fitz.Page, max_part: float = 16.0) -> list[dict]:
    groups: list[dict] = []
    for dr in page.get_drawings():
        r, fill = dr["rect"], dr.get("fill")
        if not fill or r.width >= max_part or r.height >= max_part:
            continue
        for g in groups:
            if g["fill"] == fill and (g["rect"] + (-1.5, -1.5, 1.5, 1.5)).intersects(r):
                g["rect"] |= r
                g["paths"] += 1
                g["items"] += len(dr["items"])
                break
        else:
            groups.append({"rect": fitz.Rect(r), "fill": fill, "paths": 1, "items": len(dr["items"])})
    return groups


def find_icons(page: fitz.Page) -> list[Icon]:
    icons = []
    for g in _clusters(page):
        r = g["rect"]
        # Icons are text-sized; skip specks and decorative ornaments.
        if not (3 <= r.height <= 16 and 3 <= r.width <= 40):
            continue
        token = classify(g["paths"], g["items"])
        if token == UNKNOWN and g["items"] < 8:
            continue  # bullet dots, rules, tiny ornaments
        icons.append(Icon(r, token, g["paths"], g["items"]))
    return icons
