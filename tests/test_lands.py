"""Maps and journeys for a tale set beyond the Eriador map: a land map with no parent, regions inside it,
journeys counted by miles with their lands and roads, and the drawing at land scale."""

import pytest

from ringwraith import campaign as cp
from ringwraith import geo, regions, vault

LAND = {
    "title": "The Test March", "parent": "none", "scale": "land", "land": "wild", "anchor": "Hold",
    "places": [{"name": "Hold", "at": [0, 0], "kind": "town"}, {"name": "Far Farm", "at": [120, 40], "kind": "village"},
               {"name": "Old Tower", "at": [40, 90], "kind": "tower"}],
    "roads": [{"name": "the March Road", "points": [[0, 0], [60, 10], [120, 40]], "width": "main"}],
    "mountains": [{"name": "the Grey Teeth", "area": [[60, 60], [110, 60], [110, 120], [60, 120]]}],
    "lands": [{"type": "dark", "area": [[20, 70], [55, 70], [55, 110], [20, 110]]}],
    "forests": [{"name": "Thornwood", "area": [[-30, 20], [10, 20], [10, 60], [-30, 60]], "label_at": [-10, 40]}],
}


@pytest.fixture
def camp(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "vaults_root", lambda c=None: tmp_path)
    vault.create("beyond", name="Beyond", root=tmp_path)
    geo._base_maps.cache_clear()
    yield tmp_path
    geo._base_maps.cache_clear()


def test_land_map_stands_alone_and_journeys_count_by_miles(camp):
    g = regions.create(dict(LAND))
    assert g["parent"] is None and g["scale"] == "land" and g["px_per_mile"] < 50
    assert (camp / "beyond" / "90 Assets" / "maps" / "the-test-march.jpg").exists()
    plan = geo.journey_plan("Hold", "Far Farm")
    assert plan["map"] == "the-test-march" and 124 <= plan["miles"] <= 128
    # counted on the land map's own 20-mile grid: the hexes entered (departure not counted), like Eriador
    assert plan["hex_cells"] and plan["hexes"] == len(plan["hex_cells"]) - 1 and 5 <= plan["hexes"] <= 8
    assert plan["grid"][0] == pytest.approx(20 * g["px_per_mile"], rel=0.01)       # a hex is 20 miles across
    assert plan["road_hexes"] == plan["hexes"] and set(plan["lands"]) == {"wild"}
    off = geo.journey_plan("Hold", "Old Tower")                          # through the dark country, off the road
    assert off["lands_in_order"][-1] == "dark" and off["road_hexes"] < off["hexes"]
    across = geo.journey_plan("Far Farm", "Old Tower", via=[])          # straight over the mountains
    assert "impassable" in across["lands_in_order"]


def test_regions_nest_inside_a_land_map(camp):
    regions.create(dict(LAND))
    regions.create({"title": "Far Farm Lands", "parent": "the-test-march", "anchor": "Far Farm",
                    "places": [{"name": "Far Farm", "at": [0, 0], "kind": "village"},
                               {"name": "Mill", "at": [3, -2], "kind": "hamlet"}]})
    assert geo.chain("far-farm-lands") == ["far-farm-lands", "the-test-march"]
    local = geo.journey_plan("Far Farm", "Mill")
    assert local["map"] == "far-farm-lands" and local["hexes"] == 1
    long = geo.journey_plan("Mill", "Hold")                              # counted on the land map
    assert long["map"] == "the-test-march" and long["hexes"] >= 6


def test_land_map_anchor_must_be_one_of_its_places(camp):
    bad = dict(LAND, anchor="Nowhere")
    with pytest.raises(regions.RegionError):
        regions.create(bad)


def test_cli_draws_a_land_map_from_its_yaml(camp, monkeypatch):
    import yaml
    from ringwraith import cli
    f = camp / "beyond" / ".ringwraith" / "regions" / "the-test-march.yaml"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(dict(LAND)), encoding="utf-8")        # as Ringwraith writes it: a plain spec
    monkeypatch.setattr(cp, "active_slug", lambda root=None: "beyond")
    assert cli.main(["map", "region", "the-test-march"]) == 0
    g = regions.load("the-test-march")
    assert g["parent"] is None and g["scale"] == "land" and g["land"] == "wild" and g["mountains"]


def test_moves_follow_roads_and_only_real_journeys_are_pictured(camp):
    regions.create(dict(LAND))
    leg = geo.move(["Company"], "Far Farm", frm="Hold")
    assert len(leg["path"]) > 2 and leg["stops"] == [leg["path"][0], leg["path"][-1]]   # along the March Road
    assert geo.is_notable(leg)
    f = geo.move_picture(leg)
    assert f.exists() and f.parent.name == "moves"
    regions.create({"title": "Far Farm Lands", "parent": "the-test-march", "anchor": "Far Farm",
                    "places": [{"name": "Far Farm", "at": [0, 0], "kind": "village"},
                               {"name": "Byre", "at": [0.4, 0.3], "kind": "hamlet"}]})
    step = geo.move(["Company"], "Byre", frm="Far Farm")
    assert not geo.is_notable(step)                                   # a step across the farm: no picture
    assert geo.session_maps(0) and all("far-farm-lands" not in p.name for p in geo.session_maps(0))


def test_a_place_beyond_a_local_map_goes_on_the_map_that_holds_it(camp):
    regions.create(dict(LAND))
    regions.create({"title": "Far Farm Lands", "parent": "the-test-march", "anchor": "Far Farm",
                    "places": [{"name": "Far Farm", "at": [0, 0], "kind": "village"},
                               {"name": "Byre", "at": [0.4, 0.3], "kind": "hamlet"}]})
    p = geo.add_place("Distant Cairn", near="Byre", bearing="W", miles=80)
    assert p["map"] == "the-test-march" and geo.inside(p["map"], p["at"])
    plan = geo.journey_plan("Byre", "Distant Cairn")
    assert plan["map"] == "the-test-march" and plan["hexes"] >= 3
