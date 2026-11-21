"""Recognising the reader's PDFs by their file names, whatever they are called."""

from pathlib import Path

import pytest

from ringwraith import sources


@pytest.mark.parametrize("name, sid", [
    ("The One Ring - Core Rules (printing 3).pdf", "core"),
    ("TOR 2e - Core Rules.pdf", "core"),
    ("core-rules.pdf", "core"),
    ("moria_book.pdf", "moria"),
    ("Moria - Through the Doors of Durin.pdf", "moria"),
    ("Moria Map Sheet.pdf", "map-moria"),
    ("Strider Mode.pdf", "strider"),
    ("Loremaster's Screen.pdf", "screen"),
    ("starter-set-the-rules.pdf", "ss1-rules"),
    ("SS2 rules booklet.pdf", "ss2-rules"),
    ("Starter Set 2 - Rules.pdf", "ss2-rules"),
    ("player_map_of_eriador.pdf", "map-eriador-player"),
    ("Starter Set - Map of Eriador.pdf", "map-ss1-eriador"),
    ("SS2 Map of Eriador.pdf", "map-ss2-eriador"),
    ("Tales from the Lone-lands.pdf", "lonelands"),
])
def test_recognised_by_words(name, sid):
    assert sources.match(Path(name)).id == sid


@pytest.mark.parametrize("name", ["Homebrew Adversaries.pdf", "core-rules.txt", "eriador-map.jpg"])
def test_not_a_book(name):
    assert sources.match(Path(name)) is None


def test_configured_names_and_duplicates(tmp_path):
    for n in ["My rulebook.pdf", "Core Rules.pdf", "Core Rules (old printing).pdf", "Strider Mode.pdf"]:
        (tmp_path / n).write_bytes(b"")
    found, unknown = sources.scan(tmp_path, {"core": "My rulebook.pdf"})
    assert found["core"].name == "My rulebook.pdf" and found["strider"].name == "Strider Mode.pdf"
    assert {f.name for f in unknown} == {"Core Rules.pdf", "Core Rules (old printing).pdf"}


def test_resolve_finds_the_readers_copy(tmp_path):
    (tmp_path / "Player Map of Eriador.pdf").write_bytes(b"")
    assert sources.resolve(tmp_path, "eriador_player_map_v2.pdf").name == "Player Map of Eriador.pdf"
