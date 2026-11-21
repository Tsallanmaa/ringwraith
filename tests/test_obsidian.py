import re
import json

import pytest

from ringwraith import obsidian as ob


def test_shire_year_has_365_days_and_dates_roll_over():
    assert ob.YEAR_DAYS == 365
    s = {"calendar": {"day1": "1 Astron 2965"}}
    assert ob.tale_date(1, s) == {"year": 2965, "month": ob._month_index("Astron"), "day": 1}
    assert ob.show(ob.tale_date(17, s)) == "17 Astron 2965"
    assert ob.show(ob.tale_date(31, s)) == "1 Thrimidge 2965"
    # the end of Forelithe runs into the Lithe days and Midyear's Day, then Afterlithe
    s = {"calendar": {"day1": "30 Forelithe 2965"}}
    assert [ob.show(ob.tale_date(d, s)) for d in (1, 2, 3, 4, 5)] == [
        "30 Forelithe 2965", "1 Lithe, 2965", "Midyear's Day, 2965", "2 Lithe, 2965", "1 Afterlithe 2965"]
    # 1 Yule ends the year and 2 Yule begins the next
    s = {"calendar": {"day1": "30 Foreyule 2965"}}
    assert [ob.show(ob.tale_date(d, s)) for d in (2, 3, 4)] == ["1 Yule, 2965", "2 Yule, 2966", "1 Afteryule 2966"]
    assert ob.fc_date(ob.tale_date(4, s)) == "2966-2-1"           # Calendarium: 1-based months


def test_parse_date_forms_and_errors():
    assert ob.parse_date("Astron 3 2965") == ob.parse_date("3 Astron 2965") == ob.parse_date("2965-Astron-3")
    assert ob.parse_date("1 midyear 2965")["month"] == ob._month_index("Midyear's Day")
    with pytest.raises(ob.ObsidianError):
        ob.parse_date("31 Astron 2965")
    with pytest.raises(ob.ObsidianError):
        ob.parse_date("Smeagolday")


def test_setup_merges_into_existing_plugin_settings(tmp_path):
    cal = tmp_path / ".obsidian" / "plugins" / "calendarium" / "data.json"
    cal.parent.mkdir(parents=True)
    cal.write_text(json.dumps({"calendars": [{"id": "other", "name": "Gregorian"}], "dateFormat": "YYYY-MM-DD"}))
    sb = tmp_path / ".obsidian" / "plugins" / "obsidian-5e-statblocks" / "data.json"
    sb.parent.mkdir(parents=True)
    sb.write_text(json.dumps({"layouts": [{"name": "Mine", "blocks": []}], "useDice": True}))
    ob.setup(tmp_path)
    ob.setup(tmp_path)                                            # twice: replaces, never duplicates
    c = json.loads(cal.read_text())
    assert [x["name"] for x in c["calendars"]] == ["Shire Reckoning", "Gregorian"]
    assert c["dateFormat"] == "YYYY-MM-DD" and c["autoParse"] is True
    months = c["calendars"][0]["static"]["months"]
    assert sum(m["length"] for m in months) == 365 and months[8]["type"] == "intercalary"
    s = json.loads(sb.read_text())
    assert [x["name"] for x in s["layouts"]] == ["Mine", "The One Ring"] and s["useDice"] is True
    lay = json.loads((tmp_path / "90 Assets" / "obsidian" / "the-one-ring.statblock-layout.json").read_text())
    assert lay["name"] == "The One Ring" and lay["blocks"]                  # importable by hand


def test_statblock_uses_layout_keys():
    try:
        text = ob.statblock_yaml("jack-the-stone-troll")
    except ob.ObsidianError:
        pytest.skip("the local lore library (gitignored) isn't here")
    assert text.startswith("```statblock\nlayout: The One Ring\n")
    assert re.search(r"^tor_stats: \[\d+, \d+, \d+, \d+, (?:\d+|–), (?:\d+|–)\]$", text, re.M)   # a stone-troll
    assert re.search(r"^ *- name: .+ \d+$", text, re.M) and re.search(r"desc: Damage \d+ · Injury \d+", text)


def test_home_block_is_replaced_and_the_rest_kept(tmp_path, monkeypatch):
    home = tmp_path / "00 Home.md"
    home.write_text("---\ncampaign: X\n---\n\n# X\n\n*A tale.*\n\n- my links\n", encoding="utf-8")
    monkeypatch.setattr(ob, "calendar_note", lambda vault_dir=None: None)        # not the live campaign's
    monkeypatch.setattr(ob, "home_markdown", lambda vault_dir=None: f"{ob.HOME_START}\nfirst\n{ob.HOME_END}")
    ob.home(tmp_path)
    monkeypatch.setattr(ob, "home_markdown", lambda vault_dir=None: f"{ob.HOME_START}\nsecond\n{ob.HOME_END}")
    ob.home(tmp_path)
    text = home.read_text(encoding="utf-8")
    assert text.count(ob.HOME_START) == 1 and "second" in text and "first" not in text
    assert text.index("*A tale.*") < text.index(ob.HOME_START) < text.index("- my links")


def test_timeline_dates_become_tale_days():
    assert ob._timeline_days("2965, spring (day 6)") == (6, 6)
    assert ob._timeline_days("2965, spring (days 8–10)") == (8, 10)
    assert ob._timeline_days("2965, spring (5th day)") == (5, 5)
    assert ob._timeline_days("2965, spring (night of day 10)") == (10, 10)
    assert ob._timeline_days("2965, spring (Herb 4 days overdue)") is None   # a count, not a tale day
    assert ob._timeline_days("2965, spring") is None


def test_theme_snippet_is_installed_and_enabled_once(tmp_path):
    app = tmp_path / ".obsidian" / "appearance.json"
    app.parent.mkdir(parents=True)
    app.write_text(json.dumps({"showRibbon": False, "enabledCssSnippets": ["mine"]}))
    ob.install_theme(tmp_path)
    ob.install_theme(tmp_path)
    data = json.loads(app.read_text())
    assert data["enabledCssSnippets"] == ["mine", "ringwraith"] and data["showRibbon"] is False
    css = (tmp_path / ".obsidian" / "snippets" / "ringwraith.css").read_text(encoding="utf-8")
    for callout in ("tale", "loremaster", "oracle", "player", "eye", "hope", "shadow"):
        assert f'data-callout="{callout}"' in css


def test_note_values_keep_wiki_links_as_links():
    from ringwraith import vault
    assert vault.parse_value("[[Archet]]") == "[[Archet]]"
    assert vault.parse_value("[[[A]], [[B]]]") == ["[[A]]", "[[B]]"]
    assert vault.parse_value("[[The Pony]] (held in the cellar)") == "[[The Pony]] (held in the cellar)"
    assert vault.parse_value("[a, b]") == ["a", "b"] and vault.parse_value("3") == 3


def test_calendar_uses_a_notes_own_title(tmp_path):
    f = tmp_path / "Session 002.md"
    assert ob.note_title(f, {"session": 2}, "# Session 2: The Fog at the Grey Stone\n\ntext") == \
        "Session 2: The Fog at the Grey Stone"
    assert ob.note_title(f, {"session": 2}, "no heading") == "Session 2"
    assert ob.note_title(f, {"name": "To Fornost"}, "# Session 002\n") == "To Fornost"


def test_encounters_are_kept_in_story_order(tmp_path):
    from ringwraith import vault
    f = tmp_path / "Ludo.md"
    f.write_text("---\ntype: npc\n---\n# Ludo\n\n## What the hero knows\n- A mason.\n\n## Encounters\n"
                 "- **Session 2:** caught fleeing his yard.\n- **Session 2:** earlier, drinking at the Pony.\n"
                 "\n## Notes\n- kept\n", encoding="utf-8")
    vault.add_encounter(f, "seen at the moot.", 2, 11)
    vault.add_encounter(f, "glimpsed on the road.", 1, 4)
    vault.add_encounter(f, "glimpsed on the road.", 1, 4)                      # no duplicates
    body = f.read_text(encoding="utf-8")
    enc = body.split("## Encounters\n")[1].split("\n## ")[0].strip().splitlines()
    assert enc[0].startswith("- **Session 1, day 4:**")
    assert enc[-1].startswith("- **Session 2, day 11:**") and len(enc) == 4
    assert "## Notes\n- kept" in body and "## What the hero knows\n- A mason." in body
