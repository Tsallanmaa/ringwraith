"""Game operations shared by the CLI and the web table: the roll log, the lore tables, the Telling table.

Both front ends call these, so a roll is logged and an oracle is worded the same way whichever one made it.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import campaign as cp
from . import config as cfg
from . import dice

_tables: dict[str, tuple] = {}


def log_roll(kind: str, label: str | None, text: str) -> None:
    """Append to the active campaign's roll log (silently skipped without a campaign)."""
    try:
        f = cp.private_dir() / "rolls.log"
    except cp.CampaignError:
        return
    line = "\t".join([time.strftime("%Y-%m-%d %H:%M:%S"), kind, label or "-", text.replace("\n", " / ")])
    with f.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def tables_dir() -> Path:
    return cfg.load().lore / "tables"


def all_tables() -> dict:
    """Every lore table by id. Parsing all of them takes a while (about 200 files), so they are kept until a
    table file is added, removed or changed."""
    from . import tables as tb
    tdir = tables_dir()
    if not tdir.is_dir():
        return {}
    files = sorted(tdir.glob("*.yaml"))
    key = tuple((f.name, f.stat().st_mtime_ns) for f in files)
    hit = _tables.get(str(tdir))
    if not (hit and hit[0] == key):
        hit = (key, tb.load_all(tdir))
        _tables[str(tdir)] = hit
    return hit[1]


def ask(chance: str, question: str | None = None, favoured: bool = False, ill: bool = False,
        given=None) -> tuple[str, object, str, str]:
    """The Telling table: (chance, feat face, answer, the logged line)."""
    from . import tables as tb
    tables = all_tables()
    if "telling" not in tables:
        raise tb.TableError("the Telling table isn't distilled yet (lore/tables/telling.yaml)")
    chance, face, answer = tb.telling(tables["telling"], chance, mode=dice.feat_mode(favoured, ill), given=given)
    text = f"Telling ({chance}) [feat {dice.face_str(face)}] -> {answer}"
    log_roll("ask", question, text)
    return chance, face, str(answer), text


def roll_table(table_id: str, favoured: bool = False, ill: bool = False, column: str | None = None,
               given=None, label: str | None = None):
    """Roll a lore table: (the result, the logged line). Raises tables.TableError for an unknown table."""
    from . import tables as tb
    r = tb.roll(all_tables(), table_id, mode=dice.feat_mode(favoured, ill), given=given, column=column)
    text = tb.describe(r)
    log_roll("table", label, text)
    return r, text
