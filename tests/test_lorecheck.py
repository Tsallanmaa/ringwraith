"""lore-check's organisation checks, on a tiny made-up library (no book text)."""

from ringwraith import lorecheck


def _repo(tmp_path):
    lore = tmp_path / "lore"
    for d in ("procedures", "campaigns/moria", "tables", "atoms/patrons", "atoms/npcs", "adventures/hww"):
        (lore / d).mkdir(parents=True)
    (lore / "procedures" / "combat.md").write_text(
        "# Combat\n## Steps\n1. Roll (reading).\n2. See `campaigns/moria/moria-journeys.md` and `atoms/patron/`.\n"
        "3. Short campaigns/one-shots use the same steps.\n- Reading: a longer ruling.\n"
        "4. **Reading the Riddle:** a heading from a book, not a ruling.\n", encoding="utf-8")
    (lore / "campaigns" / "moria" / "moria-journeys.md").write_text("# Moria journeys\n", encoding="utf-8")
    (lore / "adventures" / "hww" / "01-the-beast.md").write_text("# The beast\n", encoding="utf-8")
    (lore / "atoms" / "npcs" / "ann.md").write_text(
        "---\nkind: npc\nsecrets: true\n---\n# Ann\n## Player-facing\nA miller. `adventures/hww/01-*.md`\n", encoding="utf-8")
    (lore / "atoms" / "npcs" / "bob.md").write_text(
        "---\nkind: npc\nsecrets: true\n---\n# Bob\n## Player-facing\nx\n## Loremaster-only\ny\n"
        "## From Another Book\n" + "More about Bob. " * 40 + "\n", encoding="utf-8")
    (lore / "tables" / "used.yaml").write_text("id: used\n", encoding="utf-8")
    (lore / "tables" / "lonely.yaml").write_text("id: lonely\n", encoding="utf-8")
    (lore / "INDEX.md").write_text("- used, lonely\n", encoding="utf-8")
    (lore / "core.md").write_text("Roll `used` when it matters.\n", encoding="utf-8")
    return tmp_path


def test_paths_that_point_nowhere_are_found(tmp_path):
    repo = _repo(tmp_path)
    broken = [(f.name, ref) for f, _, ref in lorecheck.broken_paths(repo)]
    assert broken == [("combat.md", "atoms/patron/")]        # prose and real prefixes aren't flagged


def test_readings_are_listed_but_book_headings_are_not(tmp_path):
    repo = _repo(tmp_path)
    lines = [line for _, _, line in lorecheck.readings(repo)]
    assert len(lines) == 2 and not any("Riddle" in line for line in lines)


def test_unnamed_tables_and_weak_secret_splits(tmp_path):
    repo = _repo(tmp_path)
    assert lorecheck.orphan_tables(repo, ["used", "lonely"]) == ["lonely"]   # INDEX.md doesn't count
    no_lm, mixed = lorecheck.secret_split(repo)
    assert [f.name for f in no_lm] == ["ann.md"] and [f.name for f in mixed] == ["bob.md"]
