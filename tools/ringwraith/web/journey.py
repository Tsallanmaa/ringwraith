"""The journey tracker for the Ringwraith Table: one journey at a time, shown on the Journey panel.

A journey is the road from one place to another, told as a chain of moments: the marching tests, the events
the journey tables bring, and the interludes between them (an evening's camp, a talk on the road, a view, a
memory). The tracker keeps the route (hexes, which stretches are road), how far the Company has come, every
moment with the fatigue it cost, and writes the journey note in the vault from it, so the panel, the note and
the Tale panel always agree.

Everything here is player-facing. The land types along the way (border, wild, dark) are Loremaster-only:
they are never stored here, so they can't reach the panel.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from .. import campaign as cp
from .. import clock, fileio, vault

KINDS = ("march", "event", "interlude", "rest", "other")
ENDINGS = ("arrived", "abandoned")


class JourneyError(ValueError):
    pass


def _file():
    return cp.private_dir() / "journey.json"


def load() -> dict | None:
    f = _file()
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except ValueError:
        return None


def _save(state: dict | None) -> None:
    f = _file()
    if state is None:
        f.unlink(missing_ok=True)
        return
    fileio.atomic_write(f, json.dumps(state, ensure_ascii=False, indent=2))


def _today() -> int:
    return clock.today(clock.state()[1])


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


@fileio.with_lock
def start(frm: str, to: str, title: str = "", season: str = "", mode: str = "", via: list[str] | None = None,
          hexes: int | None = None, plan: dict | None = None) -> dict:
    """Set out. The route comes from the planned journey (plan_journey) when there is one."""
    if not frm or not to:
        raise JourneyError("a journey needs from and to")
    if load():
        raise JourneyError("a journey is already under way; end it first (action 'end')")
    road: list[bool] = []
    if plan and plan.get("to") == to:
        total = _int(plan.get("hexes"), 0)
        road = [bool(r) for r in (plan.get("road_in_order") or [])][:total]
        miles = plan.get("miles")
    else:
        total, miles = _int(hexes, 0), None
    state = {
        "id": uuid.uuid4().hex[:8], "title": title or f"{frm} to {to}", "from": frm, "to": to,
        "via": list(via or []), "season": season, "mode": mode, "start_day": _today(), "hexes": total,
        "miles": miles, "road": road, "done": 0, "log": [], "fatigue": {"hero": 0, "band": 0},
        "status": "underway", "note": None,
    }
    state["note"] = _write_note(state, create=True)
    _set_state_journey(state["title"])
    _save(state)
    return state


@fileio.with_lock
def log(entry: dict) -> tuple[dict, dict]:
    """Record a moment of the road. Returns (state, the entry as stored)."""
    state = load()
    if not state:
        raise JourneyError("no journey under way; start one first")
    kind = entry.get("kind") or "other"
    if kind not in KINDS:
        raise JourneyError(f"kind must be one of {', '.join(KINDS)}")
    if not (entry.get("title") or entry.get("text")):
        raise JourneyError("say what happened: a title or a line of text")
    if entry.get("hexes_done") is not None:
        state["done"] = max(0, _int(entry["hexes_done"], state["done"]))
        if state["hexes"]:
            state["done"] = min(state["done"], state["hexes"])
    fh, fb = _int(entry.get("fatigue_hero")), _int(entry.get("fatigue_band"))
    e = {"id": uuid.uuid4().hex[:6], "kind": kind, "day": _today(), "title": str(entry.get("title") or "").strip(),
         "text": str(entry.get("text") or "").strip(), "at": str(entry.get("at") or "").strip(),
         "who": str(entry.get("who") or "").strip(), "outcome": str(entry.get("outcome") or "").strip(),
         "hex": state["done"], "fatigue_hero": fh, "fatigue_band": fb}
    state["log"].append(e)
    state["fatigue"]["hero"] += fh
    state["fatigue"]["band"] += fb
    if fh:
        _add_hero_fatigue(fh)
    _write_note(state)
    _save(state)
    return state, e


@fileio.with_lock
def end(outcome: str = "", status: str = "arrived") -> dict:
    state = load()
    if not state:
        raise JourneyError("no journey under way")
    if status not in ENDINGS:
        raise JourneyError(f"status must be one of {', '.join(ENDINGS)}")
    state["status"], state["outcome"], state["end_day"] = status, outcome, _today()
    if status == "arrived" and state["hexes"]:
        state["done"] = state["hexes"]
    _write_note(state)
    _set_state_journey("")
    _save(None)
    return state


# ---------------------------------------------------------------- the vault
def _add_hero_fatigue(n: int) -> None:
    """Fatigue the road costs the hero goes straight onto the sheet (the single source of truth)."""
    h = vault.hero_note()
    if not h:
        return
    fm, body = vault.read_note(h)
    fm["fatigue"] = max(0, _int(fm.get("fatigue")) + n)
    vault.write_note(h, fm, body)


def _set_state_journey(title: str) -> None:
    path, fm, body = clock.state()
    if not path.exists():
        return
    fm["journey"] = f"[[{title}]]" if title else ""
    vault.write_note(path, fm, body)


def _events_md(state: dict) -> str:
    lines = []
    for e in state["log"]:
        where = f", {e['at']}" if e["at"] else (f", hex {e['hex']}/{state['hexes']}" if state["hexes"] else "")
        head = f"**Day {e['day']}{where} · {e['title'] or e['kind'].capitalize()}**"
        tail = []
        if e["who"]:
            tail.append(e["who"])
        if e["outcome"]:
            tail.append(e["outcome"])
        cost = " · ".join(x for x in (f"hero fatigue +{e['fatigue_hero']}" if e["fatigue_hero"] else "",
                                      f"Band fatigue +{e['fatigue_band']}" if e["fatigue_band"] else "") if x)
        lines.append(f"- {head}" + (f" ({'; '.join(tail)})" if tail else "") + (f": {e['text']}" if e["text"] else "")
                     + (f" *{cost}*" if cost else ""))
    if state.get("status") in ENDINGS:
        lines.append(f"- **Day {state.get('end_day')} · {'Arrived' if state['status'] == 'arrived' else 'Turned back'}**"
                     + (f": {state['outcome']}" if state.get("outcome") else ""))
    return "\n".join(lines) + "\n" if lines else "*Nothing yet.*\n"


def _write_note(state: dict, create: bool = False) -> str | None:
    """Create or update the journey note: its frontmatter and its Events section, from the tracker."""
    from .. import chronicle
    root = cp.campaign_dir()
    path = root / state["note"] if state.get("note") else None
    if path is None or not path.exists():
        if not create:
            return state.get("note")
        name = re.sub(r'[\\/:*?"<>|#^\[\]]', "", state["title"]).strip()
        path = root / vault.NOTE_TYPES["journey"] / f"{name}.md"
        if not path.exists():
            path = vault.new_note("journey", state["title"])
    fm, body = vault.read_note(path)
    reached = [e["at"] for e in state["log"] if e["at"]]
    fm.update({
        "status": state.get("status", "underway"), "from": f"[[{state['from']}]]", "to": f"[[{state['to']}]]",
        "season": state.get("season") or fm.get("season") or "", "hexes": state["done"],
        "days": max(1, _today() - state["start_day"] + 1), "start_day": state["start_day"],
        "end_day": state.get("end_day") or fm.get("end_day"), "fatigue_gained": state["fatigue"]["hero"],
        "route": [f"[[{p}]]" for p in dict.fromkeys(reached)],
    })
    vault.write_note(path, fm, body)
    chronicle.write(path, _events_md(state), heading="## Events", intro="")
    return path.relative_to(root).as_posix()


# ---------------------------------------------------------------- what the panel shows
def public_view(state: dict | None) -> dict | None:
    if not state:
        return None
    return {
        "title": state["title"], "from": state["from"], "to": state["to"], "season": state.get("season", ""),
        "mode": state.get("mode", ""), "hexes": state["hexes"], "miles": state.get("miles"),
        "road": state.get("road", []), "done": state["done"], "start_day": state["start_day"],
        "day_on_road": max(1, _today() - state["start_day"] + 1), "fatigue": state["fatigue"],
        "log": [{k: e[k] for k in ("id", "kind", "day", "title", "text", "at", "who", "outcome", "hex",
                                   "fatigue_hero", "fatigue_band")} for e in state["log"]],
    }


def summary(state: dict) -> str:
    """For Ringwraith: where the journey stands, in one short block."""
    left = f"{state['hexes'] - state['done']} of {state['hexes']} hexes to go" if state["hexes"] else "distance not counted"
    last = state["log"][-1] if state["log"] else None
    return (f"Journey '{state['title']}': day {max(1, _today() - state['start_day'] + 1)} on the road, {left}; "
            f"fatigue so far hero +{state['fatigue']['hero']}, Band +{state['fatigue']['band']}; "
            f"{len(state['log'])} moment(s) recorded" + (f", last: {last['kind']} '{last['title']}'" if last else "")
            + ". The journey note is kept up to date for you.")
