import pytest

pytest.importorskip("claude_agent_sdk")

from ringwraith.web import fight as fg  # noqa: E402


@pytest.fixture(autouse=True)
def private(tmp_path, monkeypatch):
    monkeypatch.setattr(fg.cp, "private_dir", lambda *a, **k: tmp_path)


def test_player_sees_words_and_bars_until_the_hero_knows_the_numbers():
    fg.start("combat", "At the milestone", [{"name": "Orc-chieftain", "endurance": 18, "hate": 4, "parry": 1,
                                             "armour": 2, "features": ["Fierce"], "weapons": ["broad-bladed sword"]}])
    v = fg.public_view(fg.load())["foes"][0]
    assert v["word"] == "fresh" and v["bar"] == 1.0 and v["known"] == {} and v["features"] == ["Fierce"]
    st = fg.update({"foes": [{"name": "Orc-chieftain", "endurance": 4, "hate": 0, "wounded": True,
                              "abilities": [{"name": "Bellowing Rage", "text": "rallies its kin"}]}]})
    v = fg.public_view(st)["foes"][0]
    assert v["word"] == "badly hurt" and set(v["marks"]) == {"Wounded", "Weary"}     # Hate spent shows as Weary
    assert v["abilities"][0]["name"] == "Bellowing Rage" and v["known"] == {}
    st = fg.update({"foes": [{"name": "Orc-chieftain", "known": ["endurance", "parry"],
                              "abilities": ["Bellowing Rage"]}]})              # an ability is listed once
    v = fg.public_view(st)["foes"][0]
    # Endurance and Hate stay a bar and a word for the player; Parry, Armour and Might can become known
    assert v["known"] == {"Parry": "+1"} and len(v["abilities"]) == 1
    assert "Endurance 4/18" in fg.summary(st) and "Hate 0/4" in fg.summary(st)   # the Loremaster sees everything
    st = fg.update({"foes": [{"name": "Orc-chieftain", "state": "fled"}], "log": "The chieftain flees."})
    assert fg.public_view(st)["foes"][0]["word"] == "fled" and fg.public_view(st)["log"] == ["The chieftain flees."]
    assert fg.end("Driven off.")["outcome"] == "Driven off." and fg.load() is None


def test_battle_shows_how_the_war_party_holds():
    st = fg.start("battle", "The Dike", [{"name": "Brigands", "count": 20}],
                  {"resistance": 12, "might": 2, "advantages": ["high ground"], "complications": ["dark"]})
    b = fg.public_view(st)["battle"]
    assert b["word"] == "holding" and [a["name"] for a in b["advantages"]] == ["high ground"] and "12" not in str(b)
    st = fg.update({"battle": {"resistance": 3, "clash": 3}})
    assert fg.public_view(st)["battle"]["word"] == "breaking"
    with pytest.raises(fg.FightError):
        fg.update({"foes": [{"name": "Brigands", "state": "dancing"}]})


def test_weapons_given_with_stats_show_only_their_names():
    fg.start("combat", "At the ford", [{"name": "Brann", "weapons": [{"name": "Long axe", "rating": 3, "damage": 5}],
                                        "features": "Brutal"}])
    v = fg.public_view(fg.load())["foes"][0]
    assert v["weapons"] == ["Long axe"] and v["features"] == ["Brutal"]
    st = fg.update({"foes": [{"name": "Brann", "weapons": [{"name": "Knife", "injury": 14}]}]})
    assert fg.public_view(st)["foes"][0]["weapons"] == ["Knife"]


def test_the_rank_and_file_hold_as_the_war_party_does():
    fg.start("battle", "At the ford", [{"name": "Brann", "endurance": 18}, {"name": "Riders", "count": 18}],
             battle={"resistance": 3, "resistance_max": 7})
    v = fg.public_view(fg.load())
    riders = v["foes"][1]
    assert v["battle"]["word"] == "wavering" and (riders["bar"], riders["word"]) == (v["battle"]["bar"], "wavering")
    assert v["foes"][0]["word"] == "fresh"                   # a foe with its own Endurance keeps its own


def test_advantages_carry_their_effect_and_story():
    fg.start("battle", "At the ford", [], battle={"resistance": 7, "advantages": [
        {"name": "The beck ford", "effect": "+1d", "persistent": True, "text": "They must come at you through water."},
        "Bows in the dark (persistent) (+1d)"], "complications": ["Brann, a Lesser Archfoe (-1d)"]})
    b = fg.public_view(fg.load())["battle"]
    assert b["advantages"][0] == {"name": "The beck ford", "effect": "+1d", "persistent": True,
                                  "text": "They must come at you through water."}
    assert b["advantages"][1] == {"name": "Bows in the dark", "effect": "+1d", "persistent": True, "text": ""}
    assert b["complications"][0]["name"] == "Brann, a Lesser Archfoe" and b["complications"][0]["effect"] == "−1d"
    assert "The beck ford (+1d) (persistent)" in fg.summary(fg.load())


def test_an_advantage_written_all_in_one_line_is_split():
    fg.start("battle", "At the ford", [], battle={"resistance": 7, "advantages": [
        {"name": "Loose shoes (persistent, +1d on Clash rolls): the horses stumble on the stones."}],
        "complications": ["Brann, a Lesser Archfoe (-1d on Clash rolls while he fights): his voice holds them."]})
    b = fg.public_view(fg.load())["battle"]
    assert b["advantages"][0] == {"name": "Loose shoes", "effect": "+1d", "persistent": True,
                                  "text": "The horses stumble on the stones."}
    assert b["complications"][0] == {"name": "Brann, a Lesser Archfoe", "effect": "−1d", "persistent": False,
                                     "text": "His voice holds them."}
