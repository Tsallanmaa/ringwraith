"""Hand-drawn style region maps, in the manner of the official Eriador player map.

Sepia ink on parchment:
- scalloped broadleaf trees and little firs, woods fraying at their edges, copses;
- downs drawn as rows of rolling strokes, a hill with hachures;
- grass strokes and furrowed fields across open country;
- marsh tufts, double-line roads, a hedge ring, clustered thatched cottages;
- uncial lettering with red-brown region names, a double frame, compass, scale and title cartouche.

Drawn at 2x and scaled down for smooth ink. Input is a geography file in miles (lore/maps/<region>.yaml).
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import config as cfg

PARCHMENT = (213, 196, 164)
EDGE = (167, 141, 104)
INK = (58, 40, 22)
INK_SOFT = (96, 74, 50)
RED = (138, 62, 42)
SS = 2                 # supersampling
LW = 2 * SS            # main ink line
LT = SS + 1            # thin ink


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    fonts = cfg.load().build / "fonts"
    for f in (fonts / name, Path("C:/Windows/Fonts/georgia.ttf")):
        try:
            return ImageFont.truetype(str(f), size)
        except OSError:
            continue
    return ImageFont.load_default()


def parchment(w: int, h: int, seed: int = 7) -> Image.Image:
    """Parchment with soft mottling and darkened edges, in the player map's colours."""
    rng = np.random.default_rng(seed)
    base = np.ones((h, w, 3), np.float32) * np.array(PARCHMENT, np.float32)
    mott = np.zeros((h, w), np.float32)
    for scale, amp in ((8, 9), (32, 6), (128, 4), (512, 3)):
        small = rng.normal(0, 1, (max(2, h // scale), max(2, w // scale))).astype(np.float32)
        mott += np.asarray(Image.fromarray(small).resize((w, h), Image.BICUBIC)) * amp
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    edge = np.clip((r - 0.75) / 0.6, 0, 1)[..., None]
    out = base + mott[..., None]
    out = out * (1 - edge * 0.35) + np.array(EDGE, np.float32) * edge * 0.35
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


class Region:
    def __init__(self, geo: dict, seed: int = 2965):
        self.g = geo
        self.ppm = geo["px_per_mile"]
        x0, y0, x1, y1 = geo["bounds"]
        self.x0, self.y0 = x0, y0
        from .geo.common import REGION_MARGIN
        self.margin = REGION_MARGIN
        self.w = int((x1 - x0) * self.ppm) + 2 * self.margin
        self.h = int((y1 - y0) * self.ppm) + 2 * self.margin
        self.rng = random.Random(seed)
        self.k = max(1.0, 50 / self.ppm)        # spacing in miles grows on land maps so symbols keep their pixel spacing

    # miles -> pixels (final scale), and supersampled
    def px(self, p) -> tuple[float, float]:
        return (self.margin + (p[0] - self.x0) * self.ppm, self.margin + (p[1] - self.y0) * self.ppm)

    def s(self, p) -> tuple[float, float]:
        x, y = self.px(p)
        return (x * SS, y * SS)

    # ------------------------------------------------------------------ geometry helpers
    @staticmethod
    def _inside(pt, poly) -> bool:
        from .geo.common import point_in_polygon
        return point_in_polygon(pt, poly)

    def _scatter(self, poly, spacing: float):
        """Jittered points inside a polygon (miles), roughly `spacing` miles apart, back to front."""
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        pts, y, row = [], min(ys), 0
        while y <= max(ys):
            x = min(xs) + (spacing / 2 if row % 2 else 0)
            while x <= max(xs):
                p = (x + self.rng.uniform(-.35, .35) * spacing, y + self.rng.uniform(-.35, .35) * spacing)
                if self._inside(p, poly):
                    pts.append(p)
                x += spacing
            y += spacing * 0.8
            row += 1
        return sorted(pts, key=lambda p: p[1])

    @staticmethod
    def _smooth(points, n: int = 8):
        """Catmull-Rom through the points."""
        if len(points) < 3:
            return list(points)
        pts = [points[0]] + list(points) + [points[-1]]
        out = []
        for i in range(1, len(pts) - 2):
            p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
            for k in range(n):
                t = k / n
                t2, t3 = t * t, t * t * t
                out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t
                                        + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                        + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in range(2)))
        out.append(tuple(points[-1]))
        return out

    # ------------------------------------------------------------------ glyphs (supersampled canvas)
    def tree_broadleaf(self, d, x, y, size):
        """A scalloped crown with a shaded underside and a little trunk, like the player map's woods."""
        r = size
        d.line([(x, y + r * .3), (x, y + r * .9)], fill=INK, width=LW)
        for lx, ly, lr in ((-0.5, 0.05, .55), (0.5, 0.05, .55), (0, -0.4, .6), (-0.28, -0.22, .5), (0.28, -0.22, .5)):
            cx, cy = x + lx * r, y + ly * r
            d.ellipse([cx - r * lr, cy - r * lr * .9, cx + r * lr, cy + r * lr * .9], fill=PARCHMENT, outline=INK, width=LT)
        d.ellipse([x - r * .72, y - r * .38, x + r * .72, y + r * .32], fill=PARCHMENT)
        d.arc([x - r * .75, y - r * .25, x + r * .75, y + r * .48], 15, 165, fill=INK, width=LW)
        for k in range(3):
            hx = x + r * (0.1 + k * .18)
            d.line([(hx, y + r * .05), (hx - r * .12, y + r * .3)], fill=INK_SOFT, width=SS)

    def tree_fir(self, d, x, y, size):
        h = size * 1.7
        d.line([(x, y - h * .1), (x, y + size * .3)], fill=INK, width=LT)
        for k, f in enumerate((0, .3, .58)):
            ty = y - h + f * h
            wdt = size * (0.32 + 0.2 * k)
            d.polygon([(x, ty), (x - wdt, ty + h * .44), (x + wdt, ty + h * .44)], fill=PARCHMENT)
            d.line([(x - wdt, ty + h * .44), (x, ty), (x + wdt, ty + h * .44)], fill=INK, width=LT)

    def wood(self, d, poly, spacing, kind, edge_keep=0.5):
        for p in self._scatter(poly, spacing):
            near_edge = any(not self._inside((p[0] + dx, p[1] + dy), poly)
                            for dx, dy in ((.45, 0), (-.45, 0), (0, .45), (0, -.45)))
            if near_edge and self.rng.random() > edge_keep:
                continue          # the wood frays into the country instead of ending in a line
            x, y = self.s(p)
            size = self.rng.uniform(9, 14) * SS
            if kind == "conifer" or (kind == "mixed" and self.rng.random() < 0.3):
                self.tree_fir(d, x, y, size * .9)
            else:
                self.tree_broadleaf(d, x, y, size)

    def copse(self, d, center):
        pts = sorted(((center[0] + self.rng.gauss(0, .22 * self.k), center[1] + self.rng.gauss(0, .15 * self.k))
                      for _ in range(self.rng.randint(4, 8))), key=lambda p: p[1])
        for p in pts:
            x, y = self.s(p)
            self.tree_broadleaf(d, x, y, self.rng.uniform(8, 12) * SS)

    def grass(self, d, x, y, size):
        """The player map's open-country strokes: two or three short, slightly curved dashes."""
        for k in range(self.rng.randint(2, 3)):
            ox, oy = x + self.rng.uniform(-size, size), y + k * size * .45
            d.arc([ox - size, oy - size * .3, ox + size, oy + size * .3], 200, 340, fill=INK_SOFT, width=SS)

    def field(self, d, cx, cy, w, h, angle):
        ca, sa = math.cos(angle), math.sin(angle)
        rot = lambda a, b: (cx + a * ca - b * sa, cy + a * sa + b * ca)  # noqa: E731
        poly = [rot(-w, -h), rot(w, -h), rot(w, h), rot(-w, h)]
        d.line(poly + [poly[0]], fill=INK_SOFT, width=SS)
        for k in range(1, 4):
            b = -h + k * 2 * h / 4
            d.line([rot(-w, b), rot(w, b)], fill=INK_SOFT, width=1)

    def down_rows(self, d, poly):
        """Downs as rows of long rolling strokes, with hatching under each rise."""
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        k = self.k
        y = min(ys) + 0.3 * k
        while y < max(ys):
            x = min(xs)
            while x < max(xs):
                seg = self.rng.uniform(0.8, 1.8) * k
                if self._inside((x + seg / 2, y), poly) and self.rng.random() < 0.8:
                    rise = self.rng.uniform(.12, .22) * k
                    pts = [self.s((x + t / 12 * seg, y - math.sin(t / 12 * math.pi) * rise)) for t in range(13)]
                    d.line(pts, fill=INK, width=LT, joint="curve")
                    for k in range(4):
                        hx, hy = self.s((x + seg * (0.55 + k * .1), y - rise * .5))
                        d.line([(hx, hy), (hx - 6 * SS, hy + 10 * SS)], fill=INK_SOFT, width=SS)
                x += seg + self.rng.uniform(0.15, 0.5) * k
            y += self.rng.uniform(0.4, 0.55) * k

    def hill(self, d, center, radius):
        """A broad hill: a dome outline, inner contours, and hachures falling to the south-east."""
        cx, cy = center
        rx, ry = radius
        for k, f in enumerate((1.0, .7, .42)):
            box = [*self.s((cx - rx * f, cy - ry * f)), *self.s((cx + rx * f, cy + ry * f))]
            d.arc(box, 185, 355, fill=INK if k == 0 else INK_SOFT, width=LW if k == 0 else SS)
        for k in range(16):   # hachures down the eastern shoulder and the southern skirt
            a = math.radians(285 + k * 6.5)
            x1, y1 = self.s((cx + rx * math.cos(a), cy + ry * math.sin(a)))
            x2, y2 = self.s((cx + rx * 1.22 * math.cos(a), cy + ry * 1.22 * math.sin(a) + .15 * self.k))
            d.line([(x1, y1), (x2, y2)], fill=INK_SOFT, width=SS)

    def peak(self, d, x, y, size):
        """A mountain as on the player map: a jagged peak, its eastern face hatched."""
        lean = self.rng.uniform(-.25, .25) * size
        top = (x + lean, y - size * 1.25)
        left, right = (x - size, y), (x + size, y)
        shoulder = (x + lean + size * .35, y - size * .7)
        d.polygon([left, top, shoulder, right], fill=PARCHMENT)
        d.line([left, top, shoulder, right], fill=INK, width=LW, joint="curve")
        for j in range(1, 6):                           # shading down the eastern face
            t = j / 6
            a = (top[0] + (right[0] - top[0]) * t, top[1] + (right[1] - top[1]) * t)
            d.line([a, (a[0] - size * .28, a[1] + size * .12)], fill=INK_SOFT, width=SS)

    def marsh_tuft(self, d, x, y, size):
        for k, dy in enumerate((0, size * .35, size * .7)):
            off = (k % 2) * size * .4
            d.line([(x - size + off, y + dy), (x + size * .6 + off, y + dy)], fill=INK_SOFT, width=SS)
        for dx in (-size * .3, 0, size * .3):
            d.line([(x + dx, y - size * .1), (x + dx * 1.6, y - size * .8)], fill=INK, width=LT)

    def cottage(self, d, x, y, size):
        w, h = size * 1.3, size * .8
        d.rectangle([x - w / 2, y - h, x + w / 2, y], fill=PARCHMENT, outline=INK, width=LT)
        roof = [(x - w / 2 - size * .15, y - h), (x, y - h - size * .75), (x + w / 2 + size * .15, y - h)]
        d.polygon(roof, fill=PARCHMENT)
        d.line(roof, fill=INK, width=LW)
        for k in (1, 2):
            yy = y - h - size * .55 + k * size * .2
            d.line([(x - w * .1 * k, yy), (x + w * .1 * k, yy)], fill=INK_SOFT, width=SS)
        d.rectangle([x - size * .12, y - h * .55, x + size * .12, y], fill=INK)

    def tower(self, d, x, y, size, ruined=False):
        """A round tower; ruined ones have a broken, jagged top and fallen stones."""
        w, h = size * .9, size * 2.4
        top = y - h
        if ruined:
            jag = [(x - w / 2, top + size * .5), (x - w / 4, top + size * .1), (x, top + size * .6),
                   (x + w / 5, top), (x + w / 2, top + size * .35)]
            d.polygon([(x - w / 2, y)] + jag + [(x + w / 2, y)], fill=PARCHMENT)
            d.line([(x - w / 2, y), *jag, (x + w / 2, y)], fill=INK, width=LW)
            for k in range(3):     # fallen stones
                sx = x + w * (0.7 + k * .35)
                d.rectangle([sx, y - size * .25, sx + size * .3, y], fill=PARCHMENT, outline=INK, width=SS)
        else:
            d.rectangle([x - w / 2, top, x + w / 2, y], fill=PARCHMENT, outline=INK, width=LW)
            for k in range(3):     # battlements
                bx = x - w / 2 + k * w / 2.5
                d.rectangle([bx, top - size * .3, bx + w / 5, top], fill=PARCHMENT, outline=INK, width=SS)
        d.rectangle([x - size * .1, top + h * .45, x + size * .1, top + h * .62], fill=INK)   # a window

    def stone(self, d, x, y, size):
        d.polygon([(x - size * .3, y), (x - size * .2, y - size * 1.5), (x + size * .15, y - size * 1.6),
                   (x + size * .3, y)], fill=PARCHMENT, outline=INK)
        d.line([(x - size * .3, y), (x + size * .3, y)], fill=INK, width=LW)

    # ------------------------------------------------------------------ layers
    def _open_country(self, p) -> bool:
        g = self.g
        for key in ("forests", "marshes", "downs", "lakes", "mountains"):
            if any(self._inside(p, f["area"]) for f in g.get(key, [])):
                return False
        for pl in g.get("places", []):
            if math.dist(p, pl["at"]) < (1.4 if pl.get("kind") == "town" else 0.8) * self.k:
                return False
        for rd in g.get("roads", []) + g.get("streams", []) + g.get("rivers", []):
            if any(math.dist(p, q) < 0.35 * self.k for q in self._smooth(rd["points"], 4)):
                return False
        if any(math.dist(p, c) < 0.6 * self.k for c in g.get("copses", [])):
            return False
        for hl in g.get("hills", []):
            if math.dist(p, hl["center"]) < max(hl["radius"]) * 1.15:
                return False
        return True

    def render(self) -> Image.Image:
        img = parchment(self.w * SS, self.h * SS).convert("RGB")
        d = ImageDraw.Draw(img)
        g = self.g
        x0, y0, x1, y1 = g["bounds"]

        k = self.k
        y = y0 + 0.3 * k
        while y < y1:     # open country: grass strokes
            x = x0 + self.rng.uniform(0, .5) * k
            while x < x1:
                p = (x + self.rng.uniform(-.2, .2) * k, y + self.rng.uniform(-.15, .15) * k)
                if self.rng.random() < 0.55 and self._open_country(p):
                    sx, sy = self.s(p)
                    self.grass(d, sx, sy, self.rng.uniform(7, 11) * SS)
                x += self.rng.uniform(0.55, 0.9) * k
            y += 0.45 * k
        for pl in g.get("places", []):   # fields round the settlements (not round ruins, towers or stones)
            for _ in range({"town": 12, "village": 6, "hamlet": 3}.get(pl.get("kind", "village"), 0)):
                a = self.rng.uniform(0, 2 * math.pi)
                dist = self.rng.uniform(0.7, 1.6 if pl.get("kind") == "town" else 1.1) * k
                p = (pl["at"][0] + dist * math.cos(a), pl["at"][1] + dist * math.sin(a) * .8)
                near_road = any(math.dist(p, q) < 0.45 * k for rd in g.get("roads", []) for q in self._smooth(rd["points"], 4))
                if not near_road and not any(self._inside(p, f["area"]) for f in g.get("forests", [])):
                    cx, cy = self.s(p)
                    self.field(d, cx, cy, self.rng.uniform(14, 24) * SS, self.rng.uniform(8, 13) * SS,
                               self.rng.uniform(-.5, .5))

        for dn in g.get("downs", []):
            self.down_rows(d, dn["area"])
        for hl in g.get("hills", []):
            self.hill(d, hl["center"], hl["radius"])
        for mt in g.get("mountains", []):
            for p in self._scatter(mt["area"], 1.1 * k):        # big and small peaks, back to front
                x, y = self.s(p)
                self.peak(d, x, y, self.rng.choice((self.rng.uniform(18, 26), self.rng.uniform(28, 40))) * SS)
        for st in g.get("streams", []):
            pts = [self.s(p) for p in self._smooth(st["points"], 12)]
            d.line([(x + math.sin(i * .7) * 3 * SS, y) for i, (x, y) in enumerate(pts)], fill=INK, width=LW,
                   joint="curve")
        for rv in g.get("rivers", []):
            pts = [self.s(p) for p in self._smooth(rv["points"], 14)]
            wob = [(x + math.sin(i * .45) * 4 * SS, y + math.cos(i * .5) * 2 * SS) for i, (x, y) in enumerate(pts)]
            d.line(wob, fill=INK, width=4 * SS, joint="curve")
        for lk in g.get("lakes", []):
            poly = [self.s(p) for p in self._smooth(lk["area"] + [lk["area"][0]], 8)]
            d.polygon(poly, fill=(196, 186, 160))
            d.line(poly, fill=INK, width=LW, joint="curve")
            xs, ys = [p[0] for p in lk["area"]], [p[1] for p in lk["area"]]
            yy = min(ys) + 0.15 * k
            while yy < max(ys):
                xx = min(xs)
                while xx < max(xs):
                    if self._inside((xx, yy), lk["area"]) and self.rng.random() < 0.5:
                        a, b = self.s((xx, yy)), self.s((xx + 0.35 * k, yy))
                        d.line([a, b], fill=INK_SOFT, width=SS)
                    xx += 0.5 * k
                yy += 0.22 * k
        for m in g.get("marshes", []):
            for p in self._scatter(m["area"], 0.38 * k):
                x, y = self.s(p)
                self.marsh_tuft(d, x, y, self.rng.uniform(8, 12) * SS)
        for rd in g.get("roads", []):
            pts = [self.s(p) for p in self._smooth(rd["points"], 10)]
            outer, inner = (11 * SS, 6 * SS) if rd.get("width") == "main" else (7 * SS, 3 * SS)
            d.line(pts, fill=INK, width=outer, joint="curve")
            d.line(pts, fill=PARCHMENT, width=inner, joint="curve")
        for fo in g.get("forests", []):
            self.wood(d, fo["area"], 0.3 * k, fo.get("kind", "mixed"))
        for c in g.get("copses", []):
            self.copse(d, c)
        hd = g.get("hedge")
        if hd:   # the hedge and dike round Bree: a ring of small bushes
            cx, cy = hd["center"]
            rx, ry = hd["radius"]
            for k in range(0, 360, 7):
                x, y = self.s((cx + rx * math.cos(math.radians(k)), cy + ry * math.sin(math.radians(k))))
                d.ellipse([x - 4 * SS, y - 3 * SS, x + 4 * SS, y + 3 * SS], fill=PARCHMENT, outline=INK, width=SS)
        for pl in g.get("places", []):
            kind = pl.get("kind", "village")
            if kind in ("ruin", "tower", "stone"):
                x, y = self.s(pl["at"])
                if kind == "stone":
                    self.stone(d, x, y, 14 * SS)
                else:
                    self.tower(d, x, y, 14 * SS, ruined=kind == "ruin")
                continue
            n = {"town": 13, "village": 6, "hamlet": 3}.get(kind, 4)
            spread = {"town": .45, "village": .24, "hamlet": .15}.get(kind, .2)
            cx, cy = pl["at"]
            spots = sorted(((cx + self.rng.uniform(-spread, spread), cy + self.rng.uniform(-spread * .7, spread * .7))
                            for _ in range(n)), key=lambda p: p[1])
            for p in spots:
                x, y = self.s(p)
                self.cottage(d, x, y, self.rng.uniform(10, 13) * SS)

        img = img.resize((self.w, self.h), Image.LANCZOS)
        d = ImageDraw.Draw(img)
        self._labels(d)
        self._frame(d)
        return img.filter(ImageFilter.UnsharpMask(radius=1, percent=35, threshold=2))

    # ------------------------------------------------------------------ lettering and frame
    def _text(self, d, xy, text, font, fill, spacing=0, anchor="mm", halo=True):
        if spacing:
            text = (" " * spacing).join(text)
        if halo:
            d.text(xy, text, font=font, fill=PARCHMENT, anchor=anchor, stroke_width=5, stroke_fill=PARCHMENT)
        d.text(xy, text, font=font, fill=fill, anchor=anchor)

    def _overlap(self, box) -> float:
        """How badly a label box collides with labels already placed (and with the frame)."""
        m = self.margin * .6
        out = max(0, m - box[0]) + max(0, m - box[1]) + max(0, box[2] - (self.w - m)) + max(0, box[3] - (self.h - m))
        hit = 0.0
        for b in self._boxes:
            w = min(box[2], b[2]) - max(box[0], b[0])
            h = min(box[3], b[3]) - max(box[1], b[1])
            if w > 0 and h > 0:
                hit += w * h
        return hit + out * 400

    def _fit(self, d, cands, lines, font, fill, spacing=0, halo=True, line_gap=36):
        """Draw a label (one or more lines) at the first candidate spot where it collides with nothing,
        or else where it collides least. cands: [((x, y), anchor)]. Remembers the box it took."""
        lines = [(" " * spacing).join(t) if spacing else t for t in lines]
        best = None
        for (x, y), anchor in cands:
            boxes = [d.textbbox((x, y + k * line_gap), t, font=font, anchor=anchor) for k, t in enumerate(lines)]
            box = (min(b[0] for b in boxes) - 6, min(b[1] for b in boxes) - 4,
                   max(b[2] for b in boxes) + 6, max(b[3] for b in boxes) + 4)
            score = self._overlap(box)
            if best is None or score < best[0]:
                best = (score, (x, y), anchor, box)
            if score == 0:
                break
        _, (x, y), anchor, box = best
        for k, t in enumerate(lines):
            self._text(d, (x, y + k * line_gap), t, font, fill, anchor=anchor, halo=halo)
        self._boxes.append(box)

    def _labels(self, d):
        g = self.g
        self._boxes = []
        big, mid = _font("UncialAntiqua-Regular.ttf", 48), _font("UncialAntiqua-Regular.ttf", 32)
        small, fell = _font("UncialAntiqua-Regular.ttf", 24), _font("IMFellEnglish-Italic.ttf", 26)
        nudges = (0, -34, 34, -68, 68, -102, 102)

        def around(xy, base_dy=0):     # an area label: where it was asked for, else nudged up or down
            return [((xy[0], xy[1] + base_dy + n), "mm") for n in nudges]

        for ptr in g.get("pointers", []):          # pointers sit at the edges: drawn first, they keep their place
            x, y = self.px(ptr["at"])
            side = ptr.get("side", "east")
            vx, vy = {"west": (-1, 0), "east": (1, 0), "north": (0, -1), "south": (0, 1)}[side]
            if side in ("west", "east"):
                tip = (x + vx * 4, y)
                tail = (x - vx * 30, y)
                text_at, anchor = ((x + 40, y), "lm") if side == "west" else ((x - 40, y), "rm")
            else:
                tip, tail = (x, y + vy * 4), (x, y - vy * 30)
                text_at, anchor = (x + 16, y - vy * 18), "lm"
            d.line([tail, tip], fill=INK_SOFT, width=2)
            d.polygon([tip, (tip[0] - vx * 11 - vy * 6, tip[1] - vy * 11 - vx * 6),
                       (tip[0] - vx * 11 + vy * 6, tip[1] - vy * 11 + vx * 6)], fill=INK_SOFT)
            self._fit(d, [(text_at, anchor)], [ptr["text"]], fell, INK_SOFT)

        # places first, towns before the rest: under the mark, else above, right, left, further off
        for pl in sorted(g.get("places", []), key=lambda p: p.get("kind") != "town"):
            x, y = self.px(pl["at"])
            town = pl.get("kind") == "town"
            off = 50 if town else 32
            self._boxes.append((x - 14, y - 14, x + 14, y + 14))           # keep labels off the mark itself
            cands = [((x, y + off), "mm"), ((x, y - off), "mm"), ((x + 18, y), "lm"), ((x - 18, y), "rm"),
                     ((x, y + off + 30), "mm"), ((x, y - off - 30), "mm"), ((x + 18, y + 30), "lm"),
                     ((x - 18, y - 30), "rm"), ((x + 18, y - 30), "lm"), ((x - 18, y + 30), "rm")]
            self._fit(d, cands, [pl["name"].upper()], mid if town else small, INK, spacing=1)

        for fo in g.get("forests", []):
            if fo.get("name") and fo.get("label_at"):
                self._fit(d, around(self.px(fo["label_at"])), [fo["name"].upper()], mid, INK, spacing=1)
        for m in g.get("marshes", []):
            self._fit(d, around(self.px(m["label_at"])), m["name"].upper().split(), mid, INK, spacing=1)
        for lk in g.get("lakes", []):
            if lk.get("name"):
                xs, ys = [p[0] for p in lk["area"]], [p[1] for p in lk["area"]]
                at = lk.get("label_at") or ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
                self._fit(d, around(self.px(at)), [lk["name"].upper()], small, INK, spacing=1)
        for mt in g.get("mountains", []):      # a range's name in red capitals, like the player map
            if mt.get("name") and mt.get("label", True) is not False:
                xs, ys = [p[0] for p in mt["area"]], [p[1] for p in mt["area"]]
                at = mt.get("label_at") or ((min(xs) + max(xs)) / 2, max(ys) + 0.6 * self.k)
                self._fit(d, around(self.px(at)), [mt["name"].upper()], mid, RED, spacing=2)
        for dn in g.get("downs", []):
            if dn.get("label_at"):
                self._fit(d, around(self.px(dn["label_at"])), [dn["name"].upper()], big if dn.get("region") else mid,
                          RED, spacing=1)
        for hl in g.get("hills", []):
            if hl.get("name") and hl.get("label", True) is not False:
                cx, cy = hl["center"]
                xy = self.px((cx, cy - hl["radius"][1] - 0.35 * self.k))
                self._fit(d, around(xy), [hl["name"].upper()], small, INK, spacing=1)
        for rv in g.get("rivers", []):
            if rv.get("name"):
                pts = rv["points"]
                at = rv.get("label_at") or pts[len(pts) // 2]
                xy = self.px((at[0] + 0.3 * self.k, at[1] - 0.25 * self.k))
                self._fit(d, around(xy), [rv["name"]], fell, INK_SOFT)
        for rd in g.get("roads", []):
            if rd.get("name") and rd.get("label_at"):
                x, y = self.px(rd["label_at"])
                if rd.get("vertical"):
                    for k, ch in enumerate(rd["name"]):
                        d.text((x, y + k * 24), ch, font=fell, fill=INK_SOFT, anchor="mm")
                else:
                    self._fit(d, around((x, y)), [rd["name"]], fell, INK_SOFT, halo=False)

    def _frame(self, d):
        m = self.margin
        d.rectangle([m * .35, m * .35, self.w - m * .35, self.h - m * .35], outline=INK, width=3)
        d.rectangle([m * .5, m * .5, self.w - m * .5, self.h - m * .5], outline=INK, width=1)
        title = self.g.get("title", "").upper()
        f = _font("UncialAntiqua-Regular.ttf", 66)
        tw = d.textlength(title, font=f) + 90
        x, y = m + 30, m + 20      # top left, clear of roads and labels
        d.rectangle([x, y, x + tw, y + 100], fill=PARCHMENT, outline=INK, width=3)
        d.rectangle([x + 8, y + 8, x + tw - 8, y + 92], outline=INK, width=1)
        d.text((x + tw / 2, y + 52), title, font=f, fill=RED, anchor="mm")
        cx, cy = self.w - m - 70, m + 100
        for a, ln in ((0, 62), (90, 42), (180, 42), (270, 42)):
            r = math.radians(a - 90)
            tip = (cx + ln * math.cos(r), cy + ln * math.sin(r))
            s1 = (cx + 9 * math.cos(r + 1.57), cy + 9 * math.sin(r + 1.57))
            s2 = (cx + 9 * math.cos(r - 1.57), cy + 9 * math.sin(r - 1.57))
            d.polygon([tip, s1, (cx, cy), s2], fill=INK if a == 0 else PARCHMENT, outline=INK)
        d.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], outline=INK, width=1)
        d.text((cx, cy - 82), "N", font=_font("UncialAntiqua-Regular.ttf", 32), fill=RED, anchor="mm")
        bar = next((n for n in (5, 10, 20, 50, 100, 200) if n * self.ppm >= 150), 200)   # 5 miles at local scales
        step = bar / 5 * self.ppm
        sx, sy = self.w - m - 40 - 5 * step, self.h - m - 46
        for k in range(5):
            d.rectangle([sx + k * step, sy, sx + (k + 1) * step, sy + 10],
                        fill=INK if k % 2 == 0 else PARCHMENT, outline=INK)
        fell = _font("IMFellEnglish-Italic.ttf", 24)
        d.text((sx, sy - 8), "0", font=fell, fill=INK, anchor="mb")
        d.text((sx + 5 * step, sy - 8), f"{bar} miles", font=fell, fill=INK, anchor="mb")


def load_geo(region: str) -> dict:
    return yaml.safe_load((cfg.load().lore / "maps" / f"{region}.yaml").read_text(encoding="utf-8"))


def render_geo(geo: dict, out: Path) -> Path:
    img = Region(geo).render()
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=90)
    return out


def render_region(region: str, out: Path) -> Path:
    return render_geo(load_geo(region), out)


# ---------------------------------------------------------------------- session maps (static, for Obsidian)
def _point_back(path: list, dist: float) -> tuple:
    """The point `dist` back along a path from its end (or its start, if the path is shorter)."""
    left = dist
    for a, b in zip(reversed(path[:-1]), reversed(path[1:])):
        seg = math.dist(a, b)
        if seg >= left and seg:
            t = left / seg
            return (b[0] + (a[0] - b[0]) * t, b[1] + (a[1] - b[1]) * t)
        left -= seg
    return tuple(path[0])


def session_map(base: Path, map_size, legs: list[dict], places: list[dict], out: Path, title: str,
                min_size=(1100, 760), out_width: int = 1600, day_tags: bool = True) -> Path:
    """Draw moves on a map image, cropped to where they happened, in the style of a planned journey: a red
    dashed route on a pale band, an arrowhead, gold seals at the stops, one small day tag per day.

    legs: [{path: [[x, y], ...], day, ...}] in the map's pixels; places: [{name, at, state, builtin}]."""
    img = Image.open(base).convert("RGB")
    W, H = img.size
    pts = [p for l in legs for p in l["path"]] + [p["at"] for p in places]
    if not pts:
        raise ValueError("nothing to draw")
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    w = max(min_size[0], (max(xs) - min(xs)) * 1.35)
    h = max(min_size[1], (max(ys) - min(ys)) * 1.35, w * 0.62)
    w = max(w, h / 0.62)
    x0, y0 = max(0, min(W - w, cx - w / 2)), max(0, min(H - h, cy - h / 2))
    x1, y1 = min(W, x0 + w), min(H, y0 + h)
    crop = img.crop((int(x0), int(y0), int(x1), int(y1)))
    scale = out_width / crop.width
    crop = crop.resize((out_width, int(crop.height * scale)), Image.LANCZOS)
    S = lambda p: ((p[0] - x0) * scale, (p[1] - y0) * scale)  # noqa: E731
    k = out_width / 1600                       # line widths and type follow the picture's size
    d = ImageDraw.Draw(crop)
    fell = _font("IMFellEnglish-Italic.ttf", max(18, int(24 * k)))
    tag_font = _font("UncialAntiqua-Regular.ttf", max(15, int(19 * k)))
    GOLD = (242, 193, 78)
    PALE = (246, 236, 210)
    taken: list[tuple] = []                     # boxes already used by seals, tags and names

    def dashed(path, color, width, dash, gap):
        for a, b in zip(path, path[1:]):
            dist = math.dist(a, b)
            t = 0.0
            while t < dist:
                t2 = min(dist, t + dash)
                p1 = (a[0] + (b[0] - a[0]) * t / dist, a[1] + (b[1] - a[1]) * t / dist)
                p2 = (a[0] + (b[0] - a[0]) * t2 / dist, a[1] + (b[1] - a[1]) * t2 / dist)
                d.line([p1, p2], fill=color, width=width)
                t += dash + gap

    # the routes: a pale band first (so the red reads on any map), then the dashes and an arrowhead
    paths = [[S(p) for p in l["path"]] for l in legs]
    for path in paths:
        if len(path) >= 2:
            d.line(path, fill=PALE, width=max(13, int(15 * k)), joint="curve")
    for path in paths:
        if len(path) < 2:
            continue
        dashed(path, RED, max(5, int(6 * k)), max(16, 20 * k), max(9, 11 * k))

    # the stops: gold seals, the current place larger; names for places the map doesn't already name
    for p in places:
        x, y = S(p["at"])
        r = max(11, 13 * k) if p.get("state") == "current" else max(9, 10 * k)
        d.ellipse([x - r, y - r, x + r, y + r], fill=GOLD, outline=RED, width=max(2, int(3 * k)))
        taken.append((x - r, y - r, x + r, y + r))

    # arrowheads last, big and pointing at the destination seal from just outside it
    for path in paths:
        if len(path) < 2:
            continue
        tip, back = _point_back(path, max(14, 16 * k)), _point_back(path, max(70, 80 * k))
        ang = math.atan2(tip[1] - back[1], tip[0] - back[0])
        r, spread = max(46, 54 * k), .48
        wing = [(tip[0] - r * math.cos(ang - spread), tip[1] - r * math.sin(ang - spread)),
                (tip[0] - r * .62 * math.cos(ang), tip[1] - r * .62 * math.sin(ang)),
                (tip[0] - r * math.cos(ang + spread), tip[1] - r * math.sin(ang + spread))]
        d.polygon([tip, *wing], fill=RED, outline=PALE, width=max(2, int(3 * k)))
        xs_, ys_ = [tip[0]] + [w[0] for w in wing], [tip[1]] + [w[1] for w in wing]
        taken.append((min(xs_), min(ys_), max(xs_), max(ys_)))
    for p in places:
        if p.get("builtin"):
            continue
        x, y = S(p["at"])
        tw = d.textlength(p["name"], font=fell)
        for bx, anchor in ((x + 16 * k, "lm"), (x - 16 * k, "rm")):
            box = (bx, y - 15 * k, bx + tw, y + 15 * k) if anchor == "lm" else (bx - tw, y - 15 * k, bx, y + 15 * k)
            if all(box[2] < q[0] or box[0] > q[2] or box[3] < q[1] or box[1] > q[3] for q in taken):
                d.text((bx, y), p["name"], font=fell, fill=INK, anchor=anchor, stroke_width=4, stroke_fill=PARCHMENT)
                taken.append(box)
                break

    # one day tag per day, on that day's first move, where it doesn't cover anything
    days_seen = set() if day_tags else {l.get("day") for l in legs}
    for l, path in zip(legs, paths):
        if l.get("day") in days_seen or len(path) < 2:
            continue
        days_seen.add(l.get("day"))
        text = f"Day {l.get('day')}"
        tw = d.textlength(text, font=tag_font) + 16 * k
        th = 30 * k
        length = sum(math.dist(a, b) for a, b in zip(path, path[1:]))
        placed = False
        for frac in (0.5, 0.35, 0.65, 0.2, 0.8):
            target, run = frac * length, 0.0
            for a, b in zip(path, path[1:]):
                seg = math.dist(a, b)
                if run + seg >= target and seg:
                    t = (target - run) / seg
                    mx, my = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                    break
                run += seg
            else:
                mx, my = path[-1]
            for ox, oy in ((0, -th), (0, th), (tw * .7, 0), (-tw * .7, 0)):
                box = (mx + ox - tw / 2, my + oy - th / 2, mx + ox + tw / 2, my + oy + th / 2)
                if all(box[2] < q[0] or box[0] > q[2] or box[3] < q[1] or box[1] > q[3] for q in taken):
                    d.rounded_rectangle(box, radius=int(6 * k), fill=RED, outline=PALE, width=max(1, int(2 * k)))
                    d.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2 + 1), text, font=tag_font, fill=PALE,
                           anchor="mm")
                    taken.append(box)
                    placed = True
                    break
            if placed:
                break

    # title cartouche
    tf = _font("UncialAntiqua-Regular.ttf", max(26, int(40 * k)))
    tw = d.textlength(title, font=tf) + 60 * k
    th = 68 * k
    by, bx = crop.height - th - 24 * k, crop.width - tw - 24 * k      # bottom right
    d.rectangle([bx, by, bx + tw, by + th], fill=PARCHMENT, outline=INK, width=3)
    d.rectangle([bx + 6, by + 6, bx + tw - 6, by + th - 6], outline=INK, width=1)
    d.text((bx + tw / 2, by + th / 2), title, font=tf, fill=RED, anchor="mm")
    out.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out, quality=88)
    return out
