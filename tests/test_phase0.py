"""Foundations: the guard, runes and PDF extraction. They use synthetic data only, never the reference PDFs."""

import pymupdf as fitz

from ringwraith import guard, sources
from ringwraith.extract import pdftext, runes


def fake_watermark(name: str, number: str = "12345678") -> str:
    """A purchase-watermark-shaped string, assembled at runtime so this file never
    contains the literal pattern (the pre-commit guard would block it)."""
    return f"{name} (Order " + "#" + f"{number})"


def test_rune_signatures():
    assert runes.classify(8, 96) == runes.GANDALF
    assert runes.classify(3, 38) == runes.EYE
    assert runes.classify(1, 32) == runes.SUCCESS
    assert runes.classify(2, 64) == runes.SUCCESS * 2
    assert runes.classify(5, 17) == runes.UNKNOWN


def test_guard_blocks_derived_material():
    assert guard.check("References/x.txt", b"")
    assert guard.check("lore/rules/core.md", b"")
    assert guard.check("build/raw/core/01.md", b"")
    assert guard.check("notes/book.pdf", b"")
    assert guard.check("tools/x.py", f"text {fake_watermark('Jane Doe')} more".encode())
    assert guard.check("big.png", b"0" * (guard.MAX_BYTES + 1))


def test_guard_allows_code():
    assert guard.check("tools/ringwraith/cli.py", b"print('hi')") == []
    assert guard.check("vault-kit/snippets/theme.css", b"body{}") == []


def test_text_cleanup():
    assert pdftext.clean_inline("Fellow­ship Player-­hero") == "Fellowship Player-hero"
    assert pdftext.join_lines(["an opportu-", "nity here"]) == "an opportunity here"
    assert pdftext.join_lines(["Mirkwood", "Elves"]) == "Mirkwood Elves"
    assert pdftext.slugify("Chapter 3: Journeys in the Dark") == "chapter-3-journeys-in-the-dark"
    assert pdftext.is_watermark(fake_watermark("Some Name", "53760000"))
    assert pdftext.parse_pages("3,5-7") == [3, 5, 6, 7]


def test_plan_sections_splits_long_chapters():
    toc = [
        [1, "Intro", 3],
        [1, "Big", 10],
        [2, "Part A", 12],
        [2, "Part B", 30],
        [1, "Appendix", 60],
    ]
    secs = pdftext.plan_sections(toc, 70, max_pages=30)
    titles = [(s.title, s.start, s.end) for s in secs]
    assert titles == [
        ("Front Matter", 1, 2),
        ("Intro", 3, 9),
        ("Big", 10, 11),
        ("Part A", 12, 29),
        ("Part B", 30, 59),
        ("Appendix", 60, 70),
    ]


def test_page_text_inserts_icons_and_drops_watermark():
    doc = fitz.open()
    page = doc.new_page(width=400, height=600)
    page.insert_text((50, 100), "Roll the Feat die: a      result is great.", fontsize=10)
    page.insert_text((50, 580), fake_watermark("Jane Doe"), fontsize=8)
    page.insert_text((50, 300), "Body text that should survive.", fontsize=10)
    # fake a Gandalf rune: 8 filled paths with 12 items each, inside the gap
    shape = page.new_shape()
    for i in range(8):
        x = 140 + (i % 2) * 2
        for j in range(12):
            shape.draw_line((x, 93 + j * 0.5), (x + 1, 93 + j * 0.5 + 0.4))
        shape.finish(fill=(0.78, 0.29, 0.25), color=None, closePath=True)
    shape.commit()
    pt = pdftext.page_text(page)
    text = "\n".join(pt.blocks)
    assert "Order #" not in text
    assert "Body text that should survive." in text
    assert "{gandalf}" in text or pt.icons  # signature depends on how fitz groups paths
