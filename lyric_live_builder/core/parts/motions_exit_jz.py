# Exits ported from JIZURA (src/05_anim.js J.EXIT, src/11p_exit.js, src/11p_exitB.js, src/11p_horror*.js,
# src/11p_kinetic*.js, src/11p_typo*.js), MIT License, Copyright (c) 2026 hakoniwa. Rewritten for 3D text in VR.
"""Exits added from JIZURA v0.10 (spec §7.4, design §5.6).

The same conventions as motions_enter_jz: stagger 0 and JIZURA's per-glyph windows, dx / dy in em (dy down),
rot in degrees clockwise. p = 0 is the rest pose, p = 1 has left. JIZURA's screen sizes become em: about
10 em across and 6 em down. Parts that cut glyphs use the mask with a falling progress (1 -> 0): a window
(kind 9) for sinking, rising, draining and line feeds; the line masks for the wipe, iris, diagonal, blinds and
checker. Band exits (slice, glitch, split, vertical slice) hand the glyph over to band copies at the exit's
start (design §5.6). 2D decorations (bars, rays, strings, smoke, drips) and symbol swaps are left out."""
import numpy as np

from ..registry import Delta, register
from ..rng import noise1_np
from .common import clip, in_cubic, in_expo, in_out_sine
from .motions_enter_jz import (DEG, TAU, _Enter, _LineMask, _r, _rs, _turn, centred, gi, io_cubic, key_glyph,
                               o_cubic, ord_lr, ord_rl, out, side, smooth, stg, whole, words)

SCREEN_W, SCREEN_H = 10.0, 6.0                    # em: JIZURA's canvas, for "off the screen" distances


def in_quad(x):
    return clip(x) ** 2


def io_expo(x):
    x = clip(x)
    with np.errstate(over="ignore"):
        v = np.where(x < 0.5, 2.0 ** (20 * x - 10) / 2, (2 - 2.0 ** (-20 * x + 10)) / 2)
    return np.where(x <= 0, 0.0, np.where(x >= 1, 1.0, v))


def bell(x):
    return np.sin(np.pi * clip(x))


def step(p, rate=14):
    """JIZURA's env.step: a frame number for random flicker (about 14 per exit)."""
    return np.floor(p * rate)


class _Exit(_Enter):
    """Same defaults as the JIZURA entrances (stagger 0, group extra)."""


def xpart(key, name, tags, weight=1.0, duration=0.6, group="extra"):
    def deco(fn):
        cls = type(f"x_{key}", (_Exit,), {"name": name, "tags": tuple(tags), "weight": weight,
                                         "duration": duration, "group": group,
                                         "evaluate": lambda self, ctx, p: fn(ctx, p)})
        register("exit", key)(cls)
        return cls
    return deco


# ---------------- basic set (JIZURA's core exits) ----------------

@xpart("cut", "Cut Away", (), 0.6, 0.12, group="basic")
def cut(ctx, p):
    return out(ctx, p, hide=p > 0)


@xpart("blur", "Blur Away", ("calm", "pop", "editorial", "emotional", "horror"), group="basic")
def blur(ctx, p):
    e = in_quad(p)
    return whole(ctx, p, s=1 + 0.2 * e, a=1 - e)


@xpart("stretch", "Stretch Away", ("pop", "graphic"), group="basic")
def stretch(ctx, p):
    e = in_expo(p)
    return whole(ctx, p, sx=1 + 5 * e, sy=1 - 0.4 * e, a=1 - smooth(0.7, 1, p))


@xpart("scatter", "Scatter Away", ("pop",), group="basic")
def scatter(ctx, p):
    i = gi(ctx)
    q = clip((p - _r(ctx.seed, i, 51) * 0.35) / 0.65)
    e = in_cubic(q)
    ang = _r(ctx.seed, i, 52) * TAU
    return out(ctx, p, dx=np.cos(ang) * SCREEN_W * 0.7 * e, dy=np.sin(ang) * SCREEN_W * 0.45 * e,
               rot=_rs(ctx.seed, i, 53) * 540 * e, s=1 + 0.8 * e, a=1 - q * q, hide=q >= 1)


class _BandsOut(_Exit):
    """The glyph hands over to its band copies at the exit's start (design §5.6)."""
    band_copies = 1

    def evaluate(self, ctx, p):
        return Delta(ctx.n, p.shape[1], alpha=(p <= 0).astype(float))


@register("exit", "slice")
class SliceOut(_BandsOut):
    """Seven bands fly out to alternate sides."""
    name = "Slice Away"
    tags = ("glitch", "graphic")
    group = "basic"

    def band_count(self, width_em):
        return 7

    def band_motion(self, p, b, n, k, g, width, height, em):
        far = width * 1.1 * (0.6 + 0.4 * float(_r(b, k, 41)))
        return in_expo(p) * (1 if b % 2 else -1) * far, 0.0 * p

    def band_fade(self, p, b, n, k, g):
        return 1 - smooth(0.7, 1, p)


@register("exit", "glitch")
class GlitchOut(_BandsOut):
    """Nine bands jump sideways more and more; the line flickers and goes."""
    name = "Glitch Away"
    tags = ("glitch", "horror")
    group = "basic"

    def band_count(self, width_em):
        return 9

    def band_motion(self, p, b, n, k, g, width, height, em):
        st = step(p)
        amp = (0.3 + 2.2 * p) * em
        return np.where(_r(st, b, k, 61) < 0.75, _rs(st, b, k, 62) * amp, 0.0), 0.0 * p

    def band_fade(self, p, b, n, k, g):
        flick = np.where((p > 0.55) & (_r(step(p), k, 63) < 0.5), 0.15, 1.0)
        return flick * (1 - smooth(0.8, 1, p))


# ---------------- line masks (falling progress) ----------------

@register("exit", "wipe")
class WipeOut(_LineMask):
    """An edge with the accent bar runs from left to right and takes the line with it."""
    name = "Wipe Away"
    tags = ("calm", "graphic", "editorial")
    group = "basic"
    line_fx = True

    def mask_shape(self, ctx):
        return (1.0, 1.0, 0.0, 0.0)                       # shown right of the edge

    def evaluate(self, ctx, p):
        return Delta(ctx.n, p.shape[1], mask=np.broadcast_to(1 - io_expo(p), p.shape).copy(),
                     alpha=(p < 1).astype(float))


class _LineOut(_LineMask):
    def evaluate(self, ctx, p):
        return Delta(ctx.n, p.shape[1], mask=np.broadcast_to(1 - self.ease(p), p.shape).copy(),
                     alpha=(p < 1).astype(float))

    def ease(self, p):
        return clip(p)


@register("exit", "iris_close")
class IrisClose(_LineOut):
    name = "Iris Close"
    tags = ("graphic", "pop", "editorial")
    mask_kind = 5.0
    line_fx = True

    def ease(self, p):
        return io_cubic(p)


@register("exit", "diag_wipe")
class DiagWipeOut(_LineOut):
    name = "Diagonal Wipe Away"
    tags = ("graphic", "editorial")
    mask_kind = 6.0


@register("exit", "blinds")
class BlindsClose(_LineOut):
    name = "Blinds Close"
    tags = ("graphic", "editorial")
    weight = 0.9
    mask_kind = 7.0


@register("exit", "checker")
class CheckerOut(_LineOut):
    name = "Checkerboard Away"
    tags = ("graphic", "glitch")
    weight = 0.8

    def mask_shape(self, ctx):
        return (3.0, 0.34, float(ctx.seed % 997), 0.0)


# ---------------- glyph windows (kind 9, falling progress) ----------------

class _WindowOut(_Exit):
    uses_mask = True
    mask_cell = (-2.0, -0.66, 2.0, 0.66)
    shift = -1.4                                         # glyph's offset up (em) when the mask reaches 0

    def mask_shape(self, ctx):
        return (9.0, 0.0, self.shift, 0.0)


@register("exit", "sink")
class SinkOut(_WindowOut):
    """Each glyph sinks below its own baseline, after a tiny lift."""
    name = "Sink Below"
    tags = ("calm", "editorial", "graphic")

    def evaluate(self, ctx, p):
        q = stg(p, ord_lr(ctx), 0.5)
        d = (io_cubic(q) - 0.06 * np.sin(np.pi * clip(q / 0.3))) * 1.4
        return out(ctx, p, dy=d, mask=1 - d / 1.4, hide=q >= 1)


@register("exit", "rise_out")
class RiseOut(_WindowOut):
    """Glyphs slip up out of their frames in a random order."""
    name = "Slip Out Upward"
    tags = ("calm", "emotional", "editorial")
    shift = 1.5

    def evaluate(self, ctx, p):
        q = stg(p, _r(ctx.seed, gi(ctx), 201), 0.5)
        e = q ** 2.2
        return out(ctx, p, dy=-1.5 * e, mask=1 - e, hide=q >= 1)


@register("exit", "drain")
class Drain(_WindowOut):
    """The glyphs drain away from the top down."""
    name = "Drain Down"
    tags = ("horror", "emotional")
    weight = 0.8
    duration = 1.1
    group = "horror"
    mask_cell = (-2.0, -0.7, 2.0, 0.7)
    shift = 1.4                                          # no motion: the frame's top comes down

    def evaluate(self, ctx, p):
        lev = in_out_sine(clip((p - ord_lr(ctx) * 0.25) / 0.72))
        return out(ctx, p, mask=1 - lev, hide=lev >= 0.995)


@register("exit", "flood")
class Flood(_WindowOut):
    """The water line rises over the glyphs from the bottom."""
    name = "Under the Water"
    tags = ("emotional", "calm")
    weight = 0.9
    duration = 0.8
    mask_cell = (-2.0, -0.7, 2.0, 0.7)
    shift = -1.4

    def evaluate(self, ctx, p):
        e = in_out_sine(clip(p / 0.9))
        return out(ctx, p, mask=np.broadcast_to(1 - e, p.shape), hide=p >= 0.999)


@register("exit", "ty_line_feed")
class LineFeed(_WindowOut):
    """The line is fed up out of its frame in three steps."""
    name = "Line Feed"
    tags = ("editorial", "calm", "graphic")
    group = "typo"
    shift = 1.3

    def evaluate(self, ctx, p):
        k = clip(p) * 3
        st = np.minimum(3, np.floor(k))
        st_p = np.minimum(1, (st + o_cubic(clip((k - st) * 2.6))) / 3)
        return out(ctx, p, dy=-1.3 * st_p, mask=1 - st_p, hide=p >= 0.999)


# ---------------- band copies ----------------

@register("exit", "split_apart")
class SplitApart(_BandsOut):
    """A hairline crack, then each glyph's halves spring apart up and down."""
    name = "Split Apart"
    tags = ("graphic", "pop")

    def band_count(self, width_em):
        return 2

    def band_motion(self, p, b, n, k, g, width, height, em):
        off = clip(p / 0.2) * 0.03 + 0.75 * o_cubic(clip((p - 0.16) / 0.84))
        sgn = -1 if b == 0 else 1                           # bottom half down, top half up
        return -sgn * off * 0.3 * em, sgn * off * em

    def band_fade(self, p, b, n, k, g):
        return 1 - smooth(0.35, 1, clip((p - 0.16) / 0.84))


@register("exit", "v_slice_drop")
class VSliceDrop(_BandsOut):
    """Vertical strips of the line drop away one by one."""
    name = "Vertical Slices Drop"
    tags = ("graphic", "glitch")
    weight = 0.9
    band_axis = "x"

    def band_count(self, width_em):
        return int(np.clip(round((width_em + 0.6) / 0.55), 4, 8))

    def band_motion(self, p, b, n, k, g, width, height, em):
        q = clip((p - float(_r(b, 301)) * 0.45) / 0.55)
        return 0.0 * p, -(q * q * 1.05 - np.sin(np.pi * clip(q / 0.25)) * 0.012) * (height + 4 * em)

    def band_fade(self, p, b, n, k, g):
        return 1 - smooth(0.95, 1, p)


# ---------------- glyph motions ----------------

def _slide_out(key, name, dir_):
    @xpart(key, name, ("pop", "graphic"), 0.8)
    def fn(ctx, p):
        o = ord_lr(ctx) if dir_ < 0 else 1 - ord_lr(ctx)          # the leading edge leaves first
        q = stg(p, o, 0.5)
        wind = np.where(q < 0.24, np.sin(q / 0.24 * np.pi) * 0.07, 0.0)
        u = clip((q - 0.1) / 0.9)
        v = 3 * u * u
        dist = SCREEN_W + ctx.n + 1.5
        return out(ctx, p, dx=dir_ * (dist * u ** 3 - wind), sx=1 + np.minimum(1.3, v * 0.45),
                   sy=1 - np.minimum(0.28, v * 0.09), a=1 - smooth(0.82, 1, q), hide=q >= 1)
    return fn


_slide_out("slide_out_l", "Stream Off Left", -1)
_slide_out("slide_out_r", "Stream Off Right", 1)


@xpart("door_close", "Door Closes", ("graphic", "pop", "editorial"))
def door_close(ctx, p):
    q = stg(p, ord_lr(ctx), 0.5)
    th = in_quad(q) * np.pi / 2
    c, s = np.cos(th), np.sin(th)
    d = 1.0 if _r(ctx.seed, 1, 991) < 0.5 else -1.0              # hinge side
    return out(ctx, p, sx=c, sy=1 + 0.14 * s, dx=d * (1 - c) * 0.5, back=0.5 * s, a=1 - smooth(0.8, 1, q),
               hide=q >= 1)


@xpart("fall_back", "Fall Flat", ("pop", "graphic"), 0.9)
def fall_back(ctx, p):
    q = stg(p, _r(ctx.seed, gi(ctx), 211), 0.5)
    th = in_quad(q) * np.pi / 2
    c, s = np.cos(th), np.sin(th)
    return out(ctx, p, sy=c, sx=1 - 0.12 * s, dy=(1 - c) * 0.5, back=0.5 * s, hide=q >= 1)


@xpart("squash", "Squash Flat", ("glitch", "pop", "graphic"), 0.9)
def squash(ctx, p):
    a1, a2 = clip(p / 0.42), clip((p - 0.4) / 0.45)
    ky = 1 - 0.97 * in_cubic(a1)
    kx = (1 + 0.08 * o_cubic(a1)) * (1 - io_cubic(a2))
    return whole(ctx, p, sx=np.maximum(kx, 0.01), sy=ky, a=(kx > 0.01).astype(float))


@xpart("track_out", "Spacing Drifts Apart", ("calm", "emotional", "editorial"))
def track_out(ctx, p):
    cx, _ = centred(ctx)
    k = in_quad(p) * 1.6 + clip(p) * 0.3
    return out(ctx, p, dx=cx * k, sx=1 - 0.6 * in_quad(p), a=1 - smooth(0.2, 1, p))


@xpart("suck_in", "Sucked In", ("pop", "graphic"), 0.9)
def suck_in(ctx, p):
    cx, cz = centred(ctx)
    e = in_quad(p)
    big = max(1.0, float(np.hypot(np.ptp(cx) + 1, np.ptp(cz) + 1)) * 0.5) if ctx.n else 1.0
    turn = (1 if _r(ctx.seed, 2, 991) < 0.5 else -1) * e
    phi = turn * (140 + 220 * (1 - clip(np.hypot(cx, cz) / big)))
    r = phi * DEG
    nx, nz = (np.cos(r) * cx + np.sin(r) * cz) * (1 - e), (-np.sin(r) * cx + np.cos(r) * cz) * (1 - e)
    return out(ctx, p, dx=nx - cx, dy=-(nz - cz), rot=phi, s=np.maximum(0.02, 1 - 0.94 * e),
               a=1 - smooth(0.8, 1, p))


@xpart("zoom_far", "Recede into the Distance", ("emotional", "calm"))
def zoom_far(ctx, p):
    cx, cz = centred(ctx)
    e = 1 - (1 - clip(p)) ** 2.6                                  # fast recede, slow settle
    s = 1 - 0.8 * e
    return out(ctx, p, dx=cx * (s - 1), dy=-cz * (s - 1) - 0.35 * e, s=s, back=3.0 * e,
               a=1 - smooth(0.5, 1, p))


@xpart("spin_out", "Spin Away", ("pop",), 0.9)
def spin_out(ctx, p):
    q = stg(p, ord_lr(ctx), 0.45)
    i = gi(ctx)
    return out(ctx, p, rot=side(ctx, 3) * np.where(i % 2, 1.0, 0.8) * 250 * in_quad(q),
               s=np.maximum(0.01, 1 - in_cubic(q)), dy=-np.sin(np.pi * q) * 0.18, a=1 - smooth(0.8, 1, q),
               hide=q >= 1)


@xpart("twist", "Ribbon Twist", ("pop", "graphic"), 0.8)
def twist(ctx, p):
    flat = 1 - in_quad(clip((p - 0.55) / 0.45))                 # the ribbon finally goes edge-on
    th = clip(p) ** 1.3 * (0.5 + 2 * ord_lr(ctx)) * np.pi
    return out(ctx, p, pitch=np.degrees(np.arccos(np.clip(np.cos(th) * flat, -1, 1))), a=1 - smooth(0.9, 1, p))


@xpart("wave_out", "Wave Breaks", ("pop", "emotional"), 0.9)
def wave_out(ctx, p):
    q = stg(p, ord_lr(ctx), 0.55)
    A = 0.42
    return out(ctx, p, dy=-np.sin(q * np.pi) * A + q * q * A * 2.6, dx=q * A * 0.6,
               rot=np.sin(q * np.pi * 1.5) * 28 + q * 30, a=1 - smooth(0.45, 1, q), hide=q >= 1)


@xpart("blur_stagger", "Blur Out by Letter", ("calm", "emotional"))
def blur_stagger(ctx, p):
    q = stg(p, ord_lr(ctx), 0.55)
    e = in_out_sine(q)
    return out(ctx, p, a=1 - q, dy=-e * 0.12, s=1 + e * 0.22, hide=q >= 1)


@xpart("melt", "Melt Down", ("emotional", "glitch"), 0.8, 0.8)
def melt(ctx, p):
    sy = 1 + 0.8 * in_quad(p)                                       # stretched down from the top
    return out(ctx, p, sy=sy, sx=1 - 0.05 * clip(p), dy=(sy - 1) * 0.5, a=1 - smooth(0.55, 1, p))


@xpart("crumble", "Crumble Bit by Bit", ("calm", "emotional"), 0.9)
def crumble(ctx, p):
    i = gi(ctx)
    t0 = _r(ctx.seed, i, 72) * 0.65
    x = clip((p - t0) / 0.3)
    gone = (x >= 1) | ((x > 0) & (_r(ctx.seed, step(p, 16), i, 73) < x))
    return out(ctx, p, dy=-0.05 * x, s=1 + 0.1 * x, hide=gone)


@xpart("backspace", "Erased by Backspace", ("editorial", "glitch"), 0.8, 0.9)
def backspace(ctx, p):
    n = max(ctx.n, 1)
    deleted = clip((p - 0.1) / 0.8) ** 1.3
    return out(ctx, p, hide=deleted > (n - 1 - gi(ctx)) / n)


@xpart("whip_out", "Whip Away", ("pop", "graphic"))
def whip_out(ctx, p):
    d = 1.0 if _r(ctx.seed, 4, 991) < 0.5 else -1.0
    pb = 0.14 * o_cubic(clip(p / 0.28))
    u = clip((p - 0.26) / 0.74)
    v = np.minimum(1.6, 2 * u)
    return whole(ctx, p, dx=d * ((SCREEN_W + ctx.n + 2) * u * u - pb * (1 - u)), sx=1 + v * 0.55, sy=1 - v * 0.08,
                 a=1 - smooth(0.9, 1, p))


@xpart("gravity", "Drop with Gravity", ("pop", "emotional"), 1.0, 0.75)
def gravity(ctx, p):
    i = gi(ctx)
    q = clip((p - _r(ctx.seed, i, 901) * 0.4) / 0.6)
    D = SCREEN_H
    h = 0.12 + 0.22 * _r(ctx.seed, i, 902)
    v0 = 2 * h + np.sqrt(4 * h * h + 4 * h * D)
    return out(ctx, p, dy=-v0 * q + (D + v0) * q * q, dx=_rs(ctx.seed, i, 903) * 0.9 * q,
               rot=_rs(ctx.seed, i, 904) * 240 * q * q, a=1 - smooth(0.92, 1, q), hide=q >= 1)


@xpart("pop_out", "Pop Away", ("pop",))
def pop_out(ctx, p):
    i = gi(ctx)
    q = stg(p, 0.6 * ord_lr(ctx) + 0.4 * _r(ctx.seed, i, 1001), 0.5)
    u = clip(q / 0.55)
    w = 0.07 * np.sin(u * 26) * u
    return out(ctx, p, s=1 + 0.5 * u * u, sx=1 + w, sy=1 - w, hide=q >= 0.55)


@xpart("crumple", "Crumple and Toss", ("pop", "emotional"), 0.9, 0.85)
def crumple(ctx, p):
    ob = lambda x: 1 + 2.6 * (x - 1) ** 3 + 1.6 * (x - 1) ** 2      # outBack(x, 1.6)
    g = [ob(clip((p - a) / 0.15)) for a in (0.0, 0.17, 0.34)]
    cr = np.clip(0.45 * g[0] + 0.3 * g[1] + 0.25 * g[2], 0, 1.08)
    v = clip((p - 0.5) / 0.5)
    d = 1.0 if _r(ctx.seed, 21, 991) < 0.5 else -1.0
    return whole(ctx, p, s=1 - 0.93 * np.minimum(1, cr), rot=d * (cr * 25 + 620 * v * v),
                 dx=d * SCREEN_W * 0.42 * v, dy=-SCREEN_H * 0.8 * v + SCREEN_H * 1.75 * v * v, a=1 - smooth(0.88, 1, p))


@xpart("sand_out", "Blown Away as Sand", ("emotional", "calm"), 1.0, 0.9)
def sand_out(ctx, p):
    d = 1.0 if _r(ctx.seed, 71, 991) < 0.5 else -1.0
    pos = ord_lr(ctx) if d < 0 else 1 - ord_lr(ctx)
    x = clip((p - pos * 0.5) / 0.5)
    k1 = _r(ctx.seed, gi(ctx), 82)
    lift = 0.55 * x + np.sin(x * 5 + k1 * 6) * 0.07 * x
    return out(ctx, p, dx=d * (3 + SCREEN_W * 0.18) * x * x, dy=-lift, a=1 - x, s=1 - 0.4 * x, sx=1 + x,
               hide=x >= 1)


@xpart("domino_out", "Dominoes Fall", ("pop", "graphic"), 0.9, 0.85)
def domino_out(ctx, p):
    sgn = -1.0 if _r(ctx.seed, 91, 991) < 0.5 else 1.0
    o = ord_lr(ctx) if sgn > 0 else 1 - ord_lr(ctx)
    q = stg(p, o, 0.55)
    tf = 0.62
    u = clip((q - tf) / (1 - tf))
    th = np.where(q < tf, 90 * in_cubic(q / tf), 90 - 10 * np.sin(np.pi * np.minimum(1, u * 1.6)) * (1 - u))
    px, py = sgn * 0.5, 0.5                                   # bottom corner on the falling side (dy down)
    r = sgn * th * DEG
    rx, ry = -px * np.cos(r) + py * np.sin(r), -px * np.sin(r) - py * np.cos(r)
    sink = 0.9 * in_quad(clip((p - 0.7) / 0.3))
    return out(ctx, p, dx=px + rx, dy=py + ry + sink, rot=sgn * th, a=1 - smooth(0.74, 0.98, p))


@xpart("hinge_out", "Pin Comes Loose", ("pop", "editorial"), 0.9, 0.95)
def hinge_out(ctx, p):
    cx, cz = centred(ctx)
    left = _r(ctx.seed, 102, 991) >= 0.5
    sg = 1.0 if left else -1.0
    ax = (cx.min() - 0.5 + 0.14) if left else (cx.max() + 0.5 - 0.14)
    az = cz.max() + 0.5 - 0.12
    u, v = clip(p / 0.64), clip((p - 0.64) / 0.36)
    th = sg * (40 * (1 - np.exp(-u * 4.5) * np.cos(u * 12)) + 30 * v * v)
    dx, dy = _turn(cx, cz, ax, az, th)
    return out(ctx, p, dx=dx + sg * 0.4 * v, dy=dy + SCREEN_H * 1.25 * v * v, rot=th, a=1 - smooth(0.9, 1, p))


@xpart("rocket_off", "Lift Off", ("pop",), 0.9, 0.9)
def rocket_off(ctx, p):
    i = gi(ctx)
    q = stg(p, _r(ctx.seed, i, 111) * 0.85, 0.55)
    u0 = clip(q / 0.3)
    sq = np.sin(u0 * np.pi / 2)
    k, w = 1 - 0.22 * sq, 1 + 0.12 * sq
    shake = _rs(ctx.seed, i, step(p), 112) * 0.02 * u0
    u = clip((q - 0.3) / 0.7)
    st = 1 + np.minimum(0.8, 3 * u * u)
    up = q >= 0.3
    return out(ctx, p, dx=np.where(up, 0.0, shake), dy=np.where(up, -(SCREEN_H + 2) * u ** 2.3, (1 - k) * 0.5),
               sx=np.where(up, 1 - 0.12 * (st - 1), w), sy=np.where(up, st, k), hide=q >= 1)


@xpart("balloon_off", "Float Off like a Balloon", ("emotional", "calm", "pop"), 0.9, 1.0)
def balloon_off(ctx, p):
    i = gi(ctx)
    q = stg(p, _r(ctx.seed, i, 141), 0.45)
    ph, w = _r(ctx.seed, i, 142) * TAU, 7 + 3 * _r(ctx.seed, i, 143)
    amp = np.minimum(1, q * 3)
    return out(ctx, p, dx=np.sin(q * w + ph) * 0.22 * amp, dy=-(SCREEN_H + 2) * q ** 1.7,
               rot=-np.cos(q * w + ph) * 11 * amp, s=1 + 0.07 * np.sin(np.pi * np.minimum(1, q * 2.5)), hide=q >= 1)


@xpart("deflate", "Deflate and Fly", ("pop",), 0.8, 0.85)
def deflate(ctx, p):
    i = gi(ctx)
    q = stg(p, _r(ctx.seed, i, 151) * 0.8, 0.4)
    puff = q < 0.16
    u0 = clip(q / 0.16)
    u = clip((q - 0.16) / 0.81)
    th0 = _r(ctx.seed, i, 153) * TAU
    x = y = 0.0
    th = th0
    for k in range(14):                                     # integrate an erratic heading
        t = (k + 0.5) / 14 * u
        th = th0 + 7 * noise1_np(t * 5, ctx.seed + i * 7) + 3 * t
        vel = 7.5 * (0.5 + t) * (u / 14)
        x, y = x + np.cos(th) * vel, y + np.sin(th) * vel
    wob = np.sin(u * 70) * 0.14 * (1 - u)
    pw = 0.05 * np.sin(u0 * 25)
    return out(ctx, p, dx=np.where(puff, 0.0, x), dy=np.where(puff, 0.0, y),
               rot=np.where(puff, _rs(ctx.seed, i, 152) * 4 * u0, (th - th0) / DEG * 0.5),
               s=np.where(puff, 1 + 0.16 * o_cubic(u0), 1.16 * (1 - u ** 1.3)),
               sx=np.where(puff, 1 + pw, 1 + wob), sy=np.where(puff, 1 - pw, 1 - wob), hide=q >= 0.97)


@xpart("lamp_off", "Lights Go Out", ("glitch", "emotional"), 0.8)
def lamp_off(ctx, p):
    i = gi(ctx)
    q = (p - _r(ctx.seed, i, 171) * 0.46) / 0.36
    off = _r(ctx.seed, i, step(p), 172) < 0.3 + 0.7 * (q / 0.55)
    a = np.where(q > 0.55, 0.45 * (1 - (q - 0.55) / 0.45), np.where(off, 0.35, 1.0))
    return out(ctx, p, a=np.where(q <= 0, 1.0, a), hide=q >= 1)


@xpart("tornado", "Tornado", ("pop",), 0.8, 0.9)
def tornado(ctx, p):
    cx, cz = centred(ctx)
    i = gi(ctx)
    d = 1.0 if _r(ctx.seed, 211, 991) < 0.5 else -1.0
    R0 = float(np.abs(cx).max()) + 0.3 + 0.5 if ctx.n else 1.0
    r = _r(ctx.seed, i, 212)
    q = clip(p)
    th0 = np.arcsin(np.clip(cx / R0, -1, 1))
    th = th0 + d * np.pi * (3.2 + r) * q * q
    lift = (SCREEN_H + 1.8) * q ** 2.2 * (0.8 + 0.3 * r) + 1.4 * ord_lr(ctx) * o_cubic(q)
    R = R0 * (1 - 0.35 * o_cubic(q)) + lift * 0.25 + 0.6 * q
    return out(ctx, p, dx=R * np.sin(th) - cx, dy=-lift, back=(np.cos(th0) - np.cos(th)) * R,
               rot=-np.sin(th) * 14 * q, a=1 - smooth(0.8, 0.98, p))


@xpart("roll_off", "Roll Away", ("pop",), 0.8, 0.9)
def roll_off(ctx, p):
    d = 1.0 if _r(ctx.seed, 251, 991) < 0.5 else -1.0
    o = 1 - ord_lr(ctx) if d > 0 else ord_lr(ctx)
    q = stg(p, o, 0.45)
    along = (SCREEN_W / 2 + ctx.n / 2 + 1.3) * q ** 1.7
    th = along / 0.5                                         # rolling without slipping
    ph = np.mod(th, np.pi / 2)
    rise = 0.5 * (np.sqrt(2) * np.cos(ph - np.pi / 4) - 1)   # the centre rides up over each corner
    return out(ctx, p, dx=d * along, dy=-rise, rot=d * np.degrees(th), hide=q >= 1)


@xpart("flutter", "Flutter Down", ("emotional", "calm"), 1.0, 1.0)
def flutter(ctx, p):
    i = gi(ctx)
    q = stg(p, _r(ctx.seed, i, 241), 0.5)
    ph, w = _r(ctx.seed, i, 242) * TAU, 7 + 4 * _r(ctx.seed, i, 243)
    amp = np.minimum(1, q * 4)
    flip = np.cos(q * (9 + 5 * _r(ctx.seed, i, 244)) + ph * 0.5)
    shiver = np.where(q < 0.08, np.sin(q * 300) * 6 * (1 - q / 0.08), 0.0)
    turn = np.degrees(np.arccos(np.clip(1 + (flip - 1) * amp, -1, 1)))          # sx 1 -> flip, as a real turn
    return out(ctx, p, dx=np.sin(q * w + ph) * 0.55 * amp, dy=SCREEN_H * (0.25 * q + 0.75 * q ** 1.6),
               rot=np.cos(q * w + ph) * 28 * amp + shiver, yaw=turn, hide=q >= 1)


@xpart("candle_out", "Blown Out", ("emotional", "calm"), 0.9, 0.9)
def candle_out(ctx, p):
    i = gi(ctx)
    d = 1.0 if _r(ctx.seed, 321, 991) < 0.5 else -1.0
    o = ord_lr(ctx) if d > 0 else 1 - ord_lr(ctx)
    u = (p - o * 0.42) / 0.5
    lean = np.sin(np.pi * np.minimum(1, clip(u) / 0.45))
    fl = _r(ctx.seed, i, step(p), 322)
    a = np.where(u > 0.3, (1 - (u - 0.3) / 0.15) * np.where(fl < 0.5, 1.0, 0.6), 0.65 + 0.35 * fl)
    return out(ctx, p, rot=d * 10 * lean, dx=d * 0.06 * lean, s=1 + 0.04 * lean, a=np.where(u <= 0, 1.0, a),
               hide=u >= 0.45)


# ---------------- horror ----------------

@xpart("hr_pulled_down", "Dragged Under", ("horror", "glitch", "emotional"), 1.0, 0.9, group="horror")
def hr_pulled_down(ctx, p):
    i = gi(ctx)
    last = int(_r(ctx.seed, 41, 991) * max(ctx.n, 1))
    is_last = i == last
    t0 = np.where(is_last, 0.7, _r(ctx.seed, i, 42) * 0.5)
    q = (p - t0) / 0.28
    st = step(p)
    tr = clip(1 + q * 1.5) * np.where(is_last, 1.6, 0.6) * clip(p * 20)
    shake = q < 0
    qq = clip(q)
    return out(ctx, p, dx=np.where(shake, _rs(ctx.seed, i, st, 43) * 0.03 * tr, 0.0),
               dy=np.where(shake, _rs(ctx.seed, i, st, 44) * 0.02 * tr, qq * qq * SCREEN_H * 1.1),
               rot=np.where(shake, _rs(ctx.seed, i, st, 45) * 6 * tr, _rs(ctx.seed, i, 46) * 12 * qq),
               sy=1 + qq * 1.8, sx=1 - qq * 0.3, a=1 - in_cubic(qq), hide=q >= 1)


@xpart("hr_turn_away", "Turns Its Back", ("horror", "calm", "emotional"), 0.9, 0.9, group="horror")
def hr_turn_away(ctx, p):
    q = clip((p - ord_lr(ctx) * 0.4) / 0.6)
    return out(ctx, p, yaw=q * 0.95 * 180, a=1 - smooth(0.6, 1, q), dy=q * 0.08, hide=q >= 1)


@xpart("hr_shiver", "Shiver Away", ("horror", "glitch"), 0.9, 0.8, group="horror")
def hr_shiver(ctx, p):
    i = gi(ctx)
    st = step(p)
    amp = (0.025 + 0.13 * p) * clip(p * 10)
    return out(ctx, p, dx=_rs(ctx.seed, i, st, 62) * amp, dy=_rs(ctx.seed, i, st, 63) * amp,
               rot=_rs(ctx.seed, i, st, 64) * 14 * p, hide=p >= 0.3 + _r(ctx.seed, i, 61) * 0.62)


@xpart("hr_flicker_die", "Flicker and Die", ("horror", "glitch"), 0.9, 0.8, group="horror")
def hr_flicker_die(ctx, p):
    cx, _ = centred(ctx)
    st = step(p)
    dead = (p > 0.92) | (_r(ctx.seed, st, 81) > (1 - clip(p)) ** 1.3 * 0.95)
    mirror = (_r(ctx.seed, st, 82) < 0.22) & (p > 0.15)
    return out(ctx, p, dx=np.where(mirror, -2 * cx, 0.0), yaw=np.where(mirror, 180.0, 0.0),
               dy=np.where(mirror, _rs(ctx.seed, st, 83) * 0.1, 0.0),
               a=np.where(mirror, 1.0, 0.55 + 0.45 * _r(ctx.seed, st, 84)), live=p > 0, hide=dead & (p > 0))


# ---------------- kinetic ----------------

@xpart("kn_word_kick", "Words Kicked Out", ("pop", "graphic"), 1.0, 0.75, group="kinetic")
def kn_word_kick(ctx, p):
    j, n, cx, cz, wc, *_ = words(ctx)
    q = stg(p, j / (n - 1) if n > 1 else 0.0, 0.4 if n > 1 else 0.0)
    up = np.where(j % 2, 1.0, -1.0)
    e = in_cubic(q)
    th = up * 70 * e
    dx, dy = _turn(cx, cz, wc, 0.0 * cz, th)
    return out(ctx, p, dx=dx + up * 0.6 * e, dy=dy + up * SCREEN_H * 0.9 * e - up * 0.25 * bell(q * 2), rot=th,
               a=1 - in_quad(clip((q - 0.45) / 0.55)), hide=q >= 1)


@xpart("kn_launch", "Launch Off", ("pop", "graphic"), 0.9, 0.65, group="kinetic")
def kn_launch(ctx, p):
    d = side(ctx, 71)
    back = ord_rl(ctx) if d > 0 else ord_lr(ctx)
    q = clip((p - back * 0.35) / 0.65)
    e = in_cubic(q) - 0.06 * bell(clip(p / 0.18))           # a small wind-up before the pull
    st = 1 + np.minimum(1.2, 3 * q * q * 0.35)
    return out(ctx, p, dx=d * SCREEN_W * 1.25 * e, sx=st, sy=1 / np.sqrt(st), hide=q >= 1)


@xpart("kn_word_blink", "Words Blink Off", ("pop", "glitch", "graphic"), 0.9, 0.8, group="kinetic")
def kn_word_blink(ctx, p):
    j, n, cx, cz, wc, *_ = words(ctx)
    if _r(ctx.seed, 73, 991) < 0.5:
        j = n - 1 - j
    w0, w1 = j / n, (j + 1) / n
    q = clip((p - w0) / (w1 - w0))
    s = 1 + 0.16 * bell(q * 1.4)
    return out(ctx, p, s=s, dx=(cx - wc) * (s - 1), dy=-cz * (s - 1), a=np.where(q > 0.7, 0.35, 1.0),
               hide=(p >= w1) | (p >= 0.999))


# ---------------- typo ----------------

@xpart("ty_key_last", "Key Letter Stays", ("emotional", "pop", "graphic"), 0.9, group="typo")
def ty_key_last(ctx, p):
    ki = key_glyph(ctx)
    cx, cz = centred(ctx)
    i = gi(ctx)
    md = max(1.0, float(np.abs(i - ki).max())) if ctx.n else 1.0
    kq = clip((p - 0.45) / 0.55)
    q = clip((p - (1 - np.abs(i - ki) / md) * 0.2) / 0.45)
    e = in_cubic(q)
    key = i == ki
    return out(ctx, p, dx=np.where(key, 0.0, (cx[ki] - cx) * e), dy=np.where(key, 0.0, -(cz[ki] - cz) * e),
               s=np.where(key, 1 + in_cubic(kq) * 1.8, 1 - 0.6 * e), a=np.where(key, 1 - in_cubic(kq), 1 - e),
               hide=np.where(key, kq >= 1, q >= 1))
