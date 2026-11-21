"""Retakes the README's screenshots in docs/images from a staged session at the real table.

    .venv/Scripts/python scripts/screenshots.py [name ...]     # all shots, or the named ones
    .venv/Scripts/python scripts/screenshots.py --art [key ...] # redraw the paintings (needs Lemonade)
    .venv/Scripts/python scripts/screenshots.py --keep table    # keep the staged vault and print where it is

The demo tale is docs/screenshots/session.py: its chapters say what the player typed, what Ringwraith told
and what the tools did. For each shot this script builds a fresh campaign vault in a scratch folder (never in
your vaults), plays the chapters up to that shot through the same library calls the table's tools make,
starts the table on it with Claude switched off, and photographs the page with headless Chrome.

Needs on this machine: Chrome, the gitignored lore/ (the maps), and a campaign holding the Lórien region maps,
copied from <vaults>/lorien-test by default (--regions-from <slug>). The paintings come from
docs/screenshots/art/.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
SHOTS_DIR = ROOT / "docs" / "screenshots"
ART_DIR = SHOTS_DIR / "art"
IMAGES = ROOT / "docs" / "images"
CHROME = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
          r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
          "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium"]
WINDOW = (1920, 1200)


def session():
    spec = importlib.util.spec_from_file_location("demo_session", SHOTS_DIR / "session.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- paintings

def make_art(keys: list[str]) -> None:
    from PIL import Image
    from ringwraith import art
    from ringwraith import config as cfg
    s = session()
    model = os.environ.get("RINGWRAITH_ART_MODEL", "Z-Image-Turbo-Q8B")
    ART_DIR.mkdir(parents=True, exist_ok=True)
    for key in keys or list(s.ART):
        spec = s.ART[key]
        png = ART_DIR / f"{key}.png"
        res = art.render(cfg.load().lemonade_url, model, spec["preset"], spec["subject"], png, seed=spec["seed"],
                         mood=spec.get("mood"), time=spec.get("time"), style="book")
        out = png.with_suffix(".jpg")                           # paintings keep well as JPEG, at a quarter the size
        Image.open(png).convert("RGB").save(out, quality=90)
        png.unlink()
        png.with_suffix(".json").unlink(missing_ok=True)       # the spec in session.py is the record
        print(f"{key}: {out.relative_to(ROOT)} ({res.seconds}s)", flush=True)


# ---------------------------------------------------------------- staging

class Stage:
    """Plays a chapter into the campaign: the table log the browser replays, and the vault the panels read."""

    def __init__(self, s):
        from ringwraith import campaign as cp
        self.s = s
        self.log = cp.private_dir() / "table-log.jsonl"
        self.ts = time.time() - 3600 * 3
        self.pending_roll: str | None = None
        self.marks: dict[str, int] = {}
        self._n = 0

    def emit(self, ev: dict) -> None:
        self.ts += 7
        with self.log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({**ev, "ts": self.ts}, ensure_ascii=False) + "\n")

    def _id(self) -> str:
        self._n += 1
        return f"demo{self._n:04d}"

    # what was said
    def player(self, text: str) -> None:
        self.emit({"t": "player", "text": text})

    def tell(self, text: str, sep: bool = False) -> None:
        self.emit({"t": "text_start"})
        self.emit({"t": "narration", "text": text})

    def mark(self, name: str) -> None:
        """A place in the tale a shot can stop at (SHOTS' `at`): the log after it is left out of that shot."""
        self.marks[name] = len(self.log.read_text(encoding="utf-8").splitlines()) if self.log.exists() else 0

    def end_turn(self) -> None:
        self.emit({"t": "turn_end"})

    def paths(self, paths: list[str]) -> None:
        self.emit({"t": "paths", "paths": paths})

    # the stage
    def scene(self, title: str, art: str | None = None) -> None:
        from ringwraith import campaign as cp, fileio
        self.emit({"t": "scene", "title": title, "job": None})
        fileio.atomic_write(cp.private_dir() / "table-scene.json", json.dumps({"title": title}))
        if art:
            self.emit({"t": "image", "preset": "scene", "job": None, "url": f"/assets/scenes/{art}.jpg",
                       "subject": title})

    # time, places and the sheet
    def clock(self, day: int, time: str) -> None:
        from ringwraith import clock, vault
        path, fm, body = clock.state()
        fm.update(day=day, time=time)
        vault.write_note(path, fm, body)

    def place(self, who: list[str], where: str, day: int | None = None) -> None:
        from ringwraith import geo
        if day:
            self.clock(day, "day")
        geo.place_at(where, who)
        geo.set_state(where, "current")

    def move(self, who: list[str], to: str, day: int | None = None) -> None:
        from ringwraith import geo
        geo.move(who, to, day=day, hero=self.s.HERO)

    def sheet(self, endurance: int | None = None, hope: int | None = None, fatigue: int | None = None,
              eye: int | None = None) -> None:
        from ringwraith import clock, vault
        h = vault.hero_note()
        fm, body = vault.read_note(h)
        if endurance is not None:
            fm["endurance"]["current"] = endurance
        if hope is not None:
            fm["hope"]["current"] = hope
        if fatigue is not None:
            fm["fatigue"] = fatigue
        vault.write_note(h, fm, body)
        if eye is not None:
            path, sfm, sbody = clock.state()
            sfm["eye_awareness"] = eye
            vault.write_note(path, sfm, sbody)

    # dice
    def _request(self, rid, who, what, rating, tn, stakes, favoured=False):
        from ringwraith import dice, vault
        o_plain = dice.odds(rating, tn, favoured=favoured)
        o_hope = dice.odds(rating, tn, favoured=favoured, hope=True)
        o_insp = dice.odds(rating, tn, favoured=favoured, hope=True, inspired=True)
        hope_now = vault.read_note(vault.hero_note())[0]["hope"]["current"]
        self._req = dict(who=who, what=what, rating=rating, tn=tn, favoured=favoured)
        self.emit({"t": "roll_request", "id": rid, "who": who, "what": what, "tn": tn, "stakes": stakes,
                   "mode": dice.feat_mode(favoured, False), "flags": [], "bonus": 0, "penalty": 0,
                   "dice": {"plain": o_plain.dice, "hope": o_hope.dice},
                   "odds": {"plain": vars(o_plain), "hope": vars(o_hope), "inspired": vars(o_insp)},
                   "hope_allowed": bool(hope_now), "hope_now": hope_now, "manual": False})

    def _result(self, rid, who, what, rating, tn, feat, success, favoured=False, hope=False, adversary=False):
        from ringwraith import dice
        from ringwraith.web.gametools import _face
        r = dice.test(rating, tn, favoured=favoured, hope=hope, adversary=adversary, feat=feat, success=success)
        ev = {"t": "roll_result", "who": who, "what": what, "tn": tn, "feat": [_face(f) for f in r.feat_rolled],
              "kept": _face(r.feat), "success": r.success, "total": r.total, "outcome": r.outcome,
              "degree": r.degree, "icons": r.icons, "notes": r.notes}
        if adversary:
            ev["adversary"] = True
        else:
            ev.update(id=rid, hope=hope, manual=False)
        self.emit(ev)

    def roll(self, who, what, rating, tn, feat, success, stakes="", favoured=False, hope=False, adversary=False):
        rid = self._id()
        if not adversary:
            self._request(rid, who, what, rating, tn, stakes, favoured)
        self._result(rid, who, what, rating, tn, feat, success, favoured, hope, adversary)

    def ask_roll(self, who, what, rating, tn, stakes, favoured=False):
        """A roll the table is still waiting for: the shot shows the dice tray open."""
        self.pending_roll = self._id()
        self._request(self.pending_roll, who, what, rating, tn, stakes, favoured)

    def answer_roll(self, feat, success, hope=False):
        q, rid, self.pending_roll = self._req, self.pending_roll, None
        self._result(rid, q["who"], q["what"], q["rating"], q["tn"], feat, success, q["favoured"], hope)

    def oracle(self, question, chance, feat, answer):
        self.emit({"t": "oracle", "kind": "telling", "question": question, "chance": chance, "feat": str(feat),
                   "answer": answer})

    # the fight
    def _fight(self, state):
        from ringwraith.web import fight as fg, views
        self.emit({"t": "fight", "fight": fg.public_view(state, views._portrait)})

    def fight_start(self, kind, title, foes, battle=None, stance=None):
        from ringwraith.web import fight as fg
        self._fight(fg.start(kind, title, foes, battle, stance))

    def fight_update(self, **changes):
        from ringwraith.web import fight as fg
        self._fight(fg.update(changes))

    def fight_end(self, outcome):
        from ringwraith.web import fight as fg
        done = fg.end(outcome)
        self.emit({"t": "fight", "fight": None})
        self.emit({"t": "fight_end", "title": done["title"], "kind": done["kind"], "outcome": done["outcome"]})

    # the journey
    def journey_start(self, frm, to, title, season, mode="on foot"):
        from ringwraith import geo
        from ringwraith.web import journey as jr
        plan = geo.journey_plan(frm, to)
        geo.set_plan(plan)
        self.emit({"t": "journey", "journey": jr.public_view(jr.start(frm, to, title, season, mode, plan=plan))})

    def journey_log(self, entry, story, move_to=None, end=False):
        from ringwraith.web import journey as jr
        if move_to:
            self.move(self.s.COMPANY, move_to)
        state, e = jr.log(entry)
        self.emit({"t": "journey_mark", "id": e["id"], "kind": e["kind"], "day": e["day"], "title": e["title"],
                   "at": e["at"]})
        self.tell(story)
        self.emit({"t": "journey", "journey": jr.public_view(state)})
        self.end_turn()


def build_campaign(vaults: Path, regions_from: Path, upto: str, at: str | None = None):
    """A fresh demo campaign in `vaults`, played up to the chapter `upto` (and its mark `at`, if given)."""
    from ringwraith import campaign as cp, geo, vault
    s = session()
    cp.vaults_root = lambda c=None: vaults
    vault.create(s.CAMPAIGN["slug"], name=s.CAMPAIGN["name"], region="lorien-and-moria", start="bree",
                 year=s.CAMPAIGN["year"], root=vaults)
    os.environ["RINGWRAITH_CAMPAIGN"] = s.CAMPAIGN["slug"]
    camp = vaults / s.CAMPAIGN["slug"]
    priv = camp / ".ringwraith"
    cp.set_value("art.enabled", False)          # no art worker, no image server needed
    shutil.copytree(regions_from / ".ringwraith" / "regions", priv / "regions")
    assets = camp / "90 Assets"
    for sub in ("scenes", "portraits", "adversaries"):
        (assets / sub).mkdir(parents=True, exist_ok=True)
    for pic in ART_DIR.glob("*.jpg"):
        preset = s.ART.get(pic.stem, {}).get("preset")
        sub = {"scene": "scenes", "adversary": "adversaries"}.get(preset, "portraits")
        shutil.copy(pic, assets / sub / pic.name)

    def with_fm(kind, name, fields, art_key=None, folder="portraits"):
        p = vault.new_note(kind, name)
        fm, body = vault.read_note(p)
        fm.update(fields)
        if art_key:
            fm["image"] = f"[[90 Assets/{folder}/{art_key}.jpg]]"
        vault.write_note(p, fm, body)

    with_fm("hero", s.HERO, s.HERO_SHEET, "edwy")
    band = camp / "20 Fellowship" / "Band.md"
    fm, body = vault.read_note(band)
    fm.update(s.BAND)
    vault.write_note(band, fm, body)
    for name, a in s.ALLIES.items():
        with_fm("ally", name, {"culture": a["culture"], "gift": a["gift"], "quirk": a["quirk"],
                               "status": "active", "injury": "none", "fatigue": "none"}, a["art"])
    with_fm("adversary", "Orc-chieftain", {}, "chieftain", "adversaries")
    threads = camp / "10 Campaign" / "Threads.md"
    fm, body = vault.read_note(threads)
    vault.write_note(threads, fm, body.replace("## Open\n", "## Open\n" + "".join(f"- {t}\n" for t in s.THREADS_OPEN)))
    compass = camp / "10 Campaign" / "Compass.md"
    fm, body = vault.read_note(compass)
    fm["cutaways"] = "on"
    vault.write_note(compass, fm, body)
    from ringwraith import clock
    path, sfm, sbody = clock.state()
    sfm.update(phase="adventuring", session=3, date=f"{s.CAMPAIGN['year']}, spring", day=1, eye_awareness=3,
               hunt_threshold=16)
    vault.write_note(path, sfm, sbody)
    geo.build_images(log=lambda m: None)

    stage = Stage(s)
    names = [c.__name__ for c in s.CHAPTERS]
    for chapter in s.CHAPTERS[:names.index(upto) + 1]:
        chapter(stage)
    if at:
        lines = stage.log.read_text(encoding="utf-8").splitlines()[:stage.marks[at]]
        stage.log.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        if stage.pending_roll and not any(stage.pending_roll in line for line in lines):
            stage.pending_roll = None
    path, sfm, sbody = clock.state()
    sfm["location"] = geo.load()["whereabouts"].get(s.HERO, {}).get("place", "Bree")
    vault.write_note(path, sfm, sbody)
    return stage


# ---------------------------------------------------------------- the table and the camera

def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def serve(stage: Stage, port: int):
    """The real table on the staged campaign, with Claude switched off. Returns the uvicorn server."""
    import uvicorn
    from ringwraith.web import engine, server

    async def idle(self):
        return None
    engine.Engine.start = idle
    engine.Engine.stop = idle
    server._art_worker_thread = lambda: None
    server._build_map_images = lambda: None
    hubs = []
    real_hub = server.Hub

    class Hub(real_hub):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            hubs.append(self)
    server.Hub = Hub
    app = server.create_app()
    if stage.pending_roll:          # the table waits for this roll, so the tray opens instead of "interrupted"
        class Waiting:
            def done(self):
                return False
        hubs[0].pending[stage.pending_roll] = ("roll", Waiting())
        hubs[0].busy = True
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.1)
    return srv


async def photograph(url: str, out: Path, steps: list[str], size=WINDOW) -> None:
    import websockets
    chrome = next((c for c in CHROME if Path(c).exists() or shutil.which(c)), None)
    if not chrome:
        sys.exit("Chrome (or Edge) not found")
    port = free_port()
    prof = tempfile.mkdtemp(prefix="rw-shot-")
    proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                             f"--user-data-dir={prof}", f"--window-size={size[0]},{size[1]}",
                             f"--remote-debugging-port={port}", "--remote-allow-origins=*", url],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        page = None
        for _ in range(80):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                page = next(t for t in tabs if t["type"] == "page")
                break
            except Exception:  # noqa: BLE001 - Chrome is still starting
                await asyncio.sleep(0.25)
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
            n = 0

            async def call(method, params=None):
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params or {}}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get("id") == n:
                        return r.get("result", {})

            await call("Emulation.setDeviceMetricsOverride",
                       {"width": size[0], "height": size[1], "deviceScaleFactor": 1, "mobile": False})
            await call("Page.reload")
            await asyncio.sleep(4)                   # the page connects, replays the tale and paints
            for js in steps:
                r = await call("Runtime.evaluate", {"expression": js, "awaitPromise": True})
                if r.get("exceptionDetails"):
                    print("  step failed:", js[:80], r["exceptionDetails"].get("text"))
                await asyncio.sleep(2)
            shot = await call("Page.captureScreenshot", {"format": "jpeg", "quality": 90})
            tmp = out.with_suffix(".tmp")
            tmp.write_bytes(base64.b64decode(shot["data"]))
            for attempt in range(20):                 # a preview of the old image may hold it open a moment
                try:
                    os.replace(tmp, out)
                    break
                except OSError:
                    if attempt == 19:
                        raise
                    await asyncio.sleep(0.5)
    finally:
        proc.kill()
        shutil.rmtree(prof, ignore_errors=True)


VIEWS = {
    "scene": [],
    "map": ["document.querySelector('#stage-tabs button[data-view=map]').click()"],
}


def shoot_one(name: str, regions_from: Path, keep: bool) -> None:
    s = session()
    shot = s.SHOTS[name]
    vaults = Path(tempfile.mkdtemp(prefix="rw-demo-"))
    try:
        stage = build_campaign(vaults, regions_from, shot["upto"], shot.get("at"))
        port = free_port()
        srv = serve(stage, port)
        IMAGES.mkdir(parents=True, exist_ok=True)
        out = IMAGES / f"{name}.jpg"
        steps = VIEWS[shot.get("view", "scene")] + list(shot.get("steps", []))
        asyncio.run(photograph(f"http://127.0.0.1:{port}/", out, steps, tuple(shot.get("size", WINDOW))))
        srv.should_exit = True
        print(f"{name}: {out.relative_to(ROOT)}", flush=True)
    finally:
        if keep:
            print(f"  staged vault kept: {vaults}")
        else:
            shutil.rmtree(vaults, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*")
    ap.add_argument("--art", action="store_true", help="redraw the paintings (all, or the named keys)")
    ap.add_argument("--regions-from", default="lorien-test", help="campaign slug to copy the region maps from")
    ap.add_argument("--keep", action="store_true", help="keep the staged vaults")
    ap.add_argument("--one", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.art:
        make_art(a.names)
        return
    from ringwraith import config as cfg
    regions_from = cfg.load().vaults / a.regions_from
    if not (regions_from / ".ringwraith" / "regions").is_dir():
        sys.exit(f"no region maps in {regions_from}: pass --regions-from <a campaign with the Lórien regions>")
    if a.one:
        shoot_one(a.names[0], regions_from, a.keep)
        return
    names = a.names or list(session().SHOTS)
    for name in names:                    # one process per shot: every shot starts from a clean slate
        cmd = [sys.executable, __file__, "--one", name, "--regions-from", a.regions_from] + (["--keep"] if a.keep else [])
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
