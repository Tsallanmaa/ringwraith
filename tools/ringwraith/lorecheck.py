"""Checks on how the lore library is organised (not on what it says): `ringwraith lore-check`.

- **paths**: every lore path (except the optional maps/) that the lore, the skills, the table's contract and
  CLAUDE.md point to exists
  (`procedures/combat.md`, `campaigns/moria/moria-journeys.md`, `atoms/patrons/`…). A moved file breaks these.
- **readings**: the distiller's own rulings, where the books are silent or unclear. They are marked
  `(reading)` after a sentence, `(reading: why)` / `(reading, from …)`, or a line starting `Reading:`
  (docs/lore-format.md). They are listed so the user can review them, like homebrew.
- **orphan tables**: tables no file names by id (nothing tells the Loremaster to roll them).
- **secret split**: atoms marked `secrets: true` with no Loremaster-only section, and atoms extended from a
  second book (`## From <book>`) whose added block mixes Loremaster-only matter into player-facing text.
"""

from __future__ import annotations

import re
from pathlib import Path

# A lore path in prose or code spans: procedures/…, campaigns/…, atoms/…, tables/…, adventures/…, maps/…
PATH_RE = re.compile(r"(?<![\w/.-])(?:lore/)?((?:procedures|campaigns|atoms|tables|adventures|maps)/[\w./-]*[\w/])")
READING_RE = re.compile(r"\(reading(?=[):,;]| (?:from|of|for|until|in line|cf\b))|^\s*(?:[-*]\s+)?\**Reading\**:", re.M)
REVIEWED_RE = re.compile(r"(?:approved|chosen) by the user", re.I)
SKIP_PATH = re.compile(r"[<*{]|NNN")      # patterns, not paths: atoms/<kind>/, strider-event-detail-*


def _texts(repo: Path) -> list[Path]:
    lore = repo / "lore"
    files = [p for p in lore.rglob("*.md")]
    files += list((repo / ".claude" / "skills").rglob("*.md"))     # with distill/targets.md: what the table needs
    files += [repo / "tools" / "ringwraith" / "web" / "prompt.md", repo / "CLAUDE.md"]
    return [f for f in files if f.exists()]


def broken_paths(repo: Path) -> list[tuple[Path, int, str]]:
    """(file, line, path) for every lore path that doesn't exist."""
    lore = repo / "lore"
    out = []
    for f in _texts(repo):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for m in PATH_RE.finditer(line):
                ref = m.group(1).split("#")[0].rstrip(".,;:)")
                in_code = line[:m.start()].count("`") % 2 == 1
                if not (in_code or ref.endswith("/") or re.search(r"\.(md|yaml|json)$", ref)):
                    continue                  # prose that merely looks like a path ("short campaigns/one-shots")
                if ref.startswith("maps/") or _resolves(lore, ref):
                    continue                  # maps are optional: a library may have none (distill, phase 7)
                out.append((f, n, ref))
    return out


def _resolves(lore: Path, ref: str) -> bool:
    """A file or folder, the same without its extension, or a prefix of real files (`tables/chargen-*`,
    `adventures/hww/01-*.md`, `tables/strider-event-detail-<event>.yaml`)."""
    target = lore / ref
    if target.exists() or target.with_suffix(".md").exists() or target.with_suffix(".yaml").exists():
        return True
    stem = re.sub(r"\.(md|yaml|json)$", "", ref)
    parent, _, prefix = stem.rpartition("/")
    folder = lore / parent
    return bool(prefix) and folder.is_dir() and any(p.name.startswith(prefix) for p in folder.iterdir())


def readings(repo: Path) -> list[tuple[Path, int, str]]:
    """(file, line, the line) for every marked reading in lore/ that the user hasn't approved yet. An approved one
    says so on its line: `(reading, approved by the user <date>: …)` or `chosen by the user`."""
    out = []
    for f in sorted((repo / "lore").rglob("*.md")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if READING_RE.search(line) and not REVIEWED_RE.search(line):
                out.append((f, n, line.strip()))
    return out


def orphan_tables(repo: Path, table_ids: list[str]) -> list[str]:
    """Tables that no lore file, skill, contract or code names (directly, by a `then:` chain or a prefix)."""
    # INDEX.md lists every table, so it doesn't count as telling anyone when to roll one.
    corpus = "\n".join(f.read_text(encoding="utf-8") for f in _texts(repo) if f.name != "INDEX.md")
    corpus += "\n".join(f.read_text(encoding="utf-8") for f in (repo / "lore" / "tables").glob("*.yaml"))
    corpus += "\n".join(f.read_text(encoding="utf-8") for f in (repo / "tools" / "ringwraith").rglob("*.py"))
    named = set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)+|[a-z0-9]+", corpus))
    prefixes = set(re.findall(r"([a-z0-9]+(?:-[a-z0-9]+)*-)(?:<|\*|\{)", corpus))   # `chargen-attributes-<culture>`
    out = []
    for tid in table_ids:
        own = (repo / "lore" / "tables" / f"{tid}.yaml").read_text(encoding="utf-8") if (repo / "lore" / "tables" / f"{tid}.yaml").exists() else ""
        mentions = corpus.count(tid) - own.count(tid)
        if mentions <= 0 and not any(tid.startswith(p) for p in prefixes):
            out.append(tid)
    return out


# A Loremaster-only part: a heading, or a bold line such as "**Loremaster-only additions**".
LM_HEAD = re.compile(r"^(?:#{2,4}\s.*|\*\*[^*\n]*)(loremaster|lm only|secret)", re.I | re.M)
FROM_HEAD = re.compile(r"^## From\b.*$", re.M)


def secret_split(repo: Path) -> tuple[list[Path], list[Path]]:
    """(atoms marked secret with no Loremaster-only section, atoms whose '## From <book>' block lacks the split)."""
    no_lm, mixed = [], []
    for f in sorted((repo / "lore" / "atoms").rglob("*.md")):
        text = f.read_text(encoding="utf-8")
        head = text.split("\n---", 1)[0] if text.startswith("---") else ""      # the frontmatter
        if not re.search(r"^secrets:\s*true", head, re.M):
            continue
        if not LM_HEAD.search(text):
            # Only a problem if part of the atom is meant for the player: an adversary's or item's whole note is
            # Loremaster knowledge (its stat block reaches the vault only once the hero has met it).
            # a "Player-facing" heading or bold label (not just a bold rule that mentions a Player-hero)
            if re.search(r"^(?:#{2,4}\s+|\*\*)player[- ]facing", text, re.I | re.M):
                no_lm.append(f)
            continue
        for m in FROM_HEAD.finditer(text):
            nxt = re.search(r"^## (?!#)", text[m.end():], re.M)
            block = text[m.end(): m.end() + nxt.start()] if nxt else text[m.end():]
            if block.strip() and not LM_HEAD.search(block):
                mixed.append(f)
                break
    return no_lm, mixed
