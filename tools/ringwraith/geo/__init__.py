"""Where things are and who went where: maps, places, whereabouts and the travel log.

Maps (lore/maps/*.yaml, local):
- `eriador`: the official player map, in image pixels.
- region maps such as `bree-land`, drawn by mapdraw.py from a geography in miles and anchored on their
  parent map at a known place.
Every map position is in that map's own image pixels, so the web map and the static maps share it.

Per campaign (in the vault's hidden .ringwraith/ folder):
- geo.yaml: campaign places (added in play), place states (heard, visited, current), and whereabouts
  (where each person is).
- travels.jsonl: the travel log, one leg per move: day, time, who, from, to, the route on a map, how.

The package is split by job: `registry` (which maps exist, projecting between them), `store` (places,
whereabouts, moves, the travel log), `routing` (hexes, roads, journeys), `render` (pictures, fog and map
notes), and `common`. Callers use `geo.<name>` as before; to replace a function in a test, patch it in the
module that defines it (`geo.registry.maps`), since the modules call each other through their modules."""

from __future__ import annotations

from . import common  # noqa: F401
from . import registry  # noqa: F401
from . import store  # noqa: F401
from . import routing  # noqa: F401
from . import render  # noqa: F401
from .common import (  # noqa: F401
    STATES, BEARINGS, REGION_MARGIN, GeoError, _cache, _stamp, HEX_MILES, LOCAL_MILES, ROAD_COST,
)
from .registry import (  # noqa: F401
    _is_built_region, maps, _campaign_maps, _base_maps, prepare_region, map_def, to_parent, inside, lift, chain, project, common_map, holding_map,
)
from .store import (  # noqa: F401
    _files, load, save, legs, _norm, find, state_of, add_place, _set_state, set_state, move, _move_group, leg_miles, is_notable, who_text, reroute_legs, place_at, snapshot, set_plan,
)
from .routing import (  # noqa: F401
    hexdata, _grid, land_grid, hex_center, px_to_hex, _axial, hex_distance, hex_neighbours, eriador_roads, road_hexes, hex_path, _inside, _seg_dist, _to_miles, _default_land, land_at, road_at, _hex_plan, _road_lines, route_between, _road_legs, _follow_roads, _miles_plan, journey_plan, route_in_order,
)
from .render import (  # noqa: F401
    move_picture, build_images, _map_title, session_maps, _leg_line, write_notes, session_note_section, fog_png, fog_image,
)
import yaml  # noqa: F401,E402 (some callers use geo.yaml)
