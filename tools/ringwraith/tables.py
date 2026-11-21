"""Load, validate and roll lore tables (schema: docs/lore-format.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import dice

DOMAINS: dict[str, list[Any]] = {
    "feat": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, dice.EYE, dice.GANDALF],
    "feat-number": list(range(1, 11)),
    "success": list(range(1, 7)),
    "d6": list(range(1, 7)),
    "d12": list(range(1, 13)),
}


class TableError(ValueError):
    pass


# ---------------------------------------------------------------- loading

def load_all(tables_dir: Path) -> dict[str, dict]:
    tables: dict[str, dict] = {}
    for f in sorted(tables_dir.glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TableError(f"{f.name}: not a mapping")
        data["_file"] = f.name
        tid = data.get("id")
        if tid in tables:
            raise TableError(f"{f.name}: duplicate id {tid!r} (also in {tables[tid]['_file']})")
        tables[tid] = data
    return tables


# ------------------------------------------------------------- key matching

def _key_matches(key: Any, value: Any) -> bool:
    if isinstance(key, bool):
        return False
    if isinstance(key, int):
        return key == value
    k = str(key).strip().lower()
    if k in (dice.EYE, dice.GANDALF):
        return value == k
    if isinstance(value, int):
        if "-" in k or "–" in k:
            a, b = k.replace("–", "-").split("-", 1)
            try:
                return int(a) <= value <= int(b)
            except ValueError:
                return False
        if k.isdigit():
            return int(k) == value
    return False


def lookup(entries: dict, value: Any) -> tuple[Any, Any]:
    hits = [(k, v) for k, v in entries.items() if _key_matches(k, value)]
    if len(hits) != 1:
        raise TableError(f"value {value!r} matches {len(hits)} keys ({[h[0] for h in hits]})")
    return hits[0]


# --------------------------------------------------------------- validation

def validate(t: dict) -> list[str]:
    errs: list[str] = []
    name = t.get("_file", t.get("id", "?"))
    for req in ("id", "title", "source"):
        if req not in t:
            errs.append(f"{name}: missing '{req}'")
    if t.get("id") and t.get("_file") and t["_file"] != f"{t['id']}.yaml":
        errs.append(f"{name}: id {t['id']!r} does not match file name")
    kind = t.get("kind", "roll")

    if kind == "reference":
        if not isinstance(t.get("rows"), list) or not t["rows"]:
            errs.append(f"{name}: reference table needs a non-empty 'rows' list")
        return errs

    if kind == "threshold":
        for req in ("chances", "yes", "no", "gandalf", "eye"):
            if req not in t:
                errs.append(f"{name}: threshold table missing '{req}'")
        return errs

    dlist = t.get("dice")
    if not isinstance(dlist, list) or not dlist:
        return errs + [f"{name}: 'dice' must be a non-empty list"]
    bad = [d for d in dlist if d not in DOMAINS]
    if bad:
        return errs + [f"{name}: unknown dice {bad}; allowed {list(DOMAINS)}"]

    columns = t.get("columns")

    def walk(entries: Any, depth: int, path: str) -> None:
        if depth == len(dlist):
            if isinstance(entries, dict) and columns:
                missing = [c for c in columns if c not in entries]
                if missing:
                    errs.append(f"{name}: {path} missing columns {missing}")
            elif isinstance(entries, dict) and "text" not in entries and "then" not in entries:
                errs.append(f"{name}: {path} mapping leaf needs 'text' (or 'columns' on the table)")
            elif entries is None or entries == "":
                errs.append(f"{name}: {path} empty leaf")
            return
        if not isinstance(entries, dict):
            errs.append(f"{name}: {path} should be a mapping for die '{dlist[depth]}'")
            return
        for v in DOMAINS[dlist[depth]]:
            try:
                k, child = lookup(entries, v)
            except TableError as e:
                errs.append(f"{name}: {path}[{dlist[depth]}={v}] {e}")
                continue
        for k, child in entries.items():
            if not any(_key_matches(k, v) for v in DOMAINS[dlist[depth]]):
                errs.append(f"{name}: {path} key {k!r} matches no '{dlist[depth]}' result")
            walk(child, depth + 1, f"{path}/{k}")

    if "entries" not in t:
        errs.append(f"{name}: missing 'entries'")
    else:
        walk(t["entries"], 0, "entries")
    return errs


# ------------------------------------------------------------------ rolling

@dataclass
class TableRoll:
    table: str
    title: str
    rolls: list[tuple[str, Any]] = field(default_factory=list)   # (die, face)
    keys: list[Any] = field(default_factory=list)
    result: Any = None
    followups: list["TableRoll"] = field(default_factory=list)


def _roll_die(die: str, mode: str) -> tuple[Any, list[Any]]:
    if die == "feat":
        faces = [dice.roll_feat_face() for _ in range(1 if mode == "normal" else 2)]
        return dice.pick_feat(faces, mode), faces
    if die == "feat-number":
        return dice._rng.randint(1, 10), []
    if die in ("success", "d6"):
        return dice.roll_success_face(), []
    if die == "d12":
        return dice._rng.randint(1, 12), []
    raise TableError(f"unknown die {die}")


def roll(tables: dict[str, dict], table_id: str, *, mode: str = "normal",
         given: list[Any] | None = None, column: str | None = None, depth: int = 0) -> TableRoll:
    if table_id not in tables:
        raise TableError(f"no table {table_id!r}")
    t = tables[table_id]
    kind = t.get("kind", "roll")
    if kind != "roll":
        raise TableError(f"{table_id} is a {kind} table")
    out = TableRoll(table_id, t.get("title", table_id))
    node: Any = t["entries"]
    for i, die in enumerate(t["dice"]):
        if given and i < len(given):
            face = dice.parse_feat(given[i]) if die == "feat" else int(given[i])
            shown = [face]
        else:
            face, shown = _roll_die(die, mode if die == "feat" else "normal")
        out.rolls.append((die, face if not shown or len(shown) == 1 else shown))
        key, node = lookup(node, face)
        out.keys.append(key)
    if column and isinstance(node, dict):
        node = node.get(column, node)
    out.result = node
    nxt = node.get("then") if isinstance(node, dict) else None
    if nxt and depth < 5:
        out.followups.append(roll(tables, nxt, depth=depth + 1))
    return out


def telling(t: dict, chance: str | None = None, *, mode: str = "normal",
            given: Any = None) -> tuple[str, Any, str]:
    """Answer a yes/no question. Returns (chance, feat face, answer)."""
    chance = (chance or t.get("default", "middling")).lower()
    chances = {k.lower(): v for k, v in t["chances"].items()}
    if chance not in chances:
        raise TableError(f"chance must be one of {list(chances)}")
    if given is not None:
        face = dice.parse_feat(given)
    else:
        faces = [dice.roll_feat_face() for _ in range(1 if mode == "normal" else 2)]
        face = dice.pick_feat(faces, mode)
    if face == dice.GANDALF:
        answer = t["gandalf"]
    elif face == dice.EYE:
        answer = t["eye"]
    else:
        answer = t["yes"] if face >= chances[chance] else t["no"]
    return chance, face, answer


def format_leaf(leaf: Any) -> str:
    if isinstance(leaf, dict):
        main = leaf.get("text")
        rest = {k: v for k, v in leaf.items() if k not in ("text", "then")}
        parts = [str(main)] if main else []
        parts += [f"{k}: {v}" for k, v in rest.items()]
        return " | ".join(parts)
    return str(leaf)


def describe(r: TableRoll) -> str:
    dice_txt = ", ".join(
        f"{d} " + (" / ".join(dice.face_str(x) for x in f) if isinstance(f, list) else dice.face_str(f))
        for d, f in r.rolls)
    lines = [f"{r.title} [{dice_txt}] -> {format_leaf(r.result)}"]
    for f in r.followups:
        lines.append("  then " + describe(f))
    return "\n".join(lines)
