"""Layouts usable by 2D and 3D lines (spec §7.3)."""
import math

import numpy as np

from .. import xform
from ..registry import GlyphPlacement, LayoutPart, Placement, register
from .common import DEG, column, fit_em, flat, row, vertical_rot


@register("layout", "front")
class Front(LayoutPart):
    name = "Facing Front"
    tags = ("calm", "pop", "editorial", "emotional", "glitch", "graphic")
    weight = 1.4

    def place(self, ctx, params):
        return flat(ctx, params)


@register("layout", "look_up")
class LookUp(LayoutPart):
    name = "Look Up"
    tags = ("calm", "emotional", "editorial")
    weight = 0.8
    keepable = False                   # rises above its slot into the next one

    def plan(self, rng, ctx):
        return {"elevation": rng.range(22, 34) * DEG}

    def place(self, ctx, params):
        return flat(ctx, params, elevation=ctx.anchor[1] + params["elevation"])


@register("layout", "arc")
class Arc(LayoutPart):
    name = "Surrounding Arc"
    tags = ("pop", "graphic", "emotional")
    weight = 1.0
    big = True

    def fits(self, n_chars):
        return n_chars >= 4

    def plan(self, rng, ctx):
        return {"elevation": rng.range(-4, 10) * DEG}

    def place(self, ctx, params):
        d = ctx.distance
        em = fit_em(ctx, sum(ctx.adv), d, max_angle=100)       # an arc may wrap wider than a flat line
        loc = np.array([0.0, 0.0, ctx.eye + d * math.sin(params["elevation"])])
        rot = xform.yaw(-ctx.anchor[0])
        glyphs = []
        for i, x in row(ctx, em):
            a = x / d                                           # arc length -> angle
            glyphs.append(GlyphPlacement(i, np.array([d * math.sin(a), d * math.cos(a), 0.0]), xform.yaw(-a)))
        return Placement(loc, rot, em, glyphs)


@register("layout", "spiral")
class Spiral(LayoutPart):
    name = "Spiral Around"
    tags = ("pop", "graphic", "glitch")
    weight = 0.7
    big = True

    def fits(self, n_chars):
        return n_chars >= 5

    def plan(self, rng, ctx):
        return {"rise": rng.pick([1, -1]), "turn": rng.range(160, 260) * DEG}

    def place(self, ctx, params):
        d = ctx.distance
        n = sum(ctx.adv)
        em = min(ctx.em, params["turn"] * d / max(n, 1e-6))   # the text covers `turn` around the eye
        height = min(1.0, em * 1.6 * max(1.0, n / 4))             # stays above the floor
        loc = np.array([0.0, 0.0, ctx.eye])
        rot = xform.yaw(-ctx.anchor[0])
        glyphs = []
        for i, x in row(ctx, em):
            a = x / d
            z = params["rise"] * height * (x / max(n * em, 1e-6))
            glyphs.append(GlyphPlacement(i, np.array([d * math.sin(a), d * math.cos(a), z]), xform.yaw(-a)))
        return Placement(loc, rot, em, glyphs)


@register("layout", "stagger")
class Stagger(LayoutPart):
    name = "Staggered"
    tags = ("pop", "glitch", "graphic")
    weight = 0.9

    def plan(self, rng, ctx):
        return {"up": rng.range(0.18, 0.32), "tilt": rng.range(5, 11) * DEG, "flip": rng.pick([1, -1])}

    def place(self, ctx, params):
        p = flat(ctx, params)
        for k, g in enumerate(p.glyphs):
            s = params["flip"] * (1 if k % 2 else -1)
            g.loc = g.loc + np.array([0.0, 0.0, s * params["up"] * p.em])
            g.rot = xform.roll(s * params["tilt"])
        return p


@register("layout", "pillar")
class Pillar(LayoutPart):
    name = "Vertical Pillar"
    tags = ("calm", "editorial", "emotional")
    weight = 0.8
    vertical = True
    anchored = False                   # stands to one side

    def fits(self, n_chars):
        return 2 <= n_chars <= 16

    def plan(self, rng, ctx):
        return {"side": rng.pick([1, -1]), "azimuth": rng.range(22, 34) * DEG}

    def place(self, ctx, params):
        d = ctx.distance
        height = sum(ctx.vadv)
        em = fit_em(ctx, height, d, max_angle=48)              # keep the pillar within a comfortable height
        az = params["side"] * params["azimuth"]
        loc = np.array([0.0, 0.0, ctx.eye]) + d * xform.direction(az, 0.0)
        rot = xform.facing(az, 0.0)
        glyphs = [GlyphPlacement(i, np.array([dx, 0.0, z]), vertical_rot() if r else None, r)
                  for i, dx, z, r in column(ctx, em)]
        return Placement(loc, rot, em, glyphs)


@register("layout", "scatter")
class Scatter(LayoutPart):
    name = "Scattered"
    tags = ("glitch", "pop", "graphic")
    weight = 0.7
    big = True
    anchored = False

    def fits(self, n_chars):
        return 3 <= n_chars <= 20

    def plan(self, rng, ctx):
        n = len(ctx.text)
        return {"jitter": [[rng.range(-1, 1), rng.range(-1, 1), rng.range(-1, 1)] for _ in range(n)]}

    def place(self, ctx, params):
        d = ctx.distance
        positions = row(ctx, ctx.em)
        span = max(20 * DEG, min(50 * DEG, len(positions) * 2 * ctx.em / d))   # still reads left to right
        em = min(ctx.em, 0.9 * d * span / max(1, len(positions) - 1))         # neighbours stay apart
        loc = np.array([0.0, 0.0, ctx.eye])
        glyphs = []
        for k, (i, _) in enumerate(positions):
            jx, jy, jz = params["jitter"][i]
            # reading order runs left to right; each glyph floats at its own depth and height
            az = (k / max(1, len(positions) - 1) - 0.5) * span + jx * 1.0 * DEG
            el = jy * 6 * DEG
            r = d * (1.0 + 0.15 * jz)
            glyphs.append(GlyphPlacement(i, r * xform.direction(az, el), xform.facing(az, el)))
        return Placement(loc, xform.IDENTITY.copy(), em, glyphs)
