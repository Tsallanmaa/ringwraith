"""OCR for scanned books (no text layer): page images -> the same page-marked Markdown as pdftext.py.

Uses RapidOCR (ONNX, runs locally). Each page:
- is rendered and recognised, with each page's result cached so a long run can resume;
- has its lines put into reading order: full-width lines (headings, tables across both columns) split
  the page into bands, and in each band the left column is read before the right;
- has running headers kept as a comment, its printed page number taken from a lone number in the
  footer, and any watermark line dropped;
- gets common OCR slips fixed ("(ld)" -> "(1d)") and hyphenated line breaks joined.

Dice icons are pictures, so they don't come through; a distiller checks the rendered page where a
table or roll needs them (`ringwraith render <id> <page>`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from .pdftext import is_watermark, slugify

DPI = 110
LOOSE_WATERMARK = re.compile(r"ord[e3]r\s*[#n°]?\s*\d{5,}", re.I)
FIXES = [(re.compile(r"\((?:l|I|\|)\s?d\)"), "(1d)"), (re.compile(r"\((\d)\s?d\)"), r"(\1d)"),
         (re.compile(r"\s+([,.;:])"), r"\1")]


def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def _page_lines(engine, page) -> tuple[list[dict], int, int]:
    pix = page.get_pixmap(dpi=DPI)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
    res, _ = engine(img)
    lines = []
    for box, text, score in res or []:
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        lines.append({"x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys), "text": text, "score": float(score)})
    return lines, pix.w, pix.h


def _reading_order(lines: list[dict], w: int, h: int) -> tuple[list[str], str, str]:
    """Body text in reading order, plus the running header and the printed page number."""
    header, printed, body = [], "", []
    for ln in lines:
        t = ln["text"].strip()
        if not t or is_watermark(t) or LOOSE_WATERMARK.search(t):
            continue
        if ln["y1"] < h * 0.06:
            header.append(t)
            continue
        if ln["y0"] > h * 0.92 and re.fullmatch(r"\d{1,3}", t):
            printed = t
            continue
        body.append(ln)
    mid = w / 2
    full = lambda ln: (ln["x1"] - ln["x0"]) > w * 0.55 or (ln["x0"] < mid - w * 0.04 and ln["x1"] > mid + w * 0.04)  # noqa: E731
    out, band = [], []

    def flush():
        left = sorted((ln for ln in band if (ln["x0"] + ln["x1"]) / 2 < mid), key=lambda ln: ln["y0"])
        right = sorted((ln for ln in band if (ln["x0"] + ln["x1"]) / 2 >= mid), key=lambda ln: ln["y0"])
        out.extend(ln["text"] for ln in left + right)
        band.clear()

    for ln in sorted(body, key=lambda ln: ln["y0"]):
        if full(ln):
            flush()
            out.append(ln["text"])
        else:
            band.append(ln)
    flush()
    return out, " / ".join(header), printed


def _clean(lines: list[str]) -> str:
    text = ""
    for ln in lines:
        ln = ln.strip()
        for rx, rep in FIXES:
            ln = rx.sub(rep, ln)
        if text.endswith("-") and ln[:1].islower():
            text = text[:-1] + ln           # a word broken across lines
        else:
            text += ("\n" if text else "") + ln
    return text


def ocr_pdf(pdf: Path, source_id: str, title: str, out_dir: Path, cache_dir: Path, pages_per_section: int = 10,
            log=print) -> dict:
    import pymupdf
    doc = pymupdf.open(pdf)
    cache_dir.mkdir(parents=True, exist_ok=True)
    engine = None
    pages = []
    for i in range(doc.page_count):
        cf = cache_dir / f"page-{i + 1:03d}.json"
        if cf.exists():
            data = json.loads(cf.read_text(encoding="utf-8"))
        else:
            engine = engine or _ocr_engine()
            lines, w, h = _page_lines(engine, doc[i])
            data = {"w": w, "h": h, "lines": lines}
            cf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            if (i + 1) % 10 == 0:
                log(f"  {source_id}: OCR page {i + 1}/{doc.page_count}")
        body, header, printed = _reading_order(data["lines"], data["w"], data["h"])
        pages.append({"pdf_page": i + 1, "printed": printed, "header": header, "text": _clean(body)})
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.md"):
        old.unlink()
    sections = []
    for k in range(0, len(pages), pages_per_section):
        chunk = pages[k:k + pages_per_section]
        a, b = chunk[0]["pdf_page"], chunk[-1]["pdf_page"]
        heads = [p["header"] for p in chunk if p["header"]]
        name = heads[0] if heads else f"pages {a}-{b}"
        fname = f"{len(sections) + 1:02d}-{slugify(name) or 'pages'}-p{a}-{b}.md"
        parts = [f"---\nsource: {source_id}\nbook: \"{title}\"\nsection: \"{name} (OCR)\"\npdf_pages: {a}-{b}\nocr: true\n---\n"]
        for p in chunk:
            label = f" (printed {p['printed']})" if p["printed"] else ""
            parts.append(f"<!-- page {p['pdf_page']}{label} -->")
            if p["header"]:
                parts.append(f"<!-- header: {p['header']} -->")
            parts.append(p["text"] + "\n")
        (out_dir / fname).write_text("\n".join(parts), encoding="utf-8")
        sections.append({"file": fname, "title": name, "pdf_pages": [a, b],
                         "chars": sum(len(p["text"]) for p in chunk)})
    (out_dir / "_index.json").write_text(json.dumps({"source": source_id, "pdf": pdf.name, "pages": len(pages),
                                                     "ocr": True, "sections": sections}, indent=2,
                                                    ensure_ascii=False), encoding="utf-8")
    return {"pages": len(pages), "sections": sections}
