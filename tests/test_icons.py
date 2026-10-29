"""The icons and the logo: geometric strokes of even width, a gentle taper as their only organic touch."""

import math
import re

from app.components import icons


def _widths(path: str) -> list[float]:
    """Width of a horizontal stroke along x, read from its outline (left side then right side)."""
    side = path.split("Q")[0]  # M and L points: one side of the stroke, start to end
    nums = [float(v) for v in re.findall(r"-?\d+\.\d+", side)]
    return [abs(y) * 2 for y in nums[1::2]]


def test_a_stroke_keeps_an_even_width_then_tapers_gently():
    w = _widths(icons.stroke([(0.0, 0.0), (20.0, 0.0)], 2.0))
    body = w[1:int(len(w) * .7)]
    assert max(body) - min(body) < .04 * 2.0  # no press, no tremble
    assert .45 * 2.0 <= w[-1] <= .75 * 2.0  # a gentle taper, not a needle


def test_every_icon_and_the_logo_are_drawn():
    assert set(icons.MATERIAL.values()) <= set(icons._icons())
    for name in icons._icons():
        assert icons.svg(name).count("<path") >= 1
    logo = icons.logo_svg(64)
    assert logo.count("<path") == 4 and "animateTransform" in logo  # disc, two grooves, handle
    assert math.isclose(math.dist(icons.arc(12, 12, 5, 0, 90, 3)[1], (12, 12)), 5)
