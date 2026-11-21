"""Campaign vault lifecycle, notes and the art queue (temporary vault root, no Lemonade)."""

import pytest

from ringwraith import artqueue, vault
from ringwraith import campaign as cp


@pytest.fixture
def root(tmp_path):
    vault.create("test-camp", name="Test Campaign", root=tmp_path)
    return tmp_path


def test_create_layout(root):
    d = root / "test-camp"
    assert (d / "00 Home.md").read_text(encoding="utf-8").startswith("---\ncampaign: \"Test Campaign\"")
    assert (d / "20 Fellowship" / "Band.md").exists()
    assert (d / ".ringwraith" / "state.md").exists()
    assert (d / "_templates" / "hero.md").exists()
    assert (d / "30 World" / "People.md").exists()
    assert cp.active_slug(root) == "test-camp"
    meta = cp.load_settings(root=root)["campaign"]
    assert meta["year"] == 2965 and meta["start"] == "bree"
    assert "{{" not in (d / ".ringwraith" / "state.md").read_text(encoding="utf-8")


def test_duplicate_refused(root):
    with pytest.raises(cp.CampaignError):
        vault.create("test-camp", root=root)


def test_notes_roundtrip(root):
    p = vault.new_note("ally", "Hob Hayward", root=root, extra={"gift": "Healer", "hardened": True})
    fm, body = vault.read_note(p)
    assert fm["gift"] == "Healer" and fm["hardened"] is True and "# Hob Hayward" in body
    fm["injury"] = "moderate"
    vault.write_note(p, fm, body)
    assert vault.read_note(vault.resolve_note("hob hayward", root=root))[0]["injury"] == "moderate"
    s1 = vault.new_note("session", "Arrival", root=root)
    s2 = vault.new_note("session", "The Road", root=root)
    assert s1.name == "Session 001.md" and s2.name == "Session 002.md"


def test_art_queue_attach(root):
    vault.new_note("npc", "Barliman", root=root)
    job = artqueue.enqueue("portrait", "a stout innkeeper", note="Barliman", root=root)
    assert artqueue.pending(root=root)[0]["id"] == job["id"]
    vroot = root / "test-camp"
    (vroot / job["file"]).parent.mkdir(parents=True, exist_ok=True)
    (vroot / job["file"]).write_bytes(b"png")
    artqueue._attach(vroot, job)
    fm, body = vault.read_note(vroot / job["note"])
    assert fm["image"] == f"[[{job['file']}]]"
    assert f"![[{job['file']}|320]]" in body


def test_archive_and_reset(root):
    vault.new_note("hero", "Tester", root=root)
    cp.set_value("difficulty.easy", True, root=root)
    z, dest = vault.reset("test-camp", root=root)
    assert z.exists() and dest.exists()
    assert not (dest / "20 Fellowship" / "Heroes" / "Tester.md").exists()
    assert cp.load_settings(root=root)["difficulty"]["easy"] is True
    assert [c["slug"] for c in vault.list_campaigns(root)] == ["test-camp"]


def test_a_new_session_note_sets_the_session_in_the_state(tmp_path, monkeypatch):
    from ringwraith import campaign as cp
    from ringwraith import vault
    monkeypatch.setattr(cp, "vaults_root", lambda c=None: tmp_path)
    vault.create("s", name="S", root=tmp_path)
    p = vault.new_note("session", "The first", slug="s", root=tmp_path)
    p2 = vault.new_note("session", "The second", slug="s", root=tmp_path)
    assert (p.name, p2.name) == ("Session 001.md", "Session 002.md")
    assert vault.read_note(tmp_path / "s" / ".ringwraith" / "state.md")[0]["session"] == 2
