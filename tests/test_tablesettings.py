import pytest

from ringwraith.web import tablesettings as ts


@pytest.fixture
def settings(monkeypatch):
    s = {"dice": {"mode": "auto"}, "difficulty": {"easy": False, "encounters": "story"}, "art": {"enabled": True}}

    def set_value(dotted, value):
        node = s
        *parents, leaf = dotted.split(".")
        for p in parents:
            node = node.setdefault(p, {})
        node[leaf] = value
        return s
    monkeypatch.setattr(ts.cp, "load_settings", lambda *a, **k: s)
    monkeypatch.setattr(ts.cp, "set_value", set_value)
    return s


def test_the_dialog_shows_the_current_values(settings):
    fields = {f["key"]: f for f in ts.view()["fields"]}
    assert fields["table.model"]["value"] is None                    # no model set: the account default
    assert fields["dice.mode"]["value"] == "auto"
    assert [o["value"] for o in fields["table.model"]["options"]][:3] == [None, "opus", "sonnet"]


def test_only_changes_are_saved_and_reported(settings):
    changes = ts.apply({"table.model": "sonnet", "dice.mode": "auto", "difficulty.easy": True})
    assert [c["key"] for c in changes] == ["table.model", "difficulty.easy"]
    assert settings["table"]["model"] == "sonnet" and settings["difficulty"]["easy"] is True
    assert ts.describe(changes) == "Loremaster's model: Sonnet; Easy mode: On"
    assert ts.apply({"table.model": None})[0]["value"] == "Account default"


def test_anything_else_is_refused(settings):
    for bad in ({"campaign.mode": "strider"}, {"table.model": "gpt"}, {"difficulty.easy": 1},
                {"dice.mode": None}, ["dice.mode"]):
        with pytest.raises(ts.SettingsError):
            ts.apply(bad)
    assert settings["dice"]["mode"] == "auto" and "table" not in settings
