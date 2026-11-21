"""Shared by the geo modules: place states, bearings, map margins, journey constants, errors, the file cache."""

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


STATES = ("heard", "visited", "current")


BEARINGS = {"N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
            "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5, "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5}


REGION_MARGIN = 70          # the blank border round a region map's picture (mapdraw uses it too)


class GeoError(ValueError):
    pass


# ---------------------------------------------------------------------- maps
_cache: dict[str, tuple] = {}


def _stamp(files) -> tuple:
    """What a cached reading of these files depends on: their paths, modification times and sizes."""
    out = []
    for f in files:
        try:
            st = f.stat()
            out.append((str(f), st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((str(f), None, None))
    return tuple(out)


LOCAL_MILES = 1.5     # a move shorter than this (across Bree, round Archet) isn't drawn on maps of the road


# ---------------------------------------------------------------------- hexes (journeys on Eriador)
# The Loremaster map's grid: pointy-topped hexes, odd rows shifted right, 20 miles across.
# Land types per hex (border, wild, dark, impassable, sea) are Loremaster knowledge: never shown to
# the player, only used to count journeys and set event dice.
HEX_MILES = 20


ROAD_COST = 0.75        # a road hex costs less to plan through, so routes follow a road unless it is much longer


def point_in_polygon(p, poly) -> bool:
    """Is point p inside the polygon (a list of [x, y])? Even-odd rule."""
    x, y, inside = p[0], p[1], False
    for (x1, y1), (x2, y2) in zip(poly, list(poly[1:]) + list(poly[:1])):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside
