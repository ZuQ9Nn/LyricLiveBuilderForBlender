"""Entrances (spec §7.4). p goes 0 -> 1; p = 1 is the rest pose."""
import math

import numpy as np

from .. import xform
from ..registry import Delta, MotionPart, register
from .common import glyph_random, in_out_sine, out_back, out_cubic, out_expo


def _show(p, speed=4.0):
    return np.clip(p * speed, 0, 1)


@register("enter", "pop_sing")
class PopSing(MotionPart):
    name = "Pop as Sung"
    tags = ("pop", "emotional", "calm", "graphic")
    weight = 1.6
    duration = 0.24

    def windows(self, ctx, dur):
        return ctx.char_times                     # each character pops when it is sung

    def evaluate(self, ctx, p):
        s = out_back(p)[..., None]
        return Delta(ctx.n, p.shape[1], scale=np.maximum(s, 0.0), alpha=_show(p))


@register("enter", "type")
class Type(MotionPart):
    name = "Type"
    tags = ("editorial", "glitch", "calm")
    duration = 0.05

    def windows(self, ctx, dur):
        return ctx.char_times

    def evaluate(self, ctx, p):
        return Delta(ctx.n, p.shape[1], alpha=(p > 0).astype(float))


@register("enter", "fall")
class Fall(MotionPart):
    name = "Drop In"
    tags = ("pop", "graphic")
    duration = 0.45
    stagger = 0.05

    def evaluate(self, ctx, p):
        e = out_cubic(p)
        loc = np.zeros(p.shape + (3,))
        loc[..., 2] = (1 - e) * ctx.em * 3.0
        return Delta(ctx.n, p.shape[1], loc=loc, alpha=_show(p, 3))


@register("enter", "spin")
class Spin(MotionPart):
    name = "Spin In"
    tags = ("pop", "glitch", "graphic")
    duration = 0.5

    def evaluate(self, ctx, p):
        e = out_cubic(p)
        rot = xform.yaw((1 - e) * math.pi * 1.5)
        return Delta(ctx.n, p.shape[1], rot=rot, scale=e[..., None], alpha=_show(p, 3))


@register("enter", "fly_in")
class FlyIn(MotionPart):
    name = "Fly in from Afar"
    tags = ("emotional", "pop", "calm")
    duration = 0.6
    stagger = 0.03

    def evaluate(self, ctx, p):
        e = out_expo(p)
        loc = np.zeros(p.shape + (3,))
        loc[..., 1] = (1 - e) * ctx.em * 14.0            # +y = away from the viewer
        return Delta(ctx.n, p.shape[1], loc=loc, alpha=_show(p, 2))


@register("enter", "assemble")
class Assemble(MotionPart):
    name = "Assemble"
    tags = ("glitch", "graphic", "pop")
    duration = 0.6
    stagger = 0.0

    def evaluate(self, ctx, p):
        # ponytail: whole glyphs fly together; per-stroke pieces need split glyph meshes (later phase)
        e = out_expo(p)
        k = (1 - e)[..., None]
        d = np.stack([glyph_random(ctx.seed, ctx.n, 11, a) for a in range(3)], axis=-1) * ctx.em * 3.0
        d[:, 1] = np.abs(d[:, 1])                         # spread away from the viewer, not toward
        loc = k * d[:, None, :]
        ang = (1 - e) * glyph_random(ctx.seed, ctx.n, 12, 0)[:, None] * math.pi
        return Delta(ctx.n, p.shape[1], loc=loc, rot=xform.roll(ang), alpha=_show(p, 2))


@register("enter", "unfold")
class Unfold(MotionPart):
    name = "Unfold Sideways"
    tags = ("editorial", "graphic", "calm")
    duration = 0.3
    stagger = 0.035

    def evaluate(self, ctx, p):
        e = out_expo(p)
        scale = np.ones(p.shape + (3,))
        scale[..., 0] = e                                 # unfolds sideways, left to right
        return Delta(ctx.n, p.shape[1], scale=scale, alpha=(p > 0).astype(float))


@register("enter", "zoom")
class Zoom(MotionPart):
    name = "Zoom from Big"
    tags = ("pop", "glitch", "graphic")
    duration = 0.35
    stagger = 0.02

    def evaluate(self, ctx, p):
        e = out_expo(p)
        return Delta(ctx.n, p.shape[1], scale=(2.6 - 1.6 * e)[..., None], alpha=_show(p, 2.5))


@register("enter", "fade")
class Fade(MotionPart):
    name = "Fade"
    tags = ("calm", "emotional", "editorial")
    duration = 0.5
    stagger = 0.03

    def evaluate(self, ctx, p):
        return Delta(ctx.n, p.shape[1], alpha=in_out_sine(p))


@register("enter", "gather")
class Gather(MotionPart):
    name = "Gather from Particles"
    tags = ("emotional", "calm", "pop")
    duration = 0.8
    stagger = 0.03

    def evaluate(self, ctx, p):
        # Blender preview approximation; in Unity a ParticleSystem emits from the glyph mesh
        e = out_cubic(p)
        k = (1 - e)
        a = glyph_random(ctx.seed, ctx.n, 21, 0)[:, None] * math.pi + k * 4.0
        r = k * ctx.em * 1.5
        loc = np.stack([np.cos(a) * r, np.abs(np.sin(a)) * r, np.sin(a * 0.7) * r], axis=-1)
        return Delta(ctx.n, p.shape[1], loc=loc, scale=(0.15 + 0.85 * e)[..., None], alpha=e)


# Ported from JIZURA (src/11p_enter.js glitchIn), MIT License, Copyright (c) 2026 hakoniwa.
@register("enter", "glitch_in")
class GlitchIn(MotionPart):
    """Glyphs flicker in at jumbled places and widths, each settling at its own moment."""
    name = "Glitch In"
    tags = ("glitch",)
    weight = 1.2
    group = "extra"
    duration = 0.7
    stagger = 0.0

    def evaluate(self, ctx, p):
        from ..rng import h_np
        r = lambda *k: h_np(*k) / 4294967296.0
        i = np.arange(ctx.n)[:, None]
        settle = 0.38 + 0.52 * r(ctx.seed, i, 71)
        step = np.floor(p * 16)                                     # the jumble changes about 12 times a second
        u = np.clip(p / settle, 0, 1)
        live = p < settle
        shown = (r(ctx.seed, i, step, 72) <= 0.25 * np.clip(p * 12, 0, 1) + 0.75 * u) | ~live
        k = np.where(live, 1 - u, 0.0)
        loc = np.zeros(p.shape + (3,))
        loc[..., 0] = (r(ctx.seed, i, step, 73) * 2 - 1) * ctx.em * 0.5 * k
        loc[..., 2] = -(r(ctx.seed, i, step, 74) * 2 - 1) * ctx.em * 0.14 * k
        scale = np.ones(p.shape + (3,))
        wide = live & (r(ctx.seed, i, step, 77) < 0.35)
        scale[..., 0] = np.where(wide, 0.55 + 1.35 * r(ctx.seed, i, step, 78), 1.0)
        return Delta(ctx.n, p.shape[1], loc=loc, scale=scale, alpha=shown.astype(float))


# ---------------- masked entrances (JIZURA src/05_anim.js wipe / slice, src/11p_enter.js checker) ----------------

class _Masked(MotionPart):
    """Revealed by a mask over the whole line; the shader does the shape (design §5.6)."""
    uses_mask = True
    stagger = 0.0

    def evaluate(self, ctx, p):
        return Delta(ctx.n, p.shape[1], mask=self.progress(p))

    def progress(self, p):
        return np.clip(p, 0.0, 1.0)


@register("enter", "wipe")
class Wipe(_Masked):
    """An accent bar appears at one end of the line and sweeps across, uncovering it."""
    name = "Wipe"
    tags = ("calm", "graphic", "editorial", "emotional")
    duration = 0.55
    line_fx = True

    def progress(self, p):
        x = np.clip(p, 0.0, 1.0)
        with np.errstate(over="ignore"):
            e = np.where(x < 0.5, 2.0 ** (20 * x - 10) / 2, (2 - 2.0 ** (-20 * x + 10)) / 2)    # in-out expo
        return np.where(x <= 0, 0.0, np.where(x >= 1, 1.0, e))

    def mask_shape(self, ctx):
        return (1.0, float(ctx.seed % 2), 0.0, 0.0)


@register("enter", "slice")
class Slice(MotionPart):
    """The line arrives as seven horizontal bands sliding in from alternate sides. The bands are copies of the
    glyphs that the bake adds for the entrance (band_copies); the glyph itself shows when they have landed."""
    name = "Slice"
    tags = ("glitch", "graphic", "emotional")
    duration = 0.6
    stagger = 0.0
    band_copies = 7

    def evaluate(self, ctx, p):
        return Delta(ctx.n, p.shape[1], alpha=(p >= 1).astype(float))

    def band_motion(self, p, b, n, k, g, width, height, em):
        """JIZURA: (1 - outExpo(p * 1.2 - 0.05 band)) of 0.9 screen widths, alternate sides; landed at p = 1."""
        x = np.clip(p * 1.3 - 0.05 * b, 0.0, 1.0)
        left = np.where(x >= 1, 0.0, 2.0 ** (-10 * x))
        return left * (1 if b % 2 else -1) * width * 1.2, 0.0 * p


@register("enter", "checker")
class Checker(_Masked):
    """Accent squares pop up in a checkerboard and shrink, uncovering the line square by square."""
    name = "Checkerboard"
    tags = ("graphic", "glitch", "pop")
    weight = 0.7
    group = "extra"
    duration = 0.7
    line_fx = True

    def mask_shape(self, ctx):
        return (3.0, 0.34, float(ctx.seed % 997), 0.0)

