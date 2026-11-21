import asyncio
from pathlib import Path

import pytest

pytest.importorskip("claude_agent_sdk")

from ringwraith.web import engine as eng  # noqa: E402
from ringwraith.web.hub import Hub  # noqa: E402


def test_hub_ask_answer_and_replay(tmp_path):
    async def run():
        hub = Hub(tmp_path / "log.jsonl")
        task = asyncio.create_task(hub.ask("roll", {"t": "roll_request", "who": "x"}))
        await asyncio.sleep(0)
        (iid,) = hub.pending_of("roll")
        assert hub.answer(iid, {"action": "hope"})
        ans = await task
        assert ans == {"action": "hope", "_id": iid}
        await hub.emit({"t": "text_delta", "text": "not logged"})
        # an unanswered request from an earlier run is marked stale on replay
        await hub.emit({"t": "roll_request", "id": "old"})
        events = hub.replay()
        assert [e["t"] for e in events] == ["roll_request", "roll_request"]
        assert events[-1].get("stale")
    asyncio.run(run())


def test_permission_policy(tmp_path, monkeypatch):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    monkeypatch.setattr(eng.cp, "campaign_dir", lambda *a, **k: vault_dir)
    e = eng.Engine.__new__(eng.Engine)
    e.tool_names = ["mcp__rw__request_roll"]

    def decide(name, inp):
        r = asyncio.run(e._permit(name, inp, None))
        return type(r).__name__.endswith("Allow")

    assert decide("mcp__rw__request_roll", {})
    assert decide("Read", {"file_path": "anything"})
    assert decide("Edit", {"file_path": str(vault_dir / "note.md")})
    assert not decide("Edit", {"file_path": str(Path(__file__))})
    assert decide("Bash", {"command": ".venv/Scripts/ringwraith status"})
    assert not decide("Bash", {"command": ".venv/Scripts/ringwraith roll 3 --tn 14"})
    assert not decide("Bash", {"command": ".venv/Scripts/ringwraith status; rm -rf x"})
    assert not decide("Bash", {"command": "curl example.com"})
    assert not decide("WebFetch", {"url": "https://example.com"})


def test_art_moods_replace_the_calm_default():
    from ringwraith import art
    calm = art.build_prompt("scene", "a road")
    fight = art.build_prompt("scene", "wolves attack", "battle")
    assert "hopeful" in calm and "hopeful" not in fight and "bared fangs" in fight
    assert "menace" in art.build_prompt("adversary", "an Orc")   # adversaries default to danger
    with pytest.raises(art.ArtError):
        art.build_prompt("scene", "x", "jolly")


def test_bookkeeping_asides_are_not_story():
    from ringwraith.web.narration import is_aside
    assert is_aside("Writing up Fitch and Cob, then the scene at the Forester's house.", "note_new")
    assert is_aside("Let me check the hero sheet.", "Read")
    assert not is_aside("The fire dies to embers.", "note_set")
    assert not is_aside("Tomas peers into the dark.", "request_roll")
    assert not is_aside('"Hold," says Sid.', "Edit")
    assert not is_aside("> OOC: Hope is now 3.", "note_set")
    assert is_aside("Still sorting the journey's chance meeting; the story follows.", "note_new")
    assert is_aside("Still sorting the journey's chance meeting; the story follows.", None)
    assert not is_aside("Still the rain comes on, and the story of the road follows the river.", None)


def _run_turn(blocks):
    """Feed assistant blocks through the engine's handler; return the narration events emitted."""
    from claude_agent_sdk import AssistantMessage

    class StubHub:
        def __init__(self):
            self.events = []

        async def emit(self, e):
            self.events.append(e)

    e = eng.Engine.__new__(eng.Engine)
    e.hub, e._held, e._paths_shown, e._asked = StubHub(), None, False, False
    e.turn = {"story_since_roll": True}

    async def go():
        for b in blocks:
            await e._handle(AssistantMessage(content=[b], model="m"))
        await e._flush()
    asyncio.run(go())
    return [ev for ev in e.hub.events if ev["t"] == "narration"]


def test_recap_after_paths_is_folded_only_when_the_outcome_was_told():
    from claude_agent_sdk.types import TextBlock, ToolUseBlock as T
    roll = T("1", "mcp__rw__request_roll", {})
    paths = T("2", "mcp__rw__offer_paths", {})
    # outcome told as story before the Paths: the later recap is folded
    told = _run_turn([TextBlock("You watch."), roll, TextBlock("The cobbler slips away to tell Mungo."),
                      paths, TextBlock("Recap: the roll failed.")])
    assert told[-1].get("recap")
    # outcome never told before the Paths (the warden at the pump): the text stays visible
    untold = _run_turn([TextBlock("You watch."), roll, paths, TextBlock("A warden now leans on the pump.")])
    assert not untold[-1].get("recap")


def test_a_new_roll_waits_until_the_last_one_is_told(monkeypatch):
    """Rolling again before the previous outcome is narrated is refused (no tray is shown)."""
    import claude_agent_sdk
    from ringwraith.web import gametools

    captured = {}
    real = claude_agent_sdk.create_sdk_mcp_server

    def grab(name, version, tools):
        captured.update({t.name: t for t in tools})
        return real(name=name, version=version, tools=tools)
    monkeypatch.setattr(gametools, "create_sdk_mcp_server", grab)

    class Hub:
        async def ask(self, kind, event):
            raise AssertionError("the player must not be asked")

    turn = {"story_since_roll": False}
    gametools.build(Hub(), turn)
    args = {"who": "Tomas", "what": "Scan", "dice": 2, "tn": 14, "stakes": "x"}
    r = asyncio.run(captured["request_roll"].handler(args))
    assert r.get("is_error") and "First tell the outcome" in r["content"][0]["text"]


def test_table_refuses_to_start_its_own_art_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(eng.cp, "campaign_dir", lambda *a, **k: tmp_path)
    e = eng.Engine.__new__(eng.Engine)
    e.tool_names = []
    r = asyncio.run(e._permit("Bash", {"command": ".venv/Scripts/ringwraith art worker"}, None))
    assert type(r).__name__.endswith("Deny")
    r = asyncio.run(e._permit("Bash", {"command": ".venv/Scripts/ringwraith art pending"}, None))
    assert type(r).__name__.endswith("Allow")


def test_time_of_day_leads_the_prompt_and_night_is_graded_dark():
    from PIL import Image
    from ringwraith import art
    night = art.build_prompt("scene", "a burglar at a chest", "danger", "night", style="classic")
    assert night.startswith("a nocturne") and "Rembrandt" in night
    book = art.build_prompt("scene", "a burglar at a chest", "danger", "night")       # the default style
    assert book.startswith("a nocturne") and "teal" in book and "Rembrandt" not in book
    assert not art.build_prompt("scene", "a road", "calm", "day").startswith("in daylight")
    assert art.time_from_text("late at night") == "night" and art.time_from_text("nightfall") == "dusk"
    assert art.time_from_text("midday") == "day" and art.time_from_text(None) is None
    grey = Image.new("RGB", (64, 32), (128, 128, 128))
    assert sum(art.grade(grey, "night").getpixel((32, 16))) < sum(grey.getpixel((32, 16)))
    assert art.grade(grey, "day") is grey


def test_paths_wait_until_the_outcome_is_told(monkeypatch):
    import claude_agent_sdk
    from ringwraith.web import gametools

    tools = {}
    real = claude_agent_sdk.create_sdk_mcp_server
    def grab(name, version, tools_list):
        tools.update({t.name: t for t in tools_list})
        return real(name=name, version=version, tools=tools_list)
    monkeypatch.setattr(gametools, "create_sdk_mcp_server",
                        lambda name, version, tools: grab(name, version, tools))

    class Hub:
        def __init__(self):
            self.events = []

        async def emit(self, e):
            self.events.append(e)

    hub, turn = Hub(), {"story_since_roll": False}
    gametools.build(hub, turn)
    paths = {"paths": ["Go left", "Go right"]}
    r = asyncio.run(tools["offer_paths"].handler(paths))
    assert not hub.events and turn["held_paths"] == ["Go left", "Go right"]   # untold: kept, not shown
    assert "don't call offer_paths again" in r["content"][0]["text"]
    turn["pending_story"] = True                            # the engine holds story text just written
    r = asyncio.run(tools["offer_paths"].handler({"paths": '["Go left", "Go right"]'}))   # a JSON string too
    assert not r.get("is_error") and hub.events[-1] == {"t": "paths", "paths": ["Go left", "Go right"]}
    assert turn["held_paths"] is None


def test_held_paths_appear_once_the_story_is_told():
    class Hub:
        def __init__(self):
            self.events = []

        async def emit(self, e):
            self.events.append(e)

    e = eng.Engine.__new__(eng.Engine)
    e.hub, e._stopping = Hub(), False
    e.turn = {"held_paths": ["Go left"], "story_since_roll": False}
    asyncio.run(e._show_held_paths())
    assert not e.hub.events                                 # still untold: nothing
    e.turn["story_since_roll"] = True
    asyncio.run(e._show_held_paths())
    assert e.hub.events == [{"t": "paths", "paths": ["Go left"]}] and e.turn["held_paths"] is None


def test_mechanics_only_replies_are_spotted():
    from ringwraith.web.narration import is_mechanics_only
    assert is_mechanics_only("Harrow has given Tomas nothing. The INSIGHT roll, Favoured, came to 14 against "
                             "TN 16, a failure.\n\nWhat does Tomas do?")
    assert is_mechanics_only("The roll came up short: 12.\n\nWhat now?")
    assert not is_mechanics_only('Harrow smiles thinly. "You are no judge of men, Bree-lander."\n\n'
                                 "- **INSIGHT:** 14 vs TN 16, failure.\n\nWhat does Tomas do?")
    assert not is_mechanics_only("The stone rolls away down the slope.")


def test_mechanics_drifting_into_the_story_move_to_the_ooc_box():
    from ringwraith.web.narration import tidy_story
    text = ("The mist lifts off the downs. Garth's knuckles are white on his bow.\n\n"
            "Goatleaf turned down your offer. The oracle question was at likely odds, and it came up No.\n\n"
            "\"Then we ride,\" says Sid.\n\n"
            "It's dawn on day 15. Tomas has 24 Endurance and 4 Hope.\n\n"
            "Pick a card, or tell me what Tomas does.")
    out, moved = tidy_story(text)
    assert moved
    assert out == ("The mist lifts off the downs. Garth's knuckles are white on his bow.\n\n"
                   "\"Then we ride,\" says Sid.\n\n"
                   "> OOC:\n> Goatleaf turned down your offer. The oracle question was at likely odds, and it came "
                   "up No.\n>\n> It's dawn on day 15. Tomas has 24 Endurance and 4 Hope.\n\n"
                   "Pick a card, or tell me what Tomas does.")
    # an existing OOC box takes the moved lines; plain story is left alone
    boxed, moved = tidy_story("Story.\n\nMore story.\n\nTomas has 4 Hope.\n\n> OOC:\n> - **Hope** 5 → 4.\n\nWhat now?")
    assert moved and boxed == "Story.\n\nMore story.\n\n> OOC:\n> - **Hope** 5 → 4.\n>\n> Tomas has 4 Hope.\n\nWhat now?"
    story = "They roll the bundle into the hole.\n\nThe rain comes on.\n\nWhat does Tomas do?"
    assert tidy_story(story) == (story, False)


def test_a_mechanics_only_outcome_is_retold_as_story_above_the_summary():
    from claude_agent_sdk import AssistantMessage, ResultMessage
    from claude_agent_sdk.types import TextBlock, ToolUseBlock

    def result():
        return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                             num_turns=1, session_id="")

    summary = "The INSIGHT roll came to 14 against TN 16, a failure.\n\nWhat does Tomas do?"
    story = 'Harrow only smiles. "You read nothing in me, Bree-lander."'

    class Hub:
        busy = False

        def __init__(self):
            self.events = []

        async def emit(self, e):
            self.events.append(e)

        def pending_of(self, kind):
            return []

    class Client:
        def __init__(self, turn):
            self.turn, self.queries = turn, []

        async def query(self, text):
            self.queries.append(text)

        async def receive_response(self):
            if len(self.queries) == 1:
                yield AssistantMessage(content=[ToolUseBlock("1", "mcp__rw__request_roll", {})], model="m")
                self.turn["story_since_roll"] = False      # the roll tool ran
                self.turn["held_paths"] = ["Press him"]    # Paths offered before the story
                yield AssistantMessage(content=[TextBlock(summary)], model="m")
            else:
                yield AssistantMessage(content=[TextBlock(story)], model="m")
            yield result()

    e = eng.Engine.__new__(eng.Engine)
    e.hub, e._held, e._stopping, e.turn = Hub(), None, False, {}
    e.client, e.queue = Client(e.turn), asyncio.Queue()
    e._save_session = lambda sid: None

    async def go():
        await e.queue.put("Let's read him.")
        task = asyncio.create_task(e._run())
        for _ in range(100):
            await asyncio.sleep(0.01)
            if any(ev["t"] == "turn_end" for ev in e.hub.events):
                break
        task.cancel()
    asyncio.run(go())

    assert len(e.client.queries) == 2 and e.client.queries[1] == eng.RETELL
    shown = [(ev["t"], ev.get("text"), ev.get("summary"), ev.get("retell")) for ev in e.hub.events
             if ev["t"] in ("narration", "paths", "turn_end", "text_start")]
    assert shown == [("narration", summary, True, None), ("narration", story, None, None),
                     ("paths", None, None, None), ("turn_end", None, None, None)]
    assert [ev["t"] for ev in e.hub.events].count("turn_end") == 1


def test_the_chronicle_puts_a_retold_story_above_its_summary():
    from ringwraith import chronicle
    md = chronicle.render([
        {"t": "player", "text": "Read him"},
        {"t": "text_start"}, {"t": "narration", "text": "The roll failed.", "summary": True},
        {"t": "text_start", "retell": True}, {"t": "narration", "text": "Harrow smiles."},
        {"t": "turn_end"}])
    assert md.index("Harrow smiles.") < md.index("The roll failed.")


def test_set_scene_before_the_story_asks_for_the_story(monkeypatch, tmp_path):
    import claude_agent_sdk
    from ringwraith.web import gametools

    captured = {}
    real = claude_agent_sdk.create_sdk_mcp_server
    grab_tools = lambda ts: captured.update({t.name: t for t in ts})  # noqa: E731
    monkeypatch.setattr(gametools, "create_sdk_mcp_server",
                        lambda name, version, tools: (grab_tools(tools),
                                                           real(name=name, version=version, tools=tools))[1])
    monkeypatch.setattr(gametools.cp, "load_settings", lambda *a, **k: {"art": {"enabled": False}})
    monkeypatch.setattr(gametools.cp, "private_dir", lambda *a, **k: tmp_path)

    class Hub:
        async def emit(self, e):
            pass

    turn = {"story_since_roll": True, "told": False}
    gametools.build(Hub(), turn)
    args = {"title": "The grave", "image": "a dell", "mood": "danger"}
    text = asyncio.run(captured["set_scene"].handler(args))["content"][0]["text"]
    assert "Now tell the scene as story" in text and "turn is over" not in text
    turn["told"] = True
    text = asyncio.run(captured["set_scene"].handler(args))["content"][0]["text"]
    assert "turn is over" in text


def test_chronicle_renders_scenes_images_rolls_and_skips_asides():
    from ringwraith import chronicle
    ev = [
        {"t": "player", "text": "/session-start"},
        {"t": "scene", "title": "Bree at Dusk", "job": "j1"},
        {"t": "narration", "text": "Rain on the thatch.\n\n> OOC: Hope 3 → 2, used {success}."},
        {"t": "narration", "text": "Writing up notes.", "aside": True},
        {"t": "player", "text": "I knock on the door"},
        {"t": "roll_result", "who": "Tomas", "what": "Courtesy", "tn": 14, "feat": ["gandalf"], "kept": "gandalf",
         "success": [6, 2], "total": 18, "outcome": "success", "degree": "great", "hope": True},
        {"t": "image", "job": "j2", "preset": "portrait", "url": "/assets/portraits/nob.png", "note": "30 World/People/Nob.md"},
        {"t": "image", "job": "j1", "preset": "scene", "url": "/assets/scenes/bree.png"},
        {"t": "narration", "text": "Recap", "recap": True},
        {"t": "player", "text": "/session-start"},
        {"t": "narration", "text": "Next session."},
    ]
    plays = chronicle.sessions(ev)
    assert plays == [(0, 9), (9, 11)]
    md = chronicle.render(ev, *plays[0])
    assert "### Bree at Dusk\n\n![[90 Assets/scenes/bree.png]]" in md
    assert "> [!loremaster]- Loremaster\n> Hope 3 → 2, used ✦." in md
    assert "Writing up notes" not in md and "Recap" not in md and "/session-start" not in md
    assert "> [!player] You\n> I knock on the door" in md
    assert "[!success] Tomas: Courtesy, TN 14: Success (great), total 18" in md and "ᚷ Rune" in md
    assert "![[90 Assets/portraits/nob.png|220]]\n*Nob*" in md
    assert md.count("bree.png") == 1


def test_chronicle_section_is_replaced_not_duplicated(tmp_path):
    from ringwraith import chronicle
    note = tmp_path / "Session 002.md"
    note.write_text("---\ntype: session\n---\n\n# Session 2\n\n## The tale\n\nKeep me.\n\n## As it was played\n\nold\n",
                    encoding="utf-8")
    chronicle.write(note, "new text\n")
    chronicle.write(note, "newer text\n")
    body = note.read_text(encoding="utf-8")
    assert body.count("## As it was played") == 1 and "newer text" in body and "old" not in body
    assert "Keep me." in body


def test_headings_in_narration_cannot_break_the_note():
    from ringwraith import chronicle
    md = chronicle.render([{"t": "narration", "text": "## Previously…\n\nThe tale so far."}])
    assert "#### Previously…" in md and "\n## " not in "\n" + md


def test_text_after_the_closing_question_and_a_tool_is_a_recap():
    from claude_agent_sdk.types import TextBlock, ToolUseBlock as T
    scene = T("1", "mcp__rw__set_scene", {})
    roll = T("2", "mcp__rw__request_roll", {})
    out = _run_turn([TextBlock("Breeker smiles.\n\nWhat does Tomas do as he enters the hall?"), scene,
                     TextBlock("Holly packed the market... What does Tomas do as he enters the hall?")])
    assert not out[0].get("recap") and out[-1].get("recap")
    # a roll after the question means play went on: the next story is shown
    out = _run_turn([TextBlock("You creep closer. What do you do?"), roll, TextBlock("The guard turns.")])
    assert not out[-1].get("recap")


def test_reference_art_sizes_and_prompts(tmp_path, monkeypatch):
    from ringwraith import art, artqueue
    assert art.edit_size((1344, 576)) == (960, 384)          # wide scenes fit an edit in memory
    w, h = art.edit_size((768, 1024))
    assert w * h <= art.EDIT_MAX_PIXELS and w % 64 == 0 and h % 64 == 0
    assert "image 2 shows Holly" in art.ref_intro(["Tomas", "Holly"])
    assert art.ref_intro([]) == ""
    # a job's characters become references only when their notes have a portrait file
    (tmp_path / "90 Assets").mkdir()
    (tmp_path / "90 Assets" / "t.png").write_bytes(b"png")
    notes = {"Tomas": ({"image": "[[90 Assets/t.png]]"}, ""), "Nobody": ({}, "")}
    monkeypatch.setattr(artqueue.vault, "resolve_note", lambda name, *a: name)
    monkeypatch.setattr(artqueue.vault, "read_note", lambda name: notes[name])
    refs = artqueue.job_refs(tmp_path, {"characters": ["Tomas", "Nobody"]})
    assert [n for n, _ in refs] == ["Tomas"]



def test_book_style_keeps_rooms_indoors():
    from ringwraith import art
    pony = art.build_prompt("scenery", "the common room of a large old village inn at evening, a roaring hearth")
    assert "interior view of the common room" in pony and "no open sky" in pony and "landscape with" not in pony
    gate = art.build_prompt("scene", "an orc-chieftain on the threshold of a vast stone gateway in the mountains")
    assert "land and sky large" in gate and "no open sky" not in gate
    with pytest.raises(art.ArtError):
        art.build_prompt("scene", "x", style="watercolour")


def test_indoor_and_outdoor_scenes_are_told_apart():
    from ringwraith import art
    inside = ["A burglar's moment: a man kneels in deep shadow beneath a narrow wooden staircase",
              "Night in a low crooked attic room under the eaves of an old inn", "Noon in the old moot-hall of Bree",
              "The Twenty-first Hall of the North End, deep in Moria", "the common room of a large old village inn"]
    outside = ["A small whitewashed cottage in a back lane of Bree, a door open on a bare kitchen. On the step a woman",
               "Late morning before a squat stone watch-house on the hill in Bree, wardens muster in the yard",
               "Night and thick white fog in the wooded bottoms of the Chetwood, beside a standing stone"]
    assert all(art.is_interior(s) for s in inside) and not any(art.is_interior(s) for s in outside)


def test_ruins_get_colder_dustier_light():
    from PIL import Image
    from ringwraith import art
    assert art.is_ruin("The Twenty-first Hall of the North End, deep in Moria")
    assert art.is_ruin("a barrow on the downs, its door broken") and not art.is_ruin("the common room of an inn")
    hall = art.build_prompt("scene", "a hall deep in Moria")
    assert "dust hanging" in hall and "no soft fill light" in hall
    assert "dust hanging" not in art.build_prompt("scene", "the common room of an inn")
    img = Image.new("RGB", (40, 20), (150, 120, 90))                       # warm midtones: greyer and dimmer
    r, g, b = art.grade(img, None, ruin=True).getpixel((20, 10))
    assert max(r, g, b) - min(r, g, b) < 60 / 2 and r < 150 and g < 120



def test_underground_halls_and_dark_woods_have_their_own_look():
    from ringwraith import art
    tomb = "The Chamber of Mazarbul deep in Moria, Balin's Tomb: a great square chamber hewn from the rock"
    assert art.is_underground(tomb) and art.is_ruin(tomb) and art.is_interior(tomb)
    p = art.build_prompt("scene", tomb, "sorrow")
    assert "living rock deep under the mountain" in p and "no windows" in p and "Dwarf-runes" in p
    wood = "Deep in the Old Forest beside the Withywindle: an immense grey willow leaning over the river"
    assert art.is_darkwood(wood) and not art.is_underground(wood) and not art.is_ruin(wood)
    w = art.build_prompt("scene", wood, "dread")
    assert "ancient dark forest pressing close" in w and "no sky" in w and "dust hanging" not in w
    assert not art.is_darkwood("the Chetwood on a bright morning")      # an ordinary wood stays ordinary


def test_a_roll_waits_for_an_answer_to_the_players_argument(monkeypatch):
    import claude_agent_sdk
    from ringwraith.web import gametools

    captured = {}
    real = claude_agent_sdk.create_sdk_mcp_server
    monkeypatch.setattr(gametools, "create_sdk_mcp_server",
                        lambda name, version, tools: (captured.update({t.name: t for t in tools}),
                                                      real(name=name, version=version, tools=tools))[1])

    class Hub:
        async def ask(self, kind, event):
            raise AssertionError("the player must not be asked before they've had an answer")

        async def emit(self, e):
            pass

    turn = {"story_since_roll": True, "owe_reply": "Surely this is Inspired?"}
    gametools.build(Hub(), turn)
    args = {"who": "Band", "what": "Manoeuvre", "dice": 2, "tn": 15, "stakes": "x", "chained": True}
    r = asyncio.run(captured["request_roll"].handler(args))
    assert r.get("is_error") and "Surely this is Inspired?" in r["content"][0]["text"]


def test_only_cli_commands_with_a_table_tool_are_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(eng.cp, "campaign_dir", lambda *a, **k: tmp_path)
    e = eng.Engine.__new__(eng.Engine)
    e.tool_names = []
    verdict = lambda c: type(asyncio.run(e._permit("Bash", {"command": c}, None))).__name__  # noqa: E731
    assert verdict(".venv/Scripts/ringwraith map session").endswith("Allow")
    assert verdict('.venv/Scripts/ringwraith note encounter "Fitch" "x"').endswith("Allow")
    assert verdict('.venv/Scripts/ringwraith map move "Tomas" Bree').endswith("Deny")
    assert verdict(".venv/Scripts/ringwraith roll 3 --tn 14").endswith("Deny")
    pats = eng._blocked_patterns()
    assert "Bash(.venv/Scripts/ringwraith map move *)" in pats and "Bash(.venv/Scripts/ringwraith map *)" not in pats


def test_the_system_prompt_is_the_contract_and_the_rules_card(tmp_path):
    (tmp_path / "lore").mkdir()
    (tmp_path / "lore" / "core.md").write_text("# Rules card\nTN = something", encoding="utf-8")
    text = eng.system_prompt(tmp_path)
    assert text.startswith("# Ringwraith, the Loremaster") and text.rstrip().endswith("TN = something")
    assert "missing" in eng.system_prompt(tmp_path / "nowhere")          # no card: say so, don't crash


def test_blocked_commands_cover_both_spellings_of_the_cli():
    pats = eng._blocked_patterns()
    assert "Bash(.venv/Scripts/ringwraith.exe roll *)" in pats and "Bash(.venv/Scripts/ringwraith roll *)" in pats
    assert set(eng.BUILTIN_TOOLS) >= {"Read", "Edit", "Bash", "Skill"} and "WebFetch" not in eng.BUILTIN_TOOLS


def test_the_skills_name_table_tools_not_blocked_cli_commands():
    import re
    skills = sorted((eng.Path(__file__).parents[1] / ".claude" / "skills").glob("*/SKILL.md"))
    assert skills
    for f in skills:
        text = f.read_text(encoding="utf-8")
        if "disable-model-invocation: true" in text:
            continue                      # the player's own commands (/distill), run in Claude Code, not at the table
        for m in re.finditer(r"ringwraith(?:\.exe)? (\S+)(?: (\S+))?", text):
            cmd, sub = m.group(1).strip("`"), (m.group(2) or "").strip("`\"")
            assert not eng.has_tool(cmd, sub), f"{f.parent.name} tells the model to run blocked `ringwraith {cmd} {sub}`"


def test_dialogue_that_mentions_days_or_oracles_stays_in_the_story():
    from ringwraith.web.narration import tidy_story
    text = ('Mist on the downs.\n\n"We ride on day 3," says Sid, "whatever the oracle at the well says."\n\n'
            "The fire burns low.\n\nWhat does Tomas do?")
    assert tidy_story(text) == (text, False)


def test_the_system_prompt_goes_by_file_so_the_command_line_stays_short(tmp_path, monkeypatch):
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
    monkeypatch.setattr(eng.cp, "private_dir", lambda *a, **k: tmp_path)
    monkeypatch.setattr(eng.cp, "campaign_dir", lambda *a, **k: tmp_path)
    monkeypatch.setattr(eng.cp, "load_settings", lambda *a, **k: {"table": {}})
    e = eng.Engine.__new__(eng.Engine)
    e.repo, e.server, e.tool_names = eng.Path(__file__).parents[1], None, []
    opts = e._options(None)
    assert "append" not in opts.system_prompt
    assert (tmp_path / "table-prompt.md").read_text(encoding="utf-8").startswith("# Ringwraith, the Loremaster")
    t = SubprocessCLITransport(prompt="x", options=opts)
    t._cli_path = "claude.exe"
    assert len(" ".join(t._build_command())) < 20000            # Windows refuses command lines over 32,767 chars
