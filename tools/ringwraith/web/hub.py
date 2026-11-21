"""Event hub: broadcasts events to connected browsers, keeps a replay log, and holds
interactions (e.g. a pending roll) that wait for the player's answer."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

# Events that are only useful live (streaming deltas, activity) are not written to the log.
EPHEMERAL = {"text_delta", "activity", "busy", "sheet"}   # a page that connects gets a fresh sheet anyway
REPLAY_LIMIT = 400


class Hub:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.sockets: set[Any] = set()
        self.pending: dict[str, tuple[str, asyncio.Future]] = {}
        self.busy = False

    async def emit(self, event: dict) -> None:
        event.setdefault("ts", time.time())
        if event["t"] not in EPHEMERAL:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        dead = []
        for ws in list(self.sockets):
            try:
                await ws.send_json(event)
            except Exception:  # noqa: BLE001 - a closed tab must not break play
                dead.append(ws)
        for ws in dead:
            self.sockets.discard(ws)

    def replay(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text(encoding="utf-8").splitlines()[-REPLAY_LIMIT:]
        events = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        answered = {e["id"] for e in events if e["t"] in ("roll_result", "roll_cancelled") and "id" in e}
        for e in events:   # a roll request from a previous run can no longer be answered
            if e["t"] == "roll_request" and e["id"] not in answered and e["id"] not in self.pending:
                e["stale"] = True
        return events

    async def ask(self, kind: str, event: dict) -> dict:
        """Show an interaction to the player and wait for their answer."""
        iid = uuid.uuid4().hex[:10]
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self.pending[iid] = (kind, fut)
        try:
            await self.emit({**event, "id": iid})
            return await fut
        finally:
            self.pending.pop(iid, None)

    def answer(self, iid: str, data: dict) -> bool:
        item = self.pending.get(iid)
        if not item or item[1].done():
            return False
        item[1].set_result({**data, "_id": iid})
        return True

    def pending_of(self, kind: str) -> list[str]:
        return [iid for iid, (k, f) in self.pending.items() if k == kind and not f.done()]
