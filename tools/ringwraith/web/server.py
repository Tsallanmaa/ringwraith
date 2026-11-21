"""Ringwraith Table web server: `ringwraith serve`."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import artqueue
from .. import campaign as cp
from .. import config as cfg
from . import gametools
from .engine import Engine
from .hub import Hub

log = logging.getLogger("ringwraith.table")
STATIC = Path(__file__).with_name("static")


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def local_origin(origin: str | None, host: str | None) -> bool:
    """Is a websocket coming from the table's own page? The Origin must be a local address with the same
    port the table was reached on (the Host header), so no other web page in the browser can drive it."""
    from urllib.parse import urlsplit
    if not origin or not host:
        return False
    try:
        o, h = urlsplit(origin), urlsplit("//" + host)
        same_port = o.port == h.port
    except ValueError:
        return False
    return (o.scheme in ("http", "https") and o.hostname in LOCAL_HOSTS and h.hostname in LOCAL_HOSTS
            and same_port)


def _art_worker_thread() -> None:
    """Keep the art worker running in a background thread while the table is open."""
    def loop() -> None:
        import time
        while True:
            try:
                if cp.load_settings()["art"]["enabled"] and not artqueue.worker_alive():
                    artqueue.run_worker(idle_exit_minutes=10, log=lambda m: log.info("art: %s", m))
            except Exception:  # noqa: BLE001
                log.exception("art worker crashed; restarting")
            time.sleep(5)
    threading.Thread(target=loop, name="art-worker", daemon=True).start()


def _build_map_images() -> None:
    """Make any map picture this campaign is missing (the base maps for a new campaign, a region drawn
    elsewhere), so the map view has every map it offers."""
    try:
        from .. import geo
        made = geo.build_images(log=lambda m: log.info("maps: %s", m))
        if made:
            log.info("maps: made %d map image(s)", len(made))
    except Exception:  # noqa: BLE001 - the table works without them; the map view leaves missing ones out
        log.exception("maps: could not build the map images")


async def _watch_images(hub: Hub) -> None:
    """Announce finished images (from art-done.jsonl) to the browser."""
    done = cp.private_dir() / "art-done.jsonl"
    seen = len(done.read_text(encoding="utf-8").splitlines()) if done.exists() else 0
    while True:
        await asyncio.sleep(2)
        if not done.exists():
            continue
        lines = done.read_text(encoding="utf-8").splitlines()
        for line in lines[seen:]:
            try:
                job = json.loads(line)
            except ValueError:
                continue
            if job.get("status") == "done":
                rel = job["file"].removeprefix("90 Assets/")
                await hub.emit({"t": "image", "job": job["id"], "preset": job["preset"],
                                "url": f"/assets/{rel}", "note": job.get("note"),
                                "subject": job["subject"][:200]})
                if job["preset"] in ("portrait", "adversary"):
                    await hub.emit({"t": "sheet", "sheet": gametools.sheet()})
        seen = len(lines)


def create_app() -> FastAPI:
    vault_dir = cp.campaign_dir()
    hub = Hub(cp.private_dir() / "table-log.jsonl")
    engine = Engine(hub, cfg.REPO_ROOT)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        _art_worker_thread()
        threading.Thread(target=_build_map_images, name="map-images", daemon=True).start()
        watcher = asyncio.create_task(_watch_images(hub))
        await engine.start()
        yield
        watcher.cancel()
        await engine.stop()

    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def no_stale_pages(request, call_next):
        """The table's own files (page, script, styles, data) are rechecked on every load, so a browser
        never keeps running an old version after an update. Paintings and maps may be cached."""
        response = await call_next(request)
        if not request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/api/sheet")
    async def api_sheet():
        return JSONResponse(gametools.sheet())

    @app.get("/api/geo")
    async def api_geo():
        return JSONResponse(await asyncio.to_thread(gametools.geo_view))

    @app.get("/api/fog/{map_id}.png")
    async def api_fog(map_id: str):
        from fastapi.responses import Response
        from .. import geo
        png = await asyncio.to_thread(geo.fog_png, map_id)      # drawing never holds up the table
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        if not local_origin(ws.headers.get("origin"), ws.headers.get("host")):
            # Browsers let any web page open a websocket to localhost; only the table's own page may talk to it.
            log.warning("refused a websocket from origin %r", ws.headers.get("origin"))
            await ws.close(code=1008)
            return
        await ws.accept()
        await ws.send_json({"t": "hello", "replay": hub.replay(), "busy": hub.busy,
                            "sheet": gametools.sheet()})
        hub.sockets.add(ws)
        try:
            while True:
                msg = await ws.receive_json()
                kind = msg.get("t")
                if kind == "say" and str(msg.get("text", "")).strip():
                    await engine.say(str(msg["text"]).strip())
                elif kind == "answer":
                    hub.answer(str(msg.get("id")), msg.get("data") or {})
                elif kind == "interrupt":
                    await engine.interrupt()
                elif kind == "new_session":
                    await engine.new_session()
                elif kind == "adjust":
                    from . import panels
                    try:
                        change = panels.adjust(str(msg.get("key")), msg.get("delta"), msg.get("value"))
                    except panels.AdjustError as e:
                        await ws.send_json({"t": "error", "text": str(e)})
                        continue
                    if change:
                        total = engine.player_changed(change)
                        await hub.emit({"t": "system", "change": change["key"],
                                        "text": f"You changed the sheet: {panels.describe(total)}."})
                    await hub.emit({"t": "sheet", "sheet": gametools.sheet()})
        except WebSocketDisconnect:
            pass
        finally:
            hub.sockets.discard(ws)

    assets = vault_dir / "90 Assets"
    assets.mkdir(exist_ok=True)
    app.mount("/assets", StaticFiles(directory=assets), name="assets")   # images only, never .ringwraith/
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app


def serve(host: str = "127.0.0.1", port: int = 2965, open_browser: bool = True) -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    app = create_app()
    if open_browser:
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{host}:{port}/")).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
