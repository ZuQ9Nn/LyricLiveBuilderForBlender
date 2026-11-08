# Holds ported from JIZURA (src/05_anim.js J.HOLD, src/11p_exit.js / 11p_exitB.js / 11p_horror*.js /
# 11p_kinetic*.js / 11p_typo*.js), MIT License, Copyright (c) 2026 hakoniwa. Rewritten for 3D text in VR.
"""Holds added from JIZURA v0.10 (spec §7.4, design §5.6).

JIZURA returns the transform at a moment; here the hold starts from the rest pose (it follows the entrance),
so every motion is faded in over RAMP seconds. JIZURA's 2D y (down) becomes -z; nothing moves toward the
viewer (-y). Colour, skew and blur cannot be animated: they become alpha, in-plane rotation and scale."""
import math

import numpy as np

from .. import xform
from ..registry import Delta, MotionPart, register
from ..rng import h_np, noise1_np
from .common import clip, in_cubic, in_out_sine, out_back, out_cubic, out_expo

DEG = math.pi / 180
RAMP = 0.35                           # seconds over which a hold grows from the rest pose
STEP = 12.0                           # JIZURA's random glitches change 12 times a second
TAU = 2 * math.pi


# ---------------- helpers ----------------

def _k(ctx):
    """Motion strength, 1 at the default (JIZURA's amt × motionK)."""
    return ctx.strength / 0.7


def _beat(ctx, fallback=0.5):
    return 60.0 / ctx.bpm if ctx.bpm > 0 else fallback


def _r(*k):
    return h_np(*k) / 4294967296.0


def _rs(*k):
    return _r(*k) * 2 - 1


def _gi(ctx):
    return np.arange(ctx.n)[:, None]


def _along(ctx):
    """(G, 1) offset of each glyph from the text's centre along its run, and the axis (0 = x, 2 = z)."""
    rest = np.asarray(ctx.rest, dtype=np.float64)
    spread = rest.max(axis=0) - rest.min(axis=0) if len(rest) else np.zeros(3)
    axis = 2 if spread[2] > spread[0] else 0
    o = rest[:, axis] - (rest[:, axis].max() + rest[:, axis].min()) / 2 if len(rest) else np.zeros(0)
    if not np.any(o):                                      # no layout (unit tests): space them one em apart
        o = (np.arange(ctx.n) - (ctx.n - 1) / 2) * ctx.em
    return o[:, None], axis


def _words(ctx):
    w = getattr(ctx, "words", None)
    return np.zeros(ctx.n, dtype=int) if w is None or len(w) != ctx.n else np.asarray(w, dtype=int)


def _word_centres(ctx):
    """(G, 3) centre of each glyph's word, word index (G,), number of words."""
    w = _words(ctx)
    o, axis = _along(ctx)
    pos = np.asarray(ctx.rest, dtype=np.float64).copy()
    if not np.any(pos.max(axis=0) - pos.min(axis=0)):          # no layout (unit tests): along the run
        pos[:, axis] = o[:, 0]
    centres = np.zeros_like(pos)
    for j in np.unique(w):
        centres[w == j] = pos[w == j].mean(axis=0)
    return pos, centres, w, int(w.max()) + 1 if len(w) else 1


def _out(ctx, s, dx=0.0, dz=0.0, roll=0.0, sx=1.0, sz=1.0, a=1.0, ramp=True):
    """A Delta from per-glyph offsets (G, T); everything grows from the rest pose over RAMP seconds."""
    g, t = s.shape
    r = clip(s / RAMP) if ramp else np.ones_like(s)
    loc = np.zeros((g, t, 3))
    loc[..., 0] = np.broadcast_to(dx, (g, t)) * r
    loc[..., 2] = np.broadcast_to(dz, (g, t)) * r
    scale = np.ones((g, t, 3))
    scale[..., 0] = 1 + (np.broadcast_to(sx, (g, t)) - 1) * r
    scale[..., 2] = 1 + (np.broadcast_to(sz, (g, t)) - 1) * r
    alpha = 1 - (1 - np.broadcast_to(a, (g, t))) * r
    return Delta(g, t, loc=loc, rot=xform.roll(np.broadcast_to(roll, (g, t)) * r), scale=scale, alpha=alpha)


def _about(ctx, s, centres, pos, angle, extra_dz=0.0):
    """Turn each glyph about a centre (word, line or pivot) in the text plane by angle (G, T)."""
    q = xform.roll(angle)
    v = (pos - centres)[:, None, :]
    moved = xform.rotate(q, np.broadcast_to(v, q.shape[:-1] + (3,)))
    d = moved - v
    return _out(ctx, s, dx=d[..., 0], dz=d[..., 2] + extra_dz, roll=angle)


class _Hold(MotionPart):
    group = "extra"


# ---------------- JIZURA's basic holds ----------------

@register("hold", "jitter")
class Jitter(_Hold):
    name = "Jittery Shake"
    tags = ("glitch", "pop")
    group = "basic"

    def evaluate(self, ctx, s):
        step, i, k = np.floor(s * STEP), _gi(ctx), _k(ctx)
        a = ctx.em * 0.025 * k
        return _out(ctx, s, dx=_rs(ctx.seed, step, i, 1) * a, dz=-_rs(ctx.seed, step, i, 2) * a,
                    roll=_rs(ctx.seed, step, i, 3) * 4 * k * DEG)


@register("hold", "drift")
class Drift(_Hold):
    name = "Slow Drift"
    tags = ("calm", "emotional", "editorial")
    group = "basic"

    def evaluate(self, ctx, s):
        u = clip(s / max(0.3, ctx.end - ctx.start))
        side = 1 if ctx.seed % 2 else -1
        f = 1 + 0.05 * u * _k(ctx)
        return _out(ctx, s, dx=side * u * ctx.em * 0.6 * _k(ctx), sx=f, sz=f)


@register("hold", "wave")
class Wave(_Hold):
    name = "Rolling Wave"
    tags = ("pop",)
    group = "basic"

    def evaluate(self, ctx, s):
        ph = s * 7 + _gi(ctx) * 0.75
        k = _k(ctx)
        return _out(ctx, s, dz=-np.sin(ph) * ctx.em * 0.07 * k, roll=np.cos(ph) * 5 * k * DEG)


@register("hold", "glitch_tick")
class GlitchTick(_Hold):
    name = "Glitch Ticks"
    tags = ("glitch",)
    group = "basic"

    def evaluate(self, ctx, s):
        step, i = np.floor(s * STEP), _gi(ctx)
        fire = _r(ctx.seed, step, 77) < 0.13 * _k(ctx) + 0.02
        moved = fire & (_r(ctx.seed, step, i, 5) < 0.6)
        return _out(ctx, s, dx=np.where(moved, _rs(ctx.seed, step, i, 6) * ctx.em * 0.35, 0.0))


# ---------------- added holds ----------------

@register("hold", "shimmer")
class Shimmer(_Hold):
    name = "Shimmer"
    tags = ("emotional", "calm")
    weight = 0.5

    def evaluate(self, ctx, s):
        k = min(1.0, _k(ctx))
        tw = 0.5 + 0.5 * noise1_np(s * 3.2 + _gi(ctx) * 1.7, ctx.seed)
        spark = _r(ctx.seed, np.floor(s * STEP), _gi(ctx), 401) < 0.03 * k
        f = np.where(spark, 1.05, 1.0)
        return _out(ctx, s, a=1 - 0.42 * k * tw * tw, sx=f, sz=f)


@register("hold", "slow_lean")
class SlowLean(_Hold):
    name = "Slow Lean"
    tags = ("calm", "editorial")
    weight = 0.4

    def evaluate(self, ctx, s):
        side = 1 if (ctx.seed >> 1) & 1 else -1
        o, axis = _along(ctx)
        pos = np.zeros((ctx.n, 3))
        pos[:, axis] = o[:, 0]
        return _about(ctx, s, np.zeros(3), pos, side * np.minimum(10, s * 2.6) * _k(ctx) * DEG)


@register("hold", "track_breathe")
class TrackBreathe(_Hold):
    name = "Breathing Spacing"
    tags = ("calm", "editorial")
    weight = 0.5

    def evaluate(self, ctx, s):
        o, axis = _along(ctx)
        f = np.sin(s * TAU / 2.8) * 0.075 * _k(ctx)
        return _out(ctx, s, **{("dz" if axis == 2 else "dx"): o * f})


@register("hold", "skew_wobble")
class SkewWobble(_Hold):
    name = "Slanted Wobble"
    tags = ("pop", "glitch")
    weight = 0.4

    def evaluate(self, ctx, s):
        return _out(ctx, s, roll=-np.sin(s * TAU / 1.9) * 8 * _k(ctx) * DEG)


@register("hold", "beat_hop")
class BeatHop(_Hold):
    name = "Beat Hop"
    tags = ("pop",)
    weight = 0.5

    def evaluate(self, ctx, s):
        beat = _beat(ctx, 0.45)
        u = np.mod(s, beat) / (beat * 0.85)
        h = np.where(u < 1, np.sin(np.pi * clip(u)) ** 0.7, 0.0)
        cur = np.mod(np.floor(s / beat), ctx.n)
        d = np.abs(_gi(ctx) - cur)
        w = np.where(d == 0, 1.0, np.where(d == 1, 0.3, 0.0))
        k = _k(ctx)
        return _out(ctx, s, dz=h * w * ctx.em * 0.2 * k, sz=1 + 0.08 * h * w * k, sx=1 - 0.05 * h * w * k)


@register("hold", "h_wave")
class HWave(_Hold):
    name = "Sideways Wave"
    tags = ("pop", "emotional")
    weight = 0.4

    def evaluate(self, ctx, s):
        a = s * TAU * 0.55 - _gi(ctx) * 0.9
        k = _k(ctx)
        return _out(ctx, s, dx=np.sin(a) * ctx.em * 0.085 * k, roll=-np.cos(a) * 5 * k * DEG)


@register("hold", "heartbeat")
class Heartbeat(_Hold):
    name = "Heartbeat"
    tags = ("emotional", "pop")
    weight = 0.4

    def evaluate(self, ctx, s):
        u = np.mod(s, 2 * _beat(ctx, 0.525))
        v = np.exp(-u * 9) + np.where(u > 0.2, 0.75 * np.exp(-(u - 0.2) * 9), 0.0)
        f = 1 + 0.055 * v * _k(ctx)
        return _out(ctx, s, sx=f, sz=f)


@register("hold", "orbit_small")
class OrbitSmall(_Hold):
    name = "Small Circles"
    tags = ("calm", "pop")
    weight = 0.5

    def evaluate(self, ctx, s):
        side = 1 if (ctx.seed >> 2) & 1 else -1
        t = s * TAU / 1.7 * side + _gi(ctx) * 0.9
        r = ctx.em * 0.05 * _k(ctx)
        return _out(ctx, s, dx=(np.cos(t) - np.cos(_gi(ctx) * 0.9)) * r, dz=-(np.sin(t) - np.sin(_gi(ctx) * 0.9)) * r)


@register("hold", "jelly")
class Jelly(_Hold):
    name = "Jelly"
    tags = ("pop",)
    weight = 0.4

    def evaluate(self, ctx, s):
        bs = np.mod(s, _beat(ctx)) - _gi(ctx) * 0.03
        w = np.exp(-np.maximum(bs, 0) * 4.5) * np.sin(np.maximum(bs, 0) * 21)
        a = 0.1 * w * _k(ctx)
        return _out(ctx, s, sx=1 + a, sz=1 - a, dz=-a * ctx.em * 0.5)        # squashed on its baseline


@register("hold", "noise_drift")
class NoiseDrift(_Hold):
    name = "Noisy Drift"
    tags = ("calm", "emotional")
    weight = 0.6

    def evaluate(self, ctx, s):
        t, i, k = s * 0.35, _gi(ctx), _k(ctx)
        a = ctx.em * 0.075 * k
        return _out(ctx, s, dx=noise1_np(t + i * 1.7, ctx.seed + 11) * a, dz=-noise1_np(t + i * 2.3, ctx.seed + 23) * a,
                    roll=noise1_np(t * 1.3 + i * 0.9, ctx.seed + 37) * 7 * k * DEG)


@register("hold", "tilt")
class Tilt(_Hold):
    name = "Seesaw"
    tags = ("calm", "editorial")
    weight = 0.4

    def evaluate(self, ctx, s):
        o, axis = _along(ctx)
        tn = np.tan(np.sin(s * TAU / 4.2 + ctx.seed % 5) * 4 * _k(ctx) * DEG)
        return _out(ctx, s, **({"dx": -o * tn} if axis == 2 else {"dz": o * tn}))   # the baseline tilts, glyphs upright


@register("hold", "zoom_slow")
class ZoomSlow(_Hold):
    name = "Slow Swell"
    tags = ("calm", "emotional", "editorial")
    weight = 0.8

    def evaluate(self, ctx, s):
        u = clip(s / max(0.3, ctx.end - ctx.start))
        f = 1 + 0.07 * (1 - (1 - u) ** 2) * _k(ctx)
        o, axis = _along(ctx)
        return _out(ctx, s, sx=f, sz=f, **{("dz" if axis == 2 else "dx"): o * (f - 1)})


@register("hold", "stretch_pulse")
class StretchPulse(_Hold):
    name = "Stretch on the Beat"
    tags = ("pop", "graphic")
    weight = 0.4

    def evaluate(self, ctx, s):
        kick = np.exp(-np.mod(s, _beat(ctx)) * 8) * _k(ctx)
        o, axis = _along(ctx)
        sx, sz = 1 + 0.12 * kick, 1 - 0.045 * kick
        return _out(ctx, s, sx=sx, sz=sz, **{("dz" if axis == 2 else "dx"): o * ((sz if axis == 2 else sx) - 1)})


@register("hold", "glitch_jump")
class GlitchJump(_Hold):
    name = "Sudden Slips"
    tags = ("glitch",)
    weight = 0.4

    def evaluate(self, ctx, s):
        step = np.floor(s * STEP)
        slot = np.floor(step / 8)
        on = (step - slot * 8 <= 2) & (_r(ctx.seed, slot, 501) <= 0.55)
        k = _k(ctx)
        dx = np.where(on, _rs(ctx.seed, slot, 502) * ctx.em * 0.2 * k, 0.0)
        dz = np.where(on, -_rs(ctx.seed, slot, 503) * ctx.em * 0.04 * k, 0.0)
        return _out(ctx, s, dx=np.broadcast_to(dx, s.shape), dz=np.broadcast_to(dz, s.shape))


@register("hold", "glow_flicker")
class GlowFlicker(_Hold):
    name = "Candle Flicker"
    tags = ("calm", "emotional")
    weight = 0.5

    def evaluate(self, ctx, s):
        k, seed = _k(ctx), ctx.seed
        f = 0.6 + 0.28 * noise1_np(s * 3.3, seed) + 0.12 * noise1_np(s * 11, seed + 5)
        x = clip((noise1_np(s * 1.1, seed + 9) - 0.35) / 0.45)
        lvl = clip(f * (1 - 0.45 * x * x * (3 - 2 * x)))
        st = 1 + 0.025 * k * (0.5 + 0.5 * noise1_np(s * 6 + _gi(ctx) * 2.3, seed + _gi(ctx)))
        return _out(ctx, s, a=1 - 0.16 * (1 - lvl) * min(1.0, k), sz=st, dz=(st - 1) * ctx.em * 0.5)


@register("hold", "wind_gust")
class WindGust(_Hold):
    name = "Gust of Wind"
    tags = ("pop", "emotional")
    weight = 0.5

    def evaluate(self, ctx, s):
        per = 4 * _beat(ctx) if ctx.bpm > 0 else 2.2
        t = s - 0.5
        cyc = np.floor(t / per)
        since = t - cyc * per
        side = np.where(_r(ctx.seed, cyc, 601) < 0.5, 1.0, -1.0)
        strength = (0.7 + 0.3 * _r(ctx.seed, cyc, 602)) * _k(ctx)
        order = _gi(ctx) / max(1, ctx.n - 1)
        tau = since - np.where(side > 0, order, 1 - order) * 0.4
        x = clip(tau / 0.25)
        r = np.where(tau < 0.25, x * x * (3 - 2 * x),
                     np.where(tau < 0.6, 1 + 0.08 * np.sin((tau - 0.25) * 30),
                              np.cos((tau - 0.6) * 9) * np.exp(-(tau - 0.6) * 4)))
        r = np.where((tau <= 0) | (tau > 1.7) | (t < 0), 0.0, r)
        return _out(ctx, s, dx=side * ctx.em * 0.12 * r * strength, roll=side * 6 * r * strength * DEG)


@register("hold", "dangle")
class Dangle(_Hold):
    name = "Dangling"
    tags = ("calm", "emotional")
    weight = 0.5

    def evaluate(self, ctx, s):
        i = np.arange(ctx.n)
        w = (TAU * (0.5 + 0.28 * _r(ctx.seed, i, 611)))[:, None]
        ph = (_r(ctx.seed, i, 612) * TAU)[:, None]
        th = (6.5 * np.sin(w * s + ph) + 1.6 * np.sin(w * 2.7 * s + ph * 2)) * _k(ctx) * DEG
        pivot = np.zeros((ctx.n, 3))
        pivot[:, 2] = ctx.em / 2                                              # hung by its top edge
        return _about(ctx, s, pivot, np.zeros((ctx.n, 3)), th)


@register("hold", "eq_bounce")
class EqBounce(_Hold):
    name = "Equalizer Bounce"
    tags = ("pop", "graphic")
    weight = 0.5

    def evaluate(self, ctx, s):
        base = 0.25 + 0.75 * np.exp(-np.mod(s, _beat(ctx)) * 7)
        band = clip(base * (0.3 + 0.7 * (0.5 + 0.5 * noise1_np(s * 6.5 + _gi(ctx) * 1.9, ctx.seed + 3))) * 1.15)
        st = 1 + 0.32 * band * _k(ctx)
        return _out(ctx, s, sz=st, dz=(st - 1) * ctx.em * 0.5)                # grows up from its baseline


@register("hold", "flip_swap")
class FlipSwap(_Hold):
    name = "Occasional Flip"
    tags = ("glitch", "pop")
    weight = 0.4

    def evaluate(self, ctx, s):
        per, t = 1.6, s - 0.45
        cyc = np.floor(t / per)
        u = (t - cyc * per) / 0.95
        pick = np.mod(h_np(ctx.seed, cyc, 631), ctx.n)
        flip = np.where(u < 0.18, np.cos(u / 0.18 * np.pi / 2),
                        np.where(u < 0.36, np.sin((u - 0.18) / 0.18 * np.pi / 2),
                                 np.where(u < 0.64, 1.0, np.where(u < 0.82, np.cos((u - 0.64) / 0.18 * np.pi / 2),
                                                                  np.sin((u - 0.82) / 0.18 * np.pi / 2)))))
        sx = np.where((u < 1) & (t >= 0) & (_gi(ctx) == pick), np.maximum(0.02, flip), 1.0)
        return _out(ctx, s, sx=sx)


@register("hold", "magnet")
class Magnet(_Hold):
    name = "Magnet Pull"
    tags = ("pop", "glitch")
    weight = 0.4

    def evaluate(self, ctx, s):
        o, axis = _along(ctx)
        width = max(float(o.max() - o.min()), ctx.em)
        mx = np.sin(s * 0.9 + ctx.seed % 9) * width * 0.5
        mz = np.sin(s * 1.7 + 1) * ctx.em * 0.9
        gx, gz = (o, 0.0) if axis == 0 else (0.0, o)
        vx, vz = mx - gx, mz - gz
        d = np.maximum(np.hypot(vx, vz), 1e-6)
        f = 1 / (1 + (d / (ctx.em * 1.1)) ** 2)
        k = _k(ctx)
        pull = ctx.em * 0.2 * f * k
        buzz = np.where(f > 0.35, _rs(ctx.seed, np.floor(s * STEP), _gi(ctx), 641) * ctx.em * 0.014 * k * f, 0.0)
        return _out(ctx, s, dx=vx / d * pull + buzz, dz=vz / d * pull, roll=vx / d * 7 * f * k * DEG)


@register("hold", "type_rattle")
class TypeRattle(_Hold):
    name = "Typewriter Rattle"
    tags = ("editorial", "glitch")
    weight = 0.5

    def evaluate(self, ctx, s):
        beat = _beat(ctx, 0.45)
        idx, since, i, seed = np.floor(s / beat), np.mod(s, beat), _gi(ctx), ctx.seed
        ep = np.full(s.shape, -1.0)
        for b in range(6, -1, -1):                     # the latest of the last 7 beats this glyph was struck
            ep = np.where(_r(seed, idx - b, i, 651) < 0.3, idx - b, ep)
        hit = np.where((ep == idx) & (since < 0.1), 1 - since / 0.1, 0.0)
        k, kk = _k(ctx), min(1.0, _k(ctx))
        return _out(ctx, s, dz=-_rs(seed, ep, i, 652) * ctx.em * 0.045 * k - hit * ctx.em * 0.04 * k,
                    dx=_rs(seed, ep, i, 655) * ctx.em * 0.01 * k, roll=_rs(seed, ep, i, 653) * 3.2 * k * DEG,
                    a=1 - 0.2 * _r(seed, ep, i, 654) * kk - 0.15 * hit * kk)


@register("hold", "pluck_string")
class PluckString(_Hold):
    name = "Plucked String"
    tags = ("pop", "emotional")
    weight = 0.4

    def evaluate(self, ctx, s):
        tau = np.mod(s, 4 * _beat(ctx)) if ctx.bpm > 0 else np.mod(s - 0.45, 2.4)
        a = ctx.em * 0.18 * _k(ctx) * np.exp(-tau * 1.7) * clip(tau / 0.04)
        x = (_gi(ctx) + 1) / (ctx.n + 1)
        y = a * (np.sin(np.pi * x) * np.cos(tau * TAU * 3.2) + 0.3 * np.sin(TAU * x) * np.cos(tau * TAU * 6.6 + 1))
        o, axis = _along(ctx)
        return _out(ctx, s, **{("dx" if axis == 2 else "dz"): y})


# ---------------- horror ----------------

class _Horror(_Hold):
    group = "horror"


@register("hold", "hr_twitch")
class Twitch(_Horror):
    name = "Twitch"
    tags = ("horror", "glitch")

    def evaluate(self, ctx, s):
        st, k, seed = np.floor(s * STEP), _k(ctx), ctx.seed
        fire = _r(seed, st, 101) <= 0.07 * k
        who = (_r(seed, st, 102) < 0.25) | (_gi(ctx) == np.mod(h_np(seed, st, 103), ctx.n))
        on = fire & who
        return _out(ctx, s, dx=np.where(on, _rs(seed, st, 104) * ctx.em * 0.22 * k, 0.0),
                    dz=np.where(on, -_rs(seed, st, 105) * ctx.em * 0.14 * k, 0.0),
                    roll=np.where(on, _rs(seed, st, 106) * 28 * k * DEG, 0.0),
                    sx=np.where(on, 1 + _r(seed, st, 107) * 0.12 * k, 1.0), sz=np.where(on, 1 + _r(seed, st, 107) * 0.12 * k, 1.0))


@register("hold", "hr_stare")
class Stare(_Horror):
    name = "Staring Letter"
    tags = ("horror", "emotional")
    weight = 0.8

    def evaluate(self, ctx, s):
        t = s - 0.3
        cyc = np.floor(t / 2)
        u = (t - cyc * 2) / 2
        q = np.where(u < 0.6, in_out_sine(u / 0.6), np.where(u < 0.85, 1.0, 1 - out_expo((u - 0.85) / 0.15)))
        q = np.where(t <= 0, 0.0, q)
        on = _gi(ctx) == np.mod(h_np(ctx.seed, cyc, 111), ctx.n)
        side = np.where(h_np(ctx.seed, cyc, 112) & 1, 1.0, -1.0)
        k = _k(ctx)
        f = np.where(on, 1 + 0.12 * q * k, 1.0)
        return _out(ctx, s, roll=np.where(on, side * 22 * q * k * DEG, 0.0), sx=f, sz=f,
                    dz=np.where(on, ctx.em * 0.04 * q * k, 0.0))


@register("hold", "hr_lag_one")
class LagOne(_Horror):
    name = "One Letter Late"
    tags = ("horror", "calm")
    weight = 0.8

    def evaluate(self, ctx, s):
        late = _gi(ctx) == ctx.seed % ctx.n
        t = np.where(late, s - 0.75, s)
        k, seed = _k(ctx), ctx.seed
        return _out(ctx, s, dx=noise1_np(t * 0.9, seed) * ctx.em * 0.1 * k, dz=-noise1_np(t * 0.7 + 5, seed + 1) * ctx.em * 0.06 * k,
                    roll=noise1_np(t * 0.5 + 9, seed + 2) * 4 * k * DEG)


@register("hold", "hr_flicker")
class FlickerLight(_Horror):
    name = "Failing Light"
    tags = ("horror", "glitch", "emotional")
    weight = 0.9

    def evaluate(self, ctx, s):
        st, seed, k = np.floor(s * STEP), ctx.seed, min(1.3, max(0.4, _k(ctx)))
        lvl = 0.9 + 0.1 * _r(seed, st, 131)
        dark = _r(seed, np.floor(st / 2), 132) < 0.09 * k
        lvl = np.where(dark, np.where(_r(seed, st, 133) < 0.5, 0.08, 0.35), np.where(_r(seed, st, 134) < 0.05 * k, 0.5, lvl))
        return _out(ctx, s, a=np.broadcast_to(1 - (1 - lvl) * min(1.0, k), s.shape))


# ---------------- kinetic (word by word) ----------------

class _Kinetic(_Hold):
    group = "kinetic"

    def mot(self, ctx):
        return 0.4 + ctx.strength


@register("hold", "kn_word_pulse")
class WordPulse(_Kinetic):
    name = "Word Beat"
    tags = ("pop", "graphic")

    def evaluate(self, ctx, s):
        pos, centres, w, n = _word_centres(ctx)
        beat = _beat(ctx, 0.52)
        cur = np.mod(np.floor(s / beat), n)
        f = 1 + np.where(w[:, None] == cur, np.exp(-np.mod(s, beat) * 4) * 0.14 * self.mot(ctx), 0.0)
        d = (pos - centres)[:, None, :] * (f[..., None] - 1)
        return _out(ctx, s, dx=d[..., 0], dz=d[..., 2], sx=f, sz=f)


@register("hold", "kn_counter_rock")
class CounterRock(_Kinetic):
    name = "Counter Rocking"
    tags = ("pop", "calm", "graphic")
    weight = 0.9

    def evaluate(self, ctx, s):
        pos, centres, w, n = _word_centres(ctx)
        a = 4 * self.mot(ctx) * np.sin(s * TAU * 0.55) * DEG * np.where(w % 2, -1.0, 1.0)[:, None] * (0.6 if n == 1 else 1.0)
        return _about(ctx, s, centres, pos, a)


@register("hold", "kn_word_ride")
class WordRide(_Kinetic):
    name = "Words Riding a Wave"
    tags = ("calm", "emotional", "pop")
    weight = 0.9

    def evaluate(self, ctx, s):
        pos, centres, w, n = _word_centres(ctx)
        ph = s * 3.1 - w[:, None] * 1.25
        return _about(ctx, s, centres, pos, -np.cos(ph) * 3.5 * DEG, extra_dz=ctx.em * 0.07 * self.mot(ctx) * np.sin(ph))


@register("hold", "kn_tick_shift")
class TickShift(_Kinetic):
    name = "Ticking Shift"
    tags = ("graphic", "pop", "editorial")
    weight = 0.8

    def evaluate(self, ctx, s):
        beat = _beat(ctx)
        side = np.where(np.mod(np.floor(s / beat), 2), 1.0, -1.0)
        e = out_back(clip(np.mod(s, beat) / 0.09), 2.6)
        x = (-side + (2 * side) * e) * ctx.em * 0.05 * self.mot(ctx)
        o, axis = _along(ctx)
        return _out(ctx, s, **{("dz" if axis == 2 else "dx"): np.broadcast_to(x, s.shape)})


@register("hold", "kn_beat_lean")
class BeatLean(_Kinetic):
    name = "Leaning on the Beat"
    tags = ("pop", "glitch", "graphic")
    weight = 0.8

    def evaluate(self, ctx, s):
        beat = _beat(ctx, 0.55)
        since, idx = np.mod(s, beat), np.floor(s / beat)
        a = 7 * self.mot(ctx) * np.exp(-since * 4.5) * np.cos(since * 15) * DEG
        w = _words(ctx)[:, None]
        return _out(ctx, s, roll=a * np.where(np.mod(w + idx, 2), 1.0, -1.0))


@register("hold", "kn_gap_breath")
class GapBreath(_Kinetic):
    name = "Breathing Gaps"
    tags = ("calm", "editorial", "emotional")
    weight = 0.9

    def evaluate(self, ctx, s):
        w = _words(ctx)[:, None]
        n = int(w.max()) + 1 if ctx.n else 1
        a = ctx.em * 0.16 * self.mot(ctx) * (0.5 - 0.5 * np.cos(s * TAU * 0.4)) * (n > 1)
        o, axis = _along(ctx)
        return _out(ctx, s, **{("dz" if axis == 2 else "dx"): (w - (n - 1) / 2) * a * (-1 if axis == 2 else 1)})


# ---------------- typography ----------------

class _Typo(_Hold):
    group = "typo"


def _key_glyph(ctx):
    """The glyph that carries the line: the first kanji, else the middle one."""
    chars = getattr(ctx, "chars", None) or ()
    for i, ch in enumerate(chars):
        if "一" <= ch <= "鿿" or ch == "々":
            return i
    return ctx.n // 2


@register("hold", "ty_key_pulse")
class KeyPulse(_Typo):
    name = "One Letter's Heartbeat"
    tags = ("emotional", "pop", "calm")

    def evaluate(self, ctx, s):
        beat = _beat(ctx, 0.5)
        pulse = np.exp(-np.mod(s, beat) / max(0.12, beat * 0.35))
        f = np.where(_gi(ctx) == _key_glyph(ctx), 1 + 0.1 * _k(ctx) * pulse, 1.0)
        return _out(ctx, s, sx=f, sz=f)


@register("hold", "ty_read_cursor")
class ReadCursor(_Typo):
    name = "Reading Along"
    tags = ("calm", "editorial", "pop")

    def evaluate(self, ctx, s):
        rate = 1 / max(0.2, _beat(ctx, 0.25))
        x = s * rate
        pos, frac = np.mod(np.floor(x), ctx.n + 2), np.mod(x, 1)
        up = out_cubic(clip(frac * 4)) * (1 - in_cubic(clip((frac - 0.6) / 0.4)))
        return _out(ctx, s, dz=np.where(_gi(ctx) == pos, ctx.em * 0.07 * min(1.0, _k(ctx)) * up, 0.0))


@register("hold", "ty_track_step")
class TrackStep(_Typo):
    name = "Spacing Steps"
    tags = ("graphic", "editorial", "pop")
    weight = 0.8

    def evaluate(self, ctx, s):
        t = s / max(0.25, _beat(ctx, 0.55))
        k, f = np.floor(t), t - np.floor(t)
        lv = np.array([0.0, 1.0, 2.0, 1.0])
        a, b = lv[np.mod(k, 4).astype(int)], lv[np.mod(k + 1, 4).astype(int)]
        v = a + (b - a) * out_expo(clip((f - 0.85) / 0.15))
        o, axis = _along(ctx)
        off = o / max(ctx.em, 1e-6) * v * 0.05 * ctx.em * _k(ctx)
        return _out(ctx, s, **{("dz" if axis == 2 else "dx"): off})
