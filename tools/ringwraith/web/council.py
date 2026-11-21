"""The council tracker for the Ringwraith Table: one council at a time, shown on the Council panel.

The full state lives in `.ringwraith/council.json` and is Loremaster knowledge: the Resistance and the running
count of successes. The player sees what the hero can tell (`public_view`): who is listening and their mood, what
the hero asks, how far they have been swayed (a bar and a word, never the numbers), how many exchanges the
listeners will allow (once the introduction has set it) and how many are spent, and the last few exchanges.
"""

from __future__ import annotations

import json
from typing import Any

from .. import campaign as cp
from .. import fileio


class CouncilError(ValueError):
    pass


def _file():
    return cp.private_dir() / "council.json"


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


def _int(v: Any) -> int | None:
    return None if v is None or v == "" else int(v)


def _who(v) -> list[dict]:
    """The listeners: names, or {name, note (for the portrait)}."""
    if isinstance(v, (str, dict)):
        v = [v]
    out = []
    for x in v or []:
        name = str(x.get("name") or "") if isinstance(x, dict) else str(x)
        if name:
            out.append({"name": name, "note": (x.get("note") if isinstance(x, dict) else None) or name})
    return out


@fileio.with_lock
def start(title: str, who, request: str, resistance: int | None, attitude: str | None = None) -> dict:
    if not who:
        raise CouncilError("who: the person or people the hero speaks to")
    state = {"title": title or "A council", "who": _who(who), "request": request or "",
             "resistance": _int(resistance), "successes": 0, "rounds": None, "used": 0,
             "attitude": attitude or "", "log": []}
    _save(state)
    return state


@fileio.with_lock
def update(changes: dict) -> dict:
    """Merge changes: successes (the running count) or add (successes to add), rounds (the time limit, set by the
    introduction), used (exchanges spent), a log line, attitude, request, resistance, who, title."""
    state = load()
    if not state:
        raise CouncilError("no council in progress: start one first")
    for k in ("title", "request", "attitude"):
        if changes.get(k) is not None:
            state[k] = str(changes[k])
    if changes.get("who"):
        state["who"] = _who(changes["who"])
    for k in ("resistance", "rounds", "successes", "used"):
        if changes.get(k) is not None:
            state[k] = _int(changes[k])
    if changes.get("add") is not None:
        state["successes"] = (state.get("successes") or 0) + _int(changes["add"])
    if changes.get("log"):
        state["log"] = (state.get("log") or []) + [str(changes["log"])]
    _save(state)
    return state


@fileio.with_lock
def end(outcome: str) -> dict:
    state = load()
    if not state:
        raise CouncilError("no council in progress")
    _save(None)
    return {"title": state["title"], "outcome": outcome or "", "log": state.get("log") or []}


# ---------------------------------------------------------------- what the player sees
def _swayed(got: int, need: int | None) -> tuple[float | None, str]:
    if not need:
        return None, ""
    r = max(0.0, min(1.0, got / need))
    return round(r, 2), ("unmoved" if r == 0 else "listening" if r < 0.4 else "wavering" if r < 0.75
                         else "nearly won" if r < 1 else "won over")


def public_view(state: dict | None, portrait=None) -> dict | None:
    if not state:
        return None
    bar, word = _swayed(state.get("successes") or 0, state.get("resistance"))
    return {"title": state["title"], "request": state.get("request") or "", "attitude": state.get("attitude") or "",
            "who": [{"name": w["name"], "image": portrait(w.get("note") or w["name"]) if portrait else None}
                    for w in state.get("who") or []],
            "bar": bar, "word": word, "rounds": state.get("rounds"), "used": state.get("used") or 0,
            "log": (state.get("log") or [])[-4:]}


def summary(state: dict | None) -> str:
    """The Loremaster's view, numbers included."""
    if not state:
        return "no council"
    rounds = f"{state.get('used') or 0}/{state['rounds']} exchanges" if state.get("rounds") else \
        f"{state.get('used') or 0} exchanges (no time limit set yet)"
    return (f"council: {state['title']} with {', '.join(w['name'] for w in state.get('who') or [])}; "
            f"request: {state.get('request') or '-'}; successes {state.get('successes') or 0}/"
            f"{state.get('resistance') if state.get('resistance') is not None else '?'}; {rounds}; "
            f"attitude: {state.get('attitude') or '-'}")
