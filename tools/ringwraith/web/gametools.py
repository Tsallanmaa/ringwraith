"""Game tools for Ringwraith in the web app, served in-process to the Agent SDK.

They wrap the same modules as the CLI, but report to the browser as they go: rolls appear in the
dice tray, scene changes on the stage, Paths as cards. Hero and Band rolls wait for the player,
who sees the odds and decides on Hope (or enters physical dice).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from .. import art, artqueue, clock, dice, fileio, geo, ops, vault
from .. import campaign as cp
from .. import config as cfg
from .hub import Hub
from .views import _hero_xp, _portrait, current_scene, geo_view, sheet  # noqa: F401 (server and engine use them from here)

SERVER = "rw"


def _text(s: str) -> dict:
    return {"content": [{"type": "text", "text": s}]}


def _err(s: str) -> dict:
    return {"content": [{"type": "text", "text": s}], "is_error": True}


def _face(f: Any) -> str:
    return "eye" if f == dice.EYE else "gandalf" if f == dice.GANDALF else str(f)


def hero_note() -> Path | None:
    return vault.hero_note()


def _fought_before(name: str) -> bool:
    """Has the hero fought this kind of foe? (Its adversary note holds a stat block, or says it was encountered.)"""
    try:
        fm, _ = vault.read_note(vault.resolve_note(name))
    except cp.CampaignError:
        return False
    return fm.get("type") == "adversary" and bool(fm.get("statblock_from") or fm.get("encountered"))


def player_reads_oracles() -> bool:
    return cp.load_settings()["play"]["oracle"] == "player"


def build(hub: Hub, turn: dict | None = None):
    """Create the in-process MCP server and the list of its tool names.

    `turn` is shared with the engine: turn["story_since_roll"] is False while the outcome of the
    last roll or oracle hasn't been told as story yet.
    """
    turn = turn if turn is not None else {}

    async def outcome_told() -> bool:
        """Has the story told what the last roll or oracle led to? Gives the engine a moment to catch up
        on text that was written just before this tool call."""
        for _ in range(6):
            if turn.get("story_since_roll", True) or turn.get("pending_story"):
                return True
            await asyncio.sleep(0.1)
        return False

    async def push_sheet() -> None:
        try:
            await hub.emit({"t": "sheet", "sheet": sheet()})
        except cp.CampaignError:
            pass

    # ------------------------------------------------------------ dice
    @tool("request_roll",
          "Ask the player to make a hero (or Band) test. The dice tray shows the stakes, the TN and the "
          "exact odds with and without Hope; the player chooses to roll, spend Hope, or enter physical "
          "dice. Waits for the player. Returns the result, or the player's words if they spoke instead.",
          {"type": "object",
           "properties": {
               "who": {"type": "string", "description": "hero name, 'Band', or the Ally's name"},
               "what": {"type": "string", "description": "skill, proficiency or Disposition, e.g. 'Insight'"},
               "dice": {"type": "integer", "description": "Success dice from the rating, before Hope"},
               "tn": {"type": "integer"},
               "stakes": {"type": "string", "description": "one or two sentences: what success and failure mean, risk level"},
               "favoured": {"type": "boolean"}, "ill_favoured": {"type": "boolean"},
               "bonus": {"type": "integer", "description": "gain (Nd)"},
               "penalty": {"type": "integer", "description": "lose (Nd)"},
               "inspired": {"type": "boolean", "description": "already Inspired (Hope gives +2d)"},
               "weary": {"type": "boolean"}, "miserable": {"type": "boolean"},
               "hope_allowed": {"type": "boolean", "description": "false if Hope cannot be spent on this roll"},
               "chained": {"type": "boolean",
                           "description": "true only if this roll follows directly from the previous one with "
                                          "nothing to tell in between (e.g. Protection after a hit, Endurance "
                                          "test after a failed Clash)"},
           },
           "required": ["who", "what", "dice", "tn", "stakes"]})
    async def request_roll(a: dict) -> dict:
        if turn.get("owe_reply"):
            for _ in range(6):                  # give the engine a moment to see text written just now
                await asyncio.sleep(0.1)
                if not turn.get("owe_reply"):
                    break
            else:
                said = turn.get("owe_reply")
                return _err(f"Not asked. The player spoke instead of rolling ({said!r}) and hasn't had an answer. "
                            "Answer them first in your reply text, which the player sees (your thinking is "
                            "hidden): agree or explain your ruling and what it changes. Then call request_roll "
                            "again if the roll is still needed.")
        chained = a.get("chained") in (True, "true", "True", 1)
        same = turn.get("last_roll") == (a.get("who"), str(a.get("what", "")).lower())
        if chained and same and not await outcome_told():
            return _err("Not rolled: that is the roll just made, and an action is never re-rolled. Tell its "
                        "outcome as story now, in your reply text (your thinking is hidden from the player).")
        if not chained and not await outcome_told():
            return _err("Not rolled. First tell the outcome of the previous roll or oracle as story in your "
                        "reply text, which the player sees (your thinking is hidden: story told only there is "
                        "lost). Then call request_roll again. Never re-roll an action that was already rolled. "
                        "Pass chained: true only for a roll that follows mechanically from the last (Protection "
                        "after a hit), never to skip telling a story.")
        kw = dict(favoured=bool(a.get("favoured")), ill=bool(a.get("ill_favoured")),
                  bonus=int(a.get("bonus") or 0), penalty=int(a.get("penalty") or 0),
                  inspired=bool(a.get("inspired")), weary=bool(a.get("weary")),
                  miserable=bool(a.get("miserable")))
        rating, tn = int(a["dice"]), int(a["tn"])
        o_plain = dice.odds(rating, tn, **kw)
        o_hope = dice.odds(rating, tn, hope=True, **kw)
        o_insp = dice.odds(rating, tn, hope=True, **{**kw, "inspired": True})
        settings = cp.load_settings()
        h = hero_note()
        hope_now = vault.get_path(vault.read_note(h)[0], "hope.current") if h else None
        mode = dice.feat_mode(kw["favoured"], kw["ill"])
        ans = await hub.ask("roll", {
            "t": "roll_request", "who": a["who"], "what": a["what"], "tn": tn, "stakes": a.get("stakes", ""),
            "mode": mode, "flags": [k for k in ("weary", "miserable", "inspired") if kw[k]],
            "bonus": kw["bonus"], "penalty": kw["penalty"],
            "dice": {"plain": o_plain.dice, "hope": o_hope.dice},
            "odds": {"plain": vars(o_plain), "hope": vars(o_hope),
                     **({} if kw["inspired"] else {"inspired": vars(o_insp)})},
            "hope_allowed": a.get("hope_allowed", True) and bool(hope_now),
            "hope_now": hope_now, "manual": settings["dice"]["mode"] == "manual",
        })
        if ans.get("action") == "talk":
            await hub.emit({"t": "roll_cancelled", "id": ans.get("_id")})
            turn["owe_reply"] = ans.get("text", "") or "…"     # cleared when Ringwraith writes text
            return _text(f"The player did not roll yet. They said: {ans.get('text', '')!r}. "
                         "Answer them in your reply text, which the player sees (not only in your thinking), then call "
                         "request_roll again if the roll is still needed.")
        if ans.get("action") == "cancel":
            await hub.emit({"t": "roll_cancelled", "id": ans.get("_id")})
            return _text("The player cancelled the roll. Ask what they do instead.")
        hope = ans.get("action") == "hope"
        if ans.get("success") is not None:
            want = o_hope.dice if hope else o_plain.dice
            need_feat = 1 if mode == "normal" else 2
            if len(ans["success"]) != want or len(ans.get("feat") or []) != need_feat:
                await hub.emit({"t": "roll_cancelled", "id": ans.get("_id")})
                return _err(f"The player's dice didn't match the roll (need {need_feat} Feat and {want} Success "
                            "dice). Call request_roll again.")
        note = ""
        if hope and h and int(vault.get_path(vault.read_note(h)[0], "hope.current") or 0) < 1:
            hope, note = False, " (no Hope left, rolled without it)"
        try:   # roll (or check the player's dice) before any Hope is taken off the sheet
            r = dice.test(rating, tn, hope=hope, feat=ans.get("feat"), success=ans.get("success"), **kw)
        except ValueError as e:
            await hub.emit({"t": "roll_cancelled", "id": ans.get("_id")})
            return _err(f"bad dice from the player: {e}. Nothing was rolled and no Hope spent; call request_roll again.")
        if hope and h:
            with fileio.locked():
                fm, body = vault.read_note(h)
                cur = int(vault.get_path(fm, "hope.current") or 0)
                vault.set_path(fm, "hope.current", max(0, cur - 1))
                vault.write_note(h, fm, body)
            note = f" Player spent 1 Hope: hero Hope is now {max(0, cur - 1)} (sheet updated)."
        text = dice.describe(r)
        ops.log_roll("test", f"{a['who']}: {a['what']}", text)
        await hub.emit({"t": "roll_result", "id": ans.get("_id"), "who": a["who"], "what": a["what"],
                        "tn": tn, "feat": [_face(f) for f in r.feat_rolled], "kept": _face(r.feat),
                        "success": r.success, "total": r.total, "outcome": r.outcome, "degree": r.degree,
                        "icons": r.icons, "hope": hope, "manual": ans.get("feat") is not None,
                        "notes": r.notes})
        if hope:
            await push_sheet()
        turn["story_since_roll"] = False
        turn["last_roll"] = (a.get("who"), str(a.get("what", "")).lower())
        return _text(text + note)

    @tool("journey",
          "Track a journey on the table's Journey panel; it also writes the journey note for you. action 'start' "
          "when the Company sets out (after plan_journey): from, to, optional via, title, season, mode (on foot, "
          "riding…). action 'log' for each moment of the road, in order: kind march (a marching test and what it "
          "led to), event (a journey event), interlude (a played-out moment with no event: the evening's camp, a "
          "talk on the road, a view, a memory), rest, or other; title (a few words: 'Chance meeting: a lone "
          "hunter'), text (one or two sentences of what happened, as the player saw it), at (the place, if any), "
          "who (the hero, the Band, an Ally), outcome, hexes_done (hexes covered so far, when it changes), "
          "fatigue_hero (added to the sheet by this tool) and fatigue_band. action 'end' on arrival (status "
          "arrived) or turning back (abandoned), with outcome. 'show': where it stands. The player sees all of it: "
          "never land types.",
          {"type": "object",
           "properties": {"action": {"type": "string", "enum": ["start", "log", "show", "end"]},
                          "from": {"type": "string"}, "to": {"type": "string"},
                          "via": {"type": "array", "items": {"type": "string"}}, "title": {"type": "string"},
                          "season": {"type": "string"}, "mode": {"type": "string"},
                          "kind": {"type": "string", "enum": ["march", "event", "interlude", "rest", "other"]},
                          "text": {"type": "string"}, "at": {"type": "string"}, "who": {"type": "string"},
                          "outcome": {"type": "string"}, "hexes_done": {"type": "integer"},
                          "fatigue_hero": {"type": "integer"}, "fatigue_band": {"type": "integer"},
                          "status": {"type": "string", "enum": ["arrived", "abandoned"]}},
           "required": ["action"]})
    async def journey(a: dict) -> dict:
        from . import journey as jr
        try:
            if a["action"] == "start":
                try:      # the planned route gives the hexes and which of them are road (never the land types)
                    plan = await asyncio.to_thread(geo.journey_plan, a.get("from", ""), a.get("to", ""),
                                                   list(a.get("via") or []))
                except geo.GeoError:
                    plan = None
                state = jr.start(a.get("from", ""), a.get("to", ""), a.get("title") or "", a.get("season") or "",
                                 a.get("mode") or "", list(a.get("via") or []), plan=plan)
            elif a["action"] == "show":
                state = jr.load()
                if not state:
                    return _text("no journey in progress")
            elif a["action"] == "log":
                state, e = jr.log(a)
                await hub.emit({"t": "journey_mark", "id": e["id"], "kind": e["kind"], "day": e["day"],
                                "title": e["title"] or e["kind"].capitalize(), "at": e["at"]})
            else:
                done = jr.end(a.get("outcome") or "", a.get("status") or "arrived")
                await hub.emit({"t": "journey", "journey": None})
                await hub.emit({"t": "journey_end", "title": done["title"], "status": done["status"],
                                "outcome": done.get("outcome", ""), "days": max(1, done["end_day"] - done["start_day"] + 1),
                                "fatigue": done["fatigue"]})
                await push_sheet()
                return _text(f"journey over: {done['title']} ({done['status']}). The journey note is complete.")
        except (jr.JourneyError, ValueError, TypeError) as e:
            return _err(f"journey: {e}")
        await hub.emit({"t": "journey", "journey": jr.public_view(state)})
        if a["action"] == "log" and a.get("fatigue_hero"):
            await push_sheet()
        return _text(jr.summary(state))

    @tool("fight",
          "Track a fight on the table's Fight panel. action 'start' when combat or a Band battle begins: kind "
          "(combat|battle), title, foes [{name, note (its adversary note, for the portrait), count, endurance, "
          "hate or resolve, might, parry, armour, features, weapons (names only), engaged, known, abilities}], "
          "stance (the hero's), and for a battle: battle {resistance, resistance_max (the Resistance it started "
          "with, when the panel opens part-way through), might, objective, objective_resistance, advantages and "
          "complications [{name, effect ('+1d', '−1d'), persistent, text (one line of story for the player: what it "
          "is and why it helps or hinders)}], focus, band_stance, clash}. action 'update' after each round or clash with only what "
          "changed (foes matched by name: endurance, hate, wounded, weary, state fighting|fled|surrendered|slain, "
          "count, down, engaged; round, stance; battle fields; log: one line of what happened). action 'end' "
          "with outcome. known [parry, armour, might] or 'all' once the hero would know them; abilities [{name, "
          "text}] when a foe first uses a Fell Ability. Returns the full state; 'show' gives it in a new "
          "conversation.",
          {"type": "object",
           "properties": {"action": {"type": "string", "enum": ["start", "update", "show", "end"]},
                          "kind": {"type": "string", "enum": ["combat", "battle"]}, "title": {"type": "string"},
                          "foes": {"type": "array", "items": {"type": "object"}}, "battle": {"type": "object"},
                          "round": {"type": "integer"}, "stance": {"type": "string"}, "log": {"type": "string"},
                          "outcome": {"type": "string"}},
           "required": ["action"]})
    async def fight(a: dict) -> dict:
        from . import fight as fg
        try:
            if a["action"] == "start":
                foes = list(a.get("foes") or [])
                for f in foes:                 # a kind the hero has fought before: its numbers are known
                    if f.get("known") is None and _fought_before(f.get("note") or f.get("name", "")):
                        f["known"] = "all"
                state = fg.start(a.get("kind") or "combat", a.get("title") or "", foes, a.get("battle"),
                                 a.get("stance"))
            elif a["action"] == "show":
                state = fg.load()
                if not state:
                    return _text("no fight in progress")
            elif a["action"] == "update":
                state = fg.update(a)
            else:
                done = fg.end(a.get("outcome") or "")
                await hub.emit({"t": "fight", "fight": None})
                await hub.emit({"t": "fight_end", "title": done["title"], "kind": done["kind"],
                                "outcome": done["outcome"]})
                return _text(f"fight over: {done['title']}. {done['outcome']}")
        except (fg.FightError, ValueError, TypeError) as e:
            return _err(f"fight: {e}")
        await hub.emit({"t": "fight", "fight": fg.public_view(state, _portrait)})
        return _text(fg.summary(state))

    @tool("council",
          "Track a council on the table's Council panel. action 'start' when the council begins, before the "
          "introduction roll: title, who [names, or {name, note} for portraits], request (what the hero asks, as "
          "the hero would put it), resistance (the procedure's level), attitude (one or two words: how they "
          "receive the hero). action 'update' with only what changed: rounds (the time limit the introduction "
          "set), used (exchanges spent), add (successes this exchange won) or successes (the running total), "
          "attitude, and log: one line of what was said or happened. action 'end' with outcome. Returns the full "
          "state; 'show' gives it in a new conversation.",
          {"type": "object",
           "properties": {"action": {"type": "string", "enum": ["start", "update", "show", "end"]},
                          "title": {"type": "string"}, "who": {"type": "array", "items": {}},
                          "request": {"type": "string"}, "resistance": {"type": "integer"},
                          "attitude": {"type": "string"}, "rounds": {"type": "integer"},
                          "used": {"type": "integer"}, "add": {"type": "integer"},
                          "successes": {"type": "integer"}, "log": {"type": "string"},
                          "outcome": {"type": "string"}},
           "required": ["action"]})
    async def council(a: dict) -> dict:
        from . import council as cn
        try:
            if a["action"] == "start":
                state = cn.start(a.get("title") or "", a.get("who"), a.get("request") or "", a.get("resistance"),
                                 a.get("attitude"))
            elif a["action"] == "show":
                state = cn.load()
                if not state:
                    return _text(cn.summary(None))
            elif a["action"] == "update":
                state = cn.update(a)
            else:
                done = cn.end(a.get("outcome") or "")
                await hub.emit({"t": "council", "council": None})
                await hub.emit({"t": "council_end", "title": done["title"], "outcome": done["outcome"]})
                return _text(f"council over: {done['title']}. {done['outcome']}")
        except (cn.CouncilError, ValueError, TypeError) as e:
            return _err(f"council: {e}")
        await hub.emit({"t": "council", "council": cn.public_view(state, _portrait)})
        return _text(cn.summary(state))

    @tool("fellowship",
          "Track a Fellowship Phase on the table's Fellowship panel; it keeps the phase's progress across sessions. "
          "action 'start' once the player has chosen the duration: duration (hurried, brief, extended or yule), "
          "place (the Safe Haven), undertakings (how many the duration allows). action 'update' with only what "
          "changed: done (a step or list of steps finished: recovery, updates, interruption, undertakings, "
          "close), undo (steps to reopen), chosen (one undertaking taken, as a short name), undertakings (the "
          "new number allowed, e.g. after an interruption costs one), interruption (one line of what befell the "
          "Band), log (one line). 'show': what is done and what comes next. action 'end' with outcome, after the "
          "close step. Experience is spent on the hero note's xp (note_set).",
          {"type": "object",
           "properties": {"action": {"type": "string", "enum": ["start", "update", "show", "end"]},
                          "duration": {"type": "string"}, "place": {"type": "string"},
                          "undertakings": {"type": "integer"}, "done": {}, "undo": {},
                          "chosen": {"type": "string"}, "interruption": {"type": "string"},
                          "log": {"type": "string"}, "outcome": {"type": "string"}},
           "required": ["action"]})
    async def fellowship(a: dict) -> dict:
        from . import fellowship as fs
        try:
            if a["action"] == "start":
                state = fs.start(a.get("duration") or "", a.get("place") or "", a.get("undertakings"))
            elif a["action"] == "update":
                state = fs.update(a)
            elif a["action"] == "show":
                state = fs.load()
                if not state:
                    return _text(fs.summary(None))
            else:
                done = fs.end(a.get("outcome") or "")
                await hub.emit({"t": "fellowship", "fellowship": None})
                await hub.emit({"t": "fellowship_end", **done})
                return _text(f"fellowship phase over. {done['outcome']}")
        except (fs.FellowshipError, ValueError, TypeError) as e:
            return _err(f"fellowship: {e}")
        await hub.emit({"t": "fellowship", "fellowship": fs.public_view(state, _hero_xp())})
        return _text(fs.summary(state))

    @tool("roll_adversary",
          "Roll an adversary's test (attack etc.) with the Shadow's reading of the Feat die. Shown in the tray.",
          {"type": "object",
           "properties": {"who": {"type": "string"}, "what": {"type": "string"},
                          "rating": {"type": "integer"}, "tn": {"type": "integer"},
                          "favoured": {"type": "boolean"}, "ill_favoured": {"type": "boolean"},
                          "bonus": {"type": "integer"}, "penalty": {"type": "integer"}},
           "required": ["who", "what", "rating", "tn"]})
    async def roll_adversary(a: dict) -> dict:
        r = dice.test(int(a["rating"]), int(a["tn"]), favoured=bool(a.get("favoured")),
                      ill=bool(a.get("ill_favoured")), bonus=int(a.get("bonus") or 0),
                      penalty=int(a.get("penalty") or 0), adversary=True)
        text = dice.describe(r)
        ops.log_roll("adversary", f"{a['who']}: {a['what']}", text)
        await hub.emit({"t": "roll_result", "adversary": True, "who": a["who"], "what": a["what"],
                        "tn": int(a["tn"]), "feat": [_face(f) for f in r.feat_rolled], "kept": _face(r.feat),
                        "success": r.success, "total": r.total, "outcome": r.outcome, "degree": r.degree,
                        "icons": r.icons, "notes": r.notes})
        turn["story_since_roll"] = False
        return _text(text)

    # ------------------------------------------------------------ oracles and tables
    @tool("ask",
          "Ask the Telling table a yes/no question (chance: certain, likely, middling, doubtful, unthinkable).",
          {"type": "object",
           "properties": {"question": {"type": "string"}, "chance": {"type": "string"},
                          "favoured": {"type": "boolean"}, "ill_favoured": {"type": "boolean"},
                          "show_player": {"type": "boolean",
                                          "description": "false to keep a secret question out of the oracle log"}},
           "required": ["question", "chance"]})
    async def ask(a: dict) -> dict:
        from .. import tables as tb
        try:
            chance, face, answer, text = ops.ask(a["chance"], a["question"], favoured=bool(a.get("favoured")),
                                                 ill=bool(a.get("ill_favoured")))
        except (tb.TableError, ValueError) as e:
            return _err(str(e))
        if a.get("show_player", True):
            await hub.emit({"t": "oracle", "kind": "telling", "question": a["question"], "chance": chance,
                            "feat": _face(face), "answer": str(answer)})
        turn["story_since_roll"] = False
        return _text(text + _reading_note(a.get("show_player", True)))

    @tool("roll_table",
          "Roll on a lore table by id (e.g. lore-strider with column Action/Aspect/Focus, strider-journey-events).",
          {"type": "object",
           "properties": {"id": {"type": "string"}, "column": {"type": "string"}, "label": {"type": "string"},
                          "favoured": {"type": "boolean"}, "ill_favoured": {"type": "boolean"},
                          "show_player": {"type": "boolean"}},
           "required": ["id"]})
    async def roll_table(a: dict) -> dict:
        from .. import tables as tb
        try:
            r, text = ops.roll_table(a["id"], favoured=bool(a.get("favoured")), ill=bool(a.get("ill_favoured")),
                                     column=a.get("column"), label=a.get("label"))
        except tb.TableError as e:
            return _err(str(e))
        if a.get("show_player", True):
            await hub.emit({"t": "oracle", "kind": "table", "question": a.get("label") or r.title, "answer": text})
        turn["story_since_roll"] = False
        return _text(text + _reading_note(a.get("show_player", True)))

    def _reading_note(shown: bool) -> str:
        if shown and player_reads_oracles():
            return ("\n\nThe player reads the oracles in this campaign: call oracle_reading with the question, this "
                    "result and your suggested reading before telling anything that follows from it.")
        return ""

    @tool("oracle_reading",
          "Only when the player reads the oracles (settings: play.oracle player): offer your reading of an oracle "
          "result just rolled in the open. Waits for the player, who accepts it or gives their own. Returns the "
          "reading to play by.",
          {"type": "object",
           "properties": {"question": {"type": "string", "description": "the question, as asked"},
                          "result": {"type": "string", "description": "what the oracle gave, e.g. 'Yes, with "
                                                                      "{eye}' or 'Action: Seek, Focus: Ruin'"},
                          "suggestion": {"type": "string", "description": "your reading in one or two "
                                                                          "sentences, in the story's terms"}},
           "required": ["question", "result", "suggestion"]})
    async def oracle_reading(a: dict) -> dict:
        if not player_reads_oracles():
            return _text("You read the oracles in this campaign: go on and tell what came of it.")
        ans = await hub.ask("reading", {"t": "reading_request", "question": a["question"], "result": a["result"],
                                        "suggestion": a["suggestion"]})
        if ans.get("action") == "cancel":
            await hub.emit({"t": "reading_cancelled", "id": ans.get("_id")})
            return _text("The player stopped before giving a reading. Don't play the oracle's answer; wait for "
                         "their word.")
        if ans.get("action") == "talk":         # a question about the oracle before reading it
            await hub.emit({"t": "reading_cancelled", "id": ans.get("_id")})
            turn["owe_reply"] = ans.get("text", "") or "…"
            return _text(f"The player hasn't read the oracle yet; they asked: {ans.get('text', '')!r}. Answer them "
                         "in your reply text (your thinking is hidden), then call oracle_reading again with your "
                         "suggestion.")
        own =ans.get("action") == "own" and str(ans.get("text", "")).strip()
        reading = str(ans["text"]).strip() if own else a["suggestion"]
        await hub.emit({"t": "reading_result", "id": ans.get("_id"), "question": a["question"], "text": reading,
                        "own": bool(own)})
        turn["story_since_roll"] = False
        if own:
            return _text(f"The player's reading: {reading!r}. It replaces yours entirely: play it as the truth of "
                         "the world, and if it leaves something open, fill it in their spirit. Now tell what came of "
                         "it as story.")
        return _text("The player accepted your reading. Now tell what came of it as story.")

    @tool("get_tn", "Target Number for an Attribute score (hero) or Readiness (Band); knows about easy mode.",
          {"attribute": int})
    async def get_tn(a: dict) -> dict:
        return _text(str(cp.hero_tn(int(a["attribute"]), cp.load_settings())))

    # ------------------------------------------------------------ notes
    @tool("note_new",
          "Create a vault note from a template. kind: hero, ally, npc, place, session, mission, journey, item, "
          "adversary. fields: frontmatter values (dotted keys allowed).",
          {"type": "object",
           "properties": {"kind": {"type": "string"}, "name": {"type": "string"},
                          "fields": {"type": "object"}},
           "required": ["kind", "name"]})
    async def note_new(a: dict) -> dict:
        try:
            p = vault.new_note(a["kind"], a["name"], extra=a.get("fields") or {})
        except cp.CampaignError as e:
            return _err(str(e))
        if a["kind"] in ("hero", "ally"):
            await push_sheet()
        if a["kind"] == "session":      # the chronicle tells a new session from one picked up after a break
            await hub.emit({"t": "session_mark", "note": p.name})
        return _text(str(p))

    @tool("note_get", "Read a note's frontmatter (or one dotted key) by name or vault path.",
          {"type": "object", "properties": {"note": {"type": "string"}, "key": {"type": "string"}},
           "required": ["note"]})
    async def note_get(a: dict) -> dict:
        try:
            fm, _ = vault.read_note(vault.resolve_note(a["note"]))
        except cp.CampaignError as e:
            return _err(str(e))
        value = vault.get_path(fm, a["key"]) if a.get("key") else fm
        return _text(json.dumps(value, ensure_ascii=False, indent=2, default=str))

    @tool("note_set",
          "Set frontmatter values on a note: values is an object of dotted keys, e.g. "
          "{\"hope.current\": 7, \"conditions.weary\": true}. Updates the side panels.",
          {"type": "object", "properties": {"note": {"type": "string"}, "values": {"type": "object"}},
           "required": ["note", "values"]})
    async def note_set(a: dict) -> dict:
        try:
            path = vault.resolve_note(a["note"])
        except cp.CampaignError as e:
            return _err(str(e))
        with fileio.locked():
            fm, body = vault.read_note(path)
            for k, v in (a.get("values") or {}).items():
                vault.set_path(fm, k, v)
            vault.write_note(path, fm, body)
        await push_sheet()
        return _text(f"updated {path.name}: {json.dumps(a.get('values'), ensure_ascii=False)}")

    # ------------------------------------------------------------ time
    @tool("advance_time",
          "Move the tale on by whole days and/or set the time of day. Deadlines count down from this; "
          "the result warns about any deadline reached. Use days=0 to change only the time of day.",
          {"type": "object",
           "properties": {"days": {"type": "integer"},
                          "time_of_day": {"type": "string", "description": "e.g. dawn, morning, midday, dusk, night"}},
           "required": ["days"]})
    async def advance_time(a: dict) -> dict:
        day, warnings = clock.advance(int(a.get("days") or 0), a.get("time_of_day"))
        await push_sheet()
        fm = clock.state()[1]
        reminder = (f"The stage still shows '{current_scene()}'. If the place, the time of day or the danger "
                    "has changed, call set_scene for the new moment.")
        return _text("\n".join([f"day {day}" + (f", {fm.get('time')}" if fm.get("time") else ""), *warnings,
                                 *clock.describe(fm), reminder]))

    @tool("deadline",
          "Track a deadline the hero knows about; it counts down in the World panel. action add (with "
          "in_days from today, or due = day number) or done (met, missed or no longer relevant). "
          "Secret clocks belong in fronts.md, not here.",
          {"type": "object",
           "properties": {"action": {"type": "string", "enum": ["add", "done"]}, "name": {"type": "string"},
                          "in_days": {"type": "integer"}, "due": {"type": "integer"},
                          "note": {"type": "string", "description": "a few words, e.g. 'new moon, the milestone'"}},
           "required": ["action", "name"]})
    async def deadline(a: dict) -> dict:
        try:
            if a["action"] == "add":
                e = clock.add_deadline(a["name"], in_days=a.get("in_days"), due=a.get("due"), note=a.get("note") or "")
                msg = f"deadline {e['name']}: day {e['due']}"
            else:
                gone = clock.remove("deadlines", a["name"])
                msg = f"removed {gone['name']}" if gone else f"no deadline named {a['name']!r}"
        except ValueError as e:
            return _err(str(e))
        await push_sheet()
        return _text(msg)

    @tool("counter",
          "Track a count-up the hero cares about (e.g. 'Herb missing'); the panel shows 'day N'. "
          "action add (since = start day, default today) or done.",
          {"type": "object",
           "properties": {"action": {"type": "string", "enum": ["add", "done"]}, "name": {"type": "string"},
                          "since": {"type": "integer"}},
           "required": ["action", "name"]})
    async def counter(a: dict) -> dict:
        if a["action"] == "add":
            e = clock.add_counter(a["name"], since=a.get("since"))
            msg = f"counter {e['name']}: since day {e['since']}"
        else:
            try:
                gone = clock.remove("counters", a["name"])
            except ValueError as e:
                return _err(str(e))
            msg = f"removed {gone['name']}" if gone else f"no counter named {a['name']!r}"
        await push_sheet()
        return _text(msg)

    # ------------------------------------------------------------ maps and movement
    async def push_geo(show: bool = False) -> None:
        await hub.emit({"t": "geo", "show": show})

    @tool("move",
          "Record that people go somewhere: who (names; the hero and Allies by their note names), to (a "
          "place), optional via (places on the way), mode (on foot, riding, with the wain, night march...). "
          "Updates where everyone is, the place states and the travel log on the map; the way follows roads, "
          "and a real journey (not a step across the same village or town) shows a small map of it in the tale "
          "by itself. Call it whenever "
          "anyone changes place, including Allies sent off on errands. Add unknown places first with place.",
          {"type": "object",
           "properties": {"who": {"type": "array", "items": {"type": "string"}}, "to": {"type": "string"},
                          "from": {"type": "string"}, "via": {"type": "array", "items": {"type": "string"}},
                          "mode": {"type": "string"}, "note": {"type": "string"}},
           "required": ["who", "to"]})
    async def move(a: dict) -> dict:
        try:
            leg = geo.move(list(a["who"]), a["to"], frm=a.get("from"), via=a.get("via") or [],
                           mode=a.get("mode") or "on foot", note=a.get("note") or "", hero=vault.hero_name())
        except geo.GeoError as e:
            return _err(str(e))
        await push_geo()
        shown = ""
        if leg and geo.is_notable(leg):          # a real journey gets a little map in the tale
            try:
                f = await asyncio.to_thread(geo.move_picture, leg)
                rel = f.relative_to(cp.campaign_dir() / "90 Assets").as_posix()
                await hub.emit({"t": "image", "preset": "map", "job": f"move-{leg['id']}", "url": f"/assets/{rel}",
                                "subject": f"{geo.who_text(leg['who'])}, {leg['from']} to {leg['to']}",
                                "day": leg["day"]})
                shown = " A map of the way is shown in the tale."
            except Exception as e:  # noqa: BLE001 - the move stands even if the picture fails
                shown = f" (No map picture: {e}.)"
        return _text(f"day {leg['day']}: {', '.join(leg['who'])} to {leg['to']} (map {leg['map']}).{shown}")

    @tool("place",
          "Add a place to the campaign map, or move one: near (a known place) + bearing (N, NE, ESE…) + "
          "miles; state heard (the hero has only heard of it), visited, or current. Places inside Bree "
          "or another town sit a fraction of a mile from it.",
          {"type": "object",
           "properties": {"name": {"type": "string"}, "near": {"type": "string"}, "bearing": {"type": "string"},
                          "miles": {"type": "number"},
                          "state": {"type": "string", "enum": ["heard", "visited", "current"]},
                          "note": {"type": "string"}},
           "required": ["name", "near", "bearing", "miles"]})
    async def place(a: dict) -> dict:
        try:
            e = geo.add_place(a["name"], near=a["near"], bearing=a["bearing"], miles=float(a["miles"]),
                              state=a.get("state") or "heard", note=a.get("note") or "")
        except geo.GeoError as e:
            return _err(str(e))
        await push_geo()
        return _text(f"{e['name']} placed on {e['map']}")

    @tool("plan_journey",
          "Plan a journey: across Eriador on its hex map, elsewhere on the map that holds it (20 miles a hex): "
          "hexes to enter (the destination counts, the departure "
          "doesn't), miles, which hexes are on a road (events there gain (1d)), and the land types along the way (Loremaster knowledge: use them for events "
          "and fatigue; never tell the player the land types). Draws the planned route on the player's map "
          "and switches the stage to it. Optional via: places to pass through. clear: true removes the plan.",
          {"type": "object",
           "properties": {"from": {"type": "string"}, "to": {"type": "string"},
                          "via": {"type": "array", "items": {"type": "string"}}, "clear": {"type": "boolean"}},
           "required": []})
    async def plan_journey(a: dict) -> dict:
        if a.get("clear"):
            geo.set_plan(None)
            await push_geo()
            return _text("plan cleared")
        if not a.get("from") or not a.get("to"):
            return _err("give from and to")
        try:
            plan = geo.journey_plan(a["from"], a["to"], via=a.get("via") or [])
        except geo.GeoError as e:
            return _err(str(e))
        geo.set_plan(plan)
        await push_geo(show=True)
        lands = ", ".join(f"{n} {t}" for t, n in plan["lands"].items())
        road = (f" {plan['road_hexes']} of the hexes are on a road: a journey event there gains (1d)."
                if plan["road_hexes"] else " No road on this route.")
        return _text(f"{plan['from']} to {plan['to']}: {plan['hexes']} hexes ({plan['miles']} miles). "
                     f"Lands entered (Loremaster only): {lands}. In order: {geo.route_in_order(plan)}.{road}")

    @tool("region_map",
          "Lay out and draw a region map when the tale reaches country with no close map: a stretch about "
          "15-40 miles across around a known anchor place, in miles from it (x east, y south). For a tale beyond "
          "the Eriador map (Dunland, Rohan, Wilderland, Lorien...) first draw a LAND map: parent 'none', scale "
          "'land', up to a few hundred miles across, anchored on its own first place at [0, 0]; give it land "
          "(border|wild|dark, the default), lands [{type, area}] for other journey lands, and mountains "
          "[{name, area}] (impassable). Keep a land map to the main places (a few hundred miles is coarse: "
          "places within ~5 miles crowd each other); put close detail on region maps nested in it (parent: "
          "its id, anchored on one of its places). "
          "Places {name, at, kind: town|village|hamlet|ruin|tower|stone}; roads {name, points, width: "
          "main|lane}; rivers and streams {name, points}; forests, marshes, downs, lakes {name, area, "
          "label_at; forests kind mixed|conifer|deciduous}; hills {name, center, radius: [rx, ry]}; copses "
          "[[x, y]]; pointers {text, at, side: west|east|north|south} at the edges for roads leaving the "
          "map. Keep it true to Tolkien's maps. Only what the hero can see or would know: "
          "names are drawn into the picture. Places in it can then be used with place and move.",
          {"type": "object",
           "properties": {"title": {"type": "string"}, "anchor": {"type": "string"},
                          "parent": {"type": "string"}, "scale": {"type": "string", "enum": ["local", "land"]},
                          "land": {"type": "string", "enum": ["border", "wild", "dark"]},
                          **{k: {"type": "array"} for k in ("places", "roads", "rivers", "streams", "forests",
                                                             "marshes", "downs", "lakes", "hills", "copses",
                                                             "pointers", "mountains", "lands")}},
           "required": ["title", "anchor", "places"]})
    async def region_map(a: dict) -> dict:
        from .. import regions
        try:
            g = regions.create(dict(a))
        except (regions.RegionError, geo.GeoError, KeyError, TypeError, ValueError) as e:
            return _err(f"region not drawn: {e}")
        await push_geo(show=True)
        w = g["bounds"][2] - g["bounds"][0]
        h = g["bounds"][3] - g["bounds"][1]
        kind = "land map" if g.get("scale") == "land" else "region"
        inside = f"inside '{g['parent']}'" if g.get("parent") else "standing on its own"
        crowded = [p["name"] for p in g["places"]
                   if any(q is not p and abs(q["at"][0] - p["at"][0]) * g["px_per_mile"] < 60
                          and abs(q["at"][1] - p["at"][1]) * g["px_per_mile"] < 30 for q in g["places"])]
        hint = (f" Places drawn close together at this scale: {', '.join(crowded)}. Consider keeping only the "
                f"main one here and drawing a region map of that area inside this one (parent: '{g['id']}')."
                if crowded else "")
        return _text(f"{kind} '{g['title']}' (id '{g['id']}', {inside}) drawn ({w:.0f} x {h:.0f} miles) and "
                     f"shown on the stage. To nest a region in it, give parent: '{g['id']}' and anchor it on one "
                     f"of its places: {', '.join(p['name'] for p in g['places'])}.{hint}")

    @tool("site_plan",
          "Create or replace a site plan (building, ruin, camp, cave) drawn as an ink floor plan, shown only "
          "as far as explored. place: the campaign place it belongs to (add it with place first). Rooms on a "
          "5-foot grid: {id, name, level, x, y, w, h, explored, features: [{kind, at: [x, y], label}]}; "
          "feature kinds: chest, desk, table, bed, hearth, stair, barrel, well, altar, statue, pillar, crate. "
          "Doors: {rooms: [a, b], at: [x, y] on the shared wall line, kind: door|outside, label}. Rooms are "
          "then places called '<title>: <room name>' for move.",
          {"type": "object",
           "properties": {"title": {"type": "string"}, "place": {"type": "string"},
                          "levels": {"type": "array", "items": {"type": "string"}},
                          "rooms": {"type": "array", "items": {"type": "object"}},
                          "doors": {"type": "array", "items": {"type": "object"}}},
           "required": ["title", "place", "rooms"]})
    async def site_plan(a: dict) -> dict:
        from .. import sites
        try:
            site = sites.validate({k: a[k] for k in ("title", "place", "levels", "rooms", "doors") if k in a})
            sites.save(site)
            sites.render_to_vault(site)
        except (sites.SiteError, KeyError, TypeError) as e:
            return _err(f"site plan not saved: {e}")
        await push_geo()
        rooms = ", ".join(f"{r['name']}{'' if r['explored'] else ' (unexplored)'}" for r in site["rooms"])
        return _text(f"site '{site['title']}' saved ({site['id']}): {rooms}")

    @tool("site_explore", "Reveal rooms of a site plan once the hero has seen them (room ids).",
          {"type": "object", "properties": {"site": {"type": "string"},
                                            "rooms": {"type": "array", "items": {"type": "string"}}},
           "required": ["site", "rooms"]})
    async def site_explore(a: dict) -> dict:
        from .. import sites
        try:
            site = sites.explore(sites.slug_of(a["site"]), list(a["rooms"]))
            sites.render_to_vault(site)
        except sites.SiteError as e:
            return _err(str(e))
        await push_geo()
        return _text("revealed: " + ", ".join(a["rooms"]))

    @tool("show_map", "Switch the stage to the map (e.g. when planning a journey or when the player asks "
                      "where things are).", {"type": "object", "properties": {}})
    async def show_map(a: dict) -> dict:
        await push_geo(show=True)
        return _text("the map is shown")

    # ------------------------------------------------------------ the table
    @tool("set_scene",
          "Mark a significant change of scene (new place, time jump, major dramatic shift). Shows the title "
          "on the stage and paints a new scene image from the description. Not for small beats.",
          {"type": "object",
           "properties": {"title": {"type": "string", "description": "short, e.g. 'The East Road at dusk'"},
                          "image": {"type": "string",
                                    "description": "what is visible, the main action and any threat FIRST "
                                                   "(e.g. 'Gaunt grey wolves lunge with bared fangs at...'), "
                                                   "then the place, light and weather; characters by their "
                                                   "fixed look; at most 3-4 figures"},
                          "mood": {"type": "string",
                                   "enum": ["calm", "wonder", "tense", "danger", "battle", "dread", "sorrow"],
                                   "description": "sets light and atmosphere; 'battle' for any fight in progress, "
                                                  "'danger' for high stakes such as a break-in or a chase"},
                          "time_of_day": {"type": "string", "enum": ["dawn", "day", "dusk", "night"],
                                          "description": "defaults to the World clock's time of day"},
                          "characters": {"type": "array", "items": {"type": "string"},
                                         "description": "up to 3 named characters clearly visible in the picture "
                                                        "(note names); their portraits keep their faces consistent"},
                          "look": {"type": "string",
                                   "description": "one of the campaign's painting looks, if it has any (see "
                                                  "'Painting looks' in your instructions); leave out for the house "
                                                  "style"},
},
           "required": ["title", "image", "mood"]})
    async def set_scene(a: dict) -> dict:
        s = cp.load_settings()
        job = None
        if s["art"]["enabled"]:
            when = a.get("time_of_day") or art.time_from_text(clock.state()[1].get("time"))
            try:
                job = artqueue.enqueue("scene", a["image"], name=a["title"], priority=1, mood=a.get("mood"),
                                       time=when, characters=a.get("characters") or [], look=a.get("look"))
            except art.ArtError as e:
                return _err(f"{e}. Nothing was changed; call set_scene again.")
        fileio.atomic_write(cp.private_dir() / "table-scene.json", json.dumps({"title": a["title"]}))
        await hub.emit({"t": "scene", "title": a["title"], "job": job["id"] if job else None})
        done = "scene set" + (", painting queued" if job else " (art is off)")
        if turn.get("told") or turn.get("pending_story"):
            return _text(done + ". If the closing question is already written, your turn is over: write nothing "
                         "more (no recap, no repeated question).")
        return _text(done + ". Now tell the scene as story: what the hero sees and hears, what happens and who "
                     "says what, in prose. Then the short mechanics summary and the question.")

    @tool("queue_art",
          "Queue an illustration (preset: portrait, scenery, adversary, item, scene) and attach it to a note. "
          "Put the subject's fixed look in the note first and reuse it.",
          {"type": "object",
           "properties": {"preset": {"type": "string"}, "subject": {"type": "string"},
                          "note": {"type": "string"}, "name": {"type": "string"},
                          "mood": {"type": "string",
                                   "enum": ["calm", "wonder", "tense", "danger", "battle", "dread", "sorrow"]},
                          "time_of_day": {"type": "string", "enum": ["dawn", "day", "dusk", "night"]},
                          "characters": {"type": "array", "items": {"type": "string"},
                                         "description": "named characters in the picture whose portraits exist"},
                          "look": {"type": "string",
                                   "description": "one of the campaign's painting looks, if it has any (see "
                                                  "'Painting looks' in your instructions); leave out for the house "
                                                  "style"},
},
           "required": ["preset", "subject"]})
    async def queue_art(a: dict) -> dict:
        if not cp.load_settings()["art"]["enabled"]:
            return _text("art is off in the campaign settings; nothing queued")
        try:
            job = artqueue.enqueue(a["preset"], a["subject"], note=a.get("note"), name=a.get("name"),
                                   mood=a.get("mood"), time=a.get("time_of_day"), characters=a.get("characters") or [],
                                   look=a.get("look"))
        except Exception as e:  # noqa: BLE001
            return _err(str(e))
        return _text(f"queued {job['id']}: {job['file']}")

    @tool("sketch",
          "Draw a small pencil sketch into the tale, where it is told, of something the hero hears of but doesn't "
          "see now: a place, person, creature or thing described in a tale, a rumour, a letter, a memory or a "
          "vision. Never for what is happening in front of the hero (set_scene paints that).",
          {"type": "object",
           "properties": {"subject": {"type": "string",
                                      "description": "what to draw, plainly and physically: the thing first, then "
                                                     "its setting; few or no figures"},
                          "caption": {"type": "string", "description": "a few words under the sketch, e.g. "
                                                                       "'The tower on Amon Sûl, as Bob told it'"}},
           "required": ["subject", "caption"]})
    async def sketch(a: dict) -> dict:
        if not cp.load_settings()["art"]["enabled"]:
            return _text("art is off in the campaign settings; no sketch")
        try:
            job = artqueue.enqueue("sketch", a["subject"], name=a["caption"], priority=2)
        except Exception as e:  # noqa: BLE001
            return _err(str(e))
        await hub.emit({"t": "sketch", "job": job["id"], "caption": a["caption"]})
        return _text("sketch under way; it appears in the tale here. Go on with the story.")

    @tool("offer_paths",
          "Show 2-4 Paths as clickable cards (the player may also type something else). Don't repeat them in text.",
          {"type": "object",
           "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
           "required": ["paths"]})
    async def offer_paths(a: dict) -> dict:
        paths = a["paths"]
        if isinstance(paths, str):                 # sometimes sent as a JSON string
            try:
                paths = json.loads(paths)
            except ValueError:
                paths = [paths]
        paths = [str(p) for p in paths][:5]
        if not cp.load_settings()["play"]["paths"] and not turn.get("asked_paths"):
            return _text("Not shown: Path cards are off in this campaign, so the player makes their own choices. "
                         "Don't list the options in your text either. If the closing question is written, your "
                         "turn is over.")
        if not await outcome_told():
            # Keep the cards; the engine shows them at the end of the turn, once the story is told.
            turn["held_paths"] = paths
            return _text("Not shown yet: the player hasn't been told, as story, what the last roll or oracle led "
                         "to. The cards are kept and will appear by themselves after your story; don't call "
                         "offer_paths again this turn. Write that scene now as the storyteller: prose paragraphs "
                         "of what the hero sees and hears, the speakers' own words, no lists and no talk of rolls "
                         "or oracles. Then the short mechanics summary and the question.")
        turn["held_paths"] = None
        await hub.emit({"t": "paths", "paths": paths})
        return _text("Paths are now shown to the player as cards. Your turn is over: write nothing more. "
                     "No recap, no summary, no prompt to pick a card; the table hides any text after this.")

    tools = [request_roll, fight, council, fellowship, journey, roll_adversary, ask, roll_table, get_tn, note_new, note_get,
             note_set, advance_time, deadline, counter, move, place, plan_journey, region_map, site_plan, site_explore,
             show_map, set_scene, queue_art, sketch, offer_paths, oracle_reading]
    server = create_sdk_mcp_server(name=SERVER, version="1.0.0", tools=tools)
    names = [f"mcp__{SERVER}__{t.name}" for t in tools]
    return server, names
