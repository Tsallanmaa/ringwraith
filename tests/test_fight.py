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
    assert b["word"] == "holding" and b["advantages"] == ["high ground"] and "12" not in str(b)
    st = fg.update({"battle": {"resistance": 3, "clash": 3}})
    assert fg.public_view(st)["battle"]["word"] == "breaking"
    with pytest.raises(fg.FightError):
        fg.update({"foes": [{"name": "Brigands", "state": "dancing"}]})
