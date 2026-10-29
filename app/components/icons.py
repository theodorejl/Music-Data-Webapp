"""Brush-stroke icons and the logo.

Each icon is drawn with a few strokes of a brush, the way a character is written: a stroke lands
with a little press, runs along a smooth curve and lifts off in a taper; a dot is a small
teardrop. Two to five strokes per icon, so it stays a sign you read at a glance (a house, a
podium, a sprout, headphones…). Every icon is a filled SVG path on a 24 × 24 grid, used as a CSS
mask so it takes the colour of the text around it.

Streamlit draws its icons with the Material Symbols font: the page script tags each of them with
`data-ds-icon` and the CSS below swaps the glyph for the brush drawing (see theme.background()).
"""

from __future__ import annotations

import base64
import math
from functools import lru_cache

Point = tuple[float, float]


def _spline(points: list[Point], steps: int = 14) -> list[Point]:
    """A Catmull-Rom curve through the points."""
    if len(points) == 2:
        (x0, y0), (x1, y1) = points
        return [(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps) for i in range(steps + 1)]
    pts = [points[0]] + points + [points[-1]]
    out: list[Point] = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for k in range(steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                   + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in range(2)))
    out.append(points[-1])
    return out


def stroke(points: list[Point], width: float = 2.4, lift: float = .45, press: float = .16, seed: int = 0) -> str:
    """A brush stroke through the points: a press at the start, a taper over the last `lift`
    of its length. Returns an SVG path."""
    line = _spline(points)
    seg = [math.dist(line[i], line[i + 1]) for i in range(len(line) - 1)]
    total = sum(seg) or 1.0
    acc, left, right = 0.0, [], []
    for i, (x, y) in enumerate(line):
        t = acc / total
        if i < len(seg):
            acc += seg[i]
        a, b = line[max(0, i - 1)], line[min(len(line) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / n, dx / n
        land = .62 + .38 * min(1.0, t / press) ** .6 + .18 * math.exp(-((t - press) / .09) ** 2)
        off = max(0.0, t - (1 - lift)) / lift
        w = width * land * (1 - .9 * off ** 1.5) * (1 + .05 * math.sin(t * 11 + seed))
        left.append((x + nx * w / 2, y + ny * w / 2))
        right.append((x - nx * w / 2, y - ny * w / 2))
    (sx, sy), (ex, ey) = line[0], line[-1]
    d = f"M{left[0][0]:.2f} {left[0][1]:.2f}"
    d += "".join(f"L{x:.2f} {y:.2f}" for x, y in left[1:])
    d += f"Q{ex + (ex - line[-2][0]) * .6:.2f} {ey + (ey - line[-2][1]) * .6:.2f} {right[-1][0]:.2f} {right[-1][1]:.2f}"
    d += "".join(f"L{x:.2f} {y:.2f}" for x, y in reversed(right[:-1]))
    d += f"Q{sx - (line[1][0] - sx) * 1.4:.2f} {sy - (line[1][1] - sy) * 1.4:.2f} {left[0][0]:.2f} {left[0][1]:.2f}Z"
    return d


def dot(x: float, y: float, r: float = 1.5, angle: float = 35) -> str:
    """A brush dot: a small teardrop."""
    a = math.radians(angle)
    ux, uy = math.cos(a), math.sin(a)
    tip = (x - ux * r * 1.5, y - uy * r * 1.5)
    pts = []
    for k in range(13):
        th = math.radians(-100 + k * 200 / 12)
        px, py = r * math.cos(th), r * .92 * math.sin(th)
        pts.append((x + px * ux - py * uy, y + px * uy + py * ux))
    d = f"M{tip[0]:.2f} {tip[1]:.2f}"
    d += "".join(f"L{px:.2f} {py:.2f}" for px, py in pts)
    return d + "Z"


def arc(cx: float, cy: float, r: float, a0: float, a1: float, n: int = 9) -> list[Point]:
    """Points on a circle from angle a0 to a1 (degrees, clockwise on screen)."""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1))),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1)))) for i in range(n)]


# --- the icons (24 × 24) -------------------------------------------------------------------------

def _icons() -> dict[str, list[str]]:
    S = stroke
    return {
        # a roof of two strokes and the walls standing on the ground
        "home": [S([(2.8, 12.2), (7.5, 7.6), (12, 3.6)], 2.6, .25), S([(12, 3.6), (16.6, 7.8), (21.2, 12)], 2.4, .5, seed=2),
                 S([(6.6, 11.6), (6.4, 16.4), (7, 20.2), (12.2, 20.4), (17.4, 20.1), (17.6, 15.5), (17.4, 11.6)], 2.3, .3, seed=3)],
        # a podium: three strokes of three heights
        "tops": [S([(5.4, 13.4), (5.4, 20.4)], 3, .35), S([(12, 4.6), (12, 20.4)], 3.2, .3, seed=1),
                 S([(18.6, 9.4), (18.6, 20.4)], 3, .35, seed=2)],
        # a wave
        "rhythms": [S([(2.4, 12.6), (5.4, 6.6), (9, 12), (12.4, 18.2), (16, 12.4), (19.2, 7.2), (21.6, 9.6)], 2.4, .35)],
        # a sprout: what is new in your music
        "discoveries": [S([(11.6, 21.2), (12.2, 15.4), (11.8, 10)], 2.5, .3),
                        S([(12, 12.8), (14.6, 8.2), (19.6, 5.4)], 2.4, .55, seed=4),
                        S([(11.8, 14.6), (9, 11.4), (4.6, 10.4)], 2, .6, seed=6)],
        # headphones
        "foryou": [S([(4.8, 15.2), (5.4, 8.6), (12, 4.2), (18.6, 8.6), (19.2, 15.2)], 2.3, .25),
                   S([(5.2, 13.6), (5.2, 20.2)], 3.6, .35, seed=2), S([(18.8, 13.6), (18.8, 20.2)], 3.6, .35, seed=3)],
        # a camera: the body and its lens
        "insta": [S([(3.8, 7.4), (3.4, 14), (4, 19.6), (12, 20), (20, 19.6), (20.4, 13), (19.8, 7.2), (12, 6.8), (4.6, 7.2)], 2.1, .2),
                  S(arc(12, 13.4, 3.6, -120, 210, 11), 2, .5, seed=5), dot(17, 9.8, 1, 30)],
        # an ensō and a planet: the universe of genres
        "universe": [S(arc(12, 12, 8.6, -150, 175, 15), 2.6, .45), dot(14.2, 10.2, 2.1, 40)],
        # a sparkle: the recaps
        "wrapped": [S([(12, 2.8), (12.4, 8.6), (12, 21.2)], 2.4, .5), S([(2.8, 12.2), (9.2, 11.6), (21.2, 12)], 2.2, .5, seed=2),
                    dot(18.2, 5.4, 1.2, 60), dot(5.8, 18.4, 1, 20)],
        # three books, the last one leaning
        "library": [S([(5.6, 4), (5.6, 20.2)], 2.8, .2), S([(10.4, 4.6), (10.4, 20.2)], 2.8, .2, seed=2),
                    S([(14.4, 5.4), (17, 12.6), (19.6, 19.8)], 2.6, .25, seed=3), S([(3, 21), (21, 20.8)], 1.6, .5, seed=4)],
        # a clock
        "history": [S(arc(12, 12, 8.6, -100, 245, 15), 2.3, .4), S([(12, 6.8), (12, 12.4), (15.8, 14.6)], 2.1, .35, seed=3)],
        # two sliders
        "settings": [S([(2.8, 7.6), (21.2, 7.4)], 1.8, .5), S([(2.8, 16.4), (21.2, 16.2)], 1.8, .5, seed=2),
                     dot(8.6, 7.5, 2.4, 0), dot(15.6, 16.3, 2.4, 180)],
        # a magnifying glass (the logo's sign)
        "search": [S(arc(10.2, 10.2, 6.4, -160, 175, 13), 2.2, .4), S([(15, 15), (20.8, 20.8)], 2.8, .45, seed=2)],
        # renew: a stroke going round, a hook at its end
        "sync": [S(arc(12, 12, 8, -40, 270, 15), 2.2, .3), S([(17.4, 3.8), (18.4, 6.8), (15.4, 7.6)], 1.9, .4, seed=2)],
        "download": [S([(12, 3), (12, 15.4)], 2.4, .25), S([(6.8, 10.4), (12, 15.8), (17.2, 10.4)], 2.1, .3, seed=2),
                     S([(3.6, 20.4), (20.4, 20.2)], 2, .5, seed=3)],
        "table": [S([(3.6, 4.2), (3.4, 12), (3.8, 20), (12, 20.2), (20.2, 19.8), (20.4, 12), (20, 4), (12, 3.8), (4.4, 4.2)], 1.9, .2),
                  S([(4, 12), (20, 11.8)], 1.6, .4, seed=2), S([(12, 4.4), (12, 19.6)], 1.6, .4, seed=3)],
        "pdf": [S([(5.2, 3.4), (5, 12), (5.4, 20.6), (12, 20.6), (18.8, 20.4), (18.8, 9.6), (13.6, 3.4), (5.8, 3.4)], 1.9, .2),
                S([(8.6, 12.4), (15.4, 12.2)], 1.6, .5, seed=2), S([(8.6, 16.2), (13.4, 16)], 1.6, .5, seed=3)],
        "arrow": [S([(3, 12.2), (12, 11.8), (20.6, 12)], 2.2, .3), S([(14.2, 5.8), (20.6, 12), (14.2, 18.2)], 2, .35, seed=2)],
        "arrow_back": [S([(21, 12.2), (12, 11.8), (3.4, 12)], 2.2, .3), S([(9.8, 5.8), (3.4, 12), (9.8, 18.2)], 2, .35, seed=2)],
        "arrow_out": [S([(4.6, 19.4), (12, 12), (19.2, 4.8)], 2.2, .3), S([(9.6, 4.6), (19.2, 4.8), (19.4, 14.4)], 2, .35, seed=2)],
        "check": [S([(3.6, 12.6), (9.2, 18.6), (20.6, 5.6)], 2.6, .45)],
        "close": [S([(5, 5), (19, 19)], 2.3, .45), S([(19, 5), (5, 19)], 2.3, .45, seed=2)],
        "chevron": [S([(5.4, 9), (12, 15.6), (18.6, 9)], 2.2, .4)],
        "queue": [S([(3, 6.4), (16, 6.2)], 2, .45), S([(3, 11.6), (14, 11.4)], 2, .45, seed=2), S([(3, 16.8), (10, 16.6)], 2, .45, seed=3),
                  S([(17.4, 20), (17.6, 11.2), (21.4, 9.6)], 2.1, .4, seed=4), dot(15.6, 19.6, 2.2, 200)],
        "playlist_add": [S([(3, 6.4), (15, 6.2)], 2, .45), S([(3, 11.6), (15, 11.4)], 2, .45, seed=2), S([(3, 16.8), (9.6, 16.6)], 2, .45, seed=3),
                         S([(17.6, 12), (17.6, 21)], 2.2, .4, seed=4), S([(13.2, 16.6), (22, 16.4)], 2.2, .4, seed=5)],
        "delete": [S([(3.6, 6.4), (20.4, 6.2)], 2, .45), S([(9.4, 3.4), (14.6, 3.4)], 1.8, .5, seed=2),
                   S([(5.8, 7), (6.8, 20.4), (12, 20.8), (17.2, 20.4), (18.2, 7)], 2.1, .3, seed=3)],
        "person": [S(arc(12, 8, 4.2, -110, 230, 11), 2.2, .4), S([(4, 21), (5.6, 16), (12, 14.4), (18.4, 16), (20, 21)], 2.3, .35, seed=2)],
        "album": [S(arc(12, 12, 8.8, -140, 200, 15), 2.4, .4), S(arc(12, 12, 4.4, 20, 250, 9), 1.5, .5, seed=2), dot(12, 12, 1.3, 0)],
        "play": [S([(7.4, 4), (7.2, 12), (7.6, 20), (14.4, 16), (19.6, 12), (14, 8), (8, 4.4)], 2.4, .2)],
        "pause": [S([(8, 4.6), (8, 19.4)], 3.4, .25), S([(16, 4.6), (16, 19.4)], 3.4, .25, seed=2)],
    }


# Material Symbols names Streamlit renders -> brush icon.
MATERIAL = {
    "home": "home", "trophy": "tops", "graphic_eq": "rhythms", "explore": "discoveries", "headphones": "foryou",
    "photo_camera": "insta", "blur_on": "universe", "auto_awesome": "wrapped", "library_music": "library",
    "history": "history", "tune": "settings", "search": "search", "sync": "sync", "download": "download",
    "table_view": "table", "picture_as_pdf": "pdf", "arrow_forward": "arrow", "arrow_back": "arrow_back",
    "arrow_outward": "arrow_out", "check": "check", "close": "close", "expand_more": "chevron",
    "keyboard_arrow_down": "chevron", "queue_music": "queue", "playlist_add": "playlist_add", "delete": "delete",
    "person": "person", "album": "album", "play_arrow": "play", "pause": "pause",
}


def svg(name: str, color: str = "#000") -> str:
    paths = "".join(f"<path d='{d}'/>" for d in _icons()[name])
    return f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='{color}'>{paths}</svg>"


def uri(name: str, color: str = "#000") -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg(name, color).encode()).decode()


@lru_cache(maxsize=1)
def css() -> str:
    """One CSS variable per icon (--ico-<name>), for masks."""
    return ":root{" + "".join(f"--ico-{n}:url(\"{uri(n)}\");" for n in _icons()) + "}"


# --- the logo: a record that is the lens of a magnifying glass ---------------------------------------

def logo_svg(size: int = 64, color: str = "#1c2230") -> str:
    """Four strokes: the record (an ensō), two grooves that turn slowly, and the handle that makes
    it a magnifying glass looking for music."""
    disc = stroke(arc(26, 26, 19, -150, 182, 17), 4.8, .4)
    g1 = stroke(arc(26, 26, 12.6, 150, 390, 13), 2.2, .5, seed=3)
    g2 = stroke(arc(26, 26, 7.4, -30, 170, 10), 2, .55, seed=5)
    handle = stroke([(40.2, 40.2), (49, 49), (57.6, 57.6)], 6.4, .38, seed=2)
    spin = ("<animateTransform attributeName='transform' type='rotate' from='0 26 26' to='360 26 26' "
            "dur='{d}s' repeatCount='indefinite'/>")
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64' width='{size}' height='{size}' fill='{color}'>"
            f"<path d='{disc}'/><path d='{handle}'/><g><path d='{g1}'/>{spin.format(d=9)}</g>"
            f"<g><path d='{g2}'/>{spin.format(d=6)}</g><circle cx='26' cy='26' r='2.2'/></svg>")
