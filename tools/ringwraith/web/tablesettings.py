"""The table's Settings dialog: the campaign settings a player may change from the page.

Only the keys and values listed here can be written, whatever the page sends. Changes are saved to the
campaign's settings (`.ringwraith/settings.yaml`) at once. Ringwraith hears of them with the player's next
message; a new model takes over at the start of the next turn, in the same conversation.
"""

from __future__ import annotations

from typing import Any

from .. import campaign as cp

# key: (label, help, [(value, label, hint)])
FIELDS: dict[str, tuple[str, str, list[tuple[Any, str, str]]]] = {
    "table.model": ("Loremaster's model", "Which Claude plays the Loremaster. Play counts against your plan's "
                    "usage limits; Opus uses them fastest.", [
        (None, "Account default", "Whatever Claude Code uses for your account"),
        ("opus", "Opus", "The most faithful Loremaster; the heaviest on usage"),
        ("sonnet", "Sonnet", "Much lighter on usage; a good choice on a smaller plan"),
        ("haiku", "Haiku", "The lightest; may lose track of the rules and procedures"),
        ("fable", "Fable", "Anthropic's top tier, where your plan includes it"),
    ]),
    "play.oracle": ("Oracles", "Who reads what the oracles answer, when the world is asked a question.", [
        ("loremaster", "Ringwraith reads them", "Ringwraith tells what the answer means"),
        ("player", "You read them", "Ringwraith suggests a reading; you accept it or give your own"),
    ]),
    "play.paths": ("Paths", "A few ways forward as cards at decision points.", [
        (True, "On", "Cards at decision points, and whenever you type /paths"),
        (False, "Off", "You come up with every choice yourself; /paths still shows them"),
    ]),
    "dice.mode": ("Dice", "Who rolls the dice.", [
        ("auto", "Rolled for you", "The table rolls when you press the button"),
        ("manual", "Your own dice", "You roll real dice and enter what they show"),
    ]),
    "difficulty.easy": ("Easy mode", "Lower TNs and gentler odds, for a lighter game.", [
        (False, "Off", "The standard TNs"),
        (True, "On", "Easier rolls"),
    ]),
    "difficulty.encounters": ("Encounters", "How fights are sized and resolved.", [
        ("story", "For the story", "Fights sized and resolved to keep the tale going"),
        ("standard", "By the book", "Foes and fights as the rules give them"),
    ]),
    "art.enabled": ("Paintings", "Scenes and portraits painted on your own GPU.", [
        (True, "On", "Paint scenes, portraits and adversaries"),
        (False, "Off", "No paintings in this campaign"),
    ]),
}


class SettingsError(ValueError):
    pass


def _get(s: dict, dotted: str) -> Any:
    for k in dotted.split("."):
        s = (s or {}).get(k) if isinstance(s, dict) else None
    return s


def view() -> dict:
    """The fields with their current values, for the dialog."""
    s = cp.load_settings()
    return {"fields": [{"key": k, "label": lab, "help": hlp, "value": _get(s, k),
                        "options": [{"value": v, "label": vl, "hint": vh} for v, vl, vh in opts]}
                       for k, (lab, hlp, opts) in FIELDS.items()]}


def apply(values: dict) -> list[dict]:
    """Save the changed values; returns [{key, label, value, old}] for what changed. Anything not listed in
    FIELDS, or a value not among a field's options, is refused."""
    if not isinstance(values, dict):
        raise SettingsError("settings: expected an object")
    s = cp.load_settings()
    changes = []
    for k, v in values.items():
        if k not in FIELDS:
            raise SettingsError(f"settings: '{k}' can't be changed here")
        match = [o for o in FIELDS[k][2] if type(o[0]) is type(v) and o[0] == v]   # 1 is not True
        if not match:
            raise SettingsError(f"settings: {v!r} isn't a choice for {FIELDS[k][0]}")
        old = _get(s, k)
        if old != v or type(old) is not type(v):
            changes.append({"key": k, "label": FIELDS[k][0], "value": match[0][1], "old": old, "new": v})
    for c in changes:
        cp.set_value(c["key"], c["new"])
    return changes


def describe(changes: list[dict]) -> str:
    return "; ".join(f"{c['label']}: {c['value']}" for c in changes)
