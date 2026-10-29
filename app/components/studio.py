"""The recommendation studio: the three mode cards and the loading bar.

The loading bar is a sound wave that fills from left to right under a spinning record (the
playhead), with the step in words, the share done, the time left and the tracks found. It is
redrawn several times a second while the mode works; every animation uses a negative delay equal
to the time already elapsed, so each redraw continues the motion instead of restarting it.
"""

from __future__ import annotations

import math
from html import escape

from app.components import theme

# Each mode: its colour (same as on the map) and the second colour of its gradient.
MODE_COLORS = {"neighbours": ("#ff7a59", "#e8558e"), "subgenres": ("#38b6ff", "#119f86"), "moment": ("#a98bff", "#e8558e")}


def _mix(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def mode_art(mode: str) -> str:
    """A small line drawing of how the mode works."""
    c, c2 = MODE_COLORS[mode]
    if mode == "neighbours":  # a favourite in the middle, its neighbours around, one step further
        nodes = [(60 + 34 * math.cos(a), 44 + 30 * math.sin(a)) for a in [i * math.tau / 6 + .3 for i in range(6)]]
        far = [(60 + 54 * math.cos(a), 44 + 40 * math.sin(a)) for a in [i * math.tau / 6 + .75 for i in range(6)]]
        lines = "".join(f"<line x1='60' y1='44' x2='{x:.0f}' y2='{y:.0f}' stroke='{c}' stroke-width='2'/>" for x, y in nodes)
        lines += "".join(f"<line x1='{a[0]:.0f}' y1='{a[1]:.0f}' x2='{b[0]:.0f}' y2='{b[1]:.0f}' stroke='{c2}' stroke-width='1.4' "
                         f"stroke-dasharray='3 3' opacity='.8'/>" for a, b in zip(nodes, far))
        dots = "".join(f"<circle cx='{x:.0f}' cy='{y:.0f}' r='6' fill='{c}'/>" for x, y in nodes)
        dots += "".join(f"<circle cx='{x:.0f}' cy='{y:.0f}' r='3.5' fill='none' stroke='{c2}' stroke-width='1.6'/>" for x, y in far)
        body = lines + dots + "<circle cx='60' cy='44' r='11' fill='#1f1f1f'/><circle cx='60' cy='44' r='3' fill='#fff'/>"
    elif mode == "subgenres":  # a patch of the map: your genres glow, arrows lead to new ones
        homes = [(34, 56, 15), (52, 40, 11)]
        body = "".join(f"<circle cx='{x}' cy='{y}' r='{r}' fill='{c}' opacity='.28'/><circle cx='{x}' cy='{y}' r='4' fill='{c}'/>"
                       for x, y, r in homes)
        for (x0, y0), (x1, y1) in (((34, 56), (88, 66)), ((52, 40), (92, 22)), ((34, 56), (60, 80))):
            body += (f"<path d='M{x0} {y0} Q{(x0 + x1) / 2} {min(y0, y1) - 14} {x1} {y1}' fill='none' stroke='{c2}' "
                     f"stroke-width='1.8' stroke-dasharray='4 3'/><circle cx='{x1}' cy='{y1}' r='5' fill='none' stroke='{c2}' stroke-width='2'/>")
        for x, y, w in ((8, 20, 26), (70, 8, 30), (14, 82, 22), (96, 48, 18), (64, 52, 16)):
            body += f"<rect x='{x}' y='{y}' width='{w}' height='3' rx='1.5' fill='#1f1f1f' opacity='.25'/>"
    else:  # a clock: the hand points at the moment, radio waves around
        body = (f"<circle cx='60' cy='46' r='26' fill='none' stroke='{c}' stroke-width='2.5'/>"
                + "".join(f"<line x1='{60 + 21 * math.sin(a):.1f}' y1='{46 - 21 * math.cos(a):.1f}' x2='{60 + 25 * math.sin(a):.1f}' "
                          f"y2='{46 - 25 * math.cos(a):.1f}' stroke='{c}' stroke-width='2'/>" for a in [i * math.tau / 12 for i in range(12)])
                + "<line x1='60' y1='46' x2='60' y2='30' stroke='#1f1f1f' stroke-width='3' stroke-linecap='round'/>"
                  "<line x1='60' y1='46' x2='72' y2='52' stroke='#1f1f1f' stroke-width='3' stroke-linecap='round'/>"
                  "<circle cx='60' cy='46' r='3.5' fill='#1f1f1f'/>"
                + "".join(f"<path d='M{94 + k * 6} {30 - k * 2} q{8 + k * 2} {16 + k * 2} 0 {32 + k * 4}' fill='none' stroke='{c2}' "
                          f"stroke-width='2' stroke-linecap='round' opacity='{.9 - k * .25:.2f}'/>" for k in range(3))
                + "".join(f"<path d='M{26 - k * 6} {30 - k * 2} q-{8 + k * 2} {16 + k * 2} 0 {32 + k * 4}' fill='none' stroke='{c2}' "
                          f"stroke-width='2' stroke-linecap='round' opacity='{.9 - k * .25:.2f}'/>" for k in range(3)))
    return f"<svg viewBox='0 0 120 88' class='rs-art'>{body}</svg>"


def mode_card(mode: str, name: str, tagline: str, text: str, status: str, active: bool) -> str:
    c, _ = MODE_COLORS[mode]
    return (f"<div class='rs-card{' on' if active else ''}' style='--c:{c}'>{mode_art(mode)}"
            f"<div class='rs-tag'>{escape(tagline)}</div><h3 class='rs-name'>{escape(name)}</h3>"
            f"<p class='rs-text'>{escape(text)}</p><div class='rs-status'><i></i>{escape(status)}</div></div>")


def _wave_heights(count: int) -> list[float]:
    """A plausible audio waveform: two slow swells and some grain, always the same."""
    return [0.22 + 0.5 * abs(math.sin(i * 0.19) * math.cos(i * 0.053 + 1.3)) + 0.28 * abs(math.sin(i * 1.7 + math.sin(i)))
            for i in range(count)]


def progress_html(mode: str, fraction: float, elapsed: float, eta: float | None, step: str,
                  found: int, target: int, calls: int, planned: int, labels: dict, done: bool = False) -> str:
    """The loading bar (see the module docstring). Pure HTML for st.html; the record is an <img>."""
    c, c2 = MODE_COLORS[mode]
    n = 96
    filled = fraction * n
    bars = []
    for i, h in enumerate(_wave_heights(n)):
        on = i < filled
        col = _mix(c, c2, i / (n - 1)) if on else "rgba(31,31,31,.13)"
        edge = " edge" if on and i >= filled - 3 else ""
        bars.append(f"<i class='{'on' if on else ''}{edge}' style='height:{h * 100:.0f}%;background:{col};"
                    f"animation-delay:{-(elapsed + i * 0.071):.2f}s'></i>")
    head = (f"<div class='rp-head' style='left:{fraction * 100:.2f}%;animation-delay:{-elapsed:.2f}s'>"
            f"{theme.mark_img(34)}</div>")
    pct = int(round(fraction * 100))
    eta_txt = labels["done"] if done else (labels["eta"].format(s=max(1, round(eta))) if eta is not None else labels["eta_wait"])
    return (f"<div class='rp' style='--c:{c};--c2:{c2}'>"
            f"<div class='rp-top'><div class='rp-pct num'>{pct}<small>%</small></div>"
            f"<div class='rp-step'>{escape(step)}</div><div class='rp-eta num'>{escape(eta_txt)}</div></div>"
            f"<div class='rp-wave' style='--shine-delay:{-elapsed:.2f}s'>{''.join(bars)}{head}</div>"
            f"<div class='rp-foot num'><span><b>{found}</b> / {target} {escape(labels['found'])}</span>"
            f"<span>{calls} / {max(calls, planned)} {escape(labels['calls'])}</span>"
            f"<span>{elapsed:.1f} s</span></div></div>")
