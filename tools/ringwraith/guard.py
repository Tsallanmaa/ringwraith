"""Pre-commit guard: keep copyrighted and derived material out of git.

Blocks any staged file that
  * lives under a source/derived folder (References/, lore/, build/, archive/),
  * is a PDF,
  * contains the purchase-watermark pattern from the reference PDFs,
  * is larger than MAX_BYTES (extracted art or rendered pages sneaking in).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_DIRS = ("references/", "lore/", "build/", "archive/")
FORBIDDEN_EXT = (".pdf",)
WATERMARK = re.compile(rb"\(Order\s*#\s*\d{5,}\)")
MAX_BYTES = 1_500_000


def check(path: str, data: bytes | None) -> list[str]:
    problems = []
    low = path.replace("\\", "/").lower()
    if low.startswith(FORBIDDEN_DIRS):
        problems.append("path is in a source/derived folder that must stay local")
    if low.endswith(FORBIDDEN_EXT):
        problems.append("PDF files are never committed")
    if data is not None:
        if len(data) > MAX_BYTES:
            problems.append(f"file is {len(data) // 1024} KiB (limit {MAX_BYTES // 1024} KiB)")
        if WATERMARK.search(data):
            problems.append("contains the reference-PDF purchase watermark")
    return problems


def _staged() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        check=True, capture_output=True,
    ).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def _staged_blob(path: str) -> bytes:
    return subprocess.run(["git", "show", f":{path}"], check=True, capture_output=True).stdout


def run(paths: list[str] | None = None) -> int:
    staged = paths is None
    files = _staged() if staged else paths
    failures = 0
    for f in files:
        if staged:
            data = _staged_blob(f)
        else:
            p = Path(f)
            data = p.read_bytes() if p.is_file() else None
        for problem in check(f, data):
            print(f"ringwraith guard: {f}: {problem}", file=sys.stderr)
            failures += 1
    if failures:
        print("ringwraith guard: commit blocked. Copyrighted or derived material must stay local.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:] or None))
