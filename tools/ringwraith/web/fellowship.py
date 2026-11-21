"""The Fellowship Phase tracker for the Ringwraith Table: one phase at a time, shown on the Fellowship panel.

A phase is a checklist that can span sessions, so its progress lives in `.ringwraith/fellowship.json` until the
phase ends: the duration, which steps are done, the undertakings allowed and chosen, the interruption (Band), and a
short log. Nothing in it is hidden from the player; the panel also shows the hero's Skill and Adventure points,
read live from the hero note (`xp`), so spending them shows at once. A new session picks the phase up with
`show`, which says what is done and what comes next.
"""

from __future__ import annotations

import json
from typing import Any

from .. import campaign as cp
from .. import fileio

DURATIONS = ("hurried", "brief", "extended", "yule")
STEPS = {"recovery": "Recovery", "updates": "Points & gifts", "interruption": "Interruption",
         "undertakings": "Undertakings", "close": "Time passes"}


class FellowshipError(ValueError):
    pass


def _file():
    return cp.private_dir() / "fellowship.json"


def load() -> dict | None:
    f = _file()
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except ValueError:
        return None


def _save(state: dict | None) -> None:
    f = _file()
    if state is None:
        if f.exists():
            f.unlink()
        return
    fileio.atomic_write(f, json.dumps(state, ensure_ascii=False, indent=2))


def _band() -> bool:
    try:
        return (cp.load_settings().get("campaign") or {}).get("mode") == "band"
    except Exception:  # noqa: BLE001 - no settings: treat as a lone hero
        return False


def _steps(duration: str, band: bool) -> list[str]:
    """The steps this phase has: a Band rolls for an interruption unless the phase is Hurried."""
    return [k for k in STEPS if k != "interruption" or (band and duration != "hurried")]


def _duration(v: Any) -> str:
    d = str(v or "").strip().lower()
    if d not in DURATIONS:
        raise FellowshipError(f"duration: one of {', '.join(DURATIONS)}")
    return d


def _keys(v: Any) -> list[str]:
    out = []
    for k in [v] if isinstance(v, str) else v or []:
        k = str(k).strip().lower()
        if k not in STEPS:
            raise FellowshipError(f"step '{k}': one of {', '.join(STEPS)}")
        out.append(k)
    return out


@fileio.with_lock
def start(duration: str, place: str = "", undertakings: int | None = None, band: bool | None = None) -> dict:
    d = _duration(duration)
    band = _band() if band is None else band
    state = {"duration": d, "place": place or "", "band": band, "steps": _steps(d, band), "done": [],
             "undertakings": None if undertakings is None else int(undertakings), "chosen": [],
             "interruption": "", "log": []}
    _save(state)
    return state


@fileio.with_lock
def update(changes: dict) -> dict:
    """Merge changes: done (a step or steps finished), undo (steps to reopen), undertakings (how many are allowed;
    lower it when an interruption costs one), chosen (an undertaking taken), interruption (what befell the Band),
    duration, place, log (one line)."""
    state = load()
    if not state:
        raise FellowshipError("no Fellowship Phase in progress: start one first")
    if changes.get("duration"):
        state["duration"] = _duration(changes["duration"])
        state["steps"] = _steps(state["duration"], state.get("band", False))
    if changes.get("place") is not None:
        state["place"] = str(changes["place"])
    if changes.get("undertakings") is not None:
        state["undertakings"] = max(0, int(changes["undertakings"]))
    if changes.get("chosen"):
        state["chosen"] = state.get("chosen", []) + [str(changes["chosen"])]
    if changes.get("interruption"):
        state["interruption"] = str(changes["interruption"])
    for k in _keys(changes.get("done")):
        if k not in state["done"]:
            state["done"].append(k)
    for k in _keys(changes.get("undo")):
        if k in state["done"]:
            state["done"].remove(k)
    if changes.get("log"):
        state["log"] = state.get("log", []) + [str(changes["log"])]
    _save(state)
    return state


@fileio.with_lock
def end(outcome: str) -> dict:
    state = load()
    if not state:
        raise FellowshipError("no Fellowship Phase in progress")
    _save(None)
    return {"duration": state["duration"], "place": state.get("place") or "", "outcome": outcome or "",
            "chosen": state.get("chosen") or []}


def _next(state: dict) -> str | None:
    return next((k for k in state["steps"] if k not in state["done"]), None)


# ---------------------------------------------------------------- what the table shows
def public_view(state: dict | None, xp: dict | None = None) -> dict | None:
    if not state:
        return None
    nxt = _next(state)
    return {"duration": state["duration"], "place": state.get("place") or "",
            "steps": [{"key": k, "label": STEPS[k], "done": k in state["done"], "next": k == nxt}
                      for k in state["steps"]],
            "undertakings": state.get("undertakings"), "chosen": state.get("chosen") or [],
            "interruption": state.get("interruption") or "",
            "xp": {"skill": (xp or {}).get("skill") or 0, "adventure": (xp or {}).get("adventure") or 0},
            "log": (state.get("log") or [])[-4:]}


def summary(state: dict | None) -> str:
    """Where the phase stands, for the Loremaster (and for picking it up in a new session)."""
    if not state:
        return "no Fellowship Phase in progress"
    nxt = _next(state)
    u = state.get("undertakings")
    und = (f"undertakings {len(state.get('chosen') or [])}/{u if u is not None else '?'}"
           + (f" ({', '.join(state['chosen'])})" if state.get("chosen") else ""))
    return (f"fellowship phase: {state['duration']}{' at ' + state['place'] if state.get('place') else ''}; "
            f"done: {', '.join(state['done']) or 'nothing yet'}; next: {nxt or 'end the phase'}; {und}"
            + (f"; interruption: {state['interruption']}" if state.get("interruption") else ""))
