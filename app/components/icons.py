"""Icons and the logo: geometric strokes in the spirit of a written character.

Each sign is built from a few separate strokes, the way a character is written: straight lines
and true circular arcs, of an even width with round ends, that stop just short of one another at
their joints. The only organic touch is a gentle taper at the end of each stroke, where the pen
lifts. Every icon is a filled SVG path on a 24 × 24 grid, used as a CSS mask so it takes the
colour of the text around it.

Streamlit draws its icons with the Material Symbols font: the page script tags each of them with
`data-ds-icon` and the CSS swaps the glyph for the drawing (see theme.background()).
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


def stroke(points: list[Point], width: float = 2.1, lift: float = .3, end: float = .6) -> str:
    """A stroke through the points: an even width with a round start, then a gentle taper over
    the last `lift` of its length down to `end` × the width, and a round end. Returns an SVG path."""
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
        u = min(1.0, max(0.0, (t - (1 - lift)) / lift))
        w = width * (1 - (1 - end) * u * u * (3 - 2 * u))
        left.append((x + nx * w / 2, y + ny * w / 2))
        right.append((x - nx * w / 2, y - ny * w / 2))

    def cap(p: Point, q: Point, w: float) -> Point:
        """Control point of a round cap at p, for a stroke arriving from q."""
        dx, dy = p[0] - q[0], p[1] - q[1]
        n = math.hypot(dx, dy) or 1.0
        return p[0] + dx / n * w, p[1] + dy / n * w

    ce = cap(line[-1], line[-2], width * end)
    cs = cap(line[0], line[1], width)
    d = f"M{left[0][0]:.2f} {left[0][1]:.2f}" + "".join(f"L{x:.2f} {y:.2f}" for x, y in left[1:])
    d += f"Q{ce[0]:.2f} {ce[1]:.2f} {right[-1][0]:.2f} {right[-1][1]:.2f}"
    d += "".join(f"L{x:.2f} {y:.2f}" for x, y in reversed(right[:-1]))
    return d + f"Q{cs[0]:.2f} {cs[1]:.2f} {left[0][0]:.2f} {left[0][1]:.2f}Z"


def dot(x: float, y: float, r: float = 1.5, angle: float = 0) -> str:
    """A round dot."""
    return f"M{x - r:.2f} {y:.2f}a{r:.2f} {r:.2f} 0 1 0 {2 * r:.2f} 0a{r:.2f} {r:.2f} 0 1 0 {-2 * r:.2f} 0Z"


def arc(cx: float, cy: float, r: float, a0: float, a1: float, n: int = 9) -> list[Point]:
    """Points on a circle from angle a0 to a1 (degrees, clockwise on screen)."""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1))),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1)))) for i in range(n)]


# --- the icons (24 × 24) -------------------------------------------------------------------------

def _icons() -> dict[str, list[str]]:
    S, A = stroke, arc
    return {
        # a roof of two strokes meeting at the top, the walls, the ground
        "home": [S([(3, 11.4), (11.4, 3.8)]), S([(12.6, 3.8), (21, 11.4)]), S([(6, 11.8), (6, 20)]),
                 S([(7.2, 20.4), (16.8, 20.4)]), S([(18, 20), (18, 11.8)])],
        # a podium: three bars of three heights
        "tops": [S([(5.6, 20.4), (5.6, 13)], 2.6), S([(12, 20.4), (12, 4.6)], 2.6), S([(18.4, 20.4), (18.4, 9.2)], 2.6)],
        # a wave of two half circles
        "rhythms": [S(A(7.6, 12, 4.4, 180, 360, 9)), S(A(16.4, 12, 4.4, 180, 0, 9))],
        # a sprout: what is new in your music
        "discoveries": [S([(12, 21), (12, 11)]), S(A(19, 12.6, 7, 180, 265, 7)), S(A(5.6, 14.8, 6.4, 0, -80, 7))],
        # headphones
        "foryou": [S(A(12, 13.4, 8, 180, 360, 11)), S([(4, 14.6), (4, 20)], 3.2, end=.8), S([(20, 14.6), (20, 20)], 3.2, end=.8)],
        # a camera: its body and its lens
        "insta": [S([(5.4, 6.8), (18.6, 6.8)]), S([(20.2, 8.2), (20.2, 18.8)]), S([(18.6, 20.2), (5.4, 20.2)]),
                  S([(3.8, 18.8), (3.8, 8.2)]), S(A(12, 13.6, 3.7, -90, 250, 11)), dot(16.9, 9.9, 1.05)],
        # an open circle and a planet: the universe of genres
        "universe": [S(A(12, 12, 8.6, -60, 262, 15), 2.3), dot(14.6, 9.6, 2.2)],
        # a spark: the recaps
        "wrapped": [S([(12, 3.4), (12, 20.6)]), S([(3.4, 12), (20.6, 12)]), dot(18.4, 5.6, 1.25), dot(5.6, 18.4, 1)],
        # three books, the last one leaning, on a shelf
        "library": [S([(5.8, 20), (5.8, 4)], 2.4), S([(10.4, 20), (10.4, 4)], 2.4), S([(14.6, 19.8), (18.8, 5)], 2.4),
                    S([(3, 21.2), (21, 21.2)], 1.6)],
        # a clock
        "history": [S(A(12, 12, 8.6, -80, 255, 15)), S([(12, 12.4), (12, 6.8)]), S([(12.6, 12.8), (16.2, 15)])],
        # two sliders
        "settings": [S([(3, 7.6), (21, 7.6)], 1.8), S([(3, 16.4), (21, 16.4)], 1.8), dot(8.8, 7.6, 2.5), dot(15.2, 16.4, 2.5)],
        # a magnifying glass (the logo's sign)
        "search": [S(A(10.2, 10.2, 6.4, 50, 400, 15)), S([(15, 15), (21, 21)], 2.6)],
        # renew: a circle that goes round, its arrow at the end
        "sync": [S(A(12, 12, 8, 20, 300, 15)), S([(16.3, 5.2), (16.6, 1.8)], 1.9), S([(16.3, 5.2), (19.7, 5.6)], 1.9)],
        "download": [S([(12, 3), (12, 15)]), S([(7, 10.6), (11.4, 15.2)]), S([(17, 10.6), (12.6, 15.2)]), S([(4, 20.4), (20, 20.4)])],
        "table": [S([(5, 4), (19, 4)]), S([(20.2, 5.2), (20.2, 18.8)]), S([(19, 20), (5, 20)]), S([(3.8, 18.8), (3.8, 5.2)]),
                  S([(5, 12), (19, 12)], 1.6), S([(12, 5.2), (12, 18.8)], 1.6)],
        "pdf": [S([(5, 4.6), (5, 20.4)]), S([(6.2, 20.6), (18.8, 20.6)]), S([(19, 19.4), (19, 9.4)]), S([(18.4, 8.4), (13.6, 3.6)]),
                S([(12.4, 3.4), (6.2, 3.4)]), S([(8.6, 12.4), (15.4, 12.4)], 1.6), S([(8.6, 16.2), (13.2, 16.2)], 1.6)],
        "arrow": [S([(3, 12), (20.4, 12)]), S([(14.4, 5.8), (20, 11.4)]), S([(14.4, 18.2), (20, 12.6)])],
        "arrow_back": [S([(21, 12), (3.6, 12)]), S([(9.6, 5.8), (4, 11.4)]), S([(9.6, 18.2), (4, 12.6)])],
        "arrow_out": [S([(5, 19), (18.4, 5.6)]), S([(9.6, 5), (18.6, 5)]), S([(19, 5.4), (19, 14.4)])],
        "check": [S([(4, 12.6), (9, 17.6)], 2.4), S([(10, 17.8), (20.6, 6)], 2.4)],
        "close": [S([(5.4, 5.4), (18.6, 18.6)]), S([(18.6, 5.4), (5.4, 18.6)])],
        "chevron": [S([(5.6, 9.2), (11.4, 15)]), S([(18.4, 9.2), (12.6, 15)])],
        "queue": [S([(3, 6.4), (15.6, 6.4)]), S([(3, 11.6), (13.4, 11.6)]), S([(3, 16.8), (10, 16.8)]),
                  S([(18.4, 19), (18.4, 8.4)], 1.9), S([(19, 8.2), (21.6, 9.8)], 1.9), dot(16.4, 19, 2.1)],
        "playlist_add": [S([(3, 6.4), (15, 6.4)]), S([(3, 11.6), (15, 11.6)]), S([(3, 16.8), (9.6, 16.8)]),
                         S([(17.6, 12.2), (17.6, 21)]), S([(13.2, 16.6), (22, 16.6)])],
        "delete": [S([(3.4, 6.4), (20.6, 6.4)]), S([(9.6, 3.4), (14.4, 3.4)], 1.8), S([(6, 7.8), (7, 20.4)]),
                   S([(8, 20.6), (16, 20.6)]), S([(18, 7.8), (17, 20.4)])],
        "person": [S(A(12, 8, 4.2, -90, 255, 11)), S(A(12, 23.4, 8.6, 195, 345, 9))],
        "album": [S(A(12, 12, 8.8, -70, 262, 15)), S(A(12, 12, 4.4, 20, 250, 9), 1.6), dot(12, 12, 1.25)],
        "play": [S([(7.4, 4.6), (7.4, 19.4)]), S([(8.4, 19.6), (19.6, 12.6)]), S([(19.6, 11.4), (8.4, 4.4)])],
        "pause": [S([(8, 5), (8, 19)], 3.2, end=.8), S([(16, 5), (16, 19)], 3.2, end=.8)],
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
    """Four strokes: the record (an open circle), two grooves that turn slowly, and the straight
    handle that makes it a magnifying glass looking for music."""
    disc = stroke(arc(26, 26, 19, -55, 268, 21), 4.4, .25, .7)
    g1 = stroke(arc(26, 26, 12.6, 150, 380, 15), 2.1, .3, .65)
    g2 = stroke(arc(26, 26, 7.4, -30, 165, 11), 2, .3, .65)
    handle = stroke([(40.4, 40.4), (57.4, 57.4)], 6, .35, .65)
    spin = ("<animateTransform attributeName='transform' type='rotate' from='0 26 26' to='360 26 26' "
            "dur='{d}s' repeatCount='indefinite'/>")
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64' width='{size}' height='{size}' fill='{color}'>"
            f"<path d='{disc}'/><path d='{handle}'/><g><path d='{g1}'/>{spin.format(d=9)}</g>"
            f"<g><path d='{g2}'/>{spin.format(d=6)}</g><circle cx='26' cy='26' r='2.2'/></svg>")
