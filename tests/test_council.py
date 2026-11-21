import pytest

from ringwraith.web import council as cn


@pytest.fixture(autouse=True)
def private(tmp_path, monkeypatch):
    monkeypatch.setattr(cn.cp, "private_dir", lambda *a, **k: tmp_path)


def test_the_player_sees_how_far_they_are_swayed_never_the_numbers():
    cn.start("The moot", ["Mungo", {"name": "Ludo", "note": "Ludo Heathertoes"}], "Act before Goatleaf does",
             resistance=6, attitude="wary")
    st = cn.update({"rounds": 4})
    v = cn.public_view(st)
    assert (v["bar"], v["word"], v["rounds"], v["used"]) == (0.0, "unmoved", 4, 0)
    st = cn.update({"used": 1, "add": 2, "log": "Tomas lays the ledger on the table."})
    st = cn.update({"used": 2, "add": 2, "attitude": "listening hard"})
    v = cn.public_view(st)
    assert v["word"] == "wavering" and v["used"] == 2 and v["attitude"] == "listening hard"
    assert not {"resistance", "successes"} & set(v)                                 # the numbers stay hidden
    assert "successes 4/6" in cn.summary(st) and "2/4 exchanges" in cn.summary(st)
    assert cn.end("They agree to act")["outcome"] == "They agree to act" and cn.load() is None


def test_a_council_needs_someone_to_speak_to():
    with pytest.raises(cn.CouncilError):
        cn.start("Nobody", [], "anything", 3)
    with pytest.raises(cn.CouncilError):
        cn.update({"add": 1})
