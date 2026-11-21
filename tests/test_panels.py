import pytest

pytest.importorskip("claude_agent_sdk")

from ringwraith import vault  # noqa: E402
from ringwraith.web import engine as eng  # noqa: E402
from ringwraith.web import gametools, panels, views  # noqa: E402,F401

HERO = """---
type: hero
name: Test Hero
endurance: {current: 20, max: 24}
hope: {current: 8, max: 10}
shadow: {points: 1, scars: 0}
fatigue: 0
conditions: {wounded: false}
---
# Test Hero
"""

THREADS = """---
type: threads
---
# Threads

## Open
- **The riders go north (day 17).** [[Brann]]'s muster rides to [[Deadmen's Dike|the Dike]].
- A loose end without a title

## Resolved
- **Who cut the Eye?** [[Ludo Quarrender]].
"""


@pytest.fixture
def vault_dir(tmp_path, monkeypatch):
    (tmp_path / "10 Campaign").mkdir()
    (tmp_path / "10 Campaign" / "Threads.md").write_text(THREADS, encoding="utf-8")
    hero = tmp_path / "hero.md"
    hero.write_text(HERO, encoding="utf-8")
    monkeypatch.setattr(panels.cp, "campaign_dir", lambda *a, **k: tmp_path)
    monkeypatch.setattr(panels.vault, "hero_note", lambda *a, **k: hero)
    return tmp_path


def test_adjust_clamps_writes_and_toggles(vault_dir):
    hero = vault_dir / "hero.md"
    assert panels.adjust("hope", 1) == {"key": "hope", "label": "Hope", "old": 8, "new": 9}
    assert panels.adjust("hope", 5)["new"] == 10            # never above the maximum
    assert panels.adjust("hope", 1) is None                  # already full: nothing changes
    assert panels.adjust("endurance", -30)["new"] == 0       # never below zero
    assert panels.adjust("shadow", 2)["new"] == 3            # no maximum
    assert panels.adjust("wounded")["new"] == "on"
    fm = vault.read_note(hero)[0]
    assert fm["hope"]["current"] == 10 and fm["endurance"]["current"] == 0 and fm["conditions"]["wounded"] is True
    with pytest.raises(panels.AdjustError):
        panels.adjust("readiness", 1)


def test_hand_edits_are_merged_and_told_once(vault_dir, monkeypatch):
    e = eng.Engine.__new__(eng.Engine)
    e.sheet_changes, e.settings_changes = {}, {}
    e.player_changed(panels.adjust("hope", -1))
    total = e.player_changed(panels.adjust("hope", -1))
    assert panels.describe(total) == "Hope 8 → 6"
    e.player_changed(panels.adjust("shadow", 1))
    e.player_changed(panels.adjust("shadow", -1))             # back where it was: nothing to tell
    monkeypatch.setattr(eng.gametools, "current_scene", lambda: "Bree")
    monkeypatch.setattr("ringwraith.clock.state", lambda: (None, {"day": 11, "time": "night"}))
    note = e._table_note()
    assert "Hope 8 → 6" in note and "Shadow" not in note
    assert "changed the hero sheet" not in e._table_note()    # told once


def test_settings_changes_are_told_once_and_a_new_model_waits_for_the_next_turn(vault_dir, monkeypatch):
    e = eng.Engine.__new__(eng.Engine)
    e.sheet_changes, e.settings_changes, e._reconnect = {}, {}, False
    e.settings_changed([{"key": "dice.mode", "label": "Dice", "value": "Your own dice"}])
    assert not e._reconnect
    e.settings_changed([{"key": "table.model", "label": "Loremaster's model", "value": "Sonnet"}])
    assert e._reconnect
    monkeypatch.setattr(eng.gametools, "current_scene", lambda: "Bree")
    monkeypatch.setattr("ringwraith.clock.state", lambda: (None, {"day": 11, "time": "night"}))
    note = e._table_note()
    assert "Dice: Your own dice" in note and "Loremaster's model: Sonnet" in note
    assert "changed the campaign settings" not in e._table_note()


def test_threads_parse_titles_links_and_resolved(vault_dir):
    t = panels.threads()
    assert t["open"][0] == {"title": "The riders go north (day 17)",
                            "text": "Brann's muster rides to the Dike."}
    assert t["open"][1] == {"title": "A loose end without a title", "text": ""}
    assert t["resolved"] == [{"title": "Who cut the Eye?", "text": "Ludo Quarrender."}]


def test_map_view_lists_only_the_tales_maps(tmp_path, monkeypatch):
    (tmp_path / "90 Assets" / "maps").mkdir(parents=True)
    for m in ("eriador", "bree-land", "land", "dale"):
        (tmp_path / "90 Assets" / "maps" / f"{m}.jpg").write_bytes(b"x")
    monkeypatch.setattr(views.cp, "campaign_dir", lambda *a, **k: tmp_path)
    img = lambda m: f"/assets/maps/{m}.jpg"  # noqa: E731
    snap = {"maps": {"eriador": {"parent": None, "image": img("eriador")},
                     "bree-land": {"parent": "eriador", "image": img("bree-land")},
                     "land": {"parent": None, "image": img("land")},
                     "dale": {"parent": "land", "image": img("dale")},
                     "nowhere": {"parent": "land", "image": img("nowhere")}},            # no picture yet
            "places": [{"name": "Bree", "map": "bree-land", "builtin": True}],
            "legs": [], "tokens": [{"name": "Company", "map": "dale"}], "plan": None, "grid": {"map": "eriador"}}
    views._only_the_tales_maps(snap)
    assert set(snap["maps"]) == {"land", "dale"}                  # Eriador's tree is untouched by this tale
    assert snap["places"] == [] and snap["grid"] is None
    # before anything is placed, every map with a picture is offered
    snap2 = {"maps": {"eriador": {"parent": None, "image": img("eriador")}}, "places": [], "legs": [],
             "tokens": [], "plan": None}
    views._only_the_tales_maps(snap2)
    assert set(snap2["maps"]) == {"eriador"}


def test_hero_traits_carry_what_they_do(monkeypatch, tmp_path):
    atoms = tmp_path / "atoms"
    (atoms / "virtues").mkdir(parents=True)
    (atoms / "virtues" / "prowess.md").write_text("---\nkind: virtue\n---\n# Prowess\n\nPicked at a rank.\n\n"
                                                 "## Effect\n\nSteadier in a test. [core p.1]\n", encoding="utf-8")
    (atoms / "cultures").mkdir()
    (atoms / "cultures" / "men-of-bree.md").write_text("# Men of Bree\n\n## Cultural Blessing: Bree-blood\n\n"
                                                      "Good company. [core p.1]\n", encoding="utf-8")
    monkeypatch.setattr(panels, "_lore_dir", lambda: atoms)
    t = panels.hero_traits({"culture": "Men of Bree", "virtues": ["Prowess (STRENGTH TN -1)"],
                            "distinctive_features": ["True-hearted"]})
    assert t["virtues"] == [{"name": "Prowess (STRENGTH TN -1)", "text": "Steadier in a test."}]
    assert t["blessing"] == {"name": "Bree-blood", "text": "Good company."}
    assert "Inspired" in t["features"][0]["text"] and t["rewards"] == []
