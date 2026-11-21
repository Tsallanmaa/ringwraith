import pytest

from ringwraith import geo

WORLD = {"id": "world", "title": "World", "size": [1000, 800], "miles_per_px": 1.0,
         "places_px": {"Town": [500, 400], "Tower": [700, 400]}}
REGION = {"id": "shire", "title": "Region", "size": [400, 400], "miles_per_px": 0.1, "parent": "world",
          "anchor": {"place": "Town", "at": [0, 0]}, "anchor_px": [200, 200],
          "places_px": {"Town": [200, 200], "Village": [300, 200]}}


@pytest.fixture
def camp(tmp_path, monkeypatch):
    monkeypatch.setattr(geo.registry, "maps", lambda: {"world": WORLD, "shire": REGION})
    (tmp_path / "c1" / ".ringwraith").mkdir(parents=True)
    (tmp_path / "c1" / ".ringwraith" / "state.md").write_text("---\nday: 3\nsession: 2\ntime: dusk\n---\n",
                                                              encoding="utf-8")
    return {"slug": "c1", "root": tmp_path}


def test_projection_and_lookup(camp):
    # the region's Village is 100 px (10 miles) east of Town; on the world map that's 10 px
    assert geo.project("shire", [300, 200], "world") == [510.0, 400.0]
    name, m, xy = geo.find("village", geo.load(**camp))
    assert (name, m) == ("Village", "shire")
    assert geo.find("Town", geo.load(**camp))[1] == "shire"          # the most local map wins


def test_relative_places_and_moves(camp):
    e = geo.add_place("The Mill", near="Village", bearing="N", miles=2, state="heard", **camp)
    assert e["map"] == "shire" and e["at"] == [300.0, 180.0]
    geo.place_at("Town", ["Hero", "Ally"], **camp)
    leg = geo.move(["Hero", "Ally"], "The Mill", via=["Village"], hero="Hero", **camp)
    assert leg["day"] == 3 and leg["session"] == 2 and leg["time"] == "dusk" and leg["map"] == "shire"
    assert leg["path"] == [[200, 200], [300, 200], [300.0, 180.0]]
    data = geo.load(**camp)
    assert data["whereabouts"]["Ally"]["place"] == "The Mill" and data["states"]["The Mill"] == "current"
    # a move to a place only on the world map is drawn on the world map
    leg = geo.move(["Hero"], "Tower", hero="Hero", **camp)
    assert leg["map"] == "world" and leg["path"][-1] == [700, 400]
    assert geo.load(**camp)["states"]["The Mill"] == "visited"


def test_group_moves_split_by_starting_place(camp):
    geo.place_at("Town", ["Hero"], **camp)
    geo.place_at("Village", ["Ally"], **camp)
    geo.move(["Hero", "Ally"], "Tower", hero="Hero", **camp)
    starts = sorted(l["from"] for l in geo.legs(**camp))
    assert starts == ["Town", "Village"]


def test_errors(camp):
    with pytest.raises(geo.GeoError):
        geo.find("Nowhere", geo.load(**camp))
    with pytest.raises(geo.GeoError):
        geo.add_place("X", near="Town", bearing="UP", miles=1, **camp)


GRID = {"grid": {"width": 87.4, "height": 76.0, "x0": 100.0, "y0": 100.0},
        "types": {}}


@pytest.fixture
def hexes(monkeypatch):
    # a 12x8 patch of wild land with a wall of mountains at column 5 (except a pass at row 6)
    types = {(c, r): "wild" for c in range(0, 12) for r in range(0, 8)}
    for r in range(0, 8):
        if r != 6:
            types[(5, r)] = "impassable"
    types[(9, 2)] = "dark"
    monkeypatch.setattr(geo.routing, "hexdata", lambda: {**GRID, "types": types})
    monkeypatch.setattr(geo.routing, "road_hexes", lambda: {})          # no roads unless a test lays one
    return types


def test_hex_round_trip_and_distance(hexes):
    for c, r in [(0, 0), (3, 1), (7, 4), (2, 5)]:
        x, y = geo.hex_center(c, r)
        assert geo.px_to_hex(x + 10, y - 8) == (c, r)
    assert geo.hex_distance((0, 0), (3, 0)) == 3
    assert geo.hex_distance((0, 0), (0, 2)) == 2


def test_hex_path_goes_round_mountains(hexes):
    path = geo.hex_path((2, 2), (8, 2))
    assert path[0] == (2, 2) and path[-1] == (8, 2)
    assert all(hexes[h] != "impassable" for h in path)
    assert (5, 6) in path                                   # through the pass
    assert len(path) - 1 > geo.hex_distance((2, 2), (8, 2))  # longer than the straight line


def test_site_plans_validate_and_lay_out(tmp_path):
    from ringwraith import sites
    site = sites.validate({"title": "Old Mill", "place": "The Mill", "rooms": [
        {"id": "a", "name": "Floor", "x": 0, "y": 0, "w": 4, "h": 3, "explored": True,
         "features": [{"kind": "barrel", "at": [1, 1]}]},
        {"id": "b", "name": "Loft", "level": "Upper", "x": 0, "y": 0, "w": 4, "h": 3}],
        "doors": [{"rooms": ["a", "b"], "at": [2, 0]}]})
    assert site["id"] == "old-mill" and site["levels"] == ["Ground floor", "Upper"]
    lay = sites.layout(site)
    assert lay["levels"] == ["Ground floor"]                # the unexplored loft isn't drawn
    assert lay["centres"]["b"] == [lay["size"][0] / 2, lay["size"][1] / 2]
    out = sites.render(site, tmp_path / "mill.jpg")
    assert out.exists()
    with pytest.raises(sites.SiteError):
        sites.validate({"title": "X", "place": "Y", "rooms": [{"id": "a", "name": "A", "x": 0, "y": 0, "w": 1, "h": 1,
                                                                "features": [{"kind": "dragon", "at": [0, 0]}]}]})


def test_region_specs_are_validated_and_framed():
    from ringwraith import regions
    g = regions.build({"title": "The Weather Hills", "anchor": "Weathertop",
                       "places": [{"name": "Weathertop", "at": [0, 0], "kind": "ruin"},
                                  {"name": "Post", "at": [-6, -6], "kind": "tower"}],
                       "roads": [{"name": "the Road", "points": [[-20, 3], [20, 4]], "width": "main"}],
                       "downs": [{"name": "Hills", "area": [[-4, -14], [3, -14], [4, -3]]}],
                       "pointers": [{"text": "to Bree", "at": [-15, 3], "side": "west"}]})
    assert g["id"] == "the-weather-hills" and g["parent"] == "eriador" and g["anchor"] == {"place": "Weathertop", "at": [0, 0]}
    x0, y0, x1, y1 = g["bounds"]
    assert x0 <= -15 and y0 <= -14 and x1 >= 4 and (x1 - x0) <= 45
    assert 50 <= g["px_per_mile"] <= 140
    for bad in ({"title": "X"},                                                           # no anchor
                {"title": "X", "anchor": "Y", "places": [{"name": "Z", "at": [0, 0], "kind": "castle"}]},
                {"title": "X", "anchor": "Y", "places": [], "roads": [{"points": [[0, 0]]}]},
                {"title": "X", "anchor": "Y", "places": [], "lakes": [{"area": [[0, 0], [1, 1]]}]}):
        with pytest.raises(regions.RegionError):
            regions.build(bad)


def test_routes_follow_a_road_when_it_costs_little_more(hexes, monkeypatch):
    # open land from (0,4) to (4,4); a road bends one row north, (0,3)…(4,3)
    road = {(c, 3): "Old Road" for c in range(0, 5)}
    monkeypatch.setattr(geo.routing, "road_hexes", lambda: road)
    path = geo.hex_path((0, 4), (4, 3))
    assert sum(1 for h in path if h in road) >= len(path) - 2      # it takes the road
    assert len(path) - 1 <= geo.hex_distance((0, 4), (4, 3)) + 1     # and isn't much longer
    # a road far off the way is ignored
    far = {(c, 0): "Far Road" for c in range(0, 5)}
    monkeypatch.setattr(geo.routing, "road_hexes", lambda: far)
    assert not set(geo.hex_path((0, 4), (4, 4))) & set(far)
