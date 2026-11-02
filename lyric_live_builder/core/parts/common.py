"""Shared helpers of the layout parts."""
import math

import numpy as np

from .. import lyrics, model, xform
from ..registry import GlyphPlacement, Placement

DEG = math.pi / 180


def visible(ch):
    return not ch.isspace()


def fit_em(ctx, width_em, distance=None, max_angle=model.MAX_LINE_ANGLE):
    """The context em, shrunk so a row width_em wide spans at most max_angle at distance."""
    d = distance or ctx.distance
    limit = 2 * d * math.tan(max_angle * DEG / 2)
    return min(ctx.em, limit / max(width_em, 1e-6))


def row(ctx, em):
    """Horizontal row centred on x = 0: [(char index, x)] for visible characters."""
    width = sum(ctx.adv) * em
    x, out = -width / 2, []
    for i, (ch, a) in enumerate(zip(ctx.text, ctx.adv)):
        if visible(ch):
            out.append((i, x + a * em / 2))
        x += a * em
    return out


def column(ctx, em):
    """Vertical column centred on z = 0: [(char index, x, z, rotated)] (JIZURA vertical rules)."""
    height = sum(ctx.vadv) * em
    z, out = height / 2, []
    for i, (ch, a) in enumerate(zip(ctx.text, ctx.vadv)):
        dx = dz = 0.0
        if lyrics.is_small_kana(ch):
            dx, dz = 0.11 * em, 0.11 * em
        if ch in "、。，．":
            dx, dz = 0.3 * em, 0.3 * em
        rotated = ch in lyrics.VERT_ROTATE or lyrics.is_latin(ch)
        if visible(ch):
            out.append((i, dx, z - a * em / 2 + dz, rotated))
        z -= a * em
    return out


def flat(ctx, params, em=None, azimuth=None, elevation=None, distance=None, extra_rot=None):
    """A horizontal line facing the eye at the anchor (or the given angles)."""
    az = ctx.anchor[0] if azimuth is None else azimuth
    el = ctx.anchor[1] if elevation is None else elevation
    d = distance or ctx.distance
    em = em or fit_em(ctx, sum(ctx.adv), d)
    loc = np.array([0.0, 0.0, ctx.eye]) + d * xform.direction(az, el)
    rot = xform.facing(az, el)
    if extra_rot is not None:
        rot = xform.mul(rot, extra_rot)
    glyphs = [GlyphPlacement(i, np.array([x, 0.0, 0.0])) for i, x in row(ctx, em)]
    return Placement(loc, rot, em, glyphs)


def vertical_rot():
    """Glyph turned 90° clockwise for vertical writing (about the axis toward the viewer)."""
    return xform.roll(math.pi / 2)


# ---- vectorized easing for the motion parts (p is clipped to 0..1) ----

def clip(p):
    return np.clip(p, 0.0, 1.0)


def out_cubic(p):
    return 1 - (1 - clip(p)) ** 3


def in_cubic(p):
    return clip(p) ** 3


def out_expo(p):
    p = clip(p)
    return np.where(p >= 1, 1.0, 1 - 2.0 ** (-10 * p))


def in_expo(p):
    p = clip(p)
    return np.where(p <= 0, 0.0, 2.0 ** (10 * p - 10))


def out_back(p, s=1.9):
    p = clip(p)
    return 1 + (s + 1) * (p - 1) ** 3 + s * (p - 1) ** 2


def in_out_sine(p):
    return -(np.cos(np.pi * clip(p)) - 1) / 2


def glyph_random(seed, n, salt, k):
    """(n,) deterministic values in -1..1 per glyph."""
    from ..rng import h_np
    return h_np(seed, np.arange(n), salt, k) / 4294967296.0 * 2 - 1
