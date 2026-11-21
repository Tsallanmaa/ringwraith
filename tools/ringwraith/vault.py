"""Campaign vaults: create from vault-kit, list, archive, reset, and edit notes."""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

import yaml

from . import campaign as cp
from . import fileio
from .config import REPO_ROOT

KIT = REPO_ROOT / "vault-kit"
SKELETON = KIT / "skeleton"
TEMPLATES = KIT / "templates"

FOLDERS = [
    "10 Campaign/Sessions",
    "20 Fellowship/Heroes", "20 Fellowship/Allies", "20 Fellowship/Missions", "20 Fellowship/Journeys",
    "30 World/Places", "30 World/People", "30 World/Factions", "30 World/Adversaries", "30 World/Items",
    "60 Maps",
    "90 Assets/portraits", "90 Assets/scenery", "90 Assets/items", "90 Assets/adversaries", "90 Assets/scenes",
    "_templates",
]

# note type -> (folder, index note title)
NOTE_TYPES: dict[str, str] = {
    "hero": "20 Fellowship/Heroes",
    "ally": "20 Fellowship/Allies",
    "mission": "20 Fellowship/Missions",
    "journey": "20 Fellowship/Journeys",
    "session": "10 Campaign/Sessions",
    "npc": "30 World/People",
    "place": "30 World/Places",
    "adversary": "30 World/Adversaries",
    "item": "30 World/Items",
}

# Index notes: an Obsidian Base (core plugin, no community plugins) listing a folder's notes.
# path -> (title, folder, columns, sort [(property, direction)], also a portrait gallery)
INDEXES = {
    "10 Campaign/Sessions.md": ("Sessions", "10 Campaign/Sessions", ["session", "in_game_date", "tale_days", "location"],
                                [("note.session", "DESC")], False),
    "20 Fellowship/Heroes.md": ("Heroes", "20 Fellowship/Heroes", ["culture", "calling"], [("file.name", "ASC")], True),
    "20 Fellowship/Allies.md": ("Allies", "20 Fellowship/Allies", ["gift", "status", "injury", "fatigue", "hardened"],
                                [("file.name", "ASC")], True),
    "20 Fellowship/Missions.md": ("Missions", "20 Fellowship/Missions", ["status", "objective", "grade"],
                                  [("file.ctime", "DESC")], False),
    "20 Fellowship/Journeys.md": ("Journeys", "20 Fellowship/Journeys", ["status", "from", "to", "days"],
                                  [("file.ctime", "DESC")], False),
    "30 World/Places.md": ("Places", "30 World/Places", ["region", "state"], [("file.name", "ASC")], True),
    "30 World/People.md": ("People", "30 World/People", ["role", "location", "attitude"], [("file.name", "ASC")], True),
    "30 World/Adversaries.md": ("Adversaries", "30 World/Adversaries", ["kind", "fate"], [("file.name", "ASC")], True),
    "30 World/Items.md": ("Items", "30 World/Items", ["kind", "owner"], [("file.name", "ASC")], True),
    "60 Maps/Maps.md": ("Maps", "60 Maps", [], [("file.name", "ASC")], False),
}


def index_note(title: str, folder: str, columns: list[str], sort: list[tuple[str, str]], gallery: bool) -> str:
    """An index note whose body is a `base` block: a table of the folder's notes (and a portrait gallery)."""
    def view(kind: str, name: str, cols: list[str], extra: list[str]) -> list[str]:
        out = [f"  - type: {kind}", f"    name: {name}", *extra, "    order:", "      - file.name"]
        out += [f"      - note.{c}" for c in cols]
        out.append("    sort:")
        for prop, direction in sort:
            out += [f"      - property: {prop}", f"        direction: {direction}"]
        return out

    lines = ["```base", "filters:", "  and:", f"    - 'file.inFolder(\"{folder}\")'", "    - 'type != \"index\"'",
             "views:"]
    lines += view("table", title, columns, [])
    if gallery:
        lines += view("cards", "Portraits", columns[:2], ["    image: note.image", "    cardSize: 160"])
    lines.append("```")
    return f"---\ntype: index\n---\n\n# {title}\n\n" + "\n".join(lines) + "\n"


def write_indexes(dest: Path) -> list[Path]:
    """Write the index notes. An existing one is replaced only if it is still a generated index (a Dataview
    block from older versions, or a base), never a note the player wrote."""
    out = []
    for rel, spec in INDEXES.items():
        f = dest / rel
        if f.exists():
            body = f.read_text(encoding="utf-8")
            if not ("type: index" in body and ("```dataview" in body or "```base" in body)):
                continue
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(index_note(*spec), encoding="utf-8")
        out.append(f)
    return out


def _title(slug: str) -> str:
    return " ".join(w.capitalize() for w in re.split(r"[-_ ]+", slug) if w)


def _render(text: str, values: dict[str, Any]) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(values.get(m.group(1), m.group(0))), text)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# ------------------------------------------------------------ campaigns

def create(slug: str, *, name: str | None = None, mode: str = "band", region: str = "eriador",
           start: str = "bree", year: int = 2965, easy: bool = False, root: Path | None = None) -> Path:
    root = root or cp.vaults_root()
    slug = slugify(slug)
    dest = root / slug
    if dest.exists():
        raise cp.CampaignError(f"{dest} already exists (use `ringwraith reset {slug}`)")
    values = {
        "name": name or _title(slug), "mode": mode, "region": region, "region_title": _title(region),
        "start": start, "start_title": _title(start), "year": year, "today": dt.date.today().isoformat(),
    }
    dest.mkdir(parents=True)
    for src in SKELETON.rglob("*"):
        rel = src.relative_to(SKELETON)
        if mode != "band" and rel.as_posix() == "20 Fellowship/Band.md":
            continue
        target = dest / rel
        if src.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_render(src.read_text(encoding="utf-8"), values), encoding="utf-8")
    for folder in FOLDERS:
        (dest / folder).mkdir(parents=True, exist_ok=True)
    for t in TEMPLATES.glob("*.md"):
        shutil.copy2(t, dest / "_templates" / t.name)
    write_indexes(dest)

    from .obsidian import install_theme
    install_theme(dest)                       # Parchment / Shadow theme and the tale's callouts

    settings = cp.load_settings(slug, root)
    settings["campaign"] = {"name": values["name"], "mode": mode, "region": region, "start": start,
                            "year": year, "created": values["today"]}
    settings["difficulty"]["easy"] = easy
    cp.save_settings(settings, slug, root)
    cp.set_active(slug, root)
    return dest


def list_campaigns(root: Path | None = None) -> list[dict]:
    root = root or cp.vaults_root()
    out = []
    if not root.is_dir():
        return out
    active = cp.active_slug(root)
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
        if not (d / ".ringwraith").is_dir():
            continue
        s = cp.load_settings(d.name, root)
        out.append({"slug": d.name, "active": d.name == active, **s.get("campaign", {})})
    return out


def archive(slug: str, root: Path | None = None, delete: bool = True) -> Path:
    root = root or cp.vaults_root()
    src = cp.campaign_dir(slug, root)
    adir = root / "_archive"
    adir.mkdir(exist_ok=True)
    zpath = adir / f"{slug}-{dt.datetime.now():%Y%m%d-%H%M%S}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in src.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(src.parent))
    if delete:
        shutil.rmtree(src)
        if cp.active_slug(root) == slug:
            (root / ".active").unlink(missing_ok=True)
    return zpath


def reset(slug: str, root: Path | None = None) -> tuple[Path, Path]:
    """Archive a campaign and recreate it empty with the same settings."""
    root = root or cp.vaults_root()
    meta = cp.load_settings(slug, root).get("campaign", {})
    easy = cp.load_settings(slug, root)["difficulty"]["easy"]
    zpath = archive(slug, root)
    dest = create(slug, name=meta.get("name"), mode=meta.get("mode", "band"),
                  region=meta.get("region", "eriador"), start=meta.get("start", "bree"),
                  year=int(meta.get("year", 2965)), easy=easy, root=root)
    return zpath, dest


# --------------------------------------------------------------- notes

FM = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)


def session_note(n: int, slug: str | None = None, root: Path | None = None) -> Path:
    """Where session n's note is (it may not exist yet): `10 Campaign/Sessions/Session 004.md`."""
    return cp.campaign_dir(slug, root) / NOTE_TYPES["session"] / f"Session {int(n):03d}.md"


def hero_note(slug: str | None = None, root: Path | None = None) -> Path | None:
    """The campaign's hero sheet (the first note in the heroes folder), if there is one."""
    folder = cp.campaign_dir(slug, root) / NOTE_TYPES["hero"]
    notes = sorted(folder.glob("*.md")) if folder.is_dir() else []
    return notes[0] if notes else None


def hero_name(slug: str | None = None, root: Path | None = None) -> str | None:
    h = hero_note(slug, root)
    return (read_note(h)[0].get("name") or h.stem) if h else None


def read_note(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    m = FM.match(text)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, text[m.end():]


def write_note(path: Path, fm: dict, body: str) -> None:
    head = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=1000).rstrip()
    fileio.atomic_write(path, f"---\n{head}\n---\n{body if body.startswith(chr(10)) else chr(10) + body}")


def parse_value(raw: str) -> Any:
    """A value from the command line, read as YAML, except that wiki-links stay links: `[[Bree]]` is the
    text "[[Bree]]" (YAML would read it as a list inside a list), and `[[[A]], [[B]]]` a list of two links."""
    text = re.sub(r"\[\[[^\[\]]+\]\]", lambda m: json.dumps(m.group(0)), raw) if "[[" in raw else raw
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return raw


def get_path(data: dict, dotted: str) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(dotted)
        node = node[part]
    return node


def set_path(data: dict, dotted: str, value: Any) -> None:
    *parents, leaf = dotted.split(".")
    node = data
    for p in parents:
        node = node.setdefault(p, {})
    node[leaf] = value


def new_note(kind: str, name: str, slug: str | None = None, root: Path | None = None,
             extra: dict | None = None) -> Path:
    if kind not in NOTE_TYPES:
        raise cp.CampaignError(f"unknown note type {kind!r}; one of {', '.join(NOTE_TYPES)}")
    vault = cp.campaign_dir(slug, root)
    folder = vault / NOTE_TYPES[kind]
    folder.mkdir(parents=True, exist_ok=True)
    values = {"name": name, "today": dt.date.today().isoformat()}
    if kind == "session":
        n = 1 + max([int(m.group(1)) for f in folder.glob("Session *.md")
                     if (m := re.match(r"Session (\d+)", f.stem))] or [0])
        values["number"] = n
        fname = f"Session {n:03d}.md"
    else:
        fname = re.sub(r'[\\/:*?"<>|#^\[\]]', "", name).strip() + ".md"
    path = folder / fname
    if path.exists():
        raise cp.CampaignError(f"{path.relative_to(vault)} already exists")
    text = _render((TEMPLATES / f"{kind}.md").read_text(encoding="utf-8"), values)
    path.write_text(text, encoding="utf-8")
    if extra:
        fm, body = read_note(path)
        for k, v in extra.items():
            set_path(fm, k, v)
        write_note(path, fm, body)
    if kind == "session":
        # The state's `session` is what the chronicle, the road map and encounters go by: keep it in step
        # with the newest session note, so a forgotten hand edit can't overwrite the previous session's record.
        st = vault / ".ringwraith" / "state.md"
        if st.exists():
            with fileio.locked():
                sfm, sbody = read_note(st)
                sfm["session"] = values["number"]
                write_note(st, sfm, sbody)
    return path


ENCOUNTERS = "## Encounters"
_ENC_KEY = re.compile(r"^- \*\*Session (\d+)(?:, days? (\d+)(?:[–-]\d+)?)?[:.]?\*\*", re.I)


def _encounter_key(line: str, pos: int) -> tuple:
    m = _ENC_KEY.match(line)
    if not m:
        return (10 ** 6, 10 ** 6, pos)              # undated lines keep their place at the end
    return (int(m.group(1)), int(m.group(2)) if m.group(2) else 0, pos)


def sort_encounters(body: str, section: str = ENCOUNTERS) -> str:
    """Put a note's Encounters in story order: oldest first, by session and then day."""
    if section not in body:
        return body
    head, rest = body.split(section, 1)
    nxt = re.search(r"^## ", rest, re.M)
    block, tail = (rest[:nxt.start()], rest[nxt.start():]) if nxt else (rest, "")
    # Only the bullet list is reordered. Prose before it (an introduction) and after it stays where it is;
    # an indented line under a bullet is that bullet's continuation.
    intro, items, outro, cur = [], [], [], None
    for line in block.splitlines():
        if line.startswith("- "):                    # (prose between bullets is kept, after the list)
            cur = [line]
            items.append(cur)
        elif cur is not None and line.strip() and line[:1] in (" ", "\t"):
            cur.append(line)
        elif not items:
            intro.append(line)
        elif line.strip():
            outro.append(line)
            cur = None
    items = [it for _, it in sorted(((_encounter_key(it[0], i), it) for i, it in enumerate(items)), key=lambda x: x[0])]
    pre = "\n".join(intro).strip("\n")
    text = "\n".join("\n".join(it) for it in items)
    post = "\n".join(outro)
    parts = [p for p in (pre, text, post) if p]
    return f"{head}{section}\n" + "\n\n".join(parts) + "\n" + (f"\n{tail}" if tail else "")


@fileio.with_lock
def add_encounter(path: Path, text: str, session: int, day: int | None = None, section: str = ENCOUNTERS) -> str:
    """Add one encounter line (\"- **Session N, day D:** text\") to a note, in story order. Returns the line."""
    fm, body = read_note(path)
    stamp = f"Session {session}" + (f", day {day}" if day else "")
    line = f"- **{stamp}:** {text.strip()}"
    if line in body:
        return line
    if section not in body:
        body = body.rstrip("\n") + f"\n\n{section}\n"
    head, rest = body.split(section, 1)
    nxt = re.search(r"^## ", rest, re.M)
    block, tail = (rest[:nxt.start()], rest[nxt.start():]) if nxt else (rest, "")
    block = block.rstrip("\n") + "\n" + line + "\n"
    write_note(path, fm, sort_encounters(f"{head}{section}{block}" + (f"\n{tail}" if tail else ""), section))
    return line


def resolve_note(ref: str, slug: str | None = None, root: Path | None = None) -> Path:
    """Find a note by vault-relative path or by name (case-insensitive)."""
    vault = cp.campaign_dir(slug, root)
    p = vault / ref
    if p.is_file():
        return p
    if (vault / f"{ref}.md").is_file():
        return vault / f"{ref}.md"
    target = ref.lower().removesuffix(".md")
    hits = [f for f in vault.rglob("*.md") if f.stem.lower() == target and "_templates" not in f.parts]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise cp.CampaignError(f"no note named {ref!r}")
    raise cp.CampaignError(f"{ref!r} is ambiguous: {[str(h.relative_to(vault)) for h in hits]}")
