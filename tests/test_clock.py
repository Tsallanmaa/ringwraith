from ringwraith import clock


def _camp(tmp_path):
    (tmp_path / "c1" / ".ringwraith").mkdir(parents=True)
    (tmp_path / "c1" / ".ringwraith" / "state.md").write_text("---\ndate: 2965, spring\nday: 7\n---\n\nbody\n",
                                                              encoding="utf-8")
    return {"slug": "c1", "root": tmp_path}


def test_deadlines_count_down_and_warn(tmp_path):
    kw = _camp(tmp_path)
    clock.add_deadline("Fitch's trap", in_days=10, note="new moon", **kw)
    clock.add_deadline("Quarter-day", due=25, **kw)
    clock.add_counter("Herb missing", since=1, **kw)
    fm = clock.state(**kw)[1]
    lines = clock.describe(fm)
    assert lines[0].startswith("Fitch's trap: in 10 days (day 17)")
    assert "Herb missing: day 7" in lines
    day, warnings = clock.advance(10, "dusk", **kw)
    assert day == 17 and warnings == ["DUE TODAY: Fitch's trap"]
    day, warnings = clock.advance(9, **kw)
    assert warnings == ["DUE on day 25 (passed): Quarter-day"]
    assert clock.remove("deadlines", "fitch", **kw)["name"] == "Fitch's trap"   # prefix match
    fm, body = clock.state(**kw)[1:]
    assert fm["time"] == "dusk" and [d["name"] for d in fm["deadlines"]] == ["Quarter-day"] and "body" in body
