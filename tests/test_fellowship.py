import pytest

from ringwraith.web import fellowship as fs


@pytest.fixture(autouse=True)
def private(tmp_path, monkeypatch):
    monkeypatch.setattr(fs.cp, "private_dir", lambda *a, **k: tmp_path)


def test_a_phase_keeps_its_steps_and_says_what_comes_next():
    st = fs.start("Brief", "Bree", undertakings=1, band=True)
    assert st["steps"] == ["recovery", "updates", "interruption", "undertakings", "close"]
    st = fs.update({"done": "recovery", "log": "Hope comes back."})
    assert "next: updates" in fs.summary(st)
    st = fs.update({"done": ["updates", "interruption"], "interruption": "A messenger from the Chetwood",
                    "undertakings": 0})
    v = fs.public_view(fs.load(), {"skill": 3, "adventure": 7})        # what a new session picks up
    assert [s["done"] for s in v["steps"]] == [True, True, True, False, False]
    assert [s["next"] for s in v["steps"]] == [False, False, False, True, False]
    assert v["xp"] == {"skill": 3, "adventure": 7} and v["undertakings"] == 0
    assert v["interruption"] == "A messenger from the Chetwood"
    st = fs.update({"done": "updates"})                                  # done twice stays done once
    assert st["done"].count("updates") == 1
    st = fs.update({"undo": "interruption"})
    assert "next: interruption" in fs.summary(st)
    assert fs.end("Spring passes in Bree")["outcome"] == "Spring passes in Bree" and fs.load() is None


def test_a_lone_hero_or_a_hurried_band_has_no_interruption():
    assert "interruption" not in fs.start("extended", band=False)["steps"]
    assert "interruption" not in fs.start("hurried", band=True)["steps"]
    st = fs.update({"duration": "yule", "chosen": "Meet Patron"})
    assert "interruption" in st["steps"] and st["chosen"] == ["Meet Patron"]


def test_bad_input_is_refused():
    with pytest.raises(fs.FellowshipError):
        fs.start("leisurely")
    with pytest.raises(fs.FellowshipError):
        fs.update({"done": "recovery"})                                  # nothing in progress
    fs.start("brief", band=False)
    with pytest.raises(fs.FellowshipError):
        fs.update({"done": "feasting"})
