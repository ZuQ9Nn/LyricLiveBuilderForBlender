"""Exits (spec §7.4). p goes 0 -> 1; p = 0 is the rest pose, p = 1 has left."""
import math

import numpy as np

from .. import xform
from ..registry import Delta, MotionPart, register
from .common import glyph_random, in_cubic, in_expo, in_out_sine


def _hide(p, start=0.6):
    return 1 - np.clip((p - start) / (1 - start), 0, 1)


@register("exit", "fade")
class Fade(MotionPart):
    name = "Fade"
    tags = ("calm", "emotional", "editorial", "graphic", "pop", "glitch")
    weight = 1.4
    duration = 0.4
    stagger = 0.02

    def evaluate(self, ctx, p):
        return Delta(ctx.n, p.shape[1], alpha=1 - in_out_sine(p))


@register("exit", "explode")
class Explode(MotionPart):
    name = "Burst Apart"
    tags = ("glitch", "pop", "graphic")
    duration = 0.6
    stagger = 0.0

    def evaluate(self, ctx, p):
        # ponytail: whole glyphs fly; per-stroke pieces need split glyph meshes (later phase)
        e = 1 - (1 - np.clip(p, 0, 1)) ** 2
        d = np.stack([glyph_random(ctx.seed, ctx.n, 51, a) for a in range(3)], axis=-1)
        d[:, 1] = np.abs(d[:, 1]) + 0.3                   # outward and away, never toward the viewer
        loc = e[..., None] * d[:, None, :] * ctx.em * 5.0
        rot = xform.mul(xform.yaw(e * glyph_random(ctx.seed, ctx.n, 52, 0)[:, None] * 3),
                        xform.pitch(e * glyph_random(ctx.seed, ctx.n, 53, 0)[:, None] * 3))
        return Delta(ctx.n, p.shape[1], loc=loc, rot=rot, alpha=_hide(p))


@register("exit", "collapse")
class Collapse(MotionPart):
    name = "Crumble Down"
    tags = ("glitch", "graphic", "emotional")
    duration = 0.7
    stagger = 0.04

    def evaluate(self, ctx, p):
        q = np.clip(p, 0, 1)
        loc = np.zeros(p.shape + (3,))
        loc[..., 2] = -ctx.em * 6.0 * q * q              # gravity
        loc[..., 1] = ctx.em * 0.6 * q
        tilt = q * glyph_random(ctx.seed, ctx.n, 61, 0)[:, None] * 1.2
        return Delta(ctx.n, p.shape[1], loc=loc, rot=xform.roll(tilt), alpha=_hide(p, 0.5))


@register("exit", "dust")
class Dust(MotionPart):
    name = "Scatter into Particles"
    tags = ("emotional", "calm", "glitch")
    duration = 0.8
    stagger = 0.03

    def evaluate(self, ctx, p):
        # Blender preview approximation; in Unity a ParticleSystem emits from the glyph mesh
        q = np.clip(p, 0, 1)
        drift = np.stack([glyph_random(ctx.seed, ctx.n, 71, 0), np.full(ctx.n, 0.5), np.full(ctx.n, 1.0)], axis=-1)
        loc = (q[..., None] * drift[:, None, :]) * ctx.em * 2.0
        return Delta(ctx.n, p.shape[1], loc=loc, scale=(1 - 0.85 * q)[..., None], alpha=1 - q)


@register("exit", "fly_away")
class FlyAway(MotionPart):
    name = "Fly Away"
    tags = ("emotional", "pop", "calm")
    duration = 0.6
    stagger = 0.03

    def evaluate(self, ctx, p):
        loc = np.zeros(p.shape + (3,))
        loc[..., 1] = in_expo(p) * ctx.em * 16.0
        return Delta(ctx.n, p.shape[1], loc=loc, alpha=_hide(p, 0.4))


@register("exit", "shrink")
class Shrink(MotionPart):
    name = "Shrink Away"
    tags = ("pop", "graphic", "editorial")
    duration = 0.35
    stagger = 0.02

    def evaluate(self, ctx, p):
        s = 1 - in_cubic(p)
        return Delta(ctx.n, p.shape[1], scale=s[..., None], alpha=(p < 1).astype(float))


@register("exit", "topple")
class Topple(MotionPart):
    name = "Topple"
    tags = ("pop", "graphic")
    duration = 0.7
    stagger = 0.06

    def evaluate(self, ctx, p):
        # falls backward about its bottom edge, like a domino
        a = in_cubic(p) * (math.pi / 2)
        h = ctx.em / 2
        loc = np.zeros(p.shape + (3,))
        loc[..., 1] = h * np.sin(a)
        loc[..., 2] = h * np.cos(a) - h
        return Delta(ctx.n, p.shape[1], loc=loc, rot=xform.pitch(-a), alpha=_hide(p, 0.75))
