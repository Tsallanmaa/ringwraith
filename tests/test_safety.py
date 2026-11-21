"""Security and data safety: the websocket origin check, atomic writes and the data lock, the art worker
lock, art attaching to notes, encounter sorting, deadline names, and map files that are broken or unbuilt."""

import threading

import pytest
import yaml

from ringwraith import artqueue, clock, fileio, geo, regions, vault
from ringwraith import campaign as cp


# ------------------------------------------------------------------ the websocket's origin
def test_only_the_tables_own_page_may_open_the_websocket():
    from ringwraith.web.server import local_origin
    assert local_origin("http://127.0.0.1:2965", "127.0.0.1:2965")
    assert local_origin("http://localhost:2965", "localhost:2965")
    assert not local_origin("https://evil.example", "127.0.0.1:2965")           # another web site
    assert not local_origin("http://localhost:8080", "127.0.0.1:2965")          # another local app
    assert not local_origin(None, "127.0.0.1:2965")                             # no Origin at all
    assert not local_origin("null", "127.0.0.1:2965")                           # a sandboxed page or file


# ------------------------------------------------------------------ atomic writes and the lock
def test_atomic_write_replaces_the_file_and_leaves_no_temp(tmp_path):
    f = tmp_path / "geo.yaml"
    f.write_text("old", encoding="utf-8")
    fileio.atomic_write(f, "new\n")
    assert f.read_text(encoding="utf-8") == "new\n"
    assert [p.name for p in tmp_path.iterdir()] == ["geo.yaml"]


def test_the_data_lock_is_reentrant_and_serialises_threads():
    order = []

    def writer(tag):
        with fileio.locked():
            with fileio.locked():                 # a locked function calling another
                order.append(f"{tag}-in")
                order.append(f"{tag}-out")

    ts = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    # each writer's in/out pair is never interleaved with another's
    assert all(order[i].split("-")[0] == order[i + 1].split("-")[0] for i in range(0, len(order), 2))


def test_a_held_lock_file_is_seen_as_held(tmp_path):
    lock = tmp_path / "art-worker.lock"
    assert not fileio.is_held(lock)
    fd = fileio.hold(lock)
    try:
        assert fd is not None and fileio.is_held(lock) and fileio.hold(lock) is None
    finally:
        fileio.release(fd)
    assert not fileio.is_held(lock)


# ------------------------------------------------------------------ a campaign to work in
@pytest.fixture
def camp(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "vaults_root", lambda c=None: tmp_path)
    vault.create("safe", name="Safe", root=tmp_path)
    monkeypatch.setattr(cp, "active_slug", lambda root=None: "safe")
    geo._base_maps.cache_clear()
    geo._cache.clear()
    yield tmp_path / "safe"
    geo._base_maps.cache_clear()
    geo._cache.clear()


def test_a_second_art_worker_does_not_start_while_one_is_rendering(camp):
    paths = artqueue._paths()
    fd = fileio.hold(paths["lock"])              # a worker in the middle of a long render
    try:
        assert artqueue.worker_alive()
        said = []
        assert artqueue.run_worker(once=True, log=said.append) == 0
        assert said == ["another art worker is already running"]
    finally:
        fileio.release(fd)
    assert not artqueue.worker_alive()


# ------------------------------------------------------------------ art attaching to notes
def test_a_portrait_replaces_only_the_picture_under_the_title():
    body = ("\n# Sid\n\n![[90 Assets/portraits/sid-old.png|320]]\n\nA drover.\n\n## Deeds\n"
            "![[90 Assets/scenes/the-wolves.png]]\n")
    fm, out = artqueue.attach_image({"name": "Sid"}, body, "90 Assets/portraits/sid-new.png", "portrait")
    assert fm["image"] == "[[90 Assets/portraits/sid-new.png]]"
    assert "sid-old" not in out and "![[90 Assets/portraits/sid-new.png|320]]" in out
    assert "![[90 Assets/scenes/the-wolves.png]]" in out                         # other pictures stay
    assert out.index("sid-new") < out.index("A drover.")


def test_a_scene_painting_is_added_and_never_becomes_the_notes_image():
    body = "\n# Session 004\n\n![[90 Assets/scenes/a.png]]\n\n## As it was played\n![[90 Assets/portraits/b.png|220]]\n"
    fm, out = artqueue.attach_image({"image": "[[x.png]]"}, body, "90 Assets/scenes/c.png", "scene")
    assert fm == {"image": "[[x.png]]"}
    assert all(s in out for s in ("scenes/a.png", "portraits/b.png", "![[90 Assets/scenes/c.png]]"))


# ------------------------------------------------------------------ encounters keep the prose around them
def test_sorting_encounters_keeps_the_introduction_and_prose():
    body = ("\n# Sid\n\n## Deeds\nSid has ridden with the Order since the spring.\n\n"
            "- **Session 2, day 6:** Held the door.\n"
            "  He would not give way.\n"
            "- **Session 1, day 2:** Found the wolves' trail.\n\n"
            "He keeps his own counsel.\n\n## Notes\nx\n")
    out = vault.sort_encounters(body, "## Deeds")
    assert "Sid has ridden with the Order since the spring." in out
    assert "He keeps his own counsel." in out
    assert out.index("Session 1, day 2") < out.index("Session 2, day 6") < out.index("He would not give way")
    assert out.index("since the spring") < out.index("Session 1, day 2")
    assert out.rstrip().endswith("## Notes\nx")


# ------------------------------------------------------------------ deadline names
def test_a_new_deadline_never_overwrites_one_it_merely_prefixes(camp):
    clock.add_deadline("Bree council", due=20)
    clock.add_deadline("Bree", due=12)
    names = sorted(d["name"] for d in clock.state()[1]["deadlines"])
    assert names == ["Bree", "Bree council"]
    with pytest.raises(ValueError):
        clock.remove("deadlines", "B")                                         # ambiguous
    assert clock.remove("deadlines", "Bree")["name"] == "Bree"                 # exact wins
    assert clock.remove("deadlines", "Bree c")["name"] == "Bree council"       # unique prefix


# ------------------------------------------------------------------ map files that are unbuilt or broken
LAND = {"title": "The Test March", "parent": "none", "scale": "land", "land": "wild", "anchor": "Hold",
        "places": [{"name": "Hold", "at": [0, 0], "kind": "town"}, {"name": "Far Farm", "at": [120, 40], "kind": "village"}]}


def test_an_unbuilt_region_spec_or_a_broken_file_does_not_take_the_maps_down(camp):
    from ringwraith import cli
    regions.create(dict(LAND))
    rdir = camp / ".ringwraith" / "regions"
    # Ringwraith writes a region spec (miles, no bounds) before building it, as CLAUDE.md says
    spec = {"title": "Far Farm Lands", "parent": "the-test-march", "anchor": "Far Farm",
            "places": [{"name": "Far Farm", "at": [0, 0], "kind": "village"}, {"name": "Mill", "at": [3, -2], "kind": "hamlet"}]}
    (rdir / "far-farm-lands.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    (rdir / "broken.yaml").write_text("title: [unclosed\n", encoding="utf-8")
    assert "the-test-march" in geo.maps() and "far-farm-lands" not in geo.maps()
    assert geo.find("Hold")[1] == "the-test-march"                             # map calls still work
    assert cli.main(["map", "region", "far-farm-lands"]) == 0                  # and the spec can be built
    assert geo.chain("far-farm-lands") == ["far-farm-lands", "the-test-march"]


def test_loaded_map_data_is_a_fresh_copy_and_follows_the_file(camp):
    a = geo.load()
    a["places"]["Scribble"] = {"map": "x", "at": [0, 0]}                       # a caller changing its copy
    assert "Scribble" not in geo.load()["places"]
    d = geo.load()
    d["states"]["Somewhere"] = "heard"
    geo.save(d)
    assert geo.load()["states"]["Somewhere"] == "heard"                        # a save is seen at once


# ------------------------------------------------------------------ Hope is spent only on a real roll
def test_bad_physical_dice_spend_no_hope(camp, monkeypatch):
    import asyncio

    import claude_agent_sdk
    from ringwraith.web import gametools

    h = vault.new_note("hero", "Tomas")
    fm, body = vault.read_note(h)
    fm["hope"] = {"max": 10, "current": 4}
    vault.write_note(h, fm, body)
    captured, events = {}, []
    real = claude_agent_sdk.create_sdk_mcp_server
    monkeypatch.setattr(gametools, "create_sdk_mcp_server",
                        lambda name, version, tools: (captured.update({t.name: t for t in tools}),
                                                      real(name=name, version=version, tools=tools))[1])
    monkeypatch.setattr(gametools.ops, "log_roll", lambda *a, **k: None)

    class Hub:
        async def ask(self, kind, event):          # the player spends Hope and enters a Success die of 7
            return {"action": "hope", "_id": "r1", "feat": ["5"], "success": [2, 4, 7]}

        async def emit(self, e):
            events.append(e)

    gametools.build(Hub(), {"story_since_roll": True})
    args = {"who": "Tomas", "what": "Insight", "dice": 2, "tn": 14, "stakes": "x"}
    r = asyncio.run(captured["request_roll"].handler(args))
    assert r.get("is_error") and "no Hope spent" in r["content"][0]["text"]
    assert vault.read_note(h)[0]["hope"]["current"] == 4                       # still 4
    assert {"t": "roll_cancelled", "id": "r1"} in events                       # the tray is closed, not hung


# ------------------------------------------------------------------ "you are here"
def test_the_current_place_follows_the_hero(tmp_path, monkeypatch):
    world = {"id": "world", "title": "World", "size": [1000, 800], "miles_per_px": 1.0,
             "places_px": {"Town": [500, 400], "Tower": [700, 400], "Mill": [300, 400]}}
    monkeypatch.setattr(geo.registry, "maps", lambda: {"world": world})
    (tmp_path / "c1" / ".ringwraith").mkdir(parents=True)
    (tmp_path / "c1" / ".ringwraith" / "state.md").write_text("---\nday: 3\nsession: 2\n---\n", encoding="utf-8")
    kw = {"slug": "c1", "root": tmp_path}
    geo.place_at("Town", ["Hero"], **kw)
    geo.place_at("Mill", ["Ally"], **kw)
    geo.move(["Hero", "Ally"], "Tower", hero="Hero", **kw)          # two groups from two places
    assert geo.load(**kw)["states"]["Tower"] == "current"
    geo.move(["Ally"], "Mill", hero="Hero", **kw)                  # an Ally's errand
    st = geo.load(**kw)["states"]
    assert st["Tower"] == "current" and st["Mill"] == "visited"
    geo.move(["Ally"], "Tower", hero="Hero", **kw)                 # the Ally comes back to the hero
    assert geo.load(**kw)["states"]["Tower"] == "current"
