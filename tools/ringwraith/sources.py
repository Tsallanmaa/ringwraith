"""Manifest of known reference PDFs.

Only words from the titles and short ids live here: no content from the books.

A PDF is recognised by the words in its file name, so the name it was sold under, a renamed copy or another
printing all work: "The One Ring Core Rules.pdf", "TOR 2e - Core Rules (2nd printing).pdf" and "core-rules.pdf" are all
`core`. When a name says too little, set it in ringwraith.toml:

    [sources]
    core = "My rulebook.pdf"

`scan()` maps the files in the references folder to source ids.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    words: tuple[str, ...]  # all must be in the file name; "a|b" means either
    kind: str             # book | booklet | map | sheet | cards
    phase: int            # extraction group (`extract --phase N`): 1 = needed to play, 7 = the other books, 4 = maps
    duplicate_of: str = ""  # the same content as another source: not extracted again
    without: tuple[str, ...] = ()  # none of these may be in the file name

    def accepts(self, words: set[str]) -> bool:
        return (all(any(w in words for w in group.split("|")) for group in self.words)
                and not any(w in words for w in self.without))


S1, S2 = "starter1", "starter2"   # added by _words(): which Starter Set a name belongs to
SETS = (S1, S2)

SOURCES: list[Source] = [
    # Group 1: needed to play at all
    Source("core", "The One Ring Core Rules", ("core", "rules|rulebook"), "book", 1, without=SETS),
    Source("strider", "Strider Mode", ("strider",), "booklet", 1),
    Source("moria", "Moria: Through the Doors of Durin", ("moria",), "book", 1, without=("map",)),
    Source("screen", "Loremaster's Screen", ("screen",), "sheet", 1),
    # Group 7: the other books
    Source("ss1-rules", "Starter Set: The Rules", (S1, "rules"), "booklet", 7),
    Source("ss1-adventures", "Starter Set: The Adventures", (S1, "adventures"), "booklet", 7),
    Source("ss1-shire", "Starter Set: The Shire", (S1, "shire"), "booklet", 7, without=("map",)),
    Source("ss1-pregens", "Starter Set: Pre-generated Characters", (S1, "generated|pregenerated|pregens"), "sheet", 7),
    Source("ss1-cards", "Starter Set: Stance and Journey Cards", (S1, "stance"), "cards", 7),
    Source("ss1-wargear", "Starter Set: War Gear Cards", (S1, "gear|wargear"), "cards", 7),
    Source("hobbit-tales", "Hobbit Tales", ("hobbit", "tales"), "book", 7),
    Source("ss2-rules", "Starter Set 2: Rules Booklet", (S2, "rules"), "booklet", 7),
    Source("ss2-adventure", "Starter Set 2: Adventure Booklet", (S2, "adventure|adventures"), "booklet", 7),
    Source("ss2-pregens", "Starter Set 2: Pre-generated Player-heroes", (S2, "generated|pregenerated|pregens"),
           "sheet", 7),
    Source("ss2-start", "Starter Set 2: Getting Started", (S2, "started"), "sheet", 7),
    Source("ss2-handout", "Starter Set 2: Handout", (S2, "handout"), "sheet", 7),
    Source("ss2-combat", "Starter Set 2: Combat Diagram", (S2, "combat"), "sheet", 7),
    Source("ss2-journeylog", "Starter Set 2: Journey Log Sheet", (S2, "journey", "log"), "sheet", 7),
    Source("ss2-figures", "Starter Set 2: Stand-up Figures", (S2, "figures"), "sheet", 7),
    Source("lonelands", "Tales from the Lone-lands", ("lone|lonelands",), "book", 7),
    Source("ruins", "Ruins of the Lost Realm", ("ruins", "lost"), "book", 7),
    Source("rivendell", "Rivendell", ("rivendell",), "booklet", 7),
    Source("realms", "Realms of the Three Rings", ("realms",), "book", 7),
    Source("hww", "Hands of the White Wizard", ("white", "wizard"), "book", 7),
    Source("wilderland", "Peoples of Wilderland", ("wilderland",), "booklet", 7),
    # Maps (group 4: rendered, not distilled)
    Source("map-eriador-player", "Player Map of Eriador", ("map", "eriador", "player"), "map", 4, without=SETS),
    Source("map-eriador-lm", "Loremaster Map of Eriador", ("map", "eriador", "loremaster|loremasters"), "map", 4,
           without=SETS),
    Source("map-moria", "Moria Map Sheet", ("map", "moria"), "map", 4),
    Source("map-ss1-eriador", "Starter Set Map of Eriador", (S1, "map", "eriador"), "map", 4),
    Source("map-ss1-shire", "Starter Set Map of the Shire", (S1, "map", "shire"), "map", 4),
    Source("map-ss2-eriador", "Starter Set 2 Map of Eriador", (S2, "map", "eriador"), "map", 4),
]

BY_ID = {s.id: s for s in SOURCES}


def _words(name: str) -> set[str]:
    """The words of a file name, lower case, with a word for the Starter Set it belongs to, if any."""
    stem = Path(name).stem.lower().replace("'", "").replace("’", "")
    words = set(re.findall(r"[a-z0-9]+", stem)) | set(re.findall(r"[a-z]+|\d+", stem))   # "ss2" and "ss", "2"
    if "ss2" in words or ({"starter", "2"} <= words) or ({"starter", "ii"} <= words):
        words.add(S2)
    elif "starter" in words or "ss1" in words:
        words.add(S1)
    return words


def candidates(path: Path) -> list[Source]:
    """The sources a file name fits, the most specific first."""
    if path.suffix.lower() != ".pdf":
        return []
    words = _words(path.name)
    return sorted((s for s in SOURCES if s.accepts(words)), key=lambda s: -(len(s.words) + len(s.without)))


def match(path: Path) -> Source | None:
    """The source a file name fits, or None when it fits none, or several equally well."""
    found = candidates(path)
    if len(found) > 1 and len(found[0].words) + len(found[0].without) == len(found[1].words) + len(found[1].without):
        return None
    return found[0] if found else None


def _configured() -> dict[str, str]:
    """[sources] in ringwraith.toml: source id -> file name in the references folder."""
    from . import config as cfg
    import tomllib
    if not cfg.CONFIG_FILE.exists():
        return {}
    with cfg.CONFIG_FILE.open("rb") as fh:
        return {k: str(v) for k, v in tomllib.load(fh).get("sources", {}).items()}


def scan(references: Path, configured: dict[str, str] | None = None) -> tuple[dict[str, Path], list[Path]]:
    """Return ({source id: pdf path}, [unrecognised files]).

    Files named in ringwraith.toml's [sources] come first; the rest are recognised by name. A second file
    that fits a source already found is listed as unrecognised, so `ringwraith doctor` shows it."""
    configured = _configured() if configured is None else configured
    found: dict[str, Path] = {}
    for sid, name in configured.items():
        if sid in BY_ID and (references / name).is_file():
            found[sid] = references / name
    taken = set(found.values())
    unknown: list[Path] = []
    for f in sorted(references.glob("*")):
        if not f.is_file() or f in taken:
            continue
        s = match(f)
        if s is None or s.id in found:
            unknown.append(f)
        else:
            found[s.id] = f
    return found, unknown


def resolve(references: Path, name: str) -> Path:
    """A file named in the lore (say a map's `source: {pdf: ...}`) on this machine: the same name if it is
    there, otherwise the reader's own copy of the same source, whatever it is called."""
    path = references / name
    if path.exists():
        return path
    s = match(Path(name))
    if s is not None:
        found, _ = scan(references)
        if s.id in found:
            return found[s.id]
    return path
