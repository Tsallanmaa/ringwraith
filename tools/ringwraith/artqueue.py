"""Background art queue: Ringwraith enqueues images during play, a worker renders them.

Queue:   <vault>/.ringwraith/art-queue.jsonl   (one JSON job per line, pending only)
Done:    <vault>/.ringwraith/art-done.jsonl
Worker:  `ringwraith art worker` (run in the background). Only one runs: it holds art-worker.lock for its
         whole life. art-worker.json records its last check-in and pid, for `status`.
When a job finishes, the image goes to 90 Assets/<folder>/ and, if the job names a note, the note gets it
(see attach_image: a portrait or scenery becomes the note's `image:`; a scene painting is only added).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import uuid
from pathlib import Path

from . import art
from . import campaign as cp
from . import config as cfg
from . import vault
from . import fileio

ASSET_FOLDER = {"portrait": "portraits", "adversary": "adversaries", "scenery": "scenery",
                "item": "items", "scene": "scenes"}
MAX_ATTEMPTS = 3
RETRY_DELAY = 20      # seconds between retries of a failed job


def _paths(slug: str | None = None, root: Path | None = None) -> dict[str, Path]:
    p = cp.private_dir(slug, root)
    return {"queue": p / "art-queue.jsonl", "done": p / "art-done.jsonl", "beat": p / "art-worker.json",
            "lock": p / "art-worker.lock"}


def _read_jobs(f: Path) -> list[dict]:
    if not f.exists():
        return []
    jobs = []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            if line.strip():
                jobs.append(json.loads(line))
        except ValueError:
            continue          # a damaged line is skipped, not fatal to the worker
    return jobs


def _write_jobs(f: Path, jobs: list[dict]) -> None:
    fileio.atomic_write(f, "".join(json.dumps(j, ensure_ascii=False) + "\n" for j in jobs))


def _update_queue(f: Path, change) -> list[dict]:
    """Read, change and write the queue under the data lock (the table, the CLI and the worker all write it)."""
    with fileio.locked():
        jobs = change(_read_jobs(f))
        _write_jobs(f, jobs)
        return jobs


def enqueue(preset: str, subject: str, note: str | None = None, name: str | None = None,
            priority: int = 5, seed: int | None = None, slug: str | None = None,
            root: Path | None = None, mood: str | None = None, time: str | None = None,
            characters: list[str] | None = None) -> dict:
    if preset not in art.PRESETS:
        raise art.ArtError(f"unknown preset {preset!r}")
    art.build_prompt(preset, subject, mood, time)   # validates mood and time
    paths = _paths(slug, root)
    note_rel = None
    if note:
        vroot = cp.campaign_dir(slug, root)
        note_rel = vault.resolve_note(note, slug, root).relative_to(vroot).as_posix()
    base = vault.slugify(name or (Path(note_rel).stem if note_rel else subject[:40])) or "image"
    job = {"id": uuid.uuid4().hex[:8], "preset": preset, "subject": subject, "note": note_rel,
           "file": f"90 Assets/{ASSET_FOLDER[preset]}/{base}-{uuid.uuid4().hex[:4]}.png",
           "priority": priority, "seed": seed, "mood": mood, "time": time, "characters": list(characters or []), "queued": dt.datetime.now().isoformat(timespec="seconds")}
    _update_queue(paths["queue"], lambda jobs: jobs + [job])
    return job


def pending(slug: str | None = None, root: Path | None = None) -> list[dict]:
    return _read_jobs(_paths(slug, root)["queue"])


def worker_alive(slug: str | None = None, root: Path | None = None) -> bool:
    """Is an art worker running? It holds art-worker.lock for its whole life, so this stays true through a
    long render or model load (a heartbeat alone went stale mid-render, and a second worker got started)."""
    return fileio.is_held(_paths(slug, root)["lock"])


@fileio.with_lock
def _attach(vroot: Path, job: dict) -> None:
    if not job.get("note"):
        return
    path = vroot / job["note"]
    if not path.exists():
        return
    fm, body = vault.read_note(path)
    vault.write_note(path, *attach_image(fm, body, job["file"], job.get("preset", "")))


def attach_image(fm: dict, body: str, file: str, preset: str) -> tuple[dict, str]:
    """Put a finished picture into its note. A portrait, adversary, item or scenery picture is the note's
    own picture: it becomes `image:` and replaces the picture right under the title (only that one; other
    embeds in the note, such as a chronicle's paintings, are left alone). A scene painting is added at the
    end and never becomes `image:`, since `image:` is the face used to paint that character later."""
    if preset == "scene":
        embed = f"![[{file}]]"
        return fm, body if embed in body else body.rstrip() + "\n\n" + embed + "\n"
    fm = dict(fm, image=f"[[{file}]]")
    embed = f"![[{file}|320]]"
    m = re.search(r"^# .*$", body, re.M)
    if not m:
        own = re.match(r"\s*!\[\[90 Assets/[^\]]+\]\]\n?", body)        # a picture at the very top
        return fm, embed + "\n" + (body[own.end():] if own else body)
    after = re.match(r"\n*!\[\[90 Assets/[^\]]+\]\]\n?", body[m.end():])  # the picture under the title
    rest = body[m.end() + after.end():] if after else body[m.end():]
    return fm, body[:m.end()] + "\n\n" + embed + "\n" + rest


def _code_stamp() -> tuple[float, ...]:
    """Modification times of the art code; a worker exits when they change so it never paints with stale settings."""
    return tuple(Path(m.__file__).stat().st_mtime for m in (art, cp, vault)) + (Path(__file__).stat().st_mtime,)


def _portrait_of(vroot: Path, name: str, slug=None, root=None) -> Path | None:
    """The image file of a character's portrait, from their note's `image:`."""
    try:
        fm, _ = vault.read_note(vault.resolve_note(name, slug, root))
    except Exception:  # noqa: BLE001 - unknown or ambiguous name: no reference
        return None
    img = str(fm.get("image") or "").strip("[]")
    f = vroot / img if img else None
    return f if f and f.is_file() else None


def job_refs(vroot: Path, job: dict, slug=None, root=None) -> list[tuple[str, Path]]:
    refs = []
    for name in job.get("characters") or []:
        f = _portrait_of(vroot, name, slug, root)
        if f:
            refs.append((name, f))
    return refs[:art.MAX_REFS]


def run_worker(slug: str | None = None, root: Path | None = None, once: bool = False,
               idle_exit_minutes: float = 240, log=print) -> int:
    paths = _paths(slug, root)
    fd = fileio.hold(paths["lock"])
    if fd is None:
        log("another art worker is already running")
        return 0
    try:
        return _work(slug, root, once, idle_exit_minutes, log, paths)
    finally:
        fileio.release(fd)


def _work(slug, root, once: bool, idle_exit_minutes: float, log, paths: dict[str, Path]) -> int:
    c = cfg.load()
    settings = cp.load_settings(slug, root)
    model = settings["art"].get("model") or art.DEFAULT_MODEL
    vroot = cp.campaign_dir(slug, root)
    done_count, idle_since = 0, time.time()
    last_model = None          # the first job frees the GPU for whichever model it needs
    stamp = _code_stamp()
    log(f"art worker: model {model}, vault {vroot}")
    while True:
        if _code_stamp() != stamp:
            log("art code changed; this worker stops so an up-to-date one can take over")
            break
        fileio.atomic_write(paths["beat"], json.dumps({"t": time.time(), "pid": os.getpid()}))   # for `status`
        jobs = _read_jobs(paths["queue"])
        if not jobs:
            if once or time.time() - idle_since > idle_exit_minutes * 60:
                break
            time.sleep(3)
            continue
        # prefer jobs for the model already loaded: every switch costs a long reload
        def wants(j):
            return art.REF_MODEL if job_refs(vroot, j, slug, root) else model
        best = min(j.get("priority", 5) for j in jobs)
        same = [j for j in jobs if wants(j) == last_model and j.get("priority", 5) <= best + 2]
        job = sorted(same or jobs, key=lambda j: (j.get("priority", 5), j["queued"]))[0]
        refs = job_refs(vroot, job, slug, root)
        use = art.REF_MODEL if refs else model
        if job.get("attempts", 0) >= MAX_ATTEMPTS - 1 and model != art.FALLBACK_MODEL:
            use = art.FALLBACK_MODEL   # last try with the fast fallback model
        if use != last_model:
            art.free_vram_for(c.lemonade_url, use, log=log)
            last_model = use
        try:
            if refs and job.get("attempts", 0) < MAX_ATTEMPTS - 1:
                r = art.render_with_refs(c.lemonade_url, job["preset"], job["subject"], refs, vroot / job["file"],
                                         seed=job.get("seed"), mood=job.get("mood"), time_=job.get("time"),
                                         style=cp.load_settings(slug, root)["art"].get("style"))
            else:
                r = art.render(c.lemonade_url, use, job["preset"], job["subject"], vroot / job["file"],
                               seed=job.get("seed"), mood=job.get("mood"), time=job.get("time"),
                               style=cp.load_settings(slug, root)["art"].get("style"))
            _attach(vroot, job)
            job.update(status="done", seconds=r.seconds, seed=r.seed, model=use)
            done_count += 1
            log(f"done {job['file']} ({r.seconds}s)")
        except Exception as e:  # noqa: BLE001 - keep the worker alive; record the failure
            job["attempts"] = job.get("attempts", 0) + 1
            job["error"] = str(e)[:300]
            if job["attempts"] < MAX_ATTEMPTS and not once:
                # Usually transient (GPU busy or out of memory, model loading): retry later.
                job["priority"] = job.get("priority", 5) + 1
                _update_queue(paths["queue"], lambda q: [j if j["id"] != job["id"] else job for j in q])
                log(f"retry later {job['id']} (attempt {job['attempts']}): {e}")
                time.sleep(RETRY_DELAY)
                continue
            job["status"] = "failed"
            log(f"failed {job['id']}: {e}")
        _update_queue(paths["queue"], lambda q: [j for j in q if j["id"] != job["id"]])
        with paths["done"].open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(job, ensure_ascii=False) + "\n")
        idle_since = time.time()
    paths["beat"].unlink(missing_ok=True)
    return done_count
