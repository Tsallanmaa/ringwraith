"""The player steers: reading the oracles themselves, Path cards off, and the settings behind them."""

import asyncio

import pytest

pytest.importorskip("claude_agent_sdk")

from ringwraith.web import engine as eng  # noqa: E402
from ringwraith.web import tablesettings as ts  # noqa: E402
from ringwraith.web.hub import Hub  # noqa: E402


def _tools(monkeypatch, play):
    import claude_agent_sdk
    from ringwraith.web import gametools
    tools = {}
    real = claude_agent_sdk.create_sdk_mcp_server

    def grab(name, version, tools_list):
        tools.update({t.name: t for t in tools_list})
        return real(name=name, version=version, tools=tools_list)
    monkeypatch.setattr(gametools, "create_sdk_mcp_server", lambda name, version, tools: grab(name, version, tools))
    monkeypatch.setattr(gametools.cp, "load_settings", lambda *a, **k: {"play": play})
    return gametools, tools


class _Hub:
    """Emits into a list; ask() answers at once with the given answer."""

    def __init__(self, answer=None):
        self.events, self.answer = [], answer

    async def emit(self, e):
        self.events.append(e)

    async def ask(self, kind, event):
        self.events.append({**event, "id": "r1"})
        return {**self.answer, "_id": "r1"}


def _text(r):
    return r["content"][0]["text"]


def test_the_player_can_accept_ringwraiths_reading(monkeypatch):
    gt, tools = _tools(monkeypatch, {"oracle": "player", "paths": True})
    hub = _Hub({"action": "accept"})
    gt.build(hub, {})
    r = asyncio.run(tools["oracle_reading"].handler(
        {"question": "Is anyone following?", "result": "Yes", "suggestion": "Orcs, a mile back."}))
    assert hub.events[0]["t"] == "reading_request"
    assert hub.events[-1] == {"t": "reading_result", "id": "r1", "question": "Is anyone following?",
                              "text": "Orcs, a mile back.", "own": False}
    assert "accepted" in _text(r)


def test_the_players_own_reading_replaces_ringwraiths(monkeypatch):
    gt, tools = _tools(monkeypatch, {"oracle": "player", "paths": True})
    hub = _Hub({"action": "own", "text": "Bryni's cousin, come to warn us"})
    gt.build(hub, {})
    r = asyncio.run(tools["oracle_reading"].handler(
        {"question": "Is anyone following?", "result": "Yes", "suggestion": "Orcs, a mile back."}))
    assert hub.events[-1]["text"] == "Bryni's cousin, come to warn us" and hub.events[-1]["own"]
    assert "replaces yours" in _text(r) and "Bryni's cousin" in _text(r)


def test_ringwraith_reads_the_oracles_by_default(monkeypatch):
    gt, tools = _tools(monkeypatch, {"oracle": "loremaster", "paths": True})
    hub = _Hub()
    gt.build(hub, {})
    r = asyncio.run(tools["oracle_reading"].handler({"question": "q", "result": "Yes", "suggestion": "s"}))
    assert not hub.events and "You read the oracles" in _text(r)
    assert gt.player_reads_oracles() is False


def test_path_cards_off_show_nothing_unless_the_player_asked(monkeypatch):
    gt, tools = _tools(monkeypatch, {"oracle": "loremaster", "paths": False})
    hub, turn = _Hub(), {"story_since_roll": True}
    gt.build(hub, turn)
    r = asyncio.run(tools["offer_paths"].handler({"paths": ["Go left", "Go right"]}))
    assert not hub.events and "Path cards are off" in _text(r)
    turn["asked_paths"] = True                                 # the player typed /paths
    asyncio.run(tools["offer_paths"].handler({"paths": ["Go left", "Go right"]}))
    assert hub.events == [{"t": "paths", "paths": ["Go left", "Go right"]}]


def test_typing_while_a_reading_waits_gives_the_players_own_reading(tmp_path):
    async def run():
        hub = Hub(tmp_path / "log.jsonl")
        e = eng.Engine.__new__(eng.Engine)
        e.hub = hub
        task = asyncio.create_task(hub.ask("reading", {"t": "reading_request", "question": "q"}))
        await asyncio.sleep(0)
        await e.say("It was the wind, nothing more")
        ans = await task
        assert ans["action"] == "own" and ans["text"] == "It was the wind, nothing more"
        await hub.emit({"t": "reading_request", "id": "old", "question": "q"})   # from a run that ended
        assert hub.replay()[-1].get("stale")
    asyncio.run(run())


def test_the_settings_dialog_offers_both_switches(monkeypatch):
    s = {"play": {"oracle": "loremaster", "paths": True}}
    monkeypatch.setattr(ts.cp, "load_settings", lambda *a, **k: s)
    saved = {}
    monkeypatch.setattr(ts.cp, "set_value", lambda k, v: saved.update({k: v}))
    fields = {f["key"]: f for f in ts.view()["fields"]}
    assert fields["play.oracle"]["value"] == "loremaster" and fields["play.paths"]["value"] is True
    ts.apply({"play.oracle": "player", "play.paths": False})
    assert saved == {"play.oracle": "player", "play.paths": False}
    with pytest.raises(ts.SettingsError):
        ts.apply({"play.oracle": "nobody"})


def test_stop_or_a_command_closes_a_waiting_reading(tmp_path, monkeypatch):
    gt, tools = _tools(monkeypatch, {"oracle": "player", "paths": True})

    async def run():
        hub = Hub(tmp_path / "log.jsonl")
        gt.build(hub, {})
        e = eng.Engine.__new__(eng.Engine)
        e.hub, e.queue = hub, asyncio.Queue()
        e._table_note = lambda: ""
        task = asyncio.create_task(tools["oracle_reading"].handler(
            {"question": "Is anyone following?", "result": "Yes", "suggestion": "Orcs."}))
        await asyncio.sleep(0.01)
        await e.say("/steer toward Angmar")                  # a command is never the player's reading
        r = await task
        assert "stopped before giving a reading" in r["content"][0]["text"]
        assert await e.queue.get() == "/steer toward Angmar"
        assert hub.replay()[-1]["t"] == "reading_cancelled"
    asyncio.run(run())


def test_a_cancelled_ask_closes_its_tray_on_the_page(tmp_path):
    async def run():
        hub = Hub(tmp_path / "log.jsonl")
        task = asyncio.create_task(hub.ask("reading", {"t": "reading_request", "question": "q"}))
        await asyncio.sleep(0.01)
        task.cancel()                                        # the CLI dropped the tool call
        await asyncio.sleep(0.01)
        assert [ev["t"] for ev in hub.replay()] == ["reading_request", "reading_cancelled"]
        assert not hub.replay()[0].get("stale")
    asyncio.run(run())


def test_a_reading_shows_once_and_a_question_goes_to_ringwraith(tmp_path, monkeypatch):
    gt, tools = _tools(monkeypatch, {"oracle": "player", "paths": True})

    async def run():
        hub = Hub(tmp_path / "log.jsonl")
        turn = {}
        gt.build(hub, turn)
        e = eng.Engine.__new__(eng.Engine)
        e.hub, e.queue = hub, asyncio.Queue()
        call = {"question": "Is anyone following?", "result": "Yes", "suggestion": "Orcs."}
        task = asyncio.create_task(tools["oracle_reading"].handler(call))
        await asyncio.sleep(0.01)
        await e.say("What does Yes with an Eye mean here?", ask=True)
        r = await task
        assert "they asked" in r["content"][0]["text"] and turn["owe_reply"]
        task = asyncio.create_task(tools["oracle_reading"].handler(call))
        await asyncio.sleep(0.01)
        await e.say("Only a fox in the bracken")
        await task
        said = [ev for ev in hub.replay() if ev["t"] == "player"]
        assert [ev["text"] for ev in said] == ["What does Yes with an Eye mean here?"]   # the reading: a card only
        assert hub.replay()[-1]["text"] == "Only a fox in the bracken"
    asyncio.run(run())
