"""Holds (spec §7.4). Input is the seconds since the hold began; 0 is the rest pose."""
import math

import numpy as np

from .. import xform
from ..registry import Delta, MotionPart, register
from .common import glyph_random


@register("hold", "still")
class Still(MotionPart):
    name = "Still"
    tags = ("calm", "editorial", "graphic", "pop", "glitch", "emotional")
    weight = 1.5

    def evaluate(self, ctx, s):
        return Delta(ctx.n, s.shape[1])


@register("hold", "float")
class Float(MotionPart):
    name = "Floating"
    tags = ("calm", "emotional", "pop")

    def evaluate(self, ctx, s):
        ph = glyph_random(ctx.seed, ctx.n, 31, 0)[:, None] * math.pi
        loc = np.zeros(s.shape + (3,))
        loc[..., 2] = ctx.em * 0.08 * ctx.strength * (np.sin(2 * math.pi * s / 2.4 + ph) - np.sin(ph))
        return Delta(ctx.n, s.shape[1], loc=loc)


@register("hold", "sway")
class Sway(MotionPart):
    name = "Sway"
    tags = ("calm", "emotional", "glitch")

    def evaluate(self, ctx, s):
        from ..rng import noise1_np
        seeds = (ctx.seed + np.arange(ctx.n))[:, None]
        n = noise1_np(s * 0.9 + seeds * 7.0, 41) - noise1_np(seeds * 7.0, 41)
        return Delta(ctx.n, s.shape[1], rot=xform.roll(n * 0.12 * ctx.strength))


@register("hold", "pulse")
class Pulse(MotionPart):
    name = "Beat Pulse"
    tags = ("pop", "glitch", "graphic")

    def evaluate(self, ctx, s):
        beat = 60.0 / ctx.bpm if ctx.bpm > 0 else 0.5
        k = (0.5 - 0.5 * np.cos(2 * math.pi * s / beat)) ** 4
        return Delta(ctx.n, s.shape[1], scale=(1 + 0.07 * ctx.strength * k)[..., None])


@register("hold", "slow_spin")
class SlowSpin(MotionPart):
    name = "Slow Rotation"
    tags = ("graphic", "calm")
    weight = 0.6

    def evaluate(self, ctx, s):
        return Delta(ctx.n, s.shape[1], rot=xform.yaw(np.sin(s * 0.8) * 0.35 * ctx.strength))


@register("hold", "breathe")
class Breathe(MotionPart):
    name = "Breathe"
    tags = ("calm", "emotional")

    def evaluate(self, ctx, s):
        k = 0.5 - 0.5 * np.cos(2 * math.pi * s / 3.2)
        return Delta(ctx.n, s.shape[1], scale=(1 + 0.05 * ctx.strength * k)[..., None])
