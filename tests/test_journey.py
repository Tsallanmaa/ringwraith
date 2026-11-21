"""The Journey panel's tracker: the route, the moments of the road, fatigue, and the journey note it writes."""

import pytest

from ringwraith import campaign as cp
from ringwraith import vault
from ringwraith.web import journey as jr


@pytest.fixture
def camp(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "vaults_root", lambda c=None: tmp_path)
    vault.create("road", name="Road", root=tmp_path)
    monkeypatch.setattr(cp, "active_slug", lambda root=None: "road")
    h = vault.new_note("hero", "Tomas")
    fm, body = vault.read_note(h)
    fm["fatigue"] = 1
    vault.write_note(h, fm, body)
    st = tmp_path / "road" / ".ringwraith" / "state.md"
    fm, body = vault.read_note(st)
    fm["day"] = 5
    vault.write_note(st, fm, body)
    return tmp_path / "road"


PLAN = {"from": "Bree", "to": "Rivendell", "hexes": 4, "miles": 80,
        "road_in_order": ["East Road", "East Road", None, None],
        "lands_in_order": ["border", "wild", "wild", "dark"]}       # Loremaster-only: must never reach the panel


def test_a_journey_from_setting_out_to_arrival(camp):
    s = jr.start("Bree", "Rivendell", season="spring", mode="on foot", plan=PLAN)
    assert s["road"] == [True, True, False, False] and s["hexes"] == 4
    assert "land" not in str(jr.public_view(s)).lower().replace("lands", "x") and "dark" not in str(jr.public_view(s))
    assert vault.read_note(camp / ".ringwraith" / "state.md")[0]["journey"] == "[[Bree to Rivendell]]"

    jr.log({"kind": "march", "title": "Two good days on the Road", "hexes_done": 2})
    jr.log({"kind": "interlude", "title": "The camp under Weathertop", "text": "Sid speaks of his brother."})
    s, e = jr.log({"kind": "event", "title": "Chance meeting: a lone hunter", "at": "The Lone-lands", "who": "the Band",
                   "outcome": "a fair trade of news", "fatigue_hero": 1, "fatigue_band": 1})
    assert e["hex"] == 2 and s["fatigue"] == {"hero": 1, "band": 1}
    assert vault.read_note(vault.hero_note())[0]["fatigue"] == 2          # the hero's fatigue goes on the sheet

    view = jr.public_view(s)
    assert [x["kind"] for x in view["log"]] == ["march", "interlude", "event"] and view["done"] == 2

    note = camp / s["note"]
    fm, body = vault.read_note(note)
    assert fm["status"] == "underway" and fm["hexes"] == 2 and fm["fatigue_gained"] == 1 and fm["route"] == ["[[The Lone-lands]]"]
    assert "Chance meeting: a lone hunter" in body and "Sid speaks of his brother." in body

    done = jr.end("Over the Ford of Bruinen at dusk.")
    assert done["status"] == "arrived" and jr.load() is None
    fm, body = vault.read_note(note)
    assert fm["status"] == "arrived" and fm["hexes"] == 4 and "Arrived" in body
    assert vault.read_note(camp / ".ringwraith" / "state.md")[0]["journey"] == ""


def test_one_journey_at_a_time_and_moments_need_a_journey(camp):
    with pytest.raises(jr.JourneyError):
        jr.log({"kind": "event", "title": "x"})
    jr.start("Bree", "Archet", hexes=1)
    with pytest.raises(jr.JourneyError):
        jr.start("Bree", "Staddle")
    with pytest.raises(jr.JourneyError):
        jr.log({"kind": "battle", "title": "x"})


def test_the_chronicle_closes_a_journey_and_shows_cutaways():
    from ringwraith import chronicle
    md = chronicle.render([
        {"t": "journey_mark", "day": 6, "at": "Weathertop", "title": "The camp under Weathertop"},
        {"t": "narration", "text": "Sid stares into the fire.\n\n> CUTAWAY: Far behind, Brann's riders light no fires.\n\n"
                                   "> OOC: Fatigue +1.\n\nWhat does Tomas do?"},
        {"t": "journey_end", "title": "Bree to Rivendell", "status": "arrived", "days": 9,
         "fatigue": {"hero": 2, "band": 1}, "outcome": "Over the Ford."}])
    assert "*— Day 6, Weathertop: The camp under Weathertop —*" in md
    assert "> [!cutaway] Elsewhere…\n> Far behind, Brann's riders light no fires." in md
    assert "> [!loremaster]- Loremaster\n> Fatigue +1." in md
    assert "> [!journey] Bree to Rivendell\n> 9 days on the road; hero fatigue +2, Band fatigue +1. Over the Ford." in md


def test_a_cutaway_stays_in_the_story_when_mechanics_are_tidied():
    from ringwraith.web.narration import tidy_story
    text = ("Sid stares into the fire.\n\n> CUTAWAY: Far behind, the riders light no fires.\n\n"
            "Tomas has 24 Endurance and 4 Hope.\n\nWhat does Tomas do?")
    out, moved = tidy_story(text)
    assert moved and out.index("> CUTAWAY:") < out.index("> OOC:")


def test_the_compass_cutaways_setting():
    from ringwraith.tale import cutaways_on
    assert not cutaways_on({}) and not cutaways_on({"cutaways": "off"}) and not cutaways_on({"cutaways": False})
    assert cutaways_on({"cutaways": "on"}) and cutaways_on({"cutaways": True})
