"""Dice engine and table schema tests (synthetic tables only)."""

import pytest

from ringwraith import dice, tables as tb


def test_basic_success_and_degrees():
    r = dice.test(3, 14, feat=[8], success=[6, 2, 6])
    assert r.total == 22 and r.outcome == "success" and r.degree == "extraordinary"
    r = dice.test(2, 14, feat=[3], success=[4, 5])
    assert r.outcome == "failure" and r.degree == ""


def test_gandalf_auto_success_and_eye_zero():
    assert dice.test(0, 20, feat=["gandalf"], success=[]).outcome == "success"
    r = dice.test(1, 6, feat=["eye"], success=[6])
    assert r.total == 6 and r.outcome == "success" and r.degree == "great"


def test_miserable_eye_fails():
    r = dice.test(2, 4, miserable=True, feat=["eye"], success=[6, 6])
    assert r.outcome == "failure"


def test_weary_counts_low_dice_as_zero():
    r = dice.test(3, 14, weary=True, feat=[5], success=[3, 2, 6])
    assert r.total == 11 and r.outcome == "failure"


def test_favoured_ill_and_cancel():
    assert dice.test(0, 10, favoured=True, feat=["eye", 9], success=[]).feat == 9
    assert dice.test(0, 10, ill=True, feat=["gandalf", 2], success=[]).feat == 2
    r = dice.test(0, 10, favoured=True, ill=True, feat=[7], success=[])
    assert r.mode == "normal"
    with pytest.raises(ValueError):
        dice.test(0, 10, favoured=True, feat=[7], success=[])


def test_dice_count_with_hope_bonus_penalty():
    assert dice.test(2, 10, hope=True, feat=[1], success=[1, 1, 1]).dice == 3
    assert dice.test(2, 10, hope=True, inspired=True, feat=[1], success=[1, 1, 1, 1]).dice == 4
    assert dice.test(1, 10, penalty=3, feat=[1], success=[]).dice == 0


TABLE = {
    "id": "demo", "title": "Demo", "source": ["test"], "_file": "demo.yaml",
    "dice": ["feat", "success"],
    "entries": {
        "gandalf": {"1-3": "G-low", "4-6": {"text": "G-high", "fatigue": 1}},
        "eye": {"1-6": "E"},
        "1-10": {"1-6": "N"},
    },
}


def test_validate_and_roll():
    assert tb.validate(TABLE) == []
    tables = {"demo": TABLE}
    r = tb.roll(tables, "demo", given=["gandalf", 5])
    assert r.result == {"text": "G-high", "fatigue": 1}
    assert tb.roll(tables, "demo", given=[7, 2]).result == "N"


def test_validate_finds_gaps_and_overlaps():
    bad = dict(TABLE, entries={"gandalf": {"1-6": "x"}, "1-9": {"1-6": "y"}, "9-10": {"1-6": "z"}})
    errs = tb.validate(bad)
    assert any("eye" in e for e in errs)          # eye not covered
    assert any("matches 2 keys" in e for e in errs)  # 9 overlaps


def test_telling():
    t = {"chances": {"certain": 2, "likely": 3, "middling": 5, "doubtful": 7, "unthinkable": 9},
         "yes": "Yes", "no": "No", "gandalf": "Yes!", "eye": "No!"}
    assert tb.telling(t, "middling", given=6)[2] == "Yes"
    assert tb.telling(t, "doubtful", given=6)[2] == "No"
    assert tb.telling(t, "unthinkable", given="gandalf")[2] == "Yes!"
    assert tb.telling(t, "certain", given="eye")[2] == "No!"


def test_adversary_reads_icons_reversed():
    r = dice.test(2, 20, adversary=True, feat=["eye"], success=[1, 1])
    assert r.outcome == "success" and r.total == 12
    r = dice.test(2, 5, adversary=True, feat=["gandalf"], success=[1, 1])
    assert r.total == 2 and r.outcome == "failure"
    assert dice.test(0, 5, adversary=True, favoured=True, feat=[9, "eye"], success=[]).feat == "eye"


def test_odds_exact_values():
    # Feat die only vs TN 14: just the Gandalf rune succeeds.
    assert dice.odds(0, 14).success == pytest.approx(1 / 12)
    # Miserable removes nothing here (the Eye already fails at TN 14), TN 1 shows the Eye failing.
    assert dice.odds(0, 1, miserable=True).success == pytest.approx(11 / 12)
    # Favoured: P(Gandalf on either of two dice).
    assert dice.odds(0, 14, favoured=True).success == pytest.approx(23 / 144)
    # Hope adds a die, Inspired Hope two.
    assert dice.odds(2, 14, hope=True).dice == 3
    assert dice.odds(2, 14, hope=True, inspired=True).dice == 4


def test_odds_match_simulation():
    dice.seed(7)
    n = 40000
    for kw in ({"favoured": True}, {"ill": True, "weary": True}, {"miserable": True, "bonus": 1}):
        hits = sum(dice.test(2, 13, **kw).outcome == "success" for _ in range(n)) / n
        assert dice.odds(2, 13, **kw).success == pytest.approx(hits, abs=0.015)
    dice.seed(None)


def test_lore_tables_are_read_once_and_again_only_after_a_change(tmp_path, monkeypatch):
    import os
    from ringwraith import ops
    tdir = tmp_path / "tables"
    tdir.mkdir()
    f = tdir / "coin.yaml"
    f.write_text("id: coin\ntitle: Coin\ndice: [d6]\nentries: {1-3: Heads, 4-6: Tails}\n", encoding="utf-8")
    monkeypatch.setattr(ops, "tables_dir", lambda: tdir)
    ops._tables.clear()
    first = ops.all_tables()
    assert "coin" in first and ops.all_tables() is first                  # kept, not re-read
    f.write_text("id: coin\ntitle: A coin\ndice: [d6]\nentries: {1-3: Heads, 4-6: Tails}\n", encoding="utf-8")
    os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 10_000_000))
    assert ops.all_tables()["coin"]["title"] == "A coin"                  # a change is seen
