"""The fight tracker for the Ringwraith Table: one fight at a time, a skirmish (combat) or a Band battle.

The full state, numbers included, is Loremaster knowledge and lives in `.ringwraith/fight.json`; Ringwraith
reads it back from every `fight` call. The player sees what the hero can see (`public_view`): each foe's
state in words, an Endurance bar, Weary when its Hate or Resolve is spent, its Distinctive Features and the
weapons seen so far; for a battle, how the war party holds, the advantages and complications, the clash, the
leader focus and the Band's stance.

What the hero learns is shown too. A foe's `known` lists the numbers the hero has come to know (endurance,
hate, parry, armour, might: after fighting a while, a telling roll, or because they have fought its kind
before), and `abilities` the Fell Abilities it has shown.
"""

from __future__ import annotations

import json
from typing import Any

from .. import campaign as cp
from .. import fileio

FOE_STATES = ("fighting", "fled", "surrendered", "slain")
KNOWABLE = ("endurance", "hate", "parry", "armour", "might")


class FightError(ValueError):
    pass


def _file():
    return cp.private_dir() / "fight.json"


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


def _foe(spec: dict) -> dict:
    if not spec.get("name"):
        raise FightError("every foe needs a name")
    end = _int(spec.get("endurance"))
    hate = _int(spec.get("hate", spec.get("resolve")))
    return {
        "name": spec["name"], "note": spec.get("note") or spec["name"], "count": _int(spec.get("count")) or 1,
        "down": _int(spec.get("down")) or 0,
        "endurance": end, "endurance_max": _int(spec.get("endurance_max")) or end,
        "hate": hate, "hate_max": _int(spec.get("hate_max", spec.get("resolve_max"))) or hate,
        "hate_kind": "Resolve" if "resolve" in spec and "hate" not in spec else "Hate",
        "might": _int(spec.get("might")), "features": list(spec.get("features") or []),
        "weapons": list(spec.get("weapons") or []), "wounded": bool(spec.get("wounded")),
        "parry": _int(spec.get("parry")), "armour": _int(spec.get("armour")),
        "known": _known(spec.get("known")), "abilities": _abilities(spec.get("abilities")),
        "weary": bool(spec.get("weary")), "state": spec.get("state") or "fighting",
        "engaged": list(spec.get("engaged") or []),
    }


def _known(v) -> list[str]:
    if v in (True, "all"):
        return list(KNOWABLE)
    out = [str(k).lower() for k in (v or [])]
    bad = [k for k in out if k not in KNOWABLE]
    if bad:
        raise FightError(f"known is a list of {', '.join(KNOWABLE)} (or 'all')")
    return out


def _abilities(v) -> list[dict]:
    out = []
    for a in v or []:
        out.append({"name": a, "text": ""} if isinstance(a, str) else {"name": a.get("name"), "text": a.get("text", "")})
    return out


def start(kind: str, title: str, foes: list[dict], battle: dict | None = None, stance: str | None = None) -> dict:
    if kind not in ("combat", "battle"):
        raise FightError("kind is combat or battle")
    state = {"kind": kind, "title": title or ("A battle" if kind == "battle" else "A fight"), "round": 1,
             "stance": stance, "foes": [_foe(f) for f in foes or []], "battle": None, "log": []}
    if kind == "battle":
        b = dict(battle or {})
        res = _int(b.get("resistance"))
        state["battle"] = {"clash": _int(b.get("clash")) or 1, "resistance": res,
                           "resistance_max": _int(b.get("resistance_max")) or res, "might": _int(b.get("might")),
                           "objective": b.get("objective"), "objective_resistance": _int(b.get("objective_resistance")),
                           "objective_max": _int(b.get("objective_max")) or _int(b.get("objective_resistance")),
                           "advantages": list(b.get("advantages") or []),
                           "complications": list(b.get("complications") or []),
                           "focus": b.get("focus"), "band_stance": b.get("band_stance")}
    _save(state)
    return state


def update(changes: dict) -> dict:
    """Merge changes: round, stance, log (a line), foes (matched by name; new names are added), battle fields."""
    state = load()
    if not state:
        raise FightError("no fight in progress: start one first")
    for key in ("round", "stance", "title"):
        if changes.get(key) is not None:
            state[key] = _int(changes[key]) if key == "round" else changes[key]
    for spec in changes.get("foes") or []:
        foe = next((f for f in state["foes"] if f["name"] == spec.get("name")), None)
        if foe is None:
            state["foes"].append(_foe(spec))
            continue
        if spec.get("known") is not None:            # what the hero has learned only grows
            foe["known"] = sorted(set(foe.get("known") or []) | set(_known(spec["known"])), key=KNOWABLE.index)
        for a in _abilities(spec.get("abilities")):
            if all(a["name"] != b["name"] for b in foe.get("abilities") or []):
                foe.setdefault("abilities", []).append(a)
        for k in ("endurance", "endurance_max", "hate", "hate_max", "might", "count", "down", "parry", "armour"):
            src = "resolve" if k == "hate" and "resolve" in spec and "hate" not in spec else k
            if spec.get(src) is not None:
                foe[k] = _int(spec[src])
        for k in ("wounded", "weary"):
            if spec.get(k) is not None:
                foe[k] = bool(spec[k])
        for k in ("features", "weapons", "engaged"):
            if spec.get(k) is not None:
                foe[k] = list(spec[k])
        if spec.get("state"):
            if spec["state"] not in FOE_STATES:
                raise FightError(f"a foe's state is one of {', '.join(FOE_STATES)}")
            foe["state"] = spec["state"]
    if changes.get("battle") and state.get("battle"):
        b = state["battle"]
        for k, v in changes["battle"].items():
            if v is None:
                continue
            b[k] = _int(v) if k in ("clash", "resistance", "resistance_max", "might", "objective_resistance",
                                    "objective_max") else (list(v) if k in ("advantages", "complications") else v)
    if changes.get("log"):
        state["log"] = (state.get("log") or []) + [str(changes["log"])]
    _save(state)
    return state


def end(outcome: str) -> dict:
    state = load()
    if not state:
        raise FightError("no fight in progress")
    _save(None)
    return {"title": state["title"], "kind": state["kind"], "outcome": outcome or "", "log": state.get("log") or []}


# ---------------------------------------------------------------- what the player sees
def _health(cur: int | None, top: int | None) -> tuple[float | None, str]:
    if cur is None or not top:
        return None, ""
    r = max(0.0, min(1.0, cur / top))
    word = ("fresh" if r >= 0.99 else "lightly hurt" if r > 0.66 else "hurt" if r > 0.33
            else "badly hurt" if r > 0 else "down")
    return round(r, 2), word


def _hold(cur: int | None, top: int | None) -> tuple[float | None, str]:
    if cur is None or not top:
        return None, ""
    r = max(0.0, min(1.0, cur / top))
    return round(r, 2), ("holding" if r > 0.66 else "wavering" if r > 0.33 else "breaking" if r > 0 else "broken")


def _numbers(f: dict) -> dict:
    """The numbers the hero has come to know about a foe. Endurance and Hate are never shown as numbers:
    the bar and its word carry them, which keeps the player in the tale."""
    known, out = set(f.get("known") or []), {}
    if "might" in known and f.get("might") is not None:
        out["Might"] = str(f["might"])
    if "parry" in known and f.get("parry") is not None:
        out["Parry"] = f"+{f['parry']}" if f["parry"] else "–"
    if "armour" in known and f.get("armour") is not None:
        out["Armour"] = str(f["armour"])
    return out


def public_view(state: dict | None, portrait=None) -> dict | None:
    """The fight as the hero sees it: words and bars, no numbers."""
    if not state:
        return None
    foes = []
    for f in state["foes"]:
        bar, word = _health(f.get("endurance"), f.get("endurance_max"))
        if f["state"] != "fighting":
            word = f["state"]
        marks = [m for m, on in (("Wounded", f.get("wounded")),
                                 ("Weary", f.get("weary") or (f.get("hate") == 0 and f.get("hate_max")))) if on]
        foes.append({"name": f["name"], "count": f.get("count", 1), "down": f.get("down", 0),
                     "bar": None if f["state"] != "fighting" else bar, "word": word, "marks": marks,
                     "features": f.get("features") or [], "weapons": f.get("weapons") or [],
                     "engaged": f.get("engaged") or [], "state": f["state"], "known": _numbers(f),
                     "abilities": f.get("abilities") or [],
                     "image": portrait(f.get("note") or f["name"]) if portrait else None})
    out = {"kind": state["kind"], "title": state["title"], "round": state.get("round"), "stance": state.get("stance"),
           "foes": foes, "log": (state.get("log") or [])[-4:]}
    b = state.get("battle")
    if b:
        bar, word = _hold(b.get("resistance"), b.get("resistance_max"))
        obar, oword = _hold(b.get("objective_resistance"), b.get("objective_max"))
        out["battle"] = {"clash": b.get("clash"), "bar": bar, "word": word, "objective": b.get("objective"),
                         "objective_bar": obar, "objective_word": oword.replace("holding", "contested")
                         .replace("wavering", "yielding").replace("breaking", "nearly won").replace("broken", "won"),
                         "advantages": b.get("advantages") or [], "complications": b.get("complications") or [],
                         "focus": b.get("focus"), "band_stance": b.get("band_stance")}
    return out


def summary(state: dict) -> str:
    """The full state for the Loremaster, in one compact text (the tool's reply)."""
    lines = [f"{state['kind'].upper()}: {state['title']} · round {state.get('round')}"
             + (f" · hero stance {state['stance']}" if state.get("stance") else "")]
    for f in state["foes"]:
        hk = f.get("hate_kind", "Hate")
        lines.append(f"- {f['name']}{' x' + str(f['count']) if f.get('count', 1) > 1 else ''}"
                     f"{' (' + str(f['down']) + ' down)' if f.get('down') else ''}: {f['state']}, "
                     f"Endurance {f.get('endurance')}/{f.get('endurance_max')}, {hk} {f.get('hate')}/{f.get('hate_max')}"
                     f"{', Might ' + str(f['might']) if f.get('might') is not None else ''}"
                     f"{', Wounded' if f.get('wounded') else ''}{', Weary' if f.get('weary') else ''}"
                     f"{', engaged with ' + ', '.join(f['engaged']) if f.get('engaged') else ''}"
                     f"; the hero knows: {', '.join(f.get('known') or []) or 'no numbers'}"
                     f"{'; seen: ' + ', '.join(a['name'] for a in f['abilities']) if f.get('abilities') else ''}")
    b = state.get("battle")
    if b:
        lines.append(f"Battle: clash {b.get('clash')}, war party Resistance {b.get('resistance')}/{b.get('resistance_max')}"
                     f", Might {b.get('might')}; objective {b.get('objective') or '-'} "
                     f"{b.get('objective_resistance')}/{b.get('objective_max')}; advantages: "
                     f"{', '.join(b.get('advantages') or []) or '-'}; complications: "
                     f"{', '.join(b.get('complications') or []) or '-'}; focus {b.get('focus') or '-'}, "
                     f"Band stance {b.get('band_stance') or '-'}")
    return "\n".join(lines)
