"""Time in the tale: a day count, deadlines that count down, and counters that count up.

Kept in the campaign state (`.ringwraith/state.md` frontmatter):
    day: 7                    # day of the tale
    time: midday              # time of day, free text
    deadlines: [{name, due, note}]   # due = the day it falls on
    counters:  [{name, since}]       # since = the day it started (e.g. someone missing)
Only things the hero knows belong here: the side panel shows them to the player.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import campaign as cp
from . import fileio
from . import vault


def state(slug: str | None = None, root: Path | None = None) -> tuple[Path, dict, str]:
    path = cp.private_dir(slug, root) / "state.md"
    fm, body = vault.read_note(path) if path.exists() else ({}, "")
    return path, fm, body


def _save(path: Path, fm: dict, body: str) -> None:
    vault.write_note(path, fm, body)


def today(fm: dict) -> int:
    try:
        return int(fm.get("day") or 1)
    except (TypeError, ValueError):
        return 1


def _find(items: list[dict], name: str, prefix: bool = False) -> int | None:
    """The item called `name` (any case). With prefix=True a shortened name also works, but only if it
    matches exactly one item; an ambiguous one raises ValueError rather than picking the first."""
    key = name.strip().lower()
    names = [str(it.get("name", "")).strip().lower() for it in items]
    if key in names:
        return names.index(key)
    if not prefix or not key:
        return None
    hits = [i for i, n in enumerate(names) if n.startswith(key)]
    if len(hits) > 1:
        raise ValueError(f"'{name}' could mean " + ", ".join(repr(items[i]["name"]) for i in hits)
                         + "; give the full name")
    return hits[0] if hits else None


def describe(fm: dict) -> list[str]:
    """Human-readable lines for the deadlines and counters."""
    d = today(fm)
    lines = []
    for dl in sorted(fm.get("deadlines") or [], key=lambda x: x.get("due", 0)):
        left = int(dl.get("due", d)) - d
        when = ("today" if left == 0 else f"in {left} day{'s' if left != 1 else ''}" if left > 0
                else f"passed {-left} day{'s' if left != -1 else ''} ago")
        lines.append(f"{dl['name']}: {when} (day {dl.get('due')})" + (f" ({dl['note']})" if dl.get("note") else ""))
    for c in fm.get("counters") or []:
        lines.append(f"{c['name']}: day {d - int(c.get('since', d)) + 1}")
    return lines


@fileio.with_lock
def advance(days: int = 1, time: str | None = None, **kw) -> tuple[int, list[str]]:
    """Move the tale on. Returns the new day and warnings about deadlines reached or passed."""
    path, fm, body = state(**kw)
    old = today(fm)
    new = old + max(0, int(days))
    fm["day"] = new
    if time:
        fm["time"] = time
    _save(path, fm, body)
    warnings = []
    for dl in fm.get("deadlines") or []:
        due = int(dl.get("due", 0))
        if old < due <= new:
            warnings.append(f"DUE{' TODAY' if due == new else f' on day {due} (passed)'}: {dl['name']}")
        elif due == new:
            warnings.append(f"DUE TODAY: {dl['name']}")
    return new, warnings


@fileio.with_lock
def set_time(time: str, **kw) -> None:
    path, fm, body = state(**kw)
    fm["time"] = time
    _save(path, fm, body)


@fileio.with_lock
def add_deadline(name: str, in_days: int | None = None, due: int | None = None, note: str = "", **kw) -> dict:
    path, fm, body = state(**kw)
    if due is None:
        if in_days is None:
            raise ValueError("give in_days or due")
        due = today(fm) + int(in_days)
    items: list[dict[str, Any]] = list(fm.get("deadlines") or [])
    entry = {"name": name, "due": int(due), **({"note": note} if note else {})}
    i = _find(items, name)
    if i is None:
        items.append(entry)
    else:
        items[i] = entry
    fm["deadlines"] = items
    _save(path, fm, body)
    return entry


@fileio.with_lock
def remove(kind: str, name: str, **kw) -> dict | None:
    """Remove a deadline or counter (kind: 'deadlines' or 'counters') by name or unique prefix."""
    path, fm, body = state(**kw)
    items = list(fm.get(kind) or [])
    i = _find(items, name, prefix=True)
    if i is None:
        return None
    gone = items.pop(i)
    fm[kind] = items
    _save(path, fm, body)
    return gone


@fileio.with_lock
def add_counter(name: str, since: int | None = None, **kw) -> dict:
    path, fm, body = state(**kw)
    entry = {"name": name, "since": int(since if since is not None else today(fm))}
    items = list(fm.get("counters") or [])
    i = _find(items, name)
    if i is None:
        items.append(entry)
    else:
        items[i] = entry
    fm["counters"] = items
    _save(path, fm, body)
    return entry
