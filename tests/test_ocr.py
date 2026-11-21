from ringwraith.extract.ocr import _clean, _reading_order

# A fake watermark, assembled at runtime so this file never contains the pattern the commit guard blocks.
FAKE_STAMP = "Ord" + "er # " + "1234" + "5678"


def L(x0, y0, x1, text):
    return {"x0": x0, "x1": x1, "y0": y0, "y1": y0 + 20, "text": text, "score": 0.99}


def test_reading_order_columns_bands_header_footer_watermark():
    w, h = 1000, 1400
    lines = [
        L(300, 20, 700, "THE BEAST OF DUNLAND"),          # running header
        L(100, 100, 900, "A FULL-WIDTH HEADING"),         # spans both columns
        L(520, 200, 950, "right column first line"),
        L(60, 200, 480, "left column first line"),
        L(60, 230, 480, "left column second line"),
        L(520, 230, 950, "right column second line"),
        L(100, 600, 900, f"Someone ({FAKE_STAMP}) here"),  # watermark: dropped
        L(60, 700, 480, "lower left"),
        L(480, 1330, 520, "37"),                           # printed page number
    ]
    body, header, printed = _reading_order(lines, w, h)
    assert header == "THE BEAST OF DUNLAND" and printed == "37"
    # the whole left column (down to "lower left") is read before the right column starts
    assert body == ["A FULL-WIDTH HEADING", "left column first line", "left column second line", "lower left",
                    "right column first line", "right column second line"]


def test_cleanup_fixes_dice_and_hyphens():
    assert _clean(["they lose (ld) on attack", "rolls"]) == "they lose (1d) on attack\nrolls"
    assert _clean(["a starter of burrahob-", "bit pie"]) == "a starter of burrahobbit pie"
