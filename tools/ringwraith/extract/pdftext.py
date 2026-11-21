"""Turn a reference PDF into raw Markdown sections for distillation.

Output is a faithful, lightly-cleaned dump: watermark and running headers
removed, soft hyphens fixed, dice icons restored as {gandalf}/{eye}/{success}
tokens, TOC entries marked as headings, and page markers kept so every later
note can cite its source page. Tables come out as cell soup; the distillation
step reads rendered pages for those.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz

from .runes import UNKNOWN, find_icons

WATERMARK = re.compile(r"\(Order\s*#\s*\d+\)")
SOFT_HYPHEN = "­"
HEADER_BAND = 0.06   # fraction of page height treated as running header
FOOTER_BAND = 0.05   # ... and running footer
MARGIN_MAX_CHARS = 40


# ---------------------------------------------------------------- text utils

def slugify(text: str, maxlen: int = 60) -> str:
    text = text.replace(SOFT_HYPHEN, "").lower()
    text = re.sub(r"[’'`]", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:maxlen].rstrip("-") or "section"


def norm(text: str) -> str:
    text = text.replace(SOFT_HYPHEN, "")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def clean_inline(text: str) -> str:
    text = text.replace("-" + SOFT_HYPHEN, "-").replace(SOFT_HYPHEN, "")
    text = text.replace(" ", " ").replace(" ", " ").replace("\t", " ")
    return re.sub(r"[ ]{2,}", " ", text)


def join_lines(lines: list[str]) -> str:
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not out:
            out = line
        elif re.search(r"[a-z]-$", out) and re.match(r"[a-z]", line):
            out = out[:-1] + line          # de-hyphenate a wrapped word
        else:
            out += " " + line
    return out


def is_watermark(text: str) -> bool:
    return bool(WATERMARK.search(text))


def has_text_layer(pdf: Path, sample: int = 12) -> bool:
    """False for a PDF that is only page images (it needs `extract --ocr`): judged by a few pages from its middle."""
    with fitz.open(pdf) as doc:
        start = max(0, doc.page_count // 2 - sample // 2)
        pages = range(start, min(doc.page_count, start + sample))
        return sum(len(doc[i].get_text().strip()) for i in pages) > 200 * len(pages)


# ------------------------------------------------------------- page → blocks

@dataclass
class PageText:
    pdf_page: int                       # 1-based
    label: str                          # printed page label if the PDF has one
    blocks: list[str] = field(default_factory=list)
    icons: dict[str, int] = field(default_factory=dict)


def _line_items(line: dict) -> list[tuple[float, str]]:
    """Characters of a rawdict line, in content order, with their left x."""
    return [(c["bbox"][0], c["c"]) for s in line["spans"] for c in s["chars"]]


def _insert_icon(items: list[tuple[float, str]], x: float, token: str) -> None:
    for i, (cx, _) in enumerate(items):
        if cx > x:
            items.insert(i, (x, f" {token} "))
            return
    items.append((x, f" {token} "))


def page_text(page: fitz.Page) -> PageText:
    h = page.rect.height
    data = page.get_text("rawdict")
    lines: list[dict] = []          # {"block": i, "bbox": Rect, "items": [...]}
    for bi, block in enumerate(data["blocks"]):
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            items = _line_items(line)
            if items:
                lines.append({"block": bi, "bbox": fitz.Rect(line["bbox"]), "items": items})

    icons = find_icons(page)
    counts: dict[str, int] = {}
    for icon in icons:
        # Inline icons sit within a text line; table icons sit in a Feat-die
        # column, up to ~150pt left of the row text on the same baseline.
        best, best_d = None, 40.0 if icon.token == UNKNOWN else 150.0
        for ln in lines:
            r = ln["bbox"]
            overlap = min(r.y1, icon.rect.y1) - max(r.y0, icon.rect.y0)
            if overlap < 0.25 * min(icon.rect.height, r.height):
                continue
            dx = max(r.x0 - icon.rect.x1, icon.rect.x0 - r.x1, 0)
            if dx < best_d:
                best, best_d = ln, dx
        if best is None:
            if icon.token != UNKNOWN:      # unknown + no text nearby = decoration
                counts["unplaced"] = counts.get("unplaced", 0) + 1
            continue
        counts[icon.token] = counts.get(icon.token, 0) + 1
        _insert_icon(best["items"], (icon.rect.x0 + icon.rect.x1) / 2, icon.token)

    by_block: dict[int, list[str]] = {}
    for ln in lines:
        text = clean_inline("".join(t for _, t in ln["items"]))
        if not text.strip() or is_watermark(text):
            continue
        r = ln["bbox"]
        in_margin = r.y1 < h * HEADER_BAND or r.y0 > h * (1 - FOOTER_BAND)
        if in_margin and len(text.strip()) <= MARGIN_MAX_CHARS:
            continue
        by_block.setdefault(ln["block"], []).append(text)

    pt = PageText(pdf_page=page.number + 1, label=page.get_label() or "", icons=counts)
    for bi in sorted(by_block):
        text = join_lines(by_block[bi])
        if text:
            pt.blocks.append(re.sub(r"[ ]{2,}", " ", text))
    return pt


# ---------------------------------------------------------- TOC → sections

@dataclass
class Section:
    level: int
    title: str
    start: int   # 1-based pdf page, inclusive
    end: int     # inclusive


def plan_sections(toc: list[list], page_count: int, max_pages: int = 30) -> list[Section]:
    """Split at TOC level 1, descending a level for any section longer than max_pages."""
    entries = [(lvl, title.strip(), max(1, page)) for lvl, title, page, *_ in toc if page > 0]
    if not entries:
        return [Section(1, "Full Text", 1, page_count)]

    def split(level: int, hi: int, items: list[tuple[int, str, int]]) -> list[Section]:
        tops = [i for i, e in enumerate(items) if e[0] == level]
        out: list[Section] = []
        for k, i in enumerate(tops):
            _, title, start = items[i]
            j = tops[k + 1] if k + 1 < len(tops) else len(items)
            end = max(start, items[j][2] - 1 if j < len(items) else hi)
            children = items[i + 1:j]
            if end - start + 1 > max_pages and any(c[0] == level + 1 for c in children):
                kids = split(level + 1, end, children)
                first = min(k.start for k in kids)
                if first > start:
                    out.append(Section(level, title, start, first - 1))
                else:
                    kids[0] = Section(kids[0].level, f"{title}: {kids[0].title}", kids[0].start, kids[0].end)
                out.extend(kids)
            else:
                out.append(Section(level, title, start, end))
        return out

    top = min(e[0] for e in entries)
    first_top = next(i for i, e in enumerate(entries) if e[0] == top)
    sections = split(top, page_count, entries[first_top:])
    if sections and sections[0].start > 1:
        sections.insert(0, Section(1, "Front Matter", 1, sections[0].start - 1))
    return sections


# ------------------------------------------------------------------ extract

def _heading_marks(toc: list[list]) -> dict[int, list[tuple[int, str]]]:
    marks: dict[int, list[tuple[int, str]]] = {}
    for lvl, title, page, *_ in toc:
        if page > 0:
            marks.setdefault(page, []).append((lvl, title.strip().replace(SOFT_HYPHEN, "")))
    return marks


def _render_page(pt: PageText, headings: list[tuple[int, str]]) -> str:
    label = f" (printed {pt.label})" if pt.label and pt.label != str(pt.pdf_page) else ""
    blocks = list(pt.blocks)
    placed: list[tuple[int, str]] = []
    pending: list[str] = []
    for lvl, title in headings:
        h = "#" * min(lvl + 1, 6) + " " + title
        key = norm(title)
        for i, b in enumerate(blocks):
            if key and norm(b).startswith(key):
                placed.append((i, h))
                rest = b[len(title):].strip() if b.lower().startswith(title.lower()) else None
                if rest is not None:
                    blocks[i] = rest
                elif norm(b) == key:
                    blocks[i] = ""
                break
        else:
            pending.append(h)
    out = [f"<!-- page {pt.pdf_page}{label} -->"] + pending
    insert_at = {i: h for i, h in placed}
    for i, b in enumerate(blocks):
        if i in insert_at:
            out.append(insert_at[i])
        if b:
            out.append(b)
    return "\n\n".join(out)


def extract_pdf(pdf: Path, source_id: str, title: str, out_dir: Path, max_pages: int = 30) -> dict:
    doc = fitz.open(pdf)
    toc = doc.get_toc()
    sections = plan_sections(toc, doc.page_count, max_pages)
    marks = _heading_marks(toc)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.md"):
        old.unlink()

    icon_totals: dict[str, int] = {}
    pages: dict[int, PageText] = {}
    for i in range(doc.page_count):
        pt = page_text(doc[i])
        pages[i + 1] = pt
        for k, v in pt.icons.items():
            icon_totals[k] = icon_totals.get(k, 0) + v

    index = []
    width = len(str(len(sections)))
    for n, sec in enumerate(sections, 1):
        fname = f"{n:0{width}d}-{slugify(sec.title)}.md"
        body = []
        for p in range(sec.start, sec.end + 1):
            body.append(_render_page(pages[p], marks.get(p, [])))
        front = (
            "---\n"
            f"source: {source_id}\n"
            f"book: {json.dumps(title)}\n"
            f"section: {json.dumps(sec.title)}\n"
            f"pdf_pages: {sec.start}-{sec.end}\n"
            "---\n\n"
            f"# {sec.title}\n\n"
        )
        (out_dir / fname).write_text(front + "\n\n".join(body) + "\n", encoding="utf-8")
        chars = sum(len(b) for p in range(sec.start, sec.end + 1) for b in pages[p].blocks)
        index.append({"file": fname, "title": sec.title, "level": sec.level,
                      "pdf_pages": [sec.start, sec.end], "chars": chars})

    summary = {
        "source": source_id,
        "pdf": pdf.name,
        "pages": doc.page_count,
        "sections": index,
        "icons": icon_totals,
        "empty_pages": [p for p, pt in pages.items() if not pt.blocks],
    }
    (out_dir / "_index.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


# ------------------------------------------------------------------- render

def strip_watermark(page: fitz.Page) -> int:
    """Remove the purchase watermark text from a page (in memory) before rendering."""
    n = 0
    for blk in page.get_text("dict")["blocks"]:
        for line in blk.get("lines", []):
            text = "".join(s["text"] for s in line["spans"])
            if is_watermark(text):
                page.add_redact_annot(fitz.Rect(line["bbox"]))
                n += 1
    if n:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                              graphics=fitz.PDF_REDACT_LINE_ART_NONE)
    return n


def render_pages(pdf: Path, pages: list[int], out_dir: Path, dpi: int = 110) -> list[Path]:
    doc = fitz.open(pdf)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for p in pages:
        if not 1 <= p <= doc.page_count:
            raise ValueError(f"page {p} out of range 1-{doc.page_count}")
        page = doc[p - 1]
        strip_watermark(page)
        path = out_dir / f"p{p:04d}.png"
        page.get_pixmap(dpi=dpi).save(path)
        written.append(path)
    return written


def parse_pages(spec: str) -> list[int]:
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        elif part:
            pages.append(int(part))
    return pages
