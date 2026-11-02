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


@register("enter", "wipe")
class Wipe(MotionPart):
    name = "Wipe"
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
