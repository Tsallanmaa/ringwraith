"""Safe file writes for the campaign's data.

- `atomic_write(path, text)`: writes a temp file beside the target and swaps it in, so a crash mid-write
  never leaves a half-written note, geo.yaml or state.md. On Windows a swap can fail for a moment while
  another program (Obsidian, a virus scanner) has the file open, so it retries briefly.
- `locked()`: one lock shared by every Ringwraith process (the web table, CLI commands the model runs,
  the art worker), held around each read-modify-write so two writers can't drop each other's change.
  It is re-entrant within a thread, so locked functions may call each other.
- `append_line(path, line)` / `read_jsonl(path)`: the append-only logs (travels, rolls, art, the table log). A
  crash mid-append can leave a half line at the end: the next append starts on a fresh line instead of gluing
  onto it, and reading skips a line that doesn't parse instead of failing the whole log.
"""

from __future__ import annotations

import contextlib
import functools
import json
import os
import tempfile
import threading
import time
from pathlib import Path

LOCK_FILE = Path(tempfile.gettempdir()) / "ringwraith-data.lock"
LOCK_TIMEOUT = 30.0          # seconds; every locked section is a quick load-modify-save

def append_line(path: Path, line: str, sync: bool = False) -> None:
    """Append one line (no newline in it) to a log, starting a fresh line if a crash left the last one unfinished."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as fh:
        fh.seek(0, os.SEEK_END)
        lead = b""
        if fh.tell():
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) != b"\n":
                lead = b"\n"
        fh.write(lead + line.encode("utf-8") + b"\n")
        fh.flush()
        if sync:
            os.fsync(fh.fileno())


def read_jsonl(path: Path) -> list:
    """The records of a JSON-lines log, skipping lines that don't parse (a crash's half line)."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


_local = threading.local()
_thread_lock = threading.RLock()


def atomic_write(path: Path, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with open(tmp, "w", encoding=encoding, newline="") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


def _lock_fd(fd: int) -> None:
    deadline = time.monotonic() + LOCK_TIMEOUT
    while True:
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() > deadline:
                raise TimeoutError(f"another Ringwraith process has held {LOCK_FILE} for {LOCK_TIMEOUT:.0f}s")
            time.sleep(0.02)


def _unlock_fd(fd: int) -> None:
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextlib.contextmanager
def locked():
    """Hold the data lock (re-entrant within a thread; other threads and processes wait)."""
    depth = getattr(_local, "depth", 0)
    if depth:
        _local.depth = depth + 1
        try:
            yield
        finally:
            _local.depth -= 1
        return
    with _thread_lock:
        fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT)
        try:
            _lock_fd(fd)
            _local.depth = 1
            try:
                yield
            finally:
                _local.depth = 0
                _unlock_fd(fd)
        finally:
            os.close(fd)


def hold(path: Path) -> int | None:
    """Take a lock file for as long as this process wants it (e.g. the art worker's whole life). Returns the
    handle to pass to `release`, or None if someone else already holds it. Never waits."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except OSError:
        os.close(fd)
        return None


def release(fd: int) -> None:
    try:
        _unlock_fd(fd)
    finally:
        os.close(fd)


def is_held(path: Path) -> bool:
    """Does some process hold this lock file right now?"""
    if not Path(path).exists():
        return False
    fd = hold(path)
    if fd is None:
        return True
    release(fd)
    return False


def with_lock(fn):
    """Decorator: run a read-modify-write function under the data lock."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        with locked():
            return fn(*a, **kw)
    return wrapper
