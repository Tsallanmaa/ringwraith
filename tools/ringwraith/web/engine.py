"""The Loremaster session: one Agent SDK client running Ringwraith, fed by the player's messages."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage,
                              SystemMessage)
from claude_agent_sdk.types import (PermissionResultAllow, PermissionResultDeny, StreamEvent, TextBlock,
                                    ToolUseBlock)

from .. import campaign as cp
from . import gametools
from .narration import (RETELL, ends_with_question, is_aside, is_mechanics_only,  # noqa: F401
                        tidy_story)
from .hub import Hub

log = logging.getLogger("ringwraith.table")

PROMPT_FILE = Path(__file__).with_name("prompt.md")
# Claude Code's built-in tools the Loremaster needs; the rest (agents, todos, notebooks, web…) would only cost
# tokens in every request. The table's own tools come from its MCP server.
BUILTIN_TOOLS = ["Read", "Glob", "Grep", "Edit", "Write", "Bash", "Skill"]   # no ToolSearch: see _options
READ_ONLY = {"Read", "Glob", "Grep", "Skill", "LS"}


# Parts of the contract that matter only when a setting is on: `<!-- if:name -->` … `<!-- /if -->` in prompt.md.
# Left out otherwise, they cost nothing on every call. The prompt is rebuilt when the table (re)connects, so a
# change in the Settings dialog reconnects (PROMPT_SETTINGS), and a Compass change applies from the next session.
CONDITIONAL = re.compile(r"<!-- if:([a-z-]+) -->\n(.*?)<!-- /if -->\n", re.S)
PROMPT_SETTINGS = {"table.model", "play.oracle", "play.paths", "difficulty.easy"}


def prompt_conditions() -> set[str]:
    """Which conditional parts of the contract apply to the active campaign."""
    from .. import tale, vault
    try:
        s = cp.load_settings()
    except cp.CampaignError:
        return set()
    play, difficulty = s.get("play") or {}, s.get("difficulty") or {}
    on = set()
    if play.get("oracle") == "player":
        on.add("oracle-player")
    if not play.get("paths", True):
        on.add("paths-off")
    if difficulty.get("easy"):
        on.add("easy")
    try:
        compass = cp.campaign_dir() / "10 Campaign" / "Compass.md"
        if compass.exists() and tale.cutaways_on(vault.read_note(compass)[0]):
            on.add("cutaways")
    except Exception:  # noqa: BLE001 - a Compass that won't parse just leaves cutaways off
        pass
    return on


def apply_conditions(text: str, on: set[str]) -> str:
    return CONDITIONAL.sub(lambda m: m.group(2) if m.group(1) in on else "", text)


def system_prompt(repo: Path) -> str:
    """The Loremaster contract followed by the rules card (lore/core.md, gitignored: from the user's books)."""
    text = apply_conditions(PROMPT_FILE.read_text(encoding="utf-8"), prompt_conditions())
    core = repo / "lore" / "core.md"
    if core.exists():
        text += "\n\n" + core.read_text(encoding="utf-8")
    else:
        text += "\n\n(The rules card lore/core.md is missing: open lore/INDEX.md and the procedures for every rule.)"
    return text + looks_section()


def looks_section() -> str:
    """The campaign's painting looks (settings: art.lora), for `set_scene` and `queue_art`. Empty without any."""
    from .. import art
    try:
        looks = art.look_names(cp.load_settings()["art"])
    except Exception:  # noqa: BLE001 - a broken setting means no looks, not a broken table
        return ""
    picks = {n: w for n, w in looks.items() if n != "sketch"}
    if not picks:
        return ""
    lines = "\n".join(f"- `{n}`: {w or 'when it suits the scene'}" for n, w in picks.items())
    return ("\n\n## Painting looks (this campaign)\nBesides the house style, `set_scene` and `queue_art` take a "
            "`look`. Pick one when the scene fits its description below, and leave it out otherwise; the house "
            "style stays best for places full of small detail. A look paints without portrait references, so "
            "leave it out when a named character's face matters.\n" + lines)
FILE_TOOLS = {"Edit", "Write", "MultiEdit"}
# ringwraith CLI commands that have a table tool instead (so they show up in the browser).
# None: the whole command; otherwise just those subcommands. The rest of `note` and `map`
# (note encounter, map session, map where…) stays open at the table.
HAS_TOOL: dict[str, set[str] | None] = {
    "roll": None, "ask": None, "table": None, "odds": None, "tn": None,
    "note": {"new", "get", "set"}, "map": {"move", "place", "journey", "region"}}
# Commands with no place at the table: they would remove or swap the campaign mid-play, start a second server
# or art worker, or rebuild the library. The table runs the art worker itself.
NOT_AT_TABLE: dict[str, set[str] | None] = {
    "archive": None, "reset": None, "switch": None, "serve": None, "extract": None, "render": None,
    "lore-index": None, "art": {"worker", "test", "gen", "models"}}
CLI_RE = re.compile(r"^\s*(?:\.venv[\\/]Scripts[\\/])?ringwraith(?:\.exe)?\s+(\S+)(?:\s+(\S+))?")


def _blocked_patterns() -> list[str]:
    """Deny rules for the commands a table tool stands in for, and those with no place at the table. They must be
    deny rules: the project settings allow `.venv/Scripts/ringwraith *`, and an allow rule is decided before
    `can_use_tool` (_permit) is ever asked; only a deny rule wins over it."""
    out = []
    for table in (HAS_TOOL, NOT_AT_TABLE):
        for cmd, subs in sorted(table.items()):
            for c in ([cmd] if subs is None else [f"{cmd} {s}" for s in sorted(subs)]):
                for exe in ("ringwraith", "ringwraith.exe"):       # the project settings allow both spellings
                    out += [f"Bash(.venv/Scripts/{exe} {c}:*)", f"Bash(.venv/Scripts/{exe} {c} *)",
                            f"Bash(.venv/Scripts/{exe} {c})"]
    return out


def not_at_table(cmd: str, sub: str | None) -> bool:
    if cmd not in NOT_AT_TABLE:
        return False
    subs = NOT_AT_TABLE[cmd]
    return subs is None or (sub or "") in subs


def has_tool(cmd: str, sub: str | None) -> bool:
    """Does a table tool stand in for `ringwraith <cmd> <sub>`?"""
    if cmd not in HAS_TOOL:
        return False
    subs = HAS_TOOL[cmd]
    return subs is None or (sub or "") in subs
SHELL_META = re.compile(r"[;&|<>`$\n]")
ROLL_TOOLS = {"request_roll", "roll_adversary", "ask", "roll_table", "oracle_reading"}


ACTIVITY = {"Read": "consults the lore", "Grep": "searches the lore", "Glob": "searches the lore",
            "Edit": "writes in the chronicle", "Write": "writes in the chronicle", "Skill": "opens a procedure",
            "Bash": "consults the tools"}


def last_session_ended() -> bool:
    """Whether the current session note was ended (session-end fills in its tale days). False when there is no
    session yet (a new campaign keeps its session-zero conversation)."""
    from .. import clock, vault
    try:
        n = int(clock.state()[1].get("session") or 0)
        if not n:
            return False
        note = vault.session_note(n)
        return note.exists() and bool(str(vault.read_note(note)[0].get("tale_days") or "").strip())
    except Exception:  # noqa: BLE001 - when in doubt, keep the conversation
        return False


def where_now() -> str:
    """Where the map has everyone, grouped by place: ' Map: Tomas, Sid at The Prancing Pony; Herb at Archet.'"""
    from .. import geo
    try:
        data = geo.load()
    except Exception:  # noqa: BLE001
        return ""
    groups: dict[str, list[str]] = {}
    for who, w in (data.get("whereabouts") or {}).items():
        groups.setdefault((w or {}).get("place") or "unknown", []).append(who.split()[0])
    if not groups:
        return ""
    return " Map: " + "; ".join(f"{', '.join(ws)} at {place}" for place, ws in groups.items()) + "."


class Engine:
    _retell = False       # this turn's outcome came only as mechanics: ask for the story once more
    _retelling = False    # that second ask is running; its story goes above the summary
    _drifted = False      # the last reply put mechanics in its story paragraphs; remind the model next turn

    def __init__(self, hub: Hub, repo: Path):
        self.hub = hub
        self.repo = repo
        self.client: ClaudeSDKClient | None = None
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.runner: asyncio.Task | None = None
        self.turn: dict = {"story_since_roll": True}
        self.server, self.tool_names = gametools.build(hub, self.turn)
        self._held: str | None = None     # last text block, until we know what follows it
        self._paths_shown = False         # fold later text: it's a recap (after Paths, or after the closing question)
        self._asked = False               # the turn's story has ended with its closing question
        self._stopping = False            # the player pressed Stop
        self.sheet_changes: dict[str, dict] = {}   # hand edits to the hero sheet since the last message
        self.settings_changes: dict[str, str] = {}  # settings changed in the dialog since the last message
        self._reconnect = False                     # a new model: reconnect (same conversation) before the next turn


    # ------------------------------------------------------------ session
    @property
    def _session_file(self) -> Path:
        return cp.private_dir() / "table-session.json"

    def _saved_session(self) -> str | None:
        try:
            return json.loads(self._session_file.read_text(encoding="utf-8")).get("session_id")
        except (OSError, ValueError):
            return None

    def _save_session(self, sid: str) -> None:
        from .. import fileio
        fileio.atomic_write(self._session_file, json.dumps({"session_id": sid}))

    def _prompt_file(self) -> Path:
        """Write the Loremaster's system prompt (the contract and the rules card) where the CLI can read it."""
        from .. import fileio
        f = cp.private_dir() / "table-prompt.md"
        fileio.atomic_write(f, system_prompt(self.repo))
        return f

    def _options(self, resume: str | None) -> ClaudeAgentOptions:
        settings = cp.load_settings()
        table = settings.get("table", {}) or {}
        return ClaudeAgentOptions(
            cwd=str(self.repo),
            add_dirs=[str(cp.campaign_dir())],
            setting_sources=["project"],
            # The contract and rules card are the whole system prompt, in place of Claude Code's coding preset
            # (~4k tokens of git and coding guidance on every call; the skills are still listed). They go in by
            # file: passed inline they made the command line longer than Windows allows (32,767 characters).
            extra_args={"system-prompt-file": str(self._prompt_file())},
            tools=BUILTIN_TOOLS,
            mcp_servers={gametools.SERVER: self.server},
            allowed_tools=self.tool_names,
            disallowed_tools=["WebSearch", "WebFetch", "NotebookEdit",
                              *_blocked_patterns()],
            can_use_tool=self._permit,
            include_partial_messages=True,
            resume=resume,
            model=table.get("model"),
            # A roll waits for the player; don't let the tool call time out. Tool search off: the table's own
            # tools (~5k tokens) are loaded up front, which costs less than a ToolSearch round trip (a whole
            # model call over the full context) each time one is first needed.
            # Claude Code's own skills (code review, dataviz…) have no place at the table: listing them costs ~2k
            # tokens on every call, and Ringwraith could wander into one.
            env={"MCP_TOOL_TIMEOUT": str(24 * 3600 * 1000), "ENABLE_TOOL_SEARCH": "false",
                 "CLAUDE_CODE_DISABLE_BUNDLED_SKILLS": "1"},
            stderr=lambda line: log.debug("claude: %s", line),
        )

    async def _permit(self, name: str, inp: dict[str, Any], ctx: Any):
        """Decide every tool call without asking: play must never stop for a permission prompt."""
        if name in self.tool_names or name in READ_ONLY:
            return PermissionResultAllow()
        if name in FILE_TOOLS:
            target = Path(str(inp.get("file_path", ""))).resolve()
            vault_dir = cp.campaign_dir().resolve()
            if target.is_relative_to(vault_dir):
                return PermissionResultAllow()
            return PermissionResultDeny(message=f"Only files inside the campaign vault ({vault_dir}) may be edited.")
        if name == "Bash":
            cmd = str(inp.get("command", ""))
            m = CLI_RE.match(cmd)
            if m and not SHELL_META.search(cmd):
                if has_tool(m.group(1), m.group(2)):
                    what = " ".join(g for g in m.groups() if g) if HAS_TOOL[m.group(1)] else m.group(1)
                    return PermissionResultDeny(message=f"Use the table tool instead of `ringwraith {what}`.")
                if not_at_table(m.group(1), m.group(2)):
                    return PermissionResultDeny(message=f"`ringwraith {m.group(1)}` isn't run at the table.")
                return PermissionResultAllow()
            return PermissionResultDeny(message="In the web table, Bash may only run single `ringwraith` commands.")
        return PermissionResultDeny(message=f"{name} is not available at the table.")

    async def start(self) -> None:
        if self.runner is None or self.runner.done():
            self.runner = asyncio.create_task(self._run())

    async def _connect(self) -> None:
        resume = self._saved_session()
        self.client = ClaudeSDKClient(options=self._options(resume))
        try:
            await self.client.connect()
        except Exception:
            if not resume:
                raise
            log.warning("could not resume session %s; starting a new one", resume)
            self.client = ClaudeSDKClient(options=self._options(None))
            await self.client.connect()

    async def begin(self) -> None:
        """Begin session. After a session that was ended properly, start a fresh conversation first: everything
        that matters is in the vault, and a long conversation makes every turn cost more, since each one rereads
        it. A session that was never ended (a reboot, a closed tab) keeps its conversation."""
        if last_session_ended():
            await self.new_session()
        await self.say("/session-start")

    async def new_session(self) -> None:
        """Forget the conversation (the vault and state stay). Use at the start of a play session."""
        await self.stop()
        self._session_file.unlink(missing_ok=True)
        await self.hub.emit({"t": "system", "text": "New conversation started. Ringwraith will reload the campaign state."})
        await self.start()

    async def stop(self) -> None:
        if self.runner:
            self.runner.cancel()
            try:
                await self.runner
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self.runner = None
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self.client = None

    # ------------------------------------------------------------ turns
    async def say(self, text: str, ask: bool = False) -> None:
        """A message from the player. If a roll is waiting, the words answer it instead; if an oracle reading is
        waiting, the words are the player's own reading, or with `ask` a question to Ringwraith about it."""
        waiting = self.hub.pending_of("roll")
        reading = self.hub.pending_of("reading")
        command = text.lstrip().startswith(("/", "("))
        if reading and not waiting and not command and not ask:
            if self.hub.answer(reading[0], {"action": "own", "text": text}):
                return                  # the reading card shows the words: no player bubble as well
        await self.hub.emit({"t": "player", "text": text})
        if command:
            # a command or a table button (End session, repaint, Ask again) is never an answer: it closes what
            # waits, so the turn can finish, and then goes to Ringwraith
            for iid in waiting + reading:
                self.hub.answer(iid, {"action": "cancel"})
        elif waiting and self.hub.answer(waiting[0], {"action": "talk", "text": text}):
            return
        elif reading and self.hub.answer(reading[0], {"action": "talk", "text": text}):
            return
        await self.queue.put(text + self._table_note())

    def _table_note(self) -> str:
        """What the table shows right now, appended to the player's message (not shown to the player)."""
        from .. import clock
        try:
            fm = clock.state()[1]
        except Exception:  # noqa: BLE001
            return ""
        when = f"day {clock.today(fm)}" + (f", {fm['time']}" if fm.get("time") else "")
        edits = ""
        if self.sheet_changes:
            from .panels import describe
            edits = (" The player changed the hero sheet by hand: "
                     + "; ".join(describe(c) for c in self.sheet_changes.values())
                     + ". Take these as the current values (don't re-apply them).")
            self.sheet_changes.clear()
        if self.settings_changes:
            edits += (" The player changed the campaign settings: " + "; ".join(self.settings_changes.values())
                      + ". Play by them from now on.")
            self.settings_changes.clear()
        from .views import open_procedures
        under_way = open_procedures()
        if under_way:
            edits += (f" Under way on the table: {', '.join(under_way)}. If this conversation hasn't seen it yet, "
                      "call that tool with action 'show' and open its skill before going on.")
        if self._drifted:
            self._drifted = False
            edits += (" Your last reply drifted into mechanics and recap inside the story (oracle odds, day counts, "
                      "stats, events reported instead of shown); the table moved those lines to the OOC box. This "
                      "turn, play the scene out: what is seen and heard, and the speakers' own words. Mechanics go "
                      "only in the short OOC box (changed values only), then the question.")
        return (f"\n\n<table-state>Stage shows: '{gametools.current_scene() or 'nothing yet'}'. "
                f"{when}.{where_now()}{edits} If this turn moves to a new place, time or danger, call set_scene; "
                f"if anyone has gone somewhere the map doesn't show, call move first.</table-state>")

    def player_changed(self, change: dict) -> dict:
        """The player edited the hero sheet at the table. Changes to the same tracker since the last
        message are merged (Hope 7 → 6 → 5 is Hope 7 → 5). Returns the merged change."""
        prev = self.sheet_changes.get(change["key"])
        merged = dict(change, old=prev["old"]) if prev else dict(change)
        if merged["old"] == merged["new"]:
            self.sheet_changes.pop(change["key"], None)
        else:
            self.sheet_changes[change["key"]] = merged
        return merged

    def settings_changed(self, changes: list[dict]) -> None:
        """Settings saved from the dialog: tell Ringwraith with the next message, and pick up a new model at the
        start of the next turn (never mid-turn: a roll may be waiting)."""
        for c in changes:
            self.settings_changes[c["key"]] = f"{c['label']}: {c['value']}"
            if c["key"] in PROMPT_SETTINGS:      # a new model, or a part of the contract that comes or goes
                self._reconnect = True

    async def interrupt(self) -> None:
        """Stop Ringwraith's turn. Interrupt first, then close any waiting roll, so the cancelled roll
        doesn't prompt Ringwraith to carry on writing."""
        if not self.hub.busy or not self.client:
            return
        self._stopping = True
        await self.hub.emit({"t": "system", "text": "Interrupting Ringwraith…"})
        try:
            await self.client.interrupt()
        except Exception:  # noqa: BLE001 - the CLI may be gone; the trays still close, the next turn starts clean
            log.exception("interrupt failed")
        finally:
            for iid in self.hub.pending_of("roll") + self.hub.pending_of("reading"):
                self.hub.answer(iid, {"action": "cancel"})

    async def _set_busy(self, busy: bool) -> None:
        self.hub.busy = busy
        await self.hub.emit({"t": "busy", "busy": busy})

    async def _run(self) -> None:
        while True:
            text = await self.queue.get()
            await self._set_busy(True)
            self._paths_shown = False
            self._asked = False
            self._stopping = False                # a Stop whose interrupt never came back mustn't carry over
            self.turn["story_since_roll"] = True
            self.turn["told"] = False             # any story written yet this turn?
            self.turn["held_paths"] = None        # Paths offered before the story told the outcome
            self.turn["owe_reply"] = None         # the player argued over a roll and awaits an answer
            self.turn["asked_paths"] = text.lstrip().lower().startswith("/paths")   # cards even when they're off
            self._retell = self._retelling = False
            try:
                if self._reconnect and self.client is not None:     # a new model, same conversation
                    self._reconnect = False
                    try:
                        await self.client.disconnect()
                    except Exception:  # noqa: BLE001
                        pass
                    self.client = None
                if self.client is None:
                    await self._connect()
                await self.client.query(text)
                async for msg in self.client.receive_response():
                    await self._handle(msg)
                if self._retell and not self._stopping:   # the outcome came only as mechanics: ask once for the story
                    self._retell, self._retelling = False, True
                    self._paths_shown = self._asked = False
                    await self.client.query(RETELL)
                    async for msg in self.client.receive_response():
                        await self._handle(msg)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - report and keep the table alive
                log.exception("turn failed")
                await self.hub.emit({"t": "error", "text": f"{type(e).__name__}: {e}"})
                try:
                    if self.client:
                        await self.client.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                self.client = None
            finally:
                try:
                    await self._flush()
                except Exception:  # noqa: BLE001
                    pass
                await self._set_busy(False)

    async def _flush(self, next_tool: str | None = None) -> None:
        """Emit the held text block, as story or (if it's bookkeeping) as an aside."""
        if self._held is None:
            return
        text, self._held = self._held, None
        self.turn["pending_story"] = False
        if self._paths_shown:
            await self.hub.emit({"t": "narration", "text": text, "recap": True})
            return
        aside = is_aside(text, next_tool)
        # mechanics only, or an OOC note alone: the retold story goes above it, before its closing question
        summary = (not aside and not self._retelling and not self.turn.get("story_since_roll", True)
                   and (text.lstrip().startswith(">") or is_mechanics_only(text)))
        if summary:                               # mechanics only: the outcome is still untold as story
            await self.hub.emit({"t": "narration", "text": text, "summary": True})
            return
        if not aside and not text.lstrip().startswith(">"):
            text, drifted = tidy_story(text)
            self._drifted = self._drifted or drifted
            self.turn["story_since_roll"] = True
            self.turn["told"] = True
            if ends_with_question(text):
                self._asked = True
        await self.hub.emit({"t": "narration", "text": text, **({"aside": True} if aside else {})})

    async def _show_held_paths(self) -> None:
        """Paths offered too early (before the story told the outcome) appear once the story is told."""
        held = self.turn.get("held_paths")
        if held and (self.turn.get("story_since_roll") or self._retelling) and not self._stopping:
            self.turn["held_paths"] = None
            await self.hub.emit({"t": "paths", "paths": held})

    async def _handle(self, msg: Any) -> None:
        if isinstance(msg, StreamEvent):
            if msg.parent_tool_use_id:
                return
            ev = msg.event
            if ev.get("type") == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                await self.hub.emit({"t": "text_delta", "text": ev["delta"]["text"]})
            elif ev.get("type") == "content_block_start":
                block = ev.get("content_block", {})
                if block.get("type") == "tool_use":
                    await self._flush(str(block.get("name", "")).removeprefix(f"mcp__{gametools.SERVER}__"))
                elif block.get("type") == "text":
                    await self._flush()
                    await self.hub.emit({"t": "text_start", **({"muted": True} if self._paths_shown else {}),
                                         **({"retell": True} if self._retelling else {})})
            return
        if isinstance(msg, AssistantMessage):
            if msg.parent_tool_use_id:
                return
            for block in msg.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    await self._flush()
                    self._held = block.text
                    self.turn["owe_reply"] = None   # Ringwraith has written something the player will see
                    # a placeholder ("the story follows") doesn't tell the outcome; don't let it unlock the next roll
                    self.turn["pending_story"] = not (block.text.lstrip().startswith(">") or is_aside(block.text, None))
                elif isinstance(block, ToolUseBlock):
                    short = block.name.removeprefix(f"mcp__{gametools.SERVER}__")
                    await self._flush(short)
                    if short in ROLL_TOOLS:
                        # story_since_roll is cleared by the tool itself once something is rolled: clearing it
                        # here raced the tool's own check and refused a turn's first roll as untold.
                        self.turn["held_paths"] = None   # another roll: those choices are stale
                        self._asked = False          # play goes on: what follows is new story
                    elif self._asked:
                        self._paths_shown = True     # story told and question asked: later text is a recap
                    if short == "offer_paths":
                        # Fold later text away only if the story already told what the rolls led to;
                        # otherwise that text is the outcome, and the player must see it.
                        self._paths_shown = self.turn["story_since_roll"]
                    await self.hub.emit({"t": "activity", "tool": short,
                                         "text": ACTIVITY.get(block.name, "")})
            return
        if isinstance(msg, SystemMessage):
            sid = (msg.data or {}).get("session_id")
            if msg.subtype == "init" and sid:
                self._save_session(sid)
            return
        if isinstance(msg, ResultMessage):
            await self._flush()
            if msg.session_id:
                self._save_session(msg.session_id)
            if (not self.turn.get("story_since_roll", True) and not self._retelling and not self._stopping
                    and not msg.is_error):
                self._retell = True               # _run asks for the story; the turn isn't over yet
                return
            await self._show_held_paths()
            try:   # notes and the state may have been edited directly this turn (the place, a deadline...)
                await self.hub.emit({"t": "sheet", "sheet": gametools.sheet()})
            except Exception:  # noqa: BLE001 - the panels refresh on the next change anyway
                log.exception("sheet refresh failed")
            if self._stopping:
                self._stopping = False
                await self.hub.emit({"t": "system", "text": "Interrupted. Ringwraith waits for your word."})
            elif msg.is_error:
                await self.hub.emit({"t": "error", "text": f"turn ended with {msg.subtype}"})
            await self.hub.emit({"t": "turn_end"})
